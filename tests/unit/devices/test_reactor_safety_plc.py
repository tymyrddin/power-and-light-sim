# tests/unit/devices/test_reactor_safety_plc.py
"""Tests for ReactorSafetyPLC - Dedicated safety PLC for Alchemical Reactor.

Tests:
- Initialization with reactor physics
- Safety Instrumented Functions (temp, pressure, thaumic, containment, coolant)
- SIL3 rating
- SCRAM operations
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from components.devices.control_zone.safety.base_safety_controller import (
    SafetyIntegrityLevel,
)
from components.physics.reactor_physics import ReactorParameters, ReactorPhysics
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


def create_mock_reactor_physics() -> MagicMock:
    """Create a mock ReactorPhysics with test-friendly behaviour."""
    mock = MagicMock(spec=ReactorPhysics)
    mock.device_name = "mock_reactor"

    # Create mock params
    mock.params = MagicMock(spec=ReactorParameters)
    mock.params.critical_temperature_c = 450.0
    mock.params.max_safe_pressure_bar = 160.0

    # Track values for assertions
    mock.scram_triggered = False

    mock._telemetry = {
        "core_temperature_c": 350.0,
        "vessel_pressure_bar": 155.0,
        "thaumic_field_strength": 1.0,
        "containment_integrity_percent": 100.0,
        "coolant_flow_percent": 95.0,
        "scram_active": False,
        "reactor_active": True,
    }

    def get_telemetry() -> dict:
        return mock._telemetry.copy()

    def trigger_scram() -> None:
        mock.scram_triggered = True
        mock._telemetry["scram_active"] = True

    def reset_scram() -> bool:
        if mock._telemetry["scram_active"]:
            mock._telemetry["scram_active"] = False
            mock.scram_triggered = False
            return True
        return False

    # Wire up the mock methods
    mock.get_telemetry.side_effect = get_telemetry
    mock.trigger_scram.side_effect = trigger_scram
    mock.reset_scram.side_effect = reset_scram

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
def mock_reactor():
    """Create mock reactor physics."""
    return create_mock_reactor_physics()


@pytest.fixture
async def reactor_safety_plc(datastore_setup, mock_reactor):
    """Create ReactorSafetyPLC instance."""
    from components.devices.control_zone.safety.reactor_safety_plc import (
        ReactorSafetyPLC,
    )

    plc = ReactorSafetyPLC(
        device_name="reactor_safety_1",
        device_id=20,
        data_store=datastore_setup,
        reactor_physics=mock_reactor,
        scan_interval=0.01,
    )
    yield plc
    if plc.is_running():
        await plc.stop()


@pytest.fixture
async def started_reactor_safety(reactor_safety_plc):
    """Create and start ReactorSafetyPLC."""
    await reactor_safety_plc.start()
    yield reactor_safety_plc
    if reactor_safety_plc.is_running():
        await reactor_safety_plc.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestReactorSafetyPLCInitialization:
    """Test ReactorSafetyPLC initialization."""

    def test_init_with_physics(self, datastore_setup, mock_reactor):
        """Test initialization with reactor physics."""
        from components.devices.control_zone.safety.reactor_safety_plc import (
            ReactorSafetyPLC,
        )

        plc = ReactorSafetyPLC(
            device_name="test_reactor_safety",
            device_id=1,
            data_store=datastore_setup,
            reactor_physics=mock_reactor,
        )

        assert plc.reactor_physics == mock_reactor

    def test_default_sil_level_is_sil3(self, reactor_safety_plc):
        """Test default SIL level is SIL3 (higher than turbine)."""
        assert reactor_safety_plc.sil_level == SafetyIntegrityLevel.SIL3

    def test_device_type(self, reactor_safety_plc):
        """Test device type."""
        assert reactor_safety_plc._device_type() == "reactor_safety_plc"


# ================================================================
# SIF TESTS
# ================================================================
class TestReactorSafetyPLCSIFs:
    """Test Safety Instrumented Functions."""

    @pytest.mark.asyncio
    async def test_sif_high_temp_trips(self, started_reactor_safety, mock_reactor):
        """Test high temperature SIF trips."""
        mock_reactor._telemetry["core_temperature_c"] = 550.0  # High temp

        await asyncio.sleep(0.05)

        assert started_reactor_safety.safe_state_active is True
        assert mock_reactor.scram_triggered is True

    @pytest.mark.asyncio
    async def test_sif_high_pressure_trips(self, started_reactor_safety, mock_reactor):
        """Test high pressure SIF trips."""
        # Trip setpoint is 150 bar (holding_registers[1] = 1500 / 10.0)
        mock_reactor._telemetry["vessel_pressure_bar"] = 180.0  # High pressure

        await asyncio.sleep(0.05)

        assert started_reactor_safety.safe_state_active is True

    @pytest.mark.asyncio
    async def test_sif_thaumic_instability_trips(
        self, started_reactor_safety, mock_reactor
    ):
        """Test thaumic instability SIF trips."""
        # Thaumic trip at <30% (thaumic_field_strength * 100 < 30)
        # Low thaumic field strength causes instability
        mock_reactor._telemetry["thaumic_field_strength"] = 0.1  # 10%, below 30% threshold

        await asyncio.sleep(0.05)

        assert started_reactor_safety.safe_state_active is True

    @pytest.mark.asyncio
    async def test_sif_containment_breach_trips(
        self, started_reactor_safety, mock_reactor
    ):
        """Test containment breach SIF trips."""
        # Containment trip at <50% (holding_registers[3] = 50)
        mock_reactor._telemetry["containment_integrity_percent"] = 40.0  # Low integrity

        await asyncio.sleep(0.05)

        assert started_reactor_safety.safe_state_active is True

    @pytest.mark.asyncio
    async def test_sif_low_coolant_trips(self, started_reactor_safety, mock_reactor):
        """Test low coolant SIF trips."""
        # Coolant trip at <10% (holding_registers[4] = 10)
        mock_reactor._telemetry["coolant_flow_percent"] = 5.0  # Low coolant

        await asyncio.sleep(0.05)

        assert started_reactor_safety.safe_state_active is True

    @pytest.mark.asyncio
    async def test_normal_operation(self, started_reactor_safety, mock_reactor):
        """Test normal operation doesn't trip."""
        # All values normal
        await asyncio.sleep(0.03)

        assert started_reactor_safety.safe_state_active is False


# ================================================================
# SCRAM TESTS
# ================================================================
class TestReactorSafetyPLCSCRAM:
    """Test SCRAM operations."""

    @pytest.mark.asyncio
    async def test_manual_scram(self, started_reactor_safety, mock_reactor):
        """Test manual SCRAM command."""
        await started_reactor_safety.trigger_scram()

        # Wait for scan cycle to process the SCRAM
        await asyncio.sleep(0.05)

        assert started_reactor_safety.safe_state_active is True
        assert mock_reactor.scram_triggered is True

    @pytest.mark.asyncio
    async def test_reset_after_scram(self, started_reactor_safety, mock_reactor):
        """Test reset after SCRAM."""
        await started_reactor_safety.trigger_scram()

        # Wait for scan cycle to process the SCRAM
        await asyncio.sleep(0.05)

        # Clear SCRAM condition
        mock_reactor._telemetry["scram_active"] = False

        result = await started_reactor_safety.reset_from_safe_state()

        assert result is True


# ================================================================
# STATUS TESTS
# ================================================================
class TestReactorSafetyPLCStatus:
    """Test status reporting."""

    @pytest.mark.asyncio
    async def test_get_reactor_safety_status(self, started_reactor_safety):
        """Test comprehensive status."""
        status = await started_reactor_safety.get_reactor_safety_status()

        assert "sil_level" in status
        assert status["sil_level"] == "SIL3"


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestReactorSafetyPLCIntegration:
    """Test integration."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, reactor_safety_plc, datastore_setup):
        """Test registration with DataStore."""
        await reactor_safety_plc.start()

        devices = await datastore_setup.get_devices_by_type("reactor_safety_plc")
        assert len(devices) == 1

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, reactor_safety_plc, mock_reactor):
        """Test complete safety PLC lifecycle."""
        await reactor_safety_plc.start()
        assert reactor_safety_plc.is_running()

        # Normal operation
        await asyncio.sleep(0.03)
        assert reactor_safety_plc.safe_state_active is False

        # Trigger SCRAM
        mock_reactor._telemetry["core_temperature_c"] = 600.0
        await asyncio.sleep(0.05)
        assert reactor_safety_plc.safe_state_active is True

        await reactor_safety_plc.stop()
        assert not reactor_safety_plc.is_running()
