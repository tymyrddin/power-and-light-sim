# components/state/system_state.py
"""
Centralised state management for ICS simulation.

Tracks all devices, physics engines, and simulation state.
Provides unified interface for monitoring and control.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from components.time.simulation_time import SimulationTime

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class DeviceState:
    """State snapshot for a single device.

    Attributes:
        device_name: Unique identifier for the device
        device_type: Type classification (turbine_plc, scada_server, etc.)
        device_id: Numeric device identifier
        protocols: List of supported protocols
        online: Whether device is currently online/operational
        memory_map: Protocol-specific register/coil/tag storage
        last_update: Timestamp of last state update
        metadata: Additional device information (location, config, etc.)
    """

    device_name: str
    device_type: str
    device_id: int
    protocols: list[str]
    online: bool = False
    memory_map: dict[str, Any] = field(default_factory=dict)
    last_update: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SimulationState:
    """Overall simulation state.

    Attributes:
        started_at: Simulation start timestamp
        running: Whether simulation is currently running
        total_devices: Total number of registered devices
        devices_online: Number of devices currently online
        total_update_cycles: Counter for state update cycles
    """

    started_at: datetime = field(default_factory=datetime.now)
    running: bool = False
    total_devices: int = 0
    devices_online: int = 0
    total_update_cycles: int = 0


class SystemState:
    """
    Centralised state manager for ICS simulation.

    Maintains current state of all devices and physics engines.
    Provides snapshot and monitoring capabilities.

    This is the single source of truth for all simulation state.
    All state mutations are protected by async locks for thread safety.

    Example:
        >>> system_state = SystemState()
        >>> await system_state.register_device(
        ...     "turbine_plc_1", "turbine_plc", 1, ["modbus"]
        ... )
        >>> await system_state.update_device(
        ...     "turbine_plc_1", online=True, memory_map={"holding_registers[0]": 3600}
        ... )
    """

    def __init__(self):
        self.devices: dict[str, DeviceState] = {}
        self.simulation = SimulationState()
        self._lock = asyncio.Lock()
        self._sim_time = SimulationTime()

    # ----------------------------------------------------------------
    # Device registration
    # ----------------------------------------------------------------

    async def register_device(
        self,
        device_name: str,
        device_type: str,
        device_id: int,
        protocols: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Register a device with the state manager.

        Args:
            device_name: Unique device identifier
            device_type: Device type classification
            device_id: Numeric device ID
            protocols: List of supported protocols
            metadata: Optional device metadata

        Returns:
            True if registered successfully, False if already exists (updates instead)

        Raises:
            ValueError: If device_name is empty or invalid
        """
        if not device_name or not isinstance(device_name, str):
            raise ValueError("device_name must be a non-empty string")

        if not device_type or not isinstance(device_type, str):
            raise ValueError("device_type must be a non-empty string")

        if not isinstance(protocols, list):
            raise ValueError("protocols must be a list (can be empty for client devices)")

        async with self._lock:
            already_exists = device_name in self.devices

            self.devices[device_name] = DeviceState(
                device_name=device_name,
                device_type=device_type,
                device_id=device_id,
                protocols=protocols,
                online=False,
                metadata=metadata or {},
            )
            self.simulation.total_devices = len(self.devices)

            if already_exists:
                logger.warning(
                    f"Device {device_name} already registered, replaced with new configuration"
                )
            else:
                logger.info(
                    f"Registered device: {device_name} "
                    f"(type={device_type}, id={device_id}, protocols={protocols})"
                )

            return not already_exists

    async def unregister_device(self, device_name: str) -> bool:
        """Remove a device from state tracking.

        Args:
            device_name: Device to unregister

        Returns:
            True if device was unregistered, False if device didn't exist
        """
        async with self._lock:
            if device_name not in self.devices:
                logger.warning(f"Cannot unregister non-existent device: {device_name}")
                return False

            device = self.devices[device_name]
            was_online = device.online

            del self.devices[device_name]
            self.simulation.total_devices = len(self.devices)

            if was_online:
                self.simulation.devices_online -= 1

            logger.info(f"Unregistered device: {device_name}")
            return True

    # ----------------------------------------------------------------
    # State updates
    # ----------------------------------------------------------------

    async def update_device(
        self,
        device_name: str,
        online: bool | None = None,
        memory_map: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Update device state.

        Args:
            device_name: Device to update
            online: New online status (optional)
            memory_map: New memory map (replaces existing, optional)
            metadata: Metadata to merge (optional)

        Returns:
            True if updated successfully, False if device doesn't exist
        """
        async with self._lock:
            if device_name not in self.devices:
                logger.warning(f"Cannot update non-existent device: {device_name}")
                return False

            device = self.devices[device_name]
            old_online = device.online

            # Update online status and track counter
            if online is not None and online != old_online:
                device.online = online
                if online:
                    self.simulation.devices_online += 1
                    logger.debug(f"Device {device_name} now online")
                else:
                    self.simulation.devices_online -= 1
                    logger.debug(f"Device {device_name} now offline")

            # Replace memory map entirely
            if memory_map is not None:
                device.memory_map = memory_map

            # Merge metadata (doesn't replace, merges)
            if metadata is not None:
                device.metadata.update(metadata)

            device.last_update = datetime.now()

            return True

    async def increment_update_cycles(self) -> None:
        """Increment the simulation update cycle counter.

        Should be called once per simulation update loop iteration.
        """
        async with self._lock:
            self.simulation.total_update_cycles += 1

    # ----------------------------------------------------------------
    # State queries
    # ----------------------------------------------------------------

    async def get_device(self, device_name: str) -> DeviceState | None:
        """Get current state of a specific device.

        Args:
            device_name: Device to query

        Returns:
            DeviceState if found, None otherwise
        """
        async with self._lock:
            return self.devices.get(device_name)

    async def get_all_devices(self) -> dict[str, DeviceState]:
        """Get state of all devices.

        Returns:
            Dictionary mapping device names to their states
        """
        async with self._lock:
            return self.devices.copy()

    async def get_devices_by_type(self, device_type: str) -> list[DeviceState]:
        """Get all devices of a specific type.

        Args:
            device_type: Type to filter by (e.g., "turbine_plc")

        Returns:
            List of matching devices
        """
        async with self._lock:
            return [d for d in self.devices.values() if d.device_type == device_type]

    async def get_devices_by_protocol(self, protocol: str) -> list[DeviceState]:
        """Get all devices supporting a specific protocol.

        Args:
            protocol: Protocol to filter by (e.g., "modbus")

        Returns:
            List of devices supporting the protocol
        """
        async with self._lock:
            return [d for d in self.devices.values() if protocol in d.protocols]

    async def get_simulation_state(self) -> SimulationState:
        """Get overall simulation state.

        Returns:
            Current simulation state snapshot
        """
        async with self._lock:
            return self.simulation

    # ----------------------------------------------------------------
    # Status reporting
    # ----------------------------------------------------------------

    async def get_summary(self) -> dict[str, Any]:
        """Get high-level summary of simulation state.

        Returns:
            Dictionary with simulation status, device counts, and statistics
        """
        async with self._lock:
            return {
                "simulation": {
                    "running": self.simulation.running,
                    "started_at": self.simulation.started_at.isoformat(),
                    "uptime_seconds": (
                        datetime.now() - self.simulation.started_at
                    ).total_seconds(),
                    "simulation_time": self._sim_time.now(),
                    "update_cycles": self.simulation.total_update_cycles,
                },
                "devices": {
                    "total": self.simulation.total_devices,
                    "online": self.simulation.devices_online,
                    "offline": self.simulation.total_devices
                    - self.simulation.devices_online,
                },
                "device_types": self._count_device_types(),
                "protocols": self._count_protocols(),
            }

    def _count_device_types(self) -> dict[str, int]:
        """Count devices by type.

        Note: Should only be called while holding self._lock

        Returns:
            Dictionary mapping device types to counts
        """
        counts: dict[str, int] = {}
        for device in self.devices.values():
            counts[device.device_type] = counts.get(device.device_type, 0) + 1
        return counts

    def _count_protocols(self) -> dict[str, int]:
        """Count protocol usage across devices.

        Note: Should only be called while holding self._lock

        Returns:
            Dictionary mapping protocols to usage counts
        """
        counts: dict[str, int] = {}
        for device in self.devices.values():
            for protocol in device.protocols:
                counts[protocol] = counts.get(protocol, 0) + 1
        return counts

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def mark_running(self, running: bool) -> None:
        """Mark simulation as running/stopped.

        Args:
            running: True if simulation is running, False if stopped
        """
        async with self._lock:
            old_state = self.simulation.running
            self.simulation.running = running

            if running and not old_state:
                self.simulation.started_at = datetime.now()
                logger.info("Simulation marked as running")
            elif not running and old_state:
                logger.info("Simulation marked as stopped")

    async def reset(self) -> None:
        """Reset all state.

        Clears all devices and resets simulation state to initial values.
        """
        async with self._lock:
            device_count = len(self.devices)
            self.devices.clear()
            self.simulation = SimulationState()
            logger.info(f"System state reset: cleared {device_count} devices")
