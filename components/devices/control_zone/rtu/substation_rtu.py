# components/devices/control_zone/rtu/substation_rtu.py
"""
Substation Remote Terminal Unit for UU Power & Light Co.

DNP3-based RTU for distribution substation monitoring and control.
Monitors breakers, protection relays, and grid measurements.
"""

from dataclasses import dataclass
from enum import IntEnum
from typing import Any

from components.devices.control_zone.rtu.base_rtu import BaseRTU
from components.security.logging_system import AlarmPriority, AlarmState
from components.state.data_store import DataStore


class BreakerState(IntEnum):
    """Circuit breaker state enumeration."""

    UNKNOWN = 0
    OPEN = 1
    CLOSED = 2
    INTERMEDIATE = 3  # Transitioning
    FAULT = 4  # Tripped on fault


class RelayType(IntEnum):
    """Protection relay types per ANSI device numbers."""

    OVERCURRENT = 50  # Instantaneous overcurrent
    OVERCURRENT_TIME = 51  # Time overcurrent
    UNDERVOLTAGE = 27  # Undervoltage
    OVERVOLTAGE = 59  # Overvoltage
    UNDERFREQUENCY = 81  # Frequency relay
    DIFFERENTIAL = 87  # Differential protection
    DISTANCE = 21  # Distance relay
    RECLOSER = 79  # Reclosing relay


@dataclass
class ProtectionRelay:
    """Configuration for a protection relay."""

    relay_id: str
    relay_type: RelayType
    description: str
    pickup_value: float  # Trip threshold
    time_dial: float = 0.0  # Time delay (0 = instantaneous)
    enabled: bool = True
    tripped: bool = False
    trip_count: int = 0


@dataclass
class Breaker:
    """Configuration for a circuit breaker."""

    breaker_id: str
    description: str
    state: BreakerState = BreakerState.OPEN
    rated_current: float = 1200.0  # Amps
    rated_voltage: float = 11000.0  # Volts (11kV)
    fault_current: float = 0.0
    operation_count: int = 0
    last_trip_time: float = 0.0


@dataclass
class DNP3PointMap:
    """
    DNP3 point addressing for substation data.

    Per IEEE 1815 / DNP3 specification:
    - Binary Inputs (BI): Status points (breaker states, alarms)
    - Binary Outputs (BO): Control points (breaker controls)
    - Analog Inputs (AI): Measurements (voltage, current, power)
    - Counters: Accumulated values (energy, operations)
    """

    # Binary Input base addresses
    bi_breaker_status: int = 0  # Breaker closed status
    bi_relay_tripped: int = 100  # Relay trip status
    bi_alarms: int = 200  # General alarms

    # Binary Output base addresses
    bo_breaker_control: int = 0  # Trip/close commands

    # Analog Input base addresses
    ai_voltage: int = 0  # Voltage measurements
    ai_current: int = 100  # Current measurements
    ai_power: int = 200  # Power measurements
    ai_frequency: int = 300  # Frequency measurements

    # Counter base addresses
    cnt_energy: int = 0  # Energy accumulators
    cnt_operations: int = 100  # Operation counts


class SubstationRTU(BaseRTU):
    """
    DNP3-based Remote Terminal Unit for distribution substations.

    Monitors and controls:
    - Circuit breakers (trip/close operations)
    - Protection relays (overcurrent, undervoltage, etc.)
    - Grid measurements (voltage, current, power, frequency)
    - Energy metering (kWh accumulators)

    DNP3 Features:
    - Unsolicited responses for events
    - Time synchronisation
    - Report-by-exception with deadbands

    Example:
        >>> rtu = SubstationRTU(
        ...     device_name="substation_rtu_1",
        ...     device_id=100,
        ...     data_store=data_store,
        ...     description="Campus Substation RTU",
        ...     outstation_address=100,
        ... )
        >>> rtu.add_breaker("BKR-001", "Main Incomer")
        >>> rtu.add_breaker("BKR-002", "Feeder 1")
        >>> rtu.add_relay("R50", RelayType.OVERCURRENT, 1200.0)
        >>> await rtu.initialise()
        >>> await rtu.start()
    """

    MAX_BREAKERS = 32
    MAX_RELAYS = 64

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        description: str = "",
        scan_interval: float = 1.0,
        outstation_address: int = 1,
        master_address: int = 1,
        dnp3_port: int = 20000,
        point_map: DNP3PointMap | None = None,
        grid_physics: Any | None = None,
    ):
        """
        Initialise Substation RTU.

        Args:
            device_name: Unique device identifier
            device_id: Device ID for DataStore
            data_store: Reference to DataStore
            description: RTU description
            scan_interval: Data acquisition interval (seconds)
            outstation_address: DNP3 outstation address
            master_address: DNP3 master address
            dnp3_port: DNP3 TCP port
            point_map: DNP3 point address mapping
            grid_physics: Optional GridPhysics engine reference
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
            report_by_exception=True,
        )

        # DNP3 configuration
        self.outstation_address = outstation_address
        self.master_address = master_address
        self.dnp3_port = dnp3_port
        self.point_map = point_map or DNP3PointMap()

        # Physics integration
        self.grid_physics = grid_physics

        # Substation equipment
        self.breakers: dict[str, Breaker] = {}
        self.relays: dict[str, ProtectionRelay] = {}

        # Grid measurements (simulated or from physics)
        self.voltage_a: float = 11000.0  # Phase A voltage (V)
        self.voltage_b: float = 11000.0  # Phase B voltage (V)
        self.voltage_c: float = 11000.0  # Phase C voltage (V)
        self.current_a: float = 0.0  # Phase A current (A)
        self.current_b: float = 0.0  # Phase B current (A)
        self.current_c: float = 0.0  # Phase C current (A)
        self.active_power: float = 0.0  # kW
        self.reactive_power: float = 0.0  # kVAR
        self.power_factor: float = 1.0
        self.frequency: float = 50.0  # Hz (Ankh-Morpork standard)

        # Energy accumulators
        self.energy_import_kwh: float = 0.0
        self.energy_export_kwh: float = 0.0

        # Alarms
        self.alarm_comm_fail: bool = False
        self.alarm_low_voltage: bool = False
        self.alarm_high_voltage: bool = False
        self.alarm_overcurrent: bool = False
        self.alarm_frequency: bool = False

        # Set default deadbands for analogue points
        self._set_default_deadbands()

        self.logger.info(
            f"SubstationRTU '{device_name}' created "
            f"(DNP3 outstation: {outstation_address})"
        )

    def _device_type(self) -> str:
        """Return device type for DataStore registration."""
        return "substation_rtu"

    def _supported_protocols(self) -> list[str]:
        """Return list of supported protocols."""
        return ["dnp3", "modbus"]

    def _set_default_deadbands(self) -> None:
        """Set default deadbands for report-by-exception."""
        # Voltage deadband: 0.5% of nominal
        self.set_deadband("voltage_a", 55.0)
        self.set_deadband("voltage_b", 55.0)
        self.set_deadband("voltage_c", 55.0)
        # Current deadband: 1A
        self.set_deadband("current_a", 1.0)
        self.set_deadband("current_b", 1.0)
        self.set_deadband("current_c", 1.0)
        # Power deadband: 10kW
        self.set_deadband("active_power", 10.0)
        self.set_deadband("reactive_power", 10.0)
        # Frequency deadband: 0.01Hz
        self.set_deadband("frequency", 0.01)

    # ----------------------------------------------------------------
    # Equipment configuration
    # ----------------------------------------------------------------

    def add_breaker(
        self,
        breaker_id: str,
        description: str,
        rated_current: float = 1200.0,
        rated_voltage: float = 11000.0,
        initial_state: BreakerState = BreakerState.OPEN,
    ) -> bool:
        """
        Add a circuit breaker to the substation.

        Args:
            breaker_id: Unique breaker identifier (e.g., "BKR-001")
            description: Breaker description
            rated_current: Rated current in Amps
            rated_voltage: Rated voltage in Volts
            initial_state: Initial breaker state

        Returns:
            True if added successfully
        """
        if len(self.breakers) >= self.MAX_BREAKERS:
            self.logger.error(
                f"SubstationRTU '{self.device_name}': "
                f"Maximum breakers ({self.MAX_BREAKERS}) reached"
            )
            return False

        if breaker_id in self.breakers:
            self.logger.warning(
                f"SubstationRTU '{self.device_name}': "
                f"Breaker '{breaker_id}' already exists"
            )
            return False

        self.breakers[breaker_id] = Breaker(
            breaker_id=breaker_id,
            description=description,
            rated_current=rated_current,
            rated_voltage=rated_voltage,
            state=initial_state,
        )

        self.logger.info(
            f"SubstationRTU '{self.device_name}': "
            f"Added breaker '{breaker_id}' - {description}"
        )
        return True

    def add_relay(
        self,
        relay_id: str,
        relay_type: RelayType,
        pickup_value: float,
        description: str = "",
        time_dial: float = 0.0,
    ) -> bool:
        """
        Add a protection relay to the substation.

        Args:
            relay_id: Unique relay identifier (e.g., "R50-001")
            relay_type: Type of protection relay
            pickup_value: Trip threshold value
            description: Relay description
            time_dial: Time delay setting (0 = instantaneous)

        Returns:
            True if added successfully
        """
        if len(self.relays) >= self.MAX_RELAYS:
            self.logger.error(
                f"SubstationRTU '{self.device_name}': "
                f"Maximum relays ({self.MAX_RELAYS}) reached"
            )
            return False

        if relay_id in self.relays:
            self.logger.warning(
                f"SubstationRTU '{self.device_name}': "
                f"Relay '{relay_id}' already exists"
            )
            return False

        if not description:
            description = f"{relay_type.name} relay"

        self.relays[relay_id] = ProtectionRelay(
            relay_id=relay_id,
            relay_type=relay_type,
            description=description,
            pickup_value=pickup_value,
            time_dial=time_dial,
        )

        self.logger.info(
            f"SubstationRTU '{self.device_name}': "
            f"Added relay '{relay_id}' ({relay_type.name}) - {description}"
        )
        return True

    # ----------------------------------------------------------------
    # BaseRTU abstract method implementations
    # ----------------------------------------------------------------

    async def _initialise_memory_map(self) -> None:
        """Initialise DNP3 point map structure."""
        self.memory_map = {
            # DNP3 configuration
            "dnp3_outstation_address": self.outstation_address,
            "dnp3_master_address": self.master_address,
            "dnp3_port": self.dnp3_port,
            # Grid measurements (Analog Inputs)
            "voltage_a": self.voltage_a,
            "voltage_b": self.voltage_b,
            "voltage_c": self.voltage_c,
            "current_a": self.current_a,
            "current_b": self.current_b,
            "current_c": self.current_c,
            "active_power": self.active_power,
            "reactive_power": self.reactive_power,
            "power_factor": self.power_factor,
            "frequency": self.frequency,
            # Energy counters
            "energy_import_kwh": self.energy_import_kwh,
            "energy_export_kwh": self.energy_export_kwh,
            # Alarms (Binary Inputs)
            "alarm_comm_fail": self.alarm_comm_fail,
            "alarm_low_voltage": self.alarm_low_voltage,
            "alarm_high_voltage": self.alarm_high_voltage,
            "alarm_overcurrent": self.alarm_overcurrent,
            "alarm_frequency": self.alarm_frequency,
            # Breaker states
            "breakers": {},
            # Relay states
            "relays": {},
        }

        # Initialise breaker states
        for breaker_id, breaker in self.breakers.items():
            self.memory_map["breakers"][breaker_id] = {
                "state": breaker.state,
                "description": breaker.description,
                "operation_count": breaker.operation_count,
            }

        # Initialise relay states
        for relay_id, relay in self.relays.items():
            self.memory_map["relays"][relay_id] = {
                "type": relay.relay_type.name,
                "tripped": relay.tripped,
                "enabled": relay.enabled,
                "trip_count": relay.trip_count,
            }

    async def _read_inputs(self) -> None:
        """
        Read inputs from grid physics or simulated values.

        Updates grid measurements and equipment states.
        """
        # Read from physics engine if available
        if self.grid_physics:
            try:
                grid_state = self.grid_physics.get_state()

                # Get measurements for this substation
                substation_id = self.device_name.replace("_rtu", "")
                if substation_id in grid_state.get("substations", {}):
                    sub_data = grid_state["substations"][substation_id]
                    self.voltage_a = sub_data.get("voltage_a", self.voltage_a)
                    self.voltage_b = sub_data.get("voltage_b", self.voltage_b)
                    self.voltage_c = sub_data.get("voltage_c", self.voltage_c)
                    self.current_a = sub_data.get("current_a", self.current_a)
                    self.current_b = sub_data.get("current_b", self.current_b)
                    self.current_c = sub_data.get("current_c", self.current_c)
                    self.active_power = sub_data.get("active_power", self.active_power)
                    self.reactive_power = sub_data.get(
                        "reactive_power", self.reactive_power
                    )
                    self.frequency = sub_data.get("frequency", self.frequency)

                # Calculate power factor
                apparent_power = (self.active_power**2 + self.reactive_power**2) ** 0.5
                if apparent_power > 0:
                    self.power_factor = self.active_power / apparent_power
                else:
                    self.power_factor = 1.0

            except Exception as e:
                self.logger.error(
                    f"SubstationRTU '{self.device_name}': "
                    f"Error reading physics: {e}"
                )

        # Update memory map with current values
        self.memory_map["voltage_a"] = self.voltage_a
        self.memory_map["voltage_b"] = self.voltage_b
        self.memory_map["voltage_c"] = self.voltage_c
        self.memory_map["current_a"] = self.current_a
        self.memory_map["current_b"] = self.current_b
        self.memory_map["current_c"] = self.current_c
        self.memory_map["active_power"] = self.active_power
        self.memory_map["reactive_power"] = self.reactive_power
        self.memory_map["power_factor"] = self.power_factor
        self.memory_map["frequency"] = self.frequency

        # Update breaker states in memory map
        for breaker_id, breaker in self.breakers.items():
            self.memory_map["breakers"][breaker_id] = {
                "state": breaker.state,
                "description": breaker.description,
                "operation_count": breaker.operation_count,
            }

        # Update relay states in memory map
        for relay_id, relay in self.relays.items():
            self.memory_map["relays"][relay_id] = {
                "type": relay.relay_type.name,
                "tripped": relay.tripped,
                "enabled": relay.enabled,
                "trip_count": relay.trip_count,
            }

    async def _process_data(self) -> None:
        """
        Process acquired data and check alarm conditions.

        Evaluates protection relay logic and updates alarms.
        """
        # Calculate average voltage for alarm checking
        avg_voltage = (self.voltage_a + self.voltage_b + self.voltage_c) / 3
        nominal_voltage = 11000.0  # 11kV nominal

        # Check voltage alarms (±10% of nominal)
        self.alarm_low_voltage = avg_voltage < (nominal_voltage * 0.9)
        self.alarm_high_voltage = avg_voltage > (nominal_voltage * 1.1)

        # Check overcurrent alarm
        max_current = max(self.current_a, self.current_b, self.current_c)
        self.alarm_overcurrent = any(
            max_current > breaker.rated_current for breaker in self.breakers.values()
        )

        # Check frequency alarm (±0.5Hz of nominal 50Hz)
        self.alarm_frequency = abs(self.frequency - 50.0) > 0.5

        # Update alarms in memory map
        self.memory_map["alarm_low_voltage"] = self.alarm_low_voltage
        self.memory_map["alarm_high_voltage"] = self.alarm_high_voltage
        self.memory_map["alarm_overcurrent"] = self.alarm_overcurrent
        self.memory_map["alarm_frequency"] = self.alarm_frequency
        self.memory_map["alarm_comm_fail"] = self.alarm_comm_fail

        # Evaluate protection relays
        await self._evaluate_protection()

        # Accumulate energy (simplified)
        dt = self.scan_interval / 3600.0  # Convert to hours
        if self.active_power >= 0:
            self.energy_import_kwh += self.active_power * dt
        else:
            self.energy_export_kwh += abs(self.active_power) * dt

        self.memory_map["energy_import_kwh"] = self.energy_import_kwh
        self.memory_map["energy_export_kwh"] = self.energy_export_kwh

    async def _evaluate_protection(self) -> None:
        """Evaluate protection relay conditions and trip if needed."""
        max_current = max(self.current_a, self.current_b, self.current_c)
        avg_voltage = (self.voltage_a + self.voltage_b + self.voltage_c) / 3

        for relay_id, relay in self.relays.items():
            if not relay.enabled:
                continue

            should_trip = False

            if relay.relay_type == RelayType.OVERCURRENT:
                # Instantaneous overcurrent
                should_trip = max_current > relay.pickup_value

            elif relay.relay_type == RelayType.OVERCURRENT_TIME:
                # Time overcurrent (simplified - actual would use inverse curves)
                should_trip = max_current > relay.pickup_value

            elif relay.relay_type == RelayType.UNDERVOLTAGE:
                should_trip = avg_voltage < relay.pickup_value

            elif relay.relay_type == RelayType.OVERVOLTAGE:
                should_trip = avg_voltage > relay.pickup_value

            elif relay.relay_type == RelayType.UNDERFREQUENCY:
                should_trip = self.frequency < relay.pickup_value

            if should_trip and not relay.tripped:
                relay.tripped = True
                relay.trip_count += 1
                await self.logger.log_alarm(
                    message=f"SubstationRTU '{self.device_name}': Relay '{relay_id}' ({relay.relay_type.name}) TRIPPED",
                    priority=AlarmPriority.CRITICAL,
                    state=AlarmState.ACTIVE,
                    device=self.device_name,
                    data={
                        "device": self.device_name,
                        "relay_id": relay_id,
                        "relay_type": relay.relay_type.name,
                        "trip_count": relay.trip_count,
                        "pickup_value": relay.pickup_value,
                        "current": max_current,
                        "voltage": avg_voltage,
                    },
                )

                # Trip associated breakers (simplified - trips all)
                for breaker in self.breakers.values():
                    if breaker.state == BreakerState.CLOSED:
                        await self.trip_breaker(breaker.breaker_id)

    async def _report_to_master(self) -> None:
        """
        Report data to SCADA master via DNP3.

        In a full implementation, this would format DNP3 responses.
        For simulation, we update the DataStore.
        """
        # The base class _scan_cycle already writes memory_map to DataStore
        # This method is for protocol-specific reporting

        # Log significant events
        if self.alarm_overcurrent:
            await self.logger.log_alarm(
                message=f"SubstationRTU '{self.device_name}': Overcurrent alarm active",
                priority=AlarmPriority.HIGH,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={
                    "device": self.device_name,
                    "alarm_type": "overcurrent",
                    "current_a": self.current_a,
                    "current_b": self.current_b,
                    "current_c": self.current_c,
                },
            )
        if self.alarm_low_voltage or self.alarm_high_voltage:
            alarm_type = "low_voltage" if self.alarm_low_voltage else "high_voltage"
            await self.logger.log_alarm(
                message=f"SubstationRTU '{self.device_name}': Voltage alarm active ({alarm_type})",
                priority=AlarmPriority.HIGH,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={
                    "device": self.device_name,
                    "alarm_type": alarm_type,
                    "voltage_a": self.voltage_a,
                    "voltage_b": self.voltage_b,
                    "voltage_c": self.voltage_c,
                    "alarm_low_voltage": self.alarm_low_voltage,
                    "alarm_high_voltage": self.alarm_high_voltage,
                },
            )

    # ----------------------------------------------------------------
    # Breaker control operations
    # ----------------------------------------------------------------

    async def trip_breaker(self, breaker_id: str) -> bool:
        """
        Trip (open) a circuit breaker.

        Args:
            breaker_id: Breaker to trip

        Returns:
            True if operation successful
        """
        if breaker_id not in self.breakers:
            self.logger.error(
                f"SubstationRTU '{self.device_name}': "
                f"Unknown breaker '{breaker_id}'"
            )
            return False

        breaker = self.breakers[breaker_id]

        if breaker.state == BreakerState.OPEN:
            self.logger.debug(
                f"SubstationRTU '{self.device_name}': "
                f"Breaker '{breaker_id}' already open"
            )
            return True

        # Execute trip
        breaker.state = BreakerState.OPEN
        breaker.operation_count += 1
        breaker.last_trip_time = self.sim_time.now()

        self.logger.info(
            f"SubstationRTU '{self.device_name}': "
            f"Breaker '{breaker_id}' TRIPPED (operation #{breaker.operation_count})"
        )

        # Update physics if available
        if self.grid_physics:
            try:
                self.grid_physics.set_breaker_state(breaker_id, False)
            except Exception as e:
                self.logger.error(f"Error updating physics: {e}")

        return True

    async def close_breaker(self, breaker_id: str) -> bool:
        """
        Close a circuit breaker.

        Args:
            breaker_id: Breaker to close

        Returns:
            True if operation successful
        """
        if breaker_id not in self.breakers:
            self.logger.error(
                f"SubstationRTU '{self.device_name}': "
                f"Unknown breaker '{breaker_id}'"
            )
            return False

        breaker = self.breakers[breaker_id]

        if breaker.state == BreakerState.CLOSED:
            self.logger.debug(
                f"SubstationRTU '{self.device_name}': "
                f"Breaker '{breaker_id}' already closed"
            )
            return True

        # Check if any relay is still tripped
        for relay in self.relays.values():
            if relay.tripped:
                self.logger.warning(
                    f"SubstationRTU '{self.device_name}': "
                    f"Cannot close breaker '{breaker_id}' - "
                    f"relay '{relay.relay_id}' still tripped"
                )
                return False

        # Execute close
        breaker.state = BreakerState.CLOSED
        breaker.operation_count += 1

        self.logger.info(
            f"SubstationRTU '{self.device_name}': "
            f"Breaker '{breaker_id}' CLOSED (operation #{breaker.operation_count})"
        )

        # Update physics if available
        if self.grid_physics:
            try:
                self.grid_physics.set_breaker_state(breaker_id, True)
            except Exception as e:
                self.logger.error(f"Error updating physics: {e}")

        return True

    def reset_relay(self, relay_id: str) -> bool:
        """
        Reset a tripped protection relay.

        Args:
            relay_id: Relay to reset

        Returns:
            True if reset successful
        """
        if relay_id not in self.relays:
            self.logger.error(
                f"SubstationRTU '{self.device_name}': " f"Unknown relay '{relay_id}'"
            )
            return False

        relay = self.relays[relay_id]
        relay.tripped = False

        self.logger.info(
            f"SubstationRTU '{self.device_name}': " f"Relay '{relay_id}' reset"
        )
        return True

    # ----------------------------------------------------------------
    # Measurement setters (for testing/simulation)
    # ----------------------------------------------------------------

    def set_voltage(
        self, phase_a: float, phase_b: float | None = None, phase_c: float | None = None
    ) -> None:
        """Set three-phase voltage values."""
        self.voltage_a = phase_a
        self.voltage_b = phase_b if phase_b is not None else phase_a
        self.voltage_c = phase_c if phase_c is not None else phase_a

    def set_current(
        self, phase_a: float, phase_b: float | None = None, phase_c: float | None = None
    ) -> None:
        """Set three-phase current values."""
        self.current_a = phase_a
        self.current_b = phase_b if phase_b is not None else phase_a
        self.current_c = phase_c if phase_c is not None else phase_a

    def set_power(self, active_kw: float, reactive_kvar: float = 0.0) -> None:
        """Set power measurements."""
        self.active_power = active_kw
        self.reactive_power = reactive_kvar

    def set_frequency(self, frequency_hz: float) -> None:
        """Set grid frequency."""
        self.frequency = frequency_hz

    # ----------------------------------------------------------------
    # Status and diagnostics
    # ----------------------------------------------------------------

    async def get_substation_status(self) -> dict[str, Any]:
        """Get comprehensive substation status."""
        rtu_status = await self.get_rtu_status()

        return {
            **rtu_status,
            "dnp3_outstation_address": self.outstation_address,
            "dnp3_master_address": self.master_address,
            "grid": {
                "voltage_a": self.voltage_a,
                "voltage_b": self.voltage_b,
                "voltage_c": self.voltage_c,
                "current_a": self.current_a,
                "current_b": self.current_b,
                "current_c": self.current_c,
                "active_power": self.active_power,
                "reactive_power": self.reactive_power,
                "power_factor": self.power_factor,
                "frequency": self.frequency,
            },
            "energy": {
                "import_kwh": self.energy_import_kwh,
                "export_kwh": self.energy_export_kwh,
            },
            "alarms": {
                "comm_fail": self.alarm_comm_fail,
                "low_voltage": self.alarm_low_voltage,
                "high_voltage": self.alarm_high_voltage,
                "overcurrent": self.alarm_overcurrent,
                "frequency": self.alarm_frequency,
            },
            "breakers": {
                bid: {
                    "state": b.state.name,
                    "operations": b.operation_count,
                }
                for bid, b in self.breakers.items()
            },
            "relays": {
                rid: {
                    "type": r.relay_type.name,
                    "tripped": r.tripped,
                    "trip_count": r.trip_count,
                }
                for rid, r in self.relays.items()
            },
        }
