# components/devices/control_zone/safety/sis_controller.py
"""
Safety Instrumented System (SIS) Controller device class.

Independent safety system that monitors process and automatically
brings system to safe state if danger detected.

CRITICAL: SIS must be independent from BPCS (Basic Process Control System).
Never break safety systems during penetration testing!
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime

logger = logging.getLogger(__name__)


@dataclass
class SafetyFunction:
    """Safety function configuration."""

    function_name: str
    safety_level: str  # 'SIL1', 'SIL2', 'SIL3', 'SIL4'
    trip_condition: str
    enabled: bool = True
    trip_count: int = 0
    last_trip_time: float = 0.0


class SISController:
    """
    Safety Instrumented System controller.

    Monitors process conditions and automatically executes safety
    shutdown if dangerous conditions detected. Must be independent
    from normal control system (BPCS).

    Per IEC 61511, safety systems should be:
    - Independent from control systems
    - Separate network
    - Separate engineering workstation
    - Cannot be bypassed remotely

    Reality: Often shares engineering workstation with BPCS

    Example:
        >>> sis = SISController(
        ...     device_name="reactor_sis_1",
        ...     data_store=data_store,
        ...     independent_from=["turbine_plc_1", "scada_master_1"],
        ...     safety_level="SIL2"
        ... )
        >>> sis.add_safety_function(
        ...     "high_temperature_trip",
        ...     "SIL2",
        ...     "reactor_temp > 500°C"
        ... )
        >>> await sis.initialise()
        >>> await sis.start()
    """

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        independent_from: list[str] = None,
        safety_level: str = "SIL2",
        scan_rate_hz: float = 10.0,
    ):
        self.device_name = device_name
        self.data_store = data_store
        self.sim_time = SimulationTime()

        self.independent_from = independent_from or []
        self.safety_level = safety_level
        self.scan_rate_hz = scan_rate_hz
        self.scan_interval = 1.0 / scan_rate_hz

        # Safety functions
        self.safety_functions: dict[str, SafetyFunction] = {}

        # Safety state
        self.in_safe_state = False
        self.shutdown_active = False
        self.manual_reset_required = True

        # Architectural weaknesses (realistic)
        self.shared_engineering_workstation = True  # Common weakness
        self.shared_network = False  # Should be False
        self.uses_same_historian = True  # Common issue

        self._running = False
        self._scan_task: asyncio.Task | None = None

        logger.info(f"SISController created: {device_name}, SIL={safety_level}")

    async def initialise(self) -> None:
        await self.data_store.register_device(
            device_name=self.device_name,
            device_type="sis_controller",
            device_id=hash(self.device_name) % 1000,
            protocols=["safety_modbus", "profisafe"],
            metadata={
                "safety_level": self.safety_level,
                "independent_from": self.independent_from,
                "scan_rate_hz": self.scan_rate_hz,
            },
        )
        await self._sync_to_datastore()
        logger.info(f"SISController initialised: {self.device_name}")

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._scan_task = asyncio.create_task(self._safety_scan_cycle())
        logger.info(f"SISController started: {self.device_name}")

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
        logger.info(f"SISController stopped: {self.device_name}")

    def add_safety_function(
        self,
        function_name: str,
        safety_level: str,
        trip_condition: str,
        enabled: bool = True,
    ) -> None:
        self.safety_functions[function_name] = SafetyFunction(
            function_name=function_name,
            safety_level=safety_level,
            trip_condition=trip_condition,
            enabled=enabled,
        )
        logger.info(f"Safety function added: {function_name} ({safety_level})")

    async def _safety_scan_cycle(self) -> None:
        """Safety scan cycle - monitors conditions."""
        while self._running:
            try:
                # In real system, would monitor safety sensors
                # and execute trip logic

                # Sync state
                await self._sync_to_datastore()

            except Exception as e:
                logger.error(f"Safety scan error: {e}")

            await asyncio.sleep(self.scan_interval)

    async def execute_safety_shutdown(self, reason: str) -> None:
        """Execute emergency shutdown."""
        if not self.shutdown_active:
            self.shutdown_active = True
            self.in_safe_state = True

            logger.critical(f"SAFETY SHUTDOWN ACTIVATED: {self.device_name} - {reason}")

            # In real system, this would:
            # - Close isolation valves
            # - Activate emergency cooling
            # - Vent pressure to safe release
            # - Trigger evacuation alarms
            # - Log the event
            # - Require manual reset

    def manual_reset(self) -> bool:
        """Manual safety reset (requires operator action)."""
        if self.shutdown_active and self.manual_reset_required:
            logger.warning(f"Safety system manual reset: {self.device_name}")
            self.shutdown_active = False
            self.in_safe_state = False
            return True
        return False

    async def _sync_to_datastore(self) -> None:
        memory_map = {
            "safety_level": self.safety_level,
            "shutdown_active": self.shutdown_active,
            "in_safe_state": self.in_safe_state,
            "safety_functions": len(self.safety_functions),
        }
        await self.data_store.bulk_write_memory(self.device_name, memory_map)

    async def get_telemetry(self) -> dict[str, Any]:
        return {
            "device_name": self.device_name,
            "device_type": "sis_controller",
            "safety_level": self.safety_level,
            "shutdown_active": self.shutdown_active,
            "in_safe_state": self.in_safe_state,
            "safety_functions": {
                name: {
                    "safety_level": func.safety_level,
                    "enabled": func.enabled,
                    "trip_count": func.trip_count,
                }
                for name, func in self.safety_functions.items()
            },
            "architecture": {
                "independent_from": self.independent_from,
                "shared_engineering_workstation": self.shared_engineering_workstation,
                "shared_network": self.shared_network,
            },
        }
