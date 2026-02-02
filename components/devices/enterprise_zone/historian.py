# components/devices/operations_zone/historian.py
"""
Historian device class.

Long-term time-series data storage for industrial processes.
Stores every sensor reading, alarm, operator action for years.
Common products: OSIsoft PI, GE Proficy, Wonderware Historian.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from components.devices.core.base_device import BaseDevice
from components.state.data_store import DataStore


@dataclass
class DataPoint:
    """Historical data point."""

    tag_name: str
    timestamp: float
    value: Any
    quality: str = "good"


class Historian(BaseDevice):
    """
    Historian for long-term time-series data storage.

    Collects data from SCADA and stores for years.
    Valuable for operations analysis and attacker reconnaissance.

    Security characteristics (realistic):
    - SQL database with weak credentials
    - Web interface with SQL injection vulnerabilities
    - No authentication on web interface
    - Accessible from corporate network

    Example:
        >>> historian = Historian(
        ...     device_name="historian_primary",
        ...     device_id=300,
        ...     data_store=data_store,
        ...     scada_server="scada_server_primary",
        ...     retention_days=3650  # 10 years
        ... )
        >>> await historian.start()
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        scada_server: str = "scada_server_primary",
        retention_days: int = 3650,
        description: str = "",
        scan_interval: float = 60.0,  # Collect data every 60 seconds
        log_dir: Path | None = None,
    ):
        """
        Initialise historian.

        Args:
            device_name: Unique device identifier
            device_id: Numeric ID for protocol addressing
            data_store: DataStore instance
            scada_server: SCADA server to collect data from
            retention_days: Days to retain historical data
            description: Human-readable description
            scan_interval: Data collection interval in seconds
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
        self.retention_days = retention_days

        # Historical data storage
        self.historical_data: list[DataPoint] = []

        # Realistic database configuration
        self.db_type = "SQL Server"
        self.db_user = "sa"
        self.db_password = "Historian2015"  # Terrible password
        self.db_connection_string = f"Server=localhost;Database=Historian;User={self.db_user};Password={self.db_password};"

        # Web interface (common vulnerability)
        self.web_interface_enabled = True
        self.web_interface_port = 8080
        self.web_auth_required = False  # Often disabled
        self.web_has_sql_injection = True  # Common vulnerability

        self.logger.info(
            f"Historian '{device_name}' initialised "
            f"(SCADA={scada_server}, retention={retention_days} days)"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return 'historian' as device type."""
        return "historian"

    def _supported_protocols(self) -> list[str]:
        """Historian supports SQL, HTTP, and proprietary protocols."""
        return ["sql", "http", "opcua"]

    async def _initialise_memory_map(self) -> None:
        """
        Initialise historian memory map.

        Memory map structure:
        - Configuration (SCADA server, retention)
        - Statistics (data points, collection rate)
        - Database info
        - Web interface status
        """
        self.memory_map = {
            # Configuration
            "scada_server": self.scada_server,
            "retention_days": self.retention_days,
            # Statistics
            "data_points_stored": len(self.historical_data),
            "collection_interval": self.scan_interval,
            # Database
            "db_type": self.db_type,
            "db_user": self.db_user,
            # Web interface
            "web_interface_enabled": self.web_interface_enabled,
            "web_interface_port": self.web_interface_port,
            "web_auth_required": self.web_auth_required,
        }

        self.logger.debug("Historian memory map initialised")

    async def _scan_cycle(self) -> None:
        """
        Execute historian scan cycle.

        Collects data from SCADA server and stores it.
        Trims old data based on retention policy.
        """
        try:
            # Collect data from SCADA server
            scada_memory = await self.data_store.bulk_read_memory(self.scada_server)
            if scada_memory and "tag_values" in scada_memory:
                current_time = self.sim_time.now()

                for tag_name, value in scada_memory["tag_values"].items():
                    self.historical_data.append(
                        DataPoint(
                            tag_name=tag_name,
                            timestamp=current_time,
                            value=value,
                        )
                    )

            # Trim old data based on retention policy
            cutoff_time = self.sim_time.now() - (self.retention_days * 86400)
            original_count = len(self.historical_data)
            self.historical_data = [
                dp for dp in self.historical_data if dp.timestamp > cutoff_time
            ]
            trimmed_count = original_count - len(self.historical_data)
            if trimmed_count > 0:
                self.logger.debug(f"Trimmed {trimmed_count} old data points")

            # Update memory map with current stats
            self.memory_map["data_points_stored"] = len(self.historical_data)

        except Exception as e:
            self.logger.error(f"Historian collection error: {e}", exc_info=True)

    # ----------------------------------------------------------------
    # Historical data queries
    # ----------------------------------------------------------------

    async def query_history(
        self, tag_name: str, start_time: float, end_time: float
    ) -> list[DataPoint]:
        """
        Query historical data.

        In real systems, this is often vulnerable to SQL injection.

        Args:
            tag_name: Tag to query
            start_time: Start of time range
            end_time: End of time range

        Returns:
            List of matching data points
        """
        return [
            dp
            for dp in self.historical_data
            if dp.tag_name == tag_name and start_time <= dp.timestamp <= end_time
        ]

    def get_all_tags(self) -> list[str]:
        """Get list of all tags with historical data."""
        return list(set(dp.tag_name for dp in self.historical_data))

    def get_database_credentials(self) -> dict[str, str]:
        """
        Get database credentials (security vulnerability).

        Simulates common vulnerability: exposed database credentials.
        """
        return {
            "db_type": self.db_type,
            "username": self.db_user,
            "password": self.db_password,
            "connection_string": self.db_connection_string,
        }

    # ----------------------------------------------------------------
    # Status and telemetry
    # ----------------------------------------------------------------

    async def get_historian_status(self) -> dict[str, Any]:
        """Get historian-specific status."""
        base_status = await self.get_status()
        historian_status = {
            **base_status,
            "scada_server": self.scada_server,
            "retention_days": self.retention_days,
            "data_points_stored": len(self.historical_data),
            "unique_tags": len(self.get_all_tags()),
        }
        return historian_status

    async def get_telemetry(self) -> dict[str, Any]:
        """Get historian telemetry data."""
        return {
            "device_name": self.device_name,
            "device_type": "historian",
            "scada_server": self.scada_server,
            "retention_days": self.retention_days,
            "data_points_stored": len(self.historical_data),
            "unique_tags": len(self.get_all_tags()),
            "web_interface": {
                "enabled": self.web_interface_enabled,
                "port": self.web_interface_port,
                "auth_required": self.web_auth_required,
                "has_sql_injection": self.web_has_sql_injection,
            },
            "database": {
                "type": self.db_type,
                "user": self.db_user,
                "password": self.db_password,  # Security vulnerability: exposed in telemetry
            },
        }
