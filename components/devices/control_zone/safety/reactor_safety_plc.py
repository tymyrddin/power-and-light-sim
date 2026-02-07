# components/devices/control_zone/safety/reactor_safety_plc.py
"""
Reactor Safety Instrumented System (SIS) device class.

Models the independent safety PLC for the Alchemical Reactor at UU Power & Light Co.
Certified to SIL3 standards, monitors critical parameters and initiates SCRAM
when safety limits are exceeded.

Safety Instrumented Functions (SIFs):
- SIF-R01: High core temperature protection (>450°C critical)
- SIF-R02: High vessel pressure protection (>150 bar)
- SIF-R03: Thaumic field instability protection (<30% stability)
- SIF-R04: Containment integrity protection (<50% integrity)
- SIF-R05: Loss of coolant flow protection (<10% flow)

Memory Map (S7/Modbus gateway):
-----------------------------------------------------------------
Discrete Inputs (Read-only booleans):
  0: Reactor active
  1: High temperature (SIF-R01)
  2: High pressure (SIF-R02)
  3: Thaumic instability (SIF-R03)
  4: Containment breach (SIF-R04)
  5: Low coolant flow (SIF-R05)
  6: SCRAM active
  7: System healthy

Input Registers (Read-only 16-bit):
  0: Core temperature channel A (degC)
  1: Core temperature channel B (degC)
  2: Vessel pressure channel A (bar * 10)
  3: Vessel pressure channel B (bar * 10)
  4: Thaumic field strength (per cent)
  5: Containment integrity (per cent)
  6: Coolant flow rate (per cent)
  7: Demand count
  8: Fault count
  9: Diagnostic status

Coils (Read/write booleans):
  0: Manual SCRAM command
  1: SCRAM reset command
  2: Bypass enable (REQUIRES AUTHORISATION)

Holding Registers (Read/write 16-bit):
  0: Temperature trip setpoint (degC)
  1: Pressure trip setpoint (bar * 10)
  2: Thaumic stability trip (per cent)
  3: Containment trip (per cent)
  4: Coolant flow trip (per cent)
"""

from typing import Any

from components.devices.control_zone.safety.base_safety_controller import (
    BaseSafetyController,
    SafetyIntegrityLevel,
    VotingArchitecture,
)
from components.physics.reactor_physics import ReactorPhysics
from components.security.logging_system import AlarmPriority, AlarmState
from components.state.data_store import DataStore


class ReactorSafetyPLC(BaseSafetyController):
    """
    Safety Instrumented System for Alchemical Reactor.

    Independent SIL3-rated safety PLC that monitors reactor critical
    parameters and initiates emergency SCRAM when safety limits are exceeded.

    The reactor's unique thaumic component requires special monitoring
    beyond conventional nuclear safety systems.
    """

    # S7/Modbus register definitions for adapter setup (reference only)
    DEFAULT_SETUP = {
        "discrete_inputs": {
            0: False,  # Reactor active
            1: False,  # High temperature (SIF-R01)
            2: False,  # High pressure (SIF-R02)
            3: False,  # Thaumic instability (SIF-R03)
            4: False,  # Containment breach (SIF-R04)
            5: False,  # Low coolant flow (SIF-R05)
            6: False,  # SCRAM active
            7: True,  # System healthy
        },
        "input_registers": {
            0: 25,  # Core temp channel A (degC)
            1: 25,  # Core temp channel B (degC)
            2: 10,  # Vessel pressure channel A (bar * 10)
            3: 10,  # Vessel pressure channel B (bar * 10)
            4: 100,  # Thaumic field strength (%)
            5: 100,  # Containment integrity (%)
            6: 0,  # Coolant flow rate (%)
            7: 0,  # Demand count
            8: 0,  # Fault count
            9: 0,  # Diagnostic status
        },
        "coils": {
            0: False,  # Manual SCRAM command
            1: False,  # SCRAM reset command
            2: False,  # Bypass enable
        },
        "holding_registers": {
            0: 450,  # Temperature trip setpoint (degC)
            1: 1500,  # Pressure trip setpoint (bar * 10)
            2: 30,  # Thaumic stability trip (%)
            3: 50,  # Containment trip (%)
            4: 10,  # Coolant flow trip (%)
        },
    }

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        reactor_physics: ReactorPhysics,
        description: str = "Reactor Safety PLC (Independent SIL-rated)",
        scan_interval: float = 0.025,  # 25ms for reactor safety (faster than turbine)
    ):
        """
        Initialise reactor safety PLC.

        Args:
            device_name: Unique SIS identifier
            device_id: Controller address
            data_store: Reference to DataStore
            reactor_physics: ReactorPhysics engine for monitoring
            description: Controller description
            scan_interval: Safety logic scan time (25ms for reactor)
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            sil_level=SafetyIntegrityLevel.SIL3,  # Higher SIL for reactor
            voting=VotingArchitecture.TWO_OUT_OF_THREE,
            description=description,
            scan_interval=scan_interval,
        )

        self.reactor_physics = reactor_physics

        # Safety trip setpoints (from reactor parameters)
        self._temp_trip_c = reactor_physics.params.critical_temperature_c  # 450°C
        self._pressure_trip_bar = (
            reactor_physics.params.max_safe_pressure_bar
        )  # 150 bar
        self._thaumic_trip_percent = 30  # Trip below 30% stability
        self._containment_trip_percent = 50  # Trip below 50% integrity
        self._coolant_flow_trip_percent = 10  # Trip below 10% flow

        # Simulated dual-channel inputs
        self._temp_channel_a = 25.0
        self._temp_channel_b = 25.0
        self._pressure_channel_a = 1.0
        self._pressure_channel_b = 1.0

        # Alarm state tracking (individual SIF alarms)
        self.scram_alarm_raised = False
        self.diagnostic_fault_alarm_raised = False
        self.high_temp_alarm_raised = False
        self.high_pressure_alarm_raised = False
        self.thaumic_unstable_alarm_raised = False
        self.containment_breach_alarm_raised = False
        self.low_coolant_alarm_raised = False

        self.logger.info(
            f"ReactorSafetyPLC '{device_name}' created "
            f"(temp trip: {self._temp_trip_c}°C, thaumic trip: {self._thaumic_trip_percent}%)"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return device type."""
        return "reactor_safety_plc"

    def _supported_protocols(self) -> list[str]:
        """Supported protocols - Siemens safety uses S7."""
        return ["s7", "modbus"]

    async def _initialise_memory_map(self) -> None:
        """Initialise memory map for reactor safety system."""
        # Discrete inputs (read-only status bits)
        self.memory_map["discrete_inputs[0]"] = False  # Reactor active
        self.memory_map["discrete_inputs[1]"] = False  # High temperature
        self.memory_map["discrete_inputs[2]"] = False  # High pressure
        self.memory_map["discrete_inputs[3]"] = False  # Thaumic instability
        self.memory_map["discrete_inputs[4]"] = False  # Containment breach
        self.memory_map["discrete_inputs[5]"] = False  # Low coolant flow
        self.memory_map["discrete_inputs[6]"] = False  # SCRAM active
        self.memory_map["discrete_inputs[7]"] = True  # System healthy

        # Input registers (read-only telemetry)
        self.memory_map["input_registers[0]"] = 25  # Temp channel A
        self.memory_map["input_registers[1]"] = 25  # Temp channel B
        self.memory_map["input_registers[2]"] = 10  # Pressure channel A * 10
        self.memory_map["input_registers[3]"] = 10  # Pressure channel B * 10
        self.memory_map["input_registers[4]"] = 100  # Thaumic strength %
        self.memory_map["input_registers[5]"] = 100  # Containment %
        self.memory_map["input_registers[6]"] = 0  # Coolant flow %
        self.memory_map["input_registers[7]"] = 0  # Demand count
        self.memory_map["input_registers[8]"] = 0  # Fault count
        self.memory_map["input_registers[9]"] = 0  # Diagnostic status

        # Coils (read/write control bits)
        self.memory_map["coils[0]"] = False  # Manual SCRAM
        self.memory_map["coils[1]"] = False  # SCRAM reset
        self.memory_map["coils[2]"] = False  # Bypass enable

        # Holding registers (read/write setpoints)
        self.memory_map["holding_registers[0]"] = int(self._temp_trip_c)
        self.memory_map["holding_registers[1]"] = int(self._pressure_trip_bar * 10)
        self.memory_map["holding_registers[2]"] = self._thaumic_trip_percent
        self.memory_map["holding_registers[3]"] = self._containment_trip_percent
        self.memory_map["holding_registers[4]"] = self._coolant_flow_trip_percent

        self.logger.debug(
            f"ReactorSafetyPLC '{self.device_name}' memory map initialised"
        )

    # ----------------------------------------------------------------
    # BaseSafetyController implementation
    # ----------------------------------------------------------------

    async def _read_safety_inputs(self) -> None:
        """
        Read safety-critical inputs from reactor physics.

        Simulates dual-channel redundant sensors.
        """
        reactor_telem = self.reactor_physics.get_telemetry()

        # Get base values
        actual_temp = reactor_telem.get("core_temperature_c", 25)
        actual_pressure = reactor_telem.get("vessel_pressure_bar", 1)
        thaumic_strength = reactor_telem.get("thaumic_field_strength", 1.0)
        containment = reactor_telem.get("containment_integrity_percent", 100)
        coolant_flow = reactor_telem.get("coolant_flow_percent", 0)

        # Simulate dual-channel sensors with small discrepancy
        import random

        self._temp_channel_a = actual_temp * (1.0 + random.uniform(-0.005, 0.005))
        self._temp_channel_b = actual_temp * (1.0 + random.uniform(-0.005, 0.005))
        self._pressure_channel_a = actual_pressure * (1.0 + random.uniform(-0.01, 0.01))
        self._pressure_channel_b = actual_pressure * (1.0 + random.uniform(-0.01, 0.01))

        # Update input registers
        self.memory_map["input_registers[0]"] = int(self._temp_channel_a)
        self.memory_map["input_registers[1]"] = int(self._temp_channel_b)
        self.memory_map["input_registers[2]"] = int(self._pressure_channel_a * 10)
        self.memory_map["input_registers[3]"] = int(self._pressure_channel_b * 10)
        self.memory_map["input_registers[4]"] = int(thaumic_strength * 100)
        self.memory_map["input_registers[5]"] = int(containment)
        self.memory_map["input_registers[6]"] = int(coolant_flow)

        # Update reactor active status
        self.memory_map["discrete_inputs[0]"] = reactor_telem.get(
            "reactor_active", False
        )

    async def _execute_safety_logic(self) -> bool:
        """
        Execute safety instrumented functions.

        Returns:
            True if SCRAM demanded
        """
        # Read trip setpoints
        temp_trip = self.memory_map.get("holding_registers[0]", 450)
        pressure_trip = self.memory_map.get("holding_registers[1]", 1500) / 10.0
        thaumic_trip = self.memory_map.get("holding_registers[2]", 30)
        containment_trip = self.memory_map.get("holding_registers[3]", 50)
        coolant_trip = self.memory_map.get("holding_registers[4]", 10)

        safety_demand = False

        # SIF-R01: High temperature (2oo2 voting)
        temp_a_trip = self._temp_channel_a > temp_trip
        temp_b_trip = self._temp_channel_b > temp_trip
        high_temp = temp_a_trip and temp_b_trip

        if high_temp:
            self.logger.warning(
                f"ReactorSafetyPLC '{self.device_name}': "
                f"SIF-R01 HIGH TEMP - A:{self._temp_channel_a:.1f} "
                f"B:{self._temp_channel_b:.1f} > {temp_trip}°C"
            )
            safety_demand = True

        self.memory_map["discrete_inputs[1]"] = high_temp

        # SIF-R02: High pressure (2oo2 voting)
        press_a_trip = self._pressure_channel_a > pressure_trip
        press_b_trip = self._pressure_channel_b > pressure_trip
        high_pressure = press_a_trip and press_b_trip

        if high_pressure:
            self.logger.warning(
                f"ReactorSafetyPLC '{self.device_name}': "
                f"SIF-R02 HIGH PRESSURE - A:{self._pressure_channel_a:.1f} "
                f"B:{self._pressure_channel_b:.1f} > {pressure_trip} bar"
            )
            safety_demand = True

        self.memory_map["discrete_inputs[2]"] = high_pressure

        # SIF-R03: Thaumic instability (single channel - unique to this reactor)
        thaumic_strength = self.memory_map.get("input_registers[4]", 100)
        thaumic_unstable = thaumic_strength < thaumic_trip

        if thaumic_unstable:
            self.logger.warning(
                f"ReactorSafetyPLC '{self.device_name}': "
                f"SIF-R03 THAUMIC INSTABILITY - {thaumic_strength}% < {thaumic_trip}%"
            )
            safety_demand = True

        self.memory_map["discrete_inputs[3]"] = thaumic_unstable

        # SIF-R04: Containment breach
        containment = self.memory_map.get("input_registers[5]", 100)
        containment_breach = containment < containment_trip

        if containment_breach:
            self.logger.critical(
                f"ReactorSafetyPLC '{self.device_name}': "
                f"SIF-R04 CONTAINMENT BREACH - {containment}% < {containment_trip}%"
            )
            safety_demand = True

        self.memory_map["discrete_inputs[4]"] = containment_breach

        # SIF-R05: Loss of coolant flow (only when reactor active)
        coolant_flow = self.memory_map.get("input_registers[6]", 0)
        reactor_active = self.memory_map.get("discrete_inputs[0]", False)
        low_coolant = reactor_active and coolant_flow < coolant_trip

        if low_coolant:
            self.logger.warning(
                f"ReactorSafetyPLC '{self.device_name}': "
                f"SIF-R05 LOW COOLANT FLOW - {coolant_flow}% < {coolant_trip}%"
            )
            safety_demand = True

        self.memory_map["discrete_inputs[5]"] = low_coolant

        # Manual SCRAM command
        manual_scram = self.memory_map.get("coils[0]", False)
        if manual_scram:
            self.logger.warning(
                f"ReactorSafetyPLC '{self.device_name}': Manual SCRAM commanded"
            )
            safety_demand = True

        # Check bypass
        if self.bypass_active and safety_demand:
            self.logger.critical(
                f"ReactorSafetyPLC '{self.device_name}': "
                f"SAFETY BYPASS ACTIVE - SCRAM condition ignored! DANGER!"
            )
            safety_demand = False

        return safety_demand

    async def _write_safety_outputs(self) -> None:
        """Write safety outputs to reactor physics."""
        # Update status registers
        self.memory_map["discrete_inputs[6]"] = self.safe_state_active
        self.memory_map["discrete_inputs[7]"] = not self.diagnostic_fault
        self.memory_map["input_registers[7]"] = self.demand_count
        self.memory_map["input_registers[8]"] = self.fault_count

        # If SCRAM demanded and not bypassed, trigger reactor SCRAM
        if self.safe_state_active and not self.bypass_active:
            self.reactor_physics.trigger_scram()

        # Handle SCRAM reset command
        scram_reset = self.memory_map.get("coils[1]", False)
        if scram_reset and self.safe_state_active:
            if await self.reset_from_safe_state():
                # Also reset reactor physics SCRAM
                if self.reactor_physics.reset_scram():
                    # Log SCRAM reset as audit event
                    await self.logger.log_audit(
                        message=f"Reactor SCRAM reset on '{self.device_name}'",
                        user="operator",
                        action="scram_reset",
                        data={
                            "device": self.device_name,
                            "demand_count": self.demand_count,
                        },
                    )

                    # Clear SCRAM alarm
                    if self.scram_alarm_raised:
                        await self.logger.log_alarm(
                            message=f"REACTOR SCRAM CLEARED on '{self.device_name}'",
                            priority=AlarmPriority.CRITICAL,
                            state=AlarmState.CLEARED,
                            device=self.device_name,
                            data={},
                        )
                        self.scram_alarm_raised = False

                    self.memory_map["coils[0]"] = False  # Clear manual SCRAM
                    self.memory_map["coils[1]"] = False  # Clear reset command
                else:
                    self.logger.warning(
                        f"ReactorSafetyPLC '{self.device_name}': "
                        f"Reactor SCRAM reset failed - conditions not safe"
                    )

    async def _run_diagnostics(self) -> None:
        """Run continuous self-diagnostics."""
        # Temperature channel discrepancy check
        temp_discrepancy = abs(self._temp_channel_a - self._temp_channel_b)
        max_temp_discrepancy = 5.0  # 5°C max

        if temp_discrepancy > max_temp_discrepancy:
            if not self.diagnostic_fault_alarm_raised:
                await self.logger.log_alarm(
                    message=f"Diagnostic fault on '{self.device_name}': Temperature channel discrepancy {temp_discrepancy:.1f}°C",
                    priority=AlarmPriority.HIGH,
                    state=AlarmState.ACTIVE,
                    device=self.device_name,
                    data={
                        "fault_type": "temp_channel_discrepancy",
                        "temp_a": self._temp_channel_a,
                        "temp_b": self._temp_channel_b,
                        "discrepancy": temp_discrepancy,
                    },
                )
                self.diagnostic_fault_alarm_raised = True

            self.logger.error(
                f"ReactorSafetyPLC '{self.device_name}': "
                f"Temperature channel discrepancy {temp_discrepancy:.1f}°C"
            )
            self.diagnostic_fault = True
            self.memory_map["input_registers[9]"] = 1
            return

        # Pressure channel discrepancy check
        press_discrepancy = abs(self._pressure_channel_a - self._pressure_channel_b)
        max_press_discrepancy = 3.0  # 3 bar max

        if press_discrepancy > max_press_discrepancy:
            if not self.diagnostic_fault_alarm_raised:
                await self.logger.log_alarm(
                    message=f"Diagnostic fault on '{self.device_name}': Pressure channel discrepancy {press_discrepancy:.1f} bar",
                    priority=AlarmPriority.HIGH,
                    state=AlarmState.ACTIVE,
                    device=self.device_name,
                    data={
                        "fault_type": "pressure_channel_discrepancy",
                        "pressure_a": self._pressure_channel_a,
                        "pressure_b": self._pressure_channel_b,
                        "discrepancy": press_discrepancy,
                    },
                )
                self.diagnostic_fault_alarm_raised = True

            self.logger.error(
                f"ReactorSafetyPLC '{self.device_name}': "
                f"Pressure channel discrepancy {press_discrepancy:.1f} bar"
            )
            self.diagnostic_fault = True
            self.memory_map["input_registers[9]"] = 2
            return

        # No faults - clear alarm if it was raised
        if self.diagnostic_fault_alarm_raised:
            await self.logger.log_alarm(
                message=f"Diagnostic fault cleared on '{self.device_name}'",
                priority=AlarmPriority.HIGH,
                state=AlarmState.CLEARED,
                device=self.device_name,
                data={},
            )
            self.diagnostic_fault_alarm_raised = False

        self.diagnostic_fault = False
        self.memory_map["input_registers[9]"] = 0

    async def _force_safe_state(self) -> None:
        """Force reactor to safe state (SCRAM)."""
        self.safe_state_active = True
        self.reactor_physics.trigger_scram()

        # Log SCRAM as CRITICAL alarm
        if not self.scram_alarm_raised:
            await self.logger.log_alarm(
                message=f"REACTOR SCRAM ACTIVATED on '{self.device_name}': Safe state forced",
                priority=AlarmPriority.CRITICAL,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={
                    "scram_reason": "safety_demand",
                    "demand_count": self.demand_count,
                },
            )
            self.scram_alarm_raised = True

        self.logger.critical(
            f"ReactorSafetyPLC '{self.device_name}': FORCING SAFE STATE - "
            f"Reactor SCRAM activated"
        )

    # ----------------------------------------------------------------
    # Convenience methods
    # ----------------------------------------------------------------

    async def trigger_scram(self, user: str = "operator") -> None:
        """
        Trigger a manual SCRAM (emergency shutdown).

        Args:
            user: User triggering the SCRAM
        """
        self.memory_map["coils[0]"] = True
        await self.data_store.write_memory(self.device_name, "coils[0]", True)

        # Log manual SCRAM as audit event
        await self.logger.log_audit(
            message=f"Manual SCRAM commanded on '{self.device_name}' by {user}",
            user=user,
            action="manual_scram",
            data={
                "device": self.device_name,
                "method": "trigger_scram",
            },
        )

        self.logger.warning(
            f"ReactorSafetyPLC '{self.device_name}': Manual SCRAM commanded"
        )

    async def get_safety_status(self) -> dict[str, Any]:
        """Get comprehensive reactor safety status."""
        base_status = await super().get_safety_status()

        return {
            **base_status,
            "temperature_trip_c": self._temp_trip_c,
            "pressure_trip_bar": self._pressure_trip_bar,
            "thaumic_trip_percent": self._thaumic_trip_percent,
            "containment_trip_percent": self._containment_trip_percent,
            "coolant_flow_trip_percent": self._coolant_flow_trip_percent,
            "temp_channel_a": self._temp_channel_a,
            "temp_channel_b": self._temp_channel_b,
            "pressure_channel_a": self._pressure_channel_a,
            "pressure_channel_b": self._pressure_channel_b,
        }

    async def get_reactor_safety_status(self) -> dict[str, Any]:
        """Get reactor-specific safety status. Alias for get_safety_status()."""
        status = await self.get_safety_status()
        status["sifs"] = {
            "SIF-R01": {
                "name": "High Core Temperature",
                "tripped": self.memory_map.get("discrete_inputs[1]", False),
            },
            "SIF-R02": {
                "name": "High Pressure",
                "tripped": self.memory_map.get("discrete_inputs[2]", False),
            },
            "SIF-R03": {
                "name": "Thaumic Instability",
                "tripped": self.memory_map.get("discrete_inputs[3]", False),
            },
            "SIF-R04": {
                "name": "Containment Breach",
                "tripped": self.memory_map.get("discrete_inputs[4]", False),
            },
            "SIF-R05": {
                "name": "Low Coolant Flow",
                "tripped": self.memory_map.get("discrete_inputs[5]", False),
            },
        }
        return status
