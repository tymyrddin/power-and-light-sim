# components/devices/control_zone/safety/turbine_safety_plc.py
"""
Turbine Safety Instrumented System (SIS) device class.

Models the safety PLC for the Hex Steam Turbine at UU Power & Light Co.
Independent of the main turbine PLC, monitors critical parameters and
triggers emergency shutdown when safety limits are exceeded.

Safety Instrumented Functions (SIFs):
- SIF-001: Overspeed protection (>110% rated speed)
- SIF-002: High vibration protection (>10 mils)
- SIF-003: High bearing temperature (>200°F)
- SIF-004: Low lube oil pressure (future)

Memory Map (Modbus):
-----------------------------------------------------------------
Discrete Inputs (Read-only booleans):
  0: Turbine running
  1: Overspeed condition (SIF-001 input)
  2: High vibration (SIF-002 input)
  3: High bearing temp (SIF-003 input)
  4: Safety system healthy
  5: Trip output active
  6: Bypass active (WARNING)
  7: Proof test due

Input Registers (Read-only 16-bit):
  0: Shaft speed channel A (RPM)
  1: Shaft speed channel B (RPM)
  2: Vibration channel A (mils * 10)
  3: Vibration channel B (mils * 10)
  4: Bearing temperature (degF)
  5: Diagnostic status
  6: Demand count
  7: Fault count

Coils (Read/write booleans):
  0: Manual trip command
  1: Trip reset command
  2: Bypass enable (REQUIRES AUTHORISATION)

Holding Registers (Read/write 16-bit):
  0: Overspeed trip setpoint (RPM)
  1: Vibration trip setpoint (mils * 10)
  2: Bearing temp trip setpoint (degF)
"""

from typing import Any

from components.devices.control_zone.safety.base_safety_controller import (
    BaseSafetyController,
    SafetyIntegrityLevel,
    VotingArchitecture,
)
from components.physics.turbine_physics import TurbinePhysics
from components.state.data_store import DataStore


class TurbineSafetyPLC(BaseSafetyController):
    """
    Safety Instrumented System for Hex Steam Turbine.

    Independent safety PLC that monitors turbine critical parameters
    and triggers emergency shutdown when safety limits are exceeded.

    Uses 2oo3 voting on speed sensors for overspeed protection.
    """

    # Modbus register definitions for adapter setup (reference only)
    DEFAULT_SETUP = {
        "discrete_inputs": {
            0: False,  # Turbine running
            1: False,  # Overspeed condition
            2: False,  # High vibration
            3: False,  # High bearing temp
            4: True,  # System healthy
            5: False,  # Trip output active
            6: False,  # Bypass active
            7: False,  # Proof test due
        },
        "input_registers": {
            0: 0,  # Speed channel A (RPM)
            1: 0,  # Speed channel B (RPM)
            2: 0,  # Vibration channel A (mils * 10)
            3: 0,  # Vibration channel B (mils * 10)
            4: 70,  # Bearing temperature (degF)
            5: 0,  # Diagnostic status
            6: 0,  # Demand count
            7: 0,  # Fault count
        },
        "coils": {
            0: False,  # Manual trip command
            1: False,  # Trip reset command
            2: False,  # Bypass enable
        },
        "holding_registers": {
            0: 3960,  # Overspeed trip setpoint (RPM) - 110% of 3600
            1: 100,  # Vibration trip setpoint (mils * 10)
            2: 200,  # Bearing temp trip setpoint (degF)
        },
    }

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        turbine_physics: TurbinePhysics,
        description: str = "Turbine Safety Instrumented System",
        scan_interval: float = 0.05,  # 50ms for safety-critical
    ):
        """
        Initialise turbine safety PLC.

        Args:
            device_name: Unique SIS identifier
            device_id: Controller address
            data_store: Reference to DataStore
            turbine_physics: TurbinePhysics engine for monitoring
            description: Controller description
            scan_interval: Safety logic scan time (50ms default)
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            sil_level=SafetyIntegrityLevel.SIL2,
            voting=VotingArchitecture.TWO_OUT_OF_THREE,
            description=description,
            scan_interval=scan_interval,
        )

        self.turbine_physics = turbine_physics

        # Safety trip setpoints (from turbine parameters)
        self._overspeed_trip_rpm = int(
            turbine_physics.params.rated_speed_rpm * 1.1
        )  # 110%
        self._vibration_trip_mils = turbine_physics.params.vibration_critical_mils
        self._bearing_temp_trip_f = 200  # °F

        # Simulated dual-channel inputs (for 2oo3 voting simulation)
        self._speed_channel_a = 0.0
        self._speed_channel_b = 0.0
        self._vibration_channel_a = 0.0
        self._vibration_channel_b = 0.0

        self.logger.info(
            f"TurbineSafetyPLC '{device_name}' created "
            f"(overspeed trip: {self._overspeed_trip_rpm} RPM)"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return device type."""
        return "turbine_safety_plc"

    def _supported_protocols(self) -> list[str]:
        """Supported protocols."""
        return ["modbus"]

    async def _initialise_memory_map(self) -> None:
        """Initialise Modbus memory map for safety system."""
        # Discrete inputs (read-only status bits)
        self.memory_map["discrete_inputs[0]"] = False  # Turbine running
        self.memory_map["discrete_inputs[1]"] = False  # Overspeed condition
        self.memory_map["discrete_inputs[2]"] = False  # High vibration
        self.memory_map["discrete_inputs[3]"] = False  # High bearing temp
        self.memory_map["discrete_inputs[4]"] = True  # System healthy
        self.memory_map["discrete_inputs[5]"] = False  # Trip output active
        self.memory_map["discrete_inputs[6]"] = False  # Bypass active
        self.memory_map["discrete_inputs[7]"] = False  # Proof test due

        # Input registers (read-only telemetry)
        self.memory_map["input_registers[0]"] = 0  # Speed channel A
        self.memory_map["input_registers[1]"] = 0  # Speed channel B
        self.memory_map["input_registers[2]"] = 0  # Vibration channel A
        self.memory_map["input_registers[3]"] = 0  # Vibration channel B
        self.memory_map["input_registers[4]"] = 70  # Bearing temp
        self.memory_map["input_registers[5]"] = 0  # Diagnostic status
        self.memory_map["input_registers[6]"] = 0  # Demand count
        self.memory_map["input_registers[7]"] = 0  # Fault count

        # Coils (read/write control bits)
        self.memory_map["coils[0]"] = False  # Manual trip
        self.memory_map["coils[1]"] = False  # Trip reset
        self.memory_map["coils[2]"] = False  # Bypass enable

        # Holding registers (read/write setpoints)
        self.memory_map["holding_registers[0]"] = self._overspeed_trip_rpm
        self.memory_map["holding_registers[1]"] = int(self._vibration_trip_mils * 10)
        self.memory_map["holding_registers[2]"] = self._bearing_temp_trip_f

        self.logger.debug(
            f"TurbineSafetyPLC '{self.device_name}' memory map initialised"
        )

    # ----------------------------------------------------------------
    # BaseSafetyController implementation
    # ----------------------------------------------------------------

    async def _read_safety_inputs(self) -> None:
        """
        Read safety-critical inputs from turbine physics.

        Simulates dual-channel redundant sensors with minor discrepancy
        for realistic behaviour.
        """
        turbine_telem = self.turbine_physics.get_telemetry()

        # Get base values
        actual_speed = turbine_telem.get("shaft_speed_rpm", 0)
        actual_vibration = turbine_telem.get("vibration_mils", 0)
        actual_bearing_temp = turbine_telem.get(
            "bearing_temperature_c", 21
        )  # 21°C = 70°F

        # Simulate dual-channel sensors with small discrepancy (0.5%)
        import random

        self._speed_channel_a = actual_speed * (1.0 + random.uniform(-0.005, 0.005))
        self._speed_channel_b = actual_speed * (1.0 + random.uniform(-0.005, 0.005))
        self._vibration_channel_a = actual_vibration * (
            1.0 + random.uniform(-0.01, 0.01)
        )
        self._vibration_channel_b = actual_vibration * (
            1.0 + random.uniform(-0.01, 0.01)
        )

        # Update input registers
        self.memory_map["input_registers[0]"] = int(self._speed_channel_a)
        self.memory_map["input_registers[1]"] = int(self._speed_channel_b)
        self.memory_map["input_registers[2]"] = int(self._vibration_channel_a * 10)
        self.memory_map["input_registers[3]"] = int(self._vibration_channel_b * 10)
        self.memory_map["input_registers[4]"] = int(actual_bearing_temp)

        # Update discrete input status
        self.memory_map["discrete_inputs[0]"] = turbine_telem.get(
            "turbine_running", False
        )

    async def _execute_safety_logic(self) -> bool:
        """
        Execute safety instrumented functions.

        Returns:
            True if safety action demanded (trip required)
        """
        # Read current trip setpoints from holding registers
        overspeed_trip = self.memory_map.get(
            "holding_registers[0]", self._overspeed_trip_rpm
        )
        vibration_trip = (
            self.memory_map.get("holding_registers[1]", 100) / 10.0
        )  # Convert from *10
        bearing_temp_trip = self.memory_map.get("holding_registers[2]", 200)

        safety_demand = False

        # SIF-001: Overspeed protection (2oo2 voting - both channels must agree)
        speed_a_trip = self._speed_channel_a > overspeed_trip
        speed_b_trip = self._speed_channel_b > overspeed_trip
        overspeed_trip_condition = speed_a_trip and speed_b_trip

        if overspeed_trip_condition:
            self.logger.warning(
                f"TurbineSafetyPLC '{self.device_name}': "
                f"SIF-001 OVERSPEED - A:{self._speed_channel_a:.0f} "
                f"B:{self._speed_channel_b:.0f} > {overspeed_trip} RPM"
            )
            safety_demand = True

        self.memory_map["discrete_inputs[1]"] = overspeed_trip_condition

        # SIF-002: High vibration protection (2oo2 voting)
        vib_a_trip = self._vibration_channel_a > vibration_trip
        vib_b_trip = self._vibration_channel_b > vibration_trip
        vibration_trip_condition = vib_a_trip and vib_b_trip

        if vibration_trip_condition:
            self.logger.warning(
                f"TurbineSafetyPLC '{self.device_name}': "
                f"SIF-002 HIGH VIBRATION - A:{self._vibration_channel_a:.1f} "
                f"B:{self._vibration_channel_b:.1f} > {vibration_trip} mils"
            )
            safety_demand = True

        self.memory_map["discrete_inputs[2]"] = vibration_trip_condition

        # SIF-003: High bearing temperature (single channel)
        bearing_temp = self.memory_map.get("input_registers[4]", 70)
        bearing_temp_trip_condition = bearing_temp > bearing_temp_trip

        if bearing_temp_trip_condition:
            self.logger.warning(
                f"TurbineSafetyPLC '{self.device_name}': "
                f"SIF-003 HIGH BEARING TEMP - {bearing_temp}°F > {bearing_temp_trip}°F"
            )
            safety_demand = True

        self.memory_map["discrete_inputs[3]"] = bearing_temp_trip_condition

        # Check manual trip command
        manual_trip = self.memory_map.get("coils[0]", False)
        if manual_trip:
            self.logger.warning(
                f"TurbineSafetyPLC '{self.device_name}': Manual trip commanded"
            )
            safety_demand = True

        # Check bypass status
        if self.bypass_active and safety_demand:
            self.logger.critical(
                f"TurbineSafetyPLC '{self.device_name}': "
                f"SAFETY BYPASS ACTIVE - Trip condition ignored!"
            )
            safety_demand = False

        return safety_demand

    async def _write_safety_outputs(self) -> None:
        """Write safety outputs to turbine physics."""
        # Update status registers
        self.memory_map["discrete_inputs[4]"] = not self.diagnostic_fault
        self.memory_map["discrete_inputs[5]"] = self.safe_state_active
        self.memory_map["discrete_inputs[6]"] = self.bypass_active
        self.memory_map["discrete_inputs[7]"] = self.is_proof_test_due()
        self.memory_map["input_registers[6]"] = self.demand_count
        self.memory_map["input_registers[7]"] = self.fault_count

        # If safety demanded and not bypassed, trigger turbine trip
        if self.safe_state_active and not self.bypass_active:
            self.turbine_physics.trigger_emergency_trip()

        # Handle trip reset command
        trip_reset = self.memory_map.get("coils[1]", False)
        if trip_reset and self.safe_state_active:
            if await self.reset_from_safe_state():
                self.memory_map["coils[0]"] = False  # Clear manual trip
                self.memory_map["coils[1]"] = False  # Clear reset command

    async def _run_diagnostics(self) -> None:
        """Run continuous self-diagnostics."""
        # Check channel discrepancy
        speed_discrepancy = abs(self._speed_channel_a - self._speed_channel_b)
        max_discrepancy = self._overspeed_trip_rpm * 0.02  # 2% max

        if speed_discrepancy > max_discrepancy:
            self.logger.error(
                f"TurbineSafetyPLC '{self.device_name}': "
                f"Speed channel discrepancy {speed_discrepancy:.0f} RPM"
            )
            self.diagnostic_fault = True
            self.memory_map["input_registers[5]"] = 1  # Fault code
            return

        # Vibration channel check
        vib_discrepancy = abs(self._vibration_channel_a - self._vibration_channel_b)
        if vib_discrepancy > 1.0:  # 1 mil max discrepancy
            self.logger.error(
                f"TurbineSafetyPLC '{self.device_name}': "
                f"Vibration channel discrepancy {vib_discrepancy:.1f} mils"
            )
            self.diagnostic_fault = True
            self.memory_map["input_registers[5]"] = 2  # Fault code
            return

        # No faults detected
        self.diagnostic_fault = False
        self.memory_map["input_registers[5]"] = 0

    async def _force_safe_state(self) -> None:
        """Force turbine to safe state (trip)."""
        self.safe_state_active = True
        self.turbine_physics.trigger_emergency_trip()
        self.logger.critical(
            f"TurbineSafetyPLC '{self.device_name}': FORCING SAFE STATE - "
            f"Turbine emergency trip activated"
        )

    # ----------------------------------------------------------------
    # Convenience methods
    # ----------------------------------------------------------------

    async def manual_trip(self) -> None:
        """Trigger a manual emergency trip."""
        self.memory_map["coils[0]"] = True
        await self.data_store.write_memory(self.device_name, "coils[0]", True)
        self.logger.warning(
            f"TurbineSafetyPLC '{self.device_name}': Manual trip commanded"
        )

    async def get_safety_status(self) -> dict[str, Any]:
        """Get comprehensive safety system status."""
        base_status = await super().get_safety_status()

        return {
            **base_status,
            "overspeed_trip_rpm": self._overspeed_trip_rpm,
            "vibration_trip_mils": self._vibration_trip_mils,
            "bearing_temp_trip_f": self._bearing_temp_trip_f,
            "speed_channel_a": self._speed_channel_a,
            "speed_channel_b": self._speed_channel_b,
            "vibration_channel_a": self._vibration_channel_a,
            "vibration_channel_b": self._vibration_channel_b,
        }

    async def get_turbine_safety_status(self) -> dict[str, Any]:
        """Get turbine-specific safety status. Alias for get_safety_status()."""
        status = await self.get_safety_status()
        status["sifs"] = {
            "SIF-001": {
                "name": "Overspeed Protection",
                "tripped": self.memory_map.get("discrete_inputs[1]", False),
            },
            "SIF-002": {
                "name": "High Vibration Protection",
                "tripped": self.memory_map.get("discrete_inputs[2]", False),
            },
            "SIF-003": {
                "name": "High Bearing Temperature",
                "tripped": self.memory_map.get("discrete_inputs[3]", False),
            },
        }
        return status
