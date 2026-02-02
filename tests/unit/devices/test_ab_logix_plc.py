# tests/unit/devices/test_ab_logix_plc.py
"""Tests for ABLogixPLC - Allen-Bradley ControlLogix/CompactLogix base class.

Tests:
- Initialization
- Tag operations (create, read, write)
- Controller-scoped vs program-scoped tags
- Data type handling
- Abstract method enforcement
"""

import asyncio

import pytest

from components.devices.control_zone.plc.vendor_specific.ab_logix_plc import (
    ABLogixPLC,
    LogixDataType,
)
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


# ================================================================
# CONCRETE ABLOGIXPLC IMPLEMENTATION FOR TESTING
# ================================================================
class ConcreteABLogixPLC(ABLogixPLC):
    """Concrete implementation of ABLogixPLC for testing."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_inputs_count = 0
        self.execute_logic_count = 0
        self.write_outputs_count = 0

    async def _initialise_memory_map(self) -> None:
        """Initialise test tag structure."""
        # Controller-scoped tags
        self.create_tag("Temperature", LogixDataType.REAL, 0.0)
        self.create_tag("Pressure", LogixDataType.REAL, 0.0)
        self.create_tag("Running", LogixDataType.BOOL, False)
        self.create_tag("Counter", LogixDataType.DINT, 0)

        # Program-scoped tags
        self.create_tag("Setpoint", LogixDataType.REAL, 100.0, program="MainProgram")
        self.create_tag("Mode", LogixDataType.DINT, 0, program="MainProgram")

        self.memory_map = {"tags": self.get_all_tags()}

    async def _read_inputs(self) -> None:
        """Read inputs (simulated)."""
        self.read_inputs_count += 1
        # Simulate sensor readings
        self.write_tag("Temperature", 25.0 + self.read_inputs_count * 0.1)
        self.write_tag("Counter", self.read_inputs_count)

    async def _execute_logic(self) -> None:
        """Execute ladder logic."""
        self.execute_logic_count += 1
        # Simple logic: set running if temp < setpoint
        temp = self.read_tag("Temperature")
        setpoint = self.read_tag("Program:MainProgram.Setpoint")
        self.write_tag("Running", temp < setpoint)

    async def _write_outputs(self) -> None:
        """Write outputs."""
        self.write_outputs_count += 1
        # Sync tags to memory map
        self._sync_tags_to_map()


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
async def logix_plc(datastore_setup):
    """Create ConcreteABLogixPLC instance."""
    plc = ConcreteABLogixPLC(
        device_name="test_logix_plc",
        device_id=1,
        data_store=datastore_setup,
        description="Test Allen-Bradley Logix PLC",
        scan_interval=0.01,
        slot=0,
    )
    yield plc
    if plc.is_running():
        await plc.stop()


@pytest.fixture
async def started_logix_plc(logix_plc):
    """Create and start ConcreteABLogixPLC."""
    await logix_plc.start()
    yield logix_plc
    if logix_plc.is_running():
        await logix_plc.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestABLogixPLCInitialization:
    """Test ABLogixPLC initialization."""

    def test_init_with_defaults(self, datastore_setup):
        """Test initialisation with default parameters."""
        plc = ConcreteABLogixPLC(
            device_name="logix_test",
            device_id=1,
            data_store=datastore_setup,
        )

        assert plc.device_name == "logix_test"
        assert plc.slot == 0
        assert plc.enip_port == 44818

    def test_init_with_custom_slot(self, datastore_setup):
        """Test initialisation with custom slot."""
        plc = ConcreteABLogixPLC(
            device_name="logix_custom",
            device_id=2,
            data_store=datastore_setup,
            slot=5,
        )

        assert plc.slot == 5

    def test_device_type_is_ab_logix_plc(self, logix_plc):
        """Test device type."""
        assert logix_plc._device_type() == "ab_logix_plc"

    def test_supported_protocols(self, logix_plc):
        """Test supported protocols."""
        protocols = logix_plc._supported_protocols()
        assert "ethernet_ip" in protocols
        assert "cip" in protocols
        assert "modbus" in protocols

    def test_default_program_created(self, logix_plc):
        """Test MainProgram is created by default."""
        assert "MainProgram" in logix_plc.programs


# ================================================================
# TAG CREATION TESTS
# ================================================================
class TestABLogixPLCTagCreation:
    """Test ABLogixPLC tag creation."""

    def test_create_controller_tag(self, logix_plc):
        """Test creating controller-scoped tag."""
        result = logix_plc.create_tag("NewTag", LogixDataType.REAL, 0.0)

        assert result is True
        assert "NewTag" in logix_plc.controller_tags

    def test_create_program_tag(self, logix_plc):
        """Test creating program-scoped tag."""
        result = logix_plc.create_tag(
            "LocalTag", LogixDataType.DINT, 0, program="MainProgram"
        )

        assert result is True
        assert "LocalTag" in logix_plc.programs["MainProgram"].tags

    def test_create_duplicate_tag_fails(self, logix_plc):
        """Test that creating duplicate tag fails."""
        logix_plc.create_tag("DupTag", LogixDataType.BOOL, False)
        result = logix_plc.create_tag("DupTag", LogixDataType.BOOL, True)

        assert result is False

    def test_create_bool_tag_convenience(self, logix_plc):
        """Test create_bool_tag convenience method."""
        result = logix_plc.create_bool_tag("BoolFlag", True)

        assert result is True
        assert logix_plc.controller_tags["BoolFlag"].data_type == LogixDataType.BOOL

    def test_create_dint_tag_convenience(self, logix_plc):
        """Test create_dint_tag convenience method."""
        result = logix_plc.create_dint_tag("IntValue", 42)

        assert result is True
        assert logix_plc.controller_tags["IntValue"].data_type == LogixDataType.DINT

    def test_create_real_tag_convenience(self, logix_plc):
        """Test create_real_tag convenience method."""
        result = logix_plc.create_real_tag("FloatValue", 3.14)

        assert result is True
        assert logix_plc.controller_tags["FloatValue"].data_type == LogixDataType.REAL


# ================================================================
# TAG READ/WRITE TESTS
# ================================================================
class TestABLogixPLCTagOperations:
    """Test ABLogixPLC tag read/write operations."""

    @pytest.mark.asyncio
    async def test_read_controller_tag(self, started_logix_plc):
        """Test reading controller-scoped tag."""
        value = started_logix_plc.read_tag("Counter")

        assert value is not None
        assert isinstance(value, int)

    @pytest.mark.asyncio
    async def test_read_program_tag(self, started_logix_plc):
        """Test reading program-scoped tag."""
        value = started_logix_plc.read_tag("Program:MainProgram.Setpoint")

        assert value == 100.0

    @pytest.mark.asyncio
    async def test_read_nonexistent_tag(self, started_logix_plc):
        """Test reading non-existent tag returns None."""
        value = started_logix_plc.read_tag("NonExistentTag")

        assert value is None

    @pytest.mark.asyncio
    async def test_write_controller_tag(self, started_logix_plc):
        """Test writing controller-scoped tag."""
        result = started_logix_plc.write_tag("Pressure", 150.0)

        assert result is True
        assert started_logix_plc.read_tag("Pressure") == 150.0

    @pytest.mark.asyncio
    async def test_write_program_tag(self, started_logix_plc):
        """Test writing program-scoped tag."""
        result = started_logix_plc.write_tag("Program:MainProgram.Mode", 2)

        assert result is True
        assert started_logix_plc.read_tag("Program:MainProgram.Mode") == 2

    @pytest.mark.asyncio
    async def test_write_nonexistent_tag(self, started_logix_plc):
        """Test writing non-existent tag fails."""
        result = started_logix_plc.write_tag("FakeTag", 0)

        assert result is False

    @pytest.mark.asyncio
    async def test_write_type_conversion(self, started_logix_plc):
        """Test automatic type conversion on write."""
        # Write string "42" to DINT tag
        started_logix_plc.write_tag("Counter", "42")

        assert started_logix_plc.read_tag("Counter") == 42

    @pytest.mark.asyncio
    async def test_read_only_tag(self, started_logix_plc):
        """Test writing to read-only tag fails."""
        started_logix_plc.create_tag(
            "ReadOnly", LogixDataType.DINT, 100, read_only=True
        )

        result = started_logix_plc.write_tag("ReadOnly", 200)

        assert result is False
        assert started_logix_plc.read_tag("ReadOnly") == 100


# ================================================================
# GET ALL TAGS TESTS
# ================================================================
class TestABLogixPLCGetAllTags:
    """Test get_all_tags functionality."""

    @pytest.mark.asyncio
    async def test_get_all_tags(self, started_logix_plc):
        """Test getting all tags as flat dict."""
        tags = started_logix_plc.get_all_tags()

        # Controller tags
        assert "Temperature" in tags
        assert "Running" in tags

        # Program tags (with prefix)
        assert "Program:MainProgram.Setpoint" in tags

    @pytest.mark.asyncio
    async def test_get_all_tags_values(self, started_logix_plc):
        """Test that tag values are correct."""
        started_logix_plc.write_tag("Temperature", 55.5)

        tags = started_logix_plc.get_all_tags()

        assert tags["Temperature"] == 55.5


# ================================================================
# SCAN CYCLE TESTS
# ================================================================
class TestABLogixPLCScanCycle:
    """Test ABLogixPLC scan cycle operations."""

    @pytest.mark.asyncio
    async def test_scan_cycle_executes(self, started_logix_plc):
        """Test that scan cycle executes all phases."""
        await asyncio.sleep(0.03)

        assert started_logix_plc.read_inputs_count > 0
        assert started_logix_plc.execute_logic_count > 0
        assert started_logix_plc.write_outputs_count > 0

    @pytest.mark.asyncio
    async def test_tags_updated_by_scan(self, started_logix_plc):
        """Test that tags are updated during scan."""
        initial_counter = started_logix_plc.read_tag("Counter")

        await asyncio.sleep(0.03)

        final_counter = started_logix_plc.read_tag("Counter")
        assert final_counter > initial_counter


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestABLogixPLCIntegration:
    """Test ABLogixPLC integration."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, logix_plc, datastore_setup):
        """Test registration with DataStore."""
        await logix_plc.start()

        devices = await datastore_setup.get_devices_by_type("ab_logix_plc")
        assert len(devices) == 1

    @pytest.mark.asyncio
    async def test_memory_map_contains_tags(self, started_logix_plc):
        """Test memory map contains tags."""
        mm = started_logix_plc.memory_map

        assert "tags" in mm
        assert "Temperature" in mm["tags"]
