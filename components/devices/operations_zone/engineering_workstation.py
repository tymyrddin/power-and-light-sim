# components/devices/operations_zone/engineering_workstation.py
"""
Engineering Workstation device class.

The keys to the kingdom. Used for programming PLCs, configuring SCADA,
and maintaining ICS infrastructure. Typically runs vendor-specific software
and has access to both corporate and OT networks.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from components.devices.core.base_device import BaseDevice
from components.security.logging_system import (
    AlarmPriority,
    AlarmState,
    EventSeverity,
)
from components.state.data_store import DataStore


@dataclass
class ProjectFile:
    """Engineering project file."""

    project_name: str
    device_name: str
    file_type: str  # 'plc_program', 'scada_config', 'hmi_project'
    contains_credentials: bool = False
    last_modified: float = 0.0  # Simulation time when last modified
    file_path: str = ""


class EngineeringWorkstation(BaseDevice):
    """
    Engineering workstation for programming and configuration.

    Critical security target because it can:
    - Program PLCs (upload malicious logic)
    - Configure SCADA systems
    - Access stored credentials
    - Bridge corporate and OT networks

    Realistic security characteristics:
    - Outdated OS (Windows 7, XP common)
    - Not patched (vendor software compatibility)
    - Admin privileges required
    - Shared accounts
    - RDP/VNC enabled
    - Contains project files with credentials

    Example:
        >>> eng_ws = EngineeringWorkstation(
        ...     device_name="engineering_laptop_1",
        ...     device_id=1,
        ...     data_store=data_store,
        ...     os_version="Windows 7",
        ...     patched=False
        ... )
        >>> eng_ws.add_project(
        ...     "turbine_control_v3",
        ...     "turbine_plc_1",
        ...     "plc_program",
        ...     has_credentials=True
        ... )
        >>> await eng_ws.start()
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        os_version: str = "Windows 7",
        patched: bool = False,
        laptop: bool = True,
        description: str = "",
        scan_interval: float = 1.0,  # Engineering workstations don't need fast scan
        log_dir: Path | None = None,
    ):
        """
        Initialise engineering workstation.

        Args:
            device_name: Unique device identifier
            device_id: Numeric ID for protocol addressing
            data_store: DataStore instance
            os_version: Operating system version
            patched: Whether OS is patched
            laptop: Whether this is a laptop (portable)
            description: Human-readable description
            scan_interval: State sync interval in seconds
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

        # System configuration
        self.os_version = os_version
        self.patched = patched
        self.laptop = laptop

        # Project files
        self.projects: list[ProjectFile] = []

        # Installed engineering software
        self.engineering_software: dict[str, str] = {
            "TIA Portal V15": "Siemens PLC programming",
            "RSLogix 5000 v20.01": "Allen-Bradley PLC programming",
            "RSLinx Classic": "Rockwell communication driver",
            "Wonderware InTouch 2014": "HMI development",
            "System Platform 2017": "SCADA configuration",
        }

        # Network configuration (security concern: bridges networks)
        self.connected_networks: list[str] = ["corporate", "ot", "vendor_vpn"]
        self.wifi_enabled: bool = True
        self.bridges_networks: bool = True

        # Security characteristics (realistic weaknesses)
        self.has_antivirus: bool = False
        self.admin_privileges: bool = True
        self.rdp_enabled: bool = True
        self.vnc_enabled: bool = True
        self.shared_account: bool = True
        self.account_name: str = "engineer"
        self.account_password: str = "Engineer123"
        self.usb_ports_enabled: bool = True
        self.password_on_sticky_note: bool = True

        # Vendor VPN clients
        self.vendor_vpn_clients: list[str] = [
            "Siemens TeleService",
            "Rockwell FactoryTalk VantagePoint",
        ]

        # User session
        self.current_user: str = ""
        self.login_time: float = 0.0

        self.logger.info(
            f"EngineeringWorkstation '{device_name}' initialised "
            f"(OS={os_version}, patched={patched}, laptop={laptop})"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return 'engineering_workstation' as device type."""
        return "engineering_workstation"

    def _supported_protocols(self) -> list[str]:
        """Engineering workstations support various remote access protocols."""
        return ["rdp", "vnc", "ssh", "vendor_proprietary"]

    async def _initialise_memory_map(self) -> None:
        """
        Initialise engineering workstation memory map.

        Memory map structure:
        - System configuration
        - User session state
        - Project information
        """
        self.memory_map = {
            # System info
            "os_version": self.os_version,
            "patched": self.patched,
            "laptop": self.laptop,
            # User session
            "current_user": self.current_user,
            "login_time": self.login_time,
            # Network
            "connected_networks": self.connected_networks.copy(),
            "bridges_networks": self.bridges_networks,
            # Projects
            "project_count": len(self.projects),
            "projects": [p.project_name for p in self.projects],
            # Security state
            "has_antivirus": self.has_antivirus,
            "admin_privileges": self.admin_privileges,
        }

        self.logger.debug(f"Memory map initialised with {len(self.projects)} projects")

    async def _scan_cycle(self) -> None:
        """
        Execute engineering workstation scan cycle.

        Engineering workstations don't poll devices like SCADA/HMI.
        The scan cycle just syncs current state to memory map.
        """
        # Update memory map with current state
        self.memory_map["current_user"] = self.current_user
        self.memory_map["login_time"] = self.login_time
        self.memory_map["project_count"] = len(self.projects)
        self.memory_map["projects"] = [p.project_name for p in self.projects]
        self.memory_map["connected_networks"] = self.connected_networks.copy()

    # ----------------------------------------------------------------
    # Project management
    # ----------------------------------------------------------------

    async def add_project(
        self,
        project_name: str,
        device_name: str,
        file_type: str,
        has_credentials: bool = True,
        file_path: str = "",
        user: str = "unknown",
    ) -> None:
        """
        Add a project file to the workstation.

        Args:
            project_name: Project identifier
            device_name: Target device for this project
            file_type: Type of project ('plc_program', 'scada_config', 'hmi_project')
            has_credentials: Whether project contains stored credentials
            file_path: Path to project file
            user: User adding the project
        """
        if not file_path:
            file_path = f"C:\\Projects\\{project_name}.{file_type}"

        self.projects.append(
            ProjectFile(
                project_name=project_name,
                device_name=device_name,
                file_type=file_type,
                contains_credentials=has_credentials,
                last_modified=self.sim_time.now(),
                file_path=file_path,
            )
        )

        # Log project creation as audit event
        await self.logger.log_audit(
            message=f"Project created on engineering workstation '{self.device_name}': {project_name}",
            user=user,
            action="project_create",
            data={
                "project_name": project_name,
                "device_name": device_name,
                "file_type": file_type,
                "contains_credentials": has_credentials,
                "file_path": file_path,
            },
        )

        self.logger.info(f"Project added: {project_name} for {device_name}")

    def get_project(self, project_name: str) -> ProjectFile | None:
        """
        Get a project by name.

        Args:
            project_name: Name of project to find

        Returns:
            ProjectFile if found, None otherwise
        """
        for project in self.projects:
            if project.project_name == project_name:
                return project
        return None

    async def get_project_credentials(
        self, project_name: str, user: str = "unknown"
    ) -> dict[str, str] | None:
        """
        Get stored credentials from a project file.

        Simulates common vulnerability: credentials stored in project files.

        Args:
            project_name: Name of project
            user: User extracting credentials

        Returns:
            Dictionary of credentials if available, None otherwise
        """
        for project in self.projects:
            if project.project_name == project_name and project.contains_credentials:
                # Log credential extraction as CRITICAL security event
                await self.logger.log_security(
                    message=f"Credential extraction from engineering workstation '{self.device_name}': {project_name}",
                    severity=EventSeverity.CRITICAL,
                    data={
                        "device": self.device_name,
                        "project_name": project_name,
                        "target_device": project.device_name,
                        "user": user,
                        "file_path": project.file_path,
                    },
                )

                return {
                    "device": project.device_name,
                    "plc_password": "plc123",
                    "program_protection": "",
                    "upload_password": "upload",
                    "scada_db_password": "scada2015",
                }
        return None

    # ----------------------------------------------------------------
    # PLC programming
    # ----------------------------------------------------------------

    async def program_plc(self, plc_name: str, program_data: dict[str, Any]) -> bool:
        """
        Program a PLC with new logic.

        This is a critical operation - logs as audit event.

        Args:
            plc_name: Target PLC device name
            program_data: Program data to upload

        Returns:
            True if programming successful
        """
        if not self.current_user:
            self.logger.warning(
                f"PLC programming rejected: No user logged in on {self.device_name}"
            )
            return False

        # Log PLC programming as CRITICAL audit event
        await self.logger.log_audit(
            message=f"PLC PROGRAMMING: {self.current_user} programming {plc_name} from '{self.device_name}'",
            user=self.current_user,
            action="plc_program",
            data={
                "source_workstation": self.device_name,
                "target_plc": plc_name,
                "program_size_bytes": len(str(program_data)),
                "timestamp": self.sim_time.now(),
            },
        )

        self.logger.warning(
            f"PLC PROGRAMMING: {self.current_user} @ "
            f"{self.device_name} programming {plc_name}"
        )

        await self.data_store.update_metadata(
            plc_name,
            {
                "last_programmed_by": self.device_name,
                "last_programmed_user": self.current_user,
                "last_program_time": self.sim_time.now(),
            },
        )
        return True

    # ----------------------------------------------------------------
    # User session
    # ----------------------------------------------------------------

    async def login(self, username: str, password: str = "") -> bool:
        """
        Simulate user login.

        Args:
            username: Username to login
            password: Password (often ignored in shared account scenarios)

        Returns:
            True if login successful
        """
        # Realistic: shared accounts with weak/no password enforcement
        if username == self.account_name:
            self.current_user = username
            self.login_time = self.sim_time.now()

            # Log login as audit event
            await self.logger.log_audit(
                message=f"User login to engineering workstation '{self.device_name}': {username}",
                user=username,
                action="login",
                data={
                    "device": self.device_name,
                    "login_time": self.login_time,
                    "shared_account": self.shared_account,
                },
            )

            self.logger.info(f"User logged in to {self.device_name}: {username}")
            return True
        return False

    async def logout(self) -> None:
        """Logout current user."""
        if self.current_user:
            # Log logout as audit event
            await self.logger.log_audit(
                message=f"User logout from engineering workstation '{self.device_name}': {self.current_user}",
                user=self.current_user,
                action="logout",
                data={
                    "device": self.device_name,
                    "session_duration_s": self.sim_time.now() - self.login_time,
                },
            )

            self.logger.info(
                f"User logged out from {self.device_name}: {self.current_user}"
            )
            self.current_user = ""
            self.login_time = 0.0

    # ----------------------------------------------------------------
    # Status and telemetry
    # ----------------------------------------------------------------

    async def get_engineering_status(self) -> dict[str, Any]:
        """Get engineering workstation status."""
        base_status = await self.get_status()
        eng_status = {
            **base_status,
            "os_version": self.os_version,
            "patched": self.patched,
            "laptop": self.laptop,
            "current_user": self.current_user,
            "project_count": len(self.projects),
            "connected_networks": self.connected_networks,
            "bridges_networks": self.bridges_networks,
        }
        return eng_status

    async def get_telemetry(self) -> dict[str, Any]:
        """Get engineering workstation telemetry."""
        return {
            "device_name": self.device_name,
            "device_type": "engineering_workstation",
            "os_version": self.os_version,
            "patched": self.patched,
            "laptop": self.laptop,
            "current_user": self.current_user,
            "projects": len(self.projects),
            "security": {
                "has_antivirus": self.has_antivirus,
                "admin_privileges": self.admin_privileges,
                "rdp_enabled": self.rdp_enabled,
                "vnc_enabled": self.vnc_enabled,
                "bridges_networks": self.bridges_networks,
                "usb_ports_enabled": self.usb_ports_enabled,
                "shared_account": self.shared_account,
            },
        }
