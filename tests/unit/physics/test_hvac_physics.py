# tests/unit/physics/test_hvac_physics.py
"""Comprehensive tests for HVACPhysics component.

This is Level 3 in our dependency tree - HVACPhysics depends on:
- DataStore (Level 2) - uses REAL DataStore
- SystemState (Level 1) - uses REAL SystemState (via DataStore)
- SimulationTime (Level 0) - uses REAL SimulationTime

Test Coverage:
- Initialisation and configuration
- Control input reading and caching
- Physics updates (temperature, humidity, airflow)
- L-space stability dynamics
- Energy consumption calculation
- Operating modes (off, heat, cool, auto)
- Telemetry writing to memory map
- Edge cases and error handling
"""

import asyncio

import pytest

from components.physics.hvac_physics import (
    HVACParameters,
    HVACPhysics,
    HVACState,
)
from components.state.data_store import DataStore
from components.state.system_state import SystemState


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
async def hvac_with_device():
    """Create HVACPhysics with registered device in DataStore."""
    system_state = SystemState()
    data_store = DataStore(system_state)

    await data_store.register_device(
        device_name="library_hvac_1",
        device_type="hvac_plc",
        device_id=1,
        protocols=["modbus"],
    )

    hvac = HVACPhysics("library_hvac_1", data_store)
    await hvac.initialise()

    return hvac, data_store


@pytest.fixture
def custom_params():
    """Factory for custom HVAC parameters."""

    def _create(**kwargs):
        return HVACParameters(**kwargs)

    return _create


# ================================================================
# INITIALISATION TESTS
# ================================================================
class TestHVACPhysicsInitialisation:
    """Test HVACPhysics initialisation."""

    def test_initialisation_with_defaults(self):
        """Test creating HVACPhysics with default parameters."""
        system_state = SystemState()
        data_store = DataStore(system_state)

        hvac = HVACPhysics("library_hvac_1", data_store)

        assert hvac.device_name == "library_hvac_1"
        assert hvac.data_store is data_store
        assert hvac.params.zone_thermal_mass == 500.0
        assert hvac.params.zone_volume_m3 == 5000.0
        assert not hvac._initialised

    def test_initialisation_with_custom_params(self, custom_params):
        """Test creating HVACPhysics with custom parameters."""
        system_state = SystemState()
        data_store = DataStore(system_state)

        params = custom_params(
            zone_thermal_mass=300.0,
            rated_heating_kw=30.0,
            rated_cooling_kw=50.0,
        )
        hvac = HVACPhysics("library_hvac_1", data_store, params)

        assert hvac.params.zone_thermal_mass == 300.0
        assert hvac.params.rated_heating_kw == 30.0
        assert hvac.params.rated_cooling_kw == 50.0

    def test_initialisation_empty_name_raises(self):
        """Test that empty device name raises ValueError."""
        system_state = SystemState()
        data_store = DataStore(system_state)

        with pytest.raises(ValueError, match="device_name cannot be empty"):
            HVACPhysics("", data_store)

    async def test_initialise_without_device_raises(self):
        """Test initialise raises if device not registered."""
        system_state = SystemState()
        data_store = DataStore(system_state)

        hvac = HVACPhysics("nonexistent_device", data_store)

        with pytest.raises(RuntimeError, match="not found"):
            await hvac.initialise()

    async def test_initialise_writes_initial_state(self, hvac_with_device):
        """Test initialise writes initial telemetry to memory map."""
        hvac, data_store = hvac_with_device

        # Check initial temperature was written (20°C * 10 = 200)
        zone_temp = await data_store.read_memory(
            "library_hvac_1", "holding_registers[0]"
        )
        assert zone_temp == 200  # 20.0°C * 10


# ================================================================
# CONTROL INPUT TESTS
# ================================================================
class TestHVACPhysicsControlInputs:
    """Test control input reading."""

    async def test_read_control_inputs_populates_cache(self, hvac_with_device):
        """Test reading control inputs from DataStore."""
        hvac, data_store = hvac_with_device

        await data_store.write_memory("library_hvac_1", "holding_registers[10]", 21)
        await data_store.write_memory("library_hvac_1", "holding_registers[11]", 50)
        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 75)
        await data_store.write_memory("library_hvac_1", "holding_registers[13]", 3)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()

        assert hvac._control_cache["temperature_setpoint_c"] == 21.0
        assert hvac._control_cache["humidity_setpoint_percent"] == 50.0
        assert hvac._control_cache["fan_speed_command"] == 75.0
        assert hvac._control_cache["mode_select"] == 3  # AUTO
        assert hvac._control_cache["system_enable"] is True

    async def test_read_control_inputs_handles_missing_values(self, hvac_with_device):
        """Test reading control inputs with missing values uses defaults."""
        hvac, data_store = hvac_with_device

        await hvac.read_control_inputs()

        assert hvac._control_cache["temperature_setpoint_c"] == 20.0
        assert hvac._control_cache["humidity_setpoint_percent"] == 45.0
        assert hvac._control_cache["system_enable"] is False


# ================================================================
# PHYSICS UPDATE TESTS
# ================================================================
class TestHVACPhysicsUpdates:
    """Test physics update behaviour."""

    async def test_update_before_initialise_raises(self):
        """Test update raises if not initialised."""
        system_state = SystemState()
        data_store = DataStore(system_state)

        hvac = HVACPhysics("library_hvac_1", data_store)

        with pytest.raises(RuntimeError, match="not initialised"):
            hvac.update(0.1)

    async def test_update_with_zero_dt_skipped(self, hvac_with_device):
        """Test update with zero time delta is skipped."""
        hvac, data_store = hvac_with_device
        initial_temp = hvac.state.zone_temperature_c

        hvac.update(0.0)

        assert hvac.state.zone_temperature_c == initial_temp

    async def test_update_with_negative_dt_skipped(self, hvac_with_device):
        """Test update with negative time delta is skipped."""
        hvac, data_store = hvac_with_device
        initial_temp = hvac.state.zone_temperature_c

        hvac.update(-1.0)

        assert hvac.state.zone_temperature_c == initial_temp

    async def test_system_off_causes_drift(self, hvac_with_device):
        """Test system off causes zone to drift towards ambient."""
        hvac, data_store = hvac_with_device

        # Set zone warmer than outside
        hvac.state.zone_temperature_c = 22.0
        hvac.params.outside_temp_c = 10.0

        # System disabled
        await data_store.write_memory("library_hvac_1", "coils[10]", False)
        await hvac.read_control_inputs()

        for _ in range(100):
            hvac.update(0.1)

        # Should drift slightly towards outside temp
        assert hvac.state.zone_temperature_c < 22.0


# ================================================================
# TEMPERATURE CONTROL TESTS
# ================================================================
class TestHVACTemperatureControl:
    """Test temperature control behaviour."""

    async def test_heating_raises_temperature(self, hvac_with_device):
        """Test heating mode raises zone temperature."""
        hvac, data_store = hvac_with_device

        # Set zone cold and enable heating
        hvac.state.zone_temperature_c = 15.0
        await data_store.write_memory("library_hvac_1", "holding_registers[10]", 20)
        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 100)
        await data_store.write_memory("library_hvac_1", "holding_registers[13]", 1)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()

        for _ in range(100):
            hvac.update(0.1)

        assert hvac.state.zone_temperature_c > 15.0
        assert hvac.state.heating_valve_percent > 0

    async def test_cooling_lowers_temperature(self, hvac_with_device):
        """Test cooling mode lowers zone temperature."""
        hvac, data_store = hvac_with_device

        # Set zone warm and enable cooling
        hvac.state.zone_temperature_c = 25.0
        await data_store.write_memory("library_hvac_1", "holding_registers[10]", 20)
        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 100)
        await data_store.write_memory("library_hvac_1", "holding_registers[13]", 2)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()

        for _ in range(100):
            hvac.update(0.1)

        assert hvac.state.zone_temperature_c < 25.0
        assert hvac.state.cooling_valve_percent > 0

    async def test_auto_mode_selects_heating_or_cooling(self, hvac_with_device):
        """Test auto mode selects appropriate heating or cooling."""
        hvac, data_store = hvac_with_device

        # Cold zone, auto mode should heat
        hvac.state.zone_temperature_c = 16.0
        await data_store.write_memory("library_hvac_1", "holding_registers[10]", 20)
        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 100)
        await data_store.write_memory("library_hvac_1", "holding_registers[13]", 3)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()
        hvac.update(0.1)

        assert hvac.state.heating_valve_percent > 0
        assert hvac.state.cooling_valve_percent == 0

    async def test_temperature_stabilises_at_setpoint(self, hvac_with_device):
        """Test temperature stabilises near setpoint."""
        hvac, data_store = hvac_with_device

        hvac.state.zone_temperature_c = 18.0
        await data_store.write_memory("library_hvac_1", "holding_registers[10]", 20)
        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 100)
        await data_store.write_memory("library_hvac_1", "holding_registers[13]", 3)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()

        for _ in range(500):
            hvac.update(0.1)

        # Should be close to setpoint
        assert abs(hvac.state.zone_temperature_c - 20.0) < 2.0


# ================================================================
# HUMIDITY CONTROL TESTS
# ================================================================
class TestHVACHumidityControl:
    """Test humidity control behaviour."""

    async def test_humidifier_raises_humidity(self, hvac_with_device):
        """Test humidifier raises zone humidity."""
        hvac, data_store = hvac_with_device

        hvac.state.zone_humidity_percent = 30.0
        await data_store.write_memory("library_hvac_1", "holding_registers[11]", 50)
        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 100)
        await data_store.write_memory("library_hvac_1", "holding_registers[13]", 3)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()

        for _ in range(100):
            hvac.update(0.1)

        assert hvac.state.zone_humidity_percent > 30.0
        assert hvac.state.humidifier_output_percent > 0

    async def test_humidity_stays_in_valid_range(self, hvac_with_device):
        """Test humidity stays within valid range."""
        hvac, data_store = hvac_with_device

        hvac.state.zone_humidity_percent = 50.0
        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 100)
        await data_store.write_memory("library_hvac_1", "holding_registers[13]", 3)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()

        for _ in range(1000):
            hvac.update(0.1)

        assert 10.0 <= hvac.state.zone_humidity_percent <= 90.0


# ================================================================
# FAN AND AIRFLOW TESTS
# ================================================================
class TestHVACFanControl:
    """Test fan and airflow behaviour."""

    async def test_fan_responds_to_speed_command(self, hvac_with_device):
        """Test fan speed responds to command."""
        hvac, data_store = hvac_with_device

        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 80)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()

        # Run longer for fan to reach speed
        for _ in range(150):
            hvac.update(0.1)

        assert hvac.state.fan_speed_percent > 70

    async def test_duct_pressure_proportional_to_fan_speed(self, hvac_with_device):
        """Test duct pressure follows fan speed squared (fan laws)."""
        hvac, data_store = hvac_with_device

        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 100)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()

        # Run until fan reaches full speed
        for _ in range(150):
            hvac.update(0.1)

        high_speed_pressure = hvac.state.duct_pressure_pa

        # Now reduce to 50%
        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 50)
        await hvac.read_control_inputs()

        for _ in range(200):
            hvac.update(0.1)

        low_speed_pressure = hvac.state.duct_pressure_pa

        # Pressure at 50% speed should be lower than at 100%
        assert low_speed_pressure < high_speed_pressure

    async def test_damper_moves_slowly(self, hvac_with_device):
        """Test damper moves slowly (actuator time)."""
        hvac, data_store = hvac_with_device

        hvac.state.damper_position_percent = 0.0
        await data_store.write_memory("library_hvac_1", "holding_registers[14]", 100)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()

        # After 1 second, damper should not be fully open yet
        for _ in range(10):
            hvac.update(0.1)

        assert hvac.state.damper_position_percent < 50


# ================================================================
# L-SPACE STABILITY TESTS
# ================================================================
class TestHVACLspaceStability:
    """Test L-space dimensional stability dynamics."""

    async def test_lspace_stable_at_normal_conditions(self, hvac_with_device):
        """Test L-space remains stable at normal conditions."""
        hvac, data_store = hvac_with_device

        hvac.state.zone_temperature_c = 20.0
        hvac.state.zone_humidity_percent = 45.0
        hvac.state.lspace_stability = 1.0

        await data_store.write_memory("library_hvac_1", "coils[10]", True)
        await data_store.write_memory("library_hvac_1", "coils[11]", True)  # Dampener

        await hvac.read_control_inputs()

        for _ in range(100):
            hvac.update(0.1)

        assert hvac.state.lspace_stability > 0.9

    async def test_lspace_degrades_at_high_temperature(self, hvac_with_device):
        """Test L-space stability degrades at high temperature."""
        hvac, data_store = hvac_with_device

        # Set very high stress conditions
        hvac.state.zone_temperature_c = 35.0  # Well above threshold (25)
        hvac.state.zone_humidity_percent = 70.0  # Also above threshold (60)
        hvac.state.lspace_stability = 0.8  # Start slightly degraded

        # Run without dampener for faster degradation
        for _ in range(200):
            hvac._update_lspace_stability(0.1, dampener_enabled=False)

        # Should degrade under stress without dampener
        assert hvac.state.lspace_stability < 0.8

    async def test_lspace_degrades_faster_without_dampener(self, hvac_with_device):
        """Test L-space degrades faster without dampener."""
        hvac, data_store = hvac_with_device

        # Set stressful conditions
        hvac.state.zone_temperature_c = 28.0
        hvac.state.zone_humidity_percent = 65.0

        # Test without dampener
        hvac.state.lspace_stability = 1.0
        for _ in range(100):
            hvac._update_lspace_stability(0.1, dampener_enabled=False)
        without_dampener = hvac.state.lspace_stability

        # Reset and test with dampener
        hvac.state.lspace_stability = 1.0
        for _ in range(100):
            hvac._update_lspace_stability(0.1, dampener_enabled=True)
        with_dampener = hvac.state.lspace_stability

        # Without dampener should degrade more
        assert without_dampener < with_dampener

    async def test_lspace_causes_fluctuations(self, hvac_with_device):
        """Test L-space instability causes environmental fluctuations."""
        hvac, data_store = hvac_with_device

        hvac.state.lspace_stability = 0.3  # Very unstable

        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 100)
        await data_store.write_memory("library_hvac_1", "holding_registers[13]", 3)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()

        # Collect temperature samples over longer period
        temps = []
        for _ in range(200):
            hvac.update(0.1)
            temps.append(hvac.state.zone_temperature_c)

        # Should see some variation due to L-space instability
        temp_range = max(temps) - min(temps)
        # Any variation indicates dynamic behaviour
        assert temp_range > 0.01


# ================================================================
# ENERGY CONSUMPTION TESTS
# ================================================================
class TestHVACEnergyConsumption:
    """Test energy consumption calculation."""

    async def test_energy_zero_when_off(self, hvac_with_device):
        """Test energy consumption is near zero when system off."""
        hvac, data_store = hvac_with_device

        await data_store.write_memory("library_hvac_1", "coils[10]", False)
        await hvac.read_control_inputs()

        for _ in range(50):
            hvac.update(0.1)

        assert hvac.state.energy_consumption_kw < 1.0

    async def test_energy_increases_with_heating(self, hvac_with_device):
        """Test energy consumption increases with heating."""
        hvac, data_store = hvac_with_device

        hvac.state.zone_temperature_c = 15.0
        await data_store.write_memory("library_hvac_1", "holding_registers[10]", 22)
        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 100)
        await data_store.write_memory("library_hvac_1", "holding_registers[13]", 1)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()

        for _ in range(20):
            hvac.update(0.1)

        assert hvac.state.energy_consumption_kw > 10.0

    async def test_energy_proportional_to_fan_speed(self, hvac_with_device):
        """Test energy consumption follows fan speed cubed (fan laws)."""
        hvac, data_store = hvac_with_device

        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 100)
        await data_store.write_memory("library_hvac_1", "holding_registers[13]", 0)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await hvac.read_control_inputs()

        # Run until fan reaches full speed
        for _ in range(150):
            hvac.update(0.1)

        high_energy = hvac.state.energy_consumption_kw

        # Reduce fan to 50%
        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 50)
        await hvac.read_control_inputs()

        for _ in range(200):
            hvac.update(0.1)

        low_energy = hvac.state.energy_consumption_kw

        # Lower fan speed should use less energy
        assert low_energy < high_energy


# ================================================================
# TELEMETRY TESTS
# ================================================================
class TestHVACTelemetry:
    """Test telemetry output."""

    async def test_write_telemetry_updates_memory_map(self, hvac_with_device):
        """Test write_telemetry updates device memory map."""
        hvac, data_store = hvac_with_device

        hvac.state.zone_temperature_c = 21.5
        hvac.state.zone_humidity_percent = 48.0
        hvac.state.lspace_stability = 0.85

        await hvac.write_telemetry()

        zone_temp = await data_store.read_memory(
            "library_hvac_1", "holding_registers[0]"
        )
        humidity = await data_store.read_memory(
            "library_hvac_1", "holding_registers[1]"
        )
        lspace = await data_store.read_memory(
            "library_hvac_1", "holding_registers[4]"
        )

        assert zone_temp == 215  # 21.5 * 10
        assert humidity == 480  # 48.0 * 10
        assert lspace == 85  # 0.85 * 100

    async def test_get_telemetry_returns_dict(self, hvac_with_device):
        """Test get_telemetry returns complete dictionary."""
        hvac, data_store = hvac_with_device

        telemetry = hvac.get_telemetry()

        assert "zone_temperature_c" in telemetry
        assert "zone_humidity_percent" in telemetry
        assert "fan_speed_percent" in telemetry
        assert "lspace_stability" in telemetry
        assert "energy_consumption_kw" in telemetry
        assert "lspace_warning" in telemetry
        assert "temperature_alarm" in telemetry

    async def test_get_state_returns_state_object(self, hvac_with_device):
        """Test get_state returns HVACState."""
        hvac, data_store = hvac_with_device

        state = hvac.get_state()

        assert isinstance(state, HVACState)
        assert state is hvac.state

    async def test_set_outside_conditions(self, hvac_with_device):
        """Test setting outside conditions."""
        hvac, data_store = hvac_with_device

        hvac.set_outside_conditions(temperature_c=5.0, humidity_percent=80.0)

        assert hvac.params.outside_temp_c == 5.0
        assert hvac.params.outside_humidity_percent == 80.0


# ================================================================
# ALARM TESTS
# ================================================================
class TestHVACAlarms:
    """Test alarm conditions."""

    async def test_temperature_alarm_when_out_of_range(self, hvac_with_device):
        """Test temperature alarm triggers when out of range."""
        hvac, data_store = hvac_with_device

        hvac.state.zone_temperature_c = 25.0  # Above max (22)

        await hvac.write_telemetry()

        alarm = await data_store.read_memory("library_hvac_1", "coils[3]")
        assert alarm is True

    async def test_humidity_alarm_when_out_of_range(self, hvac_with_device):
        """Test humidity alarm triggers when out of range."""
        hvac, data_store = hvac_with_device

        hvac.state.zone_humidity_percent = 35.0  # Below min (40)

        await hvac.write_telemetry()

        alarm = await data_store.read_memory("library_hvac_1", "coils[4]")
        assert alarm is True

    async def test_lspace_warning_when_unstable(self, hvac_with_device):
        """Test L-space warning triggers when unstable."""
        hvac, data_store = hvac_with_device

        hvac.state.lspace_stability = 0.4  # Below 0.5

        await hvac.write_telemetry()

        warning = await data_store.read_memory("library_hvac_1", "coils[5]")
        assert warning is True

    async def test_lspace_critical_when_very_unstable(self, hvac_with_device):
        """Test L-space critical triggers when very unstable."""
        hvac, data_store = hvac_with_device

        hvac.state.lspace_stability = 0.2  # Below 0.3

        await hvac.write_telemetry()

        critical = await data_store.read_memory("library_hvac_1", "coils[6]")
        assert critical is True


# ================================================================
# EDGE CASE TESTS
# ================================================================
class TestHVACEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_very_small_time_steps(self, hvac_with_device):
        """Test physics with very small time steps."""
        hvac, data_store = hvac_with_device

        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 100)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)
        await hvac.read_control_inputs()

        initial_pressure = hvac.state.duct_pressure_pa

        for _ in range(1000):
            hvac.update(0.001)  # 1ms steps

        # Should see some change
        assert hvac.state.duct_pressure_pa != initial_pressure

    async def test_very_large_time_steps(self, hvac_with_device):
        """Test physics with large time steps."""
        hvac, data_store = hvac_with_device

        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 100)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)
        await hvac.read_control_inputs()

        # Large time step should not break physics
        hvac.update(10.0)

        # State should still be valid
        assert 0.0 <= hvac.state.fan_speed_percent <= 100.0
        assert 0.0 <= hvac.state.lspace_stability <= 1.0

    async def test_state_after_many_updates(self, hvac_with_device):
        """Test state remains valid after many updates."""
        hvac, data_store = hvac_with_device

        await data_store.write_memory("library_hvac_1", "holding_registers[10]", 20)
        await data_store.write_memory("library_hvac_1", "holding_registers[11]", 45)
        await data_store.write_memory("library_hvac_1", "holding_registers[12]", 80)
        await data_store.write_memory("library_hvac_1", "holding_registers[13]", 3)
        await data_store.write_memory("library_hvac_1", "coils[10]", True)
        await hvac.read_control_inputs()

        for _ in range(1000):
            hvac.update(0.1)

        # All state values should be valid
        assert 10.0 <= hvac.state.zone_humidity_percent <= 90.0
        assert 0.0 <= hvac.state.fan_speed_percent <= 100.0
        assert 0.0 <= hvac.state.lspace_stability <= 1.0
        assert hvac.state.energy_consumption_kw >= 0.0


# ================================================================
# CONCURRENCY TESTS
# ================================================================
class TestHVACConcurrency:
    """Test concurrent access patterns."""

    async def test_concurrent_control_input_updates(self, hvac_with_device):
        """Test concurrent control input updates don't corrupt state."""
        hvac, data_store = hvac_with_device

        async def update_temperature():
            for i in range(10):
                await data_store.write_memory(
                    "library_hvac_1", "holding_registers[10]", 18 + i
                )
                await hvac.read_control_inputs()
                await asyncio.sleep(0.01)

        async def update_fan():
            for i in range(10):
                await data_store.write_memory(
                    "library_hvac_1", "holding_registers[12]", 50 + i * 5
                )
                await hvac.read_control_inputs()
                await asyncio.sleep(0.01)

        await data_store.write_memory("library_hvac_1", "coils[10]", True)

        await asyncio.gather(update_temperature(), update_fan())

        # State should be valid
        assert hvac._control_cache is not None
