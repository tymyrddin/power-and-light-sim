# tests/unit/devices/test_hmi_workstation.py
"""Comprehensive tests for HMIWorkstation.

This is Level 6 in our dependency tree - HMIWorkstation depends on:
- BaseSupervisoryDevice (Level 5) - uses REAL BaseSupervisoryDevice
- BaseDevice (Level 4) - uses REAL BaseDevice
- DataStore (Level 2) - uses REAL DataStore
- SystemState (Level 1) - uses REAL SystemState (via DataStore)
- SimulationTime (Level 0) - uses REAL SimulationTime

Test Coverage:
- Initialization and configuration
- Device type and protocol support
- Screen management
- Operator login/logout
- SCADA integration
- Memory map structure
- Security characteristics
- DataStore integration
- Lifecycle management
"""

import asyncio

import pytest

from components.devices.operations_zone.hmi_workstation import (
    HMIScreen,
    HMIWorkstation,
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

    WHY: HMIWorkstation requires DataStore for registration.
    """
    system_state = SystemState()
    data_store = DataStore(system_state)
    yield data_store


@pytest.fixture
async def test_hmi(datastore_setup):
    """Create HMIWorkstation instance (not started).

    WHY: Most tests need an HMI instance.
    """
    data_store = datastore_setup
    hmi = HMIWorkstation(
        device_name="test_hmi_1",
        device_id=1,
        data_store=data_store,
        scada_server="test_scada",
        description="Test HMI workstation",
        scan_interval=0.01,  # Fast for testing
    )

    yield hmi

    # Cleanup
    if hmi.is_running():
        await hmi.stop()


@pytest.fixture
async def started_hmi(test_hmi):
    """Create and start an HMIWorkstation.

    WHY: Many tests need a running HMI.
    """
    await test_hmi.start()
    yield test_hmi

    # Cleanup
    if test_hmi.is_running():
        await test_hmi.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestHMIWorkstationInitialization:
    """Test HMI workstation initialization."""

    def test_init_with_defaults(self, datastore_setup):
        """Test initialising HMI with default parameters.

        WHY: Verify sensible defaults for HMI workstations.
        """
        data_store = datastore_setup
        hmi = HMIWorkstation(
            device_name="hmi_test",
            device_id=1,
            data_store=data_store,
        )

        assert hmi.device_name == "hmi_test"
        assert hmi.device_id == 1
        assert hmi.scan_interval == 0.5  # Default 500ms
        assert hmi.scada_server == "scada_master_1"
        assert hmi.os_version == "Windows 10"
        assert hmi.hmi_software == "Wonderware InTouch 2014"
        assert not hmi.is_online()
        assert not hmi.is_running()

    def test_init_with_custom_parameters(self, datastore_setup):
        """Test initialising HMI with custom parameters.

        WHY: HMI configuration should be customizable.
        """
        data_store = datastore_setup
        hmi = HMIWorkstation(
            device_name="custom_hmi",
            device_id=5,
            data_store=data_store,
            scada_server="my_scada",
            os_version="Windows 7",
            hmi_software="FactoryTalk View",
            scan_interval=0.25,
        )

        assert hmi.scada_server == "my_scada"
        assert hmi.os_version == "Windows 7"
        assert hmi.hmi_software == "FactoryTalk View"
        assert hmi.scan_interval == 0.25

    def test_device_type_is_hmi_workstation(self, test_hmi):
        """Test that _device_type() returns 'hmi_workstation'.

        WHY: HMI must identify correctly.
        """
        assert test_hmi._device_type() == "hmi_workstation"

    def test_supported_protocols(self, test_hmi):
        """Test that HMI supports expected protocols.

        WHY: HMI has remote access protocols.
        """
        protocols = test_hmi._supported_protocols()
        assert "http" in protocols
        assert "rdp" in protocols
        assert "vnc" in protocols

    def test_scada_server_added_as_poll_target(self, test_hmi):
        """Test that SCADA server is automatically added as poll target.

        WHY: HMI needs to poll SCADA for data.
        """
        assert "test_scada" in test_hmi.poll_targets
        target = test_hmi.poll_targets["test_scada"]
        assert target.protocol == "internal"

    def test_initial_operator_state(self, test_hmi):
        """Test that no operator is logged in initially.

        WHY: Operator must explicitly login.
        """
        assert test_hmi.operator_logged_in is False
        assert test_hmi.operator_name == ""
        assert test_hmi.login_time == 0.0

    def test_security_defaults(self, test_hmi):
        """Test default security characteristics.

        WHY: Simulates realistic HMI security weaknesses.
        """
        assert test_hmi.web_interface_enabled is True
        assert test_hmi.web_interface_port == 8080
        assert test_hmi.web_default_credentials == ("admin", "admin")
        assert test_hmi.rdp_enabled is True
        assert test_hmi.credentials_plaintext is True


# ================================================================
# SCREEN MANAGEMENT TESTS
# ================================================================
class TestHMIWorkstationScreens:
    """Test HMI screen management."""

    def test_add_screen(self, test_hmi):
        """Test adding a screen.

        WHY: HMI displays are organized into screens.
        """
        test_hmi.add_screen(
            screen_name="overview",
            tags=["TAG1", "TAG2"],
            controls=["CTRL1"],
        )

        assert "overview" in test_hmi.screens
        screen = test_hmi.screens["overview"]
        assert screen.screen_name == "overview"
        assert screen.tags_displayed == ["TAG1", "TAG2"]
        assert screen.controls_available == ["CTRL1"]

    def test_add_multiple_screens(self, test_hmi):
        """Test adding multiple screens.

        WHY: HMI typically has many screens.
        """
        test_hmi.add_screen("overview", ["TAG1"], [])
        test_hmi.add_screen("turbine", ["TURB_SPEED"], ["TURB_START"])
        test_hmi.add_screen("alarms", [], [])

        assert len(test_hmi.screens) == 3

    def test_navigate_to_screen(self, test_hmi):
        """Test navigating to a screen.

        WHY: Operators switch between screens.
        """
        test_hmi.add_screen("overview", [], [])
        test_hmi.add_screen("turbine", [], [])

        result = test_hmi.navigate_to_screen("turbine")
        assert result is True
        assert test_hmi.current_screen == "turbine"

    def test_navigate_to_nonexistent_screen(self, test_hmi):
        """Test navigating to nonexistent screen.

        WHY: Should handle invalid navigation gracefully.
        """
        result = test_hmi.navigate_to_screen("nonexistent")
        assert result is False
        assert test_hmi.current_screen is None

    def test_navigate_clears_screen_data(self, test_hmi):
        """Test that navigating clears cached screen data.

        WHY: New screen needs fresh data.
        """
        test_hmi.add_screen("screen1", [], [])
        test_hmi.add_screen("screen2", [], [])
        test_hmi.screen_data = {"old_tag": 123}

        test_hmi.navigate_to_screen("screen2")
        assert test_hmi.screen_data == {}


# ================================================================
# OPERATOR LOGIN TESTS
# ================================================================
class TestHMIWorkstationOperator:
    """Test HMI operator management."""

    def test_login_operator(self, test_hmi):
        """Test operator login.

        WHY: Operators must authenticate.
        """
        result = test_hmi.login_operator("operator1")

        assert result is True
        assert test_hmi.operator_logged_in is True
        assert test_hmi.operator_name == "operator1"
        assert test_hmi.login_time >= 0.0

    def test_login_uses_simulation_time(self, test_hmi, clean_simulation_time):
        """Test that login uses simulation time.

        WHY: Login time must use sim_time, not wall clock.
        """
        sim_time = clean_simulation_time
        # Note: sim_time.now() returns simulation time

        test_hmi.login_operator("operator1")

        # Login time should be from simulation time
        assert test_hmi.login_time == sim_time.now()

    def test_logout_operator(self, test_hmi):
        """Test operator logout.

        WHY: Operators log out when done.
        """
        test_hmi.login_operator("operator1")
        test_hmi.logout_operator()

        assert test_hmi.operator_logged_in is False
        assert test_hmi.operator_name == ""
        assert test_hmi.login_time == 0.0

    def test_logout_when_not_logged_in(self, test_hmi):
        """Test logout when no operator logged in.

        WHY: Should handle gracefully.
        """
        # Should not raise
        test_hmi.logout_operator()
        assert test_hmi.operator_logged_in is False


# ================================================================
# SCADA INTEGRATION TESTS
# ================================================================
class TestHMIWorkstationSCADA:
    """Test HMI SCADA integration."""

    @pytest.mark.asyncio
    async def test_get_tag_from_scada_no_data(self, test_hmi):
        """Test getting tag when SCADA has no data.

        WHY: Should return None if not available.
        """
        value = await test_hmi.get_tag_from_scada("NONEXISTENT")
        assert value is None

    @pytest.mark.asyncio
    async def test_send_command_requires_login(self, test_hmi):
        """Test that sending command requires operator login.

        WHY: Commands should require authentication.
        """
        # Not logged in
        result = await test_hmi.send_command_to_scada(
            "device", "holding_register", 0, 100
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_send_command_when_logged_in(self, started_hmi):
        """Test sending command when logged in.

        WHY: Logged in operators can send commands.
        """
        started_hmi.login_operator("operator1")

        result = await started_hmi.send_command_to_scada(
            "test_device", "holding_register", 0, 100
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_get_current_screen_data_no_screen(self, test_hmi):
        """Test getting screen data when no screen selected.

        WHY: Should return empty dict.
        """
        data = await test_hmi.get_current_screen_data()
        assert data == {}

    @pytest.mark.asyncio
    async def test_get_current_screen_data_returns_copy(self, test_hmi):
        """Test that get_current_screen_data returns a copy.

        WHY: Callers shouldn't modify internal state.
        """
        test_hmi.add_screen("test", ["TAG1"], [])
        test_hmi.navigate_to_screen("test")
        test_hmi.screen_data = {"TAG1": 123}

        data = await test_hmi.get_current_screen_data()
        data["TAG1"] = 999

        assert test_hmi.screen_data["TAG1"] == 123  # Unchanged


# ================================================================
# MEMORY MAP TESTS
# ================================================================
class TestHMIWorkstationMemoryMap:
    """Test HMI memory map structure."""

    @pytest.mark.asyncio
    async def test_memory_map_initialisation(self, test_hmi):
        """Test that memory map is initialised correctly.

        WHY: Memory map must have expected structure.
        """
        await test_hmi._initialise_memory_map()

        assert "operator_logged_in" in test_hmi.memory_map
        assert "operator_name" in test_hmi.memory_map
        assert "current_screen" in test_hmi.memory_map
        assert "screen_count" in test_hmi.memory_map
        assert "screens" in test_hmi.memory_map
        assert "screen_data" in test_hmi.memory_map
        assert "scada_server" in test_hmi.memory_map

    @pytest.mark.asyncio
    async def test_process_polled_data_updates_memory_map(self, test_hmi):
        """Test that _process_polled_data updates memory map.

        WHY: Memory map must reflect current state.
        """
        await test_hmi._initialise_memory_map()

        test_hmi.add_screen("test_screen", [], [])
        test_hmi.navigate_to_screen("test_screen")
        test_hmi.login_operator("test_operator")
        test_hmi.screen_data = {"TAG1": 42}

        await test_hmi._process_polled_data()

        assert test_hmi.memory_map["operator_logged_in"] is True
        assert test_hmi.memory_map["operator_name"] == "test_operator"
        assert test_hmi.memory_map["current_screen"] == "test_screen"
        assert test_hmi.memory_map["screen_data"]["TAG1"] == 42


# ================================================================
# SECURITY TESTS
# ================================================================
class TestHMIWorkstationSecurity:
    """Test HMI security characteristics."""

    def test_get_config_file_contents(self, test_hmi):
        """Test getting config file contents.

        WHY: Simulates plaintext credential vulnerability.
        """
        config = test_hmi.get_config_file_contents()

        assert "scada_server" in config
        assert "scada_password" in config
        assert config["scada_password"] == "scada123"  # Plaintext!
        assert "database" in config
        assert config["database"]["password"] == "HMI2014"  # Plaintext!


# ================================================================
# STATUS AND TELEMETRY TESTS
# ================================================================
class TestHMIWorkstationStatus:
    """Test HMI status and telemetry."""

    @pytest.mark.asyncio
    async def test_get_hmi_status(self, started_hmi):
        """Test getting HMI status.

        WHY: Status API must be complete.
        """
        started_hmi.add_screen("test", [], [])
        started_hmi.login_operator("operator1")

        await asyncio.sleep(0.02)

        status = await started_hmi.get_hmi_status()

        assert status["device_name"] == "test_hmi_1"
        assert status["os_version"] == "Windows 10"
        assert status["hmi_software"] == "Wonderware InTouch 2014"
        assert status["scada_server"] == "test_scada"
        assert status["screen_count"] == 1
        assert status["operator_logged_in"] is True
        assert status["operator_name"] == "operator1"

    @pytest.mark.asyncio
    async def test_get_telemetry(self, started_hmi):
        """Test getting HMI telemetry.

        WHY: Telemetry provides comprehensive status.
        """
        started_hmi.login_operator("operator1")

        telemetry = await started_hmi.get_telemetry()

        assert telemetry["device_name"] == "test_hmi_1"
        assert telemetry["device_type"] == "hmi_workstation"
        assert "operator" in telemetry
        assert telemetry["operator"]["logged_in"] is True
        assert "security" in telemetry
        assert telemetry["security"]["web_interface_enabled"] is True


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestHMIWorkstationIntegration:
    """Test HMI integration with dependencies."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, test_hmi, datastore_setup):
        """Test that HMI registers with DataStore.

        WHY: HMI must be accessible via DataStore.
        """
        data_store = datastore_setup

        await test_hmi.start()

        devices = await data_store.get_devices_by_type("hmi_workstation")
        assert len(devices) == 1
        assert devices[0].device_name == "test_hmi_1"

    @pytest.mark.asyncio
    async def test_memory_accessible_via_datastore(self, started_hmi, datastore_setup):
        """Test that HMI memory is accessible via DataStore.

        WHY: Other systems may need HMI state.
        """
        data_store = datastore_setup

        await asyncio.sleep(0.02)

        memory = await data_store.bulk_read_memory("test_hmi_1")
        assert memory is not None
        assert "scada_server" in memory

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, test_hmi):
        """Test complete HMI lifecycle.

        WHY: Verify end-to-end operation.
        """
        # 1. Start
        await test_hmi.start()
        assert test_hmi.is_online()
        assert test_hmi.is_running()

        # 2. Run
        await asyncio.sleep(0.03)
        assert test_hmi.metadata["scan_count"] > 0

        # 3. Reset
        await test_hmi.reset()
        assert test_hmi.metadata["scan_count"] == 0
        assert test_hmi.is_running()

        # 4. Stop
        await test_hmi.stop()
        assert not test_hmi.is_online()
        assert not test_hmi.is_running()

    @pytest.mark.asyncio
    async def test_inherits_from_base_supervisory_device(self, test_hmi):
        """Test that HMIWorkstation inherits from BaseSupervisoryDevice.

        WHY: Class hierarchy must be correct.
        """
        from components.devices.operations_zone.base_supervisory import (
            BaseSupervisoryDevice,
        )
        from components.devices.core.base_device import BaseDevice

        assert isinstance(test_hmi, BaseSupervisoryDevice)
        assert isinstance(test_hmi, BaseDevice)


# ================================================================
# HMI SCREEN DATACLASS TESTS
# ================================================================
class TestHMIScreen:
    """Test HMIScreen dataclass."""

    def test_hmi_screen_defaults(self):
        """Test HMIScreen default values.

        WHY: Verify sensible defaults.
        """
        screen = HMIScreen(screen_name="test")

        assert screen.screen_name == "test"
        assert screen.tags_displayed == []
        assert screen.controls_available == []

    def test_hmi_screen_custom_values(self):
        """Test HMIScreen with custom values.

        WHY: Should accept custom configuration.
        """
        screen = HMIScreen(
            screen_name="turbine",
            tags_displayed=["SPEED", "POWER"],
            controls_available=["START", "STOP"],
        )

        assert screen.screen_name == "turbine"
        assert screen.tags_displayed == ["SPEED", "POWER"]
        assert screen.controls_available == ["START", "STOP"]


# ================================================================
# CONCURRENT OPERATIONS TESTS
# ================================================================
class TestHMIWorkstationConcurrency:
    """Test concurrent HMI operations."""

    @pytest.mark.asyncio
    async def test_multiple_instances(self, datastore_setup):
        """Test multiple HMI workstations operating concurrently.

        WHY: Control rooms have multiple HMI stations.
        """
        data_store = datastore_setup

        hmis = [
            HMIWorkstation(f"hmi_{i}", i, data_store, scan_interval=0.01)
            for i in range(3)
        ]

        # Start all
        await asyncio.gather(*[h.start() for h in hmis])

        # Let them run
        await asyncio.sleep(0.05)

        # All should be running
        for hmi in hmis:
            assert hmi.is_running()
            assert hmi.metadata["scan_count"] > 0

        # Stop all
        await asyncio.gather(*[h.stop() for h in hmis])
