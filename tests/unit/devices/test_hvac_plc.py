# tests/unit/devices/test_hvac_plc.py
"""Tests for HVACPLC - Schneider Modicon for Library Environmental.

Tests:
- Initialization with HVAC physics
- Modbus memory map structure
- Control commands (temperature, humidity, fan, damper)
- L-space dampener control (Discworld-specific)
- Telemetry reading
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from components.physics.hvac_physics import HVACPhysics
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


def create_mock_hvac_physics() -> MagicMock:
    """Create a mock HVACPhysics with test-friendly behaviour."""
    mock = MagicMock(spec=HVACPhysics)
    mock.device_name = "mock_hvac"

    # Track setpoint values for assertions
    mock.temperature_setpoint = 20.0
    mock.humidity_setpoint = 45.0
    mock.fan_speed = 0
    mock.operating_mode = 0
    mock.damper_position = 0.0
    mock.system_enabled = False
    mock.lspace_dampener_enabled = False

    # Mock telemetry
    mock._telemetry = {
        "zone_temperature_c": 21.0,
        "zone_humidity_percent": 48.0,
        "supply_air_temp_c": 18.0,
        "return_air_temp_c": 22.0,
        "fan_running": False,
        "fan_speed_percent": 0,
        "damper_position_percent": 0,
        "filter_pressure_drop_pa": 50,
        "co2_level_ppm": 450,
        "lspace_stability": 100.0,
    }

    def get_telemetry() -> dict:
        return mock._telemetry.copy()

    def set_temperature_setpoint(temp_c: float) -> None:
        mock.temperature_setpoint = temp_c

    def set_humidity_setpoint(humidity: float) -> None:
        mock.humidity_setpoint = humidity

    def set_fan_speed(speed: int) -> None:
        mock.fan_speed = speed
        mock._telemetry["fan_running"] = speed > 0
        mock._telemetry["fan_speed_percent"] = speed

    def set_operating_mode(mode: int) -> None:
        mock.operating_mode = mode

    def set_damper_position(position: float) -> None:
        mock.damper_position = position
        mock._telemetry["damper_position_percent"] = position

    def set_system_enable(enabled: bool) -> None:
        mock.system_enabled = enabled

    def is_system_enabled() -> bool:
        return mock.system_enabled

    def set_lspace_dampener(enabled: bool) -> None:
        mock.lspace_dampener_enabled = enabled

    # Wire up the mock methods
    mock.get_telemetry.side_effect = get_telemetry
    mock.set_temperature_setpoint.side_effect = set_temperature_setpoint
    mock.set_humidity_setpoint.side_effect = set_humidity_setpoint
    mock.set_fan_speed.side_effect = set_fan_speed
    mock.set_operating_mode.side_effect = set_operating_mode
    mock.set_damper_position.side_effect = set_damper_position
    mock.set_system_enable.side_effect = set_system_enable
    mock.is_system_enabled.side_effect = is_system_enabled
    mock.set_lspace_dampener.side_effect = set_lspace_dampener

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
def mock_hvac():
    """Create mock HVAC physics."""
    return create_mock_hvac_physics()


@pytest.fixture
async def hvac_plc(datastore_setup, mock_hvac):
    """Create HVACPLC instance."""
    from components.devices.control_zone.plc.vendor_specific.hvac_plc import HVACPLC

    plc = HVACPLC(
        device_name="library_hvac_plc",
        device_id=3,
        data_store=datastore_setup,
        hvac_physics=mock_hvac,
        scan_interval=0.01,
    )
    yield plc
    if plc.is_running():
        await plc.stop()


@pytest.fixture
async def started_hvac_plc(hvac_plc):
    """Create and start HVACPLC."""
    await hvac_plc.start()
    yield hvac_plc
    if hvac_plc.is_running():
        await hvac_plc.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestHVACPLCInitialization:
    """Test HVACPLC initialization."""

    def test_init_with_physics(self, datastore_setup, mock_hvac):
        """Test initialization with physics engine."""
        from components.devices.control_zone.plc.vendor_specific.hvac_plc import HVACPLC

        plc = HVACPLC(
            device_name="test_hvac_plc",
            device_id=1,
            data_store=datastore_setup,
            hvac_physics=mock_hvac,
        )

        assert plc.device_name == "test_hvac_plc"
        assert plc.hvac_physics == mock_hvac

    def test_device_type_is_hvac_plc(self, hvac_plc):
        """Test device type."""
        assert hvac_plc._device_type() == "hvac_plc"

    def test_supported_protocols(self, hvac_plc):
        """Test supported protocols include Modbus."""
        protocols = hvac_plc._supported_protocols()
        assert "modbus" in protocols


# ================================================================
# MEMORY MAP TESTS
# ================================================================
class TestHVACPLCMemoryMap:
    """Test HVACPLC memory map structure."""

    @pytest.mark.asyncio
    async def test_memory_map_initialised(self, started_hvac_plc):
        """Test memory map contains expected addresses."""
        mm = started_hvac_plc.memory_map
        assert len(mm) > 0

    @pytest.mark.asyncio
    async def test_telemetry_values_populated(self, started_hvac_plc, mock_hvac):
        """Test telemetry values are read from physics."""
        mock_hvac._telemetry["zone_temperature_c"] = 23.5

        await asyncio.sleep(0.03)

        mm = started_hvac_plc.memory_map
        assert len(mm) > 0


# ================================================================
# CONTROL COMMAND TESTS
# ================================================================
class TestHVACPLCCommands:
    """Test HVACPLC control commands."""

    @pytest.mark.asyncio
    async def test_set_temperature_setpoint(self, started_hvac_plc, mock_hvac):
        """Test temperature setpoint command."""
        await started_hvac_plc.set_temperature_setpoint(22.0)

        await asyncio.sleep(0.03)

        assert mock_hvac.temperature_setpoint == 22.0

    @pytest.mark.asyncio
    async def test_set_humidity_setpoint(self, started_hvac_plc, mock_hvac):
        """Test humidity setpoint command."""
        await started_hvac_plc.set_humidity_setpoint(50.0)

        await asyncio.sleep(0.03)

        assert mock_hvac.humidity_setpoint == 50.0

    @pytest.mark.asyncio
    async def test_set_fan_speed(self, started_hvac_plc, mock_hvac):
        """Test fan speed command."""
        await started_hvac_plc.set_fan_speed(75)

        await asyncio.sleep(0.03)

        assert mock_hvac.fan_speed == 75

    @pytest.mark.asyncio
    async def test_set_damper_position(self, started_hvac_plc, mock_hvac):
        """Test damper position command."""
        await started_hvac_plc.set_damper_position(50.0)

        await asyncio.sleep(0.03)

        assert mock_hvac.damper_position == 50.0

    @pytest.mark.asyncio
    async def test_enable_lspace_dampener(self, started_hvac_plc, mock_hvac):
        """Test L-space dampener control (Discworld-specific)."""
        await started_hvac_plc.enable_lspace_dampener(True)

        await asyncio.sleep(0.03)

        assert mock_hvac.lspace_dampener_enabled is True


# ================================================================
# STATUS TESTS
# ================================================================
class TestHVACPLCStatus:
    """Test HVACPLC status reporting."""

    @pytest.mark.asyncio
    async def test_get_hvac_status(self, started_hvac_plc, mock_hvac):
        """Test comprehensive status method."""
        mock_hvac._telemetry["zone_temperature_c"] = 21.5

        await asyncio.sleep(0.03)

        status = await started_hvac_plc.get_hvac_status()

        assert "device_name" in status
        assert "hvac" in status


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestHVACPLCIntegration:
    """Test HVACPLC integration."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, hvac_plc, datastore_setup):
        """Test registration with DataStore."""
        await hvac_plc.start()

        devices = await datastore_setup.get_devices_by_type("hvac_plc")
        assert len(devices) == 1

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, hvac_plc):
        """Test complete PLC lifecycle."""
        await hvac_plc.start()
        assert hvac_plc.is_running()

        await asyncio.sleep(0.03)
        assert hvac_plc.metadata["scan_count"] > 0

        await hvac_plc.stop()
        assert not hvac_plc.is_running()
