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
  100: Shaft speed (RPM)
  101: Power output (MW)
  102: Steam pressure (PSI)
  103: Steam temperature (°F)
  104: Bearing temperature (°F)
  105: Vibration (mils)
  106: Overspeed time (seconds)
  107: Damage level (percent)
  108: Grid frequency (Hz * 100)
  109: Grid voltage (pu * 1000)

Coils (Read/write booleans):
  0: Governor enable
  1: Emergency trip
  2: Trip reset

Holding Registers (Read/write 16-bit):
  200: Speed setpoint (RPM)
  201: Speed setpoint (upper byte for >65535)

Default Modbus Setup for pymodbus_3114 adapter integration.
"""

import logging
from typing import Any

from components.devices.control_zone.plc.generic.base_plc import BasePLC
from components.physics.grid_physics import GridPhysics
from components.physics.turbine_physics import TurbinePhysics

logger = logging.getLogger(__name__)


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

    # Modbus register definitions for adapter setup
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
            100: 0,  # Shaft speed
            101: 0,  # Power output
            102: 0,  # Steam pressure
            103: 0,  # Steam temperature
            104: 0,  # Bearing temperature
            105: 0,  # Vibration
            106: 0,  # Overspeed time
            107: 0,  # Damage level
            108: 0,  # Grid frequency
            109: 0,  # Grid voltage
        },
        "holding_registers": {
            200: 0,  # Speed setpoint (lower 16 bits)
            201: 0,  # Speed setpoint (upper bits, for >65535)
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

        logger.info(
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
        """Supported protocols."""
        return ["modbus"]

    async def _initialize_registers(self) -> None:
        """Initialize Modbus register layout."""
        # Coils (outputs)
        self.coils = {
            0: False,  # Governor enable
            1: False,  # Emergency trip
            2: False,  # Trip reset
        }

        # Discrete inputs (status bits)
        self.discrete_inputs = {
            0: False,  # Turbine running
            1: False,  # Governor online
            2: False,  # Trip active
            3: False,  # Overspeed condition
            4: False,  # Under-frequency trip
            5: False,  # Over-frequency trip
        }

        # Input registers (telemetry)
        self.input_registers = {
            100: 0,  # Shaft speed (RPM)
            101: 0,  # Power output (MW)
            102: 0,  # Steam pressure (PSI)
            103: 0,  # Steam temperature (°F)
            104: 0,  # Bearing temperature (°F)
            105: 0,  # Vibration (mils)
            106: 0,  # Overspeed time (seconds)
            107: 0,  # Damage level (percent)
            108: 0,  # Grid frequency (Hz * 100)
            109: 0,  # Grid voltage (pu * 1000)
        }

        # Holding registers (setpoints)
        self.holding_registers = {
            200: 0,  # Speed setpoint (lower 16 bits)
            201: 0,  # Speed setpoint (upper bits)
        }

        logger.debug(f"TurbinePLC '{self.device_name}' registers initialised")

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
        self.discrete_inputs[0] = turbine_telem.get("turbine_running", False)
        self.discrete_inputs[1] = turbine_telem.get("governor_online", False)
        self.discrete_inputs[2] = turbine_telem.get("trip_active", False)

        # Overspeed condition (>110% rated)
        shaft_speed = turbine_telem.get("shaft_speed_rpm", 0)
        rated_speed = self.turbine_physics.params.rated_speed_rpm
        self.discrete_inputs[3] = shaft_speed > (rated_speed * 1.1)

        # Update input registers (analog telemetry)
        self.input_registers[100] = int(turbine_telem.get("shaft_speed_rpm", 0))
        self.input_registers[101] = int(turbine_telem.get("power_output_mw", 0))
        self.input_registers[102] = int(turbine_telem.get("steam_pressure_psi", 0))
        self.input_registers[103] = int(turbine_telem.get("steam_temperature_f", 0))
        self.input_registers[104] = int(turbine_telem.get("bearing_temperature_f", 0))
        self.input_registers[105] = int(turbine_telem.get("vibration_mils", 0))
        self.input_registers[106] = int(turbine_telem.get("overspeed_time_sec", 0))
        self.input_registers[107] = int(turbine_telem.get("damage_percent", 0))

        # Get grid telemetry (if available)
        if self.grid_physics:
            grid_telem = self.grid_physics.get_telemetry()

            # Grid trip conditions
            self.discrete_inputs[4] = grid_telem.get("under_frequency_trip", False)
            self.discrete_inputs[5] = grid_telem.get("over_frequency_trip", False)

            # Grid measurements (scaled for 16-bit registers)
            # Frequency: Hz * 100 (e.g., 50.00 Hz -> 5000)
            freq_hz = grid_telem.get("frequency_hz", 50.0)
            self.input_registers[108] = int(freq_hz * 100)

            # Voltage: pu * 1000 (e.g., 1.000 pu -> 1000)
            voltage_pu = grid_telem.get("voltage_pu", 1.0)
            self.input_registers[109] = int(voltage_pu * 1000)
        else:
            # No grid physics - clear grid-related inputs
            self.discrete_inputs[4] = False
            self.discrete_inputs[5] = False
            self.input_registers[108] = 5000  # Nominal 50.00 Hz
            self.input_registers[109] = 1000  # Nominal 1.000 pu

    async def _execute_logic(self) -> None:
        """
        Execute PLC control logic.

        Processes:
        - Speed setpoint changes
        - Governor enable/disable
        - Emergency trip and reset
        """
        # Read setpoint from holding registers (32-bit value split across two registers)
        speed_setpoint_low = self.holding_registers[200]
        speed_setpoint_high = self.holding_registers[201]
        speed_setpoint = (speed_setpoint_high << 16) | speed_setpoint_low

        # Clamp to reasonable range (0-10000 RPM)
        speed_setpoint = max(0, min(10000, speed_setpoint))

        # Read control coils
        governor_enable = self.coils[0]
        emergency_trip = self.coils[1]
        trip_reset = self.coils[2]

        # Detect trip reset edge (rising edge)
        if trip_reset and not self._trip_reset_edge:
            logger.info(f"TurbinePLC '{self.device_name}': Trip reset commanded")
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
        if self.coils[1]:  # Emergency trip commanded
            self.turbine_physics.trigger_emergency_trip()
            logger.warning(f"TurbinePLC '{self.device_name}': Emergency trip activated")

        # Handle trip reset
        if self.coils[2] and self._trip_reset_edge:
            self.turbine_physics.reset_trip()
            logger.info(f"TurbinePLC '{self.device_name}': Trip reset")
            # Auto-clear trip reset coil after execution
            self.coils[2] = False

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
        self.holding_registers[200] = rpm_int & 0xFFFF  # Lower 16 bits
        self.holding_registers[201] = (rpm_int >> 16) & 0xFFFF  # Upper 16 bits

        logger.info(
            f"TurbinePLC '{self.device_name}': Speed setpoint set to {rpm_int} RPM"
        )

    async def enable_governor(self, enable: bool = True) -> None:
        """
        Enable or disable governor control.

        Args:
            enable: True to enable governor, False to disable
        """
        self.coils[0] = enable
        logger.info(
            f"TurbinePLC '{self.device_name}': "
            f"Governor {'enabled' if enable else 'disabled'}"
        )

    async def trigger_trip(self) -> None:
        """Trigger emergency trip."""
        self.coils[1] = True
        logger.warning(f"TurbinePLC '{self.device_name}': Emergency trip triggered")

    async def reset_trip_command(self) -> None:
        """Reset trip condition."""
        self.coils[2] = True
        logger.info(f"TurbinePLC '{self.device_name}': Trip reset commanded")

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
