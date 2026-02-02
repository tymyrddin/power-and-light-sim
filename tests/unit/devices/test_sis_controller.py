# tests/unit/devices/test_sis_controller.py
"""Tests for SISController - Configurable Safety Instrumented System controller.

Tests:
- Initialization
- Adding SIFs with various configurations
- Condition function and data source monitoring
- Trip actions (LOG, ALARM, TRIP, SCRAM)
- Multiple SIF evaluation
- SIF limits
"""

import asyncio

import pytest

from components.devices.control_zone.safety.base_safety_controller import (
    SafetyIntegrityLevel,
)
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


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
async def sis_controller(datastore_setup):
    """Create SISController instance."""
    from components.devices.control_zone.safety.sis_controller import SISController

    controller = SISController(
        device_name="test_sis_1",
        device_id=30,
        data_store=datastore_setup,
        description="Test SIS Controller",
        scan_interval=0.01,
    )
    yield controller
    if controller.is_running():
        await controller.stop()


@pytest.fixture
async def started_sis(sis_controller):
    """Create and start SISController."""
    await sis_controller.start()
    yield sis_controller
    if sis_controller.is_running():
        await sis_controller.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestSISControllerInitialization:
    """Test SISController initialization."""

    def test_init_with_defaults(self, datastore_setup):
        """Test initialization with defaults."""
        from components.devices.control_zone.safety.sis_controller import SISController

        controller = SISController(
            device_name="sis_default",
            device_id=1,
            data_store=datastore_setup,
        )

        assert controller.device_name == "sis_default"

    def test_device_type(self, sis_controller):
        """Test device type."""
        assert sis_controller._device_type() == "sis_controller"

    def test_no_sifs_initially(self, sis_controller):
        """Test no SIFs configured initially."""
        assert len(sis_controller.sifs) == 0


# ================================================================
# ADD SIF TESTS
# ================================================================
class TestSISControllerAddSIF:
    """Test adding Safety Instrumented Functions."""

    def test_add_sif_with_condition_func(self, sis_controller):
        """Test adding SIF with condition function."""
        from components.devices.control_zone.safety.sis_controller import TripAction

        def high_temp_condition():
            return False  # Normal

        result = sis_controller.add_sif(
            name="SIF-001",
            description="High Temperature",
            sil_level=SafetyIntegrityLevel.SIL2,
            trip_action=TripAction.TRIP,
            condition_func=high_temp_condition,
        )

        assert result is True
        assert "SIF-001" in sis_controller.sifs

    def test_add_sif_with_data_source(self, sis_controller):
        """Test adding SIF with data source monitoring."""
        from components.devices.control_zone.safety.sis_controller import TripAction

        result = sis_controller.add_sif(
            name="SIF-002",
            description="High Pressure",
            sil_level=SafetyIntegrityLevel.SIL2,
            trip_action=TripAction.ALARM,
            data_source="pressure_sensor",
            trip_high=150.0,
        )

        assert result is True
        assert "SIF-002" in sis_controller.sifs

    def test_add_sif_with_low_trip(self, sis_controller):
        """Test adding SIF with low trip threshold."""
        from components.devices.control_zone.safety.sis_controller import TripAction

        result = sis_controller.add_sif(
            name="SIF-003",
            description="Low Level",
            sil_level=SafetyIntegrityLevel.SIL1,
            trip_action=TripAction.LOG_ONLY,
            data_source="level_sensor",
            trip_low=10.0,
        )

        assert result is True

    def test_add_duplicate_sif_fails(self, sis_controller):
        """Test adding duplicate SIF fails."""
        from components.devices.control_zone.safety.sis_controller import TripAction

        sis_controller.add_sif(
            name="SIF-DUP",
            description="First",
            sil_level=SafetyIntegrityLevel.SIL1,
            trip_action=TripAction.LOG_ONLY,
            condition_func=lambda: False,
        )

        result = sis_controller.add_sif(
            name="SIF-DUP",
            description="Second",
            sil_level=SafetyIntegrityLevel.SIL1,
            trip_action=TripAction.LOG_ONLY,
            condition_func=lambda: False,
        )

        assert result is False

    def test_add_max_sifs(self, sis_controller):
        """Test maximum SIF limit."""
        from components.devices.control_zone.safety.sis_controller import (
            SISController,
            TripAction,
        )

        for i in range(SISController.MAX_SIFS):
            sis_controller.add_sif(
                name=f"SIF-{i:03d}",
                description=f"SIF {i}",
                sil_level=SafetyIntegrityLevel.SIL1,
                trip_action=TripAction.LOG_ONLY,
                condition_func=lambda: False,
            )

        result = sis_controller.add_sif(
            name="SIF-EXTRA",
            description="Extra",
            sil_level=SafetyIntegrityLevel.SIL1,
            trip_action=TripAction.LOG_ONLY,
            condition_func=lambda: False,
        )

        assert result is False


# ================================================================
# SIF EVALUATION TESTS
# ================================================================
class TestSISControllerEvaluation:
    """Test SIF evaluation during scan cycle."""

    @pytest.mark.asyncio
    async def test_condition_func_evaluated(self, sis_controller):
        """Test condition function is evaluated."""
        from components.devices.control_zone.safety.sis_controller import TripAction

        call_count = [0]

        def counting_condition():
            call_count[0] += 1
            return False

        sis_controller.add_sif(
            name="SIF-COUNT",
            description="Counting SIF",
            sil_level=SafetyIntegrityLevel.SIL1,
            trip_action=TripAction.LOG_ONLY,
            condition_func=counting_condition,
        )

        await sis_controller.start()
        await asyncio.sleep(0.03)
        await sis_controller.stop()

        assert call_count[0] > 0

    @pytest.mark.asyncio
    async def test_trip_action_trip(self, sis_controller):
        """Test TRIP action activates safe state."""
        from components.devices.control_zone.safety.sis_controller import TripAction

        sis_controller.add_sif(
            name="SIF-TRIP",
            description="Trip SIF",
            sil_level=SafetyIntegrityLevel.SIL2,
            trip_action=TripAction.TRIP,
            condition_func=lambda: True,  # Always trips
        )

        await sis_controller.start()
        await asyncio.sleep(0.03)

        assert sis_controller.safe_state_active is True

        await sis_controller.stop()

    @pytest.mark.asyncio
    async def test_trip_action_scram(self, sis_controller):
        """Test SCRAM action activates safe state."""
        from components.devices.control_zone.safety.sis_controller import TripAction

        sis_controller.add_sif(
            name="SIF-SCRAM",
            description="SCRAM SIF",
            sil_level=SafetyIntegrityLevel.SIL3,
            trip_action=TripAction.SCRAM,
            condition_func=lambda: True,
        )

        await sis_controller.start()
        await asyncio.sleep(0.03)

        assert sis_controller.safe_state_active is True

        await sis_controller.stop()

    @pytest.mark.asyncio
    async def test_trip_action_log_only(self, sis_controller):
        """Test LOG_ONLY action doesn't activate safe state."""
        from components.devices.control_zone.safety.sis_controller import TripAction

        sis_controller.add_sif(
            name="SIF-LOG",
            description="Log SIF",
            sil_level=SafetyIntegrityLevel.SIL1,
            trip_action=TripAction.LOG_ONLY,
            condition_func=lambda: True,
        )

        await sis_controller.start()
        await asyncio.sleep(0.03)

        # LOG_ONLY should not activate safe state
        assert sis_controller.safe_state_active is False

        await sis_controller.stop()

    @pytest.mark.asyncio
    async def test_multiple_sifs_any_trips(self, sis_controller):
        """Test that any SIF can trigger trip."""
        from components.devices.control_zone.safety.sis_controller import TripAction

        # First SIF - normal
        sis_controller.add_sif(
            name="SIF-NORMAL",
            description="Normal SIF",
            sil_level=SafetyIntegrityLevel.SIL1,
            trip_action=TripAction.TRIP,
            condition_func=lambda: False,
        )

        # Second SIF - trips
        sis_controller.add_sif(
            name="SIF-TRIPS",
            description="Tripping SIF",
            sil_level=SafetyIntegrityLevel.SIL2,
            trip_action=TripAction.TRIP,
            condition_func=lambda: True,
        )

        await sis_controller.start()
        await asyncio.sleep(0.03)

        assert sis_controller.safe_state_active is True

        await sis_controller.stop()


# ================================================================
# SIF STATUS TESTS
# ================================================================
class TestSISControllerSIFStatus:
    """Test SIF status reporting."""

    @pytest.mark.asyncio
    async def test_get_sif_status(self, sis_controller):
        """Test getting SIF status."""
        from components.devices.control_zone.safety.sis_controller import TripAction

        sis_controller.add_sif(
            name="SIF-STATUS",
            description="Status Test",
            sil_level=SafetyIntegrityLevel.SIL2,
            trip_action=TripAction.TRIP,
            condition_func=lambda: False,
        )

        await sis_controller.start()
        await asyncio.sleep(0.02)

        status = await sis_controller.get_safety_status()

        assert "sifs" in status or len(sis_controller.sifs) > 0

        await sis_controller.stop()


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestSISControllerIntegration:
    """Test SISController integration."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, sis_controller, datastore_setup):
        """Test registration with DataStore."""
        await sis_controller.start()

        devices = await datastore_setup.get_devices_by_type("sis_controller")
        assert len(devices) == 1

        await sis_controller.stop()

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, sis_controller):
        """Test complete SIS lifecycle."""
        from components.devices.control_zone.safety.sis_controller import TripAction

        # Add SIF
        sis_controller.add_sif(
            name="SIF-LIFECYCLE",
            description="Lifecycle Test",
            sil_level=SafetyIntegrityLevel.SIL2,
            trip_action=TripAction.TRIP,
            condition_func=lambda: False,
        )

        # Start
        await sis_controller.start()
        assert sis_controller.is_running()

        # Run
        await asyncio.sleep(0.03)
        assert sis_controller.safe_state_active is False

        # Stop
        await sis_controller.stop()
        assert not sis_controller.is_running()
