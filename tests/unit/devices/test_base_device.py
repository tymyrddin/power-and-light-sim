# tests/unit/devices/test_base_device.py
"""Comprehensive tests for BaseDevice abstract base class.

This is Level 4 in our dependency tree - BaseDevice depends on:
- DataStore (Level 2) - uses REAL DataStore
- SystemState (Level 1) - uses REAL SystemState (via DataStore)
- SimulationTime (Level 0) - uses REAL SimulationTime

Test Coverage:
- Initialization and configuration
- Lifecycle management (start/stop/reset)
- State transitions and consistency
- Scan cycle execution
- Memory map operations
- Error handling and resilience
- Diagnostic metadata tracking
- Integration with dependencies
- Concurrent operations
- Edge cases

BaseDevice is abstract, so we create a concrete test implementation.
"""

import asyncio
import pytest

from components.state.system_state import SystemState
from components.state.data_store import DataStore
from components.devices.core.base_device import BaseDevice
from components.time.simulation_time import SimulationTime


# ================================================================
# TEST DEVICE IMPLEMENTATION
# ================================================================
class ConcreteTestDevice(BaseDevice):
    """Concrete implementation of BaseDevice for testing.

    WHY: BaseDevice is abstract - need concrete class to test.
    Note: Named ConcreteTestDevice (not TestDevice) to avoid pytest collection.
    """

    def __init__(self, device_name: str, device_id: int, data_store: DataStore,
                 description: str = "", scan_interval: float = 0.1):
        super().__init__(device_name, device_id, data_store, description, scan_interval)
        self.scan_cycle_count = 0
        self.scan_cycle_error = None  # Set to exception to simulate errors
        self.initialise_call_count = 0

    def _device_type(self) -> str:
        return "test_device"

    def _supported_protocols(self) -> list[str]:
        return ["modbus", "opcua"]

    async def _initialise_memory_map(self) -> None:
        """Initialize test memory map."""
        self.initialise_call_count += 1
        self.memory_map = {
            "holding_registers[0]": 0,
            "holding_registers[1]": 0,
            "coils[0]": False,
            "coils[1]": False,
        }

    async def _scan_cycle(self) -> None:
        """Execute test scan cycle."""
        self.scan_cycle_count += 1

        # Simulate error if configured
        if self.scan_cycle_error:
            raise self.scan_cycle_error

        # Simple test logic: increment holding register
        current = self.memory_map.get("holding_registers[0]", 0)
        self.memory_map["holding_registers[0]"] = current + 1


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

    WHY: BaseDevice requires DataStore for registration.
    """
    system_state = SystemState()
    data_store = DataStore(system_state)
    return data_store


@pytest.fixture
async def test_device(datastore_setup):
    """Create TestDevice instance (not started).

    WHY: Most tests need a device instance.
    """
    data_store = datastore_setup
    device = ConcreteTestDevice(
        device_name="test_plc_1",
        device_id=1,
        data_store=data_store,
        description="Test PLC for unit testing",
        scan_interval=0.01,  # Fast scan for testing
    )

    yield device

    # Cleanup
    if device.is_running():
        await device.stop()


@pytest.fixture
async def started_device(test_device):
    """Create and start a TestDevice.

    WHY: Many tests need a running device.
    """
    await test_device.start()
    yield test_device

    # Cleanup
    if test_device.is_running():
        await test_device.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestBaseDeviceInitialization:
    """Test device initialization and configuration."""

    def test_init_with_defaults(self, datastore_setup):
        """Test initialization with default parameters.

        WHY: Verify sensible defaults are set.
        """
        data_store = datastore_setup
        device = ConcreteTestDevice(
            device_name="test_device",
            device_id=1,
            data_store=data_store,
        )

        assert device.device_name == "test_device"
        assert device.device_id == 1
        assert device.data_store is data_store
        assert device.description == ""
        assert device.scan_interval == 0.1  # Default
        assert not device.is_online()
        assert not device.is_running()
        assert device.memory_map == {}

    def test_init_with_custom_params(self, datastore_setup):
        """Test initialization with custom parameters.

        WHY: Support flexible device configuration.
        """
        data_store = datastore_setup
        device = ConcreteTestDevice(
            device_name="custom_plc",
            device_id=42,
            data_store=data_store,
            description="Custom test device",
            scan_interval=0.5,
        )

        assert device.device_name == "custom_plc"
        assert device.device_id == 42
        assert device.description == "Custom test device"
        assert device.scan_interval == 0.5

    def test_metadata_initialised(self, test_device):
        """Test that metadata is properly initialised.

        WHY: Metadata provides diagnostics and configuration.
        """
        assert "description" in test_device.metadata
        assert "scan_interval" in test_device.metadata
        assert "last_scan_time" in test_device.metadata
        assert "scan_count" in test_device.metadata
        assert "error_count" in test_device.metadata

        assert test_device.metadata["scan_count"] == 0
        assert test_device.metadata["error_count"] == 0
        assert test_device.metadata["last_scan_time"] is None

    def test_device_type_implemented(self, test_device):
        """Test that _device_type() is implemented.

        WHY: Abstract method must be implemented by subclasses.
        """
        assert test_device._device_type() == "test_device"

    def test_supported_protocols_implemented(self, test_device):
        """Test that _supported_protocols() is implemented.

        WHY: Abstract method must be implemented by subclasses.
        """
        protocols = test_device._supported_protocols()
        assert isinstance(protocols, list)
        assert "modbus" in protocols
        assert "opcua" in protocols


# ================================================================
# LIFECYCLE TESTS
# ================================================================
class TestBaseDeviceLifecycle:
    """Test device lifecycle management (start/stop/reset)."""

    @pytest.mark.asyncio
    async def test_start_registers_device(self, test_device, datastore_setup):
        """Test that start() registers device with DataStore.

        WHY: DataStore registration enables protocol access.
        """
        data_store = datastore_setup

        await test_device.start()

        # Verify device is registered
        devices = await data_store.get_devices_by_type("test_device")
        assert len(devices) == 1
        assert devices[0].device_name == "test_plc_1"

    @pytest.mark.asyncio
    async def test_start_initialises_memory_map(self, test_device):
        """Test that start() initialises memory map.

        WHY: Memory map must be ready for protocol access.
        """
        await test_device.start()

        assert test_device.initialise_call_count == 1
        assert len(test_device.memory_map) > 0
        assert "holding_registers[0]" in test_device.memory_map

    @pytest.mark.asyncio
    async def test_start_marks_online(self, test_device):
        """Test that start() sets device online.

        WHY: Online status indicates device availability.
        """
        assert not test_device.is_online()

        await test_device.start()

        assert test_device.is_online()
        assert test_device.is_running()

    @pytest.mark.asyncio
    async def test_start_begins_scan_cycle(self, test_device):
        """Test that start() begins executing scan cycles.

        WHY: Scan cycle is core device operation.
        """
        await test_device.start()

        # Wait for at least one scan cycle
        await asyncio.sleep(0.05)  # Wait 5x scan interval

        assert test_device.scan_cycle_count > 0

    @pytest.mark.asyncio
    async def test_start_idempotent(self, started_device):
        """Test that calling start() on running device is safe.

        WHY: Prevent double-start errors.
        """
        # Device already started
        assert started_device.is_running()

        # Start again
        await started_device.start()

        # Should still be running (no error)
        assert started_device.is_running()

    @pytest.mark.asyncio
    async def test_stop_cancels_scan_cycle(self, started_device):
        """Test that stop() stops scan cycle execution.

        WHY: Stop must halt all device activity.
        """
        # Device is running and scanning
        await asyncio.sleep(0.05)
        initial_count = started_device.scan_cycle_count
        assert initial_count > 0

        # Stop device
        await started_device.stop()

        # Wait and verify no more scans
        await asyncio.sleep(0.05)
        final_count = started_device.scan_cycle_count

        assert final_count == initial_count  # No new scans

    @pytest.mark.asyncio
    async def test_stop_marks_offline(self, started_device):
        """Test that stop() marks device offline.

        WHY: Offline status indicates device unavailability.
        """
        assert started_device.is_online()

        await started_device.stop()

        assert not started_device.is_online()
        assert not started_device.is_running()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self, test_device):
        """Test that calling stop() on stopped device is safe.

        WHY: Prevent double-stop errors.
        """
        # Device not started
        assert not test_device.is_running()

        # Stop anyway
        await test_device.stop()

        # Should still be stopped (no error)
        assert not test_device.is_running()

    @pytest.mark.asyncio
    async def test_reset_reinitialises_device(self, started_device):
        """Test that reset() reinitialises device state.

        WHY: Reset should return to factory state.
        """
        # Run device to accumulate state
        await asyncio.sleep(0.05)
        assert started_device.scan_cycle_count > 0

        # Device was initialised once during start
        assert started_device.initialise_call_count == 1

        # Reset
        await started_device.reset()

        # Memory map reinitialised twice more:
        # - Once directly in reset()
        # - Once when reset() calls start()
        assert started_device.initialise_call_count == 3

        # Device running again
        assert started_device.is_running()

    @pytest.mark.asyncio
    async def test_reset_clears_diagnostics(self, started_device):
        """Test that reset() clears diagnostic counters.

        WHY: Reset should provide clean slate.
        """
        # Accumulate diagnostics
        await asyncio.sleep(0.05)
        assert started_device.metadata["scan_count"] > 0

        # Reset
        await started_device.reset()

        # Diagnostics cleared
        assert started_device.metadata["scan_count"] == 0
        assert started_device.metadata["error_count"] == 0
        assert started_device.metadata["last_scan_time"] is None


# ================================================================
# MEMORY MAP TESTS
# ================================================================
class TestBaseDeviceMemoryMap:
    """Test memory map operations."""

    @pytest.mark.asyncio
    async def test_read_memory_existing_address(self, started_device):
        """Test reading from valid memory address.

        WHY: Core protocol interface functionality.
        """
        value = started_device.read_memory("holding_registers[0]")
        assert value is not None
        assert isinstance(value, int)

    @pytest.mark.asyncio
    async def test_read_memory_invalid_address(self, started_device):
        """Test reading from invalid memory address.

        WHY: Must handle invalid addresses gracefully.
        """
        value = started_device.read_memory("invalid_address")
        assert value is None

    @pytest.mark.asyncio
    async def test_write_memory_existing_address(self, started_device):
        """Test writing to valid memory address.

        WHY: Protocols must be able to write to device.
        """
        success = started_device.write_memory("holding_registers[0]", 42)

        assert success
        assert started_device.memory_map["holding_registers[0]"] == 42

    @pytest.mark.asyncio
    async def test_write_memory_invalid_address(self, started_device):
        """Test writing to invalid memory address.

        WHY: Must reject invalid addresses.
        """
        success = started_device.write_memory("invalid_address", 42)

        assert not success
        assert "invalid_address" not in started_device.memory_map

    @pytest.mark.asyncio
    async def test_bulk_read_memory(self, started_device):
        """Test reading entire memory map.

        WHY: Efficient full snapshot for diagnostics.
        """
        snapshot = started_device.bulk_read_memory()

        assert isinstance(snapshot, dict)
        assert len(snapshot) == len(started_device.memory_map)
        assert "holding_registers[0]" in snapshot

        # Verify it's a copy (not reference)
        snapshot["holding_registers[0]"] = 999
        assert started_device.memory_map["holding_registers[0]"] != 999

    @pytest.mark.asyncio
    async def test_bulk_write_memory_all_valid(self, started_device):
        """Test bulk writing to all valid addresses.

        WHY: Efficient batch updates from protocols.
        """
        updates = {
            "holding_registers[0]": 100,
            "holding_registers[1]": 200,
            "coils[0]": True,
        }

        success = started_device.bulk_write_memory(updates)

        assert success
        assert started_device.memory_map["holding_registers[0]"] == 100
        assert started_device.memory_map["holding_registers[1]"] == 200
        assert started_device.memory_map["coils[0]"] is True

    @pytest.mark.asyncio
    async def test_bulk_write_memory_partial_invalid(self, started_device):
        """Test bulk writing with some invalid addresses.

        WHY: Must handle partial failures gracefully.
        """
        updates = {
            "holding_registers[0]": 100,
            "invalid_address": 999,
        }

        success = started_device.bulk_write_memory(updates)

        assert not success  # Partial failure
        assert started_device.memory_map["holding_registers[0]"] == 100
        assert "invalid_address" not in started_device.memory_map


# ================================================================
# SCAN CYCLE TESTS
# ================================================================
class TestBaseDeviceScanCycle:
    """Test scan cycle execution and timing."""

    @pytest.mark.asyncio
    async def test_scan_cycle_executes_periodically(self, started_device):
        """Test that scan cycles execute at configured interval.

        WHY: Scan timing is critical for real-time simulation.
        """
        initial_count = started_device.scan_cycle_count

        # Wait for ~3 scan intervals
        await asyncio.sleep(0.03)

        final_count = started_device.scan_cycle_count

        # Should have executed at least 2 scans (allow for timing variance)
        assert final_count >= initial_count + 2

    @pytest.mark.asyncio
    async def test_scan_cycle_updates_memory_map(self, started_device):
        """Test that scan cycle modifies memory map.

        WHY: Scan cycle writes device state to memory.
        """
        initial_value = started_device.memory_map["holding_registers[0]"]

        # Wait for scan cycles
        await asyncio.sleep(0.03)

        final_value = started_device.memory_map["holding_registers[0]"]

        # Test device increments this register each scan
        assert final_value > initial_value

    @pytest.mark.asyncio
    async def test_scan_cycle_writes_to_datastore(self, started_device, datastore_setup):
        """Test that scan cycle writes memory to DataStore.

        WHY: DataStore must reflect current device state.
        """
        data_store = datastore_setup

        # Wait for scan cycles
        await asyncio.sleep(0.03)

        # Read from DataStore
        value = await data_store.read_memory("test_plc_1", "holding_registers[0]")

        # Should reflect scan cycle updates
        assert value > 0

    @pytest.mark.asyncio
    async def test_scan_cycle_updates_diagnostics(self, started_device):
        """Test that scan cycle updates diagnostic metadata.

        WHY: Diagnostics track device health.
        """
        # Wait for scan cycles
        await asyncio.sleep(0.03)

        assert started_device.metadata["scan_count"] > 0
        assert started_device.metadata["last_scan_time"] is not None

    @pytest.mark.asyncio
    async def test_scan_cycle_respects_simulation_pause(self, started_device, clean_simulation_time):
        """Test that scan cycle stops when simulation paused.

        WHY: Time-mode awareness is critical.
        """
        # Run normally
        await asyncio.sleep(0.02)
        count_before_pause = started_device.scan_cycle_count

        # Pause simulation
        await clean_simulation_time.pause()

        # Wait
        await asyncio.sleep(0.02)
        count_during_pause = started_device.scan_cycle_count

        # Resume
        await clean_simulation_time.resume()

        # Scans should have stopped during pause
        assert count_during_pause == count_before_pause


# ================================================================
# ERROR HANDLING TESTS
# ================================================================
class TestBaseDeviceErrorHandling:
    """Test error handling and resilience."""

    @pytest.mark.asyncio
    async def test_start_failure_cleanup(self, test_device, datastore_setup):
        """Test that start() failures cleanup properly.

        WHY: Failed start should not leave device in inconsistent state.
        """
        # Make initialise_memory_map fail
        original_init = test_device._initialise_memory_map

        async def failing_init():
            raise RuntimeError("Simulated initialisation failure")

        test_device._initialise_memory_map = failing_init

        # Start should fail
        with pytest.raises(RuntimeError):
            await test_device.start()

        # Device should be in clean state
        assert not test_device.is_online()
        assert not test_device.is_running()

        # Restore and verify device can still start
        test_device._initialise_memory_map = original_init
        await test_device.start()
        assert test_device.is_running()

    @pytest.mark.asyncio
    async def test_scan_cycle_error_continues_running(self, started_device):
        """Test that scan cycle errors don't stop device.

        WHY: Transient errors should not crash device.
        """
        # Configure scan cycle to fail
        started_device.scan_cycle_error = RuntimeError("Simulated scan error")

        # Wait for error to occur
        await asyncio.sleep(0.05)

        # Device should still be running
        assert started_device.is_running()

        # Error count should be incremented
        assert started_device.metadata["error_count"] > 0

        # Clear error and verify recovery
        started_device.scan_cycle_error = None
        initial_count = started_device.scan_cycle_count
        await asyncio.sleep(0.03)

        # Should be scanning again
        assert started_device.scan_cycle_count > initial_count

    @pytest.mark.asyncio
    async def test_datastore_write_error_continues_running(self, started_device, datastore_setup):
        """Test that DataStore write errors don't stop device.

        WHY: DataStore failures should be isolated.
        """
        data_store = datastore_setup

        # Make DataStore writes fail
        original_bulk_write = data_store.bulk_write_memory

        async def failing_bulk_write(*_args, **_kwargs):
            raise RuntimeError("Simulated DataStore failure")

        data_store.bulk_write_memory = failing_bulk_write

        # Wait for error to occur
        await asyncio.sleep(0.05)

        # Device should still be running
        assert started_device.is_running()

        # Error count should increase
        assert started_device.metadata["error_count"] > 0

        # Restore DataStore
        data_store.bulk_write_memory = original_bulk_write


# ================================================================
# STATUS AND DIAGNOSTICS TESTS
# ================================================================
class TestBaseDeviceStatus:
    """Test status reporting and diagnostics."""

    @pytest.mark.asyncio
    async def test_get_status_structure(self, started_device):
        """Test that get_status() returns expected structure.

        WHY: Status API must be consistent.
        """
        status = await started_device.get_status()

        assert isinstance(status, dict)
        assert "device_name" in status
        assert "device_type" in status
        assert "device_id" in status
        assert "online" in status
        assert "running" in status
        assert "scan_interval" in status
        assert "protocols" in status
        assert "memory_map_size" in status
        assert "scan_count" in status
        assert "error_count" in status
        assert "last_scan_time" in status

    @pytest.mark.asyncio
    async def test_get_status_values(self, started_device):
        """Test that get_status() returns accurate values.

        WHY: Status must reflect actual device state.
        """
        await asyncio.sleep(0.03)

        status = await started_device.get_status()

        assert status["device_name"] == "test_plc_1"
        assert status["device_type"] == "test_device"
        assert status["device_id"] == 1
        assert status["online"] is True
        assert status["running"] is True
        assert status["scan_count"] > 0
        assert status["last_scan_time"] is not None

    @pytest.mark.asyncio
    async def test_is_online_reflects_state(self, test_device):
        """Test that is_online() reflects actual state.

        WHY: Online status must be accurate.
        """
        assert not test_device.is_online()

        await test_device.start()
        assert test_device.is_online()

        await test_device.stop()
        assert not test_device.is_online()

    @pytest.mark.asyncio
    async def test_is_running_reflects_state(self, test_device):
        """Test that is_running() reflects actual state.

        WHY: Running status must be accurate.
        """
        assert not test_device.is_running()

        await test_device.start()
        assert test_device.is_running()

        await test_device.stop()
        assert not test_device.is_running()

    def test_repr_format(self, test_device):
        """Test string representation format.

        WHY: Useful for debugging.
        """
        repr_str = repr(test_device)

        assert "TestDevice" in repr_str
        assert "test_plc_1" in repr_str
        assert "ID: 1" in repr_str


# ================================================================
# CONCURRENT OPERATIONS TESTS
# ================================================================
class TestBaseDeviceConcurrency:
    """Test concurrent operations and thread safety."""

    @pytest.mark.asyncio
    async def test_concurrent_memory_writes(self, started_device):
        """Test concurrent writes to memory map.

        WHY: Multiple protocols may write simultaneously.
        """

        async def write_loop(address: str, start_value: int):
            for i in range(10):
                started_device.write_memory(address, start_value + i)
                await asyncio.sleep(0.001)

        # Concurrent writes to different addresses
        await asyncio.gather(
            write_loop("holding_registers[0]", 0),
            write_loop("holding_registers[1]", 100),
        )

        # Both should have completed
        assert started_device.memory_map["holding_registers[0]"] >= 0
        assert started_device.memory_map["holding_registers[1]"] >= 100

    @pytest.mark.asyncio
    async def test_multiple_device_instances(self, datastore_setup):
        """Test multiple device instances operating concurrently.

        WHY: Simulation has many devices.
        """
        data_store = datastore_setup

        # Create multiple devices
        devices = [
            ConcreteTestDevice(f"device_{i}", i, data_store, scan_interval=0.01)
            for i in range(3)
        ]

        # Start all
        await asyncio.gather(*[d.start() for d in devices])

        # Let them run
        await asyncio.sleep(0.05)

        # All should be scanning
        for device in devices:
            assert device.scan_cycle_count > 0

        # Stop all
        await asyncio.gather(*[d.stop() for d in devices])


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestBaseDeviceIntegration:
    """Test integration with dependencies."""

    @pytest.mark.asyncio
    async def test_datastore_integration(self, started_device, datastore_setup):
        """Test complete DataStore integration workflow.

        WHY: Verify full integration with DataStore.
        """
        data_store = datastore_setup

        # Wait for scans
        await asyncio.sleep(0.03)

        # Device should be registered
        devices = await data_store.get_devices_by_type("test_device")
        assert len(devices) == 1

        # Memory should be accessible via DataStore
        value = await data_store.read_memory("test_plc_1", "holding_registers[0]")
        assert value is not None

        # Writes via DataStore should update the DataStore's copy
        await data_store.write_memory("test_plc_1", "holding_registers[1]", 42)

        # Verify it's in DataStore
        datastore_value = await data_store.read_memory("test_plc_1", "holding_registers[1]")
        assert datastore_value == 42

    @pytest.mark.asyncio
    async def test_simulation_time_integration(self, started_device, clean_simulation_time):
        """Test integration with SimulationTime.

        WHY: Devices must respect simulation time control.
        """
        # Device uses sim_time for timestamps
        await asyncio.sleep(0.02)

        last_scan = started_device.metadata["last_scan_time"]
        assert last_scan is not None

        # Timestamp should come from SimulationTime
        assert isinstance(last_scan, float)

    @pytest.mark.asyncio
    async def test_complete_device_lifecycle_workflow(self, test_device):
        """Test complete device operational lifecycle.

        WHY: Verify end-to-end workflow.
        """
        # 1. Start device
        await test_device.start()
        assert test_device.is_online()

        # 2. Let it run
        await asyncio.sleep(0.03)
        assert test_device.metadata["scan_count"] > 0

        # 3. Modify memory via protocol
        test_device.write_memory("coils[0]", True)
        assert test_device.memory_map["coils[0]"] is True

        # 4. Reset device
        await test_device.reset()
        assert test_device.metadata["scan_count"] == 0
        assert test_device.is_running()

        # 5. Stop device
        await test_device.stop()
        assert not test_device.is_online()
        assert not test_device.is_running()
