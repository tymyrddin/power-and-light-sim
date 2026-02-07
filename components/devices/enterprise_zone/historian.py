# components/devices/enterprise_zone/historian.py
"""
Historian device class with ICSLogger integration.

Long-term time-series data storage for industrial processes.
Stores every sensor reading, alarm, operator action for years.
Common products: OSIsoft PI, GE Proficy, Wonderware Historian.

Multi-Protocol Support:
- OPC UA/DA: Data collection from SCADA/PLCs
- SQL/ODBC: Database storage and queries
- HTTP/REST: Web interface and API queries
- Proprietary: Vendor-specific protocols (PI, Proficy, etc.)
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
class DataPoint:
    """Historical data point with quality indicator."""

    tag_name: str
    timestamp: float
    value: Any
    quality: str = "good"  # good, bad, uncertain


class Historian(BaseDevice):
    """
    Historian for long-term time-series data storage.

    Collects data from SCADA via OPC UA and stores for years.
    Provides SQL/HTTP access for queries and analysis.
    Valuable for operations analysis and attacker reconnaissance.

    Security characteristics (realistic):
    - SQL database with weak credentials
    - Web interface with SQL injection vulnerabilities
    - No authentication on web interface
    - Accessible from corporate network
    - Exposes sensitive operational data

    Protocol Support:
    - OPC UA: Primary data collection from SCADA
    - SQL: Database queries (vulnerable to injection)
    - HTTP: Web interface and REST API
    - ODBC/JDBC: External database access

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
        storage_capacity_mb: int = 100000,  # 100GB default
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
            scada_server: SCADA server to collect data from (OPC UA)
            retention_days: Days to retain historical data
            storage_capacity_mb: Maximum storage capacity in MB
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
        self.storage_capacity_mb = storage_capacity_mb

        # Historical data storage
        self.historical_data: list[DataPoint] = []

        # Collection statistics
        self.total_points_collected = 0
        self.failed_collections = 0
        self.last_collection_time: float = 0.0
        self.storage_capacity_alarm_raised = False

        # Realistic database configuration (security vulnerabilities)
        self.db_type = "SQL Server"
        self.db_host = "localhost"
        self.db_name = "Historian"
        self.db_user = "sa"  # Default admin account
        self.db_password = "Historian2015"  # Terrible password
        self.db_connection_string = (
            f"Server={self.db_host};Database={self.db_name};"
            f"User={self.db_user};Password={self.db_password};"
        )
        self.db_connected = True  # Simulated connection state

        # Web interface (common vulnerability)
        self.web_interface_enabled = True
        self.web_interface_port = 8080
        self.web_auth_required = False  # Often disabled for convenience
        self.web_has_sql_injection = True  # Common vulnerability
        self.api_key = "historian_api_2015"  # Weak API key

        # Protocol configuration
        self.opcua_enabled = True  # Primary data collection
        self.sql_enabled = True  # Database queries
        self.http_enabled = True  # Web interface
        self.odbc_enabled = True  # External database access

        self.logger.info(
            f"Historian '{device_name}' initialised "
            f"(SCADA={scada_server}, retention={retention_days} days, "
            f"capacity={storage_capacity_mb}MB)"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return 'historian' as device type."""
        return "historian"

    def _supported_protocols(self) -> list[str]:
        """
        Historian supports multiple protocols.

        - opcua: Data collection from SCADA/PLCs
        - sql: Database queries
        - http: Web interface and REST API
        - odbc: External database access
        """
        return ["opcua", "sql", "http", "odbc"]

    async def _initialise_memory_map(self) -> None:
        """
        Initialise historian memory map.

        Memory map structure:
        - Configuration (SCADA server, retention, protocols)
        - Statistics (data points, collection rate, storage)
        - Database info (type, user, connection state)
        - Web interface status (port, auth, vulnerabilities)
        - Protocol status (OPC UA, SQL, HTTP, ODBC)
        """
        self.memory_map = {
            # Configuration
            "scada_server": self.scada_server,
            "retention_days": self.retention_days,
            "storage_capacity_mb": self.storage_capacity_mb,
            "collection_interval": self.scan_interval,
            # Statistics
            "data_points_stored": len(self.historical_data),
            "total_points_collected": self.total_points_collected,
            "failed_collections": self.failed_collections,
            "unique_tags": 0,
            "storage_used_mb": 0,  # Estimated
            # Database
            "db_type": self.db_type,
            "db_host": self.db_host,
            "db_user": self.db_user,
            "db_connected": self.db_connected,
            # Web interface
            "web_interface_enabled": self.web_interface_enabled,
            "web_interface_port": self.web_interface_port,
            "web_auth_required": self.web_auth_required,
            # Protocol status
            "opcua_enabled": self.opcua_enabled,
            "sql_enabled": self.sql_enabled,
            "http_enabled": self.http_enabled,
            "odbc_enabled": self.odbc_enabled,
        }

        self.logger.debug("Historian memory map initialised")

    async def _scan_cycle(self) -> None:
        """
        Execute historian scan cycle.

        Collects data from SCADA server via OPC UA and stores it.
        Trims old data based on retention policy.
        Monitors storage capacity and raises alarms if needed.
        """
        try:
            # Collect data from SCADA server
            await self._collect_data()

            # Trim old data based on retention policy
            await self._trim_old_data()

            # Check storage capacity
            await self._check_storage_capacity()

            # Update memory map with current stats
            self.memory_map["data_points_stored"] = len(self.historical_data)
            self.memory_map["total_points_collected"] = self.total_points_collected
            self.memory_map["failed_collections"] = self.failed_collections
            self.memory_map["unique_tags"] = len(self.get_all_tags())
            self.memory_map["storage_used_mb"] = self._estimate_storage_mb()

            self.last_collection_time = self.sim_time.now()

        except Exception as e:
            self.logger.error(f"Historian collection error: {e}", exc_info=True)
            await self.logger.log_alarm(
                message=f"Historian '{self.device_name}': Critical error in data collection",
                priority=AlarmPriority.HIGH,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={
                    "error": str(e),
                    "scada_server": self.scada_server,
                },
            )

    async def _collect_data(self) -> int:
        """
        Collect data from SCADA server via OPC UA.

        Returns:
            Number of data points collected
        """
        try:
            scada_memory = await self.data_store.bulk_read_memory(self.scada_server)

            if not scada_memory:
                self.failed_collections += 1

                # Alarm on repeated failures
                if self.failed_collections % 5 == 0:
                    await self.logger.log_alarm(
                        message=f"Historian '{self.device_name}': Failed to collect data from '{self.scada_server}' ({self.failed_collections} failures)",
                        priority=AlarmPriority.MEDIUM,
                        state=AlarmState.ACTIVE,
                        device=self.device_name,
                        data={
                            "scada_server": self.scada_server,
                            "failure_count": self.failed_collections,
                        },
                    )

                return 0

            if "tag_values" not in scada_memory:
                self.logger.debug(
                    f"No tag_values in SCADA memory for {self.scada_server}"
                )
                return 0

            current_time = self.sim_time.now()
            collected = 0

            for tag_name, value in scada_memory["tag_values"].items():
                self.historical_data.append(
                    DataPoint(
                        tag_name=tag_name,
                        timestamp=current_time,
                        value=value,
                        quality="good",
                    )
                )
                collected += 1
                self.total_points_collected += 1

            if collected > 0:
                self.logger.debug(
                    f"Collected {collected} data points from {self.scada_server}"
                )

            return collected

        except Exception as e:
            self.failed_collections += 1
            self.logger.error(f"Data collection failed: {e}", exc_info=True)

            await self.logger.log_alarm(
                message=f"Historian '{self.device_name}': Data collection error from '{self.scada_server}'",
                priority=AlarmPriority.MEDIUM,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={
                    "scada_server": self.scada_server,
                    "error": str(e),
                },
            )

            return 0

    async def _trim_old_data(self) -> None:
        """Trim data older than retention policy."""
        cutoff_time = self.sim_time.now() - (self.retention_days * 86400)
        original_count = len(self.historical_data)

        self.historical_data = [
            dp for dp in self.historical_data if dp.timestamp > cutoff_time
        ]

        trimmed_count = original_count - len(self.historical_data)

        if trimmed_count > 0:
            self.logger.debug(
                f"Trimmed {trimmed_count} data points older than {self.retention_days} days"
            )

    async def _check_storage_capacity(self) -> None:
        """Check storage capacity and raise alarm if approaching limit."""
        storage_used_mb = self._estimate_storage_mb()
        storage_percent = (storage_used_mb / self.storage_capacity_mb) * 100

        # Alarm if storage is over 90%
        if storage_percent > 90 and not self.storage_capacity_alarm_raised:
            await self.logger.log_alarm(
                message=f"Historian '{self.device_name}': Storage capacity critical ({storage_percent:.1f}% used, {storage_used_mb:.1f}/{self.storage_capacity_mb}MB)",
                priority=AlarmPriority.HIGH,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={
                    "storage_used_mb": storage_used_mb,
                    "storage_capacity_mb": self.storage_capacity_mb,
                    "storage_percent": storage_percent,
                    "data_points": len(self.historical_data),
                },
            )
            self.storage_capacity_alarm_raised = True

        # Clear alarm if storage drops below 80%
        elif storage_percent < 80 and self.storage_capacity_alarm_raised:
            await self.logger.log_alarm(
                message=f"Historian '{self.device_name}': Storage capacity normal ({storage_percent:.1f}% used)",
                priority=AlarmPriority.HIGH,
                state=AlarmState.CLEARED,
                device=self.device_name,
                data={
                    "storage_used_mb": storage_used_mb,
                    "storage_percent": storage_percent,
                },
            )
            self.storage_capacity_alarm_raised = False

    def _estimate_storage_mb(self) -> float:
        """
        Estimate storage used in MB.

        Rough estimate: ~100 bytes per data point.
        """
        return (len(self.historical_data) * 100) / (1024 * 1024)

    # ----------------------------------------------------------------
    # Historical data queries
    # ----------------------------------------------------------------

    async def query_history(
        self,
        tag_name: str,
        start_time: float,
        end_time: float,
        user: str = "anonymous",
    ) -> list[DataPoint]:
        """
        Query historical data via SQL/HTTP interface.

        In real systems, this is often vulnerable to SQL injection.

        Args:
            tag_name: Tag to query
            start_time: Start of time range
            end_time: End of time range
            user: User making the query (for audit logging)

        Returns:
            List of matching data points
        """
        # Audit log the query (security monitoring)
        await self.logger.log_audit(
            message=f"Historian query: tag='{tag_name}', time range={start_time:.1f}-{end_time:.1f}",
            user=user,
            action="historian_query",
            result="SUCCESS",
            data={
                "historian": self.device_name,
                "tag_name": tag_name,
                "start_time": start_time,
                "end_time": end_time,
                "query_type": "time_range",
            },
        )

        results = [
            dp
            for dp in self.historical_data
            if dp.tag_name == tag_name and start_time <= dp.timestamp <= end_time
        ]

        self.logger.debug(f"Query for '{tag_name}' returned {len(results)} data points")

        return results

    def get_all_tags(self) -> list[str]:
        """Get list of all tags with historical data."""
        return list({dp.tag_name for dp in self.historical_data})

    async def get_database_credentials(self, user: str = "anonymous") -> dict[str, str]:
        """
        Get database credentials (security vulnerability).

        Simulates common vulnerability: exposed database credentials.
        In real systems, credentials are often accessible via:
        - Configuration files
        - API endpoints
        - Web interface debugging
        - Memory dumps

        Args:
            user: User accessing credentials (for audit logging)

        Returns:
            Database connection information
        """
        # Log credential access (security event)
        await self.logger.log_security(
            message=f"Historian database credentials accessed by '{user}' on '{self.device_name}'",
            severity=EventSeverity.WARNING,
            user=user,
            data={
                "historian": self.device_name,
                "db_type": self.db_type,
                "db_host": self.db_host,
                "access_type": "credentials_query",
            },
        )

        return {
            "db_type": self.db_type,
            "host": self.db_host,
            "database": self.db_name,
            "username": self.db_user,
            "password": self.db_password,  # Exposed!
            "connection_string": self.db_connection_string,
        }

    # ----------------------------------------------------------------
    # Configuration management
    # ----------------------------------------------------------------

    async def set_retention_days(self, days: int, user: str = "system") -> bool:
        """
        Change data retention policy.

        Args:
            days: New retention period in days
            user: User making the change

        Returns:
            True if successful
        """
        if days <= 0:
            self.logger.warning(f"Invalid retention days: {days}")
            return False

        old_retention = self.retention_days
        self.retention_days = days
        self.memory_map["retention_days"] = days

        # Audit log configuration change
        await self.logger.log_audit(
            message=f"Historian '{self.device_name}': Retention policy changed from {old_retention} to {days} days",
            user=user,
            action="historian_config_change",
            result="SUCCESS",
            data={
                "historian": self.device_name,
                "setting": "retention_days",
                "old_value": old_retention,
                "new_value": days,
            },
        )

        self.logger.info(f"Retention policy changed to {days} days by {user}")
        return True

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
            "total_collected": self.total_points_collected,
            "failed_collections": self.failed_collections,
            "unique_tags": len(self.get_all_tags()),
            "storage_used_mb": self._estimate_storage_mb(),
            "storage_capacity_mb": self.storage_capacity_mb,
            "storage_percent": (
                self._estimate_storage_mb() / self.storage_capacity_mb * 100
            ),
            "protocols": {
                "opcua": self.opcua_enabled,
                "sql": self.sql_enabled,
                "http": self.http_enabled,
                "odbc": self.odbc_enabled,
            },
        }
        return historian_status

    async def get_telemetry(self) -> dict[str, Any]:
        """Get historian telemetry data (includes vulnerabilities for attack simulation)."""
        return {
            "device_name": self.device_name,
            "device_type": "historian",
            "scada_server": self.scada_server,
            "retention_days": self.retention_days,
            "data_points_stored": len(self.historical_data),
            "unique_tags": len(self.get_all_tags()),
            "storage": {
                "used_mb": self._estimate_storage_mb(),
                "capacity_mb": self.storage_capacity_mb,
                "percent_used": (
                    self._estimate_storage_mb() / self.storage_capacity_mb * 100
                ),
            },
            "web_interface": {
                "enabled": self.web_interface_enabled,
                "port": self.web_interface_port,
                "auth_required": self.web_auth_required,
                "has_sql_injection": self.web_has_sql_injection,
                "api_key": self.api_key,  # Exposed!
            },
            "database": {
                "type": self.db_type,
                "host": self.db_host,
                "user": self.db_user,
                "password": self.db_password,  # Security vulnerability: exposed in telemetry
                "connected": self.db_connected,
            },
            "protocols": {
                "opcua": self.opcua_enabled,
                "sql": self.sql_enabled,
                "http": self.http_enabled,
                "odbc": self.odbc_enabled,
            },
        }
