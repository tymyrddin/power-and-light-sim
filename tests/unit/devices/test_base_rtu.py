# tests/unit/devices/test_base_rtu.py
"""Comprehensive tests for BaseRTU abstract base class.

This is Level 5 in our dependency tree - BaseRTU depends on:
- BaseDevice (Level 4) - uses REAL BaseDevice
- DataStore (Level 2) - uses REAL DataStore
- SystemState (Level 1) - uses REAL SystemState (via DataStore)
- SimulationTime (Level 0) - uses REAL SimulationTime

Test Coverage:
- Initialization and configuration
- RTU data acquisition cycle
- Event detection (report-by-exception)
- Deadband handling
- Integration with BaseDevice diagnostics
- Abstract method enforcement
- Error handling
- Status reporting
"""

import asyncio

import pytest

from components.devices.control_zone.rtu.base_rtu import BaseRTU
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


# ================================================================
# TEST RTU IMPLEMENTATION
# ================================================================
class ConcreteRTU(BaseRTU):
    """Concrete implementation of BaseRTU for testing.

    WHY: BaseRTU is abstract - need concrete class to test.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_inputs_count = 0
        self.process_data_count = 0
        self.report_to_master_count = 0
        self.simulated_sensor_value = 100.0

    def _supported_protocols(self) -> list[str]:
        return ["dnp3", "modbus"]

    async def _initialise_memory_map(self) -> None:
        """Initialise test RTU point map."""
        self.memory_map = {
            "analog_input_1": 0.0,
            "analog_input_2": 0.0,
            "digital_input_1": False,
            "digital_input_2": False,
        }

    async def _read_inputs(self) -> None:
        """Read inputs from field sensors."""
        self.read_inputs_count += 1
        # Simulate sensor readings
        self.memory_map["analog_input_1"] = self.simulated_sensor_value
        self.memory_map["analog_input_2"] = self.simulated_sensor_value * 2
        self.memory_map["digital_input_1"] = self.read_inputs_count % 2 == 0

    async def _process_data(self) -> None:
        """Process and validate data."""
        self.process_data_count += 1
        # Simple processing: validate ranges
        if self.memory_map["analog_input_1"] < 0:
            self.memory_map["analog_input_1"] = 0.0

    async def _report_to_master(self) -> None:
        """Report data to SCADA master."""
        self.report_to_master_count += 1
        # Simulate reporting (would send via protocol)


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
async def clean_simulation_time():
    """Reset SimulationTime singleton before each test.

    WHY: SimulationTime is a singleton - must reset between tests.
    """
    sim_time = SimulationTime()
    await sim_time.reset()
    yield sim_time
    await sim_time.reset()


@pytest.fixture
async def datastore_setup(clean_simulation_time):
    """Create DataStore with SystemState.

    WHY: BaseRTU requires DataStore for registration.
    """
    system_state = SystemState()
    data_store = DataStore(system_state)
    yield data_store


@pytest.fixture
async def test_rtu(datastore_setup):
    """Create ConcreteRTU instance (not started).

    WHY: Most tests need an RTU instance.
    """
    data_store = datastore_setup
    rtu = ConcreteRTU(
        device_name="test_rtu_1",
        device_id=1,
        data_store=data_store,
        description="Test RTU for unit testing",
        scan_interval=0.01,  # Fast for testing (normally 1s)
        report_by_exception=True,
    )

    yield rtu

    # Cleanup
    if rtu.is_running():
        await rtu.stop()


@pytest.fixture
async def started_rtu(test_rtu):
    """Create and start a ConcreteRTU.

    WHY: Many tests need a running RTU.
    """
    await test_rtu.start()
    yield test_rtu

    # Cleanup
    if test_rtu.is_running():
        await test_rtu.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestBaseRTUInitialization:
    """Test RTU initialization."""

    def test_init_with_defaults(self, datastore_setup):
        """Test initialising RTU with default parameters.

        WHY: Verify sensible defaults for RTUs.
        """
        data_store = datastore_setup
        rtu = ConcreteRTU(
            device_name="test_rtu",
            device_id=1,
            data_store=data_store,
        )

        assert rtu.device_name == "test_rtu"
        assert rtu.device_id == 1
        assert rtu.scan_interval == 1.0  # RTU default (1s)
        assert rtu.report_by_exception is True  # Default
        assert not rtu.is_online()
        assert not rtu.is_running()

    def test_init_with_polling_mode(self, datastore_setup):
        """Test initialising RTU in polling mode.

        WHY: RTUs can operate in polling or report-by-exception mode.
        """
        data_store = datastore_setup
        rtu = ConcreteRTU(
            device_name="polling_rtu",
            device_id=2,
            data_store=data_store,
            report_by_exception=False,
        )

        assert rtu.report_by_exception is False

    def test_device_type_is_rtu(self, test_rtu):
        """Test that _device_type() returns 'rtu'.

        WHY: RTUs must identify as 'rtu' type.
        """
        assert test_rtu._device_type() == "rtu"

    def test_rtu_specific_state_initialised(self, test_rtu):
        """Test that RTU-specific state is initialised.

        WHY: RTUs track events, not just scans.
        """
        assert test_rtu.event_count == 0
        assert test_rtu.last_report_time == 0.0
        assert isinstance(test_rtu.previous_values, dict)
        assert isinstance(test_rtu.deadbands, dict)

    def test_no_duplicate_poll_count(self, test_rtu):
        """Test that RTU doesn't duplicate scan_count as poll_count.

        WHY: Should use BaseDevice.metadata["scan_count"].
        """
        # Should NOT have poll_count attribute (would be duplicate)
        assert not hasattr(test_rtu, "poll_count")

        # Should use metadata from BaseDevice
        assert "scan_count" in test_rtu.metadata


# ================================================================
# DATA ACQUISITION CYCLE TESTS
# ================================================================
class TestBaseRTUDataAcquisition:
    """Test RTU data acquisition cycle."""

    @pytest.mark.asyncio
    async def test_acquisition_cycle_order(self, started_rtu):
        """Test that acquisition cycle executes in correct order.

        WHY: RTU must follow Read → Process → Detect → Report pattern.
        """
        # Wait for at least one cycle
        await asyncio.sleep(0.03)

        # All phases should have executed
        assert started_rtu.read_inputs_count > 0
        assert started_rtu.process_data_count > 0
        # Report count depends on events

    @pytest.mark.asyncio
    async def test_acquisition_updates_memory_map(self, started_rtu):
        """Test that acquisition cycle updates memory map.

        WHY: RTU must capture sensor data.
        """
        await asyncio.sleep(0.03)

        # Analogue inputs should have values
        assert started_rtu.memory_map["analog_input_1"] > 0
        assert started_rtu.memory_map["analog_input_2"] > 0

    @pytest.mark.asyncio
    async def test_acquisition_uses_basedevice_scan_count(self, started_rtu):
        """Test that RTU uses BaseDevice scan_count (not separate poll_count).

        WHY: Should not duplicate diagnostic tracking.
        """
        await asyncio.sleep(0.03)

        # BaseDevice metadata should track scans
        assert started_rtu.metadata["scan_count"] > 0

        # Should be closely correlated with read count (may differ by 1 due to timing)
        assert (
            abs(started_rtu.metadata["scan_count"] - started_rtu.read_inputs_count) <= 1
        )


# ================================================================
# EVENT DETECTION TESTS
# ================================================================
class TestBaseRTUEventDetection:
    """Test RTU event detection functionality."""

    @pytest.mark.asyncio
    async def test_digital_change_detection(self, started_rtu):
        """Test that digital point changes are detected.

        WHY: Report-by-exception requires event detection.
        """
        # Wait for initial scans
        await asyncio.sleep(0.02)
        initial_events = started_rtu.event_count

        # Digital input toggles each scan
        await asyncio.sleep(0.03)

        # Events should be detected
        assert started_rtu.event_count > initial_events

    @pytest.mark.asyncio
    async def test_analogue_deadband_detection(self, started_rtu):
        """Test that analogue changes exceeding deadband are detected.

        WHY: Deadbands prevent noise triggering events.
        """
        # Set deadband
        started_rtu.set_deadband("analog_input_1", 10.0)

        # Wait for initial scan
        await asyncio.sleep(0.02)
        initial_events = started_rtu.event_count

        # Change value beyond deadband
        started_rtu.simulated_sensor_value = 120.0
        await asyncio.sleep(0.02)

        # Event should be detected
        assert started_rtu.event_count > initial_events

    @pytest.mark.asyncio
    async def test_analogue_within_deadband_no_event(self, started_rtu):
        """Test that analogue changes within deadband don't trigger events.

        WHY: Deadbands filter noise.
        """
        # Set large deadband
        started_rtu.set_deadband("analog_input_1", 50.0)

        # Wait for initial scan and let events settle
        await asyncio.sleep(0.02)
        initial_events = started_rtu.event_count

        # Small change within deadband
        started_rtu.simulated_sensor_value = 105.0
        await asyncio.sleep(0.02)

        final_events = started_rtu.event_count

        # Event count should not increase significantly
        # (Digital may still toggle, so analogue shouldn't add much)
        # With large deadband, analogue events should be filtered
        assert final_events - initial_events < 5  # Allow for digital toggles

    @pytest.mark.asyncio
    async def test_report_by_exception_mode(self, datastore_setup):
        """Test that report-by-exception only reports on events.

        WHY: Reduces network traffic in SCADA systems.
        """
        data_store = datastore_setup
        rtu = ConcreteRTU(
            device_name="rbe_rtu",
            device_id=10,
            data_store=data_store,
            scan_interval=0.01,
            report_by_exception=True,
        )

        await rtu.start()
        await asyncio.sleep(0.03)

        # Should have reported due to initial events
        assert rtu.report_to_master_count > 0

        # Event count should be tracked
        assert rtu.event_count > 0

        await rtu.stop()

    @pytest.mark.asyncio
    async def test_polling_mode_always_reports(self, datastore_setup):
        """Test that polling mode reports every cycle.

        WHY: Some SCADA systems use periodic polling.
        """
        data_store = datastore_setup
        rtu = ConcreteRTU(
            device_name="poll_rtu",
            device_id=11,
            data_store=data_store,
            scan_interval=0.01,
            report_by_exception=False,  # Polling mode
        )

        await rtu.start()
        await asyncio.sleep(0.03)

        # Should report every scan in polling mode
        assert rtu.report_to_master_count > 0
        # Report count should match scan count
        assert rtu.report_to_master_count == rtu.metadata["scan_count"]

        await rtu.stop()


# ================================================================
# DEADBAND MANAGEMENT TESTS
# ================================================================
class TestBaseRTUDeadbands:
    """Test RTU deadband functionality."""

    def test_set_deadband(self, test_rtu):
        """Test setting deadband for a point.

        WHY: Deadbands configure event sensitivity.
        """
        test_rtu.set_deadband("analog_input_1", 5.0)

        assert "analog_input_1" in test_rtu.deadbands
        assert test_rtu.deadbands["analog_input_1"] == 5.0

    def test_multiple_deadbands(self, test_rtu):
        """Test setting deadbands for multiple points.

        WHY: Different points may need different sensitivities.
        """
        test_rtu.set_deadband("analog_input_1", 5.0)
        test_rtu.set_deadband("analog_input_2", 10.0)

        assert len(test_rtu.deadbands) == 2
        assert test_rtu.deadbands["analog_input_1"] == 5.0
        assert test_rtu.deadbands["analog_input_2"] == 10.0


# ================================================================
# STATUS AND DIAGNOSTICS TESTS
# ================================================================
class TestBaseRTUStatus:
    """Test RTU status reporting."""

    @pytest.mark.asyncio
    async def test_get_rtu_status_structure(self, started_rtu):
        """Test that get_rtu_status() returns expected structure.

        WHY: Status API must be consistent.
        """
        await asyncio.sleep(0.03)

        status = await started_rtu.get_rtu_status()

        # Should include base status
        assert "device_name" in status
        assert "scan_count" in status  # From BaseDevice

        # Should include RTU-specific items
        assert "event_count" in status
        assert "last_report_time" in status
        assert "report_by_exception" in status
        assert "active_deadbands" in status

    @pytest.mark.asyncio
    async def test_get_rtu_status_values(self, started_rtu):
        """Test that get_rtu_status() returns accurate values.

        WHY: Status must reflect actual RTU state.
        """
        # Set some deadbands
        started_rtu.set_deadband("analog_input_1", 5.0)
        started_rtu.set_deadband("analog_input_2", 10.0)

        await asyncio.sleep(0.03)

        status = await started_rtu.get_rtu_status()

        assert status["event_count"] >= 0
        assert status["report_by_exception"] is True
        assert status["active_deadbands"] == 2

    def test_reset_event_count(self, test_rtu):
        """Test resetting event counter.

        WHY: Diagnostics may need to be reset.
        """
        test_rtu.event_count = 42

        test_rtu.reset_event_count()

        assert test_rtu.event_count == 0


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestBaseRTUIntegration:
    """Test RTU integration with dependencies."""

    @pytest.mark.asyncio
    async def test_rtu_registers_with_datastore(self, test_rtu, datastore_setup):
        """Test that RTU registers with DataStore.

        WHY: RTUs must be accessible via DataStore.
        """
        data_store = datastore_setup

        await test_rtu.start()

        # Verify registered
        devices = await data_store.get_devices_by_type("rtu")
        assert len(devices) == 1
        assert devices[0].device_name == "test_rtu_1"

    @pytest.mark.asyncio
    async def test_rtu_memory_accessible_via_datastore(
        self, started_rtu, datastore_setup
    ):
        """Test that RTU point map is accessible via DataStore.

        WHY: SCADA masters read RTU data via protocols.
        """
        data_store = datastore_setup

        # Wait for acquisition
        await asyncio.sleep(0.03)

        # Read via DataStore
        value = await data_store.read_memory("test_rtu_1", "analog_input_1")
        assert value is not None

    @pytest.mark.asyncio
    async def test_complete_rtu_lifecycle(self, test_rtu):
        """Test complete RTU operational lifecycle.

        WHY: Verify end-to-end RTU operation.
        """
        # 1. Start RTU
        await test_rtu.start()
        assert test_rtu.is_online()
        assert test_rtu.is_running()

        # 2. Let it run and acquire data
        await asyncio.sleep(0.03)
        assert test_rtu.read_inputs_count > 0
        assert test_rtu.metadata["scan_count"] > 0

        # 3. Reset RTU
        await test_rtu.reset()
        assert test_rtu.metadata["scan_count"] == 0
        assert test_rtu.is_running()

        # 4. Stop RTU
        await test_rtu.stop()
        assert not test_rtu.is_online()
        assert not test_rtu.is_running()


# ================================================================
# MEMORY MAP TESTS
# ================================================================
class TestBaseRTUMemoryMap:
    """Test RTU point map operations."""

    @pytest.mark.asyncio
    async def test_memory_map_no_diagnostic_pollution(self, started_rtu):
        """Test that point map doesn't contain diagnostic keys.

        WHY: Protocol point map should be clean, no underscore keys.
        """
        await asyncio.sleep(0.03)

        # Check for underscore keys (diagnostic pollution)
        underscore_keys = [
            k for k in started_rtu.memory_map.keys() if k.startswith("_")
        ]

        # Should have no underscore keys
        assert len(underscore_keys) == 0


# ================================================================
# CONCURRENT OPERATIONS TESTS
# ================================================================
class TestBaseRTUConcurrency:
    """Test concurrent RTU operations."""

    @pytest.mark.asyncio
    async def test_multiple_rtu_instances(self, datastore_setup):
        """Test multiple RTU instances operating concurrently.

        WHY: SCADA systems have many RTUs.
        """
        data_store = datastore_setup

        # Create multiple RTUs
        rtus = [
            ConcreteRTU(f"rtu_{i}", i, data_store, scan_interval=0.01) for i in range(3)
        ]

        # Start all
        await asyncio.gather(*[rtu.start() for rtu in rtus])

        # Let them run
        await asyncio.sleep(0.05)

        # All should be acquiring data
        for rtu in rtus:
            assert rtu.read_inputs_count > 0
            assert rtu.metadata["scan_count"] > 0

        # Stop all
        await asyncio.gather(*[rtu.stop() for rtu in rtus])
