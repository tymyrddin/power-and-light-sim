# components/physics/hvac_physics.py
"""
HVAC (Heating, Ventilation, Air Conditioning) physics simulation.

Models environmental control dynamics including:
- Zone temperature control (heating/cooling)
- Humidity control (humidification/dehumidification)
- Air handling (fans, dampers, duct pressure)
- Magical stability (L-space disturbances)

Based on the Library Environmental Management System at UU Power & Light Co.,
running on a Schneider Modicon (1987) with Modbus gateway (2005).

The Library requires precise environmental control to maintain temperature,
humidity, and magical stability within the University Library. Modifications
require formal approvals and librarian oversight (the Librarian is an orangutan
and takes book preservation very seriously).

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
class HVACState:
    """Current HVAC system physical state.

    Attributes:
        zone_temperature_c: Current zone temperature in Celsius
        zone_humidity_percent: Current relative humidity (0-100%)
        supply_air_temp_c: Supply air temperature
        return_air_temp_c: Return air temperature
        duct_pressure_pa: Duct static pressure in Pascals
        fan_speed_percent: Supply fan speed (0-100%)
        heating_valve_percent: Heating valve position (0-100%)
        cooling_valve_percent: Cooling valve position (0-100%)
        damper_position_percent: Outside air damper position (0-100%)
        humidifier_output_percent: Humidifier output (0-100%)
        lspace_stability: L-space dimensional stability (0.0-1.0, 1.0 = stable)
        energy_consumption_kw: Current power consumption
    """

    zone_temperature_c: float = 20.0
    zone_humidity_percent: float = 45.0
    supply_air_temp_c: float = 20.0
    return_air_temp_c: float = 20.0
    duct_pressure_pa: float = 0.0
    fan_speed_percent: float = 0.0
    heating_valve_percent: float = 0.0
    cooling_valve_percent: float = 0.0
    damper_position_percent: float = 0.0
    humidifier_output_percent: float = 0.0
    lspace_stability: float = 1.0
    energy_consumption_kw: float = 0.0


@dataclass
class HVACParameters:
    """HVAC system design parameters.

    Attributes:
        zone_thermal_mass: Thermal mass of zone in kJ/°C
        zone_volume_m3: Zone volume in cubic metres
        rated_heating_kw: Maximum heating capacity
        rated_cooling_kw: Maximum cooling capacity
        rated_airflow_m3s: Rated supply airflow in m³/s
        min_humidity_percent: Minimum acceptable humidity
        max_humidity_percent: Maximum acceptable humidity
        min_temperature_c: Minimum acceptable temperature
        max_temperature_c: Maximum acceptable temperature
        outside_temp_c: Outside air temperature (can be updated)
        outside_humidity_percent: Outside air humidity
        lspace_threshold_temp_c: Temperature at which L-space becomes unstable
        lspace_threshold_humidity: Humidity at which L-space becomes unstable
    """

    zone_thermal_mass: float = 500.0  # kJ/°C (large stone library)
    zone_volume_m3: float = 5000.0  # Large library
    rated_heating_kw: float = 50.0
    rated_cooling_kw: float = 75.0
    rated_airflow_m3s: float = 5.0
    min_humidity_percent: float = 40.0
    max_humidity_percent: float = 55.0
    min_temperature_c: float = 18.0
    max_temperature_c: float = 22.0
    outside_temp_c: float = 10.0  # Ankh-Morpork average
    outside_humidity_percent: float = 70.0
    lspace_threshold_temp_c: float = 25.0  # L-space gets unstable above this
    lspace_threshold_humidity: float = 60.0  # Or above this humidity


class HVACPhysics:
    """
    Simulates HVAC system physical behaviour.

    Models the Library Environmental Management System at UU P&L,
    which maintains temperature, humidity, and magical stability
    within the University Library. The Library exists partially
    in L-space (a dimension where all libraries are connected),
    requiring careful environmental control.

    Reads control inputs from device memory map:
    - temperature_setpoint_c (holding_registers[10])
    - humidity_setpoint_percent (holding_registers[11])
    - fan_speed_command (holding_registers[12])
    - mode_select (holding_registers[13]): 0=off, 1=heat, 2=cool, 3=auto
    - damper_command (holding_registers[14])
    - system_enable (coils[10])
    - lspace_dampener_enable (coils[11])

    Writes telemetry to device memory map:
    - zone_temperature_c (holding_registers[0])
    - zone_humidity_percent (holding_registers[1])
    - supply_air_temp_c (holding_registers[2])
    - duct_pressure_pa (holding_registers[3])
    - lspace_stability (holding_registers[4])
    - etc.

    Example:
        >>> hvac = HVACPhysics("library_hvac_1", data_store)
        >>> await hvac.initialise()
        >>> hvac.update(delta_time)  # Called each simulation cycle
    """

    # Operating modes
    MODE_OFF = 0
    MODE_HEAT = 1
    MODE_COOL = 2
    MODE_AUTO = 3

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        params: HVACParameters | None = None,
    ):
        """Initialise HVAC physics engine.

        Args:
            device_name: Name of device in DataStore
            data_store: DataStore instance for state access
            params: HVAC parameters (uses defaults if None)
        """
        if not device_name:
            raise ValueError("device_name cannot be empty")

        self.device_name = device_name
        self.data_store = data_store
        self.params = params or HVACParameters()
        self.state = HVACState()
        self.sim_time = SimulationTime()

        self._last_update_time: float = 0.0
        self._initialised = False
        self._control_cache: dict[str, Any] = {}

        # PID controller state for temperature
        self._temp_integral: float = 0.0
        self._temp_last_error: float = 0.0

        # PID controller state for humidity
        self._humidity_integral: float = 0.0
        self._humidity_last_error: float = 0.0

        logger.info(
            f"HVAC physics created: {device_name} "
            f"(zone {self.params.zone_volume_m3}m³, "
            f"{self.params.rated_heating_kw}kW heat, "
            f"{self.params.rated_cooling_kw}kW cool)"
        )

    # ----------------------------------------------------------------
    # Initialisation
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialise HVAC physics and write initial state to DataStore.

        Raises:
            RuntimeError: If device not found in DataStore
        """
        device = await self.data_store.get_device_state(self.device_name)
        if not device:
            raise RuntimeError(
                f"Cannot initialise HVAC physics: device {self.device_name} not found"
            )

        await self._write_telemetry()

        self._last_update_time = self.sim_time.now()
        self._initialised = True

        logger.info(f"HVAC physics initialised: {self.device_name}")

    # ----------------------------------------------------------------
    # Physics simulation
    # ----------------------------------------------------------------

    async def read_control_inputs(self) -> None:
        """Read control inputs from DataStore and cache them."""
        try:
            temp_setpoint = await self.data_store.read_memory(
                self.device_name, "holding_registers[10]"
            )
            humidity_setpoint = await self.data_store.read_memory(
                self.device_name, "holding_registers[11]"
            )
            fan_speed = await self.data_store.read_memory(
                self.device_name, "holding_registers[12]"
            )
            mode_select = await self.data_store.read_memory(
                self.device_name, "holding_registers[13]"
            )
            damper_command = await self.data_store.read_memory(
                self.device_name, "holding_registers[14]"
            )
            system_enable = await self.data_store.read_memory(
                self.device_name, "coils[10]"
            )
            lspace_dampener = await self.data_store.read_memory(
                self.device_name, "coils[11]"
            )

            self._control_cache = {
                "temperature_setpoint_c": (
                    float(temp_setpoint) if temp_setpoint else 20.0
                ),
                "humidity_setpoint_percent": (
                    float(humidity_setpoint) if humidity_setpoint else 45.0
                ),
                "fan_speed_command": float(fan_speed) if fan_speed else 0.0,
                "mode_select": int(mode_select) if mode_select else self.MODE_OFF,
                "damper_command": float(damper_command) if damper_command else 0.0,
                "system_enable": bool(system_enable) if system_enable else False,
                "lspace_dampener_enable": (
                    bool(lspace_dampener) if lspace_dampener else True
                ),
            }
        except Exception as e:
            logger.warning(
                f"Failed to read control inputs for {self.device_name}: {e}. "
                "Using defaults."
            )
            self._control_cache = {
                "temperature_setpoint_c": 20.0,
                "humidity_setpoint_percent": 45.0,
                "fan_speed_command": 0.0,
                "mode_select": self.MODE_OFF,
                "damper_command": 0.0,
                "system_enable": False,
                "lspace_dampener_enable": True,
            }

    def update(self, dt: float) -> None:
        """Update HVAC physics for one simulation step.

        Args:
            dt: Time delta in simulation seconds

        Raises:
            RuntimeError: If not initialised
        """
        if not self._initialised:
            raise RuntimeError(
                f"HVAC physics not initialised: {self.device_name}. "
                "Call initialise() first."
            )

        if dt <= 0:
            logger.warning(f"Invalid time delta {dt}, skipping update")
            return

        # Read control inputs
        temp_setpoint = self._read_control_input("temperature_setpoint_c", 20.0)
        humidity_setpoint = self._read_control_input("humidity_setpoint_percent", 45.0)
        fan_speed_cmd = self._read_control_input("fan_speed_command", 0.0)
        mode = self._read_control_input("mode_select", self.MODE_OFF)
        damper_cmd = self._read_control_input("damper_command", 0.0)
        system_enable = self._read_control_input("system_enable", False)
        lspace_dampener = self._read_control_input("lspace_dampener_enable", True)

        if not system_enable:
            self._system_off(dt)
            return

        # Update fan and airflow
        self._update_fan(dt, fan_speed_cmd)

        # Update damper position
        self._update_damper(dt, damper_cmd)

        # Update heating/cooling based on mode
        self._update_heating_cooling(dt, temp_setpoint, mode)

        # Update zone temperature
        self._update_zone_temperature(dt)

        # Update humidity
        self._update_humidity(dt, humidity_setpoint)

        # Update L-space stability
        self._update_lspace_stability(dt, lspace_dampener)

        # Calculate energy consumption
        self._update_energy_consumption()

        logger.debug(
            f"{self.device_name}: T={self.state.zone_temperature_c:.1f}°C, "
            f"RH={self.state.zone_humidity_percent:.1f}%, "
            f"L-space={self.state.lspace_stability:.2f}"
        )

    async def write_telemetry(self) -> None:
        """Write current HVAC state to device memory map."""
        await self._write_telemetry()

    def _read_control_input(self, name: str, default: Any) -> Any:
        """Read control input from cache."""
        return self._control_cache.get(name, default)

    def _system_off(self, dt: float) -> None:
        """Handle system off state - natural drift towards ambient.

        Args:
            dt: Time delta in seconds
        """
        # Fan stops
        self.state.fan_speed_percent *= 0.9 ** dt
        if self.state.fan_speed_percent < 1.0:
            self.state.fan_speed_percent = 0.0

        # Valves close
        self.state.heating_valve_percent *= 0.8 ** dt
        self.state.cooling_valve_percent *= 0.8 ** dt

        # Damper closes
        self.state.damper_position_percent *= 0.9 ** dt

        # Duct pressure drops
        self.state.duct_pressure_pa *= 0.7 ** dt

        # Zone drifts towards outside conditions (slowly due to insulation)
        drift_rate = 0.001  # Very slow for a well-insulated library
        self.state.zone_temperature_c += (
            (self.params.outside_temp_c - self.state.zone_temperature_c)
            * drift_rate
            * dt
        )
        self.state.zone_humidity_percent += (
            (self.params.outside_humidity_percent - self.state.zone_humidity_percent)
            * drift_rate
            * dt
        )

        # L-space slowly destabilises without active control
        if self.state.lspace_stability > 0.5:
            self.state.lspace_stability -= 0.001 * dt
            self.state.lspace_stability = max(0.5, self.state.lspace_stability)

        # Energy consumption drops
        self.state.energy_consumption_kw *= 0.5 ** dt
        if self.state.energy_consumption_kw < 0.1:
            self.state.energy_consumption_kw = 0.0

    def _update_fan(self, dt: float, speed_command: float) -> None:
        """Update fan speed and duct pressure.

        Args:
            dt: Time delta in seconds
            speed_command: Commanded fan speed (0-100%)
        """
        speed_command = max(0.0, min(100.0, speed_command))

        # Fan accelerates/decelerates towards command
        speed_error = speed_command - self.state.fan_speed_percent
        fan_time_constant = 5.0  # seconds
        self.state.fan_speed_percent += speed_error * (dt / fan_time_constant)
        self.state.fan_speed_percent = max(0.0, min(100.0, self.state.fan_speed_percent))

        # Duct pressure proportional to fan speed squared (fan laws)
        max_pressure = 500.0  # Pa at 100% speed
        target_pressure = max_pressure * (self.state.fan_speed_percent / 100.0) ** 2

        # Pressure responds quickly
        pressure_error = target_pressure - self.state.duct_pressure_pa
        self.state.duct_pressure_pa += pressure_error * 0.5 * dt

    def _update_damper(self, dt: float, damper_command: float) -> None:
        """Update outside air damper position.

        Args:
            dt: Time delta in seconds
            damper_command: Commanded damper position (0-100%)
        """
        damper_command = max(0.0, min(100.0, damper_command))

        # Damper moves slowly (actuator travel time)
        damper_error = damper_command - self.state.damper_position_percent
        damper_time_constant = 30.0  # seconds for full travel
        self.state.damper_position_percent += damper_error * (dt / damper_time_constant)
        self.state.damper_position_percent = max(
            0.0, min(100.0, self.state.damper_position_percent)
        )

    def _update_heating_cooling(
        self, dt: float, temp_setpoint: float, mode: int
    ) -> None:
        """Update heating and cooling valve positions.

        Uses PI control to maintain temperature setpoint.

        Args:
            dt: Time delta in seconds
            temp_setpoint: Temperature setpoint in Celsius
            mode: Operating mode (off, heat, cool, auto)
        """
        temp_setpoint = max(
            self.params.min_temperature_c,
            min(self.params.max_temperature_c, temp_setpoint),
        )

        temp_error = temp_setpoint - self.state.zone_temperature_c

        # PI controller gains
        kp = 10.0
        ki = 0.5

        # Anti-windup: limit integral
        self._temp_integral += temp_error * dt
        self._temp_integral = max(-50.0, min(50.0, self._temp_integral))

        # PI output
        control_output = kp * temp_error + ki * self._temp_integral

        if mode == self.MODE_OFF:
            self.state.heating_valve_percent = 0.0
            self.state.cooling_valve_percent = 0.0
        elif mode == self.MODE_HEAT:
            # Heating only
            self.state.heating_valve_percent = max(0.0, min(100.0, control_output))
            self.state.cooling_valve_percent = 0.0
        elif mode == self.MODE_COOL:
            # Cooling only
            self.state.heating_valve_percent = 0.0
            self.state.cooling_valve_percent = max(0.0, min(100.0, -control_output))
        elif mode == self.MODE_AUTO:
            # Auto mode - heat if too cold, cool if too warm
            if control_output > 0:
                self.state.heating_valve_percent = max(0.0, min(100.0, control_output))
                self.state.cooling_valve_percent = 0.0
            else:
                self.state.heating_valve_percent = 0.0
                self.state.cooling_valve_percent = max(
                    0.0, min(100.0, -control_output)
                )

        # Calculate supply air temperature based on valves
        if self.state.heating_valve_percent > 0:
            # Heating coil heats supply air
            heating_effect = self.state.heating_valve_percent / 100.0 * 15.0  # +15°C max
            self.state.supply_air_temp_c = self.state.return_air_temp_c + heating_effect
        elif self.state.cooling_valve_percent > 0:
            # Cooling coil cools supply air
            cooling_effect = self.state.cooling_valve_percent / 100.0 * 10.0  # -10°C max
            self.state.supply_air_temp_c = self.state.return_air_temp_c - cooling_effect
        else:
            # No conditioning - supply equals return (with some outside air mixing)
            mixing_ratio = self.state.damper_position_percent / 100.0
            self.state.supply_air_temp_c = (
                self.state.return_air_temp_c * (1 - mixing_ratio)
                + self.params.outside_temp_c * mixing_ratio
            )

    def _update_zone_temperature(self, dt: float) -> None:
        """Update zone temperature based on heat transfer.

        Args:
            dt: Time delta in seconds
        """
        # Heat input from supply air
        airflow_fraction = self.state.fan_speed_percent / 100.0
        airflow = airflow_fraction * self.params.rated_airflow_m3s

        # Heat capacity of air ~1.2 kJ/m³/°C
        air_heat_capacity = 1.2  # kJ/m³/°C
        temp_diff = self.state.supply_air_temp_c - self.state.zone_temperature_c
        heat_from_air = airflow * air_heat_capacity * temp_diff  # kW

        # Heat loss to outside (simplified)
        # U-value equivalent for a well-insulated building
        ua_value = 0.5  # kW/°C
        heat_loss = ua_value * (self.state.zone_temperature_c - self.params.outside_temp_c)

        # Internal heat gains (people, lights, equipment, magical books)
        internal_gains = 5.0  # kW baseline

        # L-space instability can cause temperature fluctuations
        if self.state.lspace_stability < 0.7:
            instability = 1.0 - self.state.lspace_stability
            fluctuation = math.sin(self.sim_time.now() * 0.5) * instability * 2.0
            internal_gains += fluctuation

        # Net heat rate
        net_heat_kw = heat_from_air - heat_loss + internal_gains

        # Temperature change
        temp_change = net_heat_kw * dt / self.params.zone_thermal_mass
        self.state.zone_temperature_c += temp_change

        # Return air temperature (slightly warmer than zone due to stratification)
        self.state.return_air_temp_c = self.state.zone_temperature_c + 0.5

    def _update_humidity(self, dt: float, humidity_setpoint: float) -> None:
        """Update zone humidity.

        Args:
            dt: Time delta in seconds
            humidity_setpoint: Humidity setpoint (%)
        """
        humidity_setpoint = max(
            self.params.min_humidity_percent,
            min(self.params.max_humidity_percent, humidity_setpoint),
        )

        humidity_error = humidity_setpoint - self.state.zone_humidity_percent

        # PI control for humidifier
        kp = 2.0
        ki = 0.1

        self._humidity_integral += humidity_error * dt
        self._humidity_integral = max(-100.0, min(100.0, self._humidity_integral))

        control_output = kp * humidity_error + ki * self._humidity_integral

        if control_output > 0:
            # Need humidification
            self.state.humidifier_output_percent = max(0.0, min(100.0, control_output))
        else:
            # Need dehumidification (via cooling coil)
            self.state.humidifier_output_percent = 0.0
            # Cooling coil also dehumidifies
            if self.state.cooling_valve_percent > 50:
                # Extra dehumidification from cooling
                pass

        # Humidity change
        # Humidifier adds moisture
        humidifier_effect = self.state.humidifier_output_percent / 100.0 * 5.0 * dt  # %

        # Outside air mixing
        airflow_fraction = self.state.fan_speed_percent / 100.0
        damper_fraction = self.state.damper_position_percent / 100.0
        outside_air_effect = (
            (self.params.outside_humidity_percent - self.state.zone_humidity_percent)
            * airflow_fraction
            * damper_fraction
            * 0.01
            * dt
        )

        # Natural moisture sources (people, books, L-space leakage)
        natural_sources = 0.1 * dt

        # L-space can cause humidity fluctuations (dimensional moisture transfer)
        if self.state.lspace_stability < 0.6:
            instability = 1.0 - self.state.lspace_stability
            fluctuation = math.cos(self.sim_time.now() * 0.3) * instability * 3.0 * dt
            natural_sources += fluctuation

        self.state.zone_humidity_percent += (
            humidifier_effect + outside_air_effect + natural_sources
        )
        self.state.zone_humidity_percent = max(
            10.0, min(90.0, self.state.zone_humidity_percent)
        )

    def _update_lspace_stability(self, dt: float, dampener_enabled: bool) -> None:
        """Update L-space dimensional stability.

        The Library exists partially in L-space, where all libraries are connected.
        Environmental stress (temperature, humidity) can cause dimensional instability,
        potentially allowing books to migrate or worse.

        Args:
            dt: Time delta in seconds
            dampener_enabled: Whether L-space dampener is active
        """
        # Calculate environmental stress
        temp_stress = 0.0
        if self.state.zone_temperature_c > self.params.lspace_threshold_temp_c:
            temp_stress = (
                self.state.zone_temperature_c - self.params.lspace_threshold_temp_c
            ) / 10.0
        elif self.state.zone_temperature_c < self.params.min_temperature_c:
            temp_stress = (
                self.params.min_temperature_c - self.state.zone_temperature_c
            ) / 10.0

        humidity_stress = 0.0
        if self.state.zone_humidity_percent > self.params.lspace_threshold_humidity:
            humidity_stress = (
                self.state.zone_humidity_percent - self.params.lspace_threshold_humidity
            ) / 20.0
        elif self.state.zone_humidity_percent < self.params.min_humidity_percent:
            humidity_stress = (
                self.params.min_humidity_percent - self.state.zone_humidity_percent
            ) / 20.0

        total_stress = temp_stress + humidity_stress

        # Dampener effect
        if dampener_enabled:
            recovery_rate = 0.02
            decay_rate = 0.01 * total_stress
        else:
            recovery_rate = 0.005
            decay_rate = 0.05 * total_stress

        # Update stability
        self.state.lspace_stability += (recovery_rate - decay_rate) * dt
        self.state.lspace_stability = max(0.0, min(1.0, self.state.lspace_stability))

        # Warn if unstable
        if self.state.lspace_stability < 0.5:
            logger.warning(
                f"{self.device_name}: L-space instability warning! "
                f"Stability={self.state.lspace_stability:.2f}, "
                f"T={self.state.zone_temperature_c:.1f}°C, "
                f"RH={self.state.zone_humidity_percent:.1f}%"
            )

    def _update_energy_consumption(self) -> None:
        """Calculate current energy consumption."""
        # Fan power (cube law)
        fan_power = 15.0 * (self.state.fan_speed_percent / 100.0) ** 3  # kW

        # Heating power
        heating_power = (
            self.params.rated_heating_kw * self.state.heating_valve_percent / 100.0
        )

        # Cooling power (COP of ~3)
        cooling_power = (
            self.params.rated_cooling_kw
            * self.state.cooling_valve_percent
            / 100.0
            / 3.0
        )

        # Humidifier power
        humidifier_power = 5.0 * self.state.humidifier_output_percent / 100.0  # kW

        # L-space dampener power
        dampener_power = 2.0 if self.state.lspace_stability < 0.9 else 0.5

        self.state.energy_consumption_kw = (
            fan_power + heating_power + cooling_power + humidifier_power + dampener_power
        )

    async def _write_telemetry(self) -> None:
        """Write current state to device memory map."""
        telemetry = {
            # Holding registers (analog values)
            "holding_registers[0]": int(self.state.zone_temperature_c * 10),  # 0.1°C
            "holding_registers[1]": int(self.state.zone_humidity_percent * 10),  # 0.1%
            "holding_registers[2]": int(self.state.supply_air_temp_c * 10),  # 0.1°C
            "holding_registers[3]": int(self.state.duct_pressure_pa),
            "holding_registers[4]": int(self.state.lspace_stability * 100),  # %
            "holding_registers[5]": int(self.state.fan_speed_percent),
            "holding_registers[6]": int(self.state.heating_valve_percent),
            "holding_registers[7]": int(self.state.cooling_valve_percent),
            "holding_registers[8]": int(self.state.damper_position_percent),
            "holding_registers[9]": int(self.state.energy_consumption_kw * 10),  # 0.1kW
            # Coils (digital status)
            "coils[0]": self.state.fan_speed_percent > 5.0,  # Fan running
            "coils[1]": self.state.heating_valve_percent > 5.0,  # Heating active
            "coils[2]": self.state.cooling_valve_percent > 5.0,  # Cooling active
            "coils[3]": (
                self.state.zone_temperature_c < self.params.min_temperature_c
                or self.state.zone_temperature_c > self.params.max_temperature_c
            ),  # Temp alarm
            "coils[4]": (
                self.state.zone_humidity_percent < self.params.min_humidity_percent
                or self.state.zone_humidity_percent > self.params.max_humidity_percent
            ),  # Humidity alarm
            "coils[5]": self.state.lspace_stability < 0.5,  # L-space warning
            "coils[6]": self.state.lspace_stability < 0.3,  # L-space critical
        }

        await self.data_store.bulk_write_memory(self.device_name, telemetry)

    # ----------------------------------------------------------------
    # State access
    # ----------------------------------------------------------------

    def get_state(self) -> HVACState:
        """Get current HVAC state."""
        return self.state

    def get_telemetry(self) -> dict[str, Any]:
        """Get telemetry data in dictionary format."""
        return {
            "zone_temperature_c": round(self.state.zone_temperature_c, 1),
            "zone_humidity_percent": round(self.state.zone_humidity_percent, 1),
            "supply_air_temp_c": round(self.state.supply_air_temp_c, 1),
            "return_air_temp_c": round(self.state.return_air_temp_c, 1),
            "duct_pressure_pa": round(self.state.duct_pressure_pa, 0),
            "fan_speed_percent": round(self.state.fan_speed_percent, 1),
            "heating_valve_percent": round(self.state.heating_valve_percent, 1),
            "cooling_valve_percent": round(self.state.cooling_valve_percent, 1),
            "damper_position_percent": round(self.state.damper_position_percent, 1),
            "humidifier_output_percent": round(self.state.humidifier_output_percent, 1),
            "lspace_stability": round(self.state.lspace_stability, 2),
            "energy_consumption_kw": round(self.state.energy_consumption_kw, 1),
            "fan_running": self.state.fan_speed_percent > 5.0,
            "heating_active": self.state.heating_valve_percent > 5.0,
            "cooling_active": self.state.cooling_valve_percent > 5.0,
            "temperature_alarm": (
                self.state.zone_temperature_c < self.params.min_temperature_c
                or self.state.zone_temperature_c > self.params.max_temperature_c
            ),
            "humidity_alarm": (
                self.state.zone_humidity_percent < self.params.min_humidity_percent
                or self.state.zone_humidity_percent > self.params.max_humidity_percent
            ),
            "lspace_warning": self.state.lspace_stability < 0.5,
            "lspace_critical": self.state.lspace_stability < 0.3,
        }

    def set_outside_conditions(
        self, temperature_c: float, humidity_percent: float
    ) -> None:
        """Update outside air conditions.

        Args:
            temperature_c: Outside temperature in Celsius
            humidity_percent: Outside relative humidity (%)
        """
        self.params.outside_temp_c = temperature_c
        self.params.outside_humidity_percent = max(0.0, min(100.0, humidity_percent))
        logger.debug(
            f"{self.device_name}: Outside conditions updated - "
            f"T={temperature_c}°C, RH={humidity_percent}%"
        )
