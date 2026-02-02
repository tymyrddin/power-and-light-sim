# tests/unit/devices/test_base_supervisory.py
"""Comprehensive tests for BaseSupervisoryDevice abstract base class.

This is Level 5 in our dependency tree - BaseSupervisoryDevice depends on:
- BaseDevice (Level 4) - uses REAL BaseDevice
- DataStore (Level 2) - uses REAL DataStore
- SystemState (Level 1) - uses REAL SystemState (via DataStore)
- SimulationTime (Level 0) - uses REAL SimulationTime

Test Coverage:
- Initialization and configuration
- Poll target management
- Poll timing logic
- Scan cycle execution
- Abstract method enforcement
- Status and diagnostics
- Integration with BaseDevice
"""

import asyncio

import pytest

from components.devices.operations_zone.base_supervisory import (
    BaseSupervisoryDevice,
    PollTarget,
)
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


# ================================================================
# TEST SUPERVISORY DEVICE IMPLEMENTATION
# ================================================================
class ConcreteSupervisoryDevice(BaseSupervisoryDevice):
    """Concrete implementation of BaseSupervisoryDevice for testing.

    WHY: BaseSupervisoryDevice is abstract - need concrete class to test.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.poll_device_count = 0
        self.process_polled_data_count = 0
        self.check_alarms_count = 0
        self.polled_targets: list[str] = []

    def _supported_protocols(self) -> list[str]:
        return ["modbus", "test_protocol"]

    async def _initialise_memory_map(self) -> None:
        """Initialise test memory map."""
        self.memory_map = {
            "status": 0,
            "poll_count": 0,
            "last_polled_device": "",
        }

    async def _poll_device(self, target: PollTarget) -> None:
        """Poll a device."""
        self.poll_device_count += 1
        self.polled_targets.append(target.device_name)
        self.memory_map["last_polled_device"] = target.device_name
        target.last_poll_success = True

    async def _process_polled_data(self) -> None:
        """Process polled data."""
        self.process_polled_data_count += 1
        self.memory_map["poll_count"] = self.poll_device_count

    def _check_alarms(self) -> None:
        """Check for alarms."""
        self.check_alarms_count += 1


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

    WHY: BaseSupervisoryDevice requires DataStore for registration.
    """
    system_state = SystemState()
    data_store = DataStore(system_state)
    yield data_store


@pytest.fixture
async def test_supervisory(datastore_setup):
    """Create ConcreteSupervisoryDevice instance (not started).

    WHY: Most tests need a supervisory device instance.
    """
    data_store = datastore_setup
    device = ConcreteSupervisoryDevice(
        device_name="test_supervisory_1",
        device_id=1,
        data_store=data_store,
        description="Test supervisory device for unit testing",
        scan_interval=0.01,  # Fast for testing
    )

    yield device

    # Cleanup
    if device.is_running():
        await device.stop()


@pytest.fixture
async def started_supervisory(test_supervisory):
    """Create and start a ConcreteSupervisoryDevice.

    WHY: Many tests need a running supervisory device.
    """
    await test_supervisory.start()
    yield test_supervisory

    # Cleanup
    if test_supervisory.is_running():
        await test_supervisory.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestBaseSupervisoryDeviceInitialization:
    """Test supervisory device initialization."""

    def test_init_with_defaults(self, datastore_setup):
        """Test initialising with default parameters.

        WHY: Verify sensible defaults for supervisory devices.
        """
        data_store = datastore_setup
        device = ConcreteSupervisoryDevice(
            device_name="test_device",
            device_id=1,
            data_store=data_store,
        )

        assert device.device_name == "test_device"
        assert device.device_id == 1
        assert device.scan_interval == 0.1  # Default 100ms
        assert not device.is_online()
        assert not device.is_running()

    def test_init_with_custom_scan_interval(self, datastore_setup):
        """Test initialising with custom scan interval.

        WHY: Different supervisory devices may need different scan rates.
        """
        data_store = datastore_setup
        device = ConcreteSupervisoryDevice(
            device_name="fast_device",
            device_id=2,
            data_store=data_store,
            scan_interval=0.05,
        )

        assert device.scan_interval == 0.05

    def test_device_type_is_supervisory(self, test_supervisory):
        """Test that _device_type() returns 'supervisory'.

        WHY: Supervisory devices must identify correctly.
        """
        assert test_supervisory._device_type() == "supervisory"

    def test_initial_poll_targets_empty(self, test_supervisory):
        """Test that poll targets are initially empty.

        WHY: No devices configured by default.
        """
        assert len(test_supervisory.poll_targets) == 0

    def test_polling_enabled_by_default(self, test_supervisory):
        """Test that polling is enabled by default.

        WHY: Supervisory devices should poll by default.
        """
        assert test_supervisory.polling_enabled is True

    def test_initial_statistics(self, test_supervisory):
        """Test that statistics are initialised to zero.

        WHY: No polls have occurred yet.
        """
        assert test_supervisory.total_polls == 0
        assert test_supervisory.failed_polls == 0


# ================================================================
# POLL TARGET MANAGEMENT TESTS
# ================================================================
class TestBaseSupervisoryDevicePollTargets:
    """Test poll target management."""

    def test_add_poll_target(self, test_supervisory):
        """Test adding a poll target.

        WHY: Must be able to configure devices to poll.
        """
        test_supervisory.add_poll_target(
            device_name="plc_1",
            protocol="modbus",
            poll_rate_s=1.0,
        )

        assert "plc_1" in test_supervisory.poll_targets
        target = test_supervisory.poll_targets["plc_1"]
        assert target.device_name == "plc_1"
        assert target.protocol == "modbus"
        assert target.poll_rate_s == 1.0
        assert target.enabled is True

    def test_add_poll_target_disabled(self, test_supervisory):
        """Test adding a disabled poll target.

        WHY: Targets can be configured but not polled.
        """
        test_supervisory.add_poll_target(
            device_name="plc_disabled",
            protocol="modbus",
            enabled=False,
        )

        assert test_supervisory.poll_targets["plc_disabled"].enabled is False

    def test_add_multiple_poll_targets(self, test_supervisory):
        """Test adding multiple poll targets.

        WHY: Supervisory devices poll many devices.
        """
        test_supervisory.add_poll_target("plc_1", "modbus", poll_rate_s=1.0)
        test_supervisory.add_poll_target("rtu_1", "dnp3", poll_rate_s=5.0)
        test_supervisory.add_poll_target("ied_1", "iec104", poll_rate_s=0.5)

        assert len(test_supervisory.poll_targets) == 3

    def test_remove_poll_target(self, test_supervisory):
        """Test removing a poll target.

        WHY: Should be able to remove devices.
        """
        test_supervisory.add_poll_target("plc_1", "modbus")
        result = test_supervisory.remove_poll_target("plc_1")

        assert result is True
        assert "plc_1" not in test_supervisory.poll_targets

    def test_remove_nonexistent_poll_target(self, test_supervisory):
        """Test removing a nonexistent poll target.

        WHY: Should handle missing targets gracefully.
        """
        result = test_supervisory.remove_poll_target("nonexistent")
        assert result is False

    def test_enable_poll_target(self, test_supervisory):
        """Test enabling a poll target.

        WHY: Targets can be enabled/disabled dynamically.
        """
        test_supervisory.add_poll_target("plc_1", "modbus", enabled=False)
        assert test_supervisory.poll_targets["plc_1"].enabled is False

        result = test_supervisory.enable_poll_target("plc_1", enabled=True)
        assert result is True
        assert test_supervisory.poll_targets["plc_1"].enabled is True

    def test_disable_poll_target(self, test_supervisory):
        """Test disabling a poll target.

        WHY: Operators may need to stop polling a device.
        """
        test_supervisory.add_poll_target("plc_1", "modbus")
        result = test_supervisory.enable_poll_target("plc_1", enabled=False)

        assert result is True
        assert test_supervisory.poll_targets["plc_1"].enabled is False

    def test_enable_nonexistent_poll_target(self, test_supervisory):
        """Test enabling a nonexistent poll target.

        WHY: Should handle missing targets gracefully.
        """
        result = test_supervisory.enable_poll_target("nonexistent", enabled=True)
        assert result is False


# ================================================================
# POLL TIMING TESTS
# ================================================================
class TestBaseSupervisoryDevicePollTiming:
    """Test poll timing logic."""

    def test_is_poll_due_first_poll(self, test_supervisory):
        """Test that first poll is always due.

        WHY: Devices should be polled immediately on start.
        """
        target = PollTarget(
            device_name="test",
            protocol="modbus",
            poll_rate_s=1.0,
            last_poll_time=0.0,
        )

        is_due = test_supervisory._is_poll_due(target, current_time=0.0)
        assert is_due is True

    def test_is_poll_due_not_elapsed(self, test_supervisory):
        """Test that poll is not due before interval elapsed.

        WHY: Respect configured poll rate.
        """
        target = PollTarget(
            device_name="test",
            protocol="modbus",
            poll_rate_s=1.0,
            last_poll_time=10.0,
        )

        # Only 0.5 seconds elapsed
        is_due = test_supervisory._is_poll_due(target, current_time=10.5)
        assert is_due is False

    def test_is_poll_due_elapsed(self, test_supervisory):
        """Test that poll is due after interval elapsed.

        WHY: Poll when interval has passed.
        """
        target = PollTarget(
            device_name="test",
            protocol="modbus",
            poll_rate_s=1.0,
            last_poll_time=10.0,
        )

        # 1.5 seconds elapsed
        is_due = test_supervisory._is_poll_due(target, current_time=11.5)
        assert is_due is True

    def test_is_poll_due_exact_interval(self, test_supervisory):
        """Test poll due at exact interval boundary.

        WHY: Should poll when exactly at interval.
        """
        target = PollTarget(
            device_name="test",
            protocol="modbus",
            poll_rate_s=1.0,
            last_poll_time=10.0,
        )

        is_due = test_supervisory._is_poll_due(target, current_time=11.0)
        assert is_due is True


# ================================================================
# SCAN CYCLE TESTS
# ================================================================
class TestBaseSupervisoryDeviceScanCycle:
    """Test scan cycle execution."""

    @pytest.mark.asyncio
    async def test_scan_cycle_polls_due_devices(self, started_supervisory):
        """Test that scan cycle polls devices that are due.

        WHY: Devices should be polled at their configured rates.
        """
        started_supervisory.add_poll_target("plc_1", "modbus", poll_rate_s=0.01)

        # Wait for scan cycles
        await asyncio.sleep(0.03)

        assert started_supervisory.poll_device_count > 0
        assert "plc_1" in started_supervisory.polled_targets

    @pytest.mark.asyncio
    async def test_scan_cycle_skips_disabled_targets(self, started_supervisory):
        """Test that scan cycle skips disabled targets.

        WHY: Disabled targets should not be polled.
        """
        started_supervisory.add_poll_target("plc_1", "modbus", enabled=False)

        await asyncio.sleep(0.03)

        assert "plc_1" not in started_supervisory.polled_targets

    @pytest.mark.asyncio
    async def test_scan_cycle_processes_data(self, started_supervisory):
        """Test that scan cycle processes polled data.

        WHY: Data must be processed after polling.
        """
        await asyncio.sleep(0.03)

        assert started_supervisory.process_polled_data_count > 0

    @pytest.mark.asyncio
    async def test_scan_cycle_checks_alarms(self, started_supervisory):
        """Test that scan cycle checks alarms.

        WHY: Alarms must be evaluated each cycle.
        """
        await asyncio.sleep(0.03)

        assert started_supervisory.check_alarms_count > 0

    @pytest.mark.asyncio
    async def test_scan_cycle_respects_polling_disabled(self, started_supervisory):
        """Test that scan cycle respects polling_enabled flag.

        WHY: Global polling disable should stop all polling.
        """
        started_supervisory.add_poll_target("plc_1", "modbus", poll_rate_s=0.01)
        started_supervisory.polling_enabled = False

        initial_count = started_supervisory.poll_device_count
        await asyncio.sleep(0.03)

        # No new polls should have occurred
        assert started_supervisory.poll_device_count == initial_count

    @pytest.mark.asyncio
    async def test_scan_cycle_increments_total_polls(self, started_supervisory):
        """Test that total_polls counter is incremented.

        WHY: Statistics tracking.
        """
        started_supervisory.add_poll_target("plc_1", "modbus", poll_rate_s=0.01)

        await asyncio.sleep(0.03)

        assert started_supervisory.total_polls > 0

    @pytest.mark.asyncio
    async def test_multiple_poll_targets_all_polled(self, started_supervisory):
        """Test that multiple poll targets are all polled.

        WHY: SCADA systems poll multiple devices.
        """
        started_supervisory.add_poll_target("device_a", "modbus", poll_rate_s=0.01)
        started_supervisory.add_poll_target("device_b", "modbus", poll_rate_s=0.01)
        started_supervisory.add_poll_target("device_c", "dnp3", poll_rate_s=0.01)

        await asyncio.sleep(0.05)

        # All devices should be polled
        assert "device_a" in started_supervisory.polled_targets
        assert "device_b" in started_supervisory.polled_targets
        assert "device_c" in started_supervisory.polled_targets


# ================================================================
# STATUS AND DIAGNOSTICS TESTS
# ================================================================
class TestBaseSupervisoryDeviceStatus:
    """Test status and diagnostics."""

    @pytest.mark.asyncio
    async def test_get_supervisory_status_structure(self, started_supervisory):
        """Test that get_supervisory_status returns expected structure.

        WHY: Status API must be consistent.
        """
        started_supervisory.add_poll_target("plc_1", "modbus")

        await asyncio.sleep(0.02)

        status = await started_supervisory.get_supervisory_status()

        # Base status fields
        assert "device_name" in status
        assert "device_type" in status
        assert "scan_count" in status

        # Supervisory-specific fields
        assert "polling_enabled" in status
        assert "poll_target_count" in status
        assert "total_polls" in status
        assert "failed_polls" in status
        assert "poll_success_rate" in status
        assert "poll_targets" in status

    @pytest.mark.asyncio
    async def test_get_supervisory_status_values(self, started_supervisory):
        """Test that status values are accurate.

        WHY: Status must reflect actual state.
        """
        started_supervisory.add_poll_target("plc_1", "modbus", poll_rate_s=0.01)
        started_supervisory.add_poll_target("plc_2", "modbus", poll_rate_s=0.01)

        await asyncio.sleep(0.03)

        status = await started_supervisory.get_supervisory_status()

        assert status["polling_enabled"] is True
        assert status["poll_target_count"] == 2
        assert status["total_polls"] > 0
        assert "plc_1" in status["poll_targets"]
        assert "plc_2" in status["poll_targets"]

    @pytest.mark.asyncio
    async def test_poll_success_rate_calculation(self, test_supervisory):
        """Test poll success rate calculation.

        WHY: Rate must be calculated correctly.
        """
        test_supervisory.total_polls = 100
        test_supervisory.failed_polls = 10

        status = await test_supervisory.get_supervisory_status()

        assert status["poll_success_rate"] == 90.0

    @pytest.mark.asyncio
    async def test_poll_success_rate_zero_polls(self, test_supervisory):
        """Test poll success rate with zero polls.

        WHY: Should handle division by zero.
        """
        test_supervisory.total_polls = 0
        test_supervisory.failed_polls = 0

        status = await test_supervisory.get_supervisory_status()

        assert status["poll_success_rate"] == 0.0


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestBaseSupervisoryDeviceIntegration:
    """Test integration with dependencies."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, test_supervisory, datastore_setup):
        """Test that device registers with DataStore.

        WHY: Devices must be accessible via DataStore.
        """
        data_store = datastore_setup

        await test_supervisory.start()

        devices = await data_store.get_devices_by_type("supervisory")
        assert len(devices) == 1
        assert devices[0].device_name == "test_supervisory_1"

    @pytest.mark.asyncio
    async def test_memory_accessible_via_datastore(
        self, started_supervisory, datastore_setup
    ):
        """Test that memory is accessible via DataStore.

        WHY: Other devices may need to access data.
        """
        data_store = datastore_setup

        await asyncio.sleep(0.02)

        memory = await data_store.bulk_read_memory("test_supervisory_1")
        assert memory is not None
        assert "status" in memory

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, test_supervisory):
        """Test complete device lifecycle.

        WHY: Verify end-to-end operation.
        """
        # 1. Start
        await test_supervisory.start()
        assert test_supervisory.is_online()
        assert test_supervisory.is_running()

        # 2. Run
        await asyncio.sleep(0.03)
        assert test_supervisory.metadata["scan_count"] > 0

        # 3. Reset
        await test_supervisory.reset()
        assert test_supervisory.metadata["scan_count"] == 0
        assert test_supervisory.is_running()

        # 4. Stop
        await test_supervisory.stop()
        assert not test_supervisory.is_online()
        assert not test_supervisory.is_running()


# ================================================================
# POLL TARGET DATACLASS TESTS
# ================================================================
class TestPollTarget:
    """Test PollTarget dataclass."""

    def test_poll_target_defaults(self):
        """Test PollTarget default values.

        WHY: Verify sensible defaults.
        """
        target = PollTarget(device_name="test", protocol="modbus")

        assert target.poll_rate_s == 1.0
        assert target.enabled is True
        assert target.last_poll_time == 0.0
        assert target.last_poll_success is False
        assert target.consecutive_failures == 0

    def test_poll_target_custom_values(self):
        """Test PollTarget with custom values.

        WHY: Should accept custom configuration.
        """
        target = PollTarget(
            device_name="custom",
            protocol="dnp3",
            poll_rate_s=5.0,
            enabled=False,
        )

        assert target.device_name == "custom"
        assert target.protocol == "dnp3"
        assert target.poll_rate_s == 5.0
        assert target.enabled is False


# ================================================================
# CONCURRENT OPERATIONS TESTS
# ================================================================
class TestBaseSupervisoryDeviceConcurrency:
    """Test concurrent operations."""

    @pytest.mark.asyncio
    async def test_multiple_instances(self, datastore_setup):
        """Test multiple supervisory devices operating concurrently.

        WHY: Systems may have multiple supervisory devices.
        """
        data_store = datastore_setup

        devices = [
            ConcreteSupervisoryDevice(f"sup_{i}", i, data_store, scan_interval=0.01)
            for i in range(3)
        ]

        # Start all
        await asyncio.gather(*[d.start() for d in devices])

        # Let them run
        await asyncio.sleep(0.05)

        # All should be running
        for device in devices:
            assert device.is_running()
            assert device.metadata["scan_count"] > 0

        # Stop all
        await asyncio.gather(*[d.stop() for d in devices])
