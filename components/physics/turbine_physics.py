# components/physics/turbine_physics.py
"""
Steam turbine physics simulation.

Models turbine dynamics including:
- Shaft speed response to steam flow
- Temperature dynamics
- Vibration based on operating conditions
- Power output calculations
- Physical damage from overspeed

Integrates with:
- SimulationTime for accurate temporal progression
- DataStore for reading control inputs and writing telemetry
- ConfigLoader for turbine parameters
"""

import logging
from dataclasses import dataclass
from typing import Any

from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class TurbineState:
    """Current turbine physical state.

    Attributes:
        shaft_speed_rpm: Current shaft rotational speed
        steam_pressure_psi: Steam inlet pressure
        steam_temperature_c: Steam inlet temperature in Celsius
        bearing_temperature_c: Bearing temperature in Celsius
        vibration_mils: Vibration amplitude in mils (0.001 inch)
        power_output_mw: Electrical power output in megawatts
        cumulative_overspeed_time: Total time spent above rated speed
        damage_level: Physical damage from overspeed (0.0-1.0)
    """

    shaft_speed_rpm: float = 0.0
    steam_pressure_psi: float = 0.0
    steam_temperature_c: float = 0.0
    bearing_temperature_c: float = 21.0  # 70°F = 21°C
    vibration_mils: float = 0.0
    power_output_mw: float = 0.0
    cumulative_overspeed_time: float = 0.0
    damage_level: float = 0.0


@dataclass
class TurbineParameters:
    """Turbine design parameters.

    Attributes:
        rated_speed_rpm: Nominal operating speed (typically 3600 or 3000 RPM)
        rated_power_mw: Maximum continuous power output
        max_safe_speed_rpm: Overspeed trip point (typically 110% rated)
        max_steam_pressure_psi: Maximum design pressure
        max_steam_temp_c: Maximum design temperature in Celsius
        inertia: Rotational inertia in kg·m²
        acceleration_rate: Maximum acceleration in RPM/second
        deceleration_rate: Natural deceleration in RPM/second
        vibration_normal_mils: Normal operating vibration
        vibration_critical_mils: Dangerous vibration threshold
    """

    rated_speed_rpm: int = 3600
    rated_power_mw: float = 100.0
    max_safe_speed_rpm: int = 3960  # 110% overspeed trip
    max_steam_pressure_psi: int = 2400
    max_steam_temp_c: int = 538  # 1000°F = 538°C
    inertia: float = 5000.0
    acceleration_rate: float = 100.0  # RPM/s
    deceleration_rate: float = 50.0  # RPM/s
    vibration_normal_mils: float = 2.0
    vibration_critical_mils: float = 10.0


class TurbinePhysics:
    """
    Simulates steam turbine physical behaviour.

    Updates turbine state based on control inputs from PLC
    and physical laws (thermodynamics, rotational dynamics).

    Reads control inputs from device memory map:
    - speed_setpoint_rpm (holding_registers[10])
    - governor_enabled (coils[10])
    - emergency_trip (coils[11])

    Writes telemetry to device memory map:
    - shaft_speed_rpm (holding_registers[0])
    - power_output_mw (holding_registers[5])
    - steam_pressure_psi (holding_registers[2])
    - etc.

    Example:
        >>> turbine = TurbinePhysics("turbine_plc_1", data_store)
        >>> await turbine.initialise()
        >>> turbine.update(delta_time)  # Called each simulation cycle
    """

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        params: TurbineParameters | None = None,
    ):
        """Initialise turbine physics engine.

        Args:
            device_name: Name of device in DataStore
            data_store: DataStore instance for state access
            params: Turbine parameters (uses defaults if None)
        """
        if not device_name:
            raise ValueError("device_name cannot be empty")

        self.device_name = device_name
        self.data_store = data_store
        self.params = params or TurbineParameters()
        self.state = TurbineState()
        self.sim_time = SimulationTime()

        self._last_update_time: float = 0.0
        self._initialised = False
        self._control_cache: dict[str, Any] = {}  # Cache for control inputs

        logger.info(
            f"Turbine physics created: {device_name} "
            f"(rated {self.params.rated_power_mw}MW @ {self.params.rated_speed_rpm}RPM)"
        )

    # ----------------------------------------------------------------
    # Initialisation
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialise turbine physics and write initial state to DataStore.

        Should be called once before simulation starts.

        Raises:
            RuntimeError: If device not found in DataStore
        """
        # Verify device exists
        device = await self.data_store.get_device_state(self.device_name)
        if not device:
            raise RuntimeError(
                f"Cannot initialise turbine physics: device {self.device_name} not found"
            )

        # Write initial state to memory map
        await self._write_telemetry()

        self._last_update_time = self.sim_time.now()
        self._initialised = True

        logger.info(f"Turbine physics initialised: {self.device_name}")

    # ----------------------------------------------------------------
    # Physics simulation
    # ----------------------------------------------------------------

    async def read_control_inputs(self) -> None:
        """Read control inputs from DataStore and cache them.

        Should be called before update() to populate the control cache.
        This allows update() to be synchronous while still accessing
        async DataStore data.
        """
        # Read control inputs from device memory map
        # These map to specific addresses that protocol handlers write to
        try:
            speed_setpoint = await self.data_store.read_memory(
                self.device_name, "holding_registers[10]"
            )
            governor_enabled = await self.data_store.read_memory(
                self.device_name, "coils[10]"
            )
            emergency_trip = await self.data_store.read_memory(
                self.device_name, "coils[11]"
            )

            self._control_cache = {
                "speed_setpoint_rpm": float(speed_setpoint) if speed_setpoint else 0.0,
                "governor_enabled": (
                    bool(governor_enabled) if governor_enabled else False
                ),
                "emergency_trip": bool(emergency_trip) if emergency_trip else False,
            }
        except Exception as e:
            logger.warning(
                f"Failed to read control inputs for {self.device_name}: {e}. Using defaults."
            )
            self._control_cache = {
                "speed_setpoint_rpm": 0.0,
                "governor_enabled": False,
                "emergency_trip": False,
            }

    def update(self, dt: float) -> None:
        """Update turbine physics for one simulation step.

        Called by main simulation loop each update cycle.
        Reads control inputs from cache (populated by read_control_inputs()),
        updates physics, and modifies internal state.

        Note: Call read_control_inputs() before this method to populate
        the control cache with current values from DataStore.

        Args:
            dt: Time delta in simulation seconds

        Raises:
            RuntimeError: If not initialised
        """
        if not self._initialised:
            raise RuntimeError(
                f"Turbine physics not initialised: {self.device_name}. Call initialise() first."
            )

        if dt <= 0:
            logger.warning(f"Invalid time delta {dt}, skipping update")
            return

        # Read control inputs from PLC (via memory map)
        # These are set by protocol handlers or test scripts
        speed_setpoint = self._read_control_input("speed_setpoint_rpm", 0.0)
        governor_enabled = self._read_control_input("governor_enabled", False)
        emergency_trip = self._read_control_input("emergency_trip", False)

        # Update physics based on controls
        if emergency_trip:
            self._emergency_shutdown(dt)
        elif governor_enabled:
            self._update_with_governor(dt, speed_setpoint)
        else:
            self._natural_deceleration(dt)

        # Update dependent states
        self._update_temperatures(dt)
        self._update_vibration()
        self._update_power_output()
        self._update_damage(dt)

        logger.debug(
            f"{self.device_name}: RPM={self.state.shaft_speed_rpm:.0f}, "
            f"Power={self.state.power_output_mw:.1f}MW"
        )

    async def write_telemetry(self) -> None:
        """Write current turbine state to device memory map.

        Should be called after update() to persist state.
        """
        await self._write_telemetry()

    def _read_control_input(self, name: str, default: Any) -> Any:
        """Read control input from device memory map.

        This is a synchronous helper that reads from the cached control inputs
        that should be populated at the start of each update cycle.

        Args:
            name: Control input name (e.g., 'speed_setpoint_rpm', 'governor_enabled')
            default: Default value if control input not found

        Returns:
            Control input value from cache or default
        """
        # Read from control cache (populated by async read before update())
        return self._control_cache.get(name, default)

    def _update_with_governor(self, dt: float, setpoint_rpm: float) -> None:
        """Update shaft speed with governor control active.

        Governor attempts to maintain speed at setpoint by adjusting steam flow.

        Args:
            dt: Time delta in seconds
            setpoint_rpm: Target speed from PLC
        """
        # Validate setpoint
        setpoint_rpm = max(0.0, min(setpoint_rpm, self.params.max_safe_speed_rpm * 1.1))

        speed_error = setpoint_rpm - self.state.shaft_speed_rpm

        if abs(speed_error) < 1.0:
            self.state.shaft_speed_rpm = setpoint_rpm
            return

        # Proportional control (simplified governor model)
        if speed_error > 0:
            # Accelerating - limited by maximum steam flow
            accel = min(self.params.acceleration_rate, abs(speed_error) * 10.0)
            self.state.shaft_speed_rpm += accel * dt
        else:
            # Decelerating - reduce steam flow
            decel = min(self.params.deceleration_rate, abs(speed_error) * 10.0)
            self.state.shaft_speed_rpm -= decel * dt

        # Physical limit - can't have negative speed
        self.state.shaft_speed_rpm = max(0.0, self.state.shaft_speed_rpm)

    def _natural_deceleration(self, dt: float) -> None:
        """Natural speed decay without governor control.

        Friction and windage cause turbine to slow down.

        Args:
            dt: Time delta in seconds
        """
        if self.state.shaft_speed_rpm > 0:
            self.state.shaft_speed_rpm -= self.params.deceleration_rate * dt
            self.state.shaft_speed_rpm = max(0.0, self.state.shaft_speed_rpm)

    def _emergency_shutdown(self, dt: float) -> None:
        """Emergency trip - rapid shutdown.

        Closes steam valves and applies emergency braking.

        Args:
            dt: Time delta in seconds
        """
        # Fast deceleration (2x normal rate)
        if self.state.shaft_speed_rpm > 0:
            emergency_decel_rate = self.params.deceleration_rate * 2.0
            self.state.shaft_speed_rpm -= emergency_decel_rate * dt
            self.state.shaft_speed_rpm = max(0.0, self.state.shaft_speed_rpm)

            logger.debug(
                f"{self.device_name}: Emergency shutdown - "
                f"RPM={self.state.shaft_speed_rpm:.0f}"
            )

        # Temperatures decay towards ambient
        ambient_temp = 21.0  # Celsius (70°F = 21°C)
        thermal_time_constant = 0.1  # Faster cooling during shutdown

        self.state.bearing_temperature_c += (
            (ambient_temp - self.state.bearing_temperature_c)
            * thermal_time_constant
            * dt
        )
        self.state.steam_temperature_c += (
            (ambient_temp - self.state.steam_temperature_c)
            * thermal_time_constant
            * 0.5
            * dt
        )

    def _update_temperatures(self, dt: float) -> None:
        """Update temperatures based on operating conditions.

        Args:
            dt: Time delta in seconds
        """
        # Bearing temperature increases with speed and vibration
        speed_factor = self.state.shaft_speed_rpm / self.params.rated_speed_rpm
        vibration_factor = self.state.vibration_mils / self.params.vibration_normal_mils

        # Target temperature = ambient + speed heating + vibration heating (Celsius)
        # Ambient: 21°C, Speed heating: up to 115°C, Vibration heating: up to 30°C
        # Max: ~166°C at full speed/vibration (realistic for industrial turbines)
        # Normal operating: ~136°C at rated speed (well above 93°C trip point)
        target_bearing_temp = 21.0 + (speed_factor * 58.0) + (vibration_factor * 15.0)

        # First-order thermal lag (faster for simulation purposes)
        thermal_time_constant = 0.15  # Faster heating response
        temp_error = target_bearing_temp - self.state.bearing_temperature_c
        self.state.bearing_temperature_c += temp_error * thermal_time_constant * dt

        # Steam temperature correlates with load (Celsius)
        if self.state.shaft_speed_rpm > 100:
            target_steam_temp = 315.0 + (
                speed_factor * 167.0
            )  # 315-482°C range (600-900°F)
            target_steam_pressure = 1000.0 + (speed_factor * 800.0)
        else:
            target_steam_temp = 21.0  # Celsius ambient
            target_steam_pressure = 0.0

        # Steam has slower thermal response
        steam_time_constant = 0.05
        temp_error = target_steam_temp - self.state.steam_temperature_c
        self.state.steam_temperature_c += temp_error * steam_time_constant * dt

        # Pressure follows similar dynamics
        pressure_error = target_steam_pressure - self.state.steam_pressure_psi
        self.state.steam_pressure_psi += pressure_error * thermal_time_constant * dt

    def _update_vibration(self) -> None:
        """Calculate vibration based on operating conditions.

        Vibration increases with:
        - Speed deviation from rated
        - Accumulated damage
        """
        # Vibration increases with speed deviation from rated
        speed_deviation = abs(self.state.shaft_speed_rpm - self.params.rated_speed_rpm)
        deviation_factor = speed_deviation / self.params.rated_speed_rpm

        # Base vibration + deviation component
        self.state.vibration_mils = self.params.vibration_normal_mils * (
            1.0 + deviation_factor * 3.0
        )

        # Damage amplifies vibration
        self.state.vibration_mils *= 1.0 + self.state.damage_level

        # Log high vibration
        if self.state.vibration_mils > self.params.vibration_critical_mils:
            logger.warning(
                f"{self.device_name}: High vibration {self.state.vibration_mils:.1f} mils"
            )

    def _update_power_output(self) -> None:
        """Calculate electrical power output.

        Power is proportional to speed, peaking near rated speed.
        """
        speed_ratio = self.state.shaft_speed_rpm / self.params.rated_speed_rpm

        if speed_ratio < 0.2:  # Below minimum stable speed
            self.state.power_output_mw = 0.0
        else:
            # Power curve peaks at rated speed, decreases above
            # Simplified: linear up to rated, slight increase to 110%, then drops
            if speed_ratio <= 1.0:
                self.state.power_output_mw = self.params.rated_power_mw * speed_ratio
            else:
                # Slight overpower capability, but efficiency drops
                self.state.power_output_mw = self.params.rated_power_mw * min(
                    speed_ratio, 1.05
                )

    def _update_damage(self, dt: float) -> None:
        """Track cumulative damage from overspeed operation.

        Operating above rated speed causes accelerated wear and potential damage.

        Args:
            dt: Time delta in seconds
        """
        if self.state.shaft_speed_rpm > self.params.rated_speed_rpm:
            # Accumulate overspeed time
            self.state.cumulative_overspeed_time += dt

            # Damage rate increases exponentially with overspeed
            overspeed_ratio = self.state.shaft_speed_rpm / self.params.rated_speed_rpm

            if overspeed_ratio > 1.1:  # Above 110% rated (trip point)
                # Severe overspeed - rapid damage accumulation
                # 1% damage per second at 120% rated speed
                damage_rate = (overspeed_ratio - 1.1) * 0.01
                self.state.damage_level += damage_rate * dt
                self.state.damage_level = min(1.0, self.state.damage_level)

                if self.state.damage_level > 0.1:
                    logger.warning(
                        f"{self.device_name}: Overspeed damage {self.state.damage_level * 100:.1f}% "
                        f"at {self.state.shaft_speed_rpm:.0f} RPM"
                    )

    async def _write_telemetry(self) -> None:
        """Write current state to device memory map.

        Maps turbine state to Modbus-style memory addresses.
        """
        telemetry = {
            # Holding registers (analog values)
            "holding_registers[0]": int(self.state.shaft_speed_rpm),
            "holding_registers[1]": int(self.state.steam_temperature_c),
            "holding_registers[2]": int(self.state.steam_pressure_psi),
            "holding_registers[3]": int(self.state.bearing_temperature_c),
            "holding_registers[4]": int(
                self.state.vibration_mils * 10
            ),  # 0.1 mil resolution
            "holding_registers[5]": int(self.state.power_output_mw),
            "holding_registers[6]": int(self.state.cumulative_overspeed_time),
            "holding_registers[7]": int(self.state.damage_level * 100),  # Percentage
            # Coils (digital status)
            "coils[0]": self.state.shaft_speed_rpm > 100,  # Running
            "coils[1]": self.state.shaft_speed_rpm
            > self.params.max_safe_speed_rpm,  # Overspeed
            "coils[2]": self.state.vibration_mils
            > self.params.vibration_critical_mils,  # High vibration
            "coils[3]": self.state.bearing_temperature_c
            > 65,  # High bearing temp (65°C = 149°F)
            "coils[4]": self.state.damage_level > 0.5,  # Severe damage
        }

        await self.data_store.bulk_write_memory(self.device_name, telemetry)

    # ----------------------------------------------------------------
    # State access
    # ----------------------------------------------------------------

    def get_state(self) -> TurbineState:
        """Get current turbine state.

        Returns:
            Current TurbineState snapshot
        """
        return self.state

    def get_telemetry(self) -> dict[str, Any]:
        """Get telemetry data in dictionary format.

        Returns:
            Dictionary with current telemetry values
        """
        return {
            "shaft_speed_rpm": int(self.state.shaft_speed_rpm),
            "power_output_mw": round(self.state.power_output_mw, 1),
            "steam_pressure_psi": int(self.state.steam_pressure_psi),
            "steam_temperature_c": int(self.state.steam_temperature_c),
            "bearing_temperature_c": int(self.state.bearing_temperature_c),
            "vibration_mils": round(self.state.vibration_mils, 1),
            "turbine_running": self.state.shaft_speed_rpm > 100,
            "governor_online": self._control_cache.get("governor_enabled", False),
            "trip_active": self._control_cache.get("emergency_trip", False),
            "overspeed": self.state.shaft_speed_rpm > self.params.max_safe_speed_rpm,
            "overspeed_time_sec": int(self.state.cumulative_overspeed_time),
            "damage_percent": int(self.state.damage_level * 100),
        }

    # ----------------------------------------------------------------
    # Control interface (for PLC integration)
    # ----------------------------------------------------------------

    def set_speed_setpoint(self, rpm: float) -> None:
        """Set turbine speed setpoint.

        This directly updates the control cache, bypassing DataStore.
        Use for direct PLC-to-physics integration.

        Args:
            rpm: Target speed in RPM
        """
        self._control_cache["speed_setpoint_rpm"] = max(0.0, float(rpm))
        logger.debug(f"{self.device_name}: Speed setpoint set to {rpm} RPM")

    def set_governor_enabled(self, enabled: bool) -> None:
        """Enable or disable governor control.

        Args:
            enabled: True to enable automatic speed control
        """
        self._control_cache["governor_enabled"] = bool(enabled)
        logger.debug(
            f"{self.device_name}: Governor {'enabled' if enabled else 'disabled'}"
        )

    def trigger_emergency_trip(self) -> None:
        """Trigger emergency shutdown.

        Closes steam valves and applies emergency braking.
        """
        self._control_cache["emergency_trip"] = True
        logger.warning(f"{self.device_name}: Emergency trip triggered")

    def reset_trip(self) -> bool:
        """Reset emergency trip condition.

        Returns:
            True if trip was reset, False if conditions not safe
        """
        # Only allow reset if turbine is below safe speed
        if self.state.shaft_speed_rpm < self.params.rated_speed_rpm * 0.1:
            self._control_cache["emergency_trip"] = False
            logger.info(f"{self.device_name}: Trip reset successful")
            return True
        else:
            logger.warning(
                f"{self.device_name}: Trip reset failed - speed too high "
                f"({self.state.shaft_speed_rpm} RPM)"
            )
            return False

    def get_speed_setpoint(self) -> float:
        """Get current speed setpoint.

        Returns:
            Current setpoint in RPM
        """
        return self._control_cache.get("speed_setpoint_rpm", 0.0)

    def is_governor_enabled(self) -> bool:
        """Check if governor is enabled.

        Returns:
            True if governor control is active
        """
        return self._control_cache.get("governor_enabled", False)

    def is_trip_active(self) -> bool:
        """Check if emergency trip is active.

        Returns:
            True if turbine is in emergency shutdown
        """
        return self._control_cache.get("emergency_trip", False)
