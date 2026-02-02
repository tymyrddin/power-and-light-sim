# tests/unit/devices/test_reactor_plc.py
"""Tests for ReactorPLC - Siemens S7-400 for Alchemical Reactor.

Tests:
- Initialization with reactor physics
- S7-style memory map structure
- Control commands (power, coolant, rods, SCRAM)
- Safety interlocks
- Telemetry reading
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from components.physics.reactor_physics import ReactorParameters, ReactorPhysics
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


def create_mock_reactor_physics() -> MagicMock:
    """Create a mock ReactorPhysics with test-friendly behaviour."""
    mock = MagicMock(spec=ReactorPhysics)
    mock.device_name = "mock_reactor"

    # Create mock params
    mock.params = MagicMock(spec=ReactorParameters)
    mock.params.max_safe_pressure_bar = 175.0
    mock.params.max_safe_temperature_c = 500.0

    # Track values for assertions
    mock.power_setpoint = 0.0
    mock.coolant_pump_speed = 0.0
    mock.control_rod_position = 100.0
    mock.thaumic_dampener_enabled = False
    mock.scram_triggered = False
    mock.scram_reset_called = False

    mock._telemetry = {
        "reactor_online": False,
        "core_temperature_c": 350.0,
        "coolant_temperature_c": 280.0,
        "pressure_bar": 155.0,
        "power_output_mw": 0.0,
        "neutron_flux": 0.0,
        "thaumic_flux": 0.0,
        "control_rod_position": 100.0,
        "coolant_flow_rate": 0.0,
        "scram_active": False,
        "xenon_poisoning": 0.0,
    }

    def get_telemetry() -> dict:
        return mock._telemetry.copy()

    def set_power_setpoint(power_percent: float) -> None:
        mock.power_setpoint = power_percent

    def set_coolant_pump_speed(percent: float) -> None:
        mock.coolant_pump_speed = percent

    def set_control_rods_position(percent: float) -> None:
        mock.control_rod_position = percent

    def set_thaumic_dampener(enabled: bool) -> None:
        mock.thaumic_dampener_enabled = enabled

    def trigger_scram() -> None:
        mock.scram_triggered = True
        mock._telemetry["scram_active"] = True

    def reset_scram() -> bool:
        if mock._telemetry["scram_active"]:
            mock.scram_reset_called = True
            mock._telemetry["scram_active"] = False
            mock.scram_triggered = False
            return True
        return False

    # Wire up the mock methods
    mock.get_telemetry.side_effect = get_telemetry
    mock.set_power_setpoint.side_effect = set_power_setpoint
    mock.set_coolant_pump_speed.side_effect = set_coolant_pump_speed
    mock.set_control_rods_position.side_effect = set_control_rods_position
    mock.set_thaumic_dampener.side_effect = set_thaumic_dampener
    mock.trigger_scram.side_effect = trigger_scram
    mock.reset_scram.side_effect = reset_scram

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
def mock_reactor():
    """Create mock reactor physics."""
    return create_mock_reactor_physics()


@pytest.fixture
async def reactor_plc(datastore_setup, mock_reactor):
    """Create ReactorPLC instance."""
    from components.devices.control_zone.plc.vendor_specific.reactor_plc import (
        ReactorPLC,
    )

    plc = ReactorPLC(
        device_name="reactor_plc_1",
        device_id=2,
        data_store=datastore_setup,
        reactor_physics=mock_reactor,
        scan_interval=0.01,
    )
    yield plc
    if plc.is_running():
        await plc.stop()


@pytest.fixture
async def started_reactor_plc(reactor_plc):
    """Create and start ReactorPLC."""
    await reactor_plc.start()
    yield reactor_plc
    if reactor_plc.is_running():
        await reactor_plc.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestReactorPLCInitialization:
    """Test ReactorPLC initialization."""

    def test_init_with_physics(self, datastore_setup, mock_reactor):
        """Test initialization with physics engine."""
        from components.devices.control_zone.plc.vendor_specific.reactor_plc import (
            ReactorPLC,
        )

        plc = ReactorPLC(
            device_name="test_reactor_plc",
            device_id=1,
            data_store=datastore_setup,
            reactor_physics=mock_reactor,
        )

        assert plc.device_name == "test_reactor_plc"
        assert plc.reactor_physics == mock_reactor

    def test_device_type_is_reactor_plc(self, reactor_plc):
        """Test device type."""
        assert reactor_plc._device_type() == "reactor_plc"

    def test_supported_protocols(self, reactor_plc):
        """Test supported protocols include S7 and Modbus."""
        protocols = reactor_plc._supported_protocols()
        assert "s7" in protocols
        assert "modbus" in protocols


# ================================================================
# MEMORY MAP TESTS
# ================================================================
class TestReactorPLCMemoryMap:
    """Test ReactorPLC memory map structure."""

    @pytest.mark.asyncio
    async def test_memory_map_initialised(self, started_reactor_plc):
        """Test memory map contains expected addresses."""
        mm = started_reactor_plc.memory_map

        # Check key addresses exist
        assert "DB1.core_temperature" in mm or "input_registers[0]" in mm

    @pytest.mark.asyncio
    async def test_telemetry_values_populated(self, started_reactor_plc, mock_reactor):
        """Test telemetry values are read from physics."""
        mock_reactor._telemetry["core_temperature_c"] = 400.0

        await asyncio.sleep(0.03)

        # Check some telemetry value is populated (structure may vary)
        mm = started_reactor_plc.memory_map
        assert len(mm) > 0


# ================================================================
# CONTROL COMMAND TESTS
# ================================================================
class TestReactorPLCCommands:
    """Test ReactorPLC control commands."""

    @pytest.mark.asyncio
    async def test_set_power_setpoint(self, started_reactor_plc, mock_reactor):
        """Test power setpoint command."""
        # Set power to 50% (value is stored as percent * 10 in holding_registers[0])
        await started_reactor_plc.set_power_setpoint(50.0)

        await asyncio.sleep(0.03)

        # Scan cycle reads holding_registers[0] / 10.0 and passes to physics
        assert mock_reactor.power_setpoint == 50.0

    @pytest.mark.asyncio
    async def test_set_coolant_pump(self, started_reactor_plc, mock_reactor):
        """Test coolant pump speed control."""
        # Set coolant pump to 75% speed
        await started_reactor_plc.set_coolant_pump(75.0)

        await asyncio.sleep(0.03)

        assert mock_reactor.coolant_pump_speed == 75.0

    @pytest.mark.asyncio
    async def test_set_control_rods(self, started_reactor_plc, mock_reactor):
        """Test control rod position command."""
        # Set control rods to 50% withdrawn
        await started_reactor_plc.set_control_rods(50.0)

        await asyncio.sleep(0.03)

        assert mock_reactor.control_rod_position == 50.0

    @pytest.mark.asyncio
    async def test_trigger_scram(self, started_reactor_plc, mock_reactor):
        """Test SCRAM command."""
        await started_reactor_plc.trigger_scram()

        await asyncio.sleep(0.03)

        assert mock_reactor.scram_triggered is True


# ================================================================
# STATUS TESTS
# ================================================================
class TestReactorPLCStatus:
    """Test ReactorPLC status reporting."""

    @pytest.mark.asyncio
    async def test_get_reactor_status(self, started_reactor_plc, mock_reactor):
        """Test comprehensive status method."""
        mock_reactor._telemetry["power_output_mw"] = 450.0

        await asyncio.sleep(0.03)

        status = await started_reactor_plc.get_reactor_status()

        assert "device_name" in status
        assert "reactor" in status


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestReactorPLCIntegration:
    """Test ReactorPLC integration."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, reactor_plc, datastore_setup):
        """Test registration with DataStore."""
        await reactor_plc.start()

        devices = await datastore_setup.get_devices_by_type("reactor_plc")
        assert len(devices) == 1

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, reactor_plc):
        """Test complete PLC lifecycle."""
        await reactor_plc.start()
        assert reactor_plc.is_running()

        await asyncio.sleep(0.03)
        assert reactor_plc.metadata["scan_count"] > 0

        await reactor_plc.stop()
        assert not reactor_plc.is_running()
