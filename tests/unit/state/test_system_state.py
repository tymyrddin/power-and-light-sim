# tests/unit/state/test_system_state.py
"""Comprehensive tests for SystemState component.

This is Level 1 in our dependency tree - SystemState depends on SimulationTime.
We use REAL SimulationTime (already tested at Level 0) rather than mocking it.

Test Coverage:
- Device registration and unregistration
- State updates and queries
- Device filtering (by type, protocol)
- Online/offline tracking
- Simulation lifecycle management
- Concurrent access safety
- Edge cases and error handling
"""

import asyncio
import pytest

from components.state.system_state import (
    SystemState
)


# ================================================================
# DEVICE REGISTRATION TESTS
# ================================================================
class TestSystemStateDeviceRegistration:
    """Test device registration functionality."""

    @pytest.mark.asyncio
    async def test_register_device_success(self):
        """Test successful device registration.

        WHY: Core functionality - must be able to add devices to state.
        """
        state = SystemState()

        result = await state.register_device(
            device_name="test_plc_1",
            device_type="turbine_plc",
            device_id=1,
            protocols=["modbus"],
        )

        assert result is True  # New registration
        assert len(state.devices) == 1
        assert "test_plc_1" in state.devices
        assert state.simulation.total_devices == 1

    @pytest.mark.asyncio
    async def test_register_device_with_metadata(self):
        """Test device registration with metadata.

        WHY: Devices need to store configuration and context information.
        """
        state = SystemState()
        metadata = {"location": "Building A", "ip": "192.168.1.10"}

        await state.register_device(
            device_name="test_plc_1",
            device_type="turbine_plc",
            device_id=1,
            protocols=["modbus"],
            metadata=metadata,
        )

        device = await state.get_device("test_plc_1")
        assert device is not None
        assert device.metadata == metadata
        assert device.metadata["location"] == "Building A"

    @pytest.mark.asyncio
    async def test_register_device_initializes_offline(self):
        """Test that newly registered devices start offline.

        WHY: Devices should be explicitly brought online after registration.
        """
        state = SystemState()

        await state.register_device(
            device_name="test_plc_1",
            device_type="turbine_plc",
            device_id=1,
            protocols=["modbus"],
        )

        device = await state.get_device("test_plc_1")
        assert device.online is False
        assert state.simulation.devices_online == 0

    @pytest.mark.asyncio
    async def test_register_duplicate_device_replaces(self):
        """Test that registering duplicate device name replaces existing.

        WHY: Re-registration should update configuration, not fail.
        """
        state = SystemState()

        # First registration
        result1 = await state.register_device(
            device_name="test_plc_1",
            device_type="turbine_plc",
            device_id=1,
            protocols=["modbus"],
        )

        # Duplicate registration
        result2 = await state.register_device(
            device_name="test_plc_1",
            device_type="substation_plc",
            device_id=2,
            protocols=["dnp3"],
        )

        assert result1 is True  # First was new
        assert result2 is False  # Second was replacement
        assert len(state.devices) == 1  # Still only one device

        device = await state.get_device("test_plc_1")
        assert device.device_type == "substation_plc"  # Updated
        assert device.device_id == 2  # Updated

    @pytest.mark.asyncio
    async def test_register_multiple_devices(self):
        """Test registering multiple devices.

        WHY: Simulations have many devices - must track them all.
        """
        state = SystemState()

        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await state.register_device("plc_2", "substation_plc", 2, ["modbus"])
        await state.register_device("scada_1", "scada_server", 3, ["dnp3"])

        assert len(state.devices) == 3
        assert state.simulation.total_devices == 3

    @pytest.mark.asyncio
    async def test_register_device_rejects_empty_name(self):
        """Test that empty device name is rejected.

        WHY: Device names are identifiers - must be valid.
        """
        state = SystemState()

        with pytest.raises(ValueError, match="device_name must be a non-empty string"):
            await state.register_device(
                device_name="",
                device_type="turbine_plc",
                device_id=1,
                protocols=["modbus"],
            )

    @pytest.mark.asyncio
    async def test_register_device_rejects_invalid_name_type(self):
        """Test that non-string device name is rejected.

        WHY: Type safety - names must be strings.
        """
        state = SystemState()

        with pytest.raises(ValueError, match="device_name must be a non-empty string"):
            await state.register_device(
                device_name=123,  # type: ignore[arg-type] Intentional: Invalid type
                device_type="turbine_plc",
                device_id=1,
                protocols=["modbus"],
            )

    @pytest.mark.asyncio
    async def test_register_device_rejects_empty_type(self):
        """Test that empty device type is rejected.

        WHY: Device type is required for classification.
        """
        state = SystemState()

        with pytest.raises(ValueError, match="device_type must be a non-empty string"):
            await state.register_device(
                device_name="test_plc",
                device_type="",
                device_id=1,
                protocols=["modbus"],
            )

    @pytest.mark.asyncio
    async def test_register_device_rejects_empty_protocols(self):
        """Test that empty protocols list is rejected.

        WHY: Every device must support at least one protocol.
        """
        state = SystemState()

        with pytest.raises(ValueError, match="protocols must be a non-empty list"):
            await state.register_device(
                device_name="test_plc",
                device_type="turbine_plc",
                device_id=1,
                protocols=[],
            )

    @pytest.mark.asyncio
    async def test_register_device_rejects_non_list_protocols(self):
        """Test that non-list protocols parameter is rejected.

        WHY: Type safety - protocols must be a list.
        """
        state = SystemState()

        with pytest.raises(ValueError, match="protocols must be a non-empty list"):
            await state.register_device(
                device_name="test_plc",
                device_type="turbine_plc",
                device_id=1,
                protocols="modbus",  # type: ignore[arg-type] Intentional: String instead of list
            )


# ================================================================
# DEVICE UNREGISTRATION TESTS
# ================================================================
class TestSystemStateDeviceUnregistration:
    """Test device unregistration functionality."""

    @pytest.mark.asyncio
    async def test_unregister_device_success(self):
        """Test successful device unregistration.

        WHY: Must be able to remove devices from simulation.
        """
        state = SystemState()
        await state.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        result = await state.unregister_device("test_plc")

        assert result is True
        assert len(state.devices) == 0
        assert state.simulation.total_devices == 0

    @pytest.mark.asyncio
    async def test_unregister_device_updates_online_count(self):
        """Test that unregistering online device updates counter.

        WHY: Online device count must stay accurate.
        """
        state = SystemState()
        await state.register_device("test_plc", "turbine_plc", 1, ["modbus"])
        await state.update_device("test_plc", online=True)

        assert state.simulation.devices_online == 1

        await state.unregister_device("test_plc")

        assert state.simulation.devices_online == 0

    @pytest.mark.asyncio
    async def test_unregister_nonexistent_device_returns_false(self):
        """Test that unregistering non-existent device returns False.

        WHY: Should indicate failure gracefully, not crash.
        """
        state = SystemState()

        result = await state.unregister_device("nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_unregister_one_of_many_devices(self):
        """Test unregistering one device from multiple.

        WHY: Should only remove specified device, leave others intact.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await state.register_device("plc_2", "turbine_plc", 2, ["modbus"])
        await state.register_device("plc_3", "turbine_plc", 3, ["modbus"])

        await state.unregister_device("plc_2")

        assert len(state.devices) == 2
        assert "plc_1" in state.devices
        assert "plc_2" not in state.devices
        assert "plc_3" in state.devices


# ================================================================
# STATE UPDATE TESTS
# ================================================================
class TestSystemStateUpdates:
    """Test device state update functionality."""

    @pytest.mark.asyncio
    async def test_update_device_online_status(self):
        """Test updating device online status.

        WHY: Devices transition between online and offline states.
        """
        state = SystemState()
        await state.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        result = await state.update_device("test_plc", online=True)

        assert result is True
        device = await state.get_device("test_plc")
        assert device.online is True
        assert state.simulation.devices_online == 1

    @pytest.mark.asyncio
    async def test_update_device_online_increments_counter(self):
        """Test that bringing device online increments counter.

        WHY: Must track how many devices are currently online.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await state.register_device("plc_2", "turbine_plc", 2, ["modbus"])

        assert state.simulation.devices_online == 0

        await state.update_device("plc_1", online=True)
        assert state.simulation.devices_online == 1

        await state.update_device("plc_2", online=True)
        assert state.simulation.devices_online == 2

    @pytest.mark.asyncio
    async def test_update_device_offline_decrements_counter(self):
        """Test that taking device offline decrements counter.

        WHY: Online count must decrease when devices go offline.
        """
        state = SystemState()
        await state.register_device("test_plc", "turbine_plc", 1, ["modbus"])
        await state.update_device("test_plc", online=True)

        assert state.simulation.devices_online == 1

        await state.update_device("test_plc", online=False)

        assert state.simulation.devices_online == 0

    @pytest.mark.asyncio
    async def test_update_device_online_status_idempotent(self):
        """Test that setting same online status doesn't change counter.

        WHY: Redundant updates shouldn't affect counters.
        """
        state = SystemState()
        await state.register_device("test_plc", "turbine_plc", 1, ["modbus"])
        await state.update_device("test_plc", online=True)

        assert state.simulation.devices_online == 1

        # Update to same status
        await state.update_device("test_plc", online=True)

        # Counter shouldn't change
        assert state.simulation.devices_online == 1

    @pytest.mark.asyncio
    async def test_update_device_memory_map(self):
        """Test updating device memory map.

        WHY: Memory maps store protocol-specific register values.
        """
        state = SystemState()
        await state.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        memory_map = {
            "holding_registers[0]": 3600,
            "holding_registers[1]": 50,
            "coils[0]": True,
        }

        await state.update_device("test_plc", memory_map=memory_map)

        device = await state.get_device("test_plc")
        assert device.memory_map == memory_map
        assert device.memory_map["holding_registers[0]"] == 3600

    @pytest.mark.asyncio
    async def test_update_device_memory_map_replaces(self):
        """Test that memory map update replaces rather than merges.

        WHY: Memory maps are complete state snapshots, not incremental.
        """
        state = SystemState()
        await state.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        # First update
        await state.update_device("test_plc", memory_map={"reg[0]": 100})

        # Second update should replace, not merge
        await state.update_device("test_plc", memory_map={"reg[1]": 200})

        device = await state.get_device("test_plc")
        assert "reg[0]" not in device.memory_map  # Old value removed
        assert device.memory_map == {"reg[1]": 200}

    @pytest.mark.asyncio
    async def test_update_device_metadata_merges(self):
        """Test that metadata update merges rather than replaces.

        WHY: Metadata is additive - new fields don't erase old ones.
        """
        state = SystemState()
        await state.register_device(
            "test_plc", "turbine_plc", 1, ["modbus"],
            metadata={"location": "Building A"}
        )

        # Update with additional metadata
        await state.update_device("test_plc", metadata={"ip": "192.168.1.10"})

        device = await state.get_device("test_plc")
        assert device.metadata["location"] == "Building A"  # Original preserved
        assert device.metadata["ip"] == "192.168.1.10"  # New added

    @pytest.mark.asyncio
    async def test_update_device_updates_timestamp(self):
        """Test that device update refreshes timestamp.

        WHY: Need to track when device state last changed.
        """
        state = SystemState()
        await state.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        device = await state.get_device("test_plc")
        old_timestamp = device.last_update

        await asyncio.sleep(0.01)  # Small delay
        await state.update_device("test_plc", online=True)

        device = await state.get_device("test_plc")
        assert device.last_update > old_timestamp

    @pytest.mark.asyncio
    async def test_update_nonexistent_device_returns_false(self):
        """Test that updating non-existent device returns False.

        WHY: Should indicate failure gracefully without crashing.
        """
        state = SystemState()

        result = await state.update_device("nonexistent", online=True)

        assert result is False

    @pytest.mark.asyncio
    async def test_update_device_with_all_parameters(self):
        """Test updating all device parameters at once.

        WHY: Should support bulk updates for efficiency.
        """
        state = SystemState()
        await state.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        await state.update_device(
            "test_plc",
            online=True,
            memory_map={"reg[0]": 100},
            metadata={"status": "operational"},
        )

        device = await state.get_device("test_plc")
        assert device.online is True
        assert device.memory_map == {"reg[0]": 100}
        assert device.metadata["status"] == "operational"


# ================================================================
# STATE QUERY TESTS
# ================================================================
class TestSystemStateQueries:
    """Test state query functionality."""

    @pytest.mark.asyncio
    async def test_get_device_returns_device(self):
        """Test getting a specific device.

        WHY: Need to query individual device state.
        """
        state = SystemState()
        await state.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        device = await state.get_device("test_plc")

        assert device is not None
        assert device.device_name == "test_plc"
        assert device.device_type == "turbine_plc"

    @pytest.mark.asyncio
    async def test_get_device_returns_none_for_nonexistent(self):
        """Test that querying non-existent device returns None.

        WHY: Should indicate absence without raising exceptions.
        """
        state = SystemState()

        device = await state.get_device("nonexistent")

        assert device is None

    @pytest.mark.asyncio
    async def test_get_all_devices_returns_all(self):
        """Test getting all devices.

        WHY: Need to enumerate all registered devices.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await state.register_device("plc_2", "substation_plc", 2, ["modbus"])

        devices = await state.get_all_devices()

        assert len(devices) == 2
        assert "plc_1" in devices
        assert "plc_2" in devices

    @pytest.mark.asyncio
    async def test_get_all_devices_returns_copy(self):
        """Test that get_all_devices returns a copy, not reference.

        WHY: Prevent external code from directly mutating internal state.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])

        devices1 = await state.get_all_devices()
        devices2 = await state.get_all_devices()

        assert devices1 is not devices2  # Different objects
        assert devices1 == devices2  # But same content

    @pytest.mark.asyncio
    async def test_get_devices_by_type(self):
        """Test filtering devices by type.

        WHY: Need to find all devices of a specific type.
        """
        state = SystemState()
        await state.register_device("turbine_1", "turbine_plc", 1, ["modbus"])
        await state.register_device("turbine_2", "turbine_plc", 2, ["modbus"])
        await state.register_device("substation_1", "substation_plc", 3, ["modbus"])

        turbines = await state.get_devices_by_type("turbine_plc")

        assert len(turbines) == 2
        assert all(d.device_type == "turbine_plc" for d in turbines)

    @pytest.mark.asyncio
    async def test_get_devices_by_type_empty_result(self):
        """Test filtering for non-existent device type.

        WHY: Should return empty list, not error.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])

        devices = await state.get_devices_by_type("nonexistent_type")

        assert devices == []

    @pytest.mark.asyncio
    async def test_get_devices_by_protocol(self):
        """Test filtering devices by protocol.

        WHY: Need to find all devices supporting a protocol.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await state.register_device("plc_2", "turbine_plc", 2, ["modbus", "dnp3"])
        await state.register_device("rtu_1", "rtu", 3, ["dnp3"])

        modbus_devices = await state.get_devices_by_protocol("modbus")
        dnp3_devices = await state.get_devices_by_protocol("dnp3")

        assert len(modbus_devices) == 2
        assert len(dnp3_devices) == 2
        assert all("modbus" in d.protocols for d in modbus_devices)
        assert all("dnp3" in d.protocols for d in dnp3_devices)

    @pytest.mark.asyncio
    async def test_get_devices_by_protocol_empty_result(self):
        """Test filtering for unsupported protocol.

        WHY: Should return empty list when no devices support it.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])

        devices = await state.get_devices_by_protocol("iec61850")

        assert devices == []

    @pytest.mark.asyncio
    async def test_get_simulation_state(self):
        """Test getting overall simulation state.

        WHY: Need to monitor simulation-level statistics.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await state.update_device("plc_1", online=True)

        sim_state = await state.get_simulation_state()

        assert sim_state.total_devices == 1
        assert sim_state.devices_online == 1
        assert sim_state.running is False


# ================================================================
# UPDATE CYCLE TESTS
# ================================================================
class TestSystemStateUpdateCycles:
    """Test simulation update cycle tracking."""

    @pytest.mark.asyncio
    async def test_increment_update_cycles(self):
        """Test incrementing update cycle counter.

        WHY: Need to track simulation iterations for diagnostics.
        """
        state = SystemState()

        assert state.simulation.total_update_cycles == 0

        await state.increment_update_cycles()
        assert state.simulation.total_update_cycles == 1

        await state.increment_update_cycles()
        assert state.simulation.total_update_cycles == 2

    @pytest.mark.asyncio
    async def test_increment_update_cycles_many_times(self):
        """Test incrementing many times.

        WHY: Simulations run for many cycles - ensure no overflow.
        """
        state = SystemState()

        for _ in range(10000):
            await state.increment_update_cycles()

        assert state.simulation.total_update_cycles == 10000


# ================================================================
# SUMMARY/STATUS TESTS
# ================================================================
class TestSystemStateSummary:
    """Test summary and status reporting."""

    @pytest.mark.asyncio
    async def test_get_summary_structure(self):
        """Test that summary has expected structure.

        WHY: Summary is used for monitoring - must be consistent.
        """
        state = SystemState()

        summary = await state.get_summary()

        assert "simulation" in summary
        assert "devices" in summary
        assert "device_types" in summary
        assert "protocols" in summary

    @pytest.mark.asyncio
    async def test_get_summary_simulation_section(self):
        """Test simulation section of summary.

        WHY: Must report simulation status accurately.
        """
        state = SystemState()
        await state.mark_running(True)

        summary = await state.get_summary()
        sim = summary["simulation"]

        assert "running" in sim
        assert "started_at" in sim
        assert "uptime_seconds" in sim
        assert "simulation_time" in sim
        assert "update_cycles" in sim
        assert sim["running"] is True

    @pytest.mark.asyncio
    async def test_get_summary_devices_section(self):
        """Test devices section of summary.

        WHY: Must show device counts accurately.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await state.register_device("plc_2", "turbine_plc", 2, ["modbus"])
        await state.update_device("plc_1", online=True)

        summary = await state.get_summary()
        devices = summary["devices"]

        assert devices["total"] == 2
        assert devices["online"] == 1
        assert devices["offline"] == 1

    @pytest.mark.asyncio
    async def test_get_summary_device_types_section(self):
        """Test device_types section of summary.

        WHY: Need to see distribution of device types.
        """
        state = SystemState()
        await state.register_device("turbine_1", "turbine_plc", 1, ["modbus"])
        await state.register_device("turbine_2", "turbine_plc", 2, ["modbus"])
        await state.register_device("sub_1", "substation_plc", 3, ["modbus"])

        summary = await state.get_summary()
        types = summary["device_types"]

        assert types["turbine_plc"] == 2
        assert types["substation_plc"] == 1

    @pytest.mark.asyncio
    async def test_get_summary_protocols_section(self):
        """Test protocols section of summary.

        WHY: Need to see which protocols are in use.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await state.register_device("plc_2", "turbine_plc", 2, ["modbus", "dnp3"])
        await state.register_device("rtu_1", "rtu", 3, ["dnp3"])

        summary = await state.get_summary()
        protocols = summary["protocols"]

        assert protocols["modbus"] == 2
        assert protocols["dnp3"] == 2


# ================================================================
# LIFECYCLE TESTS
# ================================================================
class TestSystemStateLifecycle:
    """Test simulation lifecycle management."""

    @pytest.mark.asyncio
    async def test_mark_running_true(self):
        """Test marking simulation as running.

        WHY: Need to track simulation run state.
        """
        state = SystemState()

        assert state.simulation.running is False

        await state.mark_running(True)

        assert state.simulation.running is True

    @pytest.mark.asyncio
    async def test_mark_running_updates_started_at(self):
        """Test that starting simulation updates timestamp.

        WHY: Need to know when simulation started.
        """
        state = SystemState()
        old_timestamp = state.simulation.started_at

        await asyncio.sleep(0.01)
        await state.mark_running(True)

        assert state.simulation.started_at > old_timestamp

    @pytest.mark.asyncio
    async def test_mark_running_false(self):
        """Test stopping simulation.

        WHY: Need to mark simulation as stopped.
        """
        state = SystemState()
        await state.mark_running(True)

        await state.mark_running(False)

        assert state.simulation.running is False

    @pytest.mark.asyncio
    async def test_mark_running_idempotent(self):
        """Test that repeated mark_running calls are safe.

        WHY: Prevent issues from redundant state changes.
        """
        state = SystemState()

        await state.mark_running(True)
        old_timestamp = state.simulation.started_at

        await asyncio.sleep(0.01)
        await state.mark_running(True)  # Already running

        # Timestamp shouldn't change
        assert state.simulation.started_at == old_timestamp

    @pytest.mark.asyncio
    async def test_reset_clears_all_devices(self):
        """Test that reset clears all registered devices.

        WHY: Reset should return to clean slate.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await state.register_device("plc_2", "turbine_plc", 2, ["modbus"])

        await state.reset()

        assert len(state.devices) == 0
        assert state.simulation.total_devices == 0

    @pytest.mark.asyncio
    async def test_reset_clears_simulation_state(self):
        """Test that reset clears simulation state.

        WHY: All counters and state should reset.
        """
        state = SystemState()
        await state.mark_running(True)
        await state.increment_update_cycles()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await state.update_device("plc_1", online=True)

        await state.reset()

        assert state.simulation.running is False
        assert state.simulation.total_update_cycles == 0
        assert state.simulation.devices_online == 0


# ================================================================
# CONCURRENCY TESTS
# ================================================================
class TestSystemStateConcurrency:
    """Test thread-safety and concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_device_registration(self):
        """Test concurrent device registrations are safe.

        WHY: Multiple coroutines may register devices simultaneously.
        """
        state = SystemState()

        async def register_devices(start_id: int):
            for i in range(10):
                device_id = start_id + i
                await state.register_device(
                    f"plc_{device_id}",
                    "turbine_plc",
                    device_id,
                    ["modbus"]
                )

        # Register 30 devices concurrently (3 coroutines × 10 devices)
        await asyncio.gather(
            register_devices(0),
            register_devices(10),
            register_devices(20),
        )

        assert len(state.devices) == 30
        assert state.simulation.total_devices == 30

    @pytest.mark.asyncio
    async def test_concurrent_device_updates(self):
        """Test concurrent device updates are safe.

        WHY: Multiple coroutines may update devices simultaneously.
        """
        state = SystemState()

        # Register devices first
        for i in range(10):
            await state.register_device(f"plc_{i}", "turbine_plc", i, ["modbus"])

        async def update_devices():
            for i in range(10):
                await state.update_device(f"plc_{i}", online=True)
                await asyncio.sleep(0.001)  # Small delay

        # Update from multiple coroutines
        await asyncio.gather(*[update_devices() for _ in range(3)])

        # All devices should be online
        assert state.simulation.devices_online == 10

    @pytest.mark.asyncio
    async def test_concurrent_reads_and_writes(self):
        """Test concurrent reads and writes don't corrupt state.

        WHY: Real simulation has constant read/write activity.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])

        results = []

        async def reader():
            for _ in range(50):
                device = await state.get_device("plc_1")
                results.append(device)
                await asyncio.sleep(0.001)

        async def writer():
            for i in range(50):
                await state.update_device("plc_1", memory_map={"reg": i})
                await asyncio.sleep(0.001)

        # Run readers and writers concurrently
        await asyncio.gather(
            reader(),
            reader(),
            writer(),
        )

        # Should complete without errors
        assert len(results) == 100  # 2 readers × 50 reads each

    @pytest.mark.asyncio
    async def test_concurrent_summary_generation(self):
        """Test concurrent summary generation is safe.

        WHY: Summary may be requested while state is changing.
        """
        state = SystemState()

        async def register_and_query(offset: int):
            """Register 10 devices with unique names and query summary."""
            for i in range(10):
                device_id = offset + i
                device_name = f"plc_{device_id}"
                await state.register_device(device_name, "turbine_plc", device_id, ["modbus"])
                await state.get_summary()  # Generate summary during registration

        # Launch 3 coroutines concurrently, each registering 10 unique devices
        await asyncio.gather(
            register_and_query(0),
            register_and_query(10),
            register_and_query(20),
        )

        # Final summary should report 30 devices
        summary = await state.get_summary()
        assert summary["devices"]["total"] == 30
        assert summary["devices"]["online"] == 0  # None have been brought online
        assert summary["devices"]["offline"] == 30


# ================================================================
# EDGE CASE TESTS
# ================================================================
class TestSystemStateEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_device_with_multiple_protocols(self):
        """Test device supporting multiple protocols.

        WHY: Devices often support multiple protocols.
        """
        state = SystemState()

        await state.register_device(
            "multi_plc",
            "turbine_plc",
            1,
            ["modbus", "dnp3", "iec61850"]
        )

        device = await state.get_device("multi_plc")
        assert len(device.protocols) == 3

        # Should appear in all protocol queries
        for protocol in ["modbus", "dnp3", "iec61850"]:
            devices = await state.get_devices_by_protocol(protocol)
            assert any(d.device_name == "multi_plc" for d in devices)

    @pytest.mark.asyncio
    async def test_empty_memory_map(self):
        """Test device with empty memory map.

        WHY: Newly registered devices have empty maps.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])

        device = await state.get_device("plc_1")
        assert device.memory_map == {}

    @pytest.mark.asyncio
    async def test_large_memory_map(self):
        """Test device with large memory map.

        WHY: PLCs can have thousands of registers.
        """
        state = SystemState()
        await state.register_device("plc_1", "turbine_plc", 1, ["modbus"])

        # Create large memory map
        large_map = {f"reg[{i}]": i for i in range(1000)}
        await state.update_device("plc_1", memory_map=large_map)

        device = await state.get_device("plc_1")
        assert len(device.memory_map) == 1000
        assert device.memory_map["reg[999]"] == 999

    @pytest.mark.asyncio
    async def test_metadata_with_complex_types(self):
        """Test metadata with nested dictionaries and lists.

        WHY: Metadata can contain complex configuration.
        """
        state = SystemState()

        complex_metadata = {
            "location": {"building": "A", "floor": 3, "room": "301"},
            "network": {"ip": "192.168.1.10", "ports": [502, 20000]},
            "tags": ["critical", "monitored", "redundant"],
        }

        await state.register_device(
            "plc_1", "turbine_plc", 1, ["modbus"],
            metadata=complex_metadata
        )

        device = await state.get_device("plc_1")
        assert device.metadata["location"]["building"] == "A"
        assert 502 in device.metadata["network"]["ports"]
        assert "critical" in device.metadata["tags"]

    @pytest.mark.asyncio
    async def test_state_with_no_devices(self):
        """Test querying state with no registered devices.

        WHY: Fresh state should handle empty case gracefully.
        """
        state = SystemState()

        devices = await state.get_all_devices()
        assert devices == {}

        turbines = await state.get_devices_by_type("turbine_plc")
        assert turbines == []

        summary = await state.get_summary()
        assert summary["devices"]["total"] == 0
        assert summary["device_types"] == {}
