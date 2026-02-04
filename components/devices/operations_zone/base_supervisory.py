# components/devices/operations_zone/base_supervisory.py
"""
Base class for Supervisory Control devices (SCADA servers, HMI masters).

Supervisory devices are responsible for:
- Polling field devices (PLCs, RTUs, IEDs)
- Aggregating data into a centralised database
- Managing alarms and events
- Providing operator interfaces

Unlike PLCs which execute control logic, supervisory devices focus on:
- Data acquisition from multiple sources
- Multi-rate polling coordination
- Alarm management
- Historical data collection
- Operator oversight
"""

from abc import abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from components.devices.core.base_device import BaseDevice
from components.state.data_store import DataStore


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


class BaseSupervisoryDevice(BaseDevice):
    """
    Base class for supervisory control devices.

    Supervisory devices bridge between:
    - Field devices (PLCs, RTUs, IEDs)
    - Operator interfaces (HMI, historian)

    Key features:
    - Multi-device polling with configurable rates
    - Tag database with quality tracking
    - Alarm management
    - Telemetry aggregation

    Subclasses must implement:
    - _initialise_memory_map(): Define tag/register structure
    - _poll_device(): Read data from a specific device
    - _process_polled_data(): Process and validate polled data
    - _check_alarms(): Evaluate alarm conditions
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        description: str = "",
        scan_interval: float = 0.1,  # 100ms default (main scan cycle)
        log_dir: Path | None = None,
    ):
        """
        Initialise supervisory device.

        Args:
            device_name: Unique device identifier
            device_id: Numeric ID for protocol addressing
            data_store: Reference to DataStore
            description: Human-readable description
            scan_interval: Main scan cycle interval in seconds
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

        # Poll targets (devices to poll)
        self.poll_targets: dict[str, PollTarget] = {}
        self.polling_enabled: bool = True

        # Statistics
        self.total_polls: int = 0
        self.failed_polls: int = 0

        self.logger.info(
            f"BaseSupervisoryDevice '{device_name}' initialised "
            f"(scan_interval: {scan_interval}s)"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return 'supervisory' as base type (override in subclass)."""
        return "supervisory"

    async def _scan_cycle(self) -> None:
        """
        Execute supervisory scan cycle.

        Order of operations:
        1. Poll devices that are due (based on their poll rates)
        2. Process polled data (validation, scaling)
        3. Check for alarm conditions
        4. Update memory map (for protocol access)

        Note: BaseDevice._scan_loop() handles:
        - Incrementing scan_count
        - Updating last_scan_time
        - Error counting
        - Writing memory_map to DataStore
        """
        if not self.polling_enabled:
            return

        current_time = self.sim_time.now()

        # Poll devices that are due
        for _target_name, target in self.poll_targets.items():
            if not target.enabled:
                continue

            if self._is_poll_due(target, current_time):
                await self._poll_device(target)
                target.last_poll_time = current_time
                self.total_polls += 1

        # Process polled data
        await self._process_polled_data()

        # Check alarm conditions
        self._check_alarms()

    def _is_poll_due(self, target: PollTarget, current_time: float) -> bool:
        """
        Check if a poll target is due for polling.

        Args:
            target: Poll target configuration
            current_time: Current simulation time

        Returns:
            True if poll is due, False otherwise
        """
        if target.last_poll_time == 0.0:
            return True  # Never polled, poll now

        elapsed = current_time - target.last_poll_time
        return elapsed >= target.poll_rate_s

    # ----------------------------------------------------------------
    # Abstract methods for supervisory cycle - must be implemented
    # ----------------------------------------------------------------

    @abstractmethod
    async def _poll_device(self, target: PollTarget) -> None:
        """
        Poll a specific device.

        Args:
            target: Poll target configuration

        Typically:
        - Read device memory from DataStore
        - Update local tag values
        - Track poll success/failure
        """
        pass

    @abstractmethod
    async def _process_polled_data(self) -> None:
        """
        Process polled data.

        Typically:
        - Validate data quality
        - Apply scaling/transformations
        - Update timestamps
        - Sync to memory map
        """
        pass

    @abstractmethod
    def _check_alarms(self) -> None:
        """
        Check for alarm conditions.

        Typically:
        - Evaluate high/low limits
        - Check for communication failures
        - Update alarm lists
        """
        pass

    # ----------------------------------------------------------------
    # Poll target management
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

        self.logger.info(
            f"Poll target added: {device_name} ({protocol}) @ {poll_rate_s}s"
        )

    def remove_poll_target(self, device_name: str) -> bool:
        """
        Remove a device from polling.

        Args:
            device_name: Name of device to remove

        Returns:
            True if removed, False if not found
        """
        if device_name in self.poll_targets:
            del self.poll_targets[device_name]
            self.logger.info(f"Poll target removed: {device_name}")
            return True
        return False

    def enable_poll_target(self, device_name: str, enabled: bool = True) -> bool:
        """
        Enable or disable polling for a specific device.

        Args:
            device_name: Name of device
            enabled: Whether to enable polling

        Returns:
            True if target found and updated, False otherwise
        """
        if device_name in self.poll_targets:
            self.poll_targets[device_name].enabled = enabled
            state = "enabled" if enabled else "disabled"
            self.logger.info(f"Poll target {device_name} {state}")
            return True
        return False

    # ----------------------------------------------------------------
    # Status and diagnostics
    # ----------------------------------------------------------------

    async def get_supervisory_status(self) -> dict[str, Any]:
        """Get supervisory device status."""
        base_status = await self.get_status()
        supervisory_status = {
            **base_status,
            "polling_enabled": self.polling_enabled,
            "poll_target_count": len(self.poll_targets),
            "total_polls": self.total_polls,
            "failed_polls": self.failed_polls,
            "poll_success_rate": (
                ((self.total_polls - self.failed_polls) / self.total_polls * 100)
                if self.total_polls > 0
                else 0.0
            ),
            "poll_targets": {
                name: {
                    "protocol": target.protocol,
                    "poll_rate_s": target.poll_rate_s,
                    "enabled": target.enabled,
                    "last_poll_success": target.last_poll_success,
                    "consecutive_failures": target.consecutive_failures,
                }
                for name, target in self.poll_targets.items()
            },
        }
        return supervisory_status
