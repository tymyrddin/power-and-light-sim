# components/devices/control_zone/rtu/rtu_c104.py
"""
IEC 60870-5-104 RTU device class.

Remote Terminal Unit with IEC 104 protocol support for
SCADA communications in power systems.
"""

import asyncio
import logging
from typing import Any

from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime

logger = logging.getLogger(__name__)


class RTUC104:
    """
    IEC 104 Remote Terminal Unit.

    Supports IEC 60870-5-104 information objects:
    - M_SP_NA_1 (Single-point information)
    - M_ME_NA_1 (Measured value, normalised)
    - C_SC_NA_1 (Single command)

    Example:
        >>> rtu = RTUC104(
        ...     device_name="remote_station_1",
        ...     data_store=data_store,
        ...     common_address=10
        ... )
        >>> rtu.add_single_point(100, "breaker_status")
        >>> rtu.add_measured_value(200, "line_current", scale=1000.0)
        >>> await rtu.initialise()
        >>> await rtu.start()
    """

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        common_address: int = 1,
        scan_rate_hz: float = 1.0,
    ):
        self.device_name = device_name
        self.data_store = data_store
        self.sim_time = SimulationTime()

        self.common_address = common_address
        self.scan_rate_hz = scan_rate_hz
        self.scan_interval = 1.0 / scan_rate_hz

        # IEC 104 information objects
        self.single_points: dict[int, bool] = {}  # M_SP_NA_1
        self.measured_values: dict[int, float] = {}  # M_ME_NA_1
        self.point_names: dict[int, str] = {}
        self.value_names: dict[int, str] = {}
        self.value_scales: dict[int, float] = {}

        self._running = False
        self._scan_task: asyncio.Task | None = None
        self._last_scan_time = 0.0

        logger.info(f"RTUC104 created: {device_name}, CA={common_address}")

    async def initialise(self) -> None:
        await self.data_store.register_device(
            device_name=self.device_name,
            device_type="rtu_c104",
            device_id=hash(self.device_name) % 1000,
            protocols=["iec104"],
            metadata={"common_address": self.common_address},
        )
        await self._sync_to_datastore()
        logger.info(f"RTUC104 initialised: {self.device_name}")

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._last_scan_time = self.sim_time.now()
        self._scan_task = asyncio.create_task(self._scan_cycle())
        logger.info(f"RTUC104 started: {self.device_name}")

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
        logger.info(f"RTUC104 stopped: {self.device_name}")

    def add_single_point(self, ioa: int, name: str) -> None:
        """Add single-point information object."""
        self.single_points[ioa] = False
        self.point_names[ioa] = name
        logger.debug(f"Single point added: IOA {ioa} - {name}")

    def add_measured_value(self, ioa: int, name: str, scale: float = 1.0) -> None:
        """Add measured value information object."""
        self.measured_values[ioa] = 0.0
        self.value_names[ioa] = name
        self.value_scales[ioa] = scale
        logger.debug(f"Measured value added: IOA {ioa} - {name}")

    def update_single_point(self, ioa: int, value: bool) -> None:
        """Update single-point value."""
        if ioa in self.single_points:
            self.single_points[ioa] = value

    def update_measured_value(self, ioa: int, value: float) -> None:
        """Update measured value."""
        if ioa in self.measured_values:
            self.measured_values[ioa] = value

    async def _scan_cycle(self) -> None:
        while self._running:
            try:
                await self._sync_to_datastore()
            except Exception as e:
                logger.error(f"Error in RTU scan: {e}")
            await asyncio.sleep(self.scan_interval)

    async def _sync_to_datastore(self) -> None:
        memory_map = {
            "common_address": self.common_address,
            "iec104_single_points": self.single_points.copy(),
            "iec104_measured_values": self.measured_values.copy(),
        }
        await self.data_store.bulk_write_memory(self.device_name, memory_map)

    async def get_telemetry(self) -> dict[str, Any]:
        return {
            "device_name": self.device_name,
            "common_address": self.common_address,
            "single_points": self.single_points.copy(),
            "measured_values": self.measured_values.copy(),
        }
