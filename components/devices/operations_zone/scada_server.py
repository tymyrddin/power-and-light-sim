# components/devices/operations_zone/scada_server.py
"""
SCADA Server device class.

Central Supervisory Control and Data Acquisition system that polls field devices,
aggregates data, manages alarms, and provides operator interface.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from components.devices.operations_zone.base_supervisory import (
    BaseSupervisoryDevice,
    PollTarget,
)
from components.security.logging_system import (
    AlarmPriority,
    AlarmState,
    EventSeverity,
)
from components.state.data_store import DataStore


@dataclass
class TagDefinition:
    """SCADA tag definition."""

    tag_name: str
    device_name: str
    address_type: str  # 'holding_register', 'coil', 'iec104_single_point', etc.
    address: int
    data_type: str = "int"  # 'int', 'float', 'bool'
    description: str = ""
    unit: str = ""
    alarm_high: float | None = None
    alarm_low: float | None = None


@dataclass
class Alarm:
    """Active alarm."""

    tag_name: str
    alarm_type: str  # 'high', 'low', 'change_of_state', 'comms_failure'
    triggered_at: float  # Simulation time when alarm was triggered
    acknowledged: bool = False
    value: Any = None
    message: str = ""


class SCADAServer(BaseSupervisoryDevice):
    """
    SCADA master station.

    Polls field devices (PLCs, RTUs, IEDs) over various protocols,
    aggregates data into a centralised tag database, manages alarms,
    and provides data to HMI workstations.

    Features:
    - Multi-protocol polling (Modbus, IEC 104, DNP3, OPC UA)
    - Tag database with live values
    - Alarm management
    - Historical data buffering
    - Device health monitoring

    Example:
        >>> scada = SCADAServer(
        ...     device_name="scada_master_1",
        ...     device_id=1,
        ...     data_store=data_store
        ... )
        >>>
        >>> # Configure polled devices
        >>> scada.add_poll_target(
        ...     device_name="turbine_plc_1",
        ...     protocol="modbus",
        ...     poll_rate_s=1.0
        ... )
        >>>
        >>> # Define tags
        >>> scada.add_tag(
        ...     tag_name="TURB1_SPEED",
        ...     device_name="turbine_plc_1",
        ...     address_type="holding_register",
        ...     address=0,
        ...     unit="RPM",
        ...     alarm_high=3960.0
        ... )
        >>>
        >>> await scada.start()  # initialise() is automatic
        >>>
        >>> # Read tag values
        >>> speed = await scada.get_tag_value("TURB1_SPEED")
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        description: str = "",
        scan_interval: float = 0.1,  # 100ms default (10 Hz)
        log_dir: Path | None = None,
    ):
        """
        Initialise SCADA server.

        Args:
            device_name: Unique device identifier
            device_id: Numeric ID for protocol addressing
            data_store: DataStore instance
            description: Human-readable description
            scan_interval: Main scan cycle rate in seconds
            log_dir: Directory for log files
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
            log_dir=log_dir,
        )

        # Tag database
        self.tags: dict[str, TagDefinition] = {}
        self.tag_values: dict[str, Any] = {}
        self.tag_timestamps: dict[str, float] = {}
        self.tag_quality: dict[str, str] = {}  # 'good', 'bad', 'uncertain'

        # Alarms
        self.active_alarms: list[Alarm] = []
        self.alarm_history: list[Alarm] = []
        self.total_alarms: int = 0

        self.logger.info(
            f"SCADAServer '{device_name}' initialised (scan_interval={scan_interval}s)"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return 'scada_server' as device type."""
        return "scada_server"

    def _supported_protocols(self) -> list[str]:
        """SCADA servers support multiple protocols."""
        return ["modbus", "iec104", "dnp3", "opcua"]

    async def _initialise_memory_map(self) -> None:
        """
        Initialise SCADA server memory map.

        Memory map structure:
        - Input registers for status/statistics (read-only)
        - Coils for control operations
        - Tag data containers
        """
        self.memory_map = {
            # Status (Input Registers - read-only)
            "input_registers[0]": 0,  # Poll count (low word)
            "input_registers[1]": 0,  # Poll count (high word)
            "input_registers[2]": 0,  # Failed polls
            "input_registers[3]": 0,  # Active alarm count
            # Control (Coils - read/write)
            "coils[0]": False,  # Acknowledge all alarms
            "coils[1]": False,  # Reset statistics
            "coils[2]": True,  # Polling enabled
            # Tag data (dict containers)
            "tag_values": {},
            "tag_quality": {},
            "tag_timestamps": {},
            "active_alarms": [],
        }

        # Initialise tag values
        for tag_name in self.tags:
            self.tag_values[tag_name] = None
            self.tag_timestamps[tag_name] = 0.0
            self.tag_quality[tag_name] = "uncertain"

        self.logger.debug(f"Memory map initialised with {len(self.tags)} tags")

    # ----------------------------------------------------------------
    # BaseSupervisoryDevice implementation
    # ----------------------------------------------------------------

    async def _poll_device(self, target: PollTarget) -> None:
        """
        Poll a specific device.

        Args:
            target: Poll target configuration
        """
        try:
            # Read device memory from DataStore
            device_memory = await self.data_store.bulk_read_memory(target.device_name)

            if device_memory:
                # Update tags from this device
                for tag_name, tag_def in self.tags.items():
                    if tag_def.device_name == target.device_name:
                        await self._update_tag_from_memory(
                            tag_name, tag_def, device_memory
                        )

                target.last_poll_success = True
                target.consecutive_failures = 0
            else:
                # Poll failed - no data returned
                target.last_poll_success = False
                target.consecutive_failures += 1

                # Mark tags as bad quality if failures persist
                if target.consecutive_failures >= 3:
                    for tag_name, tag_def in self.tags.items():
                        if tag_def.device_name == target.device_name:
                            self.tag_quality[tag_name] = "bad"
                            await self._raise_comms_alarm(tag_name)

        except Exception as e:
            self.logger.error(f"Error polling {target.device_name}: {e}")
            target.last_poll_success = False
            target.consecutive_failures += 1
            self.failed_polls += 1

    async def _process_polled_data(self) -> None:
        """Process polled data and sync to memory map."""
        # Update memory map with current tag data
        self.memory_map["tag_values"] = self.tag_values.copy()
        self.memory_map["tag_quality"] = self.tag_quality.copy()
        self.memory_map["tag_timestamps"] = self.tag_timestamps.copy()

        # Update statistics in registers
        self.memory_map["input_registers[0]"] = self.total_polls & 0xFFFF
        self.memory_map["input_registers[1]"] = (self.total_polls >> 16) & 0xFFFF
        self.memory_map["input_registers[2]"] = self.failed_polls
        self.memory_map["input_registers[3]"] = len(self.active_alarms)

        # Process control coils
        if self.memory_map.get("coils[0]"):  # Acknowledge all alarms
            # Log bulk alarm acknowledgment as audit event
            await self.logger.log_audit(
                message=f"SCADA: All alarms acknowledged on '{self.device_name}' ({len(self.active_alarms)} alarms)",
                user="modbus_client",
                action="alarm_ack_all",
                data={
                    "scada_server": self.device_name,
                    "alarm_count": len(self.active_alarms),
                },
            )

            for alarm in self.active_alarms:
                alarm.acknowledged = True
            self.memory_map["coils[0]"] = False  # Reset coil

        if self.memory_map.get("coils[1]"):  # Reset statistics
            # Log statistics reset as audit event
            await self.logger.log_audit(
                message=f"SCADA statistics reset on '{self.device_name}'",
                user="modbus_client",
                action="stats_reset",
                data={
                    "scada_server": self.device_name,
                    "previous_total_polls": self.total_polls,
                    "previous_failed_polls": self.failed_polls,
                },
            )

            self.total_polls = 0
            self.failed_polls = 0
            self.memory_map["coils[1]"] = False  # Reset coil

        # Sync polling enabled from coil
        self.polling_enabled = self.memory_map.get("coils[2]", True)

        # Update active alarms in memory map
        self.memory_map["active_alarms"] = [
            {
                "tag_name": a.tag_name,
                "type": a.alarm_type,
                "value": a.value,
                "message": a.message,
                "acknowledged": a.acknowledged,
            }
            for a in self.active_alarms
        ]

    async def _check_alarms(self) -> None:
        """Check all tags for alarm conditions."""
        for tag_name, tag_def in self.tags.items():
            value = self.tag_values.get(tag_name)
            quality = self.tag_quality.get(tag_name)

            if quality != "good" or value is None:
                continue

            # High alarm
            if tag_def.alarm_high is not None and value > tag_def.alarm_high:
                await self._raise_alarm(tag_name, "high", value)

            # Low alarm
            if tag_def.alarm_low is not None and value < tag_def.alarm_low:
                await self._raise_alarm(tag_name, "low", value)

    # ----------------------------------------------------------------
    # Tag management
    # ----------------------------------------------------------------

    async def add_tag(
        self,
        tag_name: str,
        device_name: str,
        address_type: str,
        address: int,
        data_type: str = "int",
        description: str = "",
        unit: str = "",
        alarm_high: float | None = None,
        alarm_low: float | None = None,
        user: str = "system",
    ) -> None:
        """
        Add a tag to the database.

        Args:
            tag_name: Unique tag identifier
            device_name: Source device
            address_type: Memory type ('holding_register', 'coil', etc.)
            address: Memory address
            data_type: Data type ('int', 'float', 'bool')
            description: Tag description
            unit: Engineering units
            alarm_high: High alarm limit
            alarm_low: Low alarm limit
            user: User adding the tag
        """
        self.tags[tag_name] = TagDefinition(
            tag_name=tag_name,
            device_name=device_name,
            address_type=address_type,
            address=address,
            data_type=data_type,
            description=description,
            unit=unit,
            alarm_high=alarm_high,
            alarm_low=alarm_low,
        )

        # Initialise tag value
        self.tag_values[tag_name] = None
        self.tag_timestamps[tag_name] = 0.0
        self.tag_quality[tag_name] = "uncertain"

        # Log tag configuration as audit event
        await self.logger.log_audit(
            message=f"SCADA tag configured on '{self.device_name}': {tag_name}",
            user=user,
            action="tag_config",
            data={
                "scada_server": self.device_name,
                "tag_name": tag_name,
                "device_name": device_name,
                "address_type": address_type,
                "address": address,
                "has_alarms": alarm_high is not None or alarm_low is not None,
            },
        )

        self.logger.debug(
            f"Tag added: {tag_name} -> {device_name}:{address_type}[{address}]"
        )

    async def _update_tag_from_memory(
        self, tag_name: str, tag_def: TagDefinition, device_memory: dict
    ) -> None:
        """Update a tag value from device memory."""
        if tag_def.address_type == "holding_register":
            registers = device_memory.get("holding_registers", {})
            value = registers.get(tag_def.address)

        elif tag_def.address_type == "coil":
            coils = device_memory.get("coils", {})
            value = coils.get(tag_def.address)

        elif tag_def.address_type == "input_register":
            registers = device_memory.get("input_registers", {})
            value = registers.get(tag_def.address)

        elif tag_def.address_type == "discrete_input":
            inputs = device_memory.get("discrete_inputs", {})
            value = inputs.get(tag_def.address)

        elif tag_def.address_type == "iec104_single_point":
            points = device_memory.get("iec104_single_points", {})
            value = points.get(tag_def.address)

        elif tag_def.address_type == "iec104_measured_value":
            values = device_memory.get("iec104_measured_values", {})
            value = values.get(tag_def.address)

        else:
            # Direct memory access by name
            value = device_memory.get(tag_def.address_type)

        if value is not None:
            old_value = self.tag_values.get(tag_name)
            self.tag_values[tag_name] = value
            self.tag_timestamps[tag_name] = self.sim_time.now()
            self.tag_quality[tag_name] = "good"

            # Check for change of state alarms
            if old_value != value and tag_def.data_type == "bool":
                await self._raise_cos_alarm(tag_name, value)

    # ----------------------------------------------------------------
    # Alarm management
    # ----------------------------------------------------------------

    async def _raise_alarm(self, tag_name: str, alarm_type: str, value: Any) -> None:
        """Raise an alarm if not already active."""
        # Check if alarm already active
        for alarm in self.active_alarms:
            if alarm.tag_name == tag_name and alarm.alarm_type == alarm_type:
                return  # Already active

        # Create new alarm
        alarm = Alarm(
            tag_name=tag_name,
            alarm_type=alarm_type,
            triggered_at=self.sim_time.now(),
            value=value,
            message=f"{tag_name} {alarm_type} alarm: {value}",
        )

        self.active_alarms.append(alarm)
        self.alarm_history.append(alarm)
        self.total_alarms += 1

        # Determine priority based on alarm type
        priority_map = {
            "high": AlarmPriority.HIGH,
            "low": AlarmPriority.MEDIUM,
            "comms_failure": AlarmPriority.HIGH,
            "change_of_state": AlarmPriority.LOW,
        }
        priority = priority_map.get(alarm_type, AlarmPriority.MEDIUM)

        await self.logger.log_alarm(
            message=f"ALARM: {alarm.message}",
            priority=priority,
            state=AlarmState.ACTIVE,
            device=self.device_name,
            data={
                "device": self.device_name,
                "tag_name": tag_name,
                "alarm_type": alarm_type,
                "value": value,
                "triggered_at": alarm.triggered_at,
            },
        )

    async def _raise_cos_alarm(self, tag_name: str, value: Any) -> None:
        """Raise change-of-state alarm."""
        await self._raise_alarm(tag_name, "change_of_state", value)

    async def _raise_comms_alarm(self, tag_name: str) -> None:
        """Raise communications failure alarm."""
        await self._raise_alarm(tag_name, "comms_failure", None)

    # ----------------------------------------------------------------
    # Public interface
    # ----------------------------------------------------------------

    async def get_tag_value(self, tag_name: str) -> Any | None:
        """Get current value of a tag."""
        return self.tag_values.get(tag_name)

    async def get_tag_info(self, tag_name: str) -> dict[str, Any] | None:
        """Get complete tag information."""
        if tag_name not in self.tags:
            return None

        return {
            "name": tag_name,
            "value": self.tag_values.get(tag_name),
            "timestamp": self.tag_timestamps.get(tag_name),
            "quality": self.tag_quality.get(tag_name),
            "definition": self.tags[tag_name],
        }

    async def get_all_tags(self) -> dict[str, Any]:
        """Get all tag values."""
        return {
            tag_name: {
                "value": self.tag_values.get(tag_name),
                "quality": self.tag_quality.get(tag_name),
                "timestamp": self.tag_timestamps.get(tag_name),
            }
            for tag_name in self.tags
        }

    async def get_active_alarms(self) -> list[Alarm]:
        """Get list of active alarms."""
        return self.active_alarms.copy()

    async def acknowledge_alarm(self, alarm_index: int, user: str = "operator") -> bool:
        """
        Acknowledge an active alarm.

        Args:
            alarm_index: Index of alarm to acknowledge
            user: User acknowledging the alarm
        """
        if 0 <= alarm_index < len(self.active_alarms):
            alarm = self.active_alarms[alarm_index]
            alarm.acknowledged = True

            # Log alarm acknowledgment as audit event
            await self.logger.log_audit(
                message=f"SCADA alarm acknowledged on '{self.device_name}': {alarm.tag_name}",
                user=user,
                action="alarm_ack",
                data={
                    "scada_server": self.device_name,
                    "tag_name": alarm.tag_name,
                    "alarm_type": alarm.alarm_type,
                    "alarm_value": alarm.value,
                    "alarm_duration_s": self.sim_time.now() - alarm.triggered_at,
                },
            )

            self.logger.info(f"Alarm acknowledged: {alarm.message}")
            return True
        return False

    async def get_telemetry(self) -> dict[str, Any]:
        """Get comprehensive SCADA telemetry."""
        return {
            "device_name": self.device_name,
            "device_type": "scada_server",
            "poll_targets": {
                name: {
                    "protocol": target.protocol,
                    "poll_rate_s": target.poll_rate_s,
                    "last_success": target.last_poll_success,
                    "consecutive_failures": target.consecutive_failures,
                }
                for name, target in self.poll_targets.items()
            },
            "tags": await self.get_all_tags(),
            "active_alarms": [
                {
                    "tag_name": a.tag_name,
                    "type": a.alarm_type,
                    "value": a.value,
                    "message": a.message,
                    "acknowledged": a.acknowledged,
                }
                for a in self.active_alarms
            ],
            "statistics": {
                "total_polls": self.total_polls,
                "failed_polls": self.failed_polls,
                "success_rate": (
                    ((self.total_polls - self.failed_polls) / self.total_polls * 100)
                    if self.total_polls > 0
                    else 0.0
                ),
                "total_alarms": self.total_alarms,
                "active_alarms": len(self.active_alarms),
            },
        }
