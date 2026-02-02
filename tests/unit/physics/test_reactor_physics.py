# tests/unit/physics/test_reactor_physics.py
"""Comprehensive tests for ReactorPhysics component.

This is Level 3 in our dependency tree - ReactorPhysics depends on:
- DataStore (Level 2) - uses REAL DataStore
- SystemState (Level 1) - uses REAL SystemState (via DataStore)
- SimulationTime (Level 0) - uses REAL SimulationTime

Test Coverage:
- Initialisation and configuration
- Control input reading and caching
- Physics updates (temperature, pressure, reaction rate)
- Thaumic field stability dynamics
- Safety systems (SCRAM, containment)
- Damage accumulation from overtemperature
- Telemetry writing to memory map
- Edge cases and error handling
"""

import asyncio

import pytest

from components.physics.reactor_physics import (
    ReactorParameters,
    ReactorPhysics,
    ReactorState,
)
from components.state.data_store import DataStore
from components.state.system_state import SystemState


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
async def reactor_with_device():
    """Create ReactorPhysics with registered device in DataStore."""
    system_state = SystemState()
    data_store = DataStore(system_state)

    await data_store.register_device(
        device_name="reactor_plc_1",
        device_type="reactor_plc",
        device_id=1,
        protocols=["s7"],
    )

    reactor = ReactorPhysics("reactor_plc_1", data_store)
    await reactor.initialise()

    return reactor, data_store


@pytest.fixture
def custom_params():
    """Factory for custom reactor parameters."""

    def _create(**kwargs):
        return ReactorParameters(**kwargs)

    return _create


# ================================================================
# INITIALISATION TESTS
# ================================================================
class TestReactorPhysicsInitialisation:
    """Test ReactorPhysics initialisation."""

    def test_initialisation_with_defaults(self):
        """Test creating ReactorPhysics with default parameters."""
        system_state = SystemState()
        data_store = DataStore(system_state)

        reactor = ReactorPhysics("reactor_plc_1", data_store)

        assert reactor.device_name == "reactor_plc_1"
        assert reactor.data_store is data_store
        assert reactor.params.rated_power_mw == 25.0
        assert reactor.params.rated_temperature_c == 350.0
        assert not reactor._initialised

    def test_initialisation_with_custom_params(self, custom_params):
        """Test creating ReactorPhysics with custom parameters."""
        system_state = SystemState()
        data_store = DataStore(system_state)

        params = custom_params(
            rated_power_mw=50.0,
            rated_temperature_c=400.0,
            max_safe_temperature_c=450.0,
        )
        reactor = ReactorPhysics("reactor_plc_1", data_store, params)

        assert reactor.params.rated_power_mw == 50.0
        assert reactor.params.rated_temperature_c == 400.0
        assert reactor.params.max_safe_temperature_c == 450.0

    def test_initialisation_empty_name_raises(self):
        """Test that empty device name raises ValueError."""
        system_state = SystemState()
        data_store = DataStore(system_state)

        with pytest.raises(ValueError, match="device_name cannot be empty"):
            ReactorPhysics("", data_store)

    async def test_initialise_without_device_raises(self):
        """Test initialise raises if device not registered."""
        system_state = SystemState()
        data_store = DataStore(system_state)

        reactor = ReactorPhysics("nonexistent_device", data_store)

        with pytest.raises(RuntimeError, match="not found"):
            await reactor.initialise()

    async def test_initialise_writes_initial_state(self, reactor_with_device):
        """Test initialise writes initial telemetry to memory map."""
        reactor, data_store = reactor_with_device

        # Check initial temperature was written
        core_temp = await data_store.read_memory(
            "reactor_plc_1", "holding_registers[0]"
        )
        assert core_temp == 25  # Initial 25°C


# ================================================================
# CONTROL INPUT TESTS
# ================================================================
class TestReactorPhysicsControlInputs:
    """Test control input reading."""

    async def test_read_control_inputs_populates_cache(self, reactor_with_device):
        """Test reading control inputs from DataStore."""
        reactor, data_store = reactor_with_device

        # Set control values
        await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 75)
        await data_store.write_memory("reactor_plc_1", "holding_registers[11]", 100)
        await data_store.write_memory("reactor_plc_1", "coils[10]", False)

        await reactor.read_control_inputs()

        assert reactor._control_cache["power_setpoint_percent"] == 75.0
        assert reactor._control_cache["coolant_pump_speed"] == 100.0
        assert reactor._control_cache["emergency_shutdown"] is False

    async def test_read_control_inputs_handles_missing_values(
        self, reactor_with_device
    ):
        """Test reading control inputs with missing values uses defaults."""
        reactor, data_store = reactor_with_device

        await reactor.read_control_inputs()

        assert reactor._control_cache["power_setpoint_percent"] == 0.0
        assert reactor._control_cache["emergency_shutdown"] is False


# ================================================================
# PHYSICS UPDATE TESTS
# ================================================================
class TestReactorPhysicsUpdates:
    """Test physics update behaviour."""

    async def test_update_before_initialise_raises(self):
        """Test update raises if not initialised."""
        system_state = SystemState()
        data_store = DataStore(system_state)

        reactor = ReactorPhysics("reactor_plc_1", data_store)

        with pytest.raises(RuntimeError, match="not initialised"):
            reactor.update(0.1)

    async def test_update_with_zero_dt_skipped(self, reactor_with_device):
        """Test update with zero time delta is skipped."""
        reactor, data_store = reactor_with_device
        initial_temp = reactor.state.core_temperature_c

        reactor.update(0.0)

        assert reactor.state.core_temperature_c == initial_temp

    async def test_update_with_negative_dt_skipped(self, reactor_with_device):
        """Test update with negative time delta is skipped."""
        reactor, data_store = reactor_with_device
        initial_temp = reactor.state.core_temperature_c

        reactor.update(-1.0)

        assert reactor.state.core_temperature_c == initial_temp


# ================================================================
# TEMPERATURE DYNAMICS TESTS
# ================================================================
class TestReactorTemperatureDynamics:
    """Test temperature physics behaviour."""

    async def test_temperature_rises_with_reaction(self, reactor_with_device):
        """Test temperature increases when reaction is active."""
        reactor, data_store = reactor_with_device

        # Set power and reduced cooling
        await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 100)
        await data_store.write_memory("reactor_plc_1", "holding_registers[11]", 20)
        await data_store.write_memory("reactor_plc_1", "holding_registers[12]", 100)

        await reactor.read_control_inputs()
        initial_temp = reactor.state.core_temperature_c

        # Run for several seconds
        for _ in range(50):
            reactor.update(0.1)

        assert reactor.state.core_temperature_c > initial_temp

    async def test_temperature_stabilises_with_cooling(self, reactor_with_device):
        """Test temperature stabilises with adequate cooling."""
        reactor, data_store = reactor_with_device

        # Set moderate power with full cooling
        await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 50)
        await data_store.write_memory("reactor_plc_1", "holding_registers[11]", 100)
        await data_store.write_memory("reactor_plc_1", "holding_registers[12]", 50)

        await reactor.read_control_inputs()

        # Run until equilibrium
        for _ in range(200):
            reactor.update(0.1)

        temp1 = reactor.state.core_temperature_c

        # Run more - should be stable
        for _ in range(100):
            reactor.update(0.1)

        temp2 = reactor.state.core_temperature_c

        # Temperature should be relatively stable
        assert abs(temp2 - temp1) < 5.0

    async def test_coolant_temperature_tracks_core(self, reactor_with_device):
        """Test coolant temperature follows core temperature."""
        reactor, data_store = reactor_with_device

        # Heat up the reactor
        await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 100)
        await data_store.write_memory("reactor_plc_1", "holding_registers[11]", 50)
        await data_store.write_memory("reactor_plc_1", "holding_registers[12]", 100)

        await reactor.read_control_inputs()

        for _ in range(100):
            reactor.update(0.1)

        # Coolant should be warmer than ambient but cooler than core
        assert reactor.state.coolant_temperature_c > 25.0
        assert reactor.state.coolant_temperature_c < reactor.state.core_temperature_c


# ================================================================
# PRESSURE DYNAMICS TESTS
# ================================================================
class TestReactorPressureDynamics:
    """Test pressure physics behaviour."""

    async def test_pressure_increases_with_temperature(self, reactor_with_device):
        """Test vessel pressure rises with temperature."""
        reactor, data_store = reactor_with_device

        initial_pressure = reactor.state.vessel_pressure_bar

        # Heat up the reactor
        await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 100)
        await data_store.write_memory("reactor_plc_1", "holding_registers[11]", 20)
        await data_store.write_memory("reactor_plc_1", "holding_registers[12]", 100)

        await reactor.read_control_inputs()

        for _ in range(100):
            reactor.update(0.1)

        assert reactor.state.vessel_pressure_bar > initial_pressure


# ================================================================
# REACTION RATE TESTS
# ================================================================
class TestReactorReactionRate:
    """Test reaction rate dynamics."""

    async def test_reaction_rate_follows_setpoint(self, reactor_with_device):
        """Test reaction rate approaches power setpoint."""
        reactor, data_store = reactor_with_device

        await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 75)
        await data_store.write_memory("reactor_plc_1", "holding_registers[12]", 100)

        await reactor.read_control_inputs()

        # Run longer to allow reaction to develop
        for _ in range(100):
            reactor.update(0.1)

        # Reaction rate should be approaching 75%
        assert reactor.state.reaction_rate > 0.3

    async def test_control_rods_limit_reaction(self, reactor_with_device):
        """Test control rods limit maximum reaction rate."""
        reactor, data_store = reactor_with_device

        # High power setpoint but rods only 30% withdrawn
        await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 100)
        await data_store.write_memory("reactor_plc_1", "holding_registers[12]", 30)

        await reactor.read_control_inputs()

        for _ in range(50):
            reactor.update(0.1)

        # Reaction rate should be limited by control rods
        assert reactor.state.reaction_rate <= 0.35


# ================================================================
# THAUMIC FIELD TESTS
# ================================================================
class TestReactorThaumicField:
    """Test thaumic field stability dynamics."""

    async def test_thaumic_field_stable_at_normal_operation(self, reactor_with_device):
        """Test thaumic field remains stable at normal conditions."""
        reactor, data_store = reactor_with_device

        # Moderate power with dampener enabled
        await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 50)
        await data_store.write_memory("reactor_plc_1", "holding_registers[11]", 100)
        await data_store.write_memory("reactor_plc_1", "holding_registers[12]", 50)
        await data_store.write_memory("reactor_plc_1", "coils[11]", True)

        await reactor.read_control_inputs()

        for _ in range(100):
            reactor.update(0.1)

        assert reactor.state.thaumic_field_strength > 0.8

    async def test_thaumic_field_degrades_without_dampener(self, reactor_with_device):
        """Test thaumic field degrades faster without dampener."""
        reactor, data_store = reactor_with_device

        # Force high stress conditions - push temperature above rated
        reactor.state.core_temperature_c = 400.0  # Above rated (350)
        reactor.state.reaction_rate = 1.2  # High reaction

        await data_store.write_memory(
            "reactor_plc_1", "coils[11]", False
        )  # No dampener

        await reactor.read_control_inputs()

        initial_thaumic = reactor.state.thaumic_field_strength

        for _ in range(100):
            reactor._update_thaumic_field(0.1, dampener_enabled=False)

        # Thaumic field should have degraded
        assert reactor.state.thaumic_field_strength < initial_thaumic

    async def test_thaumic_instability_damages_containment(self, reactor_with_device):
        """Test severe thaumic instability damages containment."""
        reactor, data_store = reactor_with_device

        # Force thaumic instability
        reactor.state.thaumic_field_strength = 0.2
        reactor.state.containment_integrity = 1.0

        # High stress conditions
        await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 150)
        await data_store.write_memory("reactor_plc_1", "holding_registers[12]", 100)
        await data_store.write_memory("reactor_plc_1", "coils[11]", False)

        await reactor.read_control_inputs()

        for _ in range(100):
            reactor.update(0.1)

        # Containment should be damaged
        assert reactor.state.containment_integrity < 1.0


# ================================================================
# SAFETY SYSTEM TESTS
# ================================================================
class TestReactorSafetySystems:
    """Test reactor safety systems."""

    async def test_emergency_shutdown_stops_reaction(self, reactor_with_device):
        """Test emergency shutdown (SCRAM) stops reaction."""
        reactor, data_store = reactor_with_device

        # Force reactor to be running at high power
        reactor.state.reaction_rate = 0.8
        reactor.state.core_temperature_c = 300.0

        # Trigger SCRAM
        await data_store.write_memory("reactor_plc_1", "coils[10]", True)
        await reactor.read_control_inputs()

        initial_rate = reactor.state.reaction_rate

        for _ in range(100):
            reactor.update(0.1)

        # Reaction should be significantly reduced (SCRAM has ~2s half-life)
        assert reactor.state.reaction_rate < initial_rate * 0.5
        assert reactor._scram_active

    async def test_auto_scram_on_critical_temperature(self, reactor_with_device):
        """Test automatic SCRAM triggers on critical temperature."""
        reactor, data_store = reactor_with_device

        # Force critical temperature
        reactor.state.core_temperature_c = 500.0  # Above critical

        await reactor.read_control_inputs()
        reactor.update(0.1)

        assert reactor._scram_active

    async def test_auto_scram_on_containment_failure(self, reactor_with_device):
        """Test automatic SCRAM triggers on containment failure."""
        reactor, data_store = reactor_with_device

        # Force containment failure
        reactor.state.containment_integrity = 0.4  # Below threshold

        await reactor.read_control_inputs()
        reactor.update(0.1)

        assert reactor._scram_active

    async def test_scram_reset_requires_safe_conditions(self, reactor_with_device):
        """Test SCRAM reset only works when conditions are safe."""
        reactor, data_store = reactor_with_device

        reactor._scram_active = True
        reactor.state.core_temperature_c = 400.0  # Too hot

        result = reactor.reset_scram()

        assert result is False
        assert reactor._scram_active

    async def test_scram_reset_succeeds_when_safe(self, reactor_with_device):
        """Test SCRAM reset succeeds when conditions are safe."""
        reactor, data_store = reactor_with_device

        reactor._scram_active = True
        reactor.state.core_temperature_c = 200.0
        reactor.state.thaumic_field_strength = 0.9
        reactor.state.containment_integrity = 0.95

        result = reactor.reset_scram()

        assert result is True
        assert not reactor._scram_active


# ================================================================
# DAMAGE ACCUMULATION TESTS
# ================================================================
class TestReactorDamage:
    """Test damage accumulation from overtemperature."""

    async def test_no_damage_below_max_safe_temperature(self, reactor_with_device):
        """Test no damage accumulates below safe temperature."""
        reactor, data_store = reactor_with_device

        reactor.state.core_temperature_c = 350.0  # Below max safe
        reactor.state.damage_level = 0.0

        for _ in range(100):
            reactor.update(0.1)

        assert reactor.state.damage_level == 0.0

    async def test_damage_accumulates_above_safe_temperature(self, reactor_with_device):
        """Test damage accumulates above safe temperature."""
        reactor, data_store = reactor_with_device

        # Force high temperature
        reactor.state.core_temperature_c = 420.0  # Above max safe (400)
        reactor.state.reaction_rate = 0.5  # Keep reaction going
        reactor.state.damage_level = 0.0

        # Manually update damage (bypass temperature dynamics)
        for _ in range(100):
            reactor._update_damage(0.1)

        assert reactor.state.damage_level > 0.0

    async def test_damage_capped_at_100_percent(self, reactor_with_device):
        """Test damage level is capped at 100%."""
        reactor, data_store = reactor_with_device

        reactor.state.damage_level = 0.99
        reactor.state.core_temperature_c = 500.0

        for _ in range(100):
            reactor._update_damage(0.1)

        assert reactor.state.damage_level == 1.0


# ================================================================
# POWER OUTPUT TESTS
# ================================================================
class TestReactorPowerOutput:
    """Test power output calculation."""

    async def test_power_proportional_to_reaction_rate(self, reactor_with_device):
        """Test power output proportional to reaction rate."""
        reactor, data_store = reactor_with_device

        reactor.state.reaction_rate = 0.5
        reactor.state.core_temperature_c = 300.0  # Normal range

        reactor._update_power_output()

        # Should be about 50% of rated power
        assert 10.0 < reactor.state.power_output_mw < 15.0

    async def test_power_reduced_at_extreme_temperatures(self, reactor_with_device):
        """Test power output reduced at extreme temperatures."""
        reactor, data_store = reactor_with_device

        reactor.state.reaction_rate = 1.0
        reactor.state.core_temperature_c = 450.0  # Above max safe

        reactor._update_power_output()

        # Efficiency drops to 80%
        assert reactor.state.power_output_mw < reactor.params.rated_power_mw


# ================================================================
# TELEMETRY TESTS
# ================================================================
class TestReactorTelemetry:
    """Test telemetry output."""

    async def test_write_telemetry_updates_memory_map(self, reactor_with_device):
        """Test write_telemetry updates device memory map."""
        reactor, data_store = reactor_with_device

        reactor.state.core_temperature_c = 300.0
        reactor.state.vessel_pressure_bar = 100.0
        reactor.state.thaumic_field_strength = 0.9

        await reactor.write_telemetry()

        core_temp = await data_store.read_memory(
            "reactor_plc_1", "holding_registers[0]"
        )
        pressure = await data_store.read_memory("reactor_plc_1", "holding_registers[2]")
        thaumic = await data_store.read_memory("reactor_plc_1", "holding_registers[4]")

        assert core_temp == 300
        assert pressure == 1000  # 100.0 * 10
        assert thaumic == 90  # 0.9 * 100

    async def test_get_telemetry_returns_dict(self, reactor_with_device):
        """Test get_telemetry returns complete dictionary."""
        reactor, data_store = reactor_with_device

        telemetry = reactor.get_telemetry()

        assert "core_temperature_c" in telemetry
        assert "vessel_pressure_bar" in telemetry
        assert "power_output_mw" in telemetry
        assert "thaumic_field_strength" in telemetry
        assert "scram_active" in telemetry
        assert "containment_integrity_percent" in telemetry

    async def test_get_state_returns_state_object(self, reactor_with_device):
        """Test get_state returns ReactorState."""
        reactor, data_store = reactor_with_device

        state = reactor.get_state()

        assert isinstance(state, ReactorState)
        assert state is reactor.state


# ================================================================
# EDGE CASE TESTS
# ================================================================
class TestReactorEdgeCases:
    """Test edge cases and boundary conditions."""

    async def test_very_small_time_steps(self, reactor_with_device):
        """Test physics with very small time steps."""
        reactor, data_store = reactor_with_device

        await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 100)
        await data_store.write_memory("reactor_plc_1", "holding_registers[12]", 100)
        await reactor.read_control_inputs()

        initial_temp = reactor.state.core_temperature_c

        for _ in range(1000):
            reactor.update(0.001)  # 1ms steps

        # Should see some change
        assert reactor.state.core_temperature_c != initial_temp

    async def test_very_large_time_steps(self, reactor_with_device):
        """Test physics with large time steps."""
        reactor, data_store = reactor_with_device

        await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 100)
        await data_store.write_memory("reactor_plc_1", "holding_registers[12]", 100)
        await reactor.read_control_inputs()

        # Large time step should not break physics
        reactor.update(10.0)

        # State should still be valid
        assert reactor.state.core_temperature_c >= 25.0
        assert 0.0 <= reactor.state.reaction_rate <= 1.5

    async def test_state_after_many_updates(self, reactor_with_device):
        """Test state remains valid after many updates."""
        reactor, data_store = reactor_with_device

        await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 75)
        await data_store.write_memory("reactor_plc_1", "holding_registers[11]", 80)
        await data_store.write_memory("reactor_plc_1", "holding_registers[12]", 75)
        await reactor.read_control_inputs()

        for _ in range(1000):
            reactor.update(0.1)

        # All state values should be valid
        assert reactor.state.core_temperature_c >= 25.0
        assert 0.0 <= reactor.state.reaction_rate <= 1.5
        assert 0.0 <= reactor.state.thaumic_field_strength <= 1.0
        assert 0.0 <= reactor.state.containment_integrity <= 1.0
        assert 0.0 <= reactor.state.damage_level <= 1.0


# ================================================================
# CONCURRENCY TESTS
# ================================================================
class TestReactorConcurrency:
    """Test concurrent access patterns."""

    async def test_concurrent_control_input_updates(self, reactor_with_device):
        """Test concurrent control input updates don't corrupt state."""
        reactor, data_store = reactor_with_device

        async def update_power():
            for i in range(10):
                await data_store.write_memory(
                    "reactor_plc_1", "holding_registers[10]", i * 10
                )
                await reactor.read_control_inputs()
                await asyncio.sleep(0.01)

        async def update_coolant():
            for i in range(10):
                await data_store.write_memory(
                    "reactor_plc_1", "holding_registers[11]", 100 - i * 5
                )
                await reactor.read_control_inputs()
                await asyncio.sleep(0.01)

        await asyncio.gather(update_power(), update_coolant())

        # State should be valid
        assert reactor._control_cache is not None
