# components/devices/control_zone/rtu/rtu_modbus.py
"""
Modbus RTU (Remote Terminal Unit) device class.

Generic field device with configurable Modbus memory map.
Suitable for simulating remote sensors, actuators, and field equipment.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Callable

from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime

logger = logging.getLogger(__name__)


@dataclass
class ModbusRegisterMap:
    """Modbus register map configuration."""

    holding_registers_count: int = 100
    coils_count: int = 100
    input_registers_count: int = 100
    discrete_inputs_count: int = 100


class RTUModbus:
    """
    Generic Modbus RTU device.

    Provides flexible Modbus memory map without built-in physics.
    Users can set custom update callbacks for application logic.

    Memory Map:
    - Holding registers: Read-write 16-bit registers (0-n)
    - Coils: Read-write binary outputs (0-n)
    - Input registers: Read-only 16-bit inputs (0-n)
    - Discrete inputs: Read-only binary inputs (0-n)

    Example:
        >>> rtu = RTUModbus(
        ...     device_name="field_rtu_1",
        ...     data_store=data_store,
        ...     register_map=ModbusRegisterMap(holding_registers_count=50)
        ... )
        >>>
        >>> # Define custom sensor simulation
        >>> async def update_sensors(rtu, dt):
        ...     import random
        ...     temp = 20 + random.gauss(0, 2)  # Temperature sensor
        ...     pressure = 100 + random.gauss(0, 5)  # Pressure sensor
        ...     rtu.set_input_register(0, int(temp * 10))
        ...     rtu.set_input_register(1, int(pressure))
        >>>
        >>> rtu.set_update_callback(update_sensors)
        >>> await rtu.initialise()
        >>> await rtu.start()
    """

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        register_map: ModbusRegisterMap | None = None,
        scan_rate_hz: float = 10.0,
        unit_id: int = 1,
    ):
        """
        Initialise RTU Modbus device.

        Args:
            device_name: Unique device identifier
            data_store: DataStore instance
            register_map: Register map configuration
            scan_rate_hz: Scan cycle rate
            unit_id: Modbus unit ID (slave ID)
        """
        self.device_name = device_name
        self.data_store = data_store
        self.sim_time = SimulationTime()

        # Configuration
        self.register_map = register_map or ModbusRegisterMap()
        self.scan_rate_hz = scan_rate_hz
        self.scan_interval = 1.0 / scan_rate_hz
        self.unit_id = unit_id

        # Memory maps
        self.holding_registers: dict[int, int] = {}
        self.coils: dict[int, bool] = {}
        self.input_registers: dict[int, int] = {}
        self.discrete_inputs: dict[int, bool] = {}

        # Runtime state
        self._running = False
        self._scan_task: asyncio.Task | None = None
        self._last_scan_time = 0.0

        # Custom update callback
        self._update_callback: Callable | None = None

        logger.info(
            f"RTUModbus created: {device_name}, "
            f"unit_id={unit_id}, scan_rate={scan_rate_hz}Hz"
        )

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialise device and register with DataStore."""
        await self.data_store.register_device(
            device_name=self.device_name,
            device_type="rtu_modbus",
            device_id=self.unit_id,
            protocols=["modbus"],
            metadata={
                "unit_id": self.unit_id,
                "scan_rate_hz": self.scan_rate_hz,
                "register_map": {
                    "holding_registers": self.register_map.holding_registers_count,
                    "coils": self.register_map.coils_count,
                    "input_registers": self.register_map.input_registers_count,
                    "discrete_inputs": self.register_map.discrete_inputs_count,
                },
            },
        )

        # Initialise memory maps
        self._initialise_memory_maps()
        await self._sync_to_datastore()

        logger.info(f"RTUModbus initialised: {self.device_name}")

    async def start(self) -> None:
        """Start the scan cycle."""
        if self._running:
            logger.warning(f"RTUModbus already running: {self.device_name}")
            return

        self._running = True
        self._last_scan_time = self.sim_time.now()
        self._scan_task = asyncio.create_task(self._scan_cycle())

        logger.info(f"RTUModbus started: {self.device_name}")

    async def stop(self) -> None:
        """Stop the scan cycle."""
        if not self._running:
            return

        self._running = False

        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None

        logger.info(f"RTUModbus stopped: {self.device_name}")

    # ----------------------------------------------------------------
    # Scan cycle
    # ----------------------------------------------------------------

    async def _scan_cycle(self) -> None:
        """Main scan cycle loop."""
        logger.info(
            f"Scan cycle started for {self.device_name} at {self.scan_rate_hz}Hz"
        )

        while self._running:
            current_time = self.sim_time.now()
            dt = current_time - self._last_scan_time

            try:
                # Read control inputs from DataStore
                await self._read_control_inputs()

                # Execute custom update callback if provided
                if self._update_callback:
                    await self._update_callback(self, dt)

                # Sync to DataStore
                await self._sync_to_datastore()

            except Exception as e:
                logger.error(f"Error in scan cycle for {self.device_name}: {e}")

            self._last_scan_time = current_time
            await asyncio.sleep(self.scan_interval)

    async def _read_control_inputs(self) -> None:
        """Read control inputs written by protocol handlers."""
        # Read holding registers from DataStore (written by Modbus writes)
        memory = await self.data_store.bulk_read_memory(self.device_name)

        if memory:
            # Update holding registers if changed via protocol
            if "holding_registers" in memory:
                for addr, value in memory["holding_registers"].items():
                    self.holding_registers[addr] = value

            # Update coils if changed via protocol
            if "coils" in memory:
                for addr, value in memory["coils"].items():
                    self.coils[addr] = value

    # ----------------------------------------------------------------
    # Memory map operations
    # ----------------------------------------------------------------

    def _initialise_memory_maps(self) -> None:
        """Initialise all memory maps with default values."""
        for i in range(self.register_map.holding_registers_count):
            self.holding_registers[i] = 0

        for i in range(self.register_map.coils_count):
            self.coils[i] = False

        for i in range(self.register_map.input_registers_count):
            self.input_registers[i] = 0

        for i in range(self.register_map.discrete_inputs_count):
            self.discrete_inputs[i] = False

    async def _sync_to_datastore(self) -> None:
        """Synchronise memory map to DataStore."""
        memory_map = {
            "holding_registers": self.holding_registers.copy(),
            "coils": self.coils.copy(),
            "input_registers": self.input_registers.copy(),
            "discrete_inputs": self.discrete_inputs.copy(),
        }
        await self.data_store.bulk_write_memory(self.device_name, memory_map)

    # ----------------------------------------------------------------
    # Public interface
    # ----------------------------------------------------------------

    def set_update_callback(self, callback: Callable) -> None:
        """
        Set custom update callback for application logic.

        Args:
            callback: Async function(rtu, dt) called each scan cycle
        """
        self._update_callback = callback

    def get_holding_register(self, address: int) -> int | None:
        """Read holding register."""
        return self.holding_registers.get(address)

    def set_holding_register(self, address: int, value: int) -> bool:
        """Write holding register."""
        if 0 <= address < self.register_map.holding_registers_count:
            self.holding_registers[address] = value
            return True
        return False

    def get_coil(self, address: int) -> bool | None:
        """Read coil."""
        return self.coils.get(address)

    def set_coil(self, address: int, value: bool) -> bool:
        """Write coil."""
        if 0 <= address < self.register_map.coils_count:
            self.coils[address] = value
            return True
        return False

    def get_input_register(self, address: int) -> int | None:
        """Read input register."""
        return self.input_registers.get(address)

    def set_input_register(self, address: int, value: int) -> bool:
        """Write input register (for simulation logic)."""
        if 0 <= address < self.register_map.input_registers_count:
            self.input_registers[address] = value
            return True
        return False

    def get_discrete_input(self, address: int) -> bool | None:
        """Read discrete input."""
        return self.discrete_inputs.get(address)

    def set_discrete_input(self, address: int, value: bool) -> bool:
        """Write discrete input (for simulation logic)."""
        if 0 <= address < self.register_map.discrete_inputs_count:
            self.discrete_inputs[address] = value
            return True
        return False

    async def get_telemetry(self) -> dict[str, Any]:
        """Get device telemetry."""
        return {
            "device_name": self.device_name,
            "device_type": "rtu_modbus",
            "unit_id": self.unit_id,
            "holding_registers": self.holding_registers.copy(),
            "coils": self.coils.copy(),
            "input_registers": self.input_registers.copy(),
            "discrete_inputs": self.discrete_inputs.copy(),
        }
