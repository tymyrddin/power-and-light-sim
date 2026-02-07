# components/devices/control_zone/plc/vendor_specific/turbine_plc.py
"""
Turbine PLC device class.

Bridges TurbinePhysics and GridPhysics engines with protocol memory maps (Modbus-style).
Implements PLC scan cycle logic, reading from physics and exposing
telemetry via holding registers and coils.

Memory Map (Modbus-style):
-----------------------------------------------------------------
Discrete Inputs (Read-only booleans):
  0: Turbine running (speed > 100 RPM)
  1: Governor online
  2: Trip active
  3: Overspeed condition (>110% rated)
  4: Under-frequency trip (grid)
  5: Over-frequency trip (grid)

Input Registers (Read-only 16-bit):
  0: Shaft speed (RPM)
  1: Power output (MW * 10)
  2: Steam pressure (PSI)
  3: Steam temperature (°C)
  4: Bearing temperature (°C)
  5: Vibration (mils * 10)
  6: Overspeed time (seconds)
  7: Damage level (percent)
  8: Grid frequency (Hz * 100)
  9: Grid voltage (pu * 1000)

Coils (Read/write booleans):
  0: Governor enable
  1: Emergency trip
  2: Trip reset

Holding Registers (Read/write 16-bit):
  0: Speed setpoint (RPM)
  1: Speed setpoint (upper word for >65535)

Default Modbus Setup for pymodbus_3114 adapter integration.
"""

from typing import Any

from components.devices.control_zone.plc.generic.base_plc import BasePLC
from components.physics.grid_physics import GridPhysics
from components.physics.turbine_physics import TurbinePhysics
from components.security.logging_system import AlarmPriority, AlarmState


class TurbinePLC(BasePLC):
    """
    PLC for steam turbine control and monitoring.

    Reads from:
    - TurbinePhysics: Shaft speed, temperatures, vibration, power output
    - GridPhysics: Frequency, voltage, trip status

    Controls:
    - Speed setpoint
    - Governor enable/disable
    - Emergency trip

    Exposes Modbus memory map for SCADA access.
    """

    # Modbus register definitions (matches actual memory map implementation)
    DEFAULT_SETUP = {
        "coils": {
            0: False,  # Governor enable
            1: False,  # Emergency trip
            2: False,  # Trip reset
        },
        "discrete_inputs": {
            0: False,  # Turbine running
            1: False,  # Governor online
            2: False,  # Trip active
            3: False,  # Overspeed condition
            4: False,  # Under-frequency trip
            5: False,  # Over-frequency trip
        },
        "input_registers": {
            0: 0,  # Shaft speed (RPM)
            1: 0,  # Power output (MW * 10)
            2: 0,  # Steam pressure (PSI)
            3: 0,  # Steam temperature (°C)
            4: 0,  # Bearing temperature (°C)
            5: 0,  # Vibration (mils * 10)
            6: 0,  # Overspeed time (seconds)
            7: 0,  # Damage level (percent)
            8: 0,  # Grid frequency (Hz * 100)
            9: 0,  # Grid voltage (pu * 1000)
        },
        "holding_registers": {
            0: 0,  # Speed setpoint (lower 16 bits)
            1: 0,  # Speed setpoint (upper bits, for >65535)
        },
    }

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: Any,
        turbine_physics: TurbinePhysics,
        grid_physics: GridPhysics | None = None,
        description: str = "Steam turbine PLC",
        scan_interval: float = 0.1,
    ):
        """
        Initialise turbine PLC.

        Args:
            device_name: Unique PLC identifier
            device_id: Modbus unit ID
            data_store: Reference to DataStore
            turbine_physics: TurbinePhysics engine instance
            grid_physics: GridPhysics engine instance (optional)
            description: PLC description
            scan_interval: Scan cycle time in seconds
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
        )

        # Physics engine references
        self.turbine_physics = turbine_physics
        self.grid_physics = grid_physics

        # Internal state
        self._last_speed_setpoint = 0.0
        self._last_governor_enable = False
        self._trip_reset_edge = False

        self.logger.info(
            f"TurbinePLC '{device_name}' initialised "
            f"(turbine: {turbine_physics is not None}, "
            f"grid: {grid_physics is not None})"
        )

    # ----------------------------------------------------------------
    # BaseDevice/BasePLC implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return device type."""
        return "turbine_plc"

    def _supported_protocols(self) -> list[str]:
        """Supported protocols - Allen-Bradley uses EtherNet/IP and Modbus."""
        return ["modbus", "ethernet_ip"]

    async def _initialise_memory_map(self) -> None:
        """Initialize Modbus register layout."""
        # Coils (read/write control bits)
        self.memory_map["coils[0]"] = False  # Governor enable
        self.memory_map["coils[1]"] = False  # Emergency trip
        self.memory_map["coils[2]"] = False  # Trip reset

        # Discrete inputs (read-only status bits)
        self.memory_map["discrete_inputs[0]"] = False  # Turbine running
        self.memory_map["discrete_inputs[1]"] = False  # Governor online
        self.memory_map["discrete_inputs[2]"] = False  # Trip active
        self.memory_map["discrete_inputs[3]"] = False  # Overspeed condition
        self.memory_map["discrete_inputs[4]"] = False  # Under-frequency trip
        self.memory_map["discrete_inputs[5]"] = False  # Over-frequency trip
        self.memory_map["discrete_inputs[6]"] = False  # High vibration alarm
        self.memory_map["discrete_inputs[7]"] = False  # High bearing temp alarm

        # Input registers (read-only telemetry)
        self.memory_map["input_registers[0]"] = 0  # Shaft speed (RPM)
        self.memory_map["input_registers[1]"] = 0  # Power output (MW * 10)
        self.memory_map["input_registers[2]"] = 0  # Steam pressure (PSI)
        self.memory_map["input_registers[3]"] = 0  # Steam temperature (°C)
        self.memory_map["input_registers[4]"] = 0  # Bearing temperature (°C)
        self.memory_map["input_registers[5]"] = 0  # Vibration (mils * 10)
        self.memory_map["input_registers[6]"] = 0  # Overspeed time (seconds)
        self.memory_map["input_registers[7]"] = 0  # Damage level (percent)
        self.memory_map["input_registers[8]"] = 5000  # Grid frequency (Hz * 100)
        self.memory_map["input_registers[9]"] = 1000  # Grid voltage (pu * 1000)

        # Holding registers (read/write setpoints)
        self.memory_map["holding_registers[0]"] = 0  # Speed setpoint (lower 16 bits)
        self.memory_map["holding_registers[1]"] = 0  # Speed setpoint (upper word)

        self.logger.debug(f"TurbinePLC '{self.device_name}' memory map initialised")

    # ----------------------------------------------------------------
    # PLC Scan Cycle
    # ----------------------------------------------------------------

    async def _read_inputs(self) -> None:
        """
        Read inputs from physics engines.

        Updates discrete inputs and input registers from:
        - TurbinePhysics state
        - GridPhysics state (if available)
        """
        # Get turbine telemetry
        turbine_telem = self.turbine_physics.get_telemetry()

        # Update discrete inputs (status bits)
        self.memory_map["discrete_inputs[0]"] = turbine_telem.get(
            "turbine_running", False
        )
        self.memory_map["discrete_inputs[1]"] = turbine_telem.get(
            "governor_online", False
        )
        self.memory_map["discrete_inputs[2]"] = turbine_telem.get("trip_active", False)

        # Overspeed condition (>110% rated)
        shaft_speed = turbine_telem.get("shaft_speed_rpm", 0)
        rated_speed = self.turbine_physics.params.rated_speed_rpm
        self.memory_map["discrete_inputs[3]"] = shaft_speed > (rated_speed * 1.1)

        # Alarm conditions
        self.memory_map["discrete_inputs[6]"] = (
            turbine_telem.get("vibration_mils", 0) > 8.0
        )
        self.memory_map["discrete_inputs[7]"] = (
            turbine_telem.get("bearing_temperature_c", 0) > 82
        )  # 82°C = 180°F

        # Update input registers (analog telemetry)
        self.memory_map["input_registers[0]"] = int(
            turbine_telem.get("shaft_speed_rpm", 0)
        )
        self.memory_map["input_registers[1]"] = int(
            turbine_telem.get("power_output_mw", 0) * 10
        )
        self.memory_map["input_registers[2]"] = int(
            turbine_telem.get("steam_pressure_psi", 0)
        )
        self.memory_map["input_registers[3]"] = int(
            turbine_telem.get("steam_temperature_c", 0)
        )
        self.memory_map["input_registers[4]"] = int(
            turbine_telem.get("bearing_temperature_c", 0)
        )
        self.memory_map["input_registers[5]"] = int(
            turbine_telem.get("vibration_mils", 0) * 10
        )
        self.memory_map["input_registers[6]"] = int(
            turbine_telem.get("overspeed_time_sec", 0)
        )
        self.memory_map["input_registers[7]"] = int(
            turbine_telem.get("damage_percent", 0)
        )

        # Get grid telemetry (if available)
        if self.grid_physics:
            grid_telem = self.grid_physics.get_telemetry()

            # Grid trip conditions
            self.memory_map["discrete_inputs[4]"] = grid_telem.get(
                "under_frequency_trip", False
            )
            self.memory_map["discrete_inputs[5]"] = grid_telem.get(
                "over_frequency_trip", False
            )

            # Grid measurements (scaled for 16-bit registers)
            # Frequency: Hz * 100 (e.g., 50.00 Hz -> 5000)
            freq_hz = grid_telem.get("frequency_hz", 50.0)
            self.memory_map["input_registers[8]"] = int(freq_hz * 100)

            # Voltage: pu * 1000 (e.g., 1.000 pu -> 1000)
            voltage_pu = grid_telem.get("voltage_pu", 1.0)
            self.memory_map["input_registers[9]"] = int(voltage_pu * 1000)
        else:
            # No grid physics - clear grid-related inputs
            self.memory_map["discrete_inputs[4]"] = False
            self.memory_map["discrete_inputs[5]"] = False
            self.memory_map["input_registers[8]"] = 5000  # Nominal 50.00 Hz
            self.memory_map["input_registers[9]"] = 1000  # Nominal 1.000 pu

    async def _execute_logic(self) -> None:
        """
        Execute PLC control logic.

        Processes:
        - Speed setpoint changes
        - Governor enable/disable
        - Emergency trip and reset
        """
        # Read setpoint from holding registers (32-bit value split across two registers)
        speed_setpoint_low = self.memory_map.get("holding_registers[0]", 0)
        speed_setpoint_high = self.memory_map.get("holding_registers[1]", 0)
        speed_setpoint = (speed_setpoint_high << 16) | speed_setpoint_low

        # Clamp to reasonable range (0-10000 RPM)
        speed_setpoint = max(0, min(10000, speed_setpoint))

        # Read control coils
        governor_enable = self.memory_map.get("coils[0]", False)
        trip_reset = self.memory_map.get("coils[2]", False)

        # Detect trip reset edge (rising edge)
        if trip_reset and not self._trip_reset_edge:
            await self.logger.log_audit(
                message=f"TurbinePLC '{self.device_name}': Trip reset commanded via coil",
                user="operator",
                action="turbine_trip_reset_detected",
                result="COMMANDED",
                data={
                    "device": self.device_name,
                    "turbine_speed_rpm": self.turbine_physics.state.shaft_speed_rpm,
                    "power_output_mw": self.turbine_physics.state.power_output_mw,
                },
            )
            self._trip_reset_edge = True
        elif not trip_reset:
            self._trip_reset_edge = False

        # Store for output phase
        self._last_speed_setpoint = float(speed_setpoint)
        self._last_governor_enable = governor_enable

    async def _write_outputs(self) -> None:
        """
        Write outputs to physics engine.

        Commands:
        - Speed setpoint to turbine governor
        - Governor enable/disable
        - Emergency trip/reset
        """
        # Update speed setpoint
        self.turbine_physics.set_speed_setpoint(self._last_speed_setpoint)

        # Update governor enable
        self.turbine_physics.set_governor_enabled(self._last_governor_enable)

        # Handle emergency trip
        if self.memory_map.get("coils[1]", False):  # Emergency trip commanded
            self.turbine_physics.trigger_emergency_trip()
            await self.logger.log_alarm(
                message=f"TurbinePLC '{self.device_name}': Emergency trip activated",
                priority=AlarmPriority.CRITICAL,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={
                    "device": self.device_name,
                    "event": "emergency_trip_activated",
                    "turbine_speed_rpm": self.turbine_physics.state.shaft_speed_rpm,
                    "power_output_mw": self.turbine_physics.state.power_output_mw,
                },
            )

        # Handle trip reset
        if self.memory_map.get("coils[2]", False) and self._trip_reset_edge:
            self.turbine_physics.reset_trip()
            await self.logger.log_audit(
                message=f"TurbinePLC '{self.device_name}': Trip reset executed",
                user="system",
                action="turbine_trip_reset_executed",
                result="SUCCESS",
                data={
                    "device": self.device_name,
                    "turbine_speed_rpm": self.turbine_physics.state.shaft_speed_rpm,
                    "power_output_mw": self.turbine_physics.state.power_output_mw,
                },
            )
            # Auto-clear trip reset coil after execution
            self.memory_map["coils[2]"] = False

    # ----------------------------------------------------------------
    # Additional functionality
    # ----------------------------------------------------------------

    async def set_speed_command(self, rpm: float) -> None:
        """
        Convenience method to set speed setpoint programmatically.

        Args:
            rpm: Target speed in RPM
        """
        rpm_int = int(max(0, min(10000, rpm)))

        # Split into two 16-bit registers
        self.memory_map["holding_registers[0]"] = rpm_int & 0xFFFF  # Lower 16 bits
        self.memory_map["holding_registers[1]"] = (
            rpm_int >> 16
        ) & 0xFFFF  # Upper 16 bits

        await self.logger.log_audit(
            message=f"TurbinePLC '{self.device_name}': Speed setpoint changed to {rpm_int} RPM",
            user="operator",
            action="turbine_speed_setpoint_change",
            result="SUCCESS",
            data={
                "device": self.device_name,
                "new_setpoint_rpm": rpm_int,
                "original_value": rpm,
            },
        )

        self.logger.info(
            f"TurbinePLC '{self.device_name}': Speed setpoint set to {rpm_int} RPM"
        )

    async def enable_governor(self, enable: bool = True) -> None:
        """
        Enable or disable governor control.

        Args:
            enable: True to enable governor, False to disable
        """
        self.memory_map["coils[0]"] = enable
        self.logger.info(
            f"TurbinePLC '{self.device_name}': "
            f"Governor {'enabled' if enable else 'disabled'}"
        )

    async def trigger_trip(self) -> None:
        """Trigger emergency trip."""
        self.memory_map["coils[1]"] = True
        await self.logger.log_alarm(
            message=f"TurbinePLC '{self.device_name}': Emergency trip triggered",
            priority=AlarmPriority.CRITICAL,
            state=AlarmState.ACTIVE,
            device=self.device_name,
            data={
                "device": self.device_name,
                "event": "emergency_trip_triggered",
                "turbine_speed_rpm": self.turbine_physics.state.shaft_speed_rpm,
                "power_output_mw": self.turbine_physics.state.power_output_mw,
            },
        )

    async def reset_trip_command(self) -> None:
        """Reset trip condition."""
        self.memory_map["coils[2]"] = True
        await self.logger.log_audit(
            message=f"TurbinePLC '{self.device_name}': Trip reset commanded",
            user="operator",
            action="turbine_trip_reset",
            result="COMMANDED",
            data={
                "device": self.device_name,
                "turbine_speed_rpm": self.turbine_physics.state.shaft_speed_rpm,
                "power_output_mw": self.turbine_physics.state.power_output_mw,
            },
        )

    async def get_turbine_status(self) -> dict[str, Any]:
        """
        Get comprehensive turbine status.

        Returns:
            Dictionary with turbine state and telemetry
        """
        plc_status = await self.get_plc_status()
        turbine_telem = self.turbine_physics.get_telemetry()

        status = {
            **plc_status,
            "turbine": turbine_telem,
            "setpoint_rpm": self._last_speed_setpoint,
            "governor_enabled": self._last_governor_enable,
        }

        if self.grid_physics:
            status["grid"] = self.grid_physics.get_telemetry()

        return status
