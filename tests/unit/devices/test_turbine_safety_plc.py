# tests/unit/devices/test_turbine_safety_plc.py
"""Tests for TurbineSafetyPLC - Dedicated safety PLC for Hex Steam Turbine.

Tests:
- Initialization with turbine physics
- Safety Instrumented Functions (overspeed, vibration, bearing temp)
- Dual-channel sensor simulation
- 2oo3 voting logic
- Trip and reset operations
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from components.devices.control_zone.safety.base_safety_controller import (
    SafetyIntegrityLevel,
    VotingArchitecture,
)
from components.physics.turbine_physics import TurbineParameters, TurbinePhysics
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


def create_mock_turbine_physics() -> MagicMock:
    """Create a mock TurbinePhysics with test-friendly behaviour."""
    mock = MagicMock(spec=TurbinePhysics)
    mock.device_name = "mock_turbine"

    # Create mock params
    mock.params = MagicMock(spec=TurbineParameters)
    mock.params.rated_speed_rpm = 3600
    mock.params.vibration_critical_mils = 10.0

    # Track values for assertions
    mock.emergency_trip_triggered = False

    mock._telemetry = {
        "shaft_speed_rpm": 3600,
        "vibration_mils": 2.0,
        "bearing_temperature_c": 65,  # Normal operating temp in Celsius (was 150°F ≈ 65°C)
        "trip_active": False,
    }

    def get_telemetry() -> dict:
        return mock._telemetry.copy()

    def trigger_emergency_trip() -> None:
        mock.emergency_trip_triggered = True
        mock._telemetry["trip_active"] = True

    # Wire up the mock methods
    mock.get_telemetry.side_effect = get_telemetry
    mock.trigger_emergency_trip.side_effect = trigger_emergency_trip

    return mock


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
async def clean_simulation_time():
    """Reset SimulationTime singleton."""
    sim_time = SimulationTime()
    await sim_time.reset()
    yield sim_time
    await sim_time.reset()


@pytest.fixture
async def datastore_setup(clean_simulation_time):
    """Create DataStore with SystemState."""
    system_state = SystemState()
    data_store = DataStore(system_state)
    return data_store


@pytest.fixture
def mock_turbine():
    """Create mock turbine physics."""
    return create_mock_turbine_physics()


@pytest.fixture
async def turbine_safety_plc(datastore_setup, mock_turbine):
    """Create TurbineSafetyPLC instance."""
    from components.devices.control_zone.safety.turbine_safety_plc import (
        TurbineSafetyPLC,
    )

    plc = TurbineSafetyPLC(
        device_name="turbine_safety_1",
        device_id=10,
        data_store=datastore_setup,
        turbine_physics=mock_turbine,
        scan_interval=0.01,
    )
    yield plc
    if plc.is_running():
        await plc.stop()


@pytest.fixture
async def started_turbine_safety(turbine_safety_plc):
    """Create and start TurbineSafetyPLC."""
    await turbine_safety_plc.start()
    yield turbine_safety_plc
    if turbine_safety_plc.is_running():
        await turbine_safety_plc.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestTurbineSafetyPLCInitialization:
    """Test TurbineSafetyPLC initialization."""

    def test_init_with_physics(self, datastore_setup, mock_turbine):
        """Test initialization with turbine physics."""
        from components.devices.control_zone.safety.turbine_safety_plc import (
            TurbineSafetyPLC,
        )

        plc = TurbineSafetyPLC(
            device_name="test_turbine_safety",
            device_id=1,
            data_store=datastore_setup,
            turbine_physics=mock_turbine,
        )

        assert plc.turbine_physics == mock_turbine

    def test_default_sil_level(self, turbine_safety_plc):
        """Test default SIL level is SIL2."""
        assert turbine_safety_plc.sil_level == SafetyIntegrityLevel.SIL2

    def test_default_voting_architecture(self, turbine_safety_plc):
        """Test default voting is 2oo3."""
        assert turbine_safety_plc.voting == VotingArchitecture.TWO_OUT_OF_THREE

    def test_device_type(self, turbine_safety_plc):
        """Test device type."""
        assert turbine_safety_plc._device_type() == "turbine_safety_plc"


# ================================================================
# SIF TESTS
# ================================================================
class TestTurbineSafetyPLCSIFs:
    """Test Safety Instrumented Functions."""

    @pytest.mark.asyncio
    async def test_sif_overspeed_normal(self, started_turbine_safety, mock_turbine):
        """Test overspeed SIF under normal conditions."""
        mock_turbine._telemetry["shaft_speed_rpm"] = 3600  # Normal

        await asyncio.sleep(0.03)

        assert started_turbine_safety.safe_state_active is False

    @pytest.mark.asyncio
    async def test_sif_overspeed_trips(self, started_turbine_safety, mock_turbine):
        """Test overspeed SIF trips on high speed."""
        # Set overspeed (>110% of 3600 = 3960)
        mock_turbine._telemetry["shaft_speed_rpm"] = 4200

        await asyncio.sleep(0.05)

        assert started_turbine_safety.safe_state_active is True
        assert mock_turbine.emergency_trip_triggered is True

    @pytest.mark.asyncio
    async def test_sif_vibration_trips(self, started_turbine_safety, mock_turbine):
        """Test vibration SIF trips on high vibration."""
        mock_turbine._telemetry["vibration_mils"] = 15.0  # High vibration

        await asyncio.sleep(0.05)

        assert started_turbine_safety.safe_state_active is True

    @pytest.mark.asyncio
    async def test_sif_bearing_temp_trips(self, started_turbine_safety, mock_turbine):
        """Test bearing temperature SIF trips on high temp."""
        mock_turbine._telemetry["bearing_temperature_c"] = (
            105  # High temp in Celsius (was 220°F ≈ 105°C)
        )

        await asyncio.sleep(0.05)

        assert started_turbine_safety.safe_state_active is True


# ================================================================
# TRIP AND RESET TESTS
# ================================================================
class TestTurbineSafetyPLCTripReset:
    """Test trip and reset operations."""

    @pytest.mark.asyncio
    async def test_manual_trip(self, started_turbine_safety, mock_turbine):
        """Test manual trip command."""
        await started_turbine_safety.manual_trip()

        # Wait for scan cycle to process the trip
        await asyncio.sleep(0.05)

        assert started_turbine_safety.safe_state_active is True
        assert mock_turbine.emergency_trip_triggered is True

    @pytest.mark.asyncio
    async def test_reset_after_trip(self, started_turbine_safety, mock_turbine):
        """Test reset after trip."""
        # Trigger trip
        await started_turbine_safety.manual_trip()

        # Wait for scan cycle to process the trip
        await asyncio.sleep(0.05)

        assert started_turbine_safety.safe_state_active is True

        # Clear trip condition
        mock_turbine._telemetry["trip_active"] = False

        # Reset
        result = await started_turbine_safety.reset_from_safe_state()

        assert result is True
        assert started_turbine_safety.safe_state_active is False


# ================================================================
# STATUS TESTS
# ================================================================
class TestTurbineSafetyPLCStatus:
    """Test status reporting."""

    @pytest.mark.asyncio
    async def test_get_turbine_safety_status(self, started_turbine_safety):
        """Test comprehensive status."""
        status = await started_turbine_safety.get_turbine_safety_status()

        assert "sil_level" in status
        assert "safe_state_active" in status
        # Should include SIF status
        assert "sifs" in status or "turbine" in status


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestTurbineSafetyPLCIntegration:
    """Test integration."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, turbine_safety_plc, datastore_setup):
        """Test registration with DataStore."""
        await turbine_safety_plc.start()

        devices = await datastore_setup.get_devices_by_type("turbine_safety_plc")
        assert len(devices) == 1

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, turbine_safety_plc):
        """Test complete safety PLC lifecycle."""
        await turbine_safety_plc.start()
        assert turbine_safety_plc.is_running()

        await asyncio.sleep(0.03)

        await turbine_safety_plc.stop()
        assert not turbine_safety_plc.is_running()
