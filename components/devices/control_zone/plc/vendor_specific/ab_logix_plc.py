# components/devices/control_zone/plc/vendor_specific/ab_logix_plc.py
"""
Allen-Bradley ControlLogix/CompactLogix PLC base class for UU Power & Light Co.

Generic Rockwell Automation Logix-style PLC with:
- Tag-based addressing (no numeric memory addresses)
- Program-scoped and controller-scoped tags
- User-Defined Types (UDTs)
- EtherNet/IP and CIP protocol support
"""

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from components.devices.control_zone.plc.generic.base_plc import BasePLC
from components.state.data_store import DataStore


class LogixDataType(IntEnum):
    """Allen-Bradley Logix data types."""

    BOOL = 0xC1  # Boolean
    SINT = 0xC2  # 8-bit signed integer
    INT = 0xC3  # 16-bit signed integer
    DINT = 0xC4  # 32-bit signed integer
    LINT = 0xC5  # 64-bit signed integer
    REAL = 0xCA  # 32-bit float
    LREAL = 0xCB  # 64-bit float
    STRING = 0xD0  # String


@dataclass
class LogixTag:
    """Definition of a Logix tag."""

    name: str
    data_type: LogixDataType
    value: Any
    description: str = ""
    read_only: bool = False
    array_size: int = 0  # 0 = scalar, >0 = array


@dataclass
class LogixProgram:
    """Definition of a Logix program with its tags."""

    name: str
    tags: dict[str, LogixTag] = field(default_factory=dict)
    description: str = ""


class ABLogixPLC(BasePLC):
    """
    Generic Allen-Bradley ControlLogix/CompactLogix PLC.

    Memory Model:
    - Controller-scoped tags: Global tags accessible from any program
    - Program-scoped tags: Tags local to a specific program
    - Tag addressing: "TagName" or "Program:ProgramName.TagName"

    Protocols:
    - EtherNet/IP (CIP over Ethernet)
    - CIP Safety (for safety-rated I/O)
    - Modbus TCP (optional via AOI)

    Subclasses should implement:
    - _initialise_memory_map(): Define tag structure
    - _read_inputs(): Read from physics/sensors
    - _execute_logic(): Ladder/structured text logic
    - _write_outputs(): Write to actuators

    Example:
        >>> class MyLogixPLC(ABLogixPLC):
        ...     def _initialise_memory_map(self):
        ...         self.create_tag("Temperature", LogixDataType.REAL, 0.0)
        ...         self.create_tag("RunCommand", LogixDataType.BOOL, False)
        ...         return {"Temperature": 0.0, "RunCommand": False}
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        description: str = "Allen-Bradley ControlLogix PLC",
        scan_interval: float = 0.05,  # Logix typically faster scan
        slot: int = 0,
        enip_port: int = 44818,
    ):
        """
        Initialise Allen-Bradley Logix PLC.

        Args:
            device_name: Unique device identifier
            device_id: Device ID for DataStore
            data_store: Reference to DataStore
            description: PLC description
            scan_interval: Scan cycle time in seconds (Logix can do 1-10ms)
            slot: Chassis slot number for CPU
            enip_port: EtherNet/IP TCP port (default 44818)
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
        )

        # Logix-specific configuration
        self.slot = slot
        self.enip_port = enip_port

        # Tag database
        self.controller_tags: dict[str, LogixTag] = {}
        self.programs: dict[str, LogixProgram] = {}

        # Default program
        self.programs["MainProgram"] = LogixProgram(
            name="MainProgram",
            description="Main program task",
        )

        self.logger.info(f"ABLogixPLC '{device_name}' created (slot={slot})")

    def _device_type(self) -> str:
        """Return device type for DataStore registration."""
        return "ab_logix_plc"

    def _supported_protocols(self) -> list[str]:
        """Return list of supported protocols."""
        return ["ethernet_ip", "cip", "modbus"]

    # ----------------------------------------------------------------
    # Tag management
    # ----------------------------------------------------------------

    async def create_tag(
        self,
        name: str,
        data_type: LogixDataType,
        initial_value: Any,
        description: str = "",
        read_only: bool = False,
        program: str | None = None,
        array_size: int = 0,
    ) -> bool:
        """
        Create a new tag.

        Args:
            name: Tag name (no special characters except underscore)
            data_type: Logix data type
            initial_value: Initial tag value
            description: Tag description
            read_only: Whether tag is read-only
            program: Program name for program-scoped tag, None for controller-scoped
            array_size: 0 for scalar, >0 for array

        Returns:
            True if created successfully
        """
        tag = LogixTag(
            name=name,
            data_type=data_type,
            value=initial_value,
            description=description,
            read_only=read_only,
            array_size=array_size,
        )

        tag_path = name if program is None else f"Program:{program}.{name}"

        if program is None:
            # Controller-scoped tag
            if name in self.controller_tags:
                self.logger.warning(
                    f"ABLogixPLC '{self.device_name}': "
                    f"Controller tag '{name}' already exists"
                )
                return False
            self.controller_tags[name] = tag
            scope = "controller"
        else:
            # Program-scoped tag
            if program not in self.programs:
                self.programs[program] = LogixProgram(name=program)

            if name in self.programs[program].tags:
                self.logger.warning(
                    f"ABLogixPLC '{self.device_name}': "
                    f"Program tag 'Program:{program}.{name}' already exists"
                )
                return False
            self.programs[program].tags[name] = tag
            scope = f"program:{program}"

        await self.logger.log_audit(
            message=f"ABLogixPLC '{self.device_name}': Created {scope} tag '{tag_path}' ({data_type.name})",
            user="engineer",
            action="logix_create_tag",
            result="SUCCESS",
            data={
                "device": self.device_name,
                "tag_path": tag_path,
                "data_type": data_type.name,
                "scope": scope,
                "initial_value": initial_value,
                "read_only": read_only,
            },
        )

        self.logger.debug(
            f"ABLogixPLC '{self.device_name}': Created {scope} tag '{tag_path}' ({data_type.name})"
        )

        return True

    def read_tag(self, tag_path: str) -> Any:
        """
        Read a tag value.

        Args:
            tag_path: Tag path - "TagName" for controller-scoped,
                      "Program:ProgramName.TagName" for program-scoped

        Returns:
            Tag value or None if not found
        """
        tag = self._resolve_tag(tag_path)
        if tag is None:
            return None
        return tag.value

    async def write_tag(self, tag_path: str, value: Any, user: str = "system") -> bool:
        """
        Write a tag value.

        Args:
            tag_path: Tag path
            value: Value to write
            user: User/system performing the write (for audit trail)

        Returns:
            True if written successfully
        """
        tag = self._resolve_tag(tag_path)
        if tag is None:
            self.logger.error(
                f"ABLogixPLC '{self.device_name}': Tag '{tag_path}' not found"
            )
            return False

        if tag.read_only:
            self.logger.error(
                f"ABLogixPLC '{self.device_name}': Tag '{tag_path}' is read-only"
            )
            return False

        old_value = tag.value

        # Type conversion based on data type
        try:
            if tag.data_type == LogixDataType.BOOL:
                tag.value = bool(value)
            elif tag.data_type in (
                LogixDataType.SINT,
                LogixDataType.INT,
                LogixDataType.DINT,
                LogixDataType.LINT,
            ):
                tag.value = int(value)
            elif tag.data_type in (LogixDataType.REAL, LogixDataType.LREAL):
                tag.value = float(value)
            elif tag.data_type == LogixDataType.STRING:
                tag.value = str(value)
            else:
                tag.value = value
        except (ValueError, TypeError) as e:
            self.logger.error(
                f"ABLogixPLC '{self.device_name}': "
                f"Type conversion error for '{tag_path}': {e}"
            )
            return False

        await self.logger.log_audit(
            message=f"ABLogixPLC '{self.device_name}': Tag '{tag_path}' changed from {old_value} to {tag.value}",
            user=user,
            action="logix_write_tag",
            result="SUCCESS",
            data={
                "device": self.device_name,
                "tag_path": tag_path,
                "data_type": tag.data_type.name,
                "old_value": old_value,
                "new_value": tag.value,
            },
        )

        return True

    def _resolve_tag(self, tag_path: str) -> LogixTag | None:
        """
        Resolve a tag path to a LogixTag object.

        Args:
            tag_path: Tag path string

        Returns:
            LogixTag or None if not found
        """
        # Check for program-scoped tag
        if tag_path.startswith("Program:"):
            # Format: "Program:ProgramName.TagName"
            try:
                _, rest = tag_path.split(":", 1)
                program_name, tag_name = rest.split(".", 1)

                if program_name in self.programs:
                    return self.programs[program_name].tags.get(tag_name)
            except ValueError:
                pass
            return None

        # Controller-scoped tag
        return self.controller_tags.get(tag_path)

    def get_all_tags(self) -> dict[str, Any]:
        """
        Get all tag values as a flat dictionary.

        Returns:
            Dictionary of tag_path: value
        """
        tags = {}

        # Controller tags
        for name, tag in self.controller_tags.items():
            tags[name] = tag.value

        # Program tags
        for prog_name, program in self.programs.items():
            for tag_name, tag in program.tags.items():
                tags[f"Program:{prog_name}.{tag_name}"] = tag.value

        return tags

    # ----------------------------------------------------------------
    # Convenience methods for common operations
    # ----------------------------------------------------------------

    async def create_bool_tag(
        self,
        name: str,
        initial_value: bool = False,
        program: str | None = None,
        description: str = "",
    ) -> bool:
        """Create a BOOL tag."""
        return await self.create_tag(
            name, LogixDataType.BOOL, initial_value, description, program=program
        )

    async def create_dint_tag(
        self,
        name: str,
        initial_value: int = 0,
        program: str | None = None,
        description: str = "",
    ) -> bool:
        """Create a DINT (32-bit integer) tag."""
        return await self.create_tag(
            name, LogixDataType.DINT, initial_value, description, program=program
        )

    async def create_real_tag(
        self,
        name: str,
        initial_value: float = 0.0,
        program: str | None = None,
        description: str = "",
    ) -> bool:
        """Create a REAL (32-bit float) tag."""
        return await self.create_tag(
            name, LogixDataType.REAL, initial_value, description, program=program
        )

    # ----------------------------------------------------------------
    # Memory map synchronisation
    # ----------------------------------------------------------------

    def _sync_tags_to_map(self) -> None:
        """Synchronise all tags to memory_map for DataStore."""
        # Flatten all tags into memory map
        self.memory_map["tags"] = self.get_all_tags()

        # EtherNet/IP configuration
        self.memory_map["enip_slot"] = self.slot
        self.memory_map["enip_port"] = self.enip_port

    # ----------------------------------------------------------------
    # Abstract methods - subclasses must implement
    # ----------------------------------------------------------------

    @abstractmethod
    def _initialise_memory_map(self) -> dict[str, Any]:
        """
        Initialise Logix tag structure.

        Should create tags using create_tag() and return initial memory map.

        Returns:
            Initial memory map dictionary
        """
        pass

    @abstractmethod
    async def _read_inputs(self) -> None:
        """Read inputs from sensors/physics into tags."""
        pass

    @abstractmethod
    async def _execute_logic(self) -> None:
        """Execute ladder logic / structured text."""
        pass

    @abstractmethod
    async def _write_outputs(self) -> None:
        """Write tag values to actuators/physics."""
        pass
