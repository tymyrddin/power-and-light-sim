# tests/unit/devices/test_legacy_workstation.py
"""Comprehensive tests for LegacyWorkstation - The Forgotten Box.

Testing the monument to technical debt. A Windows 98 machine that's been
running since 1998, collecting turbine data, and serving as an
unintentional honeypot/pivot point.

Test Coverage:
- Initialization and system configuration
- Device type and protocol support
- Data collection via serial
- SMB share enumeration (no auth required)
- Credential harvesting
- Vulnerability enumeration
- Filesystem archaeology
- Floppy disk reading
- Historical data access
- Uptime tracking (it's been a while)
"""

import asyncio

import pytest

from components.devices.enterprise_zone.legacy_workstation import (
    CSVLogEntry,
    DiscoveredArtifact,
    LegacyWorkstation,
)
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


# ================================================================
# MOCK TURBINE PHYSICS
# ================================================================
class MockTurbineState:
    """Mock TurbineState object with attributes matching real TurbineState."""

    def __init__(
        self,
        shaft_speed_rpm: float = 3600.0,
        power_output_mw: float = 100.0,
        bearing_temperature_c: float = 72.0,
        vibration_mils: float = 31.5,  # ~0.8 mm/s converted to mils
        steam_pressure_psi: float = 1200.0,
        steam_temperature_c: float = 300.0,
        cumulative_overspeed_time: float = 0.0,
        damage_level: float = 0.0,
    ):
        self.shaft_speed_rpm = shaft_speed_rpm
        self.power_output_mw = power_output_mw
        self.bearing_temperature_c = bearing_temperature_c
        self.vibration_mils = vibration_mils
        self.steam_pressure_psi = steam_pressure_psi
        self.steam_temperature_c = steam_temperature_c
        self.cumulative_overspeed_time = cumulative_overspeed_time
        self.damage_level = damage_level


class MockTurbinePhysics:
    """Mock TurbinePhysics for testing serial data collection."""

    def __init__(self):
        self.state = MockTurbineState()

    def get_state(self) -> MockTurbineState:
        """Return TurbineState-like object, not dict."""
        return self.state

    @property
    def speed_rpm(self) -> float:
        """Compatibility property for tests."""
        return self.state.shaft_speed_rpm

    @property
    def power_output_mw(self) -> float:
        """Compatibility property for tests."""
        return self.state.power_output_mw


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
async def clean_simulation_time():
    """Reset SimulationTime singleton before each test."""
    sim_time = SimulationTime()
    await sim_time.reset()
    yield sim_time
    await sim_time.reset()


@pytest.fixture
async def datastore_setup(clean_simulation_time):
    """Create DataStore with SystemState."""
    system_state = SystemState()
    data_store = DataStore(system_state)
    yield data_store


@pytest.fixture
def mock_turbine_physics():
    """Create mock turbine physics."""
    return MockTurbinePhysics()


@pytest.fixture
async def test_legacy(datastore_setup, mock_turbine_physics):
    """Create LegacyWorkstation instance (not started)."""
    data_store = datastore_setup
    legacy = LegacyWorkstation(
        device_name="forgotten_box",
        device_id=98,  # Windows 98!
        data_store=data_store,
        turbine_physics=mock_turbine_physics,
        scan_interval=0.01,  # Fast for testing
    )

    yield legacy

    if legacy.is_running():
        await legacy.stop()


@pytest.fixture
async def started_legacy(test_legacy):
    """Create and start a LegacyWorkstation."""
    await test_legacy.start()
    yield test_legacy

    if test_legacy.is_running():
        await test_legacy.stop()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestLegacyWorkstationInitialization:
    """Test the forgotten box initialization."""

    def test_init_windows_98(self, datastore_setup):
        """Test that it's running Windows 98 SE.

        WHY: Authenticity - it's been this way since 1998.
        """
        data_store = datastore_setup
        legacy = LegacyWorkstation(
            device_name="old_box",
            device_id=98,
            data_store=data_store,
        )

        assert legacy.os_version == "Windows 98 SE"
        assert legacy.os_build == "4.10.2222 A"
        assert legacy.installed_date == "1998-01-15"

    def test_device_type_is_legacy_workstation(self, test_legacy):
        """Test device type identification."""
        assert test_legacy._device_type() == "legacy_workstation"

    def test_supported_protocols_are_ancient(self, test_legacy):
        """Test that only old vulnerable protocols are supported.

        WHY: It's frozen in 1998.
        """
        protocols = test_legacy._supported_protocols()
        assert "smb1" in protocols  # EternalBlue compatible
        assert "netbios" in protocols
        assert "serial" in protocols
        assert "pcanywhere" in protocols

    def test_hardware_specs_are_1998(self, test_legacy):
        """Test hardware is period-appropriate.

        WHY: Pentium II was hot stuff in 1998.
        """
        assert "Pentium II" in test_legacy.cpu
        assert test_legacy.ram_mb == 128
        assert test_legacy.hdd_gb == 8.4
        assert "CRT" in test_legacy.monitor

    def test_physical_condition_is_poor(self, test_legacy):
        """Test physical condition after 25+ years.

        WHY: Nobody's cleaned it since installation.
        """
        assert test_legacy.dust_level == "extreme"
        assert test_legacy.plastic_yellowing is True
        assert test_legacy.fan_noise == "grinding"
        assert test_legacy.hdd_clicking is True


# ================================================================
# SECURITY VULNERABILITY TESTS
# ================================================================
class TestLegacyWorkstationSecurity:
    """Test the security 'features' (vulnerabilities)."""

    def test_admin_has_no_password(self, test_legacy):
        """Test that admin password is blank.

        WHY: 'It's just a data collection box, who needs security?'
        """
        assert test_legacy.admin_password == ""
        assert test_legacy.auto_login_enabled is True
        assert test_legacy.auto_login_user == "Administrator"

    def test_smb_is_version_1(self, test_legacy):
        """Test SMBv1 is in use.

        WHY: EternalBlue says hello.
        """
        assert test_legacy.smb_version == "SMBv1"
        assert test_legacy.null_sessions_enabled is True

    def test_no_firewall(self, test_legacy):
        """Test firewall is disabled.

        WHY: What's a firewall?
        """
        assert test_legacy.firewall_enabled is False

    def test_dual_homed_network(self, test_legacy):
        """Test machine bridges networks.

        WHY: Perfect pivot point.
        """
        assert "ot_network" in test_legacy.connected_networks
        assert "corporate_network" in test_legacy.connected_networks
        assert len(test_legacy.connected_networks) >= 2

    def test_enumerate_smb_shares_no_auth(self, test_legacy):
        """Test SMB shares are accessible without authentication.

        WHY: Null sessions enabled.
        """
        shares = test_legacy.enumerate_smb_shares()

        assert shares["null_session"] is True
        assert "TURBINE_DATA" in shares["shares"]
        assert shares["shares"]["TURBINE_DATA"]["password_required"] is False

    def test_access_share_without_password(self, test_legacy):
        """Test accessing shares without authentication.

        WHY: Everyone:Full Control
        """
        result = test_legacy.access_share("TURBINE_DATA")

        assert result["success"] is True
        assert "No password required" in result["note"]

    def test_admin_share_accessible(self, test_legacy):
        """Test C$ admin share is accessible.

        WHY: Admin has no password.
        """
        result = test_legacy.access_share("C$")
        assert result["success"] is True

    def test_enumerate_vulnerabilities(self, test_legacy):
        """Test vulnerability enumeration.

        WHY: There are many.
        """
        vulns = test_legacy.enumerate_vulnerabilities()

        vuln_ids = [v["id"] for v in vulns]
        assert "MS17-010" in vuln_ids  # EternalBlue
        assert "MS08-067" in vuln_ids  # Conficker
        assert "NO-PASSWORD" in vuln_ids
        assert "DUAL-HOMED" in vuln_ids

        # All should be exploitable
        for vuln in vulns:
            assert vuln["exploitable"] is True


# ================================================================
# CREDENTIAL HARVESTING TESTS
# ================================================================
class TestLegacyWorkstationCredentials:
    """Test credential discovery."""

    def test_stored_credentials_exist(self, test_legacy):
        """Test that credentials are stored in plaintext.

        WHY: Security wasn't a priority in 1998.
        """
        creds = test_legacy.get_stored_credentials()

        assert "turbine_plc" in creds
        assert creds["turbine_plc"]["plaintext"] is True
        assert creds["turbine_plc"]["password"] == "turbine98"

    def test_post_it_notes_with_passwords(self, test_legacy):
        """Test passwords on sticky notes.

        WHY: Classic.
        """
        creds = test_legacy.get_stored_credentials()

        assert "post_it_note_1" in creds
        assert "keyboard" in creds["post_it_note_2"]["location"].lower()

    def test_vendor_credentials_still_there(self, test_legacy):
        """Test vendor support credentials from 1998.

        WHY: Company is bankrupt, but credentials live on.
        """
        creds = test_legacy.get_stored_credentials()

        assert "vendor_support" in creds
        vendor = creds["vendor_support"]
        assert vendor["username"] == "turbodynamics"
        assert "discontinued" in vendor.get("note", "").lower()


# ================================================================
# ARCHAEOLOGY TESTS
# ================================================================
class TestLegacyWorkstationArchaeology:
    """Test filesystem exploration."""

    def test_explore_filesystem_finds_artifacts(self, test_legacy):
        """Test filesystem exploration finds interesting things.

        WHY: 25 years of accumulated digital artifacts.
        """
        artifacts = test_legacy.explore_filesystem()

        assert len(artifacts) > 0
        assert all(isinstance(a, DiscoveredArtifact) for a in artifacts)

        # Should find config.ini with credentials
        config_artifact = next((a for a in artifacts if "config.ini" in a.name), None)
        assert config_artifact is not None
        assert config_artifact.security_relevant is True

    def test_find_25_years_of_data(self, test_legacy):
        """Test that 25 years of data is available.

        WHY: This is why it can't be retired.
        """
        artifacts = test_legacy.explore_filesystem()

        data_artifact = next(
            (a for a in artifacts if "turbine_log.csv" in a.name), None
        )
        assert data_artifact is not None
        assert data_artifact.contents.get("years") == 25

    def test_find_post_it_notes(self, test_legacy):
        """Test finding post-it notes.

        WHY: Physical security artifacts.
        """
        artifacts = test_legacy.explore_filesystem()

        postit = next((a for a in artifacts if "Post-it" in a.name), None)
        assert postit is not None
        assert postit.security_relevant is True

    def test_floppy_disks_in_drawer(self, test_legacy):
        """Test floppy disk collection.

        WHY: Who knows what's on them?
        """
        assert len(test_legacy.floppy_disks_in_drawer) > 0

        # Some should be readable
        readable = [d for d in test_legacy.floppy_disks_in_drawer if d.get("readable")]
        assert len(readable) > 0

    def test_read_floppy_disk_success(self, test_legacy):
        """Test reading a floppy disk that works."""
        # Find a readable disk
        readable_idx = next(
            i
            for i, d in enumerate(test_legacy.floppy_disks_in_drawer)
            if d.get("readable", False)
        )

        result = test_legacy.read_floppy_disk(readable_idx)
        assert result["success"] is True

    def test_read_floppy_disk_failure(self, test_legacy):
        """Test reading a corrupted floppy disk.

        WHY: They're 25 years old.
        """
        # Find an unreadable disk
        unreadable_idx = next(
            i
            for i, d in enumerate(test_legacy.floppy_disks_in_drawer)
            if not d.get("readable", True)
        )

        result = test_legacy.read_floppy_disk(unreadable_idx)
        assert result["success"] is False
        assert "error" in result


# ================================================================
# DATA COLLECTION TESTS
# ================================================================
class TestLegacyWorkstationDataCollection:
    """Test serial data collection."""

    @pytest.mark.asyncio
    async def test_polls_turbine_via_serial(self, started_legacy):
        """Test data collection from turbine.

        WHY: This is its one job.
        """
        await asyncio.sleep(0.03)

        assert started_legacy.serial_connection_active is True
        assert started_legacy.total_records_collected > 0
        assert len(started_legacy.log_entries) > 0

    @pytest.mark.asyncio
    async def test_log_entries_have_correct_format(
        self, started_legacy, mock_turbine_physics
    ):
        """Test that log entries match turbine data."""
        await asyncio.sleep(0.03)

        assert len(started_legacy.log_entries) > 0
        entry = started_legacy.log_entries[-1]

        assert isinstance(entry, CSVLogEntry)
        assert entry.turbine_speed_rpm == mock_turbine_physics.speed_rpm
        assert entry.power_output_mw == mock_turbine_physics.power_output_mw

    @pytest.mark.asyncio
    async def test_get_historical_data(self, started_legacy):
        """Test historical data retrieval."""
        await asyncio.sleep(0.03)

        data = started_legacy.get_historical_data(hours=24)
        assert len(data) > 0
        assert "speed_rpm" in data[0]

    @pytest.mark.asyncio
    async def test_csv_export_format(self, started_legacy):
        """Test CSV export in legacy format.

        WHY: Maintenance contracts require this exact format.
        """
        await asyncio.sleep(0.03)

        csv = started_legacy.get_csv_export()
        lines = csv.strip().split("\n")

        # Should have header
        assert lines[0].startswith("TIMESTAMP,SPEED_RPM")

        # Should have data
        assert len(lines) > 1


# ================================================================
# UPTIME TESTS
# ================================================================
class TestLegacyWorkstationUptime:
    """Test uptime tracking."""

    def test_uptime_is_very_long(self, test_legacy):
        """Test that uptime is measured in years.

        WHY: It's been running since 2019 (last power outage).
        """
        uptime_days = test_legacy.get_uptime_days()
        assert uptime_days > 1000  # More than 3 years

    def test_total_uptime_since_1998(self, test_legacy):
        """Test total uptime since installation.

        WHY: ~26 years of continuous operation.
        """
        total_days = test_legacy.get_total_uptime_days()
        assert total_days > 9000  # Over 25 years

    def test_boot_count_is_minimal(self, test_legacy):
        """Test that it's only been rebooted a few times.

        WHY: Nobody dares turn it off.
        """
        assert test_legacy.boot_count == 3
        assert test_legacy.last_reboot == "2019-08-15"


# ================================================================
# SYSTEM INFO TESTS
# ================================================================
class TestLegacyWorkstationSystemInfo:
    """Test system information retrieval."""

    def test_get_system_info(self, test_legacy):
        """Test comprehensive system info."""
        info = test_legacy.get_system_info()

        assert info["os"]["version"] == "Windows 98 SE"
        assert info["hardware"]["cpu"] == "Intel Pentium II 350MHz"
        assert info["physical_condition"]["dust_level"] == "extreme"
        assert info["uptime"]["boot_count"] == 3


# ================================================================
# MEMORY MAP TESTS
# ================================================================
class TestLegacyWorkstationMemoryMap:
    """Test memory map (SMB share simulation)."""

    @pytest.mark.asyncio
    async def test_memory_map_initialisation(self, test_legacy):
        """Test memory map structure."""
        await test_legacy._initialise_memory_map()

        assert "computer_name" in test_legacy.memory_map
        assert "turbine_speed_rpm" in test_legacy.memory_map
        assert "smb_shares" in test_legacy.memory_map

    @pytest.mark.asyncio
    async def test_memory_map_updates_with_data(self, started_legacy):
        """Test that memory map reflects collected data."""
        await asyncio.sleep(0.03)

        assert started_legacy.memory_map["serial_connection_active"] is True
        assert started_legacy.memory_map["total_records"] > 0
        assert started_legacy.memory_map["turbine_speed_rpm"] > 0


# ================================================================
# STATUS AND TELEMETRY TESTS
# ================================================================
class TestLegacyWorkstationStatus:
    """Test status and telemetry."""

    @pytest.mark.asyncio
    async def test_get_legacy_status(self, started_legacy):
        """Test legacy status retrieval."""
        await asyncio.sleep(0.02)

        status = await started_legacy.get_legacy_status()

        assert status["os_version"] == "Windows 98 SE"
        assert status["installed_date"] == "1998-01-15"
        assert status["uptime_days"] > 1000
        assert "dust_level" in status["physical_condition"]

    @pytest.mark.asyncio
    async def test_get_telemetry(self, started_legacy):
        """Test telemetry retrieval."""
        telemetry = await started_legacy.get_telemetry()

        assert telemetry["device_type"] == "legacy_workstation"
        assert telemetry["security"]["admin_password_blank"] is True
        assert telemetry["security"]["in_asset_inventory"] is False
        assert telemetry["physical"]["dust_level"] == "extreme"


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestLegacyWorkstationIntegration:
    """Test integration with dependencies."""

    @pytest.mark.asyncio
    async def test_registers_with_datastore(self, test_legacy, datastore_setup):
        """Test that it registers with DataStore."""
        data_store = datastore_setup

        await test_legacy.start()

        devices = await data_store.get_devices_by_type("legacy_workstation")
        assert len(devices) == 1
        assert devices[0].device_name == "forgotten_box"

    @pytest.mark.asyncio
    async def test_complete_lifecycle(self, test_legacy):
        """Test complete lifecycle."""
        await test_legacy.start()
        assert test_legacy.is_online()
        assert test_legacy.is_running()

        await asyncio.sleep(0.03)
        assert test_legacy.total_records_collected > 0

        await test_legacy.stop()
        assert not test_legacy.is_online()

    @pytest.mark.asyncio
    async def test_inherits_from_base_device(self, test_legacy):
        """Test class hierarchy."""
        from components.devices.core.base_device import BaseDevice

        assert isinstance(test_legacy, BaseDevice)


# ================================================================
# DATACLASS TESTS
# ================================================================
class TestCSVLogEntry:
    """Test CSVLogEntry dataclass."""

    def test_csv_log_entry_creation(self):
        """Test creating a log entry."""
        entry = CSVLogEntry(
            timestamp=12345.0,
            turbine_speed_rpm=3600.0,
            power_output_mw=100.0,
            bearing_temp_c=72.0,
            vibration_mm_s=0.8,
            governor_position=0.75,
        )

        assert entry.timestamp == 12345.0
        assert entry.turbine_speed_rpm == 3600.0


class TestDiscoveredArtifact:
    """Test DiscoveredArtifact dataclass."""

    def test_artifact_defaults(self):
        """Test artifact default values."""
        artifact = DiscoveredArtifact(
            artifact_type="file",
            name="test.txt",
            description="A test file",
        )

        assert artifact.security_relevant is False
        assert artifact.contents == {}

    def test_artifact_with_contents(self):
        """Test artifact with contents."""
        artifact = DiscoveredArtifact(
            artifact_type="credential",
            name="passwords.txt",
            description="Passwords in plaintext",
            security_relevant=True,
            contents={"password": "hunter2"},
        )

        assert artifact.security_relevant is True
        assert artifact.contents["password"] == "hunter2"
