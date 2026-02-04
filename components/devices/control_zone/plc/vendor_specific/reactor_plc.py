# components/devices/control_zone/plc/vendor_specific/reactor_plc.py
"""
Alchemical Reactor PLC device class.

Models the Siemens S7-400 (2003) controlling the Bursar's Automated Alchemical
Reactor at UU Power & Light Co. Bridges ReactorPhysics with protocol memory maps
(S7comm + Modbus gateway).

The Alchemical Reactor converts thaumic energy into usable thermal power while
maintaining containment and thaumic field stability. The Bursar insists on
precise documentation of all modifications.

Memory Map (Modbus-style, bridged from S7 DBs):
-----------------------------------------------------------------
Discrete Inputs (Read-only booleans):
  0: Reactor active (reaction rate > 1%)
  1: High temperature warning
  2: High pressure warning
  3: Thaumic field warning (stability < 50%)
  4: Containment warning (integrity < 80%)
  5: SCRAM active
  6: Severe damage (> 50%)
  7: Coolant flow low

Input Registers (Read-only 16-bit):
  0: Core temperature (degC)
  1: Coolant temperature (degC)
  2: Vessel pressure (bar * 10)
  3: Power output (MW * 10)
  4: Thaumic field strength (per cent)
  5: Reaction rate (per cent)
  6: Coolant flow rate (per cent)
  7: Containment integrity (per cent)
  8: Overtemperature time (seconds)
  9: Damage level (per cent)

Coils (Read/write booleans):
  0: SCRAM command (emergency shutdown)
  1: SCRAM reset command
  2: Thaumic dampener enable

Holding Registers (Read/write 16-bit):
  0: Power setpoint (per cent * 10)
  1: Coolant pump speed (per cent)
  2: Control rod position (per cent)
"""

from typing import Any

from components.devices.control_zone.plc.generic.base_plc import BasePLC
from components.physics.reactor_physics import ReactorPhysics
from components.state.data_store import DataStore


class ReactorPLC(BasePLC):
    """
    PLC for Alchemical Reactor control and monitoring.

    Models a Siemens S7-400 (2003) with:
    - S7comm for native Siemens communications
    - Modbus TCP gateway for SCADA integration

    Reads from:
    - ReactorPhysics: Temperatures, pressure, reaction rate, thaumic stability

    Controls:
    - Power setpoint
    - Coolant pump speed
    - Control rod position
    - Thaumic dampener
    - Emergency shutdown (SCRAM)
    """

    # Modbus register definitions for adapter setup
    DEFAULT_SETUP = {
        "coils": {
            0: False,  # SCRAM command
            1: False,  # SCRAM reset
            2: True,  # Thaumic dampener enable
        },
        "discrete_inputs": {
            0: False,  # Reactor active
            1: False,  # High temp warning
            2: False,  # High pressure warning
            3: False,  # Thaumic warning
            4: False,  # Containment warning
            5: False,  # SCRAM active
            6: False,  # Severe damage
            7: False,  # Coolant flow low
        },
        "input_registers": {
            0: 25,  # Core temp degC
            1: 25,  # Coolant temp degC
            2: 10,  # Pressure bar * 10
            3: 0,  # Power MW * 10
            4: 100,  # Thaumic strength %
            5: 0,  # Reaction rate %
            6: 0,  # Coolant flow %
            7: 100,  # Containment %
            8: 0,  # Overtemp time sec
            9: 0,  # Damage %
        },
        "holding_registers": {
            0: 0,  # Power setpoint % * 10
            1: 0,  # Coolant pump speed %
            2: 1000,  # Control rods % * 10 (100% = inserted)
        },
    }

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        reactor_physics: ReactorPhysics,
        description: str = "Alchemical Reactor Controller (Siemens S7-400 2003)",
        scan_interval: float = 0.1,
    ):
        """
        Initialise reactor PLC.

        Args:
            device_name: Unique PLC identifier
            device_id: S7 slot / Modbus unit ID
            data_store: Reference to DataStore
            reactor_physics: ReactorPhysics engine instance
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

        self.reactor_physics = reactor_physics

        # Internal state for edge detection
        self._scram_reset_edge = False

        self.logger.info(
            f"ReactorPLC '{device_name}' created "
            f"(reactor: {reactor_physics.device_name})"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return device type."""
        return "reactor_plc"

    def _supported_protocols(self) -> list[str]:
        """Supported protocols - Siemens uses S7 and Modbus gateway."""
        return ["s7", "modbus"]

    async def _initialise_memory_map(self) -> None:
        """Initialise memory map (Modbus-style, bridged from S7 DBs)."""
        # Discrete inputs (read-only status bits)
        self.memory_map["discrete_inputs[0]"] = False  # Reactor active
        self.memory_map["discrete_inputs[1]"] = False  # High temp warning
        self.memory_map["discrete_inputs[2]"] = False  # High pressure warning
        self.memory_map["discrete_inputs[3]"] = False  # Thaumic warning
        self.memory_map["discrete_inputs[4]"] = False  # Containment warning
        self.memory_map["discrete_inputs[5]"] = False  # SCRAM active
        self.memory_map["discrete_inputs[6]"] = False  # Severe damage
        self.memory_map["discrete_inputs[7]"] = False  # Coolant flow low

        # Input registers (read-only telemetry)
        self.memory_map["input_registers[0]"] = 25  # Core temp degC
        self.memory_map["input_registers[1]"] = 25  # Coolant temp degC
        self.memory_map["input_registers[2]"] = 10  # Pressure bar * 10
        self.memory_map["input_registers[3]"] = 0  # Power MW * 10
        self.memory_map["input_registers[4]"] = 100  # Thaumic strength %
        self.memory_map["input_registers[5]"] = 0  # Reaction rate %
        self.memory_map["input_registers[6]"] = 0  # Coolant flow %
        self.memory_map["input_registers[7]"] = 100  # Containment %
        self.memory_map["input_registers[8]"] = 0  # Overtemp time sec
        self.memory_map["input_registers[9]"] = 0  # Damage %

        # Coils (read/write control bits)
        self.memory_map["coils[0]"] = False  # SCRAM command
        self.memory_map["coils[1]"] = False  # SCRAM reset
        self.memory_map["coils[2]"] = True  # Thaumic dampener enable

        # Holding registers (read/write setpoints)
        self.memory_map["holding_registers[0]"] = 0  # Power setpoint % * 10
        self.memory_map["holding_registers[1]"] = 0  # Coolant pump speed %
        self.memory_map["holding_registers[2]"] = (
            1000  # Control rods % * 10 (100% = inserted)
        )

        self.logger.debug(f"ReactorPLC '{self.device_name}' memory map initialised")

    # ----------------------------------------------------------------
    # BasePLC implementation - PLC scan cycle
    # ----------------------------------------------------------------

    async def _read_inputs(self) -> None:
        """
        Read inputs from reactor physics.

        Updates discrete inputs and input registers from ReactorPhysics state.
        """
        reactor_telem = self.reactor_physics.get_telemetry()

        # Update discrete inputs (status/alarm bits)
        self.memory_map["discrete_inputs[0]"] = reactor_telem.get(
            "reactor_active", False
        )
        self.memory_map["discrete_inputs[1]"] = reactor_telem.get(
            "high_temperature", False
        )
        self.memory_map["discrete_inputs[2]"] = (
            reactor_telem.get("vessel_pressure_bar", 0)
            > self.reactor_physics.params.max_safe_pressure_bar
        )
        self.memory_map["discrete_inputs[3]"] = reactor_telem.get(
            "thaumic_warning", False
        )
        self.memory_map["discrete_inputs[4]"] = (
            reactor_telem.get("containment_integrity_percent", 100) < 80
        )
        self.memory_map["discrete_inputs[5]"] = reactor_telem.get("scram_active", False)
        self.memory_map["discrete_inputs[6]"] = (
            reactor_telem.get("damage_percent", 0) > 50
        )
        self.memory_map["discrete_inputs[7]"] = (
            reactor_telem.get("coolant_flow_percent", 0) < 20
        )

        # Update input registers (analog telemetry)
        self.memory_map["input_registers[0]"] = int(
            reactor_telem.get("core_temperature_c", 25)
        )
        self.memory_map["input_registers[1]"] = int(
            reactor_telem.get("coolant_temperature_c", 25)
        )
        self.memory_map["input_registers[2]"] = int(
            reactor_telem.get("vessel_pressure_bar", 1) * 10
        )
        self.memory_map["input_registers[3]"] = int(
            reactor_telem.get("power_output_mw", 0) * 10
        )
        self.memory_map["input_registers[4]"] = int(
            reactor_telem.get("thaumic_field_strength", 1) * 100
        )
        self.memory_map["input_registers[5]"] = int(
            reactor_telem.get("reaction_rate_percent", 0)
        )
        self.memory_map["input_registers[6]"] = int(
            reactor_telem.get("coolant_flow_percent", 0)
        )
        self.memory_map["input_registers[7]"] = int(
            reactor_telem.get("containment_integrity_percent", 100)
        )
        self.memory_map["input_registers[8]"] = int(
            reactor_telem.get("overtemp_time_sec", 0)
        )
        self.memory_map["input_registers[9]"] = int(
            reactor_telem.get("damage_percent", 0)
        )

    async def _execute_logic(self) -> None:
        """
        Execute PLC control logic.

        Processes:
        - Power setpoint from holding registers
        - Coolant pump speed command
        - Control rod position command
        - SCRAM command and reset
        - Thaumic dampener control
        """
        # Read setpoints from holding registers
        power_setpoint = self.memory_map.get("holding_registers[0]", 0) / 10.0
        coolant_pump = self.memory_map.get("holding_registers[1]", 0)
        control_rods = self.memory_map.get("holding_registers[2]", 1000) / 10.0

        # Clamp values
        power_setpoint = max(0.0, min(150.0, power_setpoint))
        coolant_pump = max(0.0, min(100.0, coolant_pump))
        control_rods = max(0.0, min(100.0, control_rods))

        # Read control coils
        scram_command = self.memory_map.get("coils[0]", False)
        scram_reset = self.memory_map.get("coils[1]", False)
        thaumic_dampener = self.memory_map.get("coils[2]", True)

        # Detect SCRAM reset rising edge
        scram_reset_rising = scram_reset and not self._scram_reset_edge
        self._scram_reset_edge = scram_reset

        # Store for output phase
        self._power_setpoint = power_setpoint
        self._coolant_pump = coolant_pump
        self._control_rods = control_rods
        self._scram_command = scram_command
        self._scram_reset_rising = scram_reset_rising
        self._thaumic_dampener = thaumic_dampener

    async def _write_outputs(self) -> None:
        """
        Write outputs to reactor physics.

        Commands:
        - Power setpoint
        - Coolant pump speed
        - Control rod position
        - Thaumic dampener state
        - SCRAM trigger/reset
        """
        # Update reactor physics via control interface
        self.reactor_physics.set_power_setpoint(self._power_setpoint)
        self.reactor_physics.set_coolant_pump_speed(self._coolant_pump)
        self.reactor_physics.set_control_rods_position(self._control_rods)
        self.reactor_physics.set_thaumic_dampener(self._thaumic_dampener)

        # Handle SCRAM command
        if self._scram_command:
            self.reactor_physics.trigger_scram()
            self.logger.warning(f"ReactorPLC '{self.device_name}': SCRAM commanded!")

        # Handle SCRAM reset (on rising edge only)
        if self._scram_reset_rising:
            if self.reactor_physics.reset_scram():
                self.logger.info(f"ReactorPLC '{self.device_name}': SCRAM reset OK")
                # Auto-clear SCRAM coils
                self.memory_map["coils[0]"] = False
                self.memory_map["coils[1]"] = False
            else:
                self.logger.warning(
                    f"ReactorPLC '{self.device_name}': SCRAM reset failed - "
                    f"conditions not safe"
                )

    # ----------------------------------------------------------------
    # Convenience methods for programmatic control
    # ----------------------------------------------------------------

    async def set_power_setpoint(self, percent: float) -> None:
        """
        Set power setpoint programmatically.

        Args:
            percent: Target power as percentage of rated (0-150)
        """
        percent = max(0.0, min(150.0, percent))
        value = int(percent * 10)
        self.memory_map["holding_registers[0]"] = value
        await self.data_store.write_memory(
            self.device_name, "holding_registers[0]", value
        )
        self.logger.info(
            f"ReactorPLC '{self.device_name}': Power setpoint = {percent}%"
        )

    async def set_coolant_pump(self, percent: float) -> None:
        """Set coolant pump speed."""
        percent = max(0.0, min(100.0, percent))
        value = int(percent)
        self.memory_map["holding_registers[1]"] = value
        await self.data_store.write_memory(
            self.device_name, "holding_registers[1]", value
        )
        self.logger.info(f"ReactorPLC '{self.device_name}': Coolant pump = {percent}%")

    async def set_control_rods(self, percent: float) -> None:
        """
        Set control rod position.

        Args:
            percent: 0 = fully inserted (shutdown), 100 = fully withdrawn
        """
        percent = max(0.0, min(100.0, percent))
        value = int(percent * 10)
        self.memory_map["holding_registers[2]"] = value
        await self.data_store.write_memory(
            self.device_name, "holding_registers[2]", value
        )
        self.logger.info(f"ReactorPLC '{self.device_name}': Control rods = {percent}%")

    async def enable_thaumic_dampener(self, enable: bool = True) -> None:
        """Enable or disable thaumic dampener."""
        self.memory_map["coils[2]"] = enable
        await self.data_store.write_memory(self.device_name, "coils[2]", enable)
        self.logger.info(
            f"ReactorPLC '{self.device_name}': Thaumic dampener "
            f"{'enabled' if enable else 'disabled'}"
        )

    async def trigger_scram(self) -> None:
        """Trigger emergency shutdown (SCRAM)."""
        self.memory_map["coils[0]"] = True
        await self.data_store.write_memory(self.device_name, "coils[0]", True)
        self.logger.warning(f"ReactorPLC '{self.device_name}': SCRAM commanded")

    async def reset_scram_command(self) -> None:
        """Command SCRAM reset."""
        self.memory_map["coils[1]"] = True
        await self.data_store.write_memory(self.device_name, "coils[1]", True)
        self.logger.info(f"ReactorPLC '{self.device_name}': SCRAM reset commanded")

    async def get_reactor_status(self) -> dict[str, Any]:
        """Get comprehensive reactor status."""
        plc_status = await self.get_status()
        reactor_telem = self.reactor_physics.get_telemetry()

        return {
            **plc_status,
            "reactor": reactor_telem,
            "power_setpoint_percent": (
                self._power_setpoint if hasattr(self, "_power_setpoint") else 0
            ),
            "coolant_pump_percent": (
                self._coolant_pump if hasattr(self, "_coolant_pump") else 0
            ),
            "control_rods_percent": (
                self._control_rods if hasattr(self, "_control_rods") else 100
            ),
            "thaumic_dampener_enabled": (
                self._thaumic_dampener if hasattr(self, "_thaumic_dampener") else True
            ),
        }
