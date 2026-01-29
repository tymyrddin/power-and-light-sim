# components/devices/control_zone/plc/generic/substation_plc.py
"""
Substation PLC device class.

Substation controller supporting both Modbus and IEC 104 protocols.
Monitors voltage, current, power flow and controls circuit breakers.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime

logger = logging.getLogger(__name__)


@dataclass
class BreakerState:
    """Circuit breaker state."""

    position: bool = False  # False=open, True=closed
    trip_count: int = 0
    last_operation_time: float = 0.0
    manual_control: bool = False


@dataclass
class MeasurementState:
    """Electrical measurements."""

    voltage_a_v: float = 0.0
    voltage_b_v: float = 0.0
    voltage_c_v: float = 0.0
    current_a_a: float = 0.0
    current_b_a: float = 0.0
    current_c_a: float = 0.0
    frequency_hz: float = 50.0
    active_power_kw: float = 0.0
    reactive_power_kvar: float = 0.0


@dataclass
class ProtectionState:
    """Protection relay states."""

    overcurrent_trip: bool = False
    undervoltage_trip: bool = False
    overvoltage_trip: bool = False
    underfrequency_trip: bool = False
    overfrequency_trip: bool = False


class SubstationPLC:
    """
    Substation PLC with dual protocol support.

    Supports both Modbus TCP and IEC 60870-5-104 protocols for
    compatibility with different SCADA systems.

    **Modbus Memory Map:**

    Holding Registers (read-only telemetry):
    - 0: Phase A voltage (V)
    - 1: Phase B voltage (V)
    - 2: Phase C voltage (V)
    - 3: Phase A current (A)
    - 4: Phase B current (A)
    - 5: Phase C current (A)
    - 6: Frequency (Hz × 100)
    - 7: Active power (kW)
    - 8: Reactive power (kVAR)
    - 9: Breaker trip count

    Coils (status and control):
    - 0: Breaker position (0=open, 1=closed)
    - 1: Breaker control command (write to operate)
    - 10: Overcurrent trip
    - 11: Undervoltage trip
    - 12: Overvoltage trip
    - 13: Underfrequency trip
    - 14: Overfrequency trip

    **IEC 104 Information Objects:**

    Single-point information (M_SP_NA_1):
    - IOA 100: Breaker position
    - IOA 110-114: Protection trip flags

    Measured values, normalised (M_ME_NA_1):
    - IOA 200-202: Phase voltages
    - IOA 203-205: Phase currents
    - IOA 206: Frequency
    - IOA 207-208: Active/reactive power

    Single commands (C_SC_NA_1):
    - IOA 1000: Breaker control (0=open, 1=close)

    Example:
        >>> substation = SubstationPLC(
        ...     device_name="substation_plc_1",
        ...     data_store=data_store,
        ...     common_address=1,
        ...     rated_voltage_kv=132.0
        ... )
        >>> await substation.initialise()
        >>> await substation.start()
    """

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        common_address: int = 1,
        rated_voltage_kv: float = 132.0,
        rated_current_a: float = 1000.0,
        scan_rate_hz: float = 10.0,
    ):
        """
        Initialise substation PLC.

        Args:
            device_name: Unique device identifier
            data_store: DataStore instance
            common_address: IEC 104 common address (ASDU address)
            rated_voltage_kv: Rated line voltage in kV
            rated_current_a: Rated line current in A
            scan_rate_hz: Scan cycle rate
        """
        self.device_name = device_name
        self.data_store = data_store
        self.sim_time = SimulationTime()

        # Configuration
        self.common_address = common_address
        self.rated_voltage_kv = rated_voltage_kv
        self.rated_current_a = rated_current_a
        self.scan_rate_hz = scan_rate_hz
        self.scan_interval = 1.0 / scan_rate_hz

        # Device state
        self.breaker = BreakerState()
        self.measurements = MeasurementState()
        self.protection = ProtectionState()

        # Modbus memory map
        self.holding_registers: dict[int, int] = {}
        self.coils: dict[int, bool] = {}

        # IEC 104 information objects (IOA -> value mapping)
        self.iec104_single_points: dict[int, bool] = {}  # M_SP_NA_1
        self.iec104_measured_values: dict[int, float] = {}  # M_ME_NA_1

        # Runtime state
        self._running = False
        self._scan_task: asyncio.Task | None = None
        self._last_scan_time = 0.0

        # Protection limits
        self.voltage_min_v = rated_voltage_kv * 1000 * 0.9  # 90% rated
        self.voltage_max_v = rated_voltage_kv * 1000 * 1.1  # 110% rated
        self.current_max_a = rated_current_a * 1.2  # 120% rated
        self.frequency_min_hz = 49.5
        self.frequency_max_hz = 50.5

        logger.info(
            f"SubstationPLC created: {device_name}, "
            f"common_address={common_address}, "
            f"rated={rated_voltage_kv}kV/{rated_current_a}A"
        )

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialise device and register with DataStore."""
        await self.data_store.register_device(
            device_name=self.device_name,
            device_type="substation_plc",
            device_id=hash(self.device_name) % 1000,
            protocols=["modbus", "iec104"],
            metadata={
                "common_address": self.common_address,
                "rated_voltage_kv": self.rated_voltage_kv,
                "rated_current_a": self.rated_current_a,
                "scan_rate_hz": self.scan_rate_hz,
            },
        )

        # Initialise memory maps
        self._initialise_memory_maps()

        # Set default measurements (nominal conditions)
        self.measurements.voltage_a_v = self.rated_voltage_kv * 1000
        self.measurements.voltage_b_v = self.rated_voltage_kv * 1000
        self.measurements.voltage_c_v = self.rated_voltage_kv * 1000
        self.measurements.frequency_hz = 50.0

        # Write initial state to DataStore
        await self._sync_to_datastore()

        logger.info(f"SubstationPLC initialised: {self.device_name}")

    async def start(self) -> None:
        """Start the scan cycle."""
        if self._running:
            logger.warning(f"SubstationPLC already running: {self.device_name}")
            return

        self._running = True
        self._last_scan_time = self.sim_time.now()
        self._scan_task = asyncio.create_task(self._scan_cycle())

        logger.info(f"SubstationPLC started: {self.device_name}")

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

        logger.info(f"SubstationPLC stopped: {self.device_name}")

    # ----------------------------------------------------------------
    # Scan cycle
    # ----------------------------------------------------------------

    async def _scan_cycle(self) -> None:
        """Main PLC scan cycle."""
        logger.info(
            f"Scan cycle started for {self.device_name} at {self.scan_rate_hz}Hz"
        )

        while self._running:
            current_time = self.sim_time.now()
            dt = current_time - self._last_scan_time

            try:
                # 1. Read control inputs from DataStore
                await self._read_control_inputs()

                # 2. Update measurements (from grid physics if available)
                await self._update_measurements()

                # 3. Execute protection logic
                self._execute_protection()

                # 4. Update memory maps
                self._update_modbus_memory_map()
                self._update_iec104_information_objects()

                # 5. Sync to DataStore
                await self._sync_to_datastore()

            except Exception as e:
                logger.error(f"Error in scan cycle for {self.device_name}: {e}")

            self._last_scan_time = current_time
            await asyncio.sleep(self.scan_interval)

    async def _read_control_inputs(self) -> None:
        """Read control commands from DataStore."""
        # Read breaker control command (from SCADA or attacker)
        breaker_command = await self.data_store.read_memory(
            self.device_name, "breaker_command"
        )

        if breaker_command is not None:
            # Breaker control requested
            new_position = bool(breaker_command)

            if new_position != self.breaker.position:
                logger.info(
                    f"Breaker control: {self.device_name} "
                    f"{'CLOSE' if new_position else 'OPEN'}"
                )

                self.breaker.position = new_position
                self.breaker.last_operation_time = self.sim_time.now()

                if not new_position:  # Opening counts as trip
                    self.breaker.trip_count += 1

    async def _update_measurements(self) -> None:
        """
        Update measurements from grid physics.

        This is a placeholder - in a full implementation, this would
        read from GridPhysics or PowerFlow engines via DataStore.
        """
        # TODO: Integrate with GridPhysics to get real grid frequency
        # freq = await self.data_store.read_memory("grid_physics_1", "frequency_hz")

        # For now, use simulated measurements
        # In practice, these would come from physics engines

        # If breaker is closed, show load current
        if self.breaker.position:
            # Simulate some load current
            self.measurements.current_a_a = self.rated_current_a * 0.7
            self.measurements.current_b_a = self.rated_current_a * 0.7
            self.measurements.current_c_a = self.rated_current_a * 0.7

            # Calculate power (simplified)
            voltage = self.measurements.voltage_a_v
            current = self.measurements.current_a_a
            self.measurements.active_power_kw = (
                voltage * current * 3 * 0.95
            ) / 1000  # PF=0.95
            self.measurements.reactive_power_kvar = (
                voltage * current * 3 * 0.31
            ) / 1000
        else:
            # Breaker open - no current flow
            self.measurements.current_a_a = 0.0
            self.measurements.current_b_a = 0.0
            self.measurements.current_c_a = 0.0
            self.measurements.active_power_kw = 0.0
            self.measurements.reactive_power_kvar = 0.0

    def _execute_protection(self) -> None:
        """Execute protection relay logic."""
        # Overcurrent protection
        max_current = max(
            self.measurements.current_a_a,
            self.measurements.current_b_a,
            self.measurements.current_c_a,
        )

        if max_current > self.current_max_a:
            if not self.protection.overcurrent_trip:
                logger.warning(
                    f"OVERCURRENT TRIP: {self.device_name} - {max_current:.1f}A"
                )
                self.protection.overcurrent_trip = True
                self._trip_breaker()

        # Undervoltage protection
        min_voltage = min(
            self.measurements.voltage_a_v,
            self.measurements.voltage_b_v,
            self.measurements.voltage_c_v,
        )

        if min_voltage < self.voltage_min_v:
            if not self.protection.undervoltage_trip:
                logger.warning(
                    f"UNDERVOLTAGE TRIP: {self.device_name} - {min_voltage:.1f}V"
                )
                self.protection.undervoltage_trip = True
                self._trip_breaker()

        # Overvoltage protection
        max_voltage = max(
            self.measurements.voltage_a_v,
            self.measurements.voltage_b_v,
            self.measurements.voltage_c_v,
        )

        if max_voltage > self.voltage_max_v:
            if not self.protection.overvoltage_trip:
                logger.warning(
                    f"OVERVOLTAGE TRIP: {self.device_name} - {max_voltage:.1f}V"
                )
                self.protection.overvoltage_trip = True
                self._trip_breaker()

        # Frequency protection
        freq = self.measurements.frequency_hz

        if freq < self.frequency_min_hz:
            if not self.protection.underfrequency_trip:
                logger.warning(
                    f"UNDERFREQUENCY TRIP: {self.device_name} - {freq:.3f}Hz"
                )
                self.protection.underfrequency_trip = True
                self._trip_breaker()

        if freq > self.frequency_max_hz:
            if not self.protection.overfrequency_trip:
                logger.warning(f"OVERFREQUENCY TRIP: {self.device_name} - {freq:.3f}Hz")
                self.protection.overfrequency_trip = True
                self._trip_breaker()

    def _trip_breaker(self) -> None:
        """Execute breaker trip."""
        self.breaker.position = False
        self.breaker.trip_count += 1
        self.breaker.last_operation_time = self.sim_time.now()
        logger.info(f"Breaker tripped: {self.device_name}")

    def _update_modbus_memory_map(self) -> None:
        """Update Modbus holding registers and coils."""
        # Holding registers (telemetry)
        self.holding_registers[0] = int(self.measurements.voltage_a_v)
        self.holding_registers[1] = int(self.measurements.voltage_b_v)
        self.holding_registers[2] = int(self.measurements.voltage_c_v)
        self.holding_registers[3] = int(self.measurements.current_a_a)
        self.holding_registers[4] = int(self.measurements.current_b_a)
        self.holding_registers[5] = int(self.measurements.current_c_a)
        self.holding_registers[6] = int(self.measurements.frequency_hz * 100)
        self.holding_registers[7] = int(self.measurements.active_power_kw)
        self.holding_registers[8] = int(self.measurements.reactive_power_kvar)
        self.holding_registers[9] = self.breaker.trip_count

        # Coils (status and control)
        self.coils[0] = self.breaker.position
        self.coils[10] = self.protection.overcurrent_trip
        self.coils[11] = self.protection.undervoltage_trip
        self.coils[12] = self.protection.overvoltage_trip
        self.coils[13] = self.protection.underfrequency_trip
        self.coils[14] = self.protection.overfrequency_trip

    def _update_iec104_information_objects(self) -> None:
        """Update IEC 104 information objects."""
        # Single-point information (M_SP_NA_1)
        self.iec104_single_points[100] = self.breaker.position
        self.iec104_single_points[110] = self.protection.overcurrent_trip
        self.iec104_single_points[111] = self.protection.undervoltage_trip
        self.iec104_single_points[112] = self.protection.overvoltage_trip
        self.iec104_single_points[113] = self.protection.underfrequency_trip
        self.iec104_single_points[114] = self.protection.overfrequency_trip

        # Measured values, normalised (M_ME_NA_1)
        # Normalise to 0.0-1.0 range based on rated values
        rated_v = self.rated_voltage_kv * 1000
        self.iec104_measured_values[200] = self.measurements.voltage_a_v / rated_v
        self.iec104_measured_values[201] = self.measurements.voltage_b_v / rated_v
        self.iec104_measured_values[202] = self.measurements.voltage_c_v / rated_v
        self.iec104_measured_values[203] = (
            self.measurements.current_a_a / self.rated_current_a
        )
        self.iec104_measured_values[204] = (
            self.measurements.current_b_a / self.rated_current_a
        )
        self.iec104_measured_values[205] = (
            self.measurements.current_c_a / self.rated_current_a
        )
        self.iec104_measured_values[206] = self.measurements.frequency_hz / 50.0
        self.iec104_measured_values[207] = self.measurements.active_power_kw / 1000.0
        self.iec104_measured_values[208] = (
            self.measurements.reactive_power_kvar / 1000.0
        )

    # ----------------------------------------------------------------
    # Memory map operations
    # ----------------------------------------------------------------

    def _initialise_memory_maps(self) -> None:
        """Initialise memory maps with default values."""
        # Holding registers
        for i in range(20):
            self.holding_registers[i] = 0

        # Coils
        for i in range(20):
            self.coils[i] = False

        # IEC 104 information objects
        for ioa in range(100, 120):
            self.iec104_single_points[ioa] = False

        for ioa in range(200, 220):
            self.iec104_measured_values[ioa] = 0.0

    async def _sync_to_datastore(self) -> None:
        """Synchronise all data to DataStore."""
        memory_map = {
            # Modbus memory map
            "holding_registers": self.holding_registers.copy(),
            "coils": self.coils.copy(),
            # IEC 104 information objects
            "iec104_single_points": self.iec104_single_points.copy(),
            "iec104_measured_values": self.iec104_measured_values.copy(),
            # Direct access to key values
            "breaker_position": self.breaker.position,
            "breaker_command": self.breaker.position,  # Reflects current state
            "voltage_a_v": self.measurements.voltage_a_v,
            "current_a_a": self.measurements.current_a_a,
            "frequency_hz": self.measurements.frequency_hz,
            "active_power_kw": self.measurements.active_power_kw,
        }

        await self.data_store.bulk_write_memory(self.device_name, memory_map)

    # ----------------------------------------------------------------
    # Public interface
    # ----------------------------------------------------------------

    def get_holding_register(self, address: int) -> int | None:
        """Read Modbus holding register."""
        return self.holding_registers.get(address)

    def get_coil(self, address: int) -> bool | None:
        """Read Modbus coil."""
        return self.coils.get(address)

    def set_coil(self, address: int, value: bool) -> bool:
        """Write Modbus coil (for breaker control)."""
        if address == 1:  # Breaker command
            self.breaker.position = value
            self.breaker.last_operation_time = self.sim_time.now()
            if not value:
                self.breaker.trip_count += 1
            return True
        return False

    def get_iec104_single_point(self, ioa: int) -> bool | None:
        """Read IEC 104 single-point information."""
        return self.iec104_single_points.get(ioa)

    def get_iec104_measured_value(self, ioa: int) -> float | None:
        """Read IEC 104 measured value."""
        return self.iec104_measured_values.get(ioa)

    async def send_iec104_command(self, ioa: int, value: bool) -> bool:
        """
        Process IEC 104 single command.

        Args:
            ioa: Information object address
            value: Command value (0=OFF, 1=ON)

        Returns:
            True if command executed, False otherwise
        """
        if ioa == 1000:  # Breaker control
            self.breaker.position = value
            self.breaker.last_operation_time = self.sim_time.now()
            if not value:
                self.breaker.trip_count += 1
            logger.info(
                f"IEC 104 command: {self.device_name} breaker "
                f"{'CLOSE' if value else 'OPEN'}"
            )
            return True

        return False

    async def get_telemetry(self) -> dict[str, Any]:
        """Get comprehensive telemetry snapshot."""
        return {
            "device_name": self.device_name,
            "device_type": "substation_plc",
            "breaker": {
                "position": self.breaker.position,
                "trip_count": self.breaker.trip_count,
                "last_operation": self.breaker.last_operation_time,
            },
            "measurements": {
                "voltage_a_v": self.measurements.voltage_a_v,
                "voltage_b_v": self.measurements.voltage_b_v,
                "voltage_c_v": self.measurements.voltage_c_v,
                "current_a_a": self.measurements.current_a_a,
                "current_b_a": self.measurements.current_b_a,
                "current_c_a": self.measurements.current_c_a,
                "frequency_hz": self.measurements.frequency_hz,
                "active_power_kw": self.measurements.active_power_kw,
                "reactive_power_kvar": self.measurements.reactive_power_kvar,
            },
            "protection": {
                "overcurrent": self.protection.overcurrent_trip,
                "undervoltage": self.protection.undervoltage_trip,
                "overvoltage": self.protection.overvoltage_trip,
                "underfrequency": self.protection.underfrequency_trip,
                "overfrequency": self.protection.overfrequency_trip,
            },
            "modbus": {
                "holding_registers": self.holding_registers.copy(),
                "coils": self.coils.copy(),
            },
            "iec104": {
                "common_address": self.common_address,
                "single_points": self.iec104_single_points.copy(),
                "measured_values": self.iec104_measured_values.copy(),
            },
        }
