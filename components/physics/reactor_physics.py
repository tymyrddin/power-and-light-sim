# components/physics/reactor_physics.py
"""
Alchemical reactor physics simulation.

Models reactor dynamics including:
- Temperature dynamics (reaction heat, cooling)
- Pressure dynamics (vessel pressure, relief valves)
- Reaction kinetics (conversion rate, runaway conditions)
- Thaumic field stability (the magical component)
- Safety systems (trips, emergency cooling, containment)

Based on the Bursar's Automated Alchemical Reactor Controls
at UU Power & Light Co., running on a Siemens S7-400 (2003).

Integrates with:
- SimulationTime for accurate temporal progression
- DataStore for reading control inputs and writing telemetry
"""

import logging
import math
from dataclasses import dataclass
from typing import Any

from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime

logger = logging.getLogger(__name__)


@dataclass
class ReactorState:
    """Current reactor physical state.

    Attributes:
        core_temperature_c: Core temperature in Celsius
        coolant_temperature_c: Coolant outlet temperature
        vessel_pressure_bar: Reactor vessel pressure
        coolant_flow_rate: Coolant flow as fraction of nominal (0.0-1.0)
        reaction_rate: Current reaction rate as fraction of nominal (0.0-1.5)
        power_output_mw: Thermal power output in megawatts
        thaumic_field_strength: Magical field stability (0.0-1.0, 1.0 = stable)
        containment_integrity: Containment status (0.0-1.0, 1.0 = intact)
        cumulative_overtemp_time: Total time spent above safe temperature
        damage_level: Physical damage from overtemperature (0.0-1.0)
    """

    core_temperature_c: float = 25.0
    coolant_temperature_c: float = 25.0
    vessel_pressure_bar: float = 1.0
    coolant_flow_rate: float = 0.0
    reaction_rate: float = 0.0
    power_output_mw: float = 0.0
    thaumic_field_strength: float = 1.0
    containment_integrity: float = 1.0
    cumulative_overtemp_time: float = 0.0
    damage_level: float = 0.0


@dataclass
class ReactorParameters:
    """Reactor design parameters.

    Attributes:
        rated_power_mw: Nominal thermal power output
        rated_temperature_c: Normal operating core temperature
        max_safe_temperature_c: High temperature alarm threshold
        critical_temperature_c: Emergency shutdown threshold
        max_safe_pressure_bar: Maximum design pressure
        thermal_mass: Thermal inertia in MJ/°C
        coolant_capacity: Cooling capacity in MW/°C temperature difference
        reaction_time_constant: Time constant for reaction rate changes
        thaumic_decay_rate: Rate at which thaumic instability grows
        thaumic_recovery_rate: Rate at which thaumic field stabilises
    """

    rated_power_mw: float = 25.0
    rated_temperature_c: float = 350.0
    max_safe_temperature_c: float = 400.0
    critical_temperature_c: float = 450.0
    max_safe_pressure_bar: float = 150.0
    thermal_mass: float = 50.0  # MJ/°C
    coolant_capacity: float = 0.5  # MW per °C difference
    reaction_time_constant: float = 10.0  # seconds
    thaumic_decay_rate: float = 0.01  # per second when unstable
    thaumic_recovery_rate: float = 0.05  # per second when stable


class ReactorPhysics:
    """
    Simulates alchemical reactor physical behaviour.

    Models the Bursar's Automated Alchemical Reactor at UU P&L,
    which converts thaumic input into usable thermal energy while
    accounting for both chemical and metaphysical variables.

    Reads control inputs from device memory map:
    - power_setpoint_percent (holding_registers[10])
    - coolant_pump_speed (holding_registers[11])
    - control_rods_position (holding_registers[12])
    - emergency_shutdown (coils[10])
    - thaumic_dampener_enabled (coils[11])

    Writes telemetry to device memory map:
    - core_temperature_c (holding_registers[0])
    - coolant_temperature_c (holding_registers[1])
    - vessel_pressure_bar (holding_registers[2])
    - power_output_mw (holding_registers[3])
    - thaumic_field_strength (holding_registers[4])
    - etc.

    Example:
        >>> reactor = ReactorPhysics("reactor_plc_1", data_store)
        >>> await reactor.initialise()
        >>> reactor.update(delta_time)  # Called each simulation cycle
    """

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        params: ReactorParameters | None = None,
    ):
        """Initialise reactor physics engine.

        Args:
            device_name: Name of device in DataStore
            data_store: DataStore instance for state access
            params: Reactor parameters (uses defaults if None)
        """
        if not device_name:
            raise ValueError("device_name cannot be empty")

        self.device_name = device_name
        self.data_store = data_store
        self.params = params or ReactorParameters()
        self.state = ReactorState()
        self.sim_time = SimulationTime()

        self._last_update_time: float = 0.0
        self._initialised = False
        self._control_cache: dict[str, Any] = {}
        self._scram_active = False  # Emergency shutdown state

        logger.info(
            f"Reactor physics created: {device_name} "
            f"(rated {self.params.rated_power_mw}MW @ {self.params.rated_temperature_c}°C)"
        )

    # ----------------------------------------------------------------
    # Initialisation
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialise reactor physics and write initial state to DataStore.

        Raises:
            RuntimeError: If device not found in DataStore
        """
        device = await self.data_store.get_device_state(self.device_name)
        if not device:
            raise RuntimeError(
                f"Cannot initialise reactor physics: device {self.device_name} not found"
            )

        await self._write_telemetry()

        self._last_update_time = self.sim_time.now()
        self._initialised = True

        logger.info(f"Reactor physics initialised: {self.device_name}")

    # ----------------------------------------------------------------
    # Physics simulation
    # ----------------------------------------------------------------

    async def read_control_inputs(self) -> None:
        """Read control inputs from DataStore and cache them."""
        try:
            power_setpoint = await self.data_store.read_memory(
                self.device_name, "holding_registers[10]"
            )
            coolant_pump = await self.data_store.read_memory(
                self.device_name, "holding_registers[11]"
            )
            control_rods = await self.data_store.read_memory(
                self.device_name, "holding_registers[12]"
            )
            emergency_shutdown = await self.data_store.read_memory(
                self.device_name, "coils[10]"
            )
            thaumic_dampener = await self.data_store.read_memory(
                self.device_name, "coils[11]"
            )

            self._control_cache = {
                "power_setpoint_percent": (
                    float(power_setpoint) if power_setpoint else 0.0
                ),
                "coolant_pump_speed": float(coolant_pump) if coolant_pump else 0.0,
                "control_rods_position": float(control_rods) if control_rods else 100.0,
                "emergency_shutdown": (
                    bool(emergency_shutdown) if emergency_shutdown else False
                ),
                "thaumic_dampener_enabled": (
                    bool(thaumic_dampener) if thaumic_dampener else True
                ),
            }
        except Exception as e:
            logger.warning(
                f"Failed to read control inputs for {self.device_name}: {e}. Using defaults."
            )
            self._control_cache = {
                "power_setpoint_percent": 0.0,
                "coolant_pump_speed": 0.0,
                "control_rods_position": 100.0,
                "emergency_shutdown": False,
                "thaumic_dampener_enabled": True,
            }

    def update(self, dt: float) -> None:
        """Update reactor physics for one simulation step.

        Args:
            dt: Time delta in simulation seconds

        Raises:
            RuntimeError: If not initialised
        """
        if not self._initialised:
            raise RuntimeError(
                f"Reactor physics not initialised: {self.device_name}. "
                "Call initialise() first."
            )

        if dt <= 0:
            logger.warning(f"Invalid time delta {dt}, skipping update")
            return

        # Read control inputs
        power_setpoint = self._read_control_input("power_setpoint_percent", 0.0)
        coolant_pump = self._read_control_input("coolant_pump_speed", 0.0)
        control_rods = self._read_control_input("control_rods_position", 100.0)
        emergency_shutdown = self._read_control_input("emergency_shutdown", False)
        thaumic_dampener = self._read_control_input("thaumic_dampener_enabled", True)

        # Check for emergency shutdown (SCRAM)
        if emergency_shutdown or self._scram_active:
            self._emergency_shutdown(dt)
            return

        # Auto-SCRAM on critical conditions
        if (
            self.state.core_temperature_c > self.params.critical_temperature_c
            or self.state.containment_integrity < 0.5
        ):
            logger.warning(f"{self.device_name}: Auto-SCRAM triggered!")
            self._scram_active = True
            self._emergency_shutdown(dt)
            return

        # Update physics
        self._update_reaction_rate(dt, power_setpoint, control_rods)
        self._update_temperatures(dt, coolant_pump)
        self._update_pressure()
        self._update_thaumic_field(dt, thaumic_dampener)
        self._update_power_output()
        self._update_damage(dt)

        logger.debug(
            f"{self.device_name}: T={self.state.core_temperature_c:.1f}°C, "
            f"P={self.state.power_output_mw:.1f}MW, "
            f"Thaumic={self.state.thaumic_field_strength:.2f}"
        )

    async def write_telemetry(self) -> None:
        """Write current reactor state to device memory map."""
        await self._write_telemetry()

    def _read_control_input(self, name: str, default: Any) -> Any:
        """Read control input from cache."""
        return self._control_cache.get(name, default)

    def _update_reaction_rate(
        self, dt: float, power_setpoint: float, control_rods: float
    ) -> None:
        """Update reaction rate based on control inputs.

        Control rods: 0% = fully inserted (no reaction), 100% = fully withdrawn
        Power setpoint: target power as percentage of rated

        Args:
            dt: Time delta in seconds
            power_setpoint: Target power percentage (0-100)
            control_rods: Control rod position (0-100%)
        """
        # Clamp inputs
        power_setpoint = max(0.0, min(100.0, power_setpoint))
        control_rods = max(0.0, min(100.0, control_rods))

        # Target reaction rate based on control rods and setpoint
        # Control rods physically limit maximum possible reaction
        max_reaction = control_rods / 100.0
        target_reaction = min(power_setpoint / 100.0, max_reaction)

        # Thaumic instability can cause reaction rate fluctuations
        if self.state.thaumic_field_strength < 0.8:
            instability = 1.0 - self.state.thaumic_field_strength
            # Random-ish fluctuation based on time (deterministic for reproducibility)
            fluctuation = math.sin(self.sim_time.now() * 2.0) * instability * 0.2
            target_reaction *= 1.0 + fluctuation

        # First-order lag towards target
        rate_error = target_reaction - self.state.reaction_rate
        time_constant = self.params.reaction_time_constant
        self.state.reaction_rate += rate_error * (dt / time_constant)

        # Physical limits
        self.state.reaction_rate = max(0.0, min(1.5, self.state.reaction_rate))

    def _update_temperatures(self, dt: float, coolant_pump: float) -> None:
        """Update temperature dynamics.

        Heat balance: thermal_mass * dT/dt = power_generated - power_removed

        Args:
            dt: Time delta in seconds
            coolant_pump: Coolant pump speed (0-100%)
        """
        # Coolant flow rate (0-1)
        self.state.coolant_flow_rate = max(0.0, min(100.0, coolant_pump)) / 100.0

        # Heat generated by reaction (MW)
        heat_generated = self.state.reaction_rate * self.params.rated_power_mw

        # Heat removed by coolant (MW)
        # Cooling power depends on flow rate and temperature difference
        temp_difference = (
            self.state.core_temperature_c - self.state.coolant_temperature_c
        )
        heat_removed = (
            self.state.coolant_flow_rate
            * self.params.coolant_capacity
            * max(0.0, temp_difference)
        )

        # Net heat rate (MW)
        net_heat_rate = heat_generated - heat_removed

        # Temperature change: dT = (power in MW) * dt / (thermal_mass in MJ/°C)
        # Note: 1 MW = 1 MJ/s
        temp_change = net_heat_rate * dt / self.params.thermal_mass
        self.state.core_temperature_c += temp_change

        # Coolant heats up as it passes through
        if self.state.coolant_flow_rate > 0.01:
            # Heat removal efficiency: 80% (heat_removed * 0.8)
            # Simplified: coolant temp rises towards core temp
            coolant_target = 25.0 + (self.state.core_temperature_c - 25.0) * 0.3
            coolant_error = coolant_target - self.state.coolant_temperature_c
            self.state.coolant_temperature_c += coolant_error * 0.1 * dt
        else:
            # No flow - coolant stagnates
            self.state.coolant_temperature_c += (
                (self.state.core_temperature_c - self.state.coolant_temperature_c)
                * 0.01
                * dt
            )

        # Ambient cooling when cold
        if self.state.core_temperature_c < 30.0 and self.state.reaction_rate < 0.01:
            ambient = 25.0
            self.state.core_temperature_c += (
                (ambient - self.state.core_temperature_c) * 0.01 * dt
            )
            self.state.coolant_temperature_c += (
                (ambient - self.state.coolant_temperature_c) * 0.05 * dt
            )

        # Physical limit - can't go below ambient
        self.state.core_temperature_c = max(25.0, self.state.core_temperature_c)
        self.state.coolant_temperature_c = max(25.0, self.state.coolant_temperature_c)

    def _update_pressure(self) -> None:
        """Update vessel pressure based on temperature.

        Pressure rises with temperature (ideal gas approximation).
        """
        # Pressure proportional to absolute temperature
        # At 25°C (298K), pressure = 1 bar
        # At rated temp, pressure = rated pressure
        # Baseline pressure + temperature component
        base_pressure = 1.0
        temp_pressure = (self.params.max_safe_pressure_bar - base_pressure) * (
            (self.state.core_temperature_c - 25.0)
            / (self.params.rated_temperature_c - 25.0)
        )

        self.state.vessel_pressure_bar = max(1.0, base_pressure + temp_pressure)

        # Thaumic instability can cause pressure fluctuations
        if self.state.thaumic_field_strength < 0.7:
            instability = 1.0 - self.state.thaumic_field_strength
            fluctuation = math.sin(self.sim_time.now() * 3.0) * instability * 10.0
            self.state.vessel_pressure_bar += fluctuation

    def _update_thaumic_field(self, dt: float, dampener_enabled: bool) -> None:
        """Update thaumic field stability.

        The thaumic field represents the magical component of the reactor.
        It becomes unstable at high power or when the dampener is disabled.

        Args:
            dt: Time delta in seconds
            dampener_enabled: Whether thaumic dampener is active
        """
        # Thaumic instability sources
        power_stress = self.state.reaction_rate / 1.0  # Stress at 100% power
        temp_stress = max(
            0.0,
            (self.state.core_temperature_c - self.params.rated_temperature_c) / 100.0,
        )

        total_stress = power_stress * 0.3 + temp_stress * 0.5

        if dampener_enabled:
            # Dampener helps stabilise the field
            recovery = self.params.thaumic_recovery_rate * dt
            decay = total_stress * self.params.thaumic_decay_rate * dt * 0.5
        else:
            # Without dampener, field degrades faster
            recovery = self.params.thaumic_recovery_rate * dt * 0.2
            decay = total_stress * self.params.thaumic_decay_rate * dt * 2.0

        # Update field strength
        self.state.thaumic_field_strength += recovery - decay
        self.state.thaumic_field_strength = max(
            0.0, min(1.0, self.state.thaumic_field_strength)
        )

        # Severe instability damages containment
        if self.state.thaumic_field_strength < 0.3:
            containment_damage = (0.3 - self.state.thaumic_field_strength) * 0.01 * dt
            self.state.containment_integrity -= containment_damage
            self.state.containment_integrity = max(
                0.0, self.state.containment_integrity
            )

            logger.warning(
                f"{self.device_name}: Thaumic instability! "
                f"Field={self.state.thaumic_field_strength:.2f}, "
                f"Containment={self.state.containment_integrity:.2f}"
            )

    def _update_power_output(self) -> None:
        """Calculate thermal power output."""
        # Power output based on reaction rate and efficiency
        # Efficiency drops at extreme temperatures
        if self.state.core_temperature_c > self.params.max_safe_temperature_c:
            efficiency = 0.8
        elif self.state.core_temperature_c < 100.0:
            efficiency = 0.5
        else:
            efficiency = 1.0

        self.state.power_output_mw = (
            self.state.reaction_rate * self.params.rated_power_mw * efficiency
        )

    def _update_damage(self, dt: float) -> None:
        """Track cumulative damage from overtemperature operation."""
        if self.state.core_temperature_c > self.params.max_safe_temperature_c:
            self.state.cumulative_overtemp_time += dt

            # Damage rate increases with temperature
            overtemp = (
                self.state.core_temperature_c - self.params.max_safe_temperature_c
            )
            damage_rate = overtemp / 100.0 * 0.01  # 1% per second per 100°C over

            self.state.damage_level += damage_rate * dt
            self.state.damage_level = min(1.0, self.state.damage_level)

            if self.state.damage_level > 0.1:
                logger.warning(
                    f"{self.device_name}: Thermal damage {self.state.damage_level * 100:.1f}% "
                    f"at {self.state.core_temperature_c:.1f}°C"
                )

    def _emergency_shutdown(self, dt: float) -> None:
        """Emergency shutdown (SCRAM) - rapid reaction termination.

        Args:
            dt: Time delta in seconds
        """
        self._scram_active = True

        # Reaction rate drops rapidly (control rods insert)
        self.state.reaction_rate *= 0.5 ** (dt / 2.0)  # Half-life of 2 seconds
        if self.state.reaction_rate < 0.001:
            self.state.reaction_rate = 0.0

        # Decay heat continues but decreases
        decay_heat = self.state.reaction_rate * self.params.rated_power_mw * 0.07

        # Coolant runs at maximum during SCRAM
        self.state.coolant_flow_rate = 1.0

        # Temperature decreases (emergency cooling)
        temp_difference = self.state.core_temperature_c - 25.0
        cooling_rate = self.params.coolant_capacity * temp_difference - decay_heat
        temp_change = cooling_rate * dt / self.params.thermal_mass
        self.state.core_temperature_c -= max(0, temp_change)
        self.state.core_temperature_c = max(25.0, self.state.core_temperature_c)

        # Thaumic field recovers during shutdown
        self.state.thaumic_field_strength += self.params.thaumic_recovery_rate * dt
        self.state.thaumic_field_strength = min(1.0, self.state.thaumic_field_strength)

        # Update dependent states
        self._update_pressure()
        self._update_power_output()

        logger.debug(
            f"{self.device_name}: SCRAM active - T={self.state.core_temperature_c:.1f}°C, "
            f"reaction={self.state.reaction_rate:.3f}"
        )

    async def _write_telemetry(self) -> None:
        """Write current state to device memory map."""
        telemetry = {
            # Holding registers (analog values)
            "holding_registers[0]": int(self.state.core_temperature_c),
            "holding_registers[1]": int(self.state.coolant_temperature_c),
            "holding_registers[2]": int(self.state.vessel_pressure_bar * 10),  # 0.1 bar
            "holding_registers[3]": int(self.state.power_output_mw * 10),  # 0.1 MW
            "holding_registers[4]": int(self.state.thaumic_field_strength * 100),  # %
            "holding_registers[5]": int(self.state.reaction_rate * 100),  # %
            "holding_registers[6]": int(self.state.coolant_flow_rate * 100),  # %
            "holding_registers[7]": int(self.state.containment_integrity * 100),  # %
            "holding_registers[8]": int(self.state.cumulative_overtemp_time),
            "holding_registers[9]": int(self.state.damage_level * 100),  # %
            # Coils (digital status)
            "coils[0]": self.state.reaction_rate > 0.01,  # Reactor active
            "coils[1]": self.state.core_temperature_c
            > self.params.max_safe_temperature_c,
            "coils[2]": self.state.vessel_pressure_bar
            > self.params.max_safe_pressure_bar,
            "coils[3]": self.state.thaumic_field_strength < 0.5,  # Thaumic warning
            "coils[4]": self.state.containment_integrity < 0.8,  # Containment warning
            "coils[5]": self._scram_active,  # SCRAM active
            "coils[6]": self.state.damage_level > 0.5,  # Severe damage
        }

        await self.data_store.bulk_write_memory(self.device_name, telemetry)

    # ----------------------------------------------------------------
    # State access
    # ----------------------------------------------------------------

    def get_state(self) -> ReactorState:
        """Get current reactor state."""
        return self.state

    def get_telemetry(self) -> dict[str, Any]:
        """Get telemetry data in dictionary format."""
        return {
            "core_temperature_c": round(self.state.core_temperature_c, 1),
            "coolant_temperature_c": round(self.state.coolant_temperature_c, 1),
            "vessel_pressure_bar": round(self.state.vessel_pressure_bar, 1),
            "power_output_mw": round(self.state.power_output_mw, 2),
            "reaction_rate_percent": round(self.state.reaction_rate * 100, 1),
            "coolant_flow_percent": round(self.state.coolant_flow_rate * 100, 1),
            "thaumic_field_strength": round(self.state.thaumic_field_strength, 2),
            "containment_integrity_percent": round(
                self.state.containment_integrity * 100, 1
            ),
            "reactor_active": self.state.reaction_rate > 0.01,
            "scram_active": self._scram_active,
            "high_temperature": (
                self.state.core_temperature_c > self.params.max_safe_temperature_c
            ),
            "thaumic_warning": self.state.thaumic_field_strength < 0.5,
            "overtemp_time_sec": int(self.state.cumulative_overtemp_time),
            "damage_percent": round(self.state.damage_level * 100, 1),
        }

    def reset_scram(self) -> bool:
        """Attempt to reset SCRAM condition.

        Returns:
            True if SCRAM was reset, False if conditions not safe
        """
        if (
            self.state.core_temperature_c < self.params.rated_temperature_c
            and self.state.thaumic_field_strength > 0.8
            and self.state.containment_integrity > 0.9
        ):
            self._scram_active = False
            logger.info(f"{self.device_name}: SCRAM reset successful")
            return True
        else:
            logger.warning(
                f"{self.device_name}: SCRAM reset failed - conditions not safe"
            )
            return False

    # ----------------------------------------------------------------
    # Control interface (for PLC integration)
    # ----------------------------------------------------------------

    def set_power_setpoint(self, percent: float) -> None:
        """Set reactor power setpoint.

        Args:
            percent: Target power as percentage of rated (0-150)
        """
        self._control_cache["power_setpoint_percent"] = max(0.0, min(150.0, percent))
        logger.debug(f"{self.device_name}: Power setpoint set to {percent}%")

    def set_control_rods_position(self, percent: float) -> None:
        """Set control rod position.

        Args:
            percent: Rod position (0=fully inserted, 100=fully withdrawn)
        """
        self._control_cache["control_rods_position"] = max(0.0, min(100.0, percent))
        logger.debug(f"{self.device_name}: Control rods set to {percent}%")

    def set_coolant_pump_speed(self, percent: float) -> None:
        """Set coolant pump speed.

        Args:
            percent: Pump speed as percentage (0-100)
        """
        self._control_cache["coolant_pump_speed"] = max(0.0, min(100.0, percent))
        logger.debug(f"{self.device_name}: Coolant pump set to {percent}%")

    def set_thaumic_dampener(self, enabled: bool) -> None:
        """Enable or disable thaumic dampener.

        Args:
            enabled: True to enable dampener
        """
        self._control_cache["thaumic_dampener_enabled"] = bool(enabled)
        logger.debug(
            f"{self.device_name}: Thaumic dampener "
            f"{'enabled' if enabled else 'disabled'}"
        )

    def trigger_scram(self) -> None:
        """Trigger emergency shutdown (SCRAM)."""
        self._control_cache["emergency_shutdown"] = True
        logger.warning(f"{self.device_name}: SCRAM triggered")

    def get_power_setpoint(self) -> float:
        """Get current power setpoint."""
        return self._control_cache.get("power_setpoint_percent", 0.0)

    def get_control_rods_position(self) -> float:
        """Get current control rod position."""
        return self._control_cache.get("control_rods_position", 100.0)

    def is_scram_active(self) -> bool:
        """Check if SCRAM is active."""
        return self._scram_active
