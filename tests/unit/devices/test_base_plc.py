# tests/unit/devices/test_base_plc.py
"""Comprehensive tests for BasePLC abstract base class.

This is Level 5 in our dependency tree - BasePLC depends on:
- BaseDevice (Level 4) - uses REAL BaseDevice
- DataStore (Level 2) - uses REAL DataStore
- SystemState (Level 1) - uses REAL SystemState (via DataStore)
- SimulationTime (Level 0) - uses REAL SimulationTime

Test Coverage:
- Initialization and configuration
- PLC scan cycle pattern (Read → Execute → Write)
- Integration with BaseDevice diagnostics
- Abstract method enforcement
- Error handling in scan cycle
- Status reporting
- Integration with dependencies
"""

import asyncio

import pytest

from components.devices.control_zone.plc.generic.base_plc import BasePLC
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


# ================================================================
# TEST PLC IMPLEMENTATION
# ================================================================
class ConcretePLC(BasePLC):
    """Concrete implementation of BasePLC for testing.

    WHY: BasePLC is abstract - need concrete class to test.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_inputs_count = 0
        self.execute_logic_count = 0
        self.write_outputs_count = 0
        self.read_inputs_error = None  # Set to exception to simulate errors

    def _supported_protocols(self) -> list[str]:
        return ["modbus"]

    async def _initialise_memory_map(self) -> None:
        """Initialise test PLC memory map."""
        self.memory_map = {
            "holding_registers[0]": 0,  # Input from process
            "holding_registers[1]": 0,  # Output to process
            "coils[0]": False,  # Control output
        }

    async def _read_inputs(self) -> None:
        """Read inputs from process."""
        self.read_inputs_count += 1
        if self.read_inputs_error:
            raise self.read_inputs_error
        # Simulate reading from process
        self.memory_map["holding_registers[0]"] = self.read_inputs_count

    async def _execute_logic(self) -> None:
        """Execute control logic."""
        self.execute_logic_count += 1
        # Simple logic: output = input + 10
        input_val = self.memory_map["holding_registers[0]"]
        self.memory_map["holding_registers[1]"] = input_val + 10

    async def _write_outputs(self) -> None:
        """Write outputs to process."""
        self.write_outputs_count += 1
        # Simulate writing to process (activate coil if output > 50)
        output_val = self.memory_map["holding_registers[1]"]
        self.memory_map["coils[0]"] = output_val > 50


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

    WHY: BasePLC requires DataStore for registration.
    """
    system_state = SystemState()
    data_store = DataStore(system_state)
    return data_store


@pytest.fixture
async def test_plc(datastore_setup):
    """Create ConcretePLC instance (not started).

    WHY: Most tests need a PLC instance.
    """
    data_store = datastore_setup
    plc = ConcretePLC(
        device_name="test_plc_1",
        device_id=1,
        data_store=data_store,
        description="Test PLC for unit testing",
        scan_interval=0.01,  # Fast scan for testing
    )

    yield plc

    # Cleanup
    if plc.is_running():
        await plc.stop()


@pytest.fixture
async def started_plc(test_plc):
    """Create and start a ConcretePLC.

    WHY: Many tests need a running PLC.
    """
    await test_plc.start()
    yield test_plc

    # Cleanup
    if test_plc.is_running():
        await test_plc.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestBasePLCInitialization:
    """Test PLC initialisation."""

    def test_init_with_defaults(self, datastore_setup):
        """Test initialising PLC with default parameters.

        WHY: Verify sensible defaults for PLCs.
        """
        data_store = datastore_setup
        plc = ConcretePLC(
            device_name="test_plc",
            device_id=1,
            data_store=data_store,
        )

        assert plc.device_name == "test_plc"
        assert plc.device_id == 1
        assert plc.scan_interval == 0.1  # PLC default (100ms)
        assert not plc.is_online()
        assert not plc.is_running()

    def test_init_with_custom_scan_interval(self, datastore_setup):
        """Test initialising PLC with custom scan rate.

        WHY: Different PLCs have different scan rates.
        """
        data_store = datastore_setup
        plc = ConcretePLC(
            device_name="fast_plc",
            device_id=2,
            data_store=data_store,
            scan_interval=0.05,  # 50ms scan
        )

        assert plc.scan_interval == 0.05

    def test_device_type_is_plc(self, test_plc):
        """Test that _device_type() returns 'plc'.

        WHY: PLCs must identify as 'plc' type.
        """
        assert test_plc._device_type() == "plc"

    def test_no_duplicate_diagnostics(self, test_plc):
        """Test that BasePLC doesn't duplicate BaseDevice diagnostics.

        WHY: Should use BaseDevice.metadata, not create duplicates.
        """
        # Should NOT have these attributes (would be duplicates)
        assert not hasattr(test_plc, "scan_count")
        assert not hasattr(test_plc, "error_count")
        assert not hasattr(test_plc, "last_scan_time")

        # Should use metadata from BaseDevice
        assert "scan_count" in test_plc.metadata
        assert "error_count" in test_plc.metadata
        assert "last_scan_time" in test_plc.metadata


# ================================================================
# SCAN CYCLE TESTS
# ================================================================
class TestBasePLCScanCycle:
    """Test PLC scan cycle execution."""

    @pytest.mark.asyncio
    async def test_scan_cycle_order(self, started_plc):
        """Test that scan cycle executes in correct order.

        WHY: PLC scan must follow Read → Execute → Write pattern.
        """
        # Wait for at least one scan
        await asyncio.sleep(0.03)

        # All three phases should have executed
        assert started_plc.read_inputs_count > 0
        assert started_plc.execute_logic_count > 0
        assert started_plc.write_outputs_count > 0

        # Counts should be equal (one scan = one of each)
        assert started_plc.read_inputs_count == started_plc.execute_logic_count
        assert started_plc.execute_logic_count == started_plc.write_outputs_count

    @pytest.mark.asyncio
    async def test_scan_cycle_updates_memory_map(self, started_plc):
        """Test that scan cycle modifies memory map.

        WHY: Control logic must update process I/O.
        """
        initial_input = started_plc.memory_map["holding_registers[0]"]

        # Wait for scans
        await asyncio.sleep(0.03)

        final_input = started_plc.memory_map["holding_registers[0]"]

        # Input should have changed (increments each scan)
        assert final_input > initial_input

    @pytest.mark.asyncio
    async def test_scan_cycle_executes_logic(self, started_plc):
        """Test that control logic is executed.

        WHY: PLCs must run control algorithms.
        """
        await asyncio.sleep(0.03)

        # Logic should have executed (output = input + 10)
        input_val = started_plc.memory_map["holding_registers[0]"]
        output_val = started_plc.memory_map["holding_registers[1]"]

        assert output_val == input_val + 10

    @pytest.mark.asyncio
    async def test_scan_cycle_periodic_execution(self, started_plc):
        """Test that scan cycles execute periodically.

        WHY: PLCs must scan at configured rate.
        """
        initial_count = started_plc.read_inputs_count

        # Wait for ~3 scan intervals
        await asyncio.sleep(0.03)

        final_count = started_plc.read_inputs_count

        # Should have executed at least 2 scans
        assert final_count >= initial_count + 2

    @pytest.mark.asyncio
    async def test_scan_uses_basedevice_diagnostics(self, started_plc):
        """Test that scan cycle uses BaseDevice diagnostic tracking.

        WHY: Should not duplicate diagnostic tracking.
        """
        # Wait for scans
        await asyncio.sleep(0.03)

        # BaseDevice metadata should be updated
        assert started_plc.metadata["scan_count"] > 0
        assert started_plc.metadata["last_scan_time"] is not None

        # Should match our scan execution count
        assert started_plc.metadata["scan_count"] == started_plc.read_inputs_count


# ================================================================
# ERROR HANDLING TESTS
# ================================================================
class TestBasePLCErrorHandling:
    """Test error handling in PLC operations."""

    @pytest.mark.asyncio
    async def test_read_inputs_error_continues_running(self, started_plc):
        """Test that errors in _read_inputs() don't stop PLC.

        WHY: Transient errors should not crash PLC.
        """
        # Cause error in read_inputs
        started_plc.read_inputs_error = RuntimeError("Simulated sensor failure")

        # Wait for error to occur
        await asyncio.sleep(0.05)

        # PLC should still be running
        assert started_plc.is_running()

        # Error count should increase
        assert started_plc.metadata["error_count"] > 0

        # Clear error and verify recovery
        started_plc.read_inputs_error = None
        initial_count = started_plc.read_inputs_count
        await asyncio.sleep(0.03)

        # Should be scanning again
        assert started_plc.read_inputs_count > initial_count

    @pytest.mark.asyncio
    async def test_error_increments_basedevice_counter(self, started_plc):
        """Test that errors increment BaseDevice error_count.

        WHY: Should use BaseDevice error tracking, not duplicate.
        """
        initial_errors = started_plc.metadata["error_count"]

        # Cause multiple errors
        started_plc.read_inputs_error = RuntimeError("Test error")
        await asyncio.sleep(0.05)

        final_errors = started_plc.metadata["error_count"]

        # Error count should have increased
        assert final_errors > initial_errors


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestBasePLCIntegration:
    """Test PLC integration with dependencies."""

    @pytest.mark.asyncio
    async def test_plc_registers_with_datastore(self, test_plc, datastore_setup):
        """Test that PLC registers with DataStore.

        WHY: PLCs must be accessible via DataStore.
        """
        data_store = datastore_setup

        await test_plc.start()

        # Verify registered
        devices = await data_store.get_devices_by_type("plc")
        assert len(devices) == 1
        assert devices[0].device_name == "test_plc_1"

    @pytest.mark.asyncio
    async def test_plc_memory_accessible_via_datastore(
        self, started_plc, datastore_setup
    ):
        """Test that PLC memory is accessible via DataStore.

        WHY: Protocols must be able to read/write PLC memory.
        """
        data_store = datastore_setup

        # Wait for scan
        await asyncio.sleep(0.03)

        # Read PLC memory via DataStore (PLC → DataStore direction)
        value = await data_store.read_memory("test_plc_1", "holding_registers[0]")
        assert value is not None
        assert value > 0  # Should have been updated by scans

        # Write via DataStore (DataStore → PLC direction)
        test_value = 999
        await data_store.write_memory("test_plc_1", "holding_registers[1]", test_value)

        # Verify write persisted in DataStore
        read_back = await data_store.read_memory("test_plc_1", "holding_registers[1]")
        assert read_back == test_value

        # Note: PLC's next scan will overwrite this with computed value,
        # which is correct PLC behaviour (control logic has authority over outputs)

    @pytest.mark.asyncio
    async def test_complete_plc_lifecycle(self, test_plc):
        """Test complete PLC operational lifecycle.

        WHY: Verify end-to-end PLC operation.
        """
        # 1. Start PLC
        await test_plc.start()
        assert test_plc.is_online()
        assert test_plc.is_running()

        # 2. Let it run and execute scans
        await asyncio.sleep(0.03)
        assert test_plc.read_inputs_count > 0
        assert test_plc.metadata["scan_count"] > 0

        # 3. Reset PLC
        await test_plc.reset()
        assert test_plc.metadata["scan_count"] == 0
        assert test_plc.is_running()

        # 4. Stop PLC
        await test_plc.stop()
        assert not test_plc.is_online()
        assert not test_plc.is_running()

    @pytest.mark.asyncio
    async def test_status_includes_base_diagnostics(self, started_plc):
        """Test that get_status() includes BaseDevice diagnostics.

        WHY: Should use base status, not duplicate.
        """
        await asyncio.sleep(0.03)

        status = await started_plc.get_status()

        # Should include BaseDevice diagnostics
        assert "scan_count" in status
        assert "error_count" in status
        assert "last_scan_time" in status
        assert status["scan_count"] > 0


# ================================================================
# MEMORY MAP TESTS
# ================================================================
class TestBasePLCMemoryMap:
    """Test PLC memory map operations."""

    @pytest.mark.asyncio
    async def test_memory_map_no_diagnostic_pollution(self, started_plc):
        """Test that memory map doesn't contain diagnostic keys.

        WHY: Protocol memory should be clean, no underscore keys.
        """
        await asyncio.sleep(0.03)

        # Check for underscore keys (diagnostic pollution)
        underscore_keys = [
            k for k in started_plc.memory_map.keys() if k.startswith("_")
        ]

        # Should have no underscore keys
        assert len(underscore_keys) == 0

    @pytest.mark.asyncio
    async def test_memory_map_contains_only_protocol_data(self, started_plc):
        """Test that memory map contains only protocol-relevant data.

        WHY: Memory map is the protocol interface.
        """
        # All keys should be protocol addresses
        for key in started_plc.memory_map.keys():
            assert not key.startswith("_")
            # Should look like protocol addresses
            assert "holding_registers" in key or "coils" in key


# ================================================================
# CONCURRENT OPERATIONS TESTS
# ================================================================
class TestBasePLCConcurrency:
    """Test concurrent PLC operations."""

    @pytest.mark.asyncio
    async def test_multiple_plc_instances(self, datastore_setup):
        """Test multiple PLC instances operating concurrently.

        WHY: Simulation may have many PLCs.
        """
        data_store = datastore_setup

        # Create multiple PLCs
        plcs = [
            ConcretePLC(f"plc_{i}", i, data_store, scan_interval=0.01) for i in range(3)
        ]

        # Start all
        await asyncio.gather(*[plc.start() for plc in plcs])

        # Let them run
        await asyncio.sleep(0.05)

        # All should be scanning
        for plc in plcs:
            assert plc.read_inputs_count > 0
            assert plc.metadata["scan_count"] > 0

        # Stop all
        await asyncio.gather(*[plc.stop() for plc in plcs])
