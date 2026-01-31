# components/devices/hmi_workstation.py
"""
HMI (Human-Machine Interface) Workstation device class.

Operator interface for monitoring and controlling the industrial process.
Typically runs software like Wonderware InTouch, FactoryTalk View, or Ignition.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime

logger = logging.getLogger(__name__)


@dataclass
class HMIScreen:
    """HMI display screen configuration."""

    screen_name: str
    tags_displayed: list[str] = field(default_factory=list)
    controls_available: list[str] = field(default_factory=list)


class HMIWorkstation:
    """
    Human-Machine Interface workstation.

    Operator interface for monitoring and controlling the process.
    Connects to SCADA server to read tag values and send commands.

    Security characteristics (realistic):
    - Runs on Windows (often outdated versions)
    - Web interface with weak/default credentials
    - Accessible from corporate network
    - Stores credentials in config files
    - RDP/VNC enabled

    Example:
        >>> hmi = HMIWorkstation(
        ...     device_name="hmi_operator_1",
        ...     data_store=data_store,
        ...     scada_server="scada_master_1"
        ... )
        >>> hmi.add_screen(
        ...     "turbine_overview",
        ...     tags=["TURB1_SPEED", "TURB1_POWER"],
        ...     controls=["TURB1_SPEED_SETPOINT", "TURB1_START_STOP"]
        ... )
        >>> await hmi.initialise()
        >>> hmi.login_operator("operator1")
    """

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        scada_server: str = "scada_master_1",
        os_version: str = "Windows 10",
        hmi_software: str = "Wonderware InTouch 2014",
    ):
        """
        Initialise HMI workstation.

        Args:
            device_name: Unique device identifier
            data_store: DataStore instance
            scada_server: SCADA server to connect to
            os_version: Operating system version
            hmi_software: HMI software package
        """
        self.device_name = device_name
        self.data_store = data_store
        self.sim_time = SimulationTime()

        # Configuration
        self.scada_server = scada_server
        self.os_version = os_version
        self.hmi_software = hmi_software

        # HMI screens
        self.screens: dict[str, HMIScreen] = {}
        self.current_screen = None

        # Operator session
        self.operator_logged_in = False
        self.operator_name = ""
        self.login_time = 0.0

        # Security characteristics (realistic weaknesses)
        self.web_interface_enabled = True
        self.web_interface_port = 8080
        self.web_default_credentials = ("admin", "admin")  # Common vulnerability
        self.rdp_enabled = True
        self.config_file_path = "C:\\InTouch\\config.xml"  # Contains credentials
        self.credentials_plaintext = True  # Common issue

        # Runtime state
        self._running = False

        logger.info(
            f"HMIWorkstation created: {device_name}, "
            f"OS={os_version}, software={hmi_software}"
        )

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialise HMI workstation and register with DataStore."""
        await self.data_store.register_device(
            device_name=self.device_name,
            device_type="hmi_workstation",
            device_id=hash(self.device_name) % 1000,
            protocols=["http", "rdp", "vnc"],
            metadata={
                "scada_server": self.scada_server,
                "os_version": self.os_version,
                "hmi_software": self.hmi_software,
                "web_interface_port": self.web_interface_port,
                "screens": len(self.screens),
            },
        )

        await self._sync_to_datastore()

        logger.info(f"HMIWorkstation initialised: {self.device_name}")

    # ----------------------------------------------------------------
    # Screen configuration
    # ----------------------------------------------------------------

    def add_screen(
        self, screen_name: str, tags: list[str], controls: list[str]
    ) -> None:
        """
        Add HMI screen definition.

        Args:
            screen_name: Screen identifier
            tags: List of SCADA tags displayed on this screen
            controls: List of control elements available
        """
        self.screens[screen_name] = HMIScreen(
            screen_name=screen_name,
            tags_displayed=tags,
            controls_available=controls,
        )

        logger.debug(
            f"HMI screen added: {screen_name}, "
            f"{len(tags)} tags, {len(controls)} controls"
        )

    def navigate_to_screen(self, screen_name: str) -> bool:
        """Navigate to a specific screen."""
        if screen_name in self.screens:
            self.current_screen = screen_name
            logger.debug(f"HMI navigated to screen: {screen_name}")
            return True
        return False

    # ----------------------------------------------------------------
    # Operator interaction
    # ----------------------------------------------------------------

    def login_operator(self, operator_name: str, password: str = "") -> bool:
        """
        Simulate operator login.

        Args:
            operator_name: Operator username
            password: Password (often not required in older HMIs)

        Returns:
            True if login successful
        """
        # Realistic: many HMIs have weak or no authentication
        self.operator_logged_in = True
        self.operator_name = operator_name
        self.login_time = self.sim_time.now()

        logger.info(f"Operator logged in to {self.device_name}: {operator_name}")
        return True

    def logout_operator(self) -> None:
        """Logout current operator."""
        if self.operator_logged_in:
            logger.info(
                f"Operator logged out from {self.device_name}: {self.operator_name}"
            )
            self.operator_logged_in = False
            self.operator_name = ""

    # ----------------------------------------------------------------
    # SCADA integration
    # ----------------------------------------------------------------

    async def get_tag_from_scada(self, tag_name: str) -> Any:
        """
        Read tag value from SCADA server.

        Args:
            tag_name: SCADA tag name

        Returns:
            Tag value or None if not found
        """
        scada_memory = await self.data_store.bulk_read_memory(self.scada_server)

        if scada_memory and "tag_values" in scada_memory:
            return scada_memory["tag_values"].get(tag_name)

        return None

    async def send_command_to_scada(
        self, device_name: str, address_type: str, address: int, value: Any
    ) -> bool:
        """
        Send control command via SCADA to a device.

        Args:
            device_name: Target device
            address_type: Memory type (e.g., 'holding_register', 'coil')
            address: Memory address
            value: Value to write

        Returns:
            True if command sent successfully
        """
        # Write directly to device memory via DataStore
        # In real system, this would go through SCADA server
        await self.data_store.write_memory(device_name, address_type, value)

        logger.info(
            f"HMI command: {self.operator_name} → {device_name}:"
            f"{address_type}[{address}] = {value}"
        )

        return True

    async def get_current_screen_data(self) -> dict[str, Any]:
        """Get data for currently displayed screen."""
        if not self.current_screen or self.current_screen not in self.screens:
            return {}

        screen = self.screens[self.current_screen]
        screen_data = {}

        # Fetch all tags displayed on this screen
        for tag_name in screen.tags_displayed:
            value = await self.get_tag_from_scada(tag_name)
            screen_data[tag_name] = value

        return screen_data

    # ----------------------------------------------------------------
    # Security vulnerabilities (for testing)
    # ----------------------------------------------------------------

    def get_config_file_contents(self) -> dict[str, Any]:
        """
        Get HMI configuration file contents.

        Simulates common vulnerability: credentials in plaintext config files.
        """
        return {
            "scada_server": self.scada_server,
            "scada_username": "scada_user",
            "scada_password": "scada123",  # Plaintext!
            "database": {
                "server": "localhost",
                "username": "sa",
                "password": "HMI2014",  # More plaintext!
            },
            "plc_connections": [
                {
                    "name": "turbine_plc_1",
                    "ip": "192.168.1.100",
                    "port": 502,
                    "password": "",  # No password
                }
            ],
        }

    # ----------------------------------------------------------------
    # State management
    # ----------------------------------------------------------------

    async def _sync_to_datastore(self) -> None:
        """Synchronise HMI state to DataStore."""
        memory_map = {
            "scada_server": self.scada_server,
            "current_screen": self.current_screen,
            "operator_logged_in": self.operator_logged_in,
            "operator_name": self.operator_name,
            "web_interface_port": self.web_interface_port,
            "screens": [screen.screen_name for screen in self.screens.values()],
        }

        await self.data_store.bulk_write_memory(self.device_name, memory_map)

    async def get_telemetry(self) -> dict[str, Any]:
        """Get HMI telemetry."""
        return {
            "device_name": self.device_name,
            "device_type": "hmi_workstation",
            "os_version": self.os_version,
            "hmi_software": self.hmi_software,
            "scada_server": self.scada_server,
            "operator": {
                "logged_in": self.operator_logged_in,
                "name": self.operator_name,
                "login_time": self.login_time,
            },
            "current_screen": self.current_screen,
            "total_screens": len(self.screens),
            "security": {
                "web_interface_enabled": self.web_interface_enabled,
                "rdp_enabled": self.rdp_enabled,
                "credentials_plaintext": self.credentials_plaintext,
            },
        }
