# components/devices/control_zone/plc/vendor_specific/hvac_plc.py
"""
Library HVAC PLC device class.

Models the Schneider Modicon (1987) with Modbus gateway (2005) controlling
the Library Environmental Management System at UU Power & Light Co.

The Library requires precise environmental control to maintain temperature,
humidity, and magical stability. The Librarian (an orangutan) takes book
preservation very seriously - modifications require formal approvals.

Memory Map (Modbus):
-----------------------------------------------------------------
Discrete Inputs (Read-only booleans):
  0: Fan running
  1: Heating active
  2: Cooling active
  3: Temperature alarm (out of range)
  4: Humidity alarm (out of range)
  5: L-space warning (stability < 50%)
  6: L-space critical (stability < 30%)
  7: System enabled

Input Registers (Read-only 16-bit):
  0: Zone temperature (degC * 10)
  1: Zone humidity (per cent * 10)
  2: Supply air temperature (degC * 10)
  3: Duct pressure (Pa)
  4: L-space stability (per cent)
  5: Fan speed (per cent)
  6: Heating valve (per cent)
  7: Cooling valve (per cent)
  8: Damper position (per cent)
  9: Energy consumption (kW * 10)

Coils (Read/write booleans):
  0: System enable command
  1: L-space dampener enable

Holding Registers (Read/write 16-bit):
  0: Temperature setpoint (degC * 10)
  1: Humidity setpoint (per cent * 10)
  2: Fan speed command (per cent)
  3: Operating mode (0=off, 1=heat, 2=cool, 3=auto)
  4: Damper position command (per cent)
"""

from typing import Any

from components.devices.control_zone.plc.generic.base_plc import BasePLC
from components.physics.hvac_physics import HVACPhysics
from components.state.data_store import DataStore


class HVACPLC(BasePLC):
    """
    PLC for Library HVAC control and monitoring.

    Models a Schneider Modicon (1987) with Modbus gateway (2005):
    - Legacy Modicon with modern Modbus TCP interface
    - Controls temperature, humidity, and L-space stability

    Reads from:
    - HVACPhysics: Temperature, humidity, fan/valve states, L-space stability

    Controls:
    - Temperature setpoint
    - Humidity setpoint
    - Fan speed
    - Operating mode
    - Outside air damper
    - L-space dampener
    """

    # Operating modes (matches HVACPhysics)
    MODE_OFF = 0
    MODE_HEAT = 1
    MODE_COOL = 2
    MODE_AUTO = 3

    # Modbus register definitions for adapter setup
    DEFAULT_SETUP = {
        "coils": {
            0: False,  # System enable command
            1: True,   # L-space dampener enable
        },
        "discrete_inputs": {
            0: False,  # Fan running
            1: False,  # Heating active
            2: False,  # Cooling active
            3: False,  # Temperature alarm
            4: False,  # Humidity alarm
            5: False,  # L-space warning
            6: False,  # L-space critical
            7: False,  # System enabled
        },
        "input_registers": {
            0: 200,  # Zone temp degC * 10
            1: 450,  # Humidity % * 10
            2: 200,  # Supply temp degC * 10
            3: 0,    # Duct pressure Pa
            4: 100,  # L-space stability %
            5: 0,    # Fan speed %
            6: 0,    # Heating valve %
            7: 0,    # Cooling valve %
            8: 0,    # Damper position %
            9: 0,    # Energy kW * 10
        },
        "holding_registers": {
            0: 200,  # Temp setpoint degC * 10
            1: 450,  # Humidity setpoint % * 10
            2: 0,    # Fan speed command %
            3: 0,    # Operating mode
            4: 0,    # Damper position %
        },
    }

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        hvac_physics: HVACPhysics,
        description: str = "Library Environmental Controller (Schneider Modicon 1987 + Gateway)",
        scan_interval: float = 1.0,  # HVAC is slower than process PLCs
    ):
        """
        Initialise HVAC PLC.

        Args:
            device_name: Unique PLC identifier
            device_id: Modbus unit ID
            data_store: Reference to DataStore
            hvac_physics: HVACPhysics engine instance
            description: PLC description
            scan_interval: Scan cycle time in seconds (default 1s for HVAC)
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
        )

        self.hvac_physics = hvac_physics

        self.logger.info(
            f"HVACPLC '{device_name}' created " f"(hvac: {hvac_physics.device_name})"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return device type."""
        return "hvac_plc"

    def _supported_protocols(self) -> list[str]:
        """Supported protocols - Schneider Modicon uses Modbus."""
        return ["modbus"]

    async def _initialise_memory_map(self) -> None:
        """Initialise Modbus memory map."""
        # Discrete inputs (read-only status bits)
        self.memory_map["discrete_inputs[0]"] = False  # Fan running
        self.memory_map["discrete_inputs[1]"] = False  # Heating active
        self.memory_map["discrete_inputs[2]"] = False  # Cooling active
        self.memory_map["discrete_inputs[3]"] = False  # Temperature alarm
        self.memory_map["discrete_inputs[4]"] = False  # Humidity alarm
        self.memory_map["discrete_inputs[5]"] = False  # L-space warning
        self.memory_map["discrete_inputs[6]"] = False  # L-space critical
        self.memory_map["discrete_inputs[7]"] = False  # System enabled

        # Input registers (read-only telemetry)
        self.memory_map["input_registers[0]"] = 200  # Zone temp degC * 10
        self.memory_map["input_registers[1]"] = 450  # Humidity % * 10
        self.memory_map["input_registers[2]"] = 200  # Supply temp degC * 10
        self.memory_map["input_registers[3]"] = 0  # Duct pressure Pa
        self.memory_map["input_registers[4]"] = 100  # L-space stability %
        self.memory_map["input_registers[5]"] = 0  # Fan speed %
        self.memory_map["input_registers[6]"] = 0  # Heating valve %
        self.memory_map["input_registers[7]"] = 0  # Cooling valve %
        self.memory_map["input_registers[8]"] = 0  # Damper position %
        self.memory_map["input_registers[9]"] = 0  # Energy kW * 10

        # Coils (read/write control bits)
        self.memory_map["coils[0]"] = False  # System enable
        self.memory_map["coils[1]"] = True  # L-space dampener enable

        # Holding registers (read/write setpoints)
        self.memory_map["holding_registers[0]"] = 200  # Temp setpoint degC * 10
        self.memory_map["holding_registers[1]"] = 450  # Humidity setpoint % * 10
        self.memory_map["holding_registers[2]"] = 0  # Fan speed command %
        self.memory_map["holding_registers[3]"] = self.MODE_OFF  # Operating mode
        self.memory_map["holding_registers[4]"] = 0  # Damper position %

        self.logger.debug(f"HVACPLC '{self.device_name}' memory map initialised")

    # ----------------------------------------------------------------
    # BasePLC implementation - PLC scan cycle
    # ----------------------------------------------------------------

    async def _read_inputs(self) -> None:
        """
        Read inputs from HVAC physics.

        Updates discrete inputs and input registers from HVACPhysics state.
        """
        hvac_telem = self.hvac_physics.get_telemetry()

        # Update discrete inputs (status/alarm bits)
        self.memory_map["discrete_inputs[0]"] = hvac_telem.get("fan_running", False)
        self.memory_map["discrete_inputs[1]"] = hvac_telem.get("heating_active", False)
        self.memory_map["discrete_inputs[2]"] = hvac_telem.get("cooling_active", False)
        self.memory_map["discrete_inputs[3]"] = hvac_telem.get(
            "temperature_alarm", False
        )
        self.memory_map["discrete_inputs[4]"] = hvac_telem.get("humidity_alarm", False)
        self.memory_map["discrete_inputs[5]"] = hvac_telem.get("lspace_warning", False)
        self.memory_map["discrete_inputs[6]"] = hvac_telem.get("lspace_critical", False)
        self.memory_map["discrete_inputs[7]"] = self.hvac_physics.is_system_enabled()

        # Update input registers (analog telemetry)
        self.memory_map["input_registers[0]"] = int(
            hvac_telem.get("zone_temperature_c", 20) * 10
        )
        self.memory_map["input_registers[1]"] = int(
            hvac_telem.get("zone_humidity_percent", 45) * 10
        )
        self.memory_map["input_registers[2]"] = int(
            hvac_telem.get("supply_air_temp_c", 20) * 10
        )
        self.memory_map["input_registers[3]"] = int(
            hvac_telem.get("duct_pressure_pa", 0)
        )
        self.memory_map["input_registers[4]"] = int(
            hvac_telem.get("lspace_stability", 1.0) * 100
        )
        self.memory_map["input_registers[5]"] = int(
            hvac_telem.get("fan_speed_percent", 0)
        )
        self.memory_map["input_registers[6]"] = int(
            hvac_telem.get("heating_valve_percent", 0)
        )
        self.memory_map["input_registers[7]"] = int(
            hvac_telem.get("cooling_valve_percent", 0)
        )
        self.memory_map["input_registers[8]"] = int(
            hvac_telem.get("damper_position_percent", 0)
        )
        self.memory_map["input_registers[9]"] = int(
            hvac_telem.get("energy_consumption_kw", 0) * 10
        )

    async def _execute_logic(self) -> None:
        """
        Execute PLC control logic.

        Processes:
        - Temperature and humidity setpoints
        - Fan speed command
        - Operating mode
        - Damper position
        - System enable and L-space dampener
        """
        # Read setpoints from holding registers
        temp_setpoint = self.memory_map.get("holding_registers[0]", 200) / 10.0
        humidity_setpoint = self.memory_map.get("holding_registers[1]", 450) / 10.0
        fan_speed = self.memory_map.get("holding_registers[2]", 0)
        mode = self.memory_map.get("holding_registers[3]", self.MODE_OFF)
        damper_position = self.memory_map.get("holding_registers[4]", 0)

        # Clamp values
        temp_setpoint = max(15.0, min(30.0, temp_setpoint))
        humidity_setpoint = max(30.0, min(70.0, humidity_setpoint))
        fan_speed = max(0.0, min(100.0, fan_speed))
        mode = mode if mode in (0, 1, 2, 3) else self.MODE_OFF
        damper_position = max(0.0, min(100.0, damper_position))

        # Read control coils
        system_enable = self.memory_map.get("coils[0]", False)
        lspace_dampener = self.memory_map.get("coils[1]", True)

        # Store for output phase
        self._temp_setpoint = temp_setpoint
        self._humidity_setpoint = humidity_setpoint
        self._fan_speed = fan_speed
        self._mode = mode
        self._damper_position = damper_position
        self._system_enable = system_enable
        self._lspace_dampener = lspace_dampener

    async def _write_outputs(self) -> None:
        """
        Write outputs to HVAC physics.

        Commands:
        - Temperature and humidity setpoints
        - Fan speed
        - Operating mode
        - Damper position
        - System enable
        - L-space dampener
        """
        # Update HVAC physics via control interface
        self.hvac_physics.set_temperature_setpoint(self._temp_setpoint)
        self.hvac_physics.set_humidity_setpoint(self._humidity_setpoint)
        self.hvac_physics.set_fan_speed(self._fan_speed)
        self.hvac_physics.set_operating_mode(self._mode)
        self.hvac_physics.set_damper_position(self._damper_position)
        self.hvac_physics.set_system_enable(self._system_enable)
        self.hvac_physics.set_lspace_dampener(self._lspace_dampener)

    # ----------------------------------------------------------------
    # Convenience methods for programmatic control
    # ----------------------------------------------------------------

    async def set_temperature_setpoint(self, temp_c: float) -> None:
        """
        Set temperature setpoint.

        Args:
            temp_c: Target temperature in Celsius (15-30)
        """
        temp_c = max(15.0, min(30.0, temp_c))
        value = int(temp_c * 10)
        self.memory_map["holding_registers[0]"] = value
        await self.data_store.write_memory(
            self.device_name, "holding_registers[0]", value
        )
        self.logger.info(
            f"HVACPLC '{self.device_name}': Temperature setpoint = {temp_c}°C"
        )

    async def set_humidity_setpoint(self, percent: float) -> None:
        """
        Set humidity setpoint.

        Args:
            percent: Target relative humidity (30-70%)
        """
        percent = max(30.0, min(70.0, percent))
        value = int(percent * 10)
        self.memory_map["holding_registers[1]"] = value
        await self.data_store.write_memory(
            self.device_name, "holding_registers[1]", value
        )
        self.logger.info(
            f"HVACPLC '{self.device_name}': Humidity setpoint = {percent}%"
        )

    async def set_fan_speed(self, percent: float) -> None:
        """Set fan speed command."""
        percent = max(0.0, min(100.0, percent))
        value = int(percent)
        self.memory_map["holding_registers[2]"] = value
        await self.data_store.write_memory(
            self.device_name, "holding_registers[2]", value
        )
        self.logger.info(f"HVACPLC '{self.device_name}': Fan speed = {percent}%")

    async def set_operating_mode(self, mode: int) -> None:
        """
        Set operating mode.

        Args:
            mode: 0=off, 1=heat, 2=cool, 3=auto
        """
        if mode not in (0, 1, 2, 3):
            self.logger.warning(f"Invalid mode {mode}, using OFF")
            mode = 0
        self.memory_map["holding_registers[3]"] = mode
        await self.data_store.write_memory(
            self.device_name, "holding_registers[3]", mode
        )
        mode_names = {0: "OFF", 1: "HEAT", 2: "COOL", 3: "AUTO"}
        self.logger.info(f"HVACPLC '{self.device_name}': Mode = {mode_names.get(mode)}")

    async def set_damper_position(self, percent: float) -> None:
        """Set outside air damper position."""
        percent = max(0.0, min(100.0, percent))
        value = int(percent)
        self.memory_map["holding_registers[4]"] = value
        await self.data_store.write_memory(
            self.device_name, "holding_registers[4]", value
        )
        self.logger.info(f"HVACPLC '{self.device_name}': Damper = {percent}%")

    async def enable_system(self, enable: bool = True) -> None:
        """Enable or disable HVAC system."""
        self.memory_map["coils[0]"] = enable
        await self.data_store.write_memory(self.device_name, "coils[0]", enable)
        self.logger.info(
            f"HVACPLC '{self.device_name}': System "
            f"{'enabled' if enable else 'disabled'}"
        )

    async def enable_lspace_dampener(self, enable: bool = True) -> None:
        """Enable or disable L-space dampener."""
        self.memory_map["coils[1]"] = enable
        await self.data_store.write_memory(self.device_name, "coils[1]", enable)
        self.logger.info(
            f"HVACPLC '{self.device_name}': L-space dampener "
            f"{'enabled' if enable else 'disabled'}"
        )

    async def get_hvac_status(self) -> dict[str, Any]:
        """Get comprehensive HVAC status."""
        plc_status = await self.get_status()
        hvac_telem = self.hvac_physics.get_telemetry()

        return {
            **plc_status,
            "hvac": hvac_telem,
            "temperature_setpoint_c": (
                self._temp_setpoint if hasattr(self, "_temp_setpoint") else 20.0
            ),
            "humidity_setpoint_percent": (
                self._humidity_setpoint if hasattr(self, "_humidity_setpoint") else 45.0
            ),
            "fan_speed_command": (
                self._fan_speed if hasattr(self, "_fan_speed") else 0
            ),
            "operating_mode": self._mode if hasattr(self, "_mode") else 0,
            "system_enabled": (
                self._system_enable if hasattr(self, "_system_enable") else False
            ),
            "lspace_dampener_enabled": (
                self._lspace_dampener if hasattr(self, "_lspace_dampener") else True
            ),
        }
