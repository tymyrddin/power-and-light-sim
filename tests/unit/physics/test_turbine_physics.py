# tests/unit/physics/test_turbine_physics.py
"""Comprehensive tests for TurbinePhysics component.

This is Level 3 in our dependency tree - TurbinePhysics depends on:
- DataStore (Level 2) - uses REAL DataStore
- SystemState (Level 1) - uses REAL SystemState (via DataStore)
- SimulationTime (Level 0) - uses REAL SimulationTime

Test Coverage:
- Initialization and configuration
- Control input reading and caching
- Physics updates (governor, emergency, natural decay)
- State transitions (speed, temperature, vibration, power)
- Damage accumulation from overspeed
- Telemetry writing to memory map
- Edge cases and error handling
- Concurrent access patterns
"""

import asyncio

import pytest

from components.physics.turbine_physics import (
    TurbineParameters,
    TurbinePhysics,
)
from components.state.data_store import DataStore
from components.state.system_state import SystemState


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
async def turbine_with_device():
    """Create TurbinePhysics with registered device in DataStore.

    WHY: Most tests need a fully initialized turbine with device registered.
    """
    system_state = SystemState()
    data_store = DataStore(system_state)

    # Register device
    await data_store.register_device(
        device_name="turbine_plc_1",
        device_type="turbine_plc",
        device_id=1,
        protocols=["modbus"],
    )

    # Create physics engine
    turbine = TurbinePhysics("turbine_plc_1", data_store)
    await turbine.initialise()

    return turbine, data_store


@pytest.fixture
def custom_params():
    """Factory for custom turbine parameters.

    WHY: Some tests need specific turbine configurations.
    """

    def _create(**kwargs):
        """Create TurbineParameters with custom values."""
        return TurbineParameters(**kwargs)

    return _create


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestTurbinePhysicsInitialization:
    """Test TurbinePhysics initialization."""

    def test_initialization_with_defaults(self):
        """Test creating TurbinePhysics with default parameters.

        WHY: Ensures sensible defaults are set.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        turbine = TurbinePhysics("turbine_plc_1", data_store)

        assert turbine.device_name == "turbine_plc_1"
        assert turbine.data_store is data_store
        assert turbine.params.rated_speed_rpm == 3600
        assert turbine.params.rated_power_mw == 100.0
        assert not turbine._initialised

    def test_initialization_with_custom_params(self, custom_params):
        """Test creating TurbinePhysics with custom parameters.

        WHY: Different turbines have different specifications.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        params = custom_params(rated_speed_rpm=3000, rated_power_mw=150.0)
        turbine = TurbinePhysics("turbine_plc_1", data_store, params)

        assert turbine.params.rated_speed_rpm == 3000
        assert turbine.params.rated_power_mw == 150.0

    def test_initialization_empty_device_name_raises(self):
        """Test that empty device name raises ValueError.

        WHY: Device name is required identifier.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        with pytest.raises(ValueError, match="device_name cannot be empty"):
            TurbinePhysics("", data_store)

    @pytest.mark.asyncio
    async def test_initialise_with_valid_device(self):
        """Test initialise() succeeds when device exists.

        WHY: Initialization must verify device exists in DataStore.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("turbine_plc_1", "turbine_plc", 1, ["modbus"])

        turbine = TurbinePhysics("turbine_plc_1", data_store)
        await turbine.initialise()

        assert turbine._initialised

    @pytest.mark.asyncio
    async def test_initialise_without_device_raises(self):
        """Test initialise() raises when device doesn't exist.

        WHY: Cannot operate on non-existent device.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        turbine = TurbinePhysics("nonexistent", data_store)

        with pytest.raises(RuntimeError, match="device nonexistent not found"):
            await turbine.initialise()

    @pytest.mark.asyncio
    async def test_initialise_writes_initial_telemetry(self, turbine_with_device):
        """Test that initialise() writes initial state to memory map.

        WHY: Device should have initial telemetry values after init.
        """
        turbine, data_store = turbine_with_device

        # Check some initial telemetry values
        rpm = await data_store.read_memory("turbine_plc_1", "holding_registers[0]")
        power = await data_store.read_memory("turbine_plc_1", "holding_registers[5]")
        running = await data_store.read_memory("turbine_plc_1", "coils[0]")

        assert rpm == 0  # Initial speed is 0
        assert power == 0  # Initial power is 0
        assert running is False  # Not running initially

    @pytest.mark.asyncio
    async def test_state_initialized_to_zero(self, turbine_with_device):
        """Test that turbine state starts at zero values.

        WHY: New turbine should be at rest.
        """
        turbine, _ = turbine_with_device

        state = turbine.get_state()
        assert state.shaft_speed_rpm == 0.0
        assert state.power_output_mw == 0.0
        assert state.steam_pressure_psi == 0.0
        assert state.bearing_temperature_c == 21.0  # Ambient (21°C = 70°F)
        assert state.vibration_mils == 0.0
        assert state.cumulative_overspeed_time == 0.0
        assert state.damage_level == 0.0


# ================================================================
# CONTROL INPUT TESTS
# ================================================================
class TestTurbinePhysicsControlInputs:
    """Test control input reading and caching."""

    @pytest.mark.asyncio
    async def test_read_control_inputs_caches_values(self, turbine_with_device):
        """Test that read_control_inputs() populates control cache.

        WHY: Control cache enables synchronous update() calls.
        """
        turbine, data_store = turbine_with_device

        # Write control inputs
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)
        await data_store.write_memory("turbine_plc_1", "coils[11]", False)

        # Read and cache
        await turbine.read_control_inputs()

        # Verify cache populated
        assert turbine._control_cache["speed_setpoint_rpm"] == 3600.0
        assert turbine._control_cache["governor_enabled"] is True
        assert turbine._control_cache["emergency_trip"] is False

    @pytest.mark.asyncio
    async def test_read_control_inputs_handles_missing_device(self):
        """Test that read_control_inputs() handles missing device gracefully.

        WHY: Should not crash if device is removed after initialization.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("turbine_plc_1", "turbine_plc", 1, ["modbus"])
        turbine = TurbinePhysics("turbine_plc_1", data_store)
        await turbine.initialise()

        # Remove device
        await data_store.unregister_device("turbine_plc_1")

        # Should not crash, should use defaults
        await turbine.read_control_inputs()

        assert turbine._control_cache["speed_setpoint_rpm"] == 0.0
        assert turbine._control_cache["governor_enabled"] is False

    @pytest.mark.asyncio
    async def test_read_control_inputs_with_none_values(self, turbine_with_device):
        """Test handling of None values in control inputs.

        WHY: Uninitialized addresses return None.
        """
        turbine, _ = turbine_with_device

        # Don't write any control inputs, so they're None
        await turbine.read_control_inputs()

        # Should default to safe values
        assert turbine._control_cache["speed_setpoint_rpm"] == 0.0
        assert turbine._control_cache["governor_enabled"] is False
        assert turbine._control_cache["emergency_trip"] is False


# ================================================================
# PHYSICS UPDATE TESTS - GOVERNOR CONTROL
# ================================================================
class TestTurbinePhysicsGovernorControl:
    """Test governor control physics."""

    @pytest.mark.asyncio
    async def test_governor_accelerates_to_setpoint(self, turbine_with_device):
        """Test that governor accelerates turbine to setpoint.

        WHY: Core governor functionality - must reach target speed.
        """
        turbine, data_store = turbine_with_device

        # Set governor control with 3600 RPM setpoint
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        # Update with larger time steps to allow faster acceleration
        for _ in range(50):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)  # 1 second steps instead of 0.1

        # Should be approaching setpoint (within 10%)
        assert turbine.state.shaft_speed_rpm > 3240  # 90% of 3600

    @pytest.mark.asyncio
    async def test_governor_decelerates_to_lower_setpoint(self, turbine_with_device):
        """Test that governor can decelerate to lower setpoint.

        WHY: Governor must control speed in both directions.
        """
        turbine, data_store = turbine_with_device

        # First accelerate to 3600 RPM
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        for _ in range(50):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)

        initial_speed = turbine.state.shaft_speed_rpm
        assert initial_speed > 3200  # Verify we reached high speed

        # Now reduce setpoint to 3000 RPM
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3000)

        for _ in range(20):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)

        # Should be decelerating
        assert turbine.state.shaft_speed_rpm < initial_speed - 100

    @pytest.mark.asyncio
    async def test_governor_maintains_setpoint(self, turbine_with_device):
        """Test that governor maintains steady setpoint.

        WHY: Governor should hold speed once reached.
        """
        turbine, data_store = turbine_with_device

        # Accelerate to setpoint
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        for _ in range(50):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)

        # Record speed
        speed_1 = turbine.state.shaft_speed_rpm

        # Continue running
        for _ in range(20):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)

        speed_2 = turbine.state.shaft_speed_rpm

        # Speed should be stable (within 10% tolerance for proportional control)
        assert abs(speed_2 - speed_1) < 360  # 10% of 3600

    @pytest.mark.asyncio
    async def test_governor_respects_acceleration_rate(self, turbine_with_device):
        """Test that acceleration is limited by max rate.

        WHY: Physical turbines can't accelerate instantly.
        """
        turbine, data_store = turbine_with_device

        # Set very high setpoint
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        # Single update with 1 second
        await turbine.read_control_inputs()
        turbine.update(dt=1.0)

        # Speed increase should not exceed max acceleration rate
        max_possible = turbine.params.acceleration_rate * 1.0
        assert turbine.state.shaft_speed_rpm <= max_possible * 1.1  # 10% tolerance

    @pytest.mark.asyncio
    async def test_governor_clamps_negative_speed(self, turbine_with_device):
        """Test that speed cannot go negative.

        WHY: Physical constraint - turbines don't spin backwards.
        """
        turbine, data_store = turbine_with_device

        # Set zero setpoint with governor enabled
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 0)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        await turbine.read_control_inputs()
        turbine.update(dt=10.0)  # Large time step

        assert turbine.state.shaft_speed_rpm >= 0.0

    @pytest.mark.asyncio
    async def test_governor_disabled_no_acceleration(self, turbine_with_device):
        """Test that disabled governor doesn't accelerate turbine.

        WHY: Governor control must be explicitly enabled.
        """
        turbine, data_store = turbine_with_device

        # Set setpoint but disable governor
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", False)

        await turbine.read_control_inputs()
        turbine.update(dt=1.0)

        # Should remain at zero (or decelerate if it was moving)
        assert turbine.state.shaft_speed_rpm == 0.0


# ================================================================
# PHYSICS UPDATE TESTS - EMERGENCY SHUTDOWN
# ================================================================
class TestTurbinePhysicsEmergencyShutdown:
    """Test emergency trip functionality."""

    @pytest.mark.asyncio
    async def test_emergency_trip_stops_turbine(self, turbine_with_device):
        """Test that emergency trip rapidly stops turbine.

        WHY: Critical safety feature - must stop quickly.
        """
        turbine, data_store = turbine_with_device

        # First spin up turbine
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        for _ in range(50):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)

        running_speed = turbine.state.shaft_speed_rpm
        assert running_speed > 3200  # Verify we reached high speed

        # Trigger emergency trip
        await data_store.write_memory("turbine_plc_1", "coils[11]", True)

        # Run for a bit
        for _ in range(20):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)

        # Should be significantly slower
        assert turbine.state.shaft_speed_rpm < running_speed * 0.9

    @pytest.mark.asyncio
    async def test_emergency_trip_faster_than_natural(self, turbine_with_device):
        """Test that emergency deceleration is faster than natural decay.

        WHY: Emergency braking must be more aggressive than coasting.
        """
        turbine, data_store = turbine_with_device

        # Spin up to speed
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)
        for _ in range(50):
            await turbine.read_control_inputs()
            turbine.update(dt=0.1)

        # Record initial speed
        initial_speed = turbine.state.shaft_speed_rpm

        # Emergency trip
        await data_store.write_memory("turbine_plc_1", "coils[11]", True)
        await data_store.write_memory("turbine_plc_1", "coils[10]", False)

        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        emergency_speed = turbine.state.shaft_speed_rpm
        emergency_delta = initial_speed - emergency_speed

        # Reset and test natural deceleration
        turbine.state.shaft_speed_rpm = initial_speed
        await data_store.write_memory("turbine_plc_1", "coils[11]", False)

        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        natural_speed = turbine.state.shaft_speed_rpm
        natural_delta = initial_speed - natural_speed

        # Emergency should decelerate faster
        assert emergency_delta > natural_delta

    @pytest.mark.asyncio
    async def test_emergency_trip_cools_temperatures(self, turbine_with_device):
        """Test that emergency shutdown accelerates cooling.

        WHY: Temperature management during emergency stop.
        """
        turbine, data_store = turbine_with_device

        # Run turbine at rated speed first (40s to reach 3600 RPM + warm up)
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        for _ in range(400):  # 40 seconds to reach speed and heat up
            await turbine.read_control_inputs()
            turbine.update(dt=0.1)

        hot_temp = turbine.state.bearing_temperature_c
        assert hot_temp > 75  # Should be hot at rated speed (3600 RPM)

        # Emergency trip
        await data_store.write_memory("turbine_plc_1", "coils[11]", True)

        for _ in range(50):
            await turbine.read_control_inputs()
            turbine.update(dt=0.1)

        # Temperature should be decreasing
        assert turbine.state.bearing_temperature_c < hot_temp


# ================================================================
# PHYSICS UPDATE TESTS - NATURAL DECELERATION
# ================================================================
class TestTurbinePhysicsNaturalDeceleration:
    """Test natural deceleration without governor."""

    @pytest.mark.asyncio
    async def test_natural_deceleration_from_speed(self, turbine_with_device):
        """Test that turbine naturally decelerates when governor disabled.

        WHY: Friction and windage cause spindown.
        """
        turbine, data_store = turbine_with_device

        # Manually set speed
        turbine.state.shaft_speed_rpm = 3600.0

        # Disable governor
        await data_store.write_memory("turbine_plc_1", "coils[10]", False)

        # Run for a bit
        for _ in range(10):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)

        # Should be decelerating
        assert turbine.state.shaft_speed_rpm < 3600.0

    @pytest.mark.asyncio
    async def test_natural_deceleration_to_zero(self, turbine_with_device):
        """Test that natural deceleration eventually reaches zero.

        WHY: Turbine should stop completely without power input.
        """
        turbine, data_store = turbine_with_device

        # Start at moderate speed
        turbine.state.shaft_speed_rpm = 1000.0

        # Disable governor
        await data_store.write_memory("turbine_plc_1", "coils[10]", False)

        # Run until stopped (with timeout)
        for _ in range(100):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)
            if turbine.state.shaft_speed_rpm == 0.0:
                break

        assert turbine.state.shaft_speed_rpm == 0.0

    @pytest.mark.asyncio
    async def test_natural_deceleration_rate_consistent(self, turbine_with_device):
        """Test that deceleration rate is consistent.

        WHY: Physics should be predictable.
        """
        turbine, data_store = turbine_with_device

        turbine.state.shaft_speed_rpm = 3600.0
        await data_store.write_memory("turbine_plc_1", "coils[10]", False)

        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        delta_1 = 3600.0 - turbine.state.shaft_speed_rpm

        turbine.state.shaft_speed_rpm = 3600.0
        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        delta_2 = 3600.0 - turbine.state.shaft_speed_rpm

        # Should be approximately the same
        assert abs(delta_1 - delta_2) < 1.0


# ================================================================
# TEMPERATURE DYNAMICS TESTS
# ================================================================
class TestTurbinePhysicsTemperatures:
    """Test temperature dynamics."""

    @pytest.mark.asyncio
    async def test_temperature_increases_with_speed(self, turbine_with_device):
        """Test that bearing temperature increases with speed.

        WHY: Friction increases with speed.
        """
        turbine, data_store = turbine_with_device

        initial_temp = turbine.state.bearing_temperature_c

        # Spin up turbine
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        for _ in range(100):
            await turbine.read_control_inputs()
            turbine.update(dt=0.1)

        # Temperature should have increased
        assert turbine.state.bearing_temperature_c > initial_temp

    @pytest.mark.asyncio
    async def test_steam_temperature_correlates_with_load(self, turbine_with_device):
        """Test that steam temperature increases with load.

        WHY: More steam flow means higher temperatures.
        """
        turbine, data_store = turbine_with_device

        # Low speed
        turbine.state.shaft_speed_rpm = 500.0
        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        low_speed_temp = turbine.state.steam_temperature_c

        # High speed
        turbine.state.shaft_speed_rpm = 3600.0
        for _ in range(50):
            await turbine.read_control_inputs()
            turbine.update(dt=0.1)
        high_speed_temp = turbine.state.steam_temperature_c

        # High speed should have higher steam temperature
        assert high_speed_temp > low_speed_temp

    @pytest.mark.asyncio
    async def test_temperature_thermal_lag(self, turbine_with_device):
        """Test that temperatures have thermal lag.

        WHY: Thermal masses don't change temperature instantly.
        """
        turbine, data_store = turbine_with_device

        # Jump to high speed
        turbine.state.shaft_speed_rpm = 3600.0

        await turbine.read_control_inputs()
        turbine.update(dt=0.1)
        temp_after_short = turbine.state.bearing_temperature_c

        # Continue running
        for _ in range(50):
            await turbine.read_control_inputs()
            turbine.update(dt=0.1)
        temp_after_long = turbine.state.bearing_temperature_c

        # Temperature should still be rising (not instant)
        assert temp_after_long > temp_after_short


# ================================================================
# VIBRATION TESTS
# ================================================================
class TestTurbinePhysicsVibration:
    """Test vibration calculation."""

    @pytest.mark.asyncio
    async def test_vibration_at_rated_speed_is_normal(self, turbine_with_device):
        """Test that vibration is normal at rated speed.

        WHY: Turbines are designed to run smoothly at rated speed.
        """
        turbine, data_store = turbine_with_device

        # Set to rated speed
        turbine.state.shaft_speed_rpm = 3600.0

        await turbine.read_control_inputs()
        turbine.update(dt=1.0)

        # Should be close to normal vibration
        assert (
            turbine.state.vibration_mils <= turbine.params.vibration_normal_mils * 1.5
        )

    @pytest.mark.asyncio
    async def test_vibration_increases_off_rated_speed(self, turbine_with_device):
        """Test that vibration increases when off rated speed.

        WHY: Operating off-design point increases vibration.
        """
        turbine, data_store = turbine_with_device

        # At rated speed
        turbine.state.shaft_speed_rpm = 3600.0
        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        normal_vibration = turbine.state.vibration_mils

        # Off rated speed
        turbine.state.shaft_speed_rpm = 4000.0
        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        high_vibration = turbine.state.vibration_mils

        assert high_vibration > normal_vibration

    @pytest.mark.asyncio
    async def test_vibration_increases_with_damage(self, turbine_with_device):
        """Test that damage amplifies vibration.

        WHY: Damaged turbines vibrate more.
        """
        turbine, data_store = turbine_with_device

        turbine.state.shaft_speed_rpm = 3600.0
        turbine.state.damage_level = 0.0

        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        undamaged_vibration = turbine.state.vibration_mils

        # Add damage
        turbine.state.damage_level = 0.5
        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        damaged_vibration = turbine.state.vibration_mils

        assert damaged_vibration > undamaged_vibration


# ================================================================
# POWER OUTPUT TESTS
# ================================================================
class TestTurbinePhysicsPowerOutput:
    """Test power output calculation."""

    @pytest.mark.asyncio
    async def test_power_zero_below_minimum_speed(self, turbine_with_device):
        """Test that power is zero below minimum stable speed.

        WHY: Turbines need minimum speed to generate power.
        """
        turbine, data_store = turbine_with_device

        # Below 20% of rated speed
        turbine.state.shaft_speed_rpm = 500.0

        await turbine.read_control_inputs()
        turbine.update(dt=1.0)

        assert turbine.state.power_output_mw == 0.0

    @pytest.mark.asyncio
    async def test_power_increases_with_speed(self, turbine_with_device):
        """Test that power output increases with speed.

        WHY: Power proportional to speed up to rated.
        """
        turbine, data_store = turbine_with_device

        # Low speed
        turbine.state.shaft_speed_rpm = 1800.0
        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        low_power = turbine.state.power_output_mw

        # High speed
        turbine.state.shaft_speed_rpm = 3600.0
        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        high_power = turbine.state.power_output_mw

        assert high_power > low_power

    @pytest.mark.asyncio
    async def test_power_at_rated_speed(self, turbine_with_device):
        """Test power output at rated speed.

        WHY: Should produce rated power at rated speed.
        """
        turbine, data_store = turbine_with_device

        turbine.state.shaft_speed_rpm = 3600.0

        await turbine.read_control_inputs()
        turbine.update(dt=1.0)

        # Should be at or near rated power
        assert turbine.state.power_output_mw >= turbine.params.rated_power_mw * 0.95


# ================================================================
# DAMAGE ACCUMULATION TESTS
# ================================================================
class TestTurbinePhysicsDamage:
    """Test overspeed damage accumulation."""

    @pytest.mark.asyncio
    async def test_no_damage_at_rated_speed(self, turbine_with_device):
        """Test that no damage accumulates at rated speed.

        WHY: Normal operation should not cause damage.
        """
        turbine, data_store = turbine_with_device

        turbine.state.shaft_speed_rpm = 3600.0

        for _ in range(100):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)

        assert turbine.state.damage_level == 0.0
        assert turbine.state.cumulative_overspeed_time == 0.0

    @pytest.mark.asyncio
    async def test_damage_accumulates_above_rated_speed(self, turbine_with_device):
        """Test that damage accumulates when running above rated speed.

        WHY: Overspeed operation causes wear and damage.
        """
        turbine, data_store = turbine_with_device

        # Run at 115% of rated speed (above trip point)
        turbine.state.shaft_speed_rpm = 4140.0  # 115% of 3600

        for _ in range(10):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)

        assert turbine.state.damage_level > 0.0
        assert turbine.state.cumulative_overspeed_time > 0.0

    @pytest.mark.asyncio
    async def test_damage_increases_with_overspeed_magnitude(self, turbine_with_device):
        """Test that damage rate increases with overspeed severity.

        WHY: Higher overspeed causes faster damage.
        """
        turbine, data_store = turbine_with_device

        # Moderate overspeed
        turbine.state.shaft_speed_rpm = 4000.0  # 111%
        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        moderate_damage = turbine.state.damage_level

        # Reset
        turbine.state.damage_level = 0.0

        # Severe overspeed
        turbine.state.shaft_speed_rpm = 4320.0  # 120%
        await turbine.read_control_inputs()
        turbine.update(dt=1.0)
        severe_damage = turbine.state.damage_level

        assert severe_damage > moderate_damage

    @pytest.mark.asyncio
    async def test_damage_capped_at_100_percent(self, turbine_with_device):
        """Test that damage cannot exceed 100%.

        WHY: Damage level is normalized to 0.0-1.0 range.
        """
        turbine, data_store = turbine_with_device

        # Extreme overspeed for extended time
        turbine.state.shaft_speed_rpm = 5000.0

        for _ in range(1000):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)

        assert turbine.state.damage_level <= 1.0


# ================================================================
# TELEMETRY WRITING TESTS
# ================================================================
class TestTurbinePhysicsTelemetry:
    """Test telemetry writing to memory map."""

    @pytest.mark.asyncio
    async def test_write_telemetry_updates_memory_map(self, turbine_with_device):
        """Test that write_telemetry() updates device memory map.

        WHY: Telemetry must be accessible via protocol handlers.
        """
        turbine, data_store = turbine_with_device

        # Set some state
        turbine.state.shaft_speed_rpm = 3600.0
        turbine.state.power_output_mw = 100.0

        await turbine.write_telemetry()

        # Read back from memory map
        rpm = await data_store.read_memory("turbine_plc_1", "holding_registers[0]")
        power = await data_store.read_memory("turbine_plc_1", "holding_registers[5]")

        assert rpm == 3600
        assert power == 100

    @pytest.mark.asyncio
    async def test_write_telemetry_coil_status(self, turbine_with_device):
        """Test that digital status coils are written correctly.

        WHY: Coils represent boolean status flags.
        """
        turbine, data_store = turbine_with_device

        # Turbine running
        turbine.state.shaft_speed_rpm = 3600.0
        await turbine.write_telemetry()

        running = await data_store.read_memory("turbine_plc_1", "coils[0]")
        assert running is True

        # Turbine stopped
        turbine.state.shaft_speed_rpm = 0.0
        await turbine.write_telemetry()

        running = await data_store.read_memory("turbine_plc_1", "coils[0]")
        assert running is False

    @pytest.mark.asyncio
    async def test_write_telemetry_overspeed_alarm(self, turbine_with_device):
        """Test overspeed alarm coil.

        WHY: Critical safety alarm must be set correctly.
        """
        turbine, data_store = turbine_with_device

        # Below trip point
        turbine.state.shaft_speed_rpm = 3900.0
        await turbine.write_telemetry()

        overspeed = await data_store.read_memory("turbine_plc_1", "coils[1]")
        assert overspeed is False

        # Above trip point
        turbine.state.shaft_speed_rpm = 4000.0
        await turbine.write_telemetry()

        overspeed = await data_store.read_memory("turbine_plc_1", "coils[1]")
        assert overspeed is True

    @pytest.mark.asyncio
    async def test_get_telemetry_returns_dict(self, turbine_with_device):
        """Test that get_telemetry() returns formatted dictionary.

        WHY: Convenient interface for monitoring.
        """
        turbine, data_store = turbine_with_device

        turbine.state.shaft_speed_rpm = 3600.0
        turbine.state.power_output_mw = 100.0

        telemetry = turbine.get_telemetry()

        assert "shaft_speed_rpm" in telemetry
        assert "power_output_mw" in telemetry
        assert "turbine_running" in telemetry
        assert telemetry["shaft_speed_rpm"] == 3600
        assert telemetry["power_output_mw"] == 100.0


# ================================================================
# UPDATE LIFECYCLE TESTS
# ================================================================
class TestTurbinePhysicsUpdateLifecycle:
    """Test update lifecycle and error handling."""

    @pytest.mark.asyncio
    async def test_update_before_initialise_raises(self):
        """Test that update() raises if not initialized.

        WHY: Must call initialise() before update().
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        turbine = TurbinePhysics("turbine_plc_1", data_store)

        with pytest.raises(RuntimeError, match="not initialised"):
            turbine.update(dt=1.0)

    @pytest.mark.asyncio
    async def test_update_with_zero_dt_skipped(self, turbine_with_device):
        """Test that update with dt=0 is skipped.

        WHY: Zero time delta is meaningless for physics.
        """
        turbine, data_store = turbine_with_device

        turbine.state.shaft_speed_rpm = 3600.0
        initial_speed = turbine.state.shaft_speed_rpm

        await turbine.read_control_inputs()
        turbine.update(dt=0.0)

        # Speed should not have changed
        assert turbine.state.shaft_speed_rpm == initial_speed

    @pytest.mark.asyncio
    async def test_update_with_negative_dt_skipped(self, turbine_with_device):
        """Test that update with negative dt is skipped.

        WHY: Cannot step backwards in time.
        """
        turbine, data_store = turbine_with_device

        turbine.state.shaft_speed_rpm = 3600.0
        initial_speed = turbine.state.shaft_speed_rpm

        await turbine.read_control_inputs()
        turbine.update(dt=-1.0)

        # Speed should not have changed
        assert turbine.state.shaft_speed_rpm == initial_speed

    @pytest.mark.asyncio
    async def test_update_without_read_control_inputs_uses_cache(
        self, turbine_with_device
    ):
        """Test that update() uses cached control inputs.

        WHY: Allows synchronous update() after async read.
        """
        turbine, data_store = turbine_with_device

        # Write controls and read once
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)
        await turbine.read_control_inputs()

        # Now update multiple times without re-reading
        for _ in range(5):
            turbine.update(dt=1.0)

        # Should have accelerated using cached controls
        assert turbine.state.shaft_speed_rpm > 0.0


# ================================================================
# EDGE CASE TESTS
# ================================================================
class TestTurbinePhysicsEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_very_small_time_steps(self, turbine_with_device):
        """Test handling of microsecond-level time steps.

        WHY: High-frequency updates should work correctly.
        """
        turbine, data_store = turbine_with_device

        turbine.state.shaft_speed_rpm = 3600.0
        initial_speed = turbine.state.shaft_speed_rpm

        await turbine.read_control_inputs()
        turbine.update(dt=0.000001)

        # Should have minimal change
        assert abs(turbine.state.shaft_speed_rpm - initial_speed) < 0.01

    @pytest.mark.asyncio
    async def test_very_large_time_steps(self, turbine_with_device):
        """Test handling of large time steps.

        WHY: Must handle variable update rates gracefully.
        """
        turbine, data_store = turbine_with_device

        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        await turbine.read_control_inputs()
        turbine.update(dt=100.0)  # 100 second step

        # Should have made progress toward setpoint
        assert turbine.state.shaft_speed_rpm > 0.0

    @pytest.mark.asyncio
    async def test_extreme_setpoint_values(self, turbine_with_device):
        """Test handling of unrealistic setpoint values.

        WHY: Must handle invalid operator inputs gracefully.
        """
        turbine, data_store = turbine_with_device

        # Negative setpoint should be clamped
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", -1000)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        await turbine.read_control_inputs()
        turbine.update(dt=1.0)

        # Should clamp to zero
        assert turbine.state.shaft_speed_rpm >= 0.0

    @pytest.mark.asyncio
    async def test_state_after_many_updates(self, turbine_with_device):
        """Test state consistency after many update cycles.

        WHY: Long-running simulations must remain stable.
        """
        turbine, data_store = turbine_with_device

        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        # Run for many cycles
        for _ in range(1000):
            await turbine.read_control_inputs()
            turbine.update(dt=0.1)

        # State should be reasonable
        assert 0 <= turbine.state.shaft_speed_rpm <= 4500
        assert 0 <= turbine.state.power_output_mw <= 120
        assert 0 <= turbine.state.damage_level <= 1.0


# ================================================================
# CONCURRENT ACCESS TESTS
# ================================================================
class TestTurbinePhysicsConcurrency:
    """Test concurrent access patterns."""

    @pytest.mark.asyncio
    async def test_concurrent_control_input_updates(self, turbine_with_device):
        """Test concurrent updates to control inputs.

        WHY: Multiple coroutines may write controls simultaneously.
        """
        turbine, data_store = turbine_with_device

        async def update_controls(setpoint: int):
            for _ in range(10):
                await data_store.write_memory(
                    "turbine_plc_1", "holding_registers[10]", setpoint
                )
                await asyncio.sleep(0.001)

        # Multiple coroutines updating controls
        await asyncio.gather(
            update_controls(3000),
            update_controls(3600),
            update_controls(3300),
        )

        # Should complete without errors
        await turbine.read_control_inputs()
        turbine.update(dt=1.0)

    @pytest.mark.asyncio
    async def test_concurrent_physics_updates(self):
        """Test that physics updates from multiple turbines don't interfere.

        WHY: Simulation may have multiple turbine instances.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        # Register multiple devices
        await data_store.register_device("turbine_1", "turbine_plc", 1, ["modbus"])
        await data_store.register_device("turbine_2", "turbine_plc", 2, ["modbus"])

        turbine1 = TurbinePhysics("turbine_1", data_store)
        turbine2 = TurbinePhysics("turbine_2", data_store)

        await turbine1.initialise()
        await turbine2.initialise()

        # Set significantly different setpoints
        await data_store.write_memory("turbine_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_1", "coils[10]", True)
        await data_store.write_memory("turbine_2", "holding_registers[10]", 1800)
        await data_store.write_memory("turbine_2", "coils[10]", True)

        # Update both concurrently with larger time steps
        async def update_turbine(turbine):
            for _ in range(50):
                await turbine.read_control_inputs()
                turbine.update(dt=1.0)
                await turbine.write_telemetry()

        await asyncio.gather(
            update_turbine(turbine1),
            update_turbine(turbine2),
        )

        # Both should have converged to different speeds
        assert (
            abs(turbine1.state.shaft_speed_rpm - turbine2.state.shaft_speed_rpm) > 1200
        )


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestTurbinePhysicsIntegration:
    """Test complete workflows and integration."""

    @pytest.mark.asyncio
    async def test_complete_startup_sequence(self, turbine_with_device):
        """Test realistic turbine startup sequence.

        WHY: Verify complete operational workflow.
        """
        turbine, data_store = turbine_with_device

        # 1. Turbine is initially at rest
        assert turbine.state.shaft_speed_rpm == 0.0

        # 2. Enable governor with low setpoint
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 1000)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        # 3. Accelerate to low speed
        for _ in range(15):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)
            await turbine.write_telemetry()

        assert 900 <= turbine.state.shaft_speed_rpm <= 1100

        # 4. Increase to full speed
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)

        for _ in range(50):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)
            await turbine.write_telemetry()

        assert turbine.state.shaft_speed_rpm > 3200  # Within 10% of target
        assert turbine.state.power_output_mw > 85

    @pytest.mark.asyncio
    async def test_complete_shutdown_sequence(self, turbine_with_device):
        """Test realistic turbine shutdown sequence.

        WHY: Verify complete shutdown workflow.
        """
        turbine, data_store = turbine_with_device

        # 1. Start at full speed
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 3600)
        await data_store.write_memory("turbine_plc_1", "coils[10]", True)

        for _ in range(50):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)

        assert turbine.state.shaft_speed_rpm > 3200  # Verify we reached high speed

        # 2. Reduce to low speed first
        await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 1000)

        for _ in range(30):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)
            await turbine.write_telemetry()

        # 3. Emergency trip to stop
        await data_store.write_memory("turbine_plc_1", "coils[11]", True)

        for _ in range(40):
            await turbine.read_control_inputs()
            turbine.update(dt=1.0)
            await turbine.write_telemetry()

        # Should be stopped or nearly stopped
        assert turbine.state.shaft_speed_rpm < 100

    @pytest.mark.asyncio
    async def test_telemetry_accessible_via_protocols(self, turbine_with_device):
        """Test that telemetry is accessible via protocol-style reads.

        WHY: Protocol handlers need access to turbine state.
        """
        turbine, data_store = turbine_with_device

        # Run turbine
        turbine.state.shaft_speed_rpm = 3600.0
        turbine.state.power_output_mw = 100.0
        turbine.state.bearing_temperature_c = 150.0

        await turbine.write_telemetry()

        # Read via DataStore (simulating protocol handler)
        rpm = await data_store.read_memory("turbine_plc_1", "holding_registers[0]")
        power = await data_store.read_memory("turbine_plc_1", "holding_registers[5]")
        temp = await data_store.read_memory("turbine_plc_1", "holding_registers[3]")
        running = await data_store.read_memory("turbine_plc_1", "coils[0]")

        assert rpm == 3600
        assert power == 100
        assert temp == 150
        assert running is True
