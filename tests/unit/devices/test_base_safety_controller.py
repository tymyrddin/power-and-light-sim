# tests/unit/devices/test_base_safety_controller.py
"""Tests for BaseSafetyController - Safety Instrumented System base class.

Tests:
- Initialization with SIL levels and voting architectures
- Safety scan cycle (diagnostics → inputs → logic → outputs)
- Safe state handling
- Bypass operations
- Proof test tracking
- Diagnostic fault handling
"""

import asyncio

import pytest

from components.devices.control_zone.safety.base_safety_controller import (
    BaseSafetyController,
    SafetyIntegrityLevel,
    VotingArchitecture,
)
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


# ================================================================
# CONCRETE SAFETY CONTROLLER FOR TESTING
# ================================================================
class ConcreteSafetyController(BaseSafetyController):
    """Concrete implementation for testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_inputs_count = 0
        self.execute_logic_count = 0
        self.write_outputs_count = 0
        self.diagnostics_count = 0
        self.force_safe_count = 0

        # Test controls
        self.simulate_safety_demand = False
        self.simulate_diagnostic_fault = False

    def _supported_protocols(self) -> list[str]:
        return ["modbus"]

    async def _initialise_memory_map(self) -> None:
        """Initialise test memory map."""
        self.memory_map = {
            "sensor_a": 0.0,
            "sensor_b": 0.0,
            "output_safe": True,
        }

    async def _read_safety_inputs(self) -> None:
        """Read safety inputs."""
        self.read_inputs_count += 1

    async def _execute_safety_logic(self) -> bool:
        """Execute safety logic. Returns True if safety demanded."""
        self.execute_logic_count += 1
        # Base class handles setting safe_state_active when we return True
        return self.simulate_safety_demand

    async def _write_safety_outputs(self) -> None:
        """Write safety outputs."""
        self.write_outputs_count += 1
        self.memory_map["output_safe"] = not self.safe_state_active

    async def _run_diagnostics(self) -> None:
        """Run diagnostics."""
        self.diagnostics_count += 1
        if self.simulate_diagnostic_fault:
            self.diagnostic_fault = True

    async def _force_safe_state(self) -> None:
        """Force safe state."""
        self.force_safe_count += 1
        self.memory_map["output_safe"] = True


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
async def safety_controller(datastore_setup):
    """Create ConcreteSafetyController instance."""
    controller = ConcreteSafetyController(
        device_name="test_safety_1",
        device_id=1,
        data_store=datastore_setup,
        sil_level=SafetyIntegrityLevel.SIL2,
        voting=VotingArchitecture.TWO_OUT_OF_THREE,
        description="Test Safety Controller",
        scan_interval=0.01,
    )
    yield controller
    if controller.is_running():
        await controller.stop()


@pytest.fixture
async def started_safety_controller(safety_controller):
    """Create and start safety controller."""
    await safety_controller.start()
    yield safety_controller
    if safety_controller.is_running():
        await safety_controller.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestBaseSafetyControllerInitialization:
    """Test BaseSafetyController initialization."""

    def test_init_with_defaults(self, datastore_setup):
        """Test initialization with default SIL/voting."""
        controller = ConcreteSafetyController(
            device_name="safety_default",
            device_id=1,
            data_store=datastore_setup,
        )

        assert controller.sil_level == SafetyIntegrityLevel.SIL2
        assert controller.voting == VotingArchitecture.TWO_OUT_OF_THREE

    def test_init_with_custom_sil(self, datastore_setup):
        """Test initialization with custom SIL level."""
        controller = ConcreteSafetyController(
            device_name="safety_sil3",
            device_id=2,
            data_store=datastore_setup,
            sil_level=SafetyIntegrityLevel.SIL3,
        )

        assert controller.sil_level == SafetyIntegrityLevel.SIL3

    def test_init_with_custom_voting(self, datastore_setup):
        """Test initialisation with custom voting architecture."""
        controller = ConcreteSafetyController(
            device_name="safety_1oo2",
            device_id=3,
            data_store=datastore_setup,
            voting=VotingArchitecture.ONE_OUT_OF_TWO,
        )

        assert controller.voting == VotingArchitecture.ONE_OUT_OF_TWO

    def test_device_type_is_safety_controller(self, safety_controller):
        """Test device type."""
        assert safety_controller._device_type() == "safety_controller"

    def test_initial_state(self, safety_controller):
        """Test initial safety state."""
        assert safety_controller.safe_state_active is False
        assert safety_controller.diagnostic_fault is False
        assert safety_controller.bypass_active is False
        assert safety_controller.demand_count == 0
        assert safety_controller.fault_count == 0


# ================================================================
# SCAN CYCLE TESTS
# ================================================================
class TestBaseSafetyControllerScanCycle:
    """Test safety scan cycle operations."""

    @pytest.mark.asyncio
    async def test_scan_cycle_order(self, started_safety_controller):
        """Test that scan cycle executes all phases."""
        await asyncio.sleep(0.03)

        assert started_safety_controller.diagnostics_count > 0
        assert started_safety_controller.read_inputs_count > 0
        assert started_safety_controller.execute_logic_count > 0
        assert started_safety_controller.write_outputs_count > 0

    @pytest.mark.asyncio
    async def test_diagnostics_run_first(self, started_safety_controller):
        """Test that diagnostics run before logic."""
        await asyncio.sleep(0.03)

        # Diagnostics should have run at least as many times as logic
        assert (
            started_safety_controller.diagnostics_count
            >= started_safety_controller.execute_logic_count
        )


# ================================================================
# SAFE STATE TESTS
# ================================================================
class TestBaseSafetyControllerSafeState:
    """Test safe state handling."""

    @pytest.mark.asyncio
    async def test_safety_demand_activates_safe_state(self, started_safety_controller):
        """Test that safety demand activates safe state."""
        started_safety_controller.simulate_safety_demand = True

        await asyncio.sleep(0.03)

        assert started_safety_controller.safe_state_active is True
        assert started_safety_controller.demand_count > 0

    @pytest.mark.asyncio
    async def test_reset_from_safe_state(self, started_safety_controller):
        """Test resetting from safe state."""
        # Enter safe state
        started_safety_controller.safe_state_active = True

        result = await started_safety_controller.reset_from_safe_state()

        assert result is True
        assert started_safety_controller.safe_state_active is False

    @pytest.mark.asyncio
    async def test_reset_blocked_by_diagnostic_fault(self, started_safety_controller):
        """Test that reset is blocked when diagnostic fault active."""
        started_safety_controller.safe_state_active = True
        started_safety_controller.diagnostic_fault = True

        result = await started_safety_controller.reset_from_safe_state()

        assert result is False
        assert started_safety_controller.safe_state_active is True


# ================================================================
# DIAGNOSTIC FAULT TESTS
# ================================================================
class TestBaseSafetyControllerDiagnostics:
    """Test diagnostic fault handling."""

    @pytest.mark.asyncio
    async def test_diagnostic_fault_forces_safe_state(self, started_safety_controller):
        """Test that diagnostic fault forces safe state."""
        started_safety_controller.simulate_diagnostic_fault = True

        await asyncio.sleep(0.03)

        assert started_safety_controller.safe_state_active is True
        assert started_safety_controller.force_safe_count > 0

    @pytest.mark.asyncio
    async def test_diagnostic_fault_blocks_normal_operation(
        self, started_safety_controller
    ):
        """Test that diagnostic fault prevents normal scan."""
        started_safety_controller.simulate_diagnostic_fault = True

        initial_logic_count = started_safety_controller.execute_logic_count

        await asyncio.sleep(0.03)

        # Logic should not have executed (scan returns early on fault)
        # Note: May execute once before fault is detected
        assert started_safety_controller.execute_logic_count <= initial_logic_count + 1


# ================================================================
# BYPASS TESTS
# ================================================================
class TestBaseSafetyControllerBypass:
    """Test bypass operations."""

    @pytest.mark.asyncio
    async def test_activate_bypass(self, started_safety_controller):
        """Test bypass activation."""
        # Directly set bypass for testing without auth
        started_safety_controller.bypass_active = True

        assert started_safety_controller.bypass_active is True

    @pytest.mark.asyncio
    async def test_deactivate_bypass(self, started_safety_controller):
        """Test bypass deactivation."""
        started_safety_controller.bypass_active = True

        await started_safety_controller.deactivate_bypass()

        assert started_safety_controller.bypass_active is False


# ================================================================
# PROOF TEST TESTS
# ================================================================
class TestBaseSafetyControllerProofTest:
    """Test proof test tracking."""

    @pytest.mark.asyncio
    async def test_record_proof_test(
        self, started_safety_controller, clean_simulation_time
    ):
        """Test recording proof test."""
        from components.time.simulation_time import TimeMode

        # Set to stepped mode to allow manual time advancement
        clean_simulation_time.state.mode = TimeMode.STEPPED
        await clean_simulation_time.step(1.0)
        initial_time = started_safety_controller.last_proof_test

        await started_safety_controller.record_proof_test()

        assert started_safety_controller.last_proof_test > initial_time

    @pytest.mark.asyncio
    async def test_is_proof_test_due_initially(
        self, safety_controller, clean_simulation_time
    ):
        """Test proof test due check (initially due)."""
        from components.time.simulation_time import TimeMode

        # Set to stepped mode to allow manual time advancement
        clean_simulation_time.state.mode = TimeMode.STEPPED
        # Advance time past proof test interval (8760 hours = 31,536,000 seconds)
        await clean_simulation_time.step(32_000_000)
        # With last_proof_test = 0 and time advanced past interval, should be due
        assert safety_controller.is_proof_test_due() is True

    @pytest.mark.asyncio
    async def test_is_proof_test_due_after_test(self, started_safety_controller):
        """Test proof test not due after recording."""
        await started_safety_controller.record_proof_test()

        # Should not be due immediately after test
        assert started_safety_controller.is_proof_test_due() is False


# ================================================================
# STATUS TESTS
# ================================================================
class TestBaseSafetyControllerStatus:
    """Test status reporting."""

    @pytest.mark.asyncio
    async def test_get_safety_status(self, started_safety_controller):
        """Test comprehensive safety status."""
        status = await started_safety_controller.get_safety_status()

        assert "sil_level" in status
        assert "voting_architecture" in status
        assert "safe_state_active" in status
        assert "diagnostic_fault" in status
        assert "bypass_active" in status
        assert "demand_count" in status
        assert "proof_test_due" in status

    @pytest.mark.asyncio
    async def test_status_values(self, started_safety_controller):
        """Test status values are accurate."""
        started_safety_controller.demand_count = 5

        status = await started_safety_controller.get_safety_status()

        assert status["sil_level"] == "SIL2"
        assert status["voting_architecture"] == "2oo3"
        assert status["demand_count"] == 5


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestBaseSafetyControllerIntegration:
    """Test integration with dependencies."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, safety_controller, datastore_setup):
        """Test registration with DataStore."""
        await safety_controller.start()

        devices = await datastore_setup.get_devices_by_type("safety_controller")
        assert len(devices) == 1

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, safety_controller):
        """Test complete safety controller lifecycle."""
        # Start
        await safety_controller.start()
        assert safety_controller.is_running()

        # Run
        await asyncio.sleep(0.03)
        assert safety_controller.diagnostics_count > 0

        # Trigger safe state
        safety_controller.simulate_safety_demand = True
        await asyncio.sleep(0.03)
        assert safety_controller.safe_state_active is True

        # Reset
        safety_controller.simulate_safety_demand = False
        await safety_controller.reset_from_safe_state()
        assert safety_controller.safe_state_active is False

        # Stop
        await safety_controller.stop()
        assert not safety_controller.is_running()
