# tests/unit/state/test_data_store.py
"""Comprehensive tests for DataStore component.

This is Level 2 in our dependency tree - DataStore depends on SystemState.
We use REAL SystemState (already tested at Level 1) rather than mocking it.

Test Coverage:
- Device registration/unregistration via DataStore
- Memory map read/write operations
- Bulk memory operations
- Address validation for different protocols
- Metadata operations
- Device online status management
- Simulation-level operations
- Error handling and validation
- Concurrent access patterns
"""

import asyncio

import pytest

from components.state.data_store import DataStore
from components.state.system_state import SystemState


# ================================================================
# DEVICE REGISTRATION TESTS
# ================================================================
class TestDataStoreDeviceRegistration:
    """Test device registration through DataStore."""

    @pytest.mark.asyncio
    async def test_register_device_delegates_to_system_state(self):
        """Test that register_device properly delegates to SystemState.

        WHY: DataStore is a facade over SystemState - must delegate correctly.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        result = await data_store.register_device(
            device_name="test_plc",
            device_type="turbine_plc",
            device_id=1,
            protocols=["modbus"],
        )

        assert result is True
        # Verify it's actually in SystemState
        device = await system_state.get_device("test_plc")
        assert device is not None
        assert device.device_name == "test_plc"

    @pytest.mark.asyncio
    async def test_register_device_with_metadata(self):
        """Test device registration with metadata.

        WHY: Metadata should flow through to SystemState.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        metadata = {"location": "Building A", "ip": "192.168.1.10"}

        await data_store.register_device(
            "test_plc", "turbine_plc", 1, ["modbus"], metadata=metadata
        )

        device = await data_store.get_device_state("test_plc")
        assert device.metadata == metadata

    @pytest.mark.asyncio
    async def test_unregister_device_delegates_to_system_state(self):
        """Test that unregister_device properly delegates.

        WHY: Unregistration must also work through DataStore facade.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])
        result = await data_store.unregister_device("test_plc")

        assert result is True
        device = await system_state.get_device("test_plc")
        assert device is None


# ================================================================
# MEMORY READ/WRITE TESTS
# ================================================================
class TestDataStoreMemoryOperations:
    """Test memory read/write operations."""

    @pytest.mark.asyncio
    async def test_write_and_read_memory(self):
        """Test basic write and read operations.

        WHY: Core functionality - must be able to store and retrieve values.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        # Write
        write_success = await data_store.write_memory(
            "test_plc", "holding_registers[0]", 3600
        )
        assert write_success is True

        # Read
        value = await data_store.read_memory("test_plc", "holding_registers[0]")
        assert value == 3600

    @pytest.mark.asyncio
    async def test_write_memory_to_nonexistent_device(self):
        """Test writing to non-existent device returns False.

        WHY: Should fail gracefully, not crash.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        result = await data_store.write_memory(
            "nonexistent", "holding_registers[0]", 100
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_read_memory_from_nonexistent_device(self):
        """Test reading from non-existent device returns None.

        WHY: Should indicate absence, not crash.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        value = await data_store.read_memory("nonexistent", "holding_registers[0]")

        assert value is None

    @pytest.mark.asyncio
    async def test_read_nonexistent_address_returns_none(self):
        """Test reading uninitialized address returns None.

        WHY: Addresses start empty - should return None, not error.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        value = await data_store.read_memory("test_plc", "holding_registers[999]")

        assert value is None

    @pytest.mark.asyncio
    async def test_write_memory_empty_device_name_raises(self):
        """Test that empty device name raises ValueError.

        WHY: Input validation - device name is required.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        with pytest.raises(ValueError, match="device_name cannot be empty"):
            await data_store.write_memory("", "holding_registers[0]", 100)

    @pytest.mark.asyncio
    async def test_write_memory_empty_address_raises(self):
        """Test that empty address raises ValueError.

        WHY: Input validation - address is required.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        with pytest.raises(ValueError, match="address cannot be empty"):
            await data_store.write_memory("test_plc", "", 100)

    @pytest.mark.asyncio
    async def test_read_memory_empty_device_name_raises(self):
        """Test that empty device name raises ValueError on read.

        WHY: Consistent validation across read and write.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        with pytest.raises(ValueError, match="device_name cannot be empty"):
            await data_store.read_memory("", "holding_registers[0]")

    @pytest.mark.asyncio
    async def test_read_memory_empty_address_raises(self):
        """Test that empty address raises ValueError on read.

        WHY: Consistent validation across read and write.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        with pytest.raises(ValueError, match="address cannot be empty"):
            await data_store.read_memory("test_plc", "")

    @pytest.mark.asyncio
    async def test_write_overwrites_existing_value(self):
        """Test that writing to same address overwrites.

        WHY: Memory writes should replace previous values.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        await data_store.write_memory("test_plc", "holding_registers[0]", 100)
        await data_store.write_memory("test_plc", "holding_registers[0]", 200)

        value = await data_store.read_memory("test_plc", "holding_registers[0]")
        assert value == 200

    @pytest.mark.asyncio
    async def test_write_different_data_types(self):
        """Test writing different data types to memory.

        WHY: Memory should support various types (int, float, bool, string).
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        # Write different types
        await data_store.write_memory("test_plc", "holding_registers[0]", 3600)
        await data_store.write_memory("test_plc", "holding_registers[1]", 98.6)
        await data_store.write_memory("test_plc", "coils[0]", True)
        await data_store.write_memory("test_plc", "holding_registers[2]", "status_ok")

        # Read back and verify types
        assert await data_store.read_memory("test_plc", "holding_registers[0]") == 3600
        assert await data_store.read_memory("test_plc", "holding_registers[1]") == 98.6
        assert await data_store.read_memory("test_plc", "coils[0]") is True
        assert (
            await data_store.read_memory("test_plc", "holding_registers[2]")
            == "status_ok"
        )


# ================================================================
# BULK MEMORY OPERATION TESTS
# ================================================================
class TestDataStoreBulkOperations:
    """Test bulk memory read/write operations."""

    @pytest.mark.asyncio
    async def test_bulk_write_memory(self):
        """Test writing multiple addresses at once.

        WHY: Bulk operations are more efficient than individual writes.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        values = {
            "holding_registers[0]": 3600,
            "holding_registers[1]": 50,
            "coils[0]": True,
        }

        result = await data_store.bulk_write_memory("test_plc", values)

        assert result is True
        assert await data_store.read_memory("test_plc", "holding_registers[0]") == 3600
        assert await data_store.read_memory("test_plc", "holding_registers[1]") == 50
        assert await data_store.read_memory("test_plc", "coils[0]") is True

    @pytest.mark.asyncio
    async def test_bulk_read_memory(self):
        """Test reading entire memory map.

        WHY: Need to snapshot all device memory at once.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        # Write some values
        await data_store.write_memory("test_plc", "holding_registers[0]", 3600)
        await data_store.write_memory("test_plc", "holding_registers[1]", 50)

        # Bulk read
        memory = await data_store.bulk_read_memory("test_plc")

        assert memory is not None
        assert memory["holding_registers[0]"] == 3600
        assert memory["holding_registers[1]"] == 50

    @pytest.mark.asyncio
    async def test_bulk_read_returns_copy(self):
        """Test that bulk read returns a copy, not reference.

        WHY: Prevent external mutation of internal state.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])
        await data_store.write_memory("test_plc", "holding_registers[0]", 100)

        memory1 = await data_store.bulk_read_memory("test_plc")
        memory2 = await data_store.bulk_read_memory("test_plc")

        assert memory1 is not memory2  # Different objects
        assert memory1 == memory2  # Same content

    @pytest.mark.asyncio
    async def test_bulk_write_to_nonexistent_device(self):
        """Test bulk write to non-existent device returns False.

        WHY: Should fail gracefully.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        result = await data_store.bulk_write_memory(
            "nonexistent", {"holding_registers[0]": 100}
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_bulk_read_from_nonexistent_device(self):
        """Test bulk read from non-existent device returns None.

        WHY: Should indicate absence.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        memory = await data_store.bulk_read_memory("nonexistent")

        assert memory is None

    @pytest.mark.asyncio
    async def test_bulk_write_empty_values_raises(self):
        """Test that bulk write with empty values raises ValueError.

        WHY: Input validation - must have values to write.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        with pytest.raises(ValueError, match="values cannot be empty"):
            await data_store.bulk_write_memory("test_plc", {})

    @pytest.mark.asyncio
    async def test_bulk_write_merges_with_existing(self):
        """Test that bulk write merges with existing memory map.

        WHY: Bulk writes should add/update, not replace entire map.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        # First write
        await data_store.write_memory("test_plc", "holding_registers[0]", 100)

        # Bulk write different addresses
        await data_store.bulk_write_memory(
            "test_plc", {"holding_registers[1]": 200, "coils[0]": True}
        )

        # Original value should still exist
        assert await data_store.read_memory("test_plc", "holding_registers[0]") == 100
        assert await data_store.read_memory("test_plc", "holding_registers[1]") == 200


# ================================================================
# ADDRESS VALIDATION TESTS
# ================================================================
class TestDataStoreAddressValidation:
    """Test address format validation for different protocols."""

    @pytest.mark.asyncio
    async def test_modbus_holding_registers_address_valid(self):
        """Test that Modbus holding register addresses are accepted.

        WHY: Modbus is primary protocol - must support standard addressing.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        # Should not raise
        result = await data_store.write_memory("test_plc", "holding_registers[0]", 100)
        assert result is True

    @pytest.mark.asyncio
    async def test_modbus_coils_address_valid(self):
        """Test that Modbus coil addresses are accepted.

        WHY: Coils are Modbus digital outputs.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        result = await data_store.write_memory("test_plc", "coils[5]", True)
        assert result is True

    @pytest.mark.asyncio
    async def test_modbus_input_registers_address_valid(self):
        """Test that Modbus input register addresses are accepted.

        WHY: Input registers are Modbus analogue inputs.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        result = await data_store.write_memory("test_plc", "input_registers[10]", 50)
        assert result is True

    @pytest.mark.asyncio
    async def test_modbus_discrete_inputs_address_valid(self):
        """Test that Modbus discrete input addresses are accepted.

        WHY: Discrete inputs are Modbus digital inputs.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        result = await data_store.write_memory("test_plc", "discrete_inputs[3]", False)
        assert result is True

    @pytest.mark.asyncio
    async def test_opcua_address_valid(self):
        """Test that OPC UA addresses are accepted.

        WHY: OPC UA uses namespace;identifier format.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["opcua"])

        # String identifier
        result1 = await data_store.write_memory("test_plc", "ns=2;s=Temperature", 98.6)
        # Numeric identifier
        result2 = await data_store.write_memory("test_plc", "ns=2;i=1001", 100)

        assert result1 is True
        assert result2 is True

    @pytest.mark.asyncio
    async def test_iec104_address_valid(self):
        """Test that IEC 104 addresses are accepted.

        WHY: IEC 104 uses TYPE:IOA format.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_rtu", "rtu", 1, ["iec104"])

        result = await data_store.write_memory("test_rtu", "M_SP_NA_1:100", True)
        assert result is True

    @pytest.mark.asyncio
    async def test_custom_address_format_accepted(self):
        """Test that non-standard address formats are accepted with warning.

        WHY: Custom protocols may use different addressing - should allow but warn.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["custom"])

        # Should not raise, even though format is non-standard
        result = await data_store.write_memory("test_plc", "custom_addr_123", 100)
        assert result is True


# ================================================================
# METADATA OPERATION TESTS
# ================================================================
class TestDataStoreMetadataOperations:
    """Test metadata read/write operations."""

    @pytest.mark.asyncio
    async def test_update_metadata(self):
        """Test updating device metadata.

        WHY: Metadata stores configuration and context.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        metadata = {"location": "Building A", "ip": "192.168.1.10"}
        result = await data_store.update_metadata("test_plc", metadata)

        assert result is True
        read_metadata = await data_store.read_metadata("test_plc")
        assert read_metadata == metadata

    @pytest.mark.asyncio
    async def test_read_metadata_returns_copy(self):
        """Test that read_metadata returns a copy.

        WHY: Prevent external mutation of internal state.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device(
            "test_plc",
            "turbine_plc",
            1,
            ["modbus"],
            metadata={"location": "Building A"},
        )

        meta1 = await data_store.read_metadata("test_plc")
        meta2 = await data_store.read_metadata("test_plc")

        assert meta1 is not meta2  # Different objects
        assert meta1 == meta2  # Same content

    @pytest.mark.asyncio
    async def test_update_metadata_merges(self):
        """Test that metadata updates merge, not replace.

        WHY: Metadata is additive - new fields don't erase old ones.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device(
            "test_plc",
            "turbine_plc",
            1,
            ["modbus"],
            metadata={"location": "Building A"},
        )

        await data_store.update_metadata("test_plc", {"ip": "192.168.1.10"})

        metadata = await data_store.read_metadata("test_plc")
        assert metadata["location"] == "Building A"  # Original preserved
        assert metadata["ip"] == "192.168.1.10"  # New added

    @pytest.mark.asyncio
    async def test_update_metadata_nonexistent_device(self):
        """Test updating metadata on non-existent device returns False.

        WHY: Should fail gracefully.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        result = await data_store.update_metadata("nonexistent", {"key": "value"})

        assert result is False

    @pytest.mark.asyncio
    async def test_read_metadata_nonexistent_device(self):
        """Test reading metadata from non-existent device returns None.

        WHY: Should indicate absence.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        metadata = await data_store.read_metadata("nonexistent")

        assert metadata is None

    @pytest.mark.asyncio
    async def test_update_metadata_empty_device_name_raises(self):
        """Test that empty device name raises ValueError.

        WHY: Input validation.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        with pytest.raises(ValueError, match="device_name cannot be empty"):
            await data_store.update_metadata("", {"key": "value"})

    @pytest.mark.asyncio
    async def test_update_metadata_empty_metadata_raises(self):
        """Test that empty metadata raises ValueError.

        WHY: Must have metadata to update.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        with pytest.raises(ValueError, match="metadata cannot be empty"):
            await data_store.update_metadata("test_plc", {})


# ================================================================
# DEVICE ONLINE STATUS TESTS
# ================================================================
class TestDataStoreOnlineStatus:
    """Test device online/offline status management."""

    @pytest.mark.asyncio
    async def test_set_device_online(self):
        """Test setting device online.

        WHY: Devices transition between online and offline states.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        result = await data_store.set_device_online("test_plc", True)

        assert result is True
        is_online = await data_store.is_device_online("test_plc")
        assert is_online is True

    @pytest.mark.asyncio
    async def test_set_device_offline(self):
        """Test setting device offline.

        WHY: Devices can go offline.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])
        await data_store.set_device_online("test_plc", True)

        result = await data_store.set_device_online("test_plc", False)

        assert result is True
        is_online = await data_store.is_device_online("test_plc")
        assert is_online is False

    @pytest.mark.asyncio
    async def test_is_device_online_nonexistent_device(self):
        """Test checking online status of non-existent device returns None.

        WHY: Should indicate device doesn't exist.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        is_online = await data_store.is_device_online("nonexistent")

        assert is_online is None

    @pytest.mark.asyncio
    async def test_set_device_online_nonexistent_device(self):
        """Test setting online status of non-existent device returns False.

        WHY: Should fail gracefully.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        result = await data_store.set_device_online("nonexistent", True)

        assert result is False

    @pytest.mark.asyncio
    async def test_set_device_online_empty_name_raises(self):
        """Test that empty device name raises ValueError.

        WHY: Input validation.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        with pytest.raises(ValueError, match="device_name cannot be empty"):
            await data_store.set_device_online("", True)


# ================================================================
# DEVICE STATE QUERY TESTS
# ================================================================
class TestDataStoreStateQueries:
    """Test device state query operations."""

    @pytest.mark.asyncio
    async def test_get_device_state(self):
        """Test getting complete device state.

        WHY: Need access to full DeviceState object.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        device = await data_store.get_device_state("test_plc")

        assert device is not None
        assert device.device_name == "test_plc"
        assert device.device_type == "turbine_plc"

    @pytest.mark.asyncio
    async def test_get_all_device_states(self):
        """Test getting all device states.

        WHY: Need to enumerate all devices.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await data_store.register_device("plc_2", "substation_plc", 2, ["modbus"])

        devices = await data_store.get_all_device_states()

        assert len(devices) == 2
        assert "plc_1" in devices
        assert "plc_2" in devices

    @pytest.mark.asyncio
    async def test_get_devices_by_type(self):
        """Test filtering devices by type.

        WHY: Common query pattern - find all devices of specific type.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("turbine_1", "turbine_plc", 1, ["modbus"])
        await data_store.register_device("turbine_2", "turbine_plc", 2, ["modbus"])
        await data_store.register_device("sub_1", "substation_plc", 3, ["modbus"])

        turbines = await data_store.get_devices_by_type("turbine_plc")

        assert len(turbines) == 2
        assert all(d.device_type == "turbine_plc" for d in turbines)

    @pytest.mark.asyncio
    async def test_get_devices_by_protocol(self):
        """Test filtering devices by protocol.

        WHY: Need to find all devices supporting a protocol.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await data_store.register_device("plc_2", "turbine_plc", 2, ["modbus", "dnp3"])
        await data_store.register_device("rtu_1", "rtu", 3, ["dnp3"])

        modbus_devices = await data_store.get_devices_by_protocol("modbus")

        assert len(modbus_devices) == 2
        assert all("modbus" in d.protocols for d in modbus_devices)


# ================================================================
# SIMULATION-LEVEL OPERATION TESTS
# ================================================================
class TestDataStoreSimulationOperations:
    """Test simulation-level operations."""

    @pytest.mark.asyncio
    async def test_get_simulation_state(self):
        """Test getting simulation summary.

        WHY: Need access to simulation-level statistics.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await data_store.set_device_online("plc_1", True)

        summary = await data_store.get_simulation_state()

        assert "simulation" in summary
        assert "devices" in summary
        assert summary["devices"]["total"] == 1
        assert summary["devices"]["online"] == 1

    @pytest.mark.asyncio
    async def test_mark_simulation_running(self):
        """Test marking simulation as running.

        WHY: Need to track simulation lifecycle.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.mark_simulation_running(True)

        summary = await data_store.get_simulation_state()
        assert summary["simulation"]["running"] is True

    @pytest.mark.asyncio
    async def test_increment_update_cycle(self):
        """Test incrementing update cycle counter.

        WHY: Track simulation iterations.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.increment_update_cycle()
        await data_store.increment_update_cycle()

        summary = await data_store.get_simulation_state()
        assert summary["simulation"]["update_cycles"] == 2

    @pytest.mark.asyncio
    async def test_reset_simulation(self):
        """Test resetting simulation state.

        WHY: Need to clear all state between simulation runs.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("plc_1", "turbine_plc", 1, ["modbus"])
        await data_store.mark_simulation_running(True)

        await data_store.reset_simulation()

        devices = await data_store.get_all_device_states()
        assert len(devices) == 0

        summary = await data_store.get_simulation_state()
        assert summary["simulation"]["running"] is False


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestDataStoreIntegration:
    """Test DataStore integration with SystemState."""

    @pytest.mark.asyncio
    async def test_complete_device_workflow(self):
        """Test complete workflow: register, configure, use, unregister.

        WHY: Verify all operations work together correctly.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        # Register
        await data_store.register_device(
            "turbine_plc_1",
            "turbine_plc",
            1,
            ["modbus"],
            metadata={"location": "Building A"},
        )

        # Bring online
        await data_store.set_device_online("turbine_plc_1", True)

        # Write memory
        await data_store.bulk_write_memory(
            "turbine_plc_1",
            {
                "holding_registers[0]": 3600,
                "holding_registers[1]": 50,
                "coils[0]": True,
            },
        )

        # Read memory
        rpm = await data_store.read_memory("turbine_plc_1", "holding_registers[0]")
        assert rpm == 3600

        # Update metadata
        await data_store.update_metadata("turbine_plc_1", {"status": "operational"})

        # Verify state
        device = await data_store.get_device_state("turbine_plc_1")
        assert device.online is True
        assert device.metadata["location"] == "Building A"
        assert device.metadata["status"] == "operational"

        # Unregister
        await data_store.unregister_device("turbine_plc_1")
        device = await data_store.get_device_state("turbine_plc_1")
        assert device is None

    @pytest.mark.asyncio
    async def test_datastore_changes_visible_in_systemstate(self):
        """Test that DataStore changes are visible in SystemState.

        WHY: DataStore is a facade - changes must propagate to SystemState.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])
        await data_store.write_memory("test_plc", "holding_registers[0]", 3600)

        # Check via SystemState directly
        device = await system_state.get_device("test_plc")
        assert device is not None
        assert device.memory_map["holding_registers[0]"] == 3600


# ================================================================
# CONCURRENT ACCESS TESTS
# ================================================================
class TestDataStoreConcurrency:
    """Test concurrent access patterns."""

    @pytest.mark.asyncio
    async def test_concurrent_writes_to_different_devices(self):
        """Test concurrent writes to different devices are safe.

        WHY: Multiple coroutines may write to different devices.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        # Register devices
        for i in range(10):
            await data_store.register_device(f"plc_{i}", "turbine_plc", i, ["modbus"])

        async def write_device(device_id: int):
            device_name = f"plc_{device_id}"
            await data_store.write_memory(
                device_name, "holding_registers[0]", device_id * 100
            )

        # Write concurrently
        await asyncio.gather(*[write_device(i) for i in range(10)])

        # Verify all writes succeeded
        for i in range(10):
            value = await data_store.read_memory(f"plc_{i}", "holding_registers[0]")
            assert value == i * 100

    @pytest.mark.asyncio
    async def test_concurrent_reads_and_writes_same_device(self):
        """Test concurrent reads and writes to same device.

        WHY: Real simulation has constant read/write activity.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        results = []

        async def reader():
            for _ in range(50):
                value = await data_store.read_memory("test_plc", "holding_registers[0]")
                results.append(value)
                await asyncio.sleep(0.001)

        async def writer():
            for i in range(50):
                await data_store.write_memory("test_plc", "holding_registers[0]", i)
                await asyncio.sleep(0.001)

        # Run concurrently
        await asyncio.gather(reader(), reader(), writer())

        # Should complete without errors
        assert len(results) == 100

    @pytest.mark.asyncio
    async def test_concurrent_bulk_operations(self):
        """Test concurrent bulk read/write operations.

        WHY: Bulk operations must be thread-safe.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        async def bulk_operations():
            for i in range(10):
                # Bulk write
                await data_store.bulk_write_memory(
                    "test_plc",
                    {
                        f"holding_registers[{i}]": i * 100,
                        f"coils[{i}]": i % 2 == 0,
                    },
                )
                # Bulk read
                await data_store.bulk_read_memory("test_plc")

        # Run multiple bulk operation sequences concurrently
        await asyncio.gather(*[bulk_operations() for _ in range(3)])

        # Verify some values
        memory = await data_store.bulk_read_memory("test_plc")
        assert memory is not None
        assert len(memory) > 0


# ================================================================
# EDGE CASE TESTS
# ================================================================
class TestDataStoreEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_write_none_value(self):
        """Test writing None as a value.

        WHY: None might be used to clear a register.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        result = await data_store.write_memory("test_plc", "holding_registers[0]", None)

        assert result is True
        value = await data_store.read_memory("test_plc", "holding_registers[0]")
        assert value is None

    @pytest.mark.asyncio
    async def test_large_bulk_write(self):
        """Test bulk write with many addresses.

        WHY: PLCs can have thousands of registers.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["modbus"])

        # Write 1000 registers
        large_write = {f"holding_registers[{i}]": i for i in range(1000)}
        result = await data_store.bulk_write_memory("test_plc", large_write)

        assert result is True

        # Verify a few values
        assert await data_store.read_memory("test_plc", "holding_registers[0]") == 0
        assert await data_store.read_memory("test_plc", "holding_registers[500]") == 500
        assert await data_store.read_memory("test_plc", "holding_registers[999]") == 999

    @pytest.mark.asyncio
    async def test_special_characters_in_address(self):
        """Test addresses with special characters.

        WHY: Some protocols use complex addressing schemes.
        """
        system_state = SystemState()
        data_store = DataStore(system_state)

        await data_store.register_device("test_plc", "turbine_plc", 1, ["opcua"])

        # OPC UA can have complex node IDs
        result = await data_store.write_memory(
            "test_plc", "ns=2;s=Device.Sensor.Temperature", 98.6
        )

        assert result is True
        value = await data_store.read_memory(
            "test_plc", "ns=2;s=Device.Sensor.Temperature"
        )
        assert value == 98.6
