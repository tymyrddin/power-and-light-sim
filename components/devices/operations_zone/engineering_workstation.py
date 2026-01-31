# components/devices/engineering_workstation.py
"""
Engineering Workstation device class.

The keys to the kingdom. Used for programming PLCs, configuring SCADA,
and maintaining ICS infrastructure. Typically runs vendor-specific software
and has access to both corporate and OT networks.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime

logger = logging.getLogger(__name__)


@dataclass
class ProjectFile:
    """Engineering project file."""

    project_name: str
    device_name: str
    file_type: str  # 'plc_program', 'scada_config', 'hmi_project'
    contains_credentials: bool = False
    last_modified: datetime = field(default_factory=datetime.now)
    file_path: str = ""


class EngineeringWorkstation:
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
        >>> await eng_ws.initialise()
    """

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        os_version: str = "Windows 7",
        patched: bool = False,
        laptop: bool = True,
    ):
        self.device_name = device_name
        self.data_store = data_store
        self.sim_time = SimulationTime()

        self.os_version = os_version
        self.patched = patched
        self.laptop = laptop

        self.projects: list[ProjectFile] = []

        self.engineering_software = {
            "TIA Portal V15": "Siemens PLC programming",
            "RSLogix 5000 v20.01": "Allen-Bradley PLC programming",
            "RSLinx Classic": "Rockwell communication driver",
            "Wonderware InTouch 2014": "HMI development",
            "System Platform 2017": "SCADA configuration",
        }

        self.connected_networks = ["corporate", "ot", "vendor_vpn"]
        self.wifi_enabled = True
        self.bridges_networks = True

        self.has_antivirus = False
        self.admin_privileges = True
        self.rdp_enabled = True
        self.vnc_enabled = True
        self.shared_account = True
        self.account_name = "engineer"
        self.account_password = "Engineer123"
        self.usb_ports_enabled = True
        self.password_on_sticky_note = True

        self.vendor_vpn_clients = [
            "Siemens TeleService",
            "Rockwell FactoryTalk VantagePoint",
        ]

        self._running = False
        self.current_user = ""

        logger.info(
            f"EngineeringWorkstation created: {device_name}, "
            f"OS={os_version}, patched={patched}, laptop={laptop}"
        )

    async def initialise(self) -> None:
        await self.data_store.register_device(
            device_name=self.device_name,
            device_type="engineering_workstation",
            device_id=hash(self.device_name) % 1000,
            protocols=["rdp", "vnc", "ssh", "vendor_proprietary"],
            metadata={
                "os_version": self.os_version,
                "patched": self.patched,
                "laptop": self.laptop,
                "vulnerabilities": "many" if not self.patched else "some",
            },
        )
        await self._sync_to_datastore()
        logger.info(f"EngineeringWorkstation initialised: {self.device_name}")

    def add_project(
        self,
        project_name: str,
        device_name: str,
        file_type: str,
        has_credentials: bool = True,
        file_path: str = "",
    ) -> None:
        if not file_path:
            file_path = f"C:\\Projects\\{project_name}.{file_type}"

        self.projects.append(
            ProjectFile(
                project_name=project_name,
                device_name=device_name,
                file_type=file_type,
                contains_credentials=has_credentials,
                file_path=file_path,
            )
        )
        logger.info(f"Project added: {project_name} for {device_name}")

    def get_project_credentials(self, project_name: str) -> dict[str, str] | None:
        for project in self.projects:
            if project.project_name == project_name and project.contains_credentials:
                return {
                    "device": project.device_name,
                    "plc_password": "plc123",
                    "program_protection": "",
                    "upload_password": "upload",
                    "scada_db_password": "scada2015",
                }
        return None

    async def program_plc(self, plc_name: str, program_data: dict[str, Any]) -> bool:
        logger.warning(
            f"PLC PROGRAMMING: {self.current_user or 'unknown'} @ "
            f"{self.device_name} programming {plc_name}"
        )
        await self.data_store.update_metadata(
            plc_name,
            {
                "last_programmed_by": self.device_name,
                "last_program_time": self.sim_time.now(),
            },
        )
        return True

    def login(self, username: str, password: str = "") -> bool:
        if username == self.account_name:
            self.current_user = username
            logger.info(f"User logged in to {self.device_name}: {username}")
            return True
        return False

    async def _sync_to_datastore(self) -> None:
        memory_map = {
            "os_version": self.os_version,
            "patched": self.patched,
            "current_user": self.current_user,
            "connected_networks": self.connected_networks,
        }
        await self.data_store.bulk_write_memory(self.device_name, memory_map)

    async def get_telemetry(self) -> dict[str, Any]:
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
                "bridges_networks": self.bridges_networks,
            },
        }
