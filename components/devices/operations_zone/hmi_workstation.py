# components/devices/operations_zone/hmi_workstation.py
"""
HMI (Human-Machine Interface) Workstation device class.

Operator interface for monitoring and controlling the industrial process.
Typically runs software like Wonderware InTouch, FactoryTalk View, or Ignition.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from components.devices.operations_zone.base_supervisory import (
    BaseSupervisoryDevice,
    PollTarget,
)
from components.state.data_store import DataStore


@dataclass
class HMIScreen:
    """HMI display screen configuration."""

    screen_name: str
    tags_displayed: list[str] = field(default_factory=list)
    controls_available: list[str] = field(default_factory=list)


class HMIWorkstation(BaseSupervisoryDevice):
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
        ...     device_id=1,
        ...     data_store=data_store,
        ...     scada_server="scada_master_1"
        ... )
        >>> hmi.add_screen(
        ...     "turbine_overview",
        ...     tags=["TURB1_SPEED", "TURB1_POWER"],
        ...     controls=["TURB1_SPEED_SETPOINT", "TURB1_START_STOP"]
        ... )
        >>> await hmi.start()
        >>> hmi.login_operator("operator1")
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        scada_server: str = "scada_master_1",
        os_version: str = "Windows 10",
        hmi_software: str = "Wonderware InTouch 2014",
        description: str = "",
        scan_interval: float = 0.5,  # HMI refresh rate (500ms default)
        log_dir: Path | None = None,
    ):
        """
        Initialise HMI workstation.

        Args:
            device_name: Unique device identifier
            device_id: Numeric ID for protocol addressing
            data_store: DataStore instance
            scada_server: SCADA server to connect to
            os_version: Operating system version
            hmi_software: HMI software package
            description: Human-readable description
            scan_interval: Screen refresh rate in seconds
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

        # Configuration
        self.scada_server = scada_server
        self.os_version = os_version
        self.hmi_software = hmi_software

        # HMI screens
        self.screens: dict[str, HMIScreen] = {}
        self.current_screen: str | None = None

        # Screen data cache (updated each scan)
        self.screen_data: dict[str, Any] = {}

        # Operator session
        self.operator_logged_in: bool = False
        self.operator_name: str = ""
        self.login_time: float = 0.0

        # Security characteristics (realistic weaknesses)
        self.web_interface_enabled: bool = True
        self.web_interface_port: int = 8080
        self.web_default_credentials: tuple[str, str] = ("admin", "admin")
        self.rdp_enabled: bool = True
        self.config_file_path: str = "C:\\InTouch\\config.xml"
        self.credentials_plaintext: bool = True

        # Add SCADA server as poll target
        self.add_poll_target(
            device_name=scada_server,
            protocol="internal",
            poll_rate_s=scan_interval,
        )

        self.logger.info(
            f"HMIWorkstation '{device_name}' initialised "
            f"(OS={os_version}, software={hmi_software})"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return 'hmi_workstation' as device type."""
        return "hmi_workstation"

    def _supported_protocols(self) -> list[str]:
        """HMI workstations support HTTP, RDP, VNC for remote access."""
        return ["http", "rdp", "vnc"]

    async def _initialise_memory_map(self) -> None:
        """
        Initialise HMI workstation memory map.

        Memory map structure:
        - Operator session state
        - Current screen info
        - Cached screen data
        """
        self.memory_map = {
            # Operator session
            "operator_logged_in": False,
            "operator_name": "",
            "login_time": 0.0,
            # Screen state
            "current_screen": None,
            "screen_count": len(self.screens),
            "screens": list(self.screens.keys()),
            # Cached data from SCADA
            "screen_data": {},
            # Configuration
            "scada_server": self.scada_server,
            "web_interface_port": self.web_interface_port,
        }

        self.logger.debug(f"Memory map initialised with {len(self.screens)} screens")

    # ----------------------------------------------------------------
    # BaseSupervisoryDevice implementation
    # ----------------------------------------------------------------

    async def _poll_device(self, target: PollTarget) -> None:
        """
        Poll SCADA server for tag data.

        Args:
            target: Poll target (SCADA server)
        """
        try:
            # Read SCADA server memory from DataStore
            scada_memory = await self.data_store.bulk_read_memory(target.device_name)

            if scada_memory and "tag_values" in scada_memory:
                # Update screen data cache with tags for current screen
                if self.current_screen and self.current_screen in self.screens:
                    screen = self.screens[self.current_screen]
                    for tag_name in screen.tags_displayed:
                        if tag_name in scada_memory["tag_values"]:
                            self.screen_data[tag_name] = scada_memory["tag_values"][
                                tag_name
                            ]

                target.last_poll_success = True
                target.consecutive_failures = 0
            else:
                target.last_poll_success = False
                target.consecutive_failures += 1

        except Exception as e:
            self.logger.error(f"Error polling SCADA server {target.device_name}: {e}")
            target.last_poll_success = False
            target.consecutive_failures += 1
            self.failed_polls += 1

    async def _process_polled_data(self) -> None:
        """Process polled data and sync to memory map."""
        # Update memory map with current state
        self.memory_map["operator_logged_in"] = self.operator_logged_in
        self.memory_map["operator_name"] = self.operator_name
        self.memory_map["login_time"] = self.login_time
        self.memory_map["current_screen"] = self.current_screen
        self.memory_map["screen_count"] = len(self.screens)
        self.memory_map["screens"] = list(self.screens.keys())
        self.memory_map["screen_data"] = self.screen_data.copy()

    def _check_alarms(self) -> None:
        """
        Check for HMI-specific alarm conditions.

        HMI doesn't generate process alarms - those come from SCADA.
        Could check for session timeouts, connection issues, etc.
        """
        # Check for SCADA connection failure
        if self.scada_server in self.poll_targets:
            target = self.poll_targets[self.scada_server]
            if target.consecutive_failures >= 3:
                self.logger.warning(
                    f"HMI '{self.device_name}': Lost connection to SCADA server"
                )

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

        self.logger.debug(
            f"HMI screen added: {screen_name}, "
            f"{len(tags)} tags, {len(controls)} controls"
        )

    def navigate_to_screen(self, screen_name: str) -> bool:
        """
        Navigate to a specific screen.

        Args:
            screen_name: Screen to navigate to

        Returns:
            True if navigation successful, False if screen not found
        """
        if screen_name in self.screens:
            self.current_screen = screen_name
            # Clear cached data for new screen
            self.screen_data = {}
            self.logger.debug(f"HMI navigated to screen: {screen_name}")
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

        self.logger.info(f"Operator logged in to {self.device_name}: {operator_name}")
        return True

    def logout_operator(self) -> None:
        """Logout current operator."""
        if self.operator_logged_in:
            self.logger.info(
                f"Operator logged out from {self.device_name}: {self.operator_name}"
            )
            self.operator_logged_in = False
            self.operator_name = ""
            self.login_time = 0.0

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
        if not self.operator_logged_in:
            self.logger.warning(
                f"Command rejected: No operator logged in on {self.device_name}"
            )
            return False

        # Write directly to device memory via DataStore
        # In real system, this would go through SCADA server
        await self.data_store.write_memory(device_name, address_type, value)

        self.logger.info(
            f"HMI command: {self.operator_name} -> {device_name}:"
            f"{address_type}[{address}] = {value}"
        )

        return True

    async def get_current_screen_data(self) -> dict[str, Any]:
        """Get data for currently displayed screen."""
        if not self.current_screen or self.current_screen not in self.screens:
            return {}

        # Return cached screen data (updated by scan cycle)
        return self.screen_data.copy()

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
    # Status and telemetry
    # ----------------------------------------------------------------

    async def get_hmi_status(self) -> dict[str, Any]:
        """Get HMI-specific status information."""
        base_status = await self.get_supervisory_status()
        hmi_status = {
            **base_status,
            "os_version": self.os_version,
            "hmi_software": self.hmi_software,
            "scada_server": self.scada_server,
            "current_screen": self.current_screen,
            "screen_count": len(self.screens),
            "operator_logged_in": self.operator_logged_in,
            "operator_name": self.operator_name,
        }
        return hmi_status

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
