# tests/unit/devices/test_scada_server.py
"""Comprehensive tests for SCADAServer.

This is Level 6 in our dependency tree - SCADAServer depends on:
- BaseSupervisoryDevice (Level 5) - uses REAL BaseSupervisoryDevice
- BaseDevice (Level 4) - uses REAL BaseDevice
- DataStore (Level 2) - uses REAL DataStore
- SystemState (Level 1) - uses REAL SystemState (via DataStore)
- SimulationTime (Level 0) - uses REAL SimulationTime

Test Coverage:
- Initialization and configuration
- Device type and protocol support
- Poll target management
- Tag management
- Polling cycle
- Alarm management
- Memory map structure
- DataStore integration
- Lifecycle management
"""

import asyncio

import pytest

from components.devices.operations_zone.scada_server import (
    Alarm,
    SCADAServer,
    TagDefinition,
)
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


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

    WHY: SCADAServer requires DataStore for registration.
    """
    system_state = SystemState()
    data_store = DataStore(system_state)
    yield data_store


@pytest.fixture
async def test_scada(datastore_setup):
    """Create SCADAServer instance (not started).

    WHY: Most tests need a SCADA server instance.
    """
    data_store = datastore_setup
    scada = SCADAServer(
        device_name="test_scada_1",
        device_id=1,
        data_store=data_store,
        description="Test SCADA server for unit testing",
        scan_interval=0.01,  # Fast for testing
    )

    yield scada

    # Cleanup
    if scada.is_running():
        await scada.stop()


@pytest.fixture
async def started_scada(test_scada):
    """Create and start a SCADAServer.

    WHY: Many tests need a running SCADA server.
    """
    await test_scada.start()
    yield test_scada

    # Cleanup
    if test_scada.is_running():
        await test_scada.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestSCADAServerInitialization:
    """Test SCADA server initialization."""

    def test_init_with_defaults(self, datastore_setup):
        """Test initialising SCADA server with default parameters.

        WHY: Verify sensible defaults for SCADA servers.
        """
        data_store = datastore_setup
        scada = SCADAServer(
            device_name="scada_test",
            device_id=1,
            data_store=data_store,
        )

        assert scada.device_name == "scada_test"
        assert scada.device_id == 1
        assert scada.scan_interval == 0.1  # Default 100ms
        assert not scada.is_online()
        assert not scada.is_running()

    def test_init_with_custom_scan_interval(self, datastore_setup):
        """Test initialising SCADA server with custom scan interval.

        WHY: SCADA servers may need different scan rates.
        """
        data_store = datastore_setup
        scada = SCADAServer(
            device_name="fast_scada",
            device_id=2,
            data_store=data_store,
            scan_interval=0.05,  # 50ms
        )

        assert scada.scan_interval == 0.05

    def test_device_type_is_scada_server(self, test_scada):
        """Test that _device_type() returns 'scada_server'.

        WHY: SCADA servers must identify correctly.
        """
        assert test_scada._device_type() == "scada_server"

    def test_supported_protocols(self, test_scada):
        """Test that SCADA server supports expected protocols.

        WHY: SCADA servers should support multiple protocols.
        """
        protocols = test_scada._supported_protocols()
        assert "modbus" in protocols
        assert "iec104" in protocols
        assert "dnp3" in protocols
        assert "opcua" in protocols

    def test_initial_state(self, test_scada):
        """Test that SCADA server has correct initial state.

        WHY: All state should be initialised properly.
        """
        assert len(test_scada.tags) == 0
        assert len(test_scada.tag_values) == 0
        assert len(test_scada.poll_targets) == 0
        assert len(test_scada.active_alarms) == 0
        assert test_scada.total_polls == 0
        assert test_scada.failed_polls == 0
        assert test_scada.total_alarms == 0
        assert test_scada.polling_enabled is True


# ================================================================
# POLL TARGET TESTS
# ================================================================
class TestSCADAServerPolling:
    """Test SCADA server poll target management."""

    def test_add_poll_target(self, test_scada):
        """Test adding a poll target.

        WHY: SCADA servers must be able to configure polled devices.
        """
        test_scada.add_poll_target(
            device_name="plc_1",
            protocol="modbus",
            poll_rate_s=1.0,
        )

        assert "plc_1" in test_scada.poll_targets
        target = test_scada.poll_targets["plc_1"]
        assert target.device_name == "plc_1"
        assert target.protocol == "modbus"
        assert target.poll_rate_s == 1.0
        assert target.enabled is True

    def test_add_multiple_poll_targets(self, test_scada):
        """Test adding multiple poll targets with different rates.

        WHY: SCADA servers poll many devices at different rates.
        """
        test_scada.add_poll_target("plc_1", "modbus", poll_rate_s=1.0)
        test_scada.add_poll_target("rtu_1", "dnp3", poll_rate_s=5.0)
        test_scada.add_poll_target("ied_1", "iec104", poll_rate_s=0.5)

        assert len(test_scada.poll_targets) == 3
        assert test_scada.poll_targets["plc_1"].poll_rate_s == 1.0
        assert test_scada.poll_targets["rtu_1"].poll_rate_s == 5.0
        assert test_scada.poll_targets["ied_1"].poll_rate_s == 0.5

    def test_remove_poll_target(self, test_scada):
        """Test removing a poll target.

        WHY: SCADA servers should be able to remove devices.
        """
        test_scada.add_poll_target("plc_1", "modbus")
        assert "plc_1" in test_scada.poll_targets

        result = test_scada.remove_poll_target("plc_1")
        assert result is True
        assert "plc_1" not in test_scada.poll_targets

    def test_remove_nonexistent_poll_target(self, test_scada):
        """Test removing a nonexistent poll target.

        WHY: Should handle missing targets gracefully.
        """
        result = test_scada.remove_poll_target("nonexistent")
        assert result is False

    def test_enable_disable_poll_target(self, test_scada):
        """Test enabling/disabling poll targets.

        WHY: SCADA operators may need to disable polling.
        """
        test_scada.add_poll_target("plc_1", "modbus")
        assert test_scada.poll_targets["plc_1"].enabled is True

        # Disable
        result = test_scada.enable_poll_target("plc_1", enabled=False)
        assert result is True
        assert test_scada.poll_targets["plc_1"].enabled is False

        # Re-enable
        result = test_scada.enable_poll_target("plc_1", enabled=True)
        assert result is True
        assert test_scada.poll_targets["plc_1"].enabled is True


# ================================================================
# TAG MANAGEMENT TESTS
# ================================================================
class TestSCADAServerTags:
    """Test SCADA server tag management."""

    def test_add_tag(self, test_scada):
        """Test adding a tag.

        WHY: Tags map device data to named points.
        """
        test_scada.add_tag(
            tag_name="TURB1_SPEED",
            device_name="plc_1",
            address_type="holding_register",
            address=0,
            data_type="float",
            unit="RPM",
        )

        assert "TURB1_SPEED" in test_scada.tags
        tag = test_scada.tags["TURB1_SPEED"]
        assert tag.device_name == "plc_1"
        assert tag.address_type == "holding_register"
        assert tag.address == 0
        assert tag.unit == "RPM"

    def test_add_tag_with_alarms(self, test_scada):
        """Test adding a tag with alarm limits.

        WHY: Tags can have alarm thresholds.
        """
        test_scada.add_tag(
            tag_name="REACTOR_TEMP",
            device_name="plc_1",
            address_type="holding_register",
            address=10,
            alarm_high=350.0,
            alarm_low=100.0,
        )

        tag = test_scada.tags["REACTOR_TEMP"]
        assert tag.alarm_high == 350.0
        assert tag.alarm_low == 100.0

    def test_tag_initial_quality(self, test_scada):
        """Test that new tags have 'uncertain' quality.

        WHY: Tags should be uncertain until polled.
        """
        test_scada.add_tag(
            tag_name="TEST_TAG",
            device_name="plc_1",
            address_type="holding_register",
            address=0,
        )

        assert test_scada.tag_quality["TEST_TAG"] == "uncertain"
        assert test_scada.tag_values["TEST_TAG"] is None

    @pytest.mark.asyncio
    async def test_get_tag_value(self, test_scada):
        """Test getting tag value.

        WHY: Public API for reading tags.
        """
        test_scada.add_tag(
            tag_name="TEST_TAG",
            device_name="plc_1",
            address_type="holding_register",
            address=0,
        )

        # Initially None
        value = await test_scada.get_tag_value("TEST_TAG")
        assert value is None

        # Set a value manually
        test_scada.tag_values["TEST_TAG"] = 42
        value = await test_scada.get_tag_value("TEST_TAG")
        assert value == 42

    @pytest.mark.asyncio
    async def test_get_tag_info(self, test_scada):
        """Test getting complete tag information.

        WHY: Need full tag details for HMI display.
        """
        test_scada.add_tag(
            tag_name="TEST_TAG",
            device_name="plc_1",
            address_type="holding_register",
            address=0,
            description="Test tag",
            unit="units",
        )

        info = await test_scada.get_tag_info("TEST_TAG")
        assert info is not None
        assert info["name"] == "TEST_TAG"
        assert info["quality"] == "uncertain"
        assert isinstance(info["definition"], TagDefinition)

    @pytest.mark.asyncio
    async def test_get_nonexistent_tag_info(self, test_scada):
        """Test getting info for nonexistent tag.

        WHY: Should return None for missing tags.
        """
        info = await test_scada.get_tag_info("NONEXISTENT")
        assert info is None

    @pytest.mark.asyncio
    async def test_get_all_tags(self, test_scada):
        """Test getting all tag values.

        WHY: HMI may need all tags at once.
        """
        test_scada.add_tag("TAG_1", "plc_1", "holding_register", 0)
        test_scada.add_tag("TAG_2", "plc_1", "holding_register", 1)
        test_scada.add_tag("TAG_3", "plc_2", "coil", 0)

        all_tags = await test_scada.get_all_tags()
        assert len(all_tags) == 3
        assert "TAG_1" in all_tags
        assert "TAG_2" in all_tags
        assert "TAG_3" in all_tags


# ================================================================
# ALARM TESTS
# ================================================================
class TestSCADAServerAlarms:
    """Test SCADA server alarm management."""

    def test_raise_high_alarm(self, test_scada):
        """Test raising high alarm.

        WHY: High alarms indicate values above limits.
        """
        test_scada.add_tag(
            tag_name="PRESSURE",
            device_name="plc_1",
            address_type="holding_register",
            address=0,
            alarm_high=100.0,
        )

        # Set value and quality for alarm check
        test_scada.tag_values["PRESSURE"] = 110.0
        test_scada.tag_quality["PRESSURE"] = "good"

        # Check alarms
        test_scada._check_alarms()

        assert len(test_scada.active_alarms) == 1
        alarm = test_scada.active_alarms[0]
        assert alarm.tag_name == "PRESSURE"
        assert alarm.alarm_type == "high"
        assert alarm.value == 110.0

    def test_raise_low_alarm(self, test_scada):
        """Test raising low alarm.

        WHY: Low alarms indicate values below limits.
        """
        test_scada.add_tag(
            tag_name="LEVEL",
            device_name="plc_1",
            address_type="holding_register",
            address=0,
            alarm_low=20.0,
        )

        test_scada.tag_values["LEVEL"] = 15.0
        test_scada.tag_quality["LEVEL"] = "good"

        test_scada._check_alarms()

        assert len(test_scada.active_alarms) == 1
        alarm = test_scada.active_alarms[0]
        assert alarm.alarm_type == "low"

    def test_no_duplicate_alarms(self, test_scada):
        """Test that duplicate alarms are not raised.

        WHY: Only one active alarm per tag/type.
        """
        test_scada.add_tag(
            tag_name="PRESSURE",
            device_name="plc_1",
            address_type="holding_register",
            address=0,
            alarm_high=100.0,
        )

        test_scada.tag_values["PRESSURE"] = 110.0
        test_scada.tag_quality["PRESSURE"] = "good"

        # Check alarms multiple times
        test_scada._check_alarms()
        test_scada._check_alarms()
        test_scada._check_alarms()

        # Should only have one alarm
        assert len(test_scada.active_alarms) == 1

    def test_no_alarm_on_bad_quality(self, test_scada):
        """Test that alarms are not raised for bad quality data.

        WHY: Don't alarm on unreliable data.
        """
        test_scada.add_tag(
            tag_name="PRESSURE",
            device_name="plc_1",
            address_type="holding_register",
            address=0,
            alarm_high=100.0,
        )

        test_scada.tag_values["PRESSURE"] = 110.0
        test_scada.tag_quality["PRESSURE"] = "bad"  # Bad quality

        test_scada._check_alarms()

        assert len(test_scada.active_alarms) == 0

    @pytest.mark.asyncio
    async def test_acknowledge_alarm(self, test_scada):
        """Test acknowledging an alarm.

        WHY: Operators acknowledge alarms.
        """
        test_scada._raise_alarm("TEST", "high", 100)
        assert len(test_scada.active_alarms) == 1
        assert test_scada.active_alarms[0].acknowledged is False

        result = await test_scada.acknowledge_alarm(0)
        assert result is True
        assert test_scada.active_alarms[0].acknowledged is True

    @pytest.mark.asyncio
    async def test_acknowledge_invalid_alarm(self, test_scada):
        """Test acknowledging invalid alarm index.

        WHY: Should handle invalid indices gracefully.
        """
        result = await test_scada.acknowledge_alarm(99)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_active_alarms(self, test_scada):
        """Test getting active alarms list.

        WHY: HMI needs alarm list.
        """
        test_scada._raise_alarm("TAG1", "high", 100)
        test_scada._raise_alarm("TAG2", "low", 5)

        alarms = await test_scada.get_active_alarms()
        assert len(alarms) == 2
        # Should be a copy
        alarms.clear()
        assert len(test_scada.active_alarms) == 2

    def test_alarm_history(self, test_scada):
        """Test that alarms are added to history.

        WHY: Historical alarm tracking.
        """
        test_scada._raise_alarm("TAG1", "high", 100)
        test_scada._raise_alarm("TAG2", "low", 5)

        assert len(test_scada.alarm_history) == 2

    def test_total_alarms_counter(self, test_scada):
        """Test total alarms counter.

        WHY: Track alarm statistics.
        """
        test_scada._raise_alarm("TAG1", "high", 100)
        test_scada._raise_alarm("TAG2", "low", 5)
        test_scada._raise_alarm("TAG3", "comms_failure", None)

        assert test_scada.total_alarms == 3


# ================================================================
# MEMORY MAP TESTS
# ================================================================
class TestSCADAServerMemoryMap:
    """Test SCADA server memory map structure."""

    @pytest.mark.asyncio
    async def test_memory_map_initialisation(self, test_scada):
        """Test that memory map is initialised correctly.

        WHY: Memory map must have expected structure.
        """
        await test_scada._initialise_memory_map()

        # Check input registers exist
        assert "input_registers[0]" in test_scada.memory_map
        assert "input_registers[1]" in test_scada.memory_map
        assert "input_registers[2]" in test_scada.memory_map
        assert "input_registers[3]" in test_scada.memory_map

        # Check coils exist
        assert "coils[0]" in test_scada.memory_map
        assert "coils[1]" in test_scada.memory_map
        assert "coils[2]" in test_scada.memory_map

        # Check tag containers exist
        assert "tag_values" in test_scada.memory_map
        assert "tag_quality" in test_scada.memory_map
        assert "tag_timestamps" in test_scada.memory_map
        assert "active_alarms" in test_scada.memory_map

    @pytest.mark.asyncio
    async def test_memory_map_default_values(self, test_scada):
        """Test default values in memory map.

        WHY: Defaults must be sensible.
        """
        await test_scada._initialise_memory_map()

        # Statistics should be zero
        assert test_scada.memory_map["input_registers[0]"] == 0
        assert test_scada.memory_map["input_registers[2]"] == 0

        # Polling should be enabled
        assert test_scada.memory_map["coils[2]"] is True

        # Acknowledge coil should be off
        assert test_scada.memory_map["coils[0]"] is False

    @pytest.mark.asyncio
    async def test_process_polled_data_updates_memory_map(self, test_scada):
        """Test that _process_polled_data updates memory map.

        WHY: Memory map must reflect current state.
        """
        await test_scada._initialise_memory_map()

        # Add some data
        test_scada.add_tag("TAG1", "plc_1", "holding_register", 0)
        test_scada.tag_values["TAG1"] = 42
        test_scada.tag_quality["TAG1"] = "good"
        test_scada.total_polls = 100
        test_scada.failed_polls = 5
        test_scada._raise_alarm("TAG1", "high", 42)

        await test_scada._process_polled_data()

        # Check values are synced
        assert test_scada.memory_map["tag_values"]["TAG1"] == 42
        assert test_scada.memory_map["tag_quality"]["TAG1"] == "good"
        assert test_scada.memory_map["input_registers[0]"] == 100  # Poll count low
        assert test_scada.memory_map["input_registers[2]"] == 5  # Failed polls
        assert test_scada.memory_map["input_registers[3]"] == 1  # Active alarms
        assert len(test_scada.memory_map["active_alarms"]) == 1


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestSCADAServerIntegration:
    """Test SCADA server integration with dependencies."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, test_scada, datastore_setup):
        """Test that SCADA server registers with DataStore.

        WHY: SCADA servers must be accessible via DataStore.
        """
        data_store = datastore_setup

        await test_scada.start()

        # Verify registered
        devices = await data_store.get_devices_by_type("scada_server")
        assert len(devices) == 1
        assert devices[0].device_name == "test_scada_1"

    @pytest.mark.asyncio
    async def test_memory_accessible_via_datastore(
        self, started_scada, datastore_setup
    ):
        """Test that SCADA memory is accessible via DataStore.

        WHY: Other devices may need to access SCADA data.
        """
        data_store = datastore_setup

        # Wait for a scan cycle
        await asyncio.sleep(0.03)

        # Read memory via DataStore
        memory = await data_store.bulk_read_memory("test_scada_1")
        assert memory is not None
        assert "coils[2]" in memory  # Polling enabled coil

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, test_scada):
        """Test complete SCADA server lifecycle.

        WHY: Verify end-to-end operation.
        """
        # 1. Start
        await test_scada.start()
        assert test_scada.is_online()
        assert test_scada.is_running()

        # 2. Run for a bit
        await asyncio.sleep(0.03)
        assert test_scada.metadata["scan_count"] > 0

        # 3. Reset
        await test_scada.reset()
        assert test_scada.metadata["scan_count"] == 0
        assert test_scada.is_running()

        # 4. Stop
        await test_scada.stop()
        assert not test_scada.is_online()
        assert not test_scada.is_running()

    @pytest.mark.asyncio
    async def test_get_telemetry(self, started_scada):
        """Test getting SCADA telemetry.

        WHY: Telemetry provides comprehensive status.
        """
        # Add some configuration
        started_scada.add_poll_target("plc_1", "modbus", poll_rate_s=1.0)
        started_scada.add_tag("TAG1", "plc_1", "holding_register", 0)

        await asyncio.sleep(0.02)

        telemetry = await started_scada.get_telemetry()

        assert telemetry["device_name"] == "test_scada_1"
        assert telemetry["device_type"] == "scada_server"
        assert "poll_targets" in telemetry
        assert "plc_1" in telemetry["poll_targets"]
        assert "tags" in telemetry
        assert "active_alarms" in telemetry
        assert "statistics" in telemetry

    @pytest.mark.asyncio
    async def test_get_supervisory_status(self, started_scada):
        """Test getting supervisory device status.

        WHY: Inherited status method should work.
        """
        started_scada.add_poll_target("plc_1", "modbus")

        await asyncio.sleep(0.02)

        status = await started_scada.get_supervisory_status()

        assert status["device_name"] == "test_scada_1"
        assert "polling_enabled" in status
        assert "poll_target_count" in status
        assert status["poll_target_count"] == 1
        assert "total_polls" in status
        assert "failed_polls" in status


# ================================================================
# CONCURRENT OPERATIONS TESTS
# ================================================================
class TestSCADAServerConcurrency:
    """Test concurrent SCADA operations."""

    @pytest.mark.asyncio
    async def test_multiple_scada_instances(self, datastore_setup):
        """Test multiple SCADA servers operating concurrently.

        WHY: Large systems may have multiple SCADA servers.
        """
        data_store = datastore_setup

        scadas = [
            SCADAServer(f"scada_{i}", i, data_store, scan_interval=0.01)
            for i in range(3)
        ]

        # Start all
        await asyncio.gather(*[s.start() for s in scadas])

        # Let them run
        await asyncio.sleep(0.05)

        # All should be running and scanning
        for scada in scadas:
            assert scada.is_running()
            assert scada.metadata["scan_count"] > 0

        # Stop all
        await asyncio.gather(*[s.stop() for s in scadas])


# ================================================================
# API COMPATIBILITY TESTS
# ================================================================
class TestSCADAServerAPICompatibility:
    """Test that refactored API is compatible with original."""

    def test_poll_target_from_base_class(self, test_scada):
        """Test that poll target management comes from base class.

        WHY: BaseSupervisoryDevice provides poll target methods.
        """
        # add_poll_target should be inherited
        test_scada.add_poll_target("plc_1", "modbus")
        assert "plc_1" in test_scada.poll_targets

        # remove_poll_target should be inherited
        test_scada.remove_poll_target("plc_1")
        assert "plc_1" not in test_scada.poll_targets

    def test_inherits_from_base_supervisory_device(self, test_scada):
        """Test that SCADAServer inherits from BaseSupervisoryDevice.

        WHY: Class hierarchy must be correct.
        """
        from components.devices.core.base_device import BaseDevice
        from components.devices.operations_zone.base_supervisory import (
            BaseSupervisoryDevice,
        )

        assert isinstance(test_scada, BaseSupervisoryDevice)
        assert isinstance(test_scada, BaseDevice)

    @pytest.mark.asyncio
    async def test_start_replaces_initialise(self, test_scada):
        """Test that start() handles initialization automatically.

        WHY: No separate initialise() call needed.
        """
        # Should not have initialise() method
        assert not hasattr(test_scada, "initialise")

        # start() should work directly
        await test_scada.start()
        assert test_scada.is_online()
        assert test_scada.is_running()

        await test_scada.stop()
