# components/state/data_store.py
"""
Async data store for ICS simulation.

Provides device-level read/write access and unified memory map interface.
Integrates with SystemState for centralised state tracking.
"""

from __future__ import annotations

import re
from typing import Any

from components.security.logging_system import get_logger
from components.state.system_state import DeviceState, SystemState

# Configure logging
logger = get_logger(__name__)


class DataStore:
    """
    Async interface to simulation data.

    Provides read/write primitives for devices, memory maps, and metadata.
    All operations delegate to SystemState which handles locking and consistency.

    Memory map addresses should follow protocol conventions:
    - Modbus: "holding_registers[0]", "coils[5]", "input_registers[10]"
    - OPC UA: "ns=2;s=Temperature", "ns=2;s=Pressure"
    - IEC 104: "M_SP_NA_1:100", "M_ME_NC_1:200"

    Example:
        >>> data_store = DataStore(system_state)
        >>> await data_store.register_device("turbine_plc_1", "turbine_plc", 1, ["modbus"])
        >>> await data_store.write_memory("turbine_plc_1", "holding_registers[0]", 3600)
        >>> rpm = await data_store.read_memory("turbine_plc_1", "holding_registers[0]")
    """

    # Supported memory address patterns
    _MODBUS_PATTERN = re.compile(
        r"^(holding_registers|input_registers|coils|discrete_inputs)\[\d+\]$"
    )
    _OPCUA_PATTERN = re.compile(r"^ns=\d+;[si]=.+$")
    _IEC104_PATTERN = re.compile(r"^[A-Z_]+:\d+$")
    _S7_PATTERN = re.compile(r"^DB\d+$")  # Siemens S7 data blocks
    _INTERNAL_PATTERN = re.compile(r"^_[a-z_]+$")  # Device-internal diagnostic addresses
    _CONFIG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")  # Configuration/application addresses

    def __init__(self, system_state: SystemState):
        """Initialise data store.

        Args:
            system_state: SystemState instance to delegate to
        """
        self.system_state = system_state

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
        """Register a new device.

        Args:
            device_name: Unique device identifier
            device_type: Device type classification
            device_id: Numeric device ID
            protocols: List of supported protocols
            metadata: Optional device metadata

        Returns:
            True if newly registered, False if device already existed (updated)

        Raises:
            ValueError: If parameters are invalid
        """
        return await self.system_state.register_device(
            device_name=device_name,
            device_type=device_type,
            device_id=device_id,
            protocols=protocols,
            metadata=metadata,
        )

    async def unregister_device(self, device_name: str) -> bool:
        """Remove a device.

        Args:
            device_name: Device to unregister

        Returns:
            True if device was removed, False if device didn't exist
        """
        return await self.system_state.unregister_device(device_name)

    # ----------------------------------------------------------------
    # Memory map access
    # ----------------------------------------------------------------

    async def read_memory(self, device_name: str, address: str) -> Any:
        """Read a single memory field from a device.

        Args:
            device_name: Device to read from
            address: Memory address (protocol-specific format)

        Returns:
            Value at the address, or None if device/address doesn't exist

        Raises:
            ValueError: If device_name or address is invalid
        """
        if not device_name:
            raise ValueError("device_name cannot be empty")
        if not address:
            raise ValueError("address cannot be empty")

        self._validate_address(address)

        device = await self.system_state.get_device(device_name)
        if device is None:
            logger.debug(f"Read from non-existent device: {device_name}")
            return None

        value = device.memory_map.get(address)
        logger.debug(f"Read {device_name}[{address}] = {value}")
        return value

    async def write_memory(self, device_name: str, address: str, value: Any) -> bool:
        """Write a single memory field.

        Args:
            device_name: Device to write to
            address: Memory address (protocol-specific format)
            value: Value to write

        Returns:
            True if written successfully, False if device doesn't exist

        Raises:
            ValueError: If device_name or address is invalid
        """
        if not device_name:
            raise ValueError("device_name cannot be empty")
        if not address:
            raise ValueError("address cannot be empty")

        self._validate_address(address)

        device = await self.system_state.get_device(device_name)
        if device is None:
            logger.warning(f"Write to non-existent device: {device_name}")
            return False

        # Create updated memory map
        memory_map = device.memory_map.copy()
        memory_map[address] = value

        success = await self.system_state.update_device(
            device_name, memory_map=memory_map
        )

        if success:
            logger.debug(f"Wrote {device_name}[{address}] = {value}")

        return success

    async def bulk_read_memory(self, device_name: str) -> dict[str, Any] | None:
        """Read the entire memory map of a device.

        Args:
            device_name: Device to read from

        Returns:
            Copy of device's memory map, or None if device doesn't exist

        Raises:
            ValueError: If device_name is invalid
        """
        if not device_name:
            raise ValueError("device_name cannot be empty")

        device = await self.system_state.get_device(device_name)
        if device is None:
            logger.debug(f"Bulk read from non-existent device: {device_name}")
            return None

        logger.debug(f"Bulk read {device_name}: {len(device.memory_map)} addresses")
        return device.memory_map.copy()

    async def bulk_write_memory(self, device_name: str, values: dict[str, Any]) -> bool:
        """Write multiple memory fields at once.

        Args:
            device_name: Device to write to
            values: Dictionary of address -> value mappings

        Returns:
            True if written successfully, False if device doesn't exist

        Raises:
            ValueError: If device_name is invalid or values is empty
        """
        if not device_name:
            raise ValueError("device_name cannot be empty")
        if not values:
            raise ValueError("values cannot be empty")

        # Validate all addresses before writing
        for address in values.keys():
            self._validate_address(address)

        device = await self.system_state.get_device(device_name)
        if device is None:
            logger.warning(f"Bulk write to non-existent device: {device_name}")
            return False

        # Create updated memory map
        memory_map = device.memory_map.copy()
        memory_map.update(values)

        success = await self.system_state.update_device(
            device_name, memory_map=memory_map
        )

        if success:
            logger.debug(f"Bulk wrote {device_name}: {len(values)} addresses")

        return success

    def _validate_address(self, address: str) -> None:
        """Validate memory address format.

        Checks if address matches known protocol patterns.
        Logs warning if format is unrecognised but doesn't fail.

        Args:
            address: Address to validate
        """
        # Check against known patterns
        if (
            self._MODBUS_PATTERN.match(address)
            or self._OPCUA_PATTERN.match(address)
            or self._IEC104_PATTERN.match(address)
            or self._S7_PATTERN.match(address)
            or self._INTERNAL_PATTERN.match(address)
            or self._CONFIG_PATTERN.match(address)
        ):
            return

        # Allow custom patterns but log warning
        logger.debug(
            f"Address '{address}' doesn't match standard patterns "
            "(Modbus, OPC UA, IEC 104, Siemens S7, Internal, Config). Proceeding anyway."
        )

    # ----------------------------------------------------------------
    # Device state queries
    # ----------------------------------------------------------------

    async def get_device_state(self, device_name: str) -> DeviceState | None:
        """Return the full device state.

        Args:
            device_name: Device to query

        Returns:
            DeviceState if found, None otherwise
        """
        return await self.system_state.get_device(device_name)

    async def get_all_device_states(self) -> dict[str, DeviceState]:
        """Return all device states.

        Returns:
            Dictionary mapping device names to states
        """
        return await self.system_state.get_all_devices()

    async def get_devices_by_type(self, device_type: str) -> list[DeviceState]:
        """Return devices filtered by type.

        Args:
            device_type: Type to filter by

        Returns:
            List of matching devices
        """
        return await self.system_state.get_devices_by_type(device_type)

    async def get_devices_by_protocol(self, protocol: str) -> list[DeviceState]:
        """Return devices filtered by protocol.

        Args:
            protocol: Protocol to filter by

        Returns:
            List of devices supporting the protocol
        """
        return await self.system_state.get_devices_by_protocol(protocol)

    # ----------------------------------------------------------------
    # Metadata access
    # ----------------------------------------------------------------

    async def update_metadata(self, device_name: str, metadata: dict[str, Any]) -> bool:
        """Update device metadata.

        Merges provided metadata with existing metadata (doesn't replace).

        Args:
            device_name: Device to update
            metadata: Metadata key-value pairs to merge

        Returns:
            True if updated successfully, False if device doesn't exist

        Raises:
            ValueError: If device_name is invalid or metadata is empty
        """
        if not device_name:
            raise ValueError("device_name cannot be empty")
        if not metadata:
            raise ValueError("metadata cannot be empty")

        device = await self.system_state.get_device(device_name)
        if device is None:
            logger.warning(f"Update metadata on non-existent device: {device_name}")
            return False

        success = await self.system_state.update_device(device_name, metadata=metadata)

        if success:
            logger.debug(f"Updated metadata on {device_name}: {list(metadata.keys())}")

        return success

    async def read_metadata(self, device_name: str) -> dict[str, Any] | None:
        """Read device metadata.

        Args:
            device_name: Device to query

        Returns:
            Copy of device metadata, or None if device doesn't exist

        Raises:
            ValueError: If device_name is invalid
        """
        if not device_name:
            raise ValueError("device_name cannot be empty")

        device = await self.system_state.get_device(device_name)
        if device is None:
            logger.debug(f"Read metadata from non-existent device: {device_name}")
            return None

        return device.metadata.copy()

    # ----------------------------------------------------------------
    # Device online status
    # ----------------------------------------------------------------

    async def set_device_online(self, device_name: str, online: bool) -> bool:
        """Set device online/offline status.

        Args:
            device_name: Device to update
            online: True for online, False for offline

        Returns:
            True if updated successfully, False if device doesn't exist

        Raises:
            ValueError: If device_name is invalid
        """
        if not device_name:
            raise ValueError("device_name cannot be empty")

        success = await self.system_state.update_device(device_name, online=online)

        if success:
            status = "online" if online else "offline"
            logger.info(f"Device {device_name} marked {status}")
        else:
            logger.warning(
                f"Cannot set online status for non-existent device: {device_name}"
            )

        return success

    async def is_device_online(self, device_name: str) -> bool | None:
        """Check if device is online.

        Args:
            device_name: Device to check

        Returns:
            True if online, False if offline, None if device doesn't exist
        """
        device = await self.system_state.get_device(device_name)
        if device is None:
            return None
        return device.online

    # ----------------------------------------------------------------
    # Simulation-level access
    # ----------------------------------------------------------------

    async def get_simulation_state(self) -> dict[str, Any]:
        """Return high-level simulation summary.

        Returns:
            Dictionary with simulation status, device counts, and statistics
        """
        return await self.system_state.get_summary()

    async def mark_simulation_running(self, running: bool) -> None:
        """Set the simulation running state.

        Args:
            running: True if simulation is running, False if stopped
        """
        await self.system_state.mark_running(running)

    async def reset_simulation(self) -> None:
        """Reset all state and devices.

        Clears all registered devices and resets simulation state.
        """
        await self.system_state.reset()
        logger.info("Simulation state reset via DataStore")

    async def increment_update_cycle(self) -> None:
        """Increment the simulation update cycle counter.

        Should be called once per simulation loop iteration.
        """
        await self.system_state.increment_update_cycles()

    # ----------------------------------------------------------------
    # Audit trail access
    # ----------------------------------------------------------------

    async def get_audit_log(
        self,
        limit: int | None = None,
        device: str | None = None,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Query central audit log.

        Args:
            limit: Maximum events to return
            device: Filter by device name
            event_type: Filter by event type (e.g., "Memory write")

        Returns:
            List of audit events (most recent first)

        Example:
            >>> events = await data_store.get_audit_log(limit=10, device="turbine_plc_1")
            >>> for event in events:
            ...     print(f"{event['message']}: {event['data']}")
        """
        return await self.system_state.get_audit_log(
            limit=limit, device=device, event_type=event_type
        )
