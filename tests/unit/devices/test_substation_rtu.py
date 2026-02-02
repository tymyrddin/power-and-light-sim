# tests/unit/devices/test_substation_rtu.py
"""Tests for SubstationRTU - DNP3-based RTU for distribution substations.

Tests:
- Initialization
- Breaker operations (trip, close)
- Protection relay configuration and evaluation
- Grid measurements
- Alarm detection
- Energy accumulation
- DNP3 point mapping
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from components.devices.control_zone.rtu.substation_rtu import (
    BreakerState,
    RelayType,
    SubstationRTU,
)
from components.physics.grid_physics import GridPhysics
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


def create_mock_grid_physics() -> MagicMock:
    """Create a mock GridPhysics with test-friendly behaviour.

    Note: Uses spec_set=False to allow test-specific methods like set_breaker_state
    that aren't part of the real GridPhysics interface.
    """
    mock = MagicMock()  # No spec - RTU calls methods not in GridPhysics interface

    mock._state = {
        "substations": {
            "substation_1": {
                "voltage_a": 11000.0,
                "voltage_b": 11000.0,
                "voltage_c": 11000.0,
                "current_a": 100.0,
                "current_b": 100.0,
                "current_c": 100.0,
                "active_power": 1900.0,
                "reactive_power": 500.0,
                "frequency": 50.0,
            }
        }
    }
    mock.breaker_states = {}

    def get_state() -> dict:
        return mock._state

    def set_breaker_state(breaker_id: str, closed: bool) -> None:
        mock.breaker_states[breaker_id] = closed

    # Wire up the mock methods
    mock.get_state.side_effect = get_state
    mock.set_breaker_state.side_effect = set_breaker_state

    return mock


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
def mock_grid():
    """Create mock grid physics."""
    return create_mock_grid_physics()


@pytest.fixture
async def substation_rtu(datastore_setup, mock_grid):
    """Create SubstationRTU instance."""
    rtu = SubstationRTU(
        device_name="substation_1_rtu",
        device_id=100,
        data_store=datastore_setup,
        description="Test Substation RTU",
        scan_interval=0.01,
        outstation_address=100,
        grid_physics=mock_grid,
    )
    yield rtu
    if rtu.is_running():
        await rtu.stop()


@pytest.fixture
async def configured_rtu(substation_rtu):
    """Create RTU with breakers and relays configured."""
    substation_rtu.add_breaker("BKR-001", "Main Incomer", rated_current=1200.0)
    substation_rtu.add_breaker("BKR-002", "Feeder 1", rated_current=600.0)
    substation_rtu.add_relay("R50-001", RelayType.OVERCURRENT, 1500.0)
    substation_rtu.add_relay("R27-001", RelayType.UNDERVOLTAGE, 9900.0)  # 90% of 11kV
    return substation_rtu


@pytest.fixture
async def started_rtu(configured_rtu):
    """Create and start configured RTU."""
    await configured_rtu.start()
    yield configured_rtu
    if configured_rtu.is_running():
        await configured_rtu.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestSubstationRTUInitialization:
    """Test SubstationRTU initialization."""

    def test_init_with_defaults(self, datastore_setup):
        """Test initialization with default parameters."""
        rtu = SubstationRTU(
            device_name="test_rtu",
            device_id=1,
            data_store=datastore_setup,
        )

        assert rtu.device_name == "test_rtu"
        assert rtu.outstation_address == 1
        assert rtu.dnp3_port == 20000
        assert rtu.voltage_a == 11000.0  # Default nominal

    def test_init_with_custom_dnp3(self, datastore_setup):
        """Test initialization with custom DNP3 settings."""
        rtu = SubstationRTU(
            device_name="custom_rtu",
            device_id=101,
            data_store=datastore_setup,
            outstation_address=101,
            master_address=2,
            dnp3_port=20001,
        )

        assert rtu.outstation_address == 101
        assert rtu.master_address == 2
        assert rtu.dnp3_port == 20001

    def test_device_type_is_substation_rtu(self, substation_rtu):
        """Test device type."""
        assert substation_rtu._device_type() == "substation_rtu"

    def test_supported_protocols(self, substation_rtu):
        """Test supported protocols."""
        protocols = substation_rtu._supported_protocols()
        assert "dnp3" in protocols
        assert "modbus" in protocols


# ================================================================
# BREAKER TESTS
# ================================================================
class TestSubstationRTUBreakers:
    """Test SubstationRTU breaker operations."""

    def test_add_breaker(self, substation_rtu):
        """Test adding a breaker."""
        result = substation_rtu.add_breaker("BKR-001", "Test Breaker", 1200.0)

        assert result is True
        assert "BKR-001" in substation_rtu.breakers
        assert substation_rtu.breakers["BKR-001"].rated_current == 1200.0

    def test_add_duplicate_breaker_fails(self, substation_rtu):
        """Test adding duplicate breaker fails."""
        substation_rtu.add_breaker("BKR-001", "First")
        result = substation_rtu.add_breaker("BKR-001", "Second")

        assert result is False

    def test_add_max_breakers(self, substation_rtu):
        """Test maximum breaker limit."""
        for i in range(SubstationRTU.MAX_BREAKERS):
            substation_rtu.add_breaker(f"BKR-{i:03d}", f"Breaker {i}")

        result = substation_rtu.add_breaker("BKR-EXTRA", "Extra")

        assert result is False

    @pytest.mark.asyncio
    async def test_trip_breaker(self, started_rtu):
        """Test tripping a breaker."""
        # Close breaker first
        started_rtu.breakers["BKR-001"].state = BreakerState.CLOSED

        result = await started_rtu.trip_breaker("BKR-001")

        assert result is True
        assert started_rtu.breakers["BKR-001"].state == BreakerState.OPEN

    @pytest.mark.asyncio
    async def test_close_breaker(self, started_rtu):
        """Test closing a breaker."""
        result = await started_rtu.close_breaker("BKR-001")

        assert result is True
        assert started_rtu.breakers["BKR-001"].state == BreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_close_breaker_blocked_by_tripped_relay(self, started_rtu):
        """Test that breaker close is blocked when relay is tripped."""
        # Trip a relay
        started_rtu.relays["R50-001"].tripped = True

        result = await started_rtu.close_breaker("BKR-001")

        assert result is False

    @pytest.mark.asyncio
    async def test_breaker_operation_count(self, started_rtu):
        """Test breaker operation counter."""
        started_rtu.breakers["BKR-001"].state = BreakerState.CLOSED
        initial_count = started_rtu.breakers["BKR-001"].operation_count

        await started_rtu.trip_breaker("BKR-001")
        await started_rtu.close_breaker("BKR-001")

        assert started_rtu.breakers["BKR-001"].operation_count == initial_count + 2


# ================================================================
# RELAY TESTS
# ================================================================
class TestSubstationRTURelays:
    """Test SubstationRTU relay operations."""

    def test_add_relay(self, substation_rtu):
        """Test adding a relay."""
        result = substation_rtu.add_relay("R50-001", RelayType.OVERCURRENT, 1200.0)

        assert result is True
        assert "R50-001" in substation_rtu.relays
        assert substation_rtu.relays["R50-001"].relay_type == RelayType.OVERCURRENT

    def test_add_duplicate_relay_fails(self, substation_rtu):
        """Test adding duplicate relay fails."""
        substation_rtu.add_relay("R50-001", RelayType.OVERCURRENT, 1000.0)
        result = substation_rtu.add_relay("R50-001", RelayType.OVERCURRENT, 1200.0)

        assert result is False

    def test_reset_relay(self, configured_rtu):
        """Test resetting a tripped relay."""
        configured_rtu.relays["R50-001"].tripped = True

        result = configured_rtu.reset_relay("R50-001")

        assert result is True
        assert configured_rtu.relays["R50-001"].tripped is False


# ================================================================
# MEASUREMENT TESTS
# ================================================================
class TestSubstationRTUMeasurements:
    """Test SubstationRTU measurement operations."""

    def test_set_voltage(self, substation_rtu):
        """Test setting voltage values."""
        substation_rtu.set_voltage(11000.0, 10900.0, 11100.0)

        assert substation_rtu.voltage_a == 11000.0
        assert substation_rtu.voltage_b == 10900.0
        assert substation_rtu.voltage_c == 11100.0

    def test_set_voltage_single_phase(self, substation_rtu):
        """Test setting single voltage applies to all phases."""
        substation_rtu.set_voltage(10500.0)

        assert substation_rtu.voltage_a == 10500.0
        assert substation_rtu.voltage_b == 10500.0
        assert substation_rtu.voltage_c == 10500.0

    def test_set_current(self, substation_rtu):
        """Test setting current values."""
        substation_rtu.set_current(150.0, 145.0, 155.0)

        assert substation_rtu.current_a == 150.0
        assert substation_rtu.current_b == 145.0
        assert substation_rtu.current_c == 155.0

    def test_set_power(self, substation_rtu):
        """Test setting power values."""
        substation_rtu.set_power(2000.0, 500.0)

        assert substation_rtu.active_power == 2000.0
        assert substation_rtu.reactive_power == 500.0

    def test_set_frequency(self, substation_rtu):
        """Test setting frequency."""
        substation_rtu.set_frequency(49.95)

        assert substation_rtu.frequency == 49.95


# ================================================================
# ALARM TESTS
# ================================================================
class TestSubstationRTUAlarms:
    """Test SubstationRTU alarm detection."""

    @pytest.mark.asyncio
    async def test_low_voltage_alarm(self, started_rtu, mock_grid):
        """Test low voltage alarm detection."""
        # Set voltage below 90% of nominal in mock grid
        # (scan cycle reads from grid physics and overwrites local values)
        mock_grid._state["substations"]["substation_1"]["voltage_a"] = 9500.0
        mock_grid._state["substations"]["substation_1"]["voltage_b"] = 9500.0
        mock_grid._state["substations"]["substation_1"]["voltage_c"] = 9500.0

        await asyncio.sleep(0.03)

        assert started_rtu.alarm_low_voltage is True

    @pytest.mark.asyncio
    async def test_high_voltage_alarm(self, started_rtu, mock_grid):
        """Test high voltage alarm detection."""
        # Set voltage above 110% of nominal in mock grid
        mock_grid._state["substations"]["substation_1"]["voltage_a"] = 12500.0
        mock_grid._state["substations"]["substation_1"]["voltage_b"] = 12500.0
        mock_grid._state["substations"]["substation_1"]["voltage_c"] = 12500.0

        await asyncio.sleep(0.03)

        assert started_rtu.alarm_high_voltage is True

    @pytest.mark.asyncio
    async def test_frequency_alarm(self, started_rtu, mock_grid):
        """Test frequency alarm detection."""
        # Set frequency below 49.5Hz threshold in mock grid
        mock_grid._state["substations"]["substation_1"]["frequency"] = 49.0

        await asyncio.sleep(0.03)

        assert started_rtu.alarm_frequency is True


# ================================================================
# PROTECTION EVALUATION TESTS
# ================================================================
class TestSubstationRTUProtection:
    """Test SubstationRTU protection relay evaluation."""

    @pytest.mark.asyncio
    async def test_overcurrent_trips_relay(self, started_rtu, mock_grid):
        """Test overcurrent condition trips relay."""
        # Set current above pickup (1500A) in mock grid
        mock_grid._state["substations"]["substation_1"]["current_a"] = 1600.0
        mock_grid._state["substations"]["substation_1"]["current_b"] = 1600.0
        mock_grid._state["substations"]["substation_1"]["current_c"] = 1600.0

        await asyncio.sleep(0.03)

        assert started_rtu.relays["R50-001"].tripped is True

    @pytest.mark.asyncio
    async def test_undervoltage_trips_relay(self, started_rtu, mock_grid):
        """Test undervoltage condition trips relay."""
        # Set voltage below pickup (9900V) in mock grid
        mock_grid._state["substations"]["substation_1"]["voltage_a"] = 9000.0
        mock_grid._state["substations"]["substation_1"]["voltage_b"] = 9000.0
        mock_grid._state["substations"]["substation_1"]["voltage_c"] = 9000.0

        await asyncio.sleep(0.03)

        assert started_rtu.relays["R27-001"].tripped is True

    @pytest.mark.asyncio
    async def test_relay_trip_opens_breakers(self, started_rtu, mock_grid):
        """Test that relay trip opens breakers."""
        # Close breaker first
        started_rtu.breakers["BKR-001"].state = BreakerState.CLOSED

        # Trigger overcurrent in mock grid
        mock_grid._state["substations"]["substation_1"]["current_a"] = 1600.0
        mock_grid._state["substations"]["substation_1"]["current_b"] = 1600.0
        mock_grid._state["substations"]["substation_1"]["current_c"] = 1600.0

        await asyncio.sleep(0.05)

        # Breaker should be open
        assert started_rtu.breakers["BKR-001"].state == BreakerState.OPEN


# ================================================================
# STATUS TESTS
# ================================================================
class TestSubstationRTUStatus:
    """Test SubstationRTU status reporting."""

    @pytest.mark.asyncio
    async def test_get_substation_status(self, started_rtu):
        """Test comprehensive status method."""
        status = await started_rtu.get_substation_status()

        assert "device_name" in status
        assert "dnp3_outstation_address" in status
        assert "grid" in status
        assert "energy" in status
        assert "alarms" in status
        assert "breakers" in status
        assert "relays" in status

    @pytest.mark.asyncio
    async def test_status_grid_values(self, started_rtu, mock_grid):
        """Test grid values in status."""
        # Update mock grid state (scan cycle reads from grid physics)
        mock_grid._state["substations"]["substation_1"]["voltage_a"] = 11000.0
        mock_grid._state["substations"]["substation_1"]["current_a"] = 200.0

        await asyncio.sleep(0.03)

        status = await started_rtu.get_substation_status()

        assert status["grid"]["voltage_a"] == 11000.0
        assert status["grid"]["current_a"] == 200.0


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestSubstationRTUIntegration:
    """Test SubstationRTU integration."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, configured_rtu, datastore_setup):
        """Test registration with DataStore."""
        await configured_rtu.start()

        devices = await datastore_setup.get_devices_by_type("substation_rtu")
        assert len(devices) == 1

    @pytest.mark.asyncio
    async def test_reads_from_grid_physics(self, started_rtu, mock_grid):
        """Test reading from grid physics."""
        mock_grid._state["substations"]["substation_1"]["voltage_a"] = 10800.0

        await asyncio.sleep(0.03)

        assert started_rtu.voltage_a == 10800.0

    @pytest.mark.asyncio
    async def test_writes_breaker_to_physics(self, started_rtu, mock_grid):
        """Test breaker state written to physics."""
        started_rtu.breakers["BKR-001"].state = BreakerState.CLOSED

        await started_rtu.trip_breaker("BKR-001")

        assert mock_grid.breaker_states.get("BKR-001") is False

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, configured_rtu):
        """Test complete RTU lifecycle."""
        await configured_rtu.start()
        assert configured_rtu.is_running()

        await asyncio.sleep(0.03)
        assert configured_rtu.metadata["scan_count"] > 0

        await configured_rtu.stop()
        assert not configured_rtu.is_running()
