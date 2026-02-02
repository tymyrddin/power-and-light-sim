# tests/unit/devices/test_s7_plc.py
"""Tests for S7PLC - Siemens S7-style PLC base class.

Tests:
- Initialization
- Data Block operations (create, read, write)
- I/O area operations (bit, byte, word)
- Merker operations
- Abstract method enforcement
"""

import asyncio
from typing import Any

import pytest

from components.devices.control_zone.plc.vendor_specific.s7_plc import S7PLC
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


# ================================================================
# CONCRETE S7PLC IMPLEMENTATION FOR TESTING
# ================================================================
class ConcreteS7PLC(S7PLC):
    """Concrete implementation of S7PLC for testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_inputs_count = 0
        self.execute_logic_count = 0
        self.write_outputs_count = 0

    async def _initialise_memory_map(self) -> None:
        """Initialise test memory map with DBs."""
        # Create Data Blocks
        self.create_db(1, {"temperature": 0.0, "pressure": 0.0, "running": False})
        self.create_db(2, {"setpoint": 100.0, "mode": 0})

        self.memory_map = {
            "DB1": self.data_blocks[1].copy(),
            "DB2": self.data_blocks[2].copy(),
            "s7_inputs": self.inputs.hex(),
            "s7_outputs": self.outputs.hex(),
            "s7_rack": self.rack,
            "s7_slot": self.slot,
        }

    async def _read_inputs(self) -> None:
        """Read inputs (simulated)."""
        self.read_inputs_count += 1
        # Simulate sensor reading
        self.data_blocks[1]["temperature"] = 25.0 + self.read_inputs_count * 0.1

    async def _execute_logic(self) -> None:
        """Execute control logic."""
        self.execute_logic_count += 1
        # Simple logic: set running if temp > setpoint
        temp = self.data_blocks[1]["temperature"]
        setpoint = self.data_blocks[2]["setpoint"]
        self.data_blocks[1]["running"] = temp < setpoint

    async def _write_outputs(self) -> None:
        """Write outputs."""
        self.write_outputs_count += 1
        # Write running status to output bit
        running = self.data_blocks[1]["running"]
        self.write_output_bit(0, 0, running)
        # Sync to memory map
        self._sync_memory_to_map()


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
async def s7_plc(datastore_setup):
    """Create ConcreteS7PLC instance."""
    plc = ConcreteS7PLC(
        device_name="test_s7_plc",
        device_id=1,
        data_store=datastore_setup,
        description="Test Siemens S7 PLC",
        scan_interval=0.01,
        rack=0,
        slot=2,
    )
    yield plc
    if plc.is_running():
        await plc.stop()


@pytest.fixture
async def started_s7_plc(s7_plc):
    """Create and start ConcreteS7PLC."""
    await s7_plc.start()
    yield s7_plc
    if s7_plc.is_running():
        await s7_plc.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestS7PLCInitialization:
    """Test S7PLC initialization."""

    def test_init_with_defaults(self, datastore_setup):
        """Test initialization with default parameters."""
        plc = ConcreteS7PLC(
            device_name="s7_test",
            device_id=1,
            data_store=datastore_setup,
        )

        assert plc.device_name == "s7_test"
        assert plc.rack == 0
        assert plc.slot == 2
        assert plc.s7_port == 102

    def test_init_with_custom_rack_slot(self, datastore_setup):
        """Test initialization with custom rack/slot."""
        plc = ConcreteS7PLC(
            device_name="s7_custom",
            device_id=2,
            data_store=datastore_setup,
            rack=1,
            slot=3,
        )

        assert plc.rack == 1
        assert plc.slot == 3

    def test_device_type_is_s7_plc(self, s7_plc):
        """Test device type."""
        assert s7_plc._device_type() == "s7_plc"

    def test_supported_protocols(self, s7_plc):
        """Test supported protocols."""
        protocols = s7_plc._supported_protocols()
        assert "s7" in protocols
        assert "profinet" in protocols
        assert "modbus" in protocols

    def test_memory_areas_initialised(self, s7_plc):
        """Test S7 memory areas are initialised."""
        assert len(s7_plc.inputs) == S7PLC.DEFAULT_INPUT_SIZE
        assert len(s7_plc.outputs) == S7PLC.DEFAULT_OUTPUT_SIZE
        assert len(s7_plc.merkers) == S7PLC.DEFAULT_MERKER_SIZE


# ================================================================
# DATA BLOCK TESTS
# ================================================================
class TestS7PLCDataBlocks:
    """Test S7PLC Data Block operations."""

    @pytest.mark.asyncio
    async def test_create_db(self, started_s7_plc):
        """Test creating a Data Block."""
        result = started_s7_plc.create_db(
            10, {"value1": 0, "value2": 0.0, "flag": False}
        )

        assert result is True
        assert 10 in started_s7_plc.data_blocks
        assert "value1" in started_s7_plc.data_blocks[10]

    @pytest.mark.asyncio
    async def test_create_duplicate_db_fails(self, started_s7_plc):
        """Test that creating duplicate DB fails."""
        started_s7_plc.create_db(20, {"test": 0})
        result = started_s7_plc.create_db(20, {"test2": 0})

        assert result is False

    @pytest.mark.asyncio
    async def test_read_db_entire(self, started_s7_plc):
        """Test reading entire Data Block."""
        db = started_s7_plc.read_db(1)

        assert db is not None
        assert "temperature" in db
        assert "pressure" in db

    @pytest.mark.asyncio
    async def test_read_db_variable(self, started_s7_plc):
        """Test reading specific DB variable."""
        value = started_s7_plc.read_db(2, "setpoint")

        assert value == 100.0

    @pytest.mark.asyncio
    async def test_read_db_nonexistent(self, started_s7_plc):
        """Test reading non-existent DB returns None."""
        result = started_s7_plc.read_db(999)

        assert result is None

    @pytest.mark.asyncio
    async def test_write_db(self, started_s7_plc):
        """Test writing to Data Block."""
        result = started_s7_plc.write_db(1, "pressure", 150.0)

        assert result is True
        assert started_s7_plc.data_blocks[1]["pressure"] == 150.0

    @pytest.mark.asyncio
    async def test_write_db_nonexistent(self, started_s7_plc):
        """Test writing to non-existent DB fails."""
        result = started_s7_plc.write_db(999, "test", 0)

        assert result is False


# ================================================================
# I/O OPERATIONS TESTS
# ================================================================
class TestS7PLCIO:
    """Test S7PLC I/O operations."""

    def test_read_write_input_bit(self, s7_plc):
        """Test input bit operations."""
        # Inputs are typically read-only from field, but we can set for testing
        s7_plc.inputs[0] = 0b00000101  # Bits 0 and 2 set

        assert s7_plc.read_input_bit(0, 0) is True
        assert s7_plc.read_input_bit(0, 1) is False
        assert s7_plc.read_input_bit(0, 2) is True

    def test_read_input_byte(self, s7_plc):
        """Test input byte read."""
        s7_plc.inputs[5] = 0xAB

        assert s7_plc.read_input_byte(5) == 0xAB

    def test_read_input_word(self, s7_plc):
        """Test input word read (big-endian)."""
        s7_plc.inputs[10] = 0x12
        s7_plc.inputs[11] = 0x34

        assert s7_plc.read_input_word(10) == 0x1234

    def test_write_output_bit(self, s7_plc):
        """Test output bit write."""
        s7_plc.write_output_bit(0, 3, True)

        assert s7_plc.outputs[0] & (1 << 3) != 0

        s7_plc.write_output_bit(0, 3, False)

        assert s7_plc.outputs[0] & (1 << 3) == 0

    def test_write_output_byte(self, s7_plc):
        """Test output byte write."""
        s7_plc.write_output_byte(5, 0xCD)

        assert s7_plc.outputs[5] == 0xCD

    def test_write_output_word(self, s7_plc):
        """Test output word write (big-endian)."""
        s7_plc.write_output_word(10, 0x5678)

        assert s7_plc.outputs[10] == 0x56
        assert s7_plc.outputs[11] == 0x78


# ================================================================
# MERKER TESTS
# ================================================================
class TestS7PLCMerkers:
    """Test S7PLC Merker operations."""

    def test_read_write_merker_bit(self, s7_plc):
        """Test merker bit operations."""
        s7_plc.write_merker_bit(0, 5, True)

        assert s7_plc.read_merker_bit(0, 5) is True
        assert s7_plc.read_merker_bit(0, 4) is False

    def test_read_write_merker_word(self, s7_plc):
        """Test merker word operations."""
        s7_plc.write_merker_word(20, 0xABCD)

        assert s7_plc.read_merker_word(20) == 0xABCD


# ================================================================
# SCAN CYCLE TESTS
# ================================================================
class TestS7PLCScanCycle:
    """Test S7PLC scan cycle operations."""

    @pytest.mark.asyncio
    async def test_scan_cycle_executes(self, started_s7_plc):
        """Test that scan cycle executes all phases."""
        await asyncio.sleep(0.03)

        assert started_s7_plc.read_inputs_count > 0
        assert started_s7_plc.execute_logic_count > 0
        assert started_s7_plc.write_outputs_count > 0

    @pytest.mark.asyncio
    async def test_db_values_updated_by_scan(self, started_s7_plc):
        """Test that DB values are updated during scan."""
        initial_temp = started_s7_plc.data_blocks[1]["temperature"]

        await asyncio.sleep(0.03)

        final_temp = started_s7_plc.data_blocks[1]["temperature"]
        assert final_temp != initial_temp


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestS7PLCIntegration:
    """Test S7PLC integration."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, s7_plc, datastore_setup):
        """Test registration with DataStore."""
        await s7_plc.start()

        devices = await datastore_setup.get_devices_by_type("s7_plc")
        assert len(devices) == 1

    @pytest.mark.asyncio
    async def test_memory_map_contains_dbs(self, started_s7_plc):
        """Test memory map contains Data Blocks."""
        mm = started_s7_plc.memory_map

        assert "DB1" in mm
        assert "DB2" in mm
