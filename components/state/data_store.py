# components/state/data_store.py
"""
Async data store for ICS simulation.

Provides device-level read/write access and unified memory map interface.
Integrates with SystemState for centralized state tracking.
"""

from __future__ import annotations

import asyncio
from typing import Any

from components.state.system_state import DeviceState, SystemState


class DataStore:
    """
    Async interface to simulation data.

    Provides read/write primitives for devices, memory maps, and metadata.
    """

    def __init__(self, system_state: SystemState):
        self.system_state = system_state
        self._lock = asyncio.Lock()  # Optional extra layer for atomic operations

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
    ) -> None:
        """Register a new device."""
        async with self._lock:
            await self.system_state.register_device(
                device_name=device_name,
                device_type=device_type,
                device_id=device_id,
                protocols=protocols,
                metadata=metadata,
            )

    async def unregister_device(self, device_name: str) -> None:
        """Remove a device."""
        async with self._lock:
            await self.system_state.unregister_device(device_name)

    # ----------------------------------------------------------------
    # Memory map access
    # ----------------------------------------------------------------

    async def read_memory(self, device_name: str, address: str) -> Any | None:
        """Read a single memory field from a device."""
        device = await self.system_state.get_device(device_name)
        if device is None:
            return None
        return device.memory_map.get(address)

    async def write_memory(self, device_name: str, address: str, value: Any) -> bool:
        """Write a single memory field."""
        device = await self.system_state.get_device(device_name)
        if device is None:
            return False
        memory_map = device.memory_map.copy()
        memory_map[address] = value
        await self.system_state.update_device(device_name, memory_map=memory_map)
        return True

    async def bulk_read_memory(self, device_name: str) -> dict[str, Any] | None:
        """Read the entire memory map of a device."""
        device = await self.system_state.get_device(device_name)
        if device is None:
            return None
        return device.memory_map.copy()

    async def bulk_write_memory(self, device_name: str, values: dict[str, Any]) -> bool:
        """Write multiple memory fields at once."""
        device = await self.system_state.get_device(device_name)
        if device is None:
            return False
        memory_map = device.memory_map.copy()
        memory_map.update(values)
        await self.system_state.update_device(device_name, memory_map=memory_map)
        return True

    # ----------------------------------------------------------------
    # Device state queries
    # ----------------------------------------------------------------

    async def get_device_state(self, device_name: str) -> DeviceState | None:
        """Return the full device state."""
        return await self.system_state.get_device(device_name)

    async def get_all_device_states(self) -> dict[str, DeviceState]:
        """Return all device states."""
        return await self.system_state.get_all_devices()

    async def get_devices_by_type(self, device_type: str) -> list[DeviceState]:
        """Return devices filtered by type."""
        return await self.system_state.get_devices_by_type(device_type)

    async def get_devices_by_protocol(self, protocol: str) -> list[DeviceState]:
        """Return devices filtered by protocol."""
        return await self.system_state.get_devices_by_protocol(protocol)

    # ----------------------------------------------------------------
    # Metadata access
    # ----------------------------------------------------------------

    async def update_metadata(self, device_name: str, metadata: dict[str, Any]) -> bool:
        """Update device metadata."""
        device = await self.system_state.get_device(device_name)
        if device is None:
            return False
        await self.system_state.update_device(device_name, metadata=metadata)
        return True

    async def read_metadata(self, device_name: str) -> dict[str, Any] | None:
        """Read device metadata."""
        device = await self.system_state.get_device(device_name)
        if device is None:
            return None
        return device.metadata.copy()

    # ----------------------------------------------------------------
    # Simulation-level access
    # ----------------------------------------------------------------

    async def get_simulation_state(self) -> dict[str, Any]:
        """Return high-level simulation summary."""
        return await self.system_state.get_summary()

    async def mark_simulation_running(self, running: bool) -> None:
        """Set the simulation running state."""
        await self.system_state.mark_running(running)

    async def reset_simulation(self) -> None:
        """Reset all state and devices."""
        await self.system_state.reset()
