# components/devices/core/base_device.py
"""
Abstract base class for all simulated devices.

Provides common infrastructure for:
- DataStore registration and integration
- Async lifecycle management
- Protocol memory map interface
- Logging and telemetry
- Security integration
"""

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from components.security.logging_system import get_logger
from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime


class BaseDevice(ABC):
    """
    Abstract base for all devices in the simulation.

    Devices are responsible for:
    - Registering with DataStore
    - Managing their memory map (protocol interface)
    - Running periodic update cycles
    - Providing telemetry to SCADA/HMI systems

    Subclasses must implement:
    - _device_type(): Return device type string
    - _supported_protocols(): Return list of protocol names
    - _initialise_memory_map(): Set up initial memory map
    - _scan_cycle(): Periodic update logic
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        description: str = "",
        scan_interval: float = 0.1,  # 100ms default scan rate
        log_dir: Path | None = None,
    ):
        """
        Initialise base device.

        Args:
            device_name: Unique identifier for this device
            device_id: Numeric ID (used by protocols like Modbus)
            data_store: Reference to shared DataStore
            description: Human-readable description
            scan_interval: Time between scan cycles in seconds
            log_dir: Directory for log files (None = no file logging)
        """
        self.device_name = device_name
        self.device_id = device_id
        self.data_store = data_store
        self.description = description
        self.scan_interval = scan_interval

        # Simulation timing
        self.sim_time = SimulationTime()

        # Device-specific logger with ICS logging system
        self.logger = get_logger(
            self.__class__.__name__,
            device=device_name,
            log_dir=log_dir,
            data_store=data_store,
        )

        # Lifecycle state
        self._online = False
        self._running = False
        self._scan_task: asyncio.Task | None = None

        # Memory map (exposed to protocols)
        self.memory_map: dict[str, Any] = {}

        # Metadata for DataStore
        self.metadata: dict[str, Any] = {
            "description": description,
            "scan_interval": scan_interval,
        }

        self.logger.info(
            f"Initialised {self._device_type()} '{device_name}' "
            f"(ID: {device_id}, scan: {scan_interval}s)"
        )

    # ----------------------------------------------------------------
    # Abstract methods - must be implemented by subclasses
    # ----------------------------------------------------------------

    @abstractmethod
    def _device_type(self) -> str:
        """Return device type identifier (e.g., 'turbine_plc', 'rtu')."""
        pass

    @abstractmethod
    def _supported_protocols(self) -> list[str]:
        """Return list of supported protocol names."""
        pass

    @abstractmethod
    async def _initialize_memory_map(self) -> None:
        """Initialize device-specific memory map structure."""
        pass

    @abstractmethod
    async def _scan_cycle(self) -> None:
        """
        Execute one scan cycle.

        Typically:
        1. Read from physics engines
        2. Update internal state
        3. Update memory map for protocol access
        4. Write telemetry to DataStore
        """
        pass

    # ----------------------------------------------------------------
    # Lifecycle management
    # ----------------------------------------------------------------

    async def start(self) -> None:
        """
        Start the device.

        Registers with DataStore, initialises memory map, and begins scan cycle.
        """
        if self._running:
            self.logger.warning(f"Device '{self.device_name}' already running")
            return

        self.logger.info(f"Starting device '{self.device_name}'")

        # Register with DataStore
        await self.data_store.register_device(
            device_name=self.device_name,
            device_type=self._device_type(),
            device_id=self.device_id,
            protocols=self._supported_protocols(),
            metadata=self.metadata,
        )

        # Initialise memory map
        await self._initialize_memory_map()

        # Write initial memory map to DataStore
        await self.data_store.bulk_write_memory(
            self.device_name,
            self.memory_map,
        )

        # Mark online
        self._online = True
        await self.data_store.get_device_state(self.device_name)
        await self.data_store.system_state.update_device(
            self.device_name,
            online=True,
        )

        # Start scan cycle
        self._running = True
        self._scan_task = asyncio.create_task(self._scan_loop())

        self.logger.info(f"Device '{self.device_name}' started successfully")

    async def stop(self) -> None:
        """
        Stop the device cleanly.

        Stops scan cycle, marks offline, and optionally unregisters from DataStore.
        """
        if not self._running:
            return

        self.logger.info(f"Stopping device '{self.device_name}'")

        # Stop scan loop
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None

        # Mark offline
        self._online = False
        await self.data_store.system_state.update_device(
            self.device_name,
            online=False,
        )

        self.logger.info(f"Device '{self.device_name}' stopped")

    async def reset(self) -> None:
        """Reset device to initial state."""
        self.logger.info(f"Resetting device '{self.device_name}'")
        await self.stop()
        await self._initialize_memory_map()
        await self.start()

    # ----------------------------------------------------------------
    # Scan cycle execution
    # ----------------------------------------------------------------

    async def _scan_loop(self) -> None:
        """
        Main scan loop - executes scan cycles at regular intervals.

        Uses simulation time for timing, so it's time-mode aware.
        """
        self.logger.debug(
            f"Scan loop started for '{self.device_name}' "
            f"(interval: {self.scan_interval}s)"
        )

        _last_scan_time = self.sim_time.now()

        while self._running:
            try:
                # Wait for next scan interval (simulation time aware)
                await asyncio.sleep(self.scan_interval)

                # Check if we should skip due to pause
                if self.sim_time.is_paused():
                    continue

                # Execute scan cycle
                current_time = self.sim_time.now()

                await self._scan_cycle()

                # Update DataStore with new memory map
                await self.data_store.bulk_write_memory(
                    self.device_name,
                    self.memory_map,
                )

                _last_scan_time = current_time

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    f"Error in scan cycle for '{self.device_name}': {e}",
                    exc_info=True,
                )
                # Continue running despite errors
                await asyncio.sleep(self.scan_interval)

    # ----------------------------------------------------------------
    # Memory map interface (for protocols)
    # ----------------------------------------------------------------

    def read_memory(self, address: str) -> Any | None:
        """
        Read a value from the memory map.

        Args:
            address: Memory address/key

        Returns:
            Value at address, or None if not found
        """
        return self.memory_map.get(address)

    def write_memory(self, address: str, value: Any) -> bool:
        """
        Write a value to the memory map.

        Args:
            address: Memory address/key
            value: Value to write

        Returns:
            True if successful, False if address invalid
        """
        if address not in self.memory_map:
            self.logger.warning(
                f"Attempted write to invalid address '{address}' "
                f"on device '{self.device_name}'"
            )
            return False

        self.memory_map[address] = value
        self.logger.debug(f"Device '{self.device_name}': {address} <- {value}")
        return True

    def bulk_read_memory(self) -> dict[str, Any]:
        """Return complete memory map snapshot."""
        return self.memory_map.copy()

    def bulk_write_memory(self, values: dict[str, Any]) -> bool:
        """
        Write multiple values to memory map.

        Args:
            values: Dictionary of address: value pairs

        Returns:
            True if all writes successful
        """
        success = True
        for address, value in values.items():
            if not self.write_memory(address, value):
                success = False
        return success

    # ----------------------------------------------------------------
    # Status and diagnostics
    # ----------------------------------------------------------------

    def is_online(self) -> bool:
        """Check if device is currently online."""
        return self._online

    def is_running(self) -> bool:
        """Check if device scan cycle is running."""
        return self._running

    async def get_status(self) -> dict[str, Any]:
        """
        Get comprehensive device status.

        Returns:
            Dictionary containing device state and diagnostics
        """
        return {
            "device_name": self.device_name,
            "device_type": self._device_type(),
            "device_id": self.device_id,
            "online": self._online,
            "running": self._running,
            "scan_interval": self.scan_interval,
            "protocols": self._supported_protocols(),
            "memory_map_size": len(self.memory_map),
            "description": self.description,
        }

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"'{self.device_name}' "
            f"(ID: {self.device_id}, "
            f"online: {self._online})>"
        )
