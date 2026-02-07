# components/devices/control_zone/plc/vendor_specific/s7_plc.py
"""
Siemens S7 PLC base class for UU Power & Light Co.

Generic Siemens S7-300/400/1200/1500 style PLC with:
- Data Blocks (DBs) for structured data
- Process Image Input/Output (PI/PQ)
- Merker (flag) memory area
- S7comm and Profinet protocol support
"""

from abc import abstractmethod
from typing import Any

from components.devices.control_zone.plc.generic.base_plc import BasePLC
from components.state.data_store import DataStore


class S7PLC(BasePLC):
    """
    Generic Siemens S7 PLC with S7-style memory model.

    Memory Areas (per IEC 61131-3 / Siemens addressing):
    - DB (Data Blocks): Structured data storage (DB1.DBW0, DB1.DBD4, etc.)
    - I (Inputs): Process image inputs (I0.0, IW0, ID0)
    - Q (Outputs): Process image outputs (Q0.0, QW0, QD0)
    - M (Merkers): Internal flags/memory (M0.0, MW0, MD0)

    Protocols:
    - S7comm (native Siemens protocol)
    - Profinet (industrial Ethernet)
    - Modbus TCP (optional)

    Subclasses should implement:
    - _initialise_memory_map(): Define DB structure
    - _read_inputs(): Read from physics/sensors
    - _execute_logic(): PLC program logic
    - _write_outputs(): Write to actuators

    Example:
        >>> class MyS7PLC(S7PLC):
        ...     def _initialise_memory_map(self):
        ...         return {
        ...             "DB1": {"temperature": 0.0, "pressure": 0.0},
        ...             "DB2": {"setpoint": 100.0},
        ...         }
    """

    # S7 memory area sizes (bytes)
    DEFAULT_INPUT_SIZE = 128  # PI area
    DEFAULT_OUTPUT_SIZE = 128  # PQ area
    DEFAULT_MERKER_SIZE = 256  # M area

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        description: str = "Siemens S7 PLC",
        scan_interval: float = 0.1,
        rack: int = 0,
        slot: int = 2,
        s7_port: int = 102,
    ):
        """
        Initialise Siemens S7 PLC.

        Args:
            device_name: Unique device identifier
            device_id: Device ID for DataStore
            data_store: Reference to DataStore
            description: PLC description
            scan_interval: Scan cycle time in seconds
            rack: S7 rack number (typically 0)
            slot: S7 slot number (typically 2 for CPU)
            s7_port: S7comm TCP port (default 102)
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
        )

        # S7-specific configuration
        self.rack = rack
        self.slot = slot
        self.s7_port = s7_port

        # S7 memory areas
        self.inputs = bytearray(self.DEFAULT_INPUT_SIZE)  # I area
        self.outputs = bytearray(self.DEFAULT_OUTPUT_SIZE)  # Q area
        self.merkers = bytearray(self.DEFAULT_MERKER_SIZE)  # M area
        self.data_blocks: dict[int, dict[str, Any]] = {}  # DB areas

        self.logger.info(f"S7PLC '{device_name}' created (rack={rack}, slot={slot})")

    def _device_type(self) -> str:
        """Return device type for DataStore registration."""
        return "s7_plc"

    def _supported_protocols(self) -> list[str]:
        """Return list of supported protocols."""
        return ["s7", "profinet", "modbus"]

    # ----------------------------------------------------------------
    # S7 Data Block operations
    # ----------------------------------------------------------------

    async def create_db(self, db_number: int, structure: dict[str, Any]) -> bool:
        """
        Create a Data Block with specified structure.

        Args:
            db_number: DB number (e.g., 1 for DB1)
            structure: Dictionary defining DB variables and initial values

        Returns:
            True if created successfully
        """
        if db_number in self.data_blocks:
            self.logger.warning(
                f"S7PLC '{self.device_name}': DB{db_number} already exists"
            )
            return False

        self.data_blocks[db_number] = structure.copy()

        await self.logger.log_audit(
            message=f"S7PLC '{self.device_name}': Created DB{db_number} with {len(structure)} variables",
            user="engineer",
            action="s7_create_db",
            result="SUCCESS",
            data={
                "device": self.device_name,
                "db_number": db_number,
                "variable_count": len(structure),
                "variables": list(structure.keys()),
            },
        )

        self.logger.debug(
            f"S7PLC '{self.device_name}': Created DB{db_number} "
            f"with {len(structure)} variables"
        )
        return True

    def read_db(self, db_number: int, variable: str | None = None) -> Any:
        """
        Read from a Data Block.

        Args:
            db_number: DB number to read from
            variable: Specific variable name, or None for entire DB

        Returns:
            Variable value, entire DB dict, or None if not found
        """
        if db_number not in self.data_blocks:
            return None

        if variable is None:
            return self.data_blocks[db_number].copy()

        return self.data_blocks[db_number].get(variable)

    async def write_db(self, db_number: int, variable: str, value: Any, user: str = "system") -> bool:
        """
        Write to a Data Block variable.

        Args:
            db_number: DB number to write to
            variable: Variable name within the DB
            value: Value to write
            user: User/system performing the write (for audit trail)

        Returns:
            True if written successfully
        """
        if db_number not in self.data_blocks:
            self.logger.error(
                f"S7PLC '{self.device_name}': DB{db_number} does not exist"
            )
            return False

        if variable not in self.data_blocks[db_number]:
            self.logger.error(
                f"S7PLC '{self.device_name}': "
                f"Variable '{variable}' not in DB{db_number}"
            )
            return False

        old_value = self.data_blocks[db_number][variable]
        self.data_blocks[db_number][variable] = value

        await self.logger.log_audit(
            message=f"S7PLC '{self.device_name}': DB{db_number}.{variable} changed from {old_value} to {value}",
            user=user,
            action="s7_write_db",
            result="SUCCESS",
            data={
                "device": self.device_name,
                "db_number": db_number,
                "variable": variable,
                "old_value": old_value,
                "new_value": value,
            },
        )

        return True

    # ----------------------------------------------------------------
    # S7 I/O operations (bit, byte, word, double word)
    # ----------------------------------------------------------------

    def read_input_bit(self, byte_addr: int, bit_addr: int) -> bool:
        """Read input bit (e.g., I0.0)."""
        if 0 <= byte_addr < len(self.inputs) and 0 <= bit_addr <= 7:
            return bool(self.inputs[byte_addr] & (1 << bit_addr))
        return False

    def read_input_byte(self, byte_addr: int) -> int:
        """Read input byte (e.g., IB0)."""
        if 0 <= byte_addr < len(self.inputs):
            return self.inputs[byte_addr]
        return 0

    def read_input_word(self, byte_addr: int) -> int:
        """Read input word (e.g., IW0) - big-endian."""
        if 0 <= byte_addr < len(self.inputs) - 1:
            return (self.inputs[byte_addr] << 8) | self.inputs[byte_addr + 1]
        return 0

    def write_output_bit(self, byte_addr: int, bit_addr: int, value: bool) -> bool:
        """Write output bit (e.g., Q0.0)."""
        if 0 <= byte_addr < len(self.outputs) and 0 <= bit_addr <= 7:
            if value:
                self.outputs[byte_addr] |= 1 << bit_addr
            else:
                self.outputs[byte_addr] &= ~(1 << bit_addr)
            return True
        return False

    def write_output_byte(self, byte_addr: int, value: int) -> bool:
        """Write output byte (e.g., QB0)."""
        if 0 <= byte_addr < len(self.outputs):
            self.outputs[byte_addr] = value & 0xFF
            return True
        return False

    def write_output_word(self, byte_addr: int, value: int) -> bool:
        """Write output word (e.g., QW0) - big-endian."""
        if 0 <= byte_addr < len(self.outputs) - 1:
            self.outputs[byte_addr] = (value >> 8) & 0xFF
            self.outputs[byte_addr + 1] = value & 0xFF
            return True
        return False

    # ----------------------------------------------------------------
    # S7 Merker (flag) operations
    # ----------------------------------------------------------------

    def read_merker_bit(self, byte_addr: int, bit_addr: int) -> bool:
        """Read merker bit (e.g., M0.0)."""
        if 0 <= byte_addr < len(self.merkers) and 0 <= bit_addr <= 7:
            return bool(self.merkers[byte_addr] & (1 << bit_addr))
        return False

    def write_merker_bit(self, byte_addr: int, bit_addr: int, value: bool) -> bool:
        """Write merker bit (e.g., M0.0)."""
        if 0 <= byte_addr < len(self.merkers) and 0 <= bit_addr <= 7:
            if value:
                self.merkers[byte_addr] |= 1 << bit_addr
            else:
                self.merkers[byte_addr] &= ~(1 << bit_addr)
            return True
        return False

    def read_merker_word(self, byte_addr: int) -> int:
        """Read merker word (e.g., MW0) - big-endian."""
        if 0 <= byte_addr < len(self.merkers) - 1:
            return (self.merkers[byte_addr] << 8) | self.merkers[byte_addr + 1]
        return 0

    def write_merker_word(self, byte_addr: int, value: int) -> bool:
        """Write merker word (e.g., MW0) - big-endian."""
        if 0 <= byte_addr < len(self.merkers) - 1:
            self.merkers[byte_addr] = (value >> 8) & 0xFF
            self.merkers[byte_addr + 1] = value & 0xFF
            return True
        return False

    # ----------------------------------------------------------------
    # Memory map synchronisation
    # ----------------------------------------------------------------

    def _sync_memory_to_map(self) -> None:
        """Synchronise S7 memory areas to memory_map for DataStore."""
        # Sync Data Blocks
        for db_num, db_data in self.data_blocks.items():
            self.memory_map[f"DB{db_num}"] = db_data.copy()

        # Sync I/O as hex strings (for protocol handlers)
        self.memory_map["s7_inputs"] = self.inputs.hex()
        self.memory_map["s7_outputs"] = self.outputs.hex()
        self.memory_map["s7_merkers"] = self.merkers.hex()

        # S7 connection info
        self.memory_map["s7_rack"] = self.rack
        self.memory_map["s7_slot"] = self.slot

    # ----------------------------------------------------------------
    # Abstract methods - subclasses must implement
    # ----------------------------------------------------------------

    @abstractmethod
    def _initialise_memory_map(self) -> dict[str, Any]:
        """
        Initialise S7 memory map structure.

        Should create Data Blocks and return initial memory map.
        Call create_db() to set up DB structure.

        Returns:
            Initial memory map dictionary
        """
        pass

    @abstractmethod
    async def _read_inputs(self) -> None:
        """Read inputs from sensors/physics into I area and DBs."""
        pass

    @abstractmethod
    async def _execute_logic(self) -> None:
        """Execute PLC program logic."""
        pass

    @abstractmethod
    async def _write_outputs(self) -> None:
        """Write Q area and DB values to actuators/physics."""
        pass
