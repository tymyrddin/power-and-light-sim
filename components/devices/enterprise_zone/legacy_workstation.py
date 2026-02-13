# components/devices/control_zone/legacy_workstation.py
"""
Legacy Workstation - The Forgotten Box in the Corner.

In almost every OT environment, there's a computer sitting in a corner,
covered in dust, with yellowing plastic and a CRT monitor. Nobody's quite
sure what it does. Nobody dares turn it off. It's been running continuously
since it was installed decades ago.

At UU P&L, there's a Windows 98 machine in the turbine hall running data
collection software from the original turbine vendor. It polls turbine data
via serial connection, logs it to local CSV files, and makes the data
available via a network share.

This machine has been running since 1998. It cannot be upgraded because
the data collection software won't run on newer Windows. It cannot be
retired because maintenance contracts require this specific data format.
It cannot be secured because applying security policies breaks the software.

It sits there, a monument to technical debt, accessible via SMBv1 with no
password, containing 25 years of turbine operational data, and serving as
a potential pivot point into the turbine control network.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from components.devices.core.base_device import BaseDevice
from components.devices.device_filesystem import DeviceFilesystem
from components.security.logging_system import (
    AlarmPriority,
    AlarmState,
    EventSeverity,
)
from components.state.data_store import DataStore


@dataclass
class CSVLogEntry:
    """A single CSV log entry."""

    timestamp: float
    turbine_speed_rpm: float
    power_output_mw: float
    bearing_temp_c: float
    vibration_mm_s: float
    governor_position: float


@dataclass
class DiscoveredArtifact:
    """Something interesting found on the old machine."""

    artifact_type: str  # 'file', 'credential', 'software', 'hardware'
    name: str
    description: str
    security_relevant: bool = False
    contents: dict[str, Any] = field(default_factory=dict)


class LegacyWorkstation(BaseDevice):
    """
    The Forgotten Windows 98 Box in the Turbine Hall.

    A monument to technical debt. Running continuously since 1998.
    Polls turbine data via serial, logs to CSV, shares via SMBv1.

    Security characteristics (all vulnerabilities, no features):
    - Windows 98 SE (never patched, never will be)
    - SMBv1 with null session (no password required)
    - Serial connection to turbine (potential pivot point)
    - 25+ years of operational data (intelligence goldmine)
    - Not in asset inventory (security team doesn't know)
    - IE 5.5 with all historical vulnerabilities
    - No antivirus (Norton 2001 expired in 2002)
    - Admin account with no password
    - Contains vendor credentials from 1998
    - Backup floppies in the drawer (who knows what's on them)
    - Connected to both OT and somehow corporate network
    - Post-it notes with passwords stuck to monitor

    Physical characteristics:
    - Beige/yellowed plastic case
    - CRT monitor (or ancient LCD)
    - Covered in dust
    - Constant HDD activity light
    - Fan making concerning noises
    - Original keyboard with stuck keys

    Example:
        >>> legacy = LegacyWorkstation(
        ...     device_name="forgotten_corner_box",
        ...     device_id=98,  # Windows 98, get it?
        ...     data_store=data_store,
        ...     turbine_physics=turbine_physics,
        ... )
        >>> await legacy.start()
        >>> # It's been running since 1998...
        >>> uptime = legacy.get_uptime_days()  # ~9500 days
        >>> # Explore what's on this thing
        >>> artefacts = legacy.explore_filesystem()
    """

    # Machine was installed January 15, 1998
    INSTALLATION_DATE = "1998-01-15"
    INSTALLATION_TIMESTAMP = 884822400.0  # Unix timestamp

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        turbine_physics: Any | None = None,
        description: str = "Forgotten Windows 98 data collection workstation",
        scan_interval: float = 5.0,  # Polls every 5 seconds (it's old and slow)
        log_dir: Path | None = None,
    ):
        """
        Initialise the forgotten legacy workstation.

        Args:
            device_name: Unique device identifier
            device_id: Numeric ID (suggest 98 for Windows 98)
            data_store: DataStore instance
            turbine_physics: TurbinePhysics instance for serial data
            description: Human-readable description
            scan_interval: Serial polling rate (slow, it's old)
            log_dir: Directory for log files
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
            log_dir=log_dir,
        )

        self.turbine_physics = turbine_physics

        # System information (frozen in time)
        self.os_version = "Windows 98 SE"
        self.os_build = "4.10.2222 A"
        self.installed_date = self.INSTALLATION_DATE
        self.last_patch = "1999-05-05"  # Windows 98 SE release
        self.computer_name = "TURBINE-DATA"
        self.workgroup = "PLANT"

        # Hardware (original 1998 specs)
        self.cpu = "Intel Pentium II 350MHz"
        self.ram_mb = 128
        self.hdd_gb = 8.4  # Quantum Fireball
        self.hdd_free_gb = 0.3  # Almost full after 25 years of logs
        self.serial_ports = ["COM1", "COM2"]  # COM1 connected to turbine
        self.network_card = "3Com EtherLink III"
        self.monitor = 'ViewSonic G773 17" CRT'

        # Physical condition
        self.dust_level = "extreme"  # 'light', 'moderate', 'heavy', 'extreme'
        self.plastic_yellowing = True
        self.fan_noise = "grinding"  # 'quiet', 'loud', 'grinding', 'dying'
        self.hdd_clicking = True  # Bad sectors imminent
        self.crt_burn_in = True  # Ghost of Windows 98 logo

        # Software installed
        self.installed_software = {
            "TurbineLink Pro 2.1": {
                "vendor": "TurboDynamics Inc.",  # Company went bankrupt in 2003
                "installed": "1998-01-15",
                "purpose": "Serial turbine data collection",
                "status": "running",
                "has_source_code": False,
                "installation_media_exists": False,
            },
            "Microsoft Office 97": {
                "vendor": "Microsoft",
                "installed": "1998-01-15",
                "purpose": "Viewing CSV files",
                "status": "installed",
            },
            "Internet Explorer 5.5": {
                "vendor": "Microsoft",
                "installed": "1999-07-01",
                "purpose": "Unknown (probably never used)",
                "status": "installed",
                "vulnerabilities": "all of them",
            },
            "Norton AntiVirus 2001": {
                "vendor": "Symantec",
                "installed": "2001-03-15",
                "purpose": "Antivirus",
                "status": "expired",
                "last_definition_update": "2002-03-15",
            },
            "WinZip 8.0": {
                "vendor": "WinZip Computing",
                "installed": "2000-06-01",
                "purpose": "Compressing old logs",
                "status": "trial expired",
            },
            "pcAnywhere 10.5": {
                "vendor": "Symantec",
                "installed": "2001-09-01",
                "purpose": "Remote access",
                "status": "running",
                "port": 5631,
            },
        }

        # Network configuration (the scary part)
        # Primary NIC: legacy_network (enterprise_zone)
        self.ip_address = "10.40.99.10"  # Static IP since 1998
        # Second NIC: turbine_network (control_zone) - this is the dual-homed bridge
        self.ip_address_ot = "10.10.1.50"  # Plugged in "temporarily" in 2001
        self.subnet_mask = "255.255.255.0"
        self.gateway = "10.40.99.1"
        self.dns_servers = ["10.40.99.1"]  # Probably doesn't resolve anymore
        self.connected_networks = ["legacy_network", "turbine_network"]  # Dual-homed!

        # SMB shares (wide open)
        self.smb_shares = {
            "TURBINE_DATA": {
                "path": "C:\\TURBINE\\DATA",
                "permissions": "Everyone:Full Control",
                "password_required": False,
            },
            "BACKUP": {
                "path": "C:\\BACKUP",
                "permissions": "Everyone:Full Control",
                "password_required": False,
            },
            "C$": {
                "path": "C:\\",
                "permissions": "Admin share",
                "password_required": False,  # Admin has no password
            },
        }

        # Security "features" (all vulnerabilities)
        self.smb_version = "SMBv1"  # EternalBlue compatible
        self.null_sessions_enabled = True
        self.admin_password = ""  # Empty
        self.guest_account_enabled = True
        self.firewall_enabled = False  # What firewall?
        self.auto_login_enabled = True
        self.auto_login_user = "Administrator"
        self.screen_saver_password = False

        # Credentials found on the system
        self.stored_credentials = {
            "turbine_plc": {
                "location": "C:\\TURBINE\\config.ini",
                "username": "engineer",
                "password": "turbine98",
                "plaintext": True,
            },
            "scada_server": {
                "location": "C:\\TURBINE\\scada.cfg",
                "username": "datalink",
                "password": "d@t@1998",
                "plaintext": True,
            },
            "vendor_support": {
                "location": "C:\\TURBINE\\vendor.txt",
                "username": "turbodynamics",
                "password": "support123",
                "note": "Call 1-800-TURBO (discontinued)",
                "plaintext": True,
            },
            "post_it_note_1": {
                "location": "Stuck to monitor",
                "text": "Admin pw: (blank)",
                "plaintext": True,
            },
            "post_it_note_2": {
                "location": "Under keyboard",
                "text": "SCADA: operator/operator",
                "plaintext": True,
            },
        }

        # Archaeological artifacts
        self.floppy_disks_in_drawer = [
            {"label": "TurbineLink Install Disk 1/3", "readable": False},
            {"label": "TurbineLink Install Disk 2/3", "readable": False},
            {"label": "TurbineLink Install Disk 3/3", "readable": True},
            {"label": "BACKUP 03-15-99", "readable": True, "contains": "config files"},
            {"label": "Norton Emergency Disk", "readable": False},
            {"label": "Unlabeled", "readable": True, "contains": "unknown"},
        ]

        # Data collection state
        self.csv_log_path = "C:\\TURBINE\\DATA\\turbine_log.csv"
        self.log_entries: list[CSVLogEntry] = []
        self.total_records_collected = 0
        self.serial_connection_active = False
        self.last_serial_error = ""

        # Uptime (it's been running a LONG time)
        self.boot_count = 3  # Only rebooted twice since 1998 (power outages)
        self.last_reboot = "2019-08-15"  # Brief power outage

        # Alarm state tracking
        self.disk_space_alarm_raised = False
        self.serial_failure_alarm_raised = False
        self.serial_failure_count = 0

        # Simulated filesystem (Windows 98 - case-insensitive)
        self.filesystem = DeviceFilesystem(case_sensitive=False)
        self._populate_filesystem()

        self.logger.info(
            f"LegacyWorkstation '{device_name}' initialised "
            f"(OS={self.os_version}, installed={self.installed_date})"
        )

    # ----------------------------------------------------------------
    # Filesystem population
    # ----------------------------------------------------------------

    def _populate_filesystem(self) -> None:
        """Populate the simulated filesystem with realistic artefacts."""
        fs = self.filesystem

        # TurbineLink configuration - THE credential goldmine
        fs.add_file(
            "C:/TURBINE/config.ini",
            (
                "[TurbineLink]\n"
                "Version=2.1\n"
                "InstallDate=1998-01-15\n"
                "\n"
                "[Serial]\n"
                "Port=COM1\n"
                "Baud=9600\n"
                "DataBits=8\n"
                "StopBits=1\n"
                "Parity=None\n"
                "\n"
                "[Network]\n"
                "; PLC connection for direct setpoint writing\n"
                "PLCAddress=10.10.1.10\n"
                "PLCPort=10502\n"
                "PLCUsername=engineer\n"
                "PLCPassword=turbine98\n"
                "\n"
                "[Registers]\n"
                "; Input registers (read-only telemetry from PLC)\n"
                "IR0=Speed,RPM\n"
                "IR1=Power Output,MW,10\n"
                "IR2=Steam Pressure,PSI\n"
                "IR3=Steam Temp,°C\n"
                "IR4=Bearing Temp,°C\n"
                "IR5=Vibration,mils,10\n"
                "IR6=Overspeed Time,s\n"
                "IR7=Damage Level,%%\n"
                "; Holding registers (writable setpoints)\n"
                "HR0=Speed Setpoint Lo,RPM\n"
                "HR1=Speed Setpoint Hi,RPM\n"
                "; Coils (digital outputs)\n"
                "COIL0=Governor Enable\n"
                "COIL1=Emergency Trip\n"
                "COIL2=Trip Reset\n"
                "; Discrete inputs (read-only status)\n"
                "DI0=Turbine Running\n"
                "DI1=Governor Online\n"
                "DI2=Trip Active\n"
                "DI3=Overspeed\n"
                "DI6=High Vibration\n"
                "DI7=High Bearing Temp\n"
                "\n"
                "[Logging]\n"
                "LogPath=C:\\TURBINE\\DATA\\\n"
                "LogInterval=5\n"
                "MaxLogSize=10000\n"
            ),
            modified="2001-09-15",
            security_relevant=True,
        )

        # SCADA connection config
        fs.add_file(
            "C:/TURBINE/scada.cfg",
            (
                "# SCADA Server Connection\n"
                "# Updated by vendor 1998-03-20\n"
                "SCADA_HOST=10.20.1.10\n"
                "SCADA_PORT=4840\n"
                "SCADA_USER=datalink\n"
                "SCADA_PASS=d@t@1998\n"
                "POLL_INTERVAL=10\n"
                "RETRY_COUNT=3\n"
            ),
            modified="1998-03-20",
            security_relevant=True,
        )

        # Vendor support file
        fs.add_file(
            "C:/TURBINE/vendor.txt",
            (
                "TurboDynamics Inc. Support Contact\n"
                "===================================\n"
                "Phone: 1-800-TURBO (discontinued)\n"
                "Email: support@turbodynamics.com (domain expired 2004)\n"
                "\n"
                "Remote Support Login:\n"
                "  Username: turbodynamics\n"
                "  Password: support123\n"
                "\n"
                "Note: Vendor went bankrupt in 2003.\n"
                "      No more updates available.\n"
                "      DO NOT LOSE THE INSTALL DISKS.\n"
            ),
            modified="1998-01-15",
            security_relevant=True,
        )

        # Vendor manual
        fs.add_file(
            "C:/TURBINE/vendor_manual.pdf",
            "[Binary: TurboDynamics TurbineLink Pro 2.1 Manual - 234 pages - Coffee stains on pages 45-48]",
            modified="1998-01-15",
        )

        # CSV data directory (recent entries populated dynamically)
        fs.add_directory("C:/TURBINE/DATA", modified="2026-02-12")
        fs.add_file(
            "C:/TURBINE/DATA/turbine_log.csv",
            (
                "TIMESTAMP,SPEED_RPM,POWER_MW,BEARING_C,VIB_MMS,GOV_POS\n"
                "# 25 years of continuous logging\n"
                "# Oldest entries on backup tapes\n"
                "# Recent entries in memory\n"
            ),
            modified="2026-02-12",
            metadata={"dynamic": True, "records": "25+ years"},
        )

        # Passwords file - the classic
        fs.add_file(
            "C:/My Documents/passwords.txt",
            (
                "System Passwords - DO NOT DELETE\n"
                "================================\n"
                "Updated: 1999-03-15\n"
                "\n"
                "Windows Admin: (blank)\n"
                "TurbineLink: engineer / turbine98\n"
                "SCADA: datalink / d@t@1998\n"
                "SCADA operator: operator / operator\n"
                "Vendor remote: turbodynamics / support123\n"
                "pcAnywhere: (no password set)\n"
                "\n"
                "Note from Dave (1999):\n"
                "  Don't change these. The software breaks.\n"
            ),
            modified="1999-03-15",
            security_relevant=True,
        )

        # System backup from 1999
        fs.add_file(
            "C:/BACKUP/full_backup_1999.zip",
            "[Binary: WinZip archive - 47MB - Contains full system backup from March 1999]",
            modified="1999-03-15",
            security_relevant=True,
            metadata={"contains": ["configs", "credentials", "TurbineLink install"]},
        )

        # pcAnywhere configuration
        fs.add_file(
            "C:/Program Files/pcAnywhere/hosts.txt",
            (
                "# pcAnywhere Host Connections\n"
                "# Last connection: 2019-03-15 from 10.40.1.20\n"
                "#   (someone from IT tried to check on the machine)\n"
                "\n"
                "HOST=TURBINE-DATA\n"
                "PORT=5631\n"
                "AUTHENTICATION=NONE\n"
                "ENCRYPTION=NONE\n"
            ),
            modified="2019-03-15",
            security_relevant=True,
        )

        # IE cache
        fs.add_file(
            "C:/Windows/Temporary Internet Files/history.dat",
            (
                "1999-06-15 http://www.yahoo.com\n"
                "1999-06-15 http://www.turbodynamics.com/support\n"
                "1999-07-02 http://www.download.com/winzip\n"
                "2000-01-05 http://www.symantec.com/pcanywhere\n"
            ),
            modified="2000-01-05",
        )

        # Network configuration (ipconfig output)
        fs.add_file(
            "C:/Windows/system.ini",
            (
                "[boot]\n"
                "shell=Explorer.exe\n"
                "network.drv=vredir.vxd\n"
                "\n"
                "[Network]\n"
                "ComputerName=TURBINE-DATA\n"
                "Workgroup=PLANT\n"
            ),
            modified="1998-01-15",
        )

        # Network adapter configs showing dual-homed
        fs.add_file(
            "C:/Windows/network.txt",
            (
                "Windows IP Configuration\n"
                "========================\n"
                "\n"
                "Ethernet adapter 1 (3Com EtherLink III):\n"
                f"   IP Address. . . . . . : {self.ip_address}\n"
                f"   Subnet Mask . . . . . : {self.subnet_mask}\n"
                f"   Default Gateway . . . : {self.gateway}\n"
                "   Description . . . . . : Corporate/Legacy network\n"
                "\n"
                "Ethernet adapter 2 (3Com EtherLink III #2):\n"
                f"   IP Address. . . . . . : {self.ip_address_ot}\n"
                "   Subnet Mask . . . . . : 255.255.255.0\n"
                "   Default Gateway . . . : 10.10.1.1\n"
                "   Description . . . . . : Turbine control network\n"
                "   Note: Added 2001-09-15 for 'temporary' direct PLC access\n"
            ),
            modified="2001-09-15",
            security_relevant=True,
        )

        # Autoexec.bat
        fs.add_file(
            "C:/AUTOEXEC.BAT",
            (
                "@echo off\n"
                "SET PATH=C:\\WINDOWS;C:\\TURBINE\n"
                "SET TEMP=C:\\WINDOWS\\TEMP\n"
                'echo "Starting TurbineLink Data Collection..."\n'
                "C:\\TURBINE\\TURBLINK.EXE /AUTO /LOG\n"
            ),
            modified="1998-01-15",
        )

        # Connection log (forensic artefact - updated during simulation)
        fs.add_file(
            "C:/TURBINE/connection.log",
            (
                "TurbineLink Connection Log\n"
                "==========================\n"
                "1998-01-15 14:30 Serial COM1 connected - Turbine online\n"
                "2003-08-14 09:15 Serial COM1 error - Power outage\n"
                "2003-08-14 09:22 Serial COM1 reconnected\n"
                "2019-08-15 16:45 Serial COM1 error - Power outage\n"
                "2019-08-15 17:01 Serial COM1 reconnected\n"
            ),
            modified="2019-08-15",
            metadata={"dynamic": True},
        )

        # SMB access log (forensic artefact - will be appended to)
        fs.add_file(
            "C:/Windows/smblog.txt",
            (
                "SMB Access Log\n"
                "==============\n"
                "2019-03-15 10:23 \\\\TURBINE-DATA\\C$ accessed from 10.40.1.20 (IT check)\n"
            ),
            modified="2019-03-15",
            metadata={"dynamic": True},
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return 'legacy_workstation' as device type."""
        return "legacy_workstation"

    def _supported_protocols(self) -> list[str]:
        """Protocols supported (all old and vulnerable)."""
        return ["smb1", "netbios", "serial", "pcanywhere"]

    async def _initialise_memory_map(self) -> None:
        """
        Initialise memory map.

        Simulates the data available via SMB shares.
        """
        self.memory_map = {
            # System info
            "computer_name": self.computer_name,
            "os_version": self.os_version,
            "ip_address": self.ip_address,
            "uptime_days": self.get_uptime_days(),
            # Current turbine data (from serial)
            "turbine_speed_rpm": 0.0,
            "power_output_mw": 0.0,
            "bearing_temp_c": 0.0,
            "vibration_mm_s": 0.0,
            "governor_position": 0.0,
            # Collection stats
            "serial_connection_active": False,
            "total_records": 0,
            "disk_free_mb": int(self.hdd_free_gb * 1024),
            # Share access (simulated)
            "smb_shares": list(self.smb_shares.keys()),
        }

        self.logger.debug("Memory map initialised (simulating SMB shares)")

    async def _scan_cycle(self) -> None:
        """
        Execute data collection cycle.

        Polls turbine via serial (actually reads from TurbinePhysics),
        logs to CSV, updates memory map for SMB access.
        """
        # Poll turbine data via "serial connection"
        await self._poll_turbine_serial()

        # Update memory map (data available via SMB)
        if self.log_entries:
            latest = self.log_entries[-1]
            self.memory_map["turbine_speed_rpm"] = latest.turbine_speed_rpm
            self.memory_map["power_output_mw"] = latest.power_output_mw
            self.memory_map["bearing_temp_c"] = latest.bearing_temp_c
            self.memory_map["vibration_mm_s"] = latest.vibration_mm_s
            self.memory_map["governor_position"] = latest.governor_position

        self.memory_map["serial_connection_active"] = self.serial_connection_active
        self.memory_map["total_records"] = self.total_records_collected
        self.memory_map["uptime_days"] = self.get_uptime_days()

        # Check alarm conditions
        await self._check_alarm_conditions()

        # Simulate slow disk (occasional delays)
        # The HDD is dying after all...

    async def _poll_turbine_serial(self) -> None:
        """
        Poll turbine data via serial connection.

        Actually reads from TurbinePhysics if available.
        """
        if not self.turbine_physics:
            self.serial_connection_active = False
            self.last_serial_error = "No turbine connected to COM1"
            return

        try:
            # Read turbine state (returns TurbineState object, not dict)
            state = self.turbine_physics.get_state()

            # Create log entry - access TurbineState attributes directly
            # Note: Governor position is a control system parameter, not in TurbineState
            # Estimate from power output (normalized 0-1)
            governor_estimate = (
                min(1.0, state.power_output_mw / 50.0)
                if state.power_output_mw > 0
                else 0.0
            )

            entry = CSVLogEntry(
                timestamp=self.sim_time.now(),
                turbine_speed_rpm=float(state.shaft_speed_rpm),
                power_output_mw=float(state.power_output_mw),
                bearing_temp_c=float(state.bearing_temperature_c),  # Already in Celsius
                vibration_mm_s=float(
                    state.vibration_mils * 0.0254
                ),  # Convert mils to mm/s
                governor_position=float(governor_estimate),
            )

            self.log_entries.append(entry)
            self.total_records_collected += 1
            self.serial_connection_active = True
            self.last_serial_error = ""

            # Keep only last 1000 entries in memory (disk has more)
            if len(self.log_entries) > 1000:
                self.log_entries = self.log_entries[-1000:]

        except Exception as e:
            self.serial_connection_active = False
            self.last_serial_error = str(e)
            self.serial_failure_count += 1
            self.logger.error(f"Serial communication error: {e}")

    # ----------------------------------------------------------------
    # Alarm conditions
    # ----------------------------------------------------------------

    async def _check_alarm_conditions(self) -> None:
        """Check and raise/clear alarms for critical conditions."""
        # Disk space critical alarm (>95% full)
        disk_percent = ((self.hdd_gb - self.hdd_free_gb) / self.hdd_gb) * 100
        if disk_percent > 95.0 and not self.disk_space_alarm_raised:
            await self.logger.log_alarm(
                message=f"Legacy workstation '{self.device_name}': Disk space critical ({disk_percent:.1f}% full)",
                priority=AlarmPriority.HIGH,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={
                    "disk_free_gb": self.hdd_free_gb,
                    "disk_total_gb": self.hdd_gb,
                    "disk_percent_used": disk_percent,
                },
            )
            self.disk_space_alarm_raised = True
        elif disk_percent < 90.0 and self.disk_space_alarm_raised:
            await self.logger.log_alarm(
                message=f"Legacy workstation '{self.device_name}': Disk space recovered",
                priority=AlarmPriority.HIGH,
                state=AlarmState.CLEARED,
                device=self.device_name,
                data={"disk_percent_used": disk_percent},
            )
            self.disk_space_alarm_raised = False

        # Serial connection failure alarm (>5 consecutive failures)
        if self.serial_failure_count > 5 and not self.serial_failure_alarm_raised:
            await self.logger.log_alarm(
                message=f"Legacy workstation '{self.device_name}': Serial connection failed ({self.serial_failure_count} failures)",
                priority=AlarmPriority.MEDIUM,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={
                    "failure_count": self.serial_failure_count,
                    "last_error": self.last_serial_error,
                },
            )
            self.serial_failure_alarm_raised = True
        elif self.serial_connection_active and self.serial_failure_alarm_raised:
            await self.logger.log_alarm(
                message=f"Legacy workstation '{self.device_name}': Serial connection restored",
                priority=AlarmPriority.MEDIUM,
                state=AlarmState.CLEARED,
                device=self.device_name,
                data={"failure_count": self.serial_failure_count},
            )
            self.serial_failure_alarm_raised = False
            self.serial_failure_count = 0

    # ----------------------------------------------------------------
    # Uptime and system info
    # ----------------------------------------------------------------

    def get_uptime_days(self) -> int:
        """
        Get system uptime in days since last reboot.

        The machine has been running since 2019 (last power outage).
        """
        # Last reboot was 2019-08-15 (1565827200.0 Unix timestamp)
        # For fun, let's say it's been running ~1600 days since last reboot
        return 1642  # About 4.5 years since last power outage (2019-08-15 to now)

    def get_total_uptime_days(self) -> int:
        """
        Get total uptime since installation (minus reboots).

        Installed 1998-01-15, only 3 reboots total.
        """
        # ~26 years of operation
        return 9497  # Days since 1998-01-15

    def get_system_info(self) -> dict[str, Any]:
        """Get detailed system information."""
        return {
            "computer_name": self.computer_name,
            "workgroup": self.workgroup,
            "os": {
                "version": self.os_version,
                "build": self.os_build,
                "installed": self.installed_date,
                "last_patch": self.last_patch,
            },
            "hardware": {
                "cpu": self.cpu,
                "ram_mb": self.ram_mb,
                "hdd_gb": self.hdd_gb,
                "hdd_free_gb": self.hdd_free_gb,
                "serial_ports": self.serial_ports,
                "network_card": self.network_card,
                "monitor": self.monitor,
            },
            "physical_condition": {
                "dust_level": self.dust_level,
                "plastic_yellowing": self.plastic_yellowing,
                "fan_noise": self.fan_noise,
                "hdd_clicking": self.hdd_clicking,
                "crt_burn_in": self.crt_burn_in,
            },
            "uptime": {
                "current_days": self.get_uptime_days(),
                "total_days": self.get_total_uptime_days(),
                "boot_count": self.boot_count,
                "last_reboot": self.last_reboot,
            },
        }

    # ----------------------------------------------------------------
    # Security vulnerabilities (for red team fun)
    # ----------------------------------------------------------------

    def enumerate_smb_shares(self) -> dict[str, Any]:
        """
        Enumerate SMB shares (null session).

        No authentication required. Returns all shares.
        """
        return {
            "host": self.ip_address,
            "smb_version": self.smb_version,
            "null_session": self.null_sessions_enabled,
            "shares": self.smb_shares,
        }

    async def access_share(
        self, share_name: str, username: str = "", password: str = ""
    ) -> dict[str, Any]:
        """
        Access an SMB share.

        Authentication is optional (and ignored).
        """
        if share_name not in self.smb_shares:
            return {"success": False, "error": "Share not found"}

        share = self.smb_shares[share_name]

        # Log the access as security event
        await self.logger.log_security(
            message=f"SMB share access: {username or 'anonymous'} accessed \\\\{self.computer_name}\\{share_name}",
            severity=EventSeverity.WARNING,
            data={
                "share": share_name,
                "username": username or "anonymous",
                "path": share["path"],
                "authentication_required": False,
            },
        )

        # Forensic artefact: append to SMB access log
        from components.time.simulation_time import SimulationTime
        sim_time = SimulationTime()
        self.filesystem.append_to_file(
            "C:/Windows/smblog.txt",
            f"{sim_time.now():.0f} \\\\{self.computer_name}\\{share_name} "
            f"accessed by {username or 'anonymous'}\n",
        )

        return {
            "success": True,
            "share": share_name,
            "path": share["path"],
            "permissions": share["permissions"],
            "note": "No password required",
        }

    async def get_stored_credentials(self, user: str = "unknown") -> dict[str, Any]:
        """
        Extract stored credentials from the system.

        Simulates credential harvesting from config files and post-its.
        """
        await self.logger.log_security(
            message=f"Credential extraction from legacy workstation '{self.device_name}'",
            severity=EventSeverity.CRITICAL,
            data={
                "device": self.device_name,
                "user": user,
                "credentials_exposed": len(self.stored_credentials),
                "credential_locations": list(self.stored_credentials.keys()),
            },
        )
        return self.stored_credentials

    def enumerate_vulnerabilities(self) -> list[dict[str, Any]]:
        """
        Enumerate known vulnerabilities.

        Returns a list of CVEs and security issues.
        """
        return [
            {
                "id": "MS17-010",
                "name": "EternalBlue",
                "description": "SMBv1 remote code execution",
                "severity": "critical",
                "exploitable": True,
                "note": "Machine is running SMBv1 with no patches",
            },
            {
                "id": "MS08-067",
                "name": "Conficker",
                "description": "Server Service remote code execution",
                "severity": "critical",
                "exploitable": True,
            },
            {
                "id": "CVE-1999-0519",
                "name": "Null Session",
                "description": "Anonymous SMB access",
                "severity": "high",
                "exploitable": True,
            },
            {
                "id": "NO-PASSWORD",
                "name": "Empty Admin Password",
                "description": "Administrator account has no password",
                "severity": "critical",
                "exploitable": True,
            },
            {
                "id": "DUAL-HOMED",
                "name": "Network Bridge",
                "description": "Connected to both OT and corporate networks",
                "severity": "high",
                "exploitable": True,
                "note": "Pivot point between networks",
            },
            {
                "id": "PCANYWHERE",
                "name": "pcAnywhere Exposed",
                "description": "Remote access software on port 5631",
                "severity": "high",
                "exploitable": True,
            },
            {
                "id": "ANCIENT-IE",
                "name": "Internet Explorer 5.5",
                "description": "Browser with hundreds of unpatched vulnerabilities",
                "severity": "critical",
                "exploitable": True,
            },
        ]

    # ----------------------------------------------------------------
    # Archaeology - exploring the forgotten machine
    # ----------------------------------------------------------------

    async def explore_filesystem(
        self, user: str = "unknown"
    ) -> list[DiscoveredArtifact]:
        """
        Explore the filesystem for interesting artifacts.

        Like digital archaeology on a machine frozen in 1998.
        """
        # Log filesystem exploration as audit event
        await self.logger.log_audit(
            message=f"Filesystem exploration on legacy workstation '{self.device_name}'",
            user=user,
            action="filesystem_exploration",
            data={"device": self.device_name},
        )

        artifacts = [
            DiscoveredArtifact(
                artifact_type="file",
                name="C:\\TURBINE\\config.ini",
                description="TurbineLink configuration with PLC credentials",
                security_relevant=True,
                contents={"plc_password": "turbine98"},
            ),
            DiscoveredArtifact(
                artifact_type="file",
                name="C:\\TURBINE\\DATA\\turbine_log.csv",
                description="25 years of turbine operational data",
                security_relevant=True,
                contents={"records": self.total_records_collected, "years": 25},
            ),
            DiscoveredArtifact(
                artifact_type="file",
                name="C:\\BACKUP\\full_backup_1999.zip",
                description="System backup from 1999",
                security_relevant=True,
                contents={"includes": ["configs", "credentials", "source"]},
            ),
            DiscoveredArtifact(
                artifact_type="file",
                name="C:\\Windows\\Temporary Internet Files\\",
                description="IE cache from 1999-2000",
                security_relevant=False,
                contents={"note": "Someone browsed yahoo.com"},
            ),
            DiscoveredArtifact(
                artifact_type="file",
                name="C:\\My Documents\\passwords.txt",
                description="Text file with passwords",
                security_relevant=True,
                contents={"note": "List of all system passwords"},
            ),
            DiscoveredArtifact(
                artifact_type="software",
                name="TurbineLink Pro 2.1",
                description="Critical data collection software - no install media",
                security_relevant=True,
                contents={"vendor_status": "bankrupt", "source_code": "lost"},
            ),
            DiscoveredArtifact(
                artifact_type="hardware",
                name="Floppy Drive A:",
                description='3.5" floppy drive, still functional',
                security_relevant=False,
                contents={"floppies_in_drawer": len(self.floppy_disks_in_drawer)},
            ),
            DiscoveredArtifact(
                artifact_type="credential",
                name="Post-it notes",
                description="Passwords written on sticky notes",
                security_relevant=True,
                contents={
                    "on_monitor": "Admin pw: (blank)",
                    "under_keyboard": "SCADA: operator/operator",
                },
            ),
            DiscoveredArtifact(
                artifact_type="file",
                name="C:\\TURBINE\\vendor_manual.pdf",
                description="TurboDynamics TurbineLink manual (only copy)",
                security_relevant=False,
                contents={"pages": 234, "note": "Coffee stains on pages 45-48"},
            ),
            DiscoveredArtifact(
                artifact_type="file",
                name="C:\\Program Files\\pcAnywhere\\hosts.txt",
                description="pcAnywhere connection history",
                security_relevant=True,
                contents={"last_connection": "2019-03-15", "from": "10.0.0.50"},
            ),
        ]

        self.logger.info(f"Filesystem exploration found {len(artifacts)} artifacts")
        return artifacts

    async def read_floppy_disk(
        self, disk_index: int, user: str = "unknown"
    ) -> dict[str, Any]:
        """
        Attempt to read a floppy disk from the drawer.

        Some are corrupted, some contain treasures.
        """
        if disk_index < 0 or disk_index >= len(self.floppy_disks_in_drawer):
            return {"success": False, "error": "Invalid disk index"}

        disk = self.floppy_disks_in_drawer[disk_index]

        if not disk.get("readable", False):
            self.logger.warning(f"Floppy disk read failed: {disk['label']}")
            return {
                "success": False,
                "label": disk["label"],
                "error": "Disk read error - bad sectors",
            }

        # Log floppy disk access as audit event
        await self.logger.log_audit(
            message=f"Floppy disk read from legacy workstation '{self.device_name}': {disk['label']}",
            user=user,
            action="floppy_disk_read",
            data={
                "disk_index": disk_index,
                "label": disk["label"],
                "contents": disk.get("contains", "unknown data"),
            },
        )

        self.logger.info(f"Floppy disk read: {disk['label']}")
        return {
            "success": True,
            "label": disk["label"],
            "contents": disk.get("contains", "unknown data"),
        }

    # ----------------------------------------------------------------
    # Data access (what makes this machine "critical")
    # ----------------------------------------------------------------

    def get_historical_data(self, hours: int = 24) -> list[dict[str, Any]]:
        """
        Get historical turbine data from CSV logs.

        This is why the machine can't be retired.
        """
        # Return recent entries from memory
        return [
            {
                "timestamp": entry.timestamp,
                "speed_rpm": entry.turbine_speed_rpm,
                "power_mw": entry.power_output_mw,
                "bearing_temp_c": entry.bearing_temp_c,
                "vibration_mm_s": entry.vibration_mm_s,
                "governor": entry.governor_position,
            }
            for entry in self.log_entries[-100:]  # Last 100 entries
        ]

    def get_csv_export(self) -> str:
        """
        Export data in the exact CSV format required by maintenance contracts.

        This specific format is why the machine can't be replaced.
        """
        header = "TIMESTAMP,SPEED_RPM,POWER_MW,BEARING_C,VIB_MMS,GOV_POS\n"
        lines = [header]

        for entry in self.log_entries[-50:]:
            lines.append(
                f"{entry.timestamp:.2f},{entry.turbine_speed_rpm:.1f},"
                f"{entry.power_output_mw:.2f},{entry.bearing_temp_c:.1f},"
                f"{entry.vibration_mm_s:.2f},{entry.governor_position:.3f}\n"
            )

        return "".join(lines)

    # ----------------------------------------------------------------
    # Status and telemetry
    # ----------------------------------------------------------------

    async def get_legacy_status(self) -> dict[str, Any]:
        """Get legacy workstation status."""
        base_status = await self.get_status()
        legacy_status = {
            **base_status,
            "os_version": self.os_version,
            "installed_date": self.installed_date,
            "uptime_days": self.get_uptime_days(),
            "total_uptime_days": self.get_total_uptime_days(),
            "serial_connection": self.serial_connection_active,
            "total_records": self.total_records_collected,
            "disk_free_gb": self.hdd_free_gb,
            "physical_condition": {
                "dust_level": self.dust_level,
                "fan_noise": self.fan_noise,
                "hdd_clicking": self.hdd_clicking,
            },
        }
        return legacy_status

    async def get_telemetry(self) -> dict[str, Any]:
        """Get legacy workstation telemetry."""
        return {
            "device_name": self.device_name,
            "device_type": "legacy_workstation",
            "system": {
                "os": self.os_version,
                "installed": self.installed_date,
                "last_patch": self.last_patch,
                "uptime_days": self.get_uptime_days(),
            },
            "data_collection": {
                "serial_active": self.serial_connection_active,
                "total_records": self.total_records_collected,
                "csv_path": self.csv_log_path,
            },
            "network": {
                "ip": self.ip_address,
                "smb_shares": list(self.smb_shares.keys()),
                "dual_homed": len(self.connected_networks) > 1,
            },
            "security": {
                "vulnerabilities": len(self.enumerate_vulnerabilities()),
                "smb_version": self.smb_version,
                "admin_password_blank": self.admin_password == "",
                "antivirus_status": "expired",
                "in_asset_inventory": False,
            },
            "physical": {
                "dust_level": self.dust_level,
                "fan_status": self.fan_noise,
                "hdd_health": "failing" if self.hdd_clicking else "unknown",
            },
        }
