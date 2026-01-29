# components/devices/enterprise_zone/historian.py
"""
Historian device class.

Long-term time-series data storage for industrial processes.
Stores every sensor reading, alarm, operator action for years.
Common products: OSIsoft PI, GE Proficy, Wonderware Historian.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime

logger = logging.getLogger(__name__)


@dataclass
class DataPoint:
    """Historical data point."""

    tag_name: str
    timestamp: float
    value: Any
    quality: str = "good"


class Historian:
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
        ...     device_name="historian_1",
        ...     data_store=data_store,
        ...     scada_server="scada_master_1",
        ...     retention_days=3650  # 10 years
        ... )
        >>> await historian.initialise()
        >>> await historian.start()
    """

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        scada_server: str = "scada_master_1",
        retention_days: int = 3650,
    ):
        self.device_name = device_name
        self.data_store = data_store
        self.sim_time = SimulationTime()
        self.scada_server = scada_server
        self.retention_days = retention_days

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

        self._running = False
        self._collection_task: asyncio.Task | None = None

        logger.info(
            f"Historian created: {device_name}, retention={retention_days} days"
        )

    async def initialise(self) -> None:
        await self.data_store.register_device(
            device_name=self.device_name,
            device_type="historian",
            device_id=hash(self.device_name) % 1000,
            protocols=["sql", "http", "proprietary"],
            metadata={
                "scada_server": self.scada_server,
                "retention_days": self.retention_days,
                "data_points": len(self.historical_data),
            },
        )
        logger.info(f"Historian initialised: {self.device_name}")

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._collection_task = asyncio.create_task(self._collect_data())
        logger.info(f"Historian started: {self.device_name}")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._collection_task:
            self._collection_task.cancel()
            try:
                await self._collection_task
            except asyncio.CancelledError:
                pass
        logger.info(f"Historian stopped: {self.device_name}")

    async def _collect_data(self) -> None:
        """Collect data from SCADA server periodically."""
        while self._running:
            try:
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

                # Trim old data
                cutoff_time = self.sim_time.now() - (self.retention_days * 86400)
                self.historical_data = [
                    dp for dp in self.historical_data if dp.timestamp > cutoff_time
                ]

            except Exception as e:
                logger.error(f"Historian collection error: {e}")

            await asyncio.sleep(60.0)  # Collect every minute

    async def query_history(
        self, tag_name: str, start_time: float, end_time: float
    ) -> list[DataPoint]:
        """
        Query historical data.

        In real systems, this is often vulnerable to SQL injection.
        """
        return [
            dp
            for dp in self.historical_data
            if dp.tag_name == tag_name and start_time <= dp.timestamp <= end_time
        ]

    def get_database_credentials(self) -> dict[str, str]:
        """Get database credentials (security vulnerability)."""
        return {
            "db_type": self.db_type,
            "username": self.db_user,
            "password": self.db_password,
            "connection_string": self.db_connection_string,
        }

    async def get_telemetry(self) -> dict[str, Any]:
        return {
            "device_name": self.device_name,
            "device_type": "historian",
            "scada_server": self.scada_server,
            "retention_days": self.retention_days,
            "data_points_stored": len(self.historical_data),
            "web_interface": {
                "enabled": self.web_interface_enabled,
                "port": self.web_interface_port,
                "auth_required": self.web_auth_required,
                "has_sql_injection": self.web_has_sql_injection,
            },
            "database": {
                "type": self.db_type,
                "user": self.db_user,
            },
        }
