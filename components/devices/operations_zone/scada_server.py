# components/devices/scada_server.py
"""
SCADA Server device class.

Central Supervisory Control and Data Acquisition system that polls field devices,
aggregates data, manages alarms, and provides operator interface.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime

logger = logging.getLogger(__name__)


@dataclass
class PollTarget:
    """Configuration for a polled device."""

    device_name: str
    protocol: str  # 'modbus', 'iec104', 'dnp3', 'opcua'
    poll_rate_s: float = 1.0
    enabled: bool = True
    last_poll_time: float = 0.0
    last_poll_success: bool = False
    consecutive_failures: int = 0


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
    triggered_at: datetime
    acknowledged: bool = False
    value: Any = None
    message: str = ""


class SCADAServer:
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
        >>> await scada.initialise()
        >>> await scada.start()
        >>>
        >>> # Read tag values
        >>> speed = await scada.get_tag_value("TURB1_SPEED")
    """

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        scan_rate_hz: float = 1.0,
    ):
        """
        Initialise SCADA server.

        Args:
            device_name: Unique device identifier
            data_store: DataStore instance
            scan_rate_hz: Main scan cycle rate
        """
        self.device_name = device_name
        self.data_store = data_store
        self.sim_time = SimulationTime()

        # Configuration
        self.scan_rate_hz = scan_rate_hz
        self.scan_interval = 1.0 / scan_rate_hz

        # Poll targets (devices to poll)
        self.poll_targets: dict[str, PollTarget] = {}

        # Tag database
        self.tags: dict[str, TagDefinition] = {}
        self.tag_values: dict[str, Any] = {}
        self.tag_timestamps: dict[str, float] = {}
        self.tag_quality: dict[str, str] = {}  # 'good', 'bad', 'uncertain'

        # Alarms
        self.active_alarms: list[Alarm] = []
        self.alarm_history: list[Alarm] = []

        # Statistics
        self.total_polls = 0
        self.failed_polls = 0
        self.total_alarms = 0

        # Runtime state
        self._running = False
        self._scan_task: asyncio.Task | None = None
        self._poll_tasks: dict[str, asyncio.Task] = {}
        self._last_scan_time = 0.0

        logger.info(f"SCADAServer created: {device_name}, scan_rate={scan_rate_hz}Hz")

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialise SCADA server and register with DataStore."""
        await self.data_store.register_device(
            device_name=self.device_name,
            device_type="scada_server",
            device_id=hash(self.device_name) % 1000,
            protocols=["modbus", "iec104", "dnp3", "opcua"],  # Master supports all
            metadata={
                "scan_rate_hz": self.scan_rate_hz,
                "poll_target_count": len(self.poll_targets),
                "tag_count": len(self.tags),
            },
        )

        # Initialise tag values
        for tag_name in self.tags:
            self.tag_values[tag_name] = None
            self.tag_timestamps[tag_name] = 0.0
            self.tag_quality[tag_name] = "uncertain"

        await self._sync_to_datastore()

        logger.info(
            f"SCADAServer initialised: {self.device_name}, "
            f"{len(self.poll_targets)} poll targets, {len(self.tags)} tags"
        )

    async def start(self) -> None:
        """Start SCADA server polling."""
        if self._running:
            logger.warning(f"SCADAServer already running: {self.device_name}")
            return

        self._running = True
        self._last_scan_time = self.sim_time.now()

        # Start main scan cycle
        self._scan_task = asyncio.create_task(self._scan_cycle())

        # Start individual poll tasks for each device
        for device_name, poll_target in self.poll_targets.items():
            if poll_target.enabled:
                task = asyncio.create_task(self._poll_device(poll_target))
                self._poll_tasks[device_name] = task

        logger.info(f"SCADAServer started: {self.device_name}")

    async def stop(self) -> None:
        """Stop SCADA server polling."""
        if not self._running:
            return

        self._running = False

        # Stop main scan cycle
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None

        # Stop all poll tasks
        for task in self._poll_tasks.values():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._poll_tasks.clear()

        logger.info(f"SCADAServer stopped: {self.device_name}")

    # ----------------------------------------------------------------
    # Configuration
    # ----------------------------------------------------------------

    def add_poll_target(
        self,
        device_name: str,
        protocol: str,
        poll_rate_s: float = 1.0,
        enabled: bool = True,
    ) -> None:
        """
        Add a device to poll.

        Args:
            device_name: Name of device to poll
            protocol: Protocol to use ('modbus', 'iec104', 'dnp3', 'opcua')
            poll_rate_s: Polling interval in seconds
            enabled: Whether polling is enabled
        """
        self.poll_targets[device_name] = PollTarget(
            device_name=device_name,
            protocol=protocol,
            poll_rate_s=poll_rate_s,
            enabled=enabled,
        )

        logger.info(f"Poll target added: {device_name} ({protocol}) @ {poll_rate_s}s")

    def add_tag(
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

        logger.debug(
            f"Tag added: {tag_name} -> {device_name}:{address_type}[{address}]"
        )

    # ----------------------------------------------------------------
    # Scan cycle
    # ----------------------------------------------------------------

    async def _scan_cycle(self) -> None:
        """Main SCADA scan cycle - manages alarms and coordination."""
        logger.info(f"SCADA scan cycle started for {self.device_name}")

        while self._running:
            current_time = self.sim_time.now()

            try:
                # Check for alarms
                self._check_alarms()

                # Update statistics
                await self._update_statistics()

                # Sync to DataStore
                await self._sync_to_datastore()

            except Exception as e:
                logger.error(f"Error in SCADA scan cycle for {self.device_name}: {e}")

            self._last_scan_time = current_time
            await asyncio.sleep(self.scan_interval)

    async def _poll_device(self, poll_target: PollTarget) -> None:
        """
        Poll a specific device at its configured rate.

        Args:
            poll_target: Device polling configuration
        """
        while self._running:
            current_time = self.sim_time.now()

            try:
                # Read device memory from DataStore
                device_memory = await self.data_store.bulk_read_memory(
                    poll_target.device_name
                )

                if device_memory:
                    # Update tags from this device
                    for tag_name, tag_def in self.tags.items():
                        if tag_def.device_name == poll_target.device_name:
                            await self._update_tag_from_memory(
                                tag_name, tag_def, device_memory
                            )

                    poll_target.last_poll_success = True
                    poll_target.consecutive_failures = 0
                else:
                    # Poll failed
                    poll_target.last_poll_success = False
                    poll_target.consecutive_failures += 1

                    # Mark tags as bad quality if failures persist
                    if poll_target.consecutive_failures >= 3:
                        for tag_name, tag_def in self.tags.items():
                            if tag_def.device_name == poll_target.device_name:
                                self.tag_quality[tag_name] = "bad"
                                self._raise_comms_alarm(tag_name)

                poll_target.last_poll_time = current_time
                self.total_polls += 1

            except Exception as e:
                logger.error(f"Error polling {poll_target.device_name}: {e}")
                poll_target.last_poll_success = False
                poll_target.consecutive_failures += 1
                self.failed_polls += 1

            # Wait for next poll
            await asyncio.sleep(poll_target.poll_rate_s)

    async def _update_tag_from_memory(
        self, tag_name: str, tag_def: TagDefinition, device_memory: dict
    ) -> None:
        """Update a tag value from device memory."""
        # Extract value based on address type
        value = None

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
            # Update tag
            old_value = self.tag_values.get(tag_name)
            self.tag_values[tag_name] = value
            self.tag_timestamps[tag_name] = self.sim_time.now()
            self.tag_quality[tag_name] = "good"

            # Check for change of state alarms
            if old_value != value and tag_def.data_type == "bool":
                self._raise_cos_alarm(tag_name, value)

    def _check_alarms(self) -> None:
        """Check all tags for alarm conditions."""
        for tag_name, tag_def in self.tags.items():
            value = self.tag_values.get(tag_name)
            quality = self.tag_quality.get(tag_name)

            if quality != "good" or value is None:
                continue

            # High alarm
            if tag_def.alarm_high is not None and value > tag_def.alarm_high:
                self._raise_alarm(tag_name, "high", value)

            # Low alarm
            if tag_def.alarm_low is not None and value < tag_def.alarm_low:
                self._raise_alarm(tag_name, "low", value)

    def _raise_alarm(self, tag_name: str, alarm_type: str, value: Any) -> None:
        """Raise an alarm if not already active."""
        # Check if alarm already active
        for alarm in self.active_alarms:
            if alarm.tag_name == tag_name and alarm.alarm_type == alarm_type:
                return  # Already active

        # Create new alarm
        alarm = Alarm(
            tag_name=tag_name,
            alarm_type=alarm_type,
            triggered_at=datetime.now(),
            value=value,
            message=f"{tag_name} {alarm_type} alarm: {value}",
        )

        self.active_alarms.append(alarm)
        self.alarm_history.append(alarm)
        self.total_alarms += 1

        logger.warning(f"ALARM: {alarm.message}")

    def _raise_cos_alarm(self, tag_name: str, value: Any) -> None:
        """Raise change-of-state alarm."""
        self._raise_alarm(tag_name, "change_of_state", value)

    def _raise_comms_alarm(self, tag_name: str) -> None:
        """Raise communications failure alarm."""
        self._raise_alarm(tag_name, "comms_failure", None)

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

    async def acknowledge_alarm(self, alarm_index: int) -> bool:
        """Acknowledge an active alarm."""
        if 0 <= alarm_index < len(self.active_alarms):
            self.active_alarms[alarm_index].acknowledged = True
            logger.info(
                f"Alarm acknowledged: {self.active_alarms[alarm_index].message}"
            )
            return True
        return False

    async def _update_statistics(self) -> None:
        """Update polling statistics."""
        # Calculate success rate
        if self.total_polls > 0:
            success_rate = (
                (self.total_polls - self.failed_polls) / self.total_polls
            ) * 100
        else:
            success_rate = 0.0

        # Update metadata
        await self.data_store.update_metadata(
            self.device_name,
            {
                "total_polls": self.total_polls,
                "failed_polls": self.failed_polls,
                "success_rate": success_rate,
                "active_alarms": len(self.active_alarms),
                "total_alarms": self.total_alarms,
            },
        )

    async def _sync_to_datastore(self) -> None:
        """Synchronise SCADA data to DataStore."""
        memory_map = {
            "tag_values": self.tag_values.copy(),
            "tag_quality": self.tag_quality.copy(),
            "tag_timestamps": self.tag_timestamps.copy(),
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
        }

        await self.data_store.bulk_write_memory(self.device_name, memory_map)

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
