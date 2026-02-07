# tests/unit/devices/test_engineering_workstation.py
"""Comprehensive tests for EngineeringWorkstation.

This is Level 5 in our dependency tree - EngineeringWorkstation depends on:
- BaseDevice (Level 4) - uses REAL BaseDevice
- DataStore (Level 2) - uses REAL DataStore
- SystemState (Level 1) - uses REAL SystemState (via DataStore)
- SimulationTime (Level 0) - uses REAL SimulationTime

Test Coverage:
- Initialization and configuration
- Device type and protocol support
- Project management
- User login/logout
- PLC programming
- Memory map structure
- Security characteristics
- DataStore integration
- Lifecycle management
"""

import asyncio

import pytest

from components.devices.operations_zone.engineering_workstation import (
    EngineeringWorkstation,
    ProjectFile,
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

    WHY: EngineeringWorkstation requires DataStore for registration.
    """
    system_state = SystemState()
    data_store = DataStore(system_state)
    yield data_store


@pytest.fixture
async def test_eng_ws(datastore_setup):
    """Create EngineeringWorkstation instance (not started).

    WHY: Most tests need an engineering workstation instance.
    """
    data_store = datastore_setup
    eng_ws = EngineeringWorkstation(
        device_name="test_eng_ws_1",
        device_id=1,
        data_store=data_store,
        os_version="Windows 10",
        patched=True,
        laptop=False,
        description="Test engineering workstation",
        scan_interval=0.01,  # Fast for testing
    )

    yield eng_ws

    # Cleanup
    if eng_ws.is_running():
        await eng_ws.stop()


@pytest.fixture
async def started_eng_ws(test_eng_ws):
    """Create and start an EngineeringWorkstation.

    WHY: Many tests need a running workstation.
    """
    await test_eng_ws.start()
    yield test_eng_ws

    # Cleanup
    if test_eng_ws.is_running():
        await test_eng_ws.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestEngineeringWorkstationInitialization:
    """Test engineering workstation initialization."""

    def test_init_with_defaults(self, datastore_setup):
        """Test initialising with default parameters.

        WHY: Verify sensible defaults for engineering workstations.
        """
        data_store = datastore_setup
        eng_ws = EngineeringWorkstation(
            device_name="eng_test",
            device_id=1,
            data_store=data_store,
        )

        assert eng_ws.device_name == "eng_test"
        assert eng_ws.device_id == 1
        assert eng_ws.scan_interval == 1.0  # Default 1s
        assert eng_ws.os_version == "Windows 7"
        assert eng_ws.patched is False
        assert eng_ws.laptop is True
        assert not eng_ws.is_online()
        assert not eng_ws.is_running()

    def test_init_with_custom_parameters(self, datastore_setup):
        """Test initialising with custom parameters.

        WHY: Configuration should be customizable.
        """
        data_store = datastore_setup
        eng_ws = EngineeringWorkstation(
            device_name="custom_eng",
            device_id=5,
            data_store=data_store,
            os_version="Windows 10",
            patched=True,
            laptop=False,
        )

        assert eng_ws.os_version == "Windows 10"
        assert eng_ws.patched is True
        assert eng_ws.laptop is False

    def test_device_type_is_engineering_workstation(self, test_eng_ws):
        """Test that _device_type() returns 'engineering_workstation'.

        WHY: Device must identify correctly.
        """
        assert test_eng_ws._device_type() == "engineering_workstation"

    def test_supported_protocols(self, test_eng_ws):
        """Test that workstation supports expected protocols.

        WHY: Engineering workstations have various access protocols.
        """
        protocols = test_eng_ws._supported_protocols()
        assert "rdp" in protocols
        assert "vnc" in protocols
        assert "ssh" in protocols
        assert "vendor_proprietary" in protocols

    def test_initial_user_state(self, test_eng_ws):
        """Test that no user is logged in initially.

        WHY: User must explicitly login.
        """
        assert test_eng_ws.current_user == ""
        assert test_eng_ws.login_time == 0.0

    def test_initial_projects_empty(self, test_eng_ws):
        """Test that projects list is initially empty.

        WHY: No projects configured by default.
        """
        assert len(test_eng_ws.projects) == 0

    def test_engineering_software_installed(self, test_eng_ws):
        """Test that engineering software is pre-configured.

        WHY: Workstations have vendor software installed.
        """
        assert "TIA Portal V15" in test_eng_ws.engineering_software
        assert "RSLogix 5000 v20.01" in test_eng_ws.engineering_software

    def test_security_defaults(self, test_eng_ws):
        """Test default security characteristics.

        WHY: Simulates realistic engineering workstation weaknesses.
        """
        assert test_eng_ws.has_antivirus is False
        assert test_eng_ws.admin_privileges is True
        assert test_eng_ws.rdp_enabled is True
        assert test_eng_ws.shared_account is True
        assert test_eng_ws.usb_ports_enabled is True
        assert test_eng_ws.bridges_networks is True

    def test_network_configuration(self, test_eng_ws):
        """Test network configuration.

        WHY: Engineering workstations bridge networks.
        """
        assert "corporate" in test_eng_ws.connected_networks
        assert "ot" in test_eng_ws.connected_networks
        assert test_eng_ws.wifi_enabled is True


# ================================================================
# PROJECT MANAGEMENT TESTS
# ================================================================
class TestEngineeringWorkstationProjects:
    """Test project management."""

    @pytest.mark.asyncio
    async def test_add_project(self, test_eng_ws):
        """Test adding a project.

        WHY: Workstations store project files.
        """
        await test_eng_ws.add_project(
            project_name="turbine_control",
            device_name="turbine_plc_1",
            file_type="plc_program",
        )

        assert len(test_eng_ws.projects) == 1
        project = test_eng_ws.projects[0]
        assert project.project_name == "turbine_control"
        assert project.device_name == "turbine_plc_1"
        assert project.file_type == "plc_program"
        assert project.contains_credentials is True  # Default

    @pytest.mark.asyncio
    async def test_add_project_uses_simulation_time(
        self, test_eng_ws, clean_simulation_time
    ):
        """Test that project last_modified uses simulation time.

        WHY: Timestamps must use sim_time, not wall clock.
        """
        sim_time = clean_simulation_time

        await test_eng_ws.add_project("test", "device", "plc_program")

        project = test_eng_ws.projects[0]
        assert project.last_modified == sim_time.now()

    @pytest.mark.asyncio
    async def test_add_project_custom_path(self, test_eng_ws):
        """Test adding project with custom file path.

        WHY: Projects can be stored anywhere.
        """
        await test_eng_ws.add_project(
            project_name="custom",
            device_name="device",
            file_type="plc_program",
            file_path="D:\\MyProjects\\custom.acd",
        )

        assert test_eng_ws.projects[0].file_path == "D:\\MyProjects\\custom.acd"

    @pytest.mark.asyncio
    async def test_add_project_default_path(self, test_eng_ws):
        """Test that default path is generated.

        WHY: Convenience for typical project storage.
        """
        await test_eng_ws.add_project("myproject", "device", "plc_program")

        assert (
            test_eng_ws.projects[0].file_path == "C:\\Projects\\myproject.plc_program"
        )

    @pytest.mark.asyncio
    async def test_add_multiple_projects(self, test_eng_ws):
        """Test adding multiple projects.

        WHY: Workstations have many project files.
        """
        await test_eng_ws.add_project("project1", "plc_1", "plc_program")
        await test_eng_ws.add_project("project2", "plc_2", "scada_config")
        await test_eng_ws.add_project("project3", "hmi_1", "hmi_project")

        assert len(test_eng_ws.projects) == 3

    @pytest.mark.asyncio
    async def test_get_project(self, test_eng_ws):
        """Test getting a project by name.

        WHY: Need to retrieve specific projects.
        """
        await test_eng_ws.add_project("target", "device", "plc_program")
        await test_eng_ws.add_project("other", "device2", "scada_config")

        project = test_eng_ws.get_project("target")
        assert project is not None
        assert project.project_name == "target"

    def test_get_nonexistent_project(self, test_eng_ws):
        """Test getting nonexistent project.

        WHY: Should return None.
        """
        project = test_eng_ws.get_project("nonexistent")
        assert project is None

    @pytest.mark.asyncio
    async def test_get_project_credentials(self, test_eng_ws):
        """Test getting credentials from project.

        WHY: Simulates credential extraction vulnerability.
        """
        await test_eng_ws.add_project(
            "with_creds", "plc_1", "plc_program", has_credentials=True
        )

        creds = await test_eng_ws.get_project_credentials("with_creds")
        assert creds is not None
        assert "plc_password" in creds
        assert "scada_db_password" in creds

    @pytest.mark.asyncio
    async def test_get_credentials_no_creds_project(self, test_eng_ws):
        """Test getting credentials from project without credentials.

        WHY: Not all projects store credentials.
        """
        await test_eng_ws.add_project(
            "no_creds", "plc_1", "plc_program", has_credentials=False
        )

        creds = await test_eng_ws.get_project_credentials("no_creds")
        assert creds is None


# ================================================================
# USER LOGIN TESTS
# ================================================================
class TestEngineeringWorkstationUser:
    """Test user management."""

    @pytest.mark.asyncio
    async def test_login(self, test_eng_ws):
        """Test user login.

        WHY: Users must authenticate.
        """
        result = await test_eng_ws.login("engineer")

        assert result is True
        assert test_eng_ws.current_user == "engineer"
        assert test_eng_ws.login_time >= 0.0

    @pytest.mark.asyncio
    async def test_login_uses_simulation_time(self, test_eng_ws, clean_simulation_time):
        """Test that login uses simulation time.

        WHY: Login time must use sim_time.
        """
        sim_time = clean_simulation_time

        await test_eng_ws.login("engineer")

        assert test_eng_ws.login_time == sim_time.now()

    @pytest.mark.asyncio
    async def test_login_wrong_username(self, test_eng_ws):
        """Test login with wrong username.

        WHY: Should fail for unknown users.
        """
        result = await test_eng_ws.login("unknown_user")

        assert result is False
        assert test_eng_ws.current_user == ""

    @pytest.mark.asyncio
    async def test_logout(self, test_eng_ws):
        """Test user logout.

        WHY: Users log out when done.
        """
        await test_eng_ws.login("engineer")
        await test_eng_ws.logout()

        assert test_eng_ws.current_user == ""
        assert test_eng_ws.login_time == 0.0

    @pytest.mark.asyncio
    async def test_logout_when_not_logged_in(self, test_eng_ws):
        """Test logout when no user logged in.

        WHY: Should handle gracefully.
        """
        # Should not raise
        await test_eng_ws.logout()
        assert test_eng_ws.current_user == ""


# ================================================================
# PLC PROGRAMMING TESTS
# ================================================================
class TestEngineeringWorkstationProgramming:
    """Test PLC programming functionality."""

    @pytest.mark.asyncio
    async def test_program_plc_requires_login(self, started_eng_ws):
        """Test that PLC programming requires login.

        WHY: Critical operation should require authentication.
        """
        # Not logged in
        result = await started_eng_ws.program_plc("plc_1", {"logic": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_program_plc_when_logged_in(self, started_eng_ws):
        """Test PLC programming when logged in.

        WHY: Logged in users can program PLCs.
        """
        await started_eng_ws.login("engineer")

        result = await started_eng_ws.program_plc("plc_1", {"logic": "test"})
        assert result is True


# ================================================================
# MEMORY MAP TESTS
# ================================================================
class TestEngineeringWorkstationMemoryMap:
    """Test memory map structure."""

    @pytest.mark.asyncio
    async def test_memory_map_initialisation(self, test_eng_ws):
        """Test that memory map is initialised correctly.

        WHY: Memory map must have expected structure.
        """
        await test_eng_ws._initialise_memory_map()

        assert "os_version" in test_eng_ws.memory_map
        assert "patched" in test_eng_ws.memory_map
        assert "current_user" in test_eng_ws.memory_map
        assert "connected_networks" in test_eng_ws.memory_map
        assert "project_count" in test_eng_ws.memory_map
        assert "projects" in test_eng_ws.memory_map

    @pytest.mark.asyncio
    async def test_scan_cycle_updates_memory_map(self, test_eng_ws):
        """Test that scan cycle updates memory map.

        WHY: Memory map must reflect current state.
        """
        await test_eng_ws._initialise_memory_map()

        await test_eng_ws.login("engineer")
        await test_eng_ws.add_project("test", "device", "plc_program")

        await test_eng_ws._scan_cycle()

        assert test_eng_ws.memory_map["current_user"] == "engineer"
        assert test_eng_ws.memory_map["project_count"] == 1
        assert "test" in test_eng_ws.memory_map["projects"]


# ================================================================
# STATUS AND TELEMETRY TESTS
# ================================================================
class TestEngineeringWorkstationStatus:
    """Test status and telemetry."""

    @pytest.mark.asyncio
    async def test_get_engineering_status(self, started_eng_ws):
        """Test getting engineering workstation status.

        WHY: Status API must be complete.
        """
        await started_eng_ws.login("engineer")
        await started_eng_ws.add_project("test", "device", "plc_program")

        await asyncio.sleep(0.02)

        status = await started_eng_ws.get_engineering_status()

        assert status["device_name"] == "test_eng_ws_1"
        assert status["os_version"] == "Windows 10"
        assert status["patched"] is True
        assert status["laptop"] is False
        assert status["current_user"] == "engineer"
        assert status["project_count"] == 1
        assert "bridges_networks" in status

    @pytest.mark.asyncio
    async def test_get_telemetry(self, started_eng_ws):
        """Test getting telemetry.

        WHY: Telemetry provides comprehensive status.
        """
        telemetry = await started_eng_ws.get_telemetry()

        assert telemetry["device_name"] == "test_eng_ws_1"
        assert telemetry["device_type"] == "engineering_workstation"
        assert "security" in telemetry
        assert telemetry["security"]["has_antivirus"] is False
        assert telemetry["security"]["bridges_networks"] is True


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestEngineeringWorkstationIntegration:
    """Test integration with dependencies."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, test_eng_ws, datastore_setup):
        """Test that workstation registers with DataStore.

        WHY: Must be accessible via DataStore.
        """
        data_store = datastore_setup

        await test_eng_ws.start()

        devices = await data_store.get_devices_by_type("engineering_workstation")
        assert len(devices) == 1
        assert devices[0].device_name == "test_eng_ws_1"

    @pytest.mark.asyncio
    async def test_memory_accessible_via_datastore(
        self, started_eng_ws, datastore_setup
    ):
        """Test that memory is accessible via DataStore.

        WHY: Other systems may need state.
        """
        data_store = datastore_setup

        await asyncio.sleep(0.02)

        memory = await data_store.bulk_read_memory("test_eng_ws_1")
        assert memory is not None
        assert "os_version" in memory

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, test_eng_ws):
        """Test complete workstation lifecycle.

        WHY: Verify end-to-end operation.
        """
        # 1. Start
        await test_eng_ws.start()
        assert test_eng_ws.is_online()
        assert test_eng_ws.is_running()

        # 2. Run
        await asyncio.sleep(0.03)
        assert test_eng_ws.metadata["scan_count"] > 0

        # 3. Reset
        await test_eng_ws.reset()
        assert test_eng_ws.metadata["scan_count"] == 0
        assert test_eng_ws.is_running()

        # 4. Stop
        await test_eng_ws.stop()
        assert not test_eng_ws.is_online()
        assert not test_eng_ws.is_running()

    @pytest.mark.asyncio
    async def test_inherits_from_base_device(self, test_eng_ws):
        """Test that EngineeringWorkstation inherits from BaseDevice.

        WHY: Class hierarchy must be correct.
        """
        from components.devices.core.base_device import BaseDevice

        assert isinstance(test_eng_ws, BaseDevice)


# ================================================================
# PROJECT FILE DATACLASS TESTS
# ================================================================
class TestProjectFile:
    """Test ProjectFile dataclass."""

    def test_project_file_defaults(self):
        """Test ProjectFile default values.

        WHY: Verify sensible defaults.
        """
        project = ProjectFile(
            project_name="test",
            device_name="device",
            file_type="plc_program",
        )

        assert project.project_name == "test"
        assert project.contains_credentials is False
        assert project.last_modified == 0.0
        assert project.file_path == ""

    def test_project_file_custom_values(self):
        """Test ProjectFile with custom values.

        WHY: Should accept custom configuration.
        """
        project = ProjectFile(
            project_name="custom",
            device_name="plc_1",
            file_type="scada_config",
            contains_credentials=True,
            last_modified=123.45,
            file_path="C:\\custom\\path.cfg",
        )

        assert project.contains_credentials is True
        assert project.last_modified == 123.45
        assert project.file_path == "C:\\custom\\path.cfg"


# ================================================================
# CONCURRENT OPERATIONS TESTS
# ================================================================
class TestEngineeringWorkstationConcurrency:
    """Test concurrent operations."""

    @pytest.mark.asyncio
    async def test_multiple_instances(self, datastore_setup):
        """Test multiple engineering workstations operating concurrently.

        WHY: Organizations may have multiple engineering workstations.
        """
        data_store = datastore_setup

        workstations = [
            EngineeringWorkstation(f"eng_{i}", i, data_store, scan_interval=0.01)
            for i in range(3)
        ]

        # Start all
        await asyncio.gather(*[ws.start() for ws in workstations])

        # Let them run
        await asyncio.sleep(0.05)

        # All should be running
        for ws in workstations:
            assert ws.is_running()
            assert ws.metadata["scan_count"] > 0

        # Stop all
        await asyncio.gather(*[ws.stop() for ws in workstations])
