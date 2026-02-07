# components/devices/ied.py
"""
Intelligent Electronic Device (IED) class.

Protection relays, power quality meters, and other smart grid devices
that monitor electrical conditions and provide protection functions.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from components.security.logging_system import (
    AlarmPriority,
    AlarmState,
    EventSeverity,
    get_logger,
)
from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime


@dataclass
class ProtectionFunction:
    """Protection function configuration."""

    function_type: str  # 'overcurrent', 'undervoltage', 'overvoltage', 'frequency'
    enabled: bool = True
    pickup_value: float = 0.0
    time_delay_s: float = 0.0
    trip_count: int = 0
    last_trip_time: float = 0.0


@dataclass
class MeasuredValues:
    """Electrical measurements."""

    voltage_v: float = 0.0
    current_a: float = 0.0
    frequency_hz: float = 50.0
    active_power_kw: float = 0.0
    reactive_power_kvar: float = 0.0
    power_factor: float = 1.0


class IED:
    """
    Intelligent Electronic Device.

    Simulates protection relays and smart grid devices with:
    - IEC 61850 GOOSE messaging
    - Protection function simulation
    - Electrical measurements
    - Trip logic

    Example:
        >>> ied = IED(
        ...     device_name="protection_relay_1",
        ...     data_store=data_store,
        ...     ied_name="BAY1_PROT",
        ...     goose_enabled=True
        ... )
        >>>
        >>> # Add overcurrent protection
        >>> ied.add_protection_function(
        ...     "overcurrent",
        ...     pickup_value=1200.0,  # 1200 A
        ...     time_delay_s=0.5
        ... )
        >>>
        >>> await ied.initialise()
        >>> await ied.start()
    """

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        ied_name: str = "IED_1",
        goose_enabled: bool = True,
        mms_enabled: bool = True,
        scan_rate_hz: float = 100.0,  # Protection relays scan fast
        log_dir: Path | None = None,
    ):
        """
        Initialise IED.

        Args:
            device_name: Unique device identifier
            data_store: DataStore instance
            ied_name: IEC 61850 IED name
            goose_enabled: Enable GOOSE messaging
            mms_enabled: Enable MMS reporting
            scan_rate_hz: Protection scan rate (typically fast)
            log_dir: Directory for log files
        """
        self.device_name = device_name
        self.data_store = data_store
        self.sim_time = SimulationTime()

        # Device-specific logger with ICS logging system
        self.logger = get_logger(
            self.__class__.__name__,
            device=device_name,
            log_dir=log_dir,
            data_store=data_store,
        )

        # Configuration
        self.ied_name = ied_name
        self.goose_enabled = goose_enabled
        self.mms_enabled = mms_enabled
        self.scan_rate_hz = scan_rate_hz
        self.scan_interval = 1.0 / scan_rate_hz

        # Protection functions
        self.protection_functions: dict[str, ProtectionFunction] = {}

        # Measurements
        self.measurements = MeasuredValues()

        # Trip state
        self.tripped = False
        self.trip_reason = ""

        # IEC 61850 data model (simplified)
        self.goose_messages: list[dict] = []
        self.mms_reports: list[dict] = []

        # Runtime state
        self._running = False
        self._scan_task: asyncio.Task | None = None
        self._last_scan_time = 0.0

        # Timers for time-delayed trips
        self._trip_timers: dict[str, float] = {}

        # Alarm state tracking
        self.trip_alarm_raised = False
        self.repeated_trip_alarm_raised = False

        self.logger.info(
            f"IED created: {device_name} ({ied_name}), scan_rate={scan_rate_hz}Hz"
        )

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialise IED and register with DataStore."""
        await self.data_store.register_device(
            device_name=self.device_name,
            device_type="ied",
            device_id=hash(self.device_name) % 1000,
            protocols=["iec61850_goose", "iec61850_mms", "modbus"],
            metadata={
                "ied_name": self.ied_name,
                "goose_enabled": self.goose_enabled,
                "mms_enabled": self.mms_enabled,
                "scan_rate_hz": self.scan_rate_hz,
                "protection_functions": len(self.protection_functions),
            },
        )

        await self._sync_to_datastore()

        self.logger.info(f"IED initialised: {self.device_name}")

    async def start(self) -> None:
        """Start protection scanning."""
        if self._running:
            self.logger.warning(f"IED already running: {self.device_name}")
            return

        self._running = True
        self._last_scan_time = self.sim_time.now()
        self._scan_task = asyncio.create_task(self._scan_cycle())

        self.logger.info(f"IED started: {self.device_name}")

    async def stop(self) -> None:
        """Stop protection scanning."""
        if not self._running:
            return

        self._running = False

        if self._scan_task:
            self._scan_task.cancel()
            try:
                await self._scan_task
            except asyncio.CancelledError:
                pass
            self._scan_task = None

        self.logger.info(f"IED stopped: {self.device_name}")

    # ----------------------------------------------------------------
    # Protection configuration
    # ----------------------------------------------------------------

    async def add_protection_function(
        self,
        function_type: str,
        pickup_value: float,
        time_delay_s: float = 0.0,
        enabled: bool = True,
        user: str = "system",
    ) -> None:
        """
        Add a protection function.

        Args:
            function_type: 'overcurrent', 'undervoltage', 'overvoltage', 'frequency'
            pickup_value: Trip threshold
            time_delay_s: Time delay before trip
            enabled: Function enabled
            user: User making the configuration change
        """
        self.protection_functions[function_type] = ProtectionFunction(
            function_type=function_type,
            enabled=enabled,
            pickup_value=pickup_value,
            time_delay_s=time_delay_s,
        )

        self._trip_timers[function_type] = 0.0

        # Log configuration change as audit event
        await self.logger.log_audit(
            message=f"Protection function configured on IED '{self.device_name}': {function_type}",
            user=user,
            action="protection_config",
            data={
                "function_type": function_type,
                "pickup_value": pickup_value,
                "time_delay_s": time_delay_s,
                "enabled": enabled,
            },
        )

        self.logger.info(
            f"Protection function added: {function_type}, "
            f"pickup={pickup_value}, delay={time_delay_s}s"
        )

    # ----------------------------------------------------------------
    # Scan cycle
    # ----------------------------------------------------------------

    async def _scan_cycle(self) -> None:
        """Main protection scan cycle."""
        self.logger.info(f"Protection scan started for {self.device_name}")

        while self._running:
            current_time = self.sim_time.now()
            dt = current_time - self._last_scan_time

            try:
                # Read measurements (from grid physics if available)
                await self._update_measurements()

                # Execute protection logic
                await self._execute_protection_logic(dt)

                # Publish GOOSE if state changed
                if self.goose_enabled and self.tripped:
                    await self._publish_goose_trip()

                # Check alarm conditions
                await self._check_alarm_conditions()

                # Sync to DataStore
                await self._sync_to_datastore()

            except Exception as e:
                self.logger.error(
                    f"Error in protection scan for {self.device_name}: {e}"
                )

            self._last_scan_time = current_time
            await asyncio.sleep(self.scan_interval)

    async def _update_measurements(self) -> None:
        """
        Update electrical measurements.

        In a full implementation, this would read from GridPhysics or
        substations via DataStore. For now, simulated.
        """
        # TODO: Read from grid physics
        # measurements = await self.data_store.read_memory("substation_1", "measurements")

        # For now, maintain current values (set externally or from physics integration)
        pass

    async def _execute_protection_logic(self, dt: float) -> None:
        """Execute all enabled protection functions."""
        if self.tripped:
            return  # Already tripped, lockout

        for func_type, func in self.protection_functions.items():
            if not func.enabled:
                continue

            # Check condition
            condition_met = False

            if func_type == "overcurrent":
                condition_met = self.measurements.current_a > func.pickup_value

            elif func_type == "undervoltage":
                condition_met = self.measurements.voltage_v < func.pickup_value

            elif func_type == "overvoltage":
                condition_met = self.measurements.voltage_v > func.pickup_value

            elif func_type == "underfrequency":
                condition_met = self.measurements.frequency_hz < func.pickup_value

            elif func_type == "overfrequency":
                condition_met = self.measurements.frequency_hz > func.pickup_value

            # Handle time delay
            if condition_met:
                self._trip_timers[func_type] += dt

                if self._trip_timers[func_type] >= func.time_delay_s:
                    # Trip!
                    await self._trip(func_type)
                    func.trip_count += 1
                    func.last_trip_time = self.sim_time.now()
            else:
                # Reset timer
                self._trip_timers[func_type] = 0.0

    async def _trip(self, reason: str) -> None:
        """Execute protection trip."""
        self.tripped = True
        self.trip_reason = reason

        # Log protection trip as CRITICAL alarm
        await self.logger.log_alarm(
            message=f"PROTECTION TRIP on IED '{self.device_name}': {reason}",
            priority=AlarmPriority.CRITICAL,
            state=AlarmState.ACTIVE,
            device=self.device_name,
            data={
                "trip_reason": reason,
                "current_a": self.measurements.current_a,
                "voltage_v": self.measurements.voltage_v,
                "frequency_hz": self.measurements.frequency_hz,
            },
        )

        self.logger.warning(
            f"PROTECTION TRIP: {self.device_name} - {reason} "
            f"(I={self.measurements.current_a}A, V={self.measurements.voltage_v}V, "
            f"f={self.measurements.frequency_hz}Hz)"
        )

    async def _publish_goose_trip(self) -> None:
        """Publish IEC 61850 GOOSE trip message."""
        goose_msg = {
            "ied_name": self.ied_name,
            "timestamp": self.sim_time.now(),
            "trip": self.tripped,
            "trip_reason": self.trip_reason,
            "measurements": {
                "current_a": self.measurements.current_a,
                "voltage_v": self.measurements.voltage_v,
                "frequency_hz": self.measurements.frequency_hz,
            },
        }

        self.goose_messages.append(goose_msg)

        # Log GOOSE message as security event (can be spoofed)
        await self.logger.log_security(
            message=f"GOOSE trip message published from IED '{self.device_name}'",
            severity=EventSeverity.CRITICAL,
            data={
                "ied_name": self.ied_name,
                "trip_reason": self.trip_reason,
                "protocol": "iec61850_goose",
            },
        )

        self.logger.info(f"GOOSE trip message published: {self.device_name}")

    async def _check_alarm_conditions(self) -> None:
        """Check and raise/clear alarms for protection events."""
        # Trip alarm
        if self.tripped and not self.trip_alarm_raised:
            self.trip_alarm_raised = True
            # Alarm already raised in _trip() method

        elif not self.tripped and self.trip_alarm_raised:
            await self.logger.log_alarm(
                message=f"Protection trip cleared on IED '{self.device_name}'",
                priority=AlarmPriority.CRITICAL,
                state=AlarmState.CLEARED,
                device=self.device_name,
                data={"previous_trip_reason": self.trip_reason},
            )
            self.trip_alarm_raised = False

        # Repeated trip alarm (>3 trips)
        total_trips = sum(
            func.trip_count for func in self.protection_functions.values()
        )
        if total_trips > 3 and not self.repeated_trip_alarm_raised:
            await self.logger.log_alarm(
                message=f"Repeated protection trips on IED '{self.device_name}': {total_trips} total trips",
                priority=AlarmPriority.HIGH,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={
                    "total_trips": total_trips,
                    "function_trip_counts": {
                        func_type: func.trip_count
                        for func_type, func in self.protection_functions.items()
                    },
                },
            )
            self.repeated_trip_alarm_raised = True

    # ----------------------------------------------------------------
    # Public interface
    # ----------------------------------------------------------------

    def set_measurements(
        self,
        voltage_v: float | None = None,
        current_a: float | None = None,
        frequency_hz: float | None = None,
    ) -> None:
        """Update measurements (for simulation or grid integration)."""
        if voltage_v is not None:
            self.measurements.voltage_v = voltage_v

        if current_a is not None:
            self.measurements.current_a = current_a

        if frequency_hz is not None:
            self.measurements.frequency_hz = frequency_hz

    async def reset_trip(self, user: str = "operator") -> None:
        """Reset protection trip (manual reset)."""
        if self.tripped:
            # Log trip reset as audit event
            await self.logger.log_audit(
                message=f"Protection trip reset on IED '{self.device_name}' by {user}",
                user=user,
                action="trip_reset",
                data={
                    "device": self.device_name,
                    "previous_trip_reason": self.trip_reason,
                },
            )

            self.logger.info(f"Trip reset: {self.device_name}")
            self.tripped = False
            self.trip_reason = ""

            # Reset all timers
            for func_type in self._trip_timers:
                self._trip_timers[func_type] = 0.0

    async def _sync_to_datastore(self) -> None:
        """Synchronise IED data to DataStore."""
        memory_map = {
            "ied_name": self.ied_name,
            "tripped": self.tripped,
            "trip_reason": self.trip_reason,
            "measurements": {
                "voltage_v": self.measurements.voltage_v,
                "current_a": self.measurements.current_a,
                "frequency_hz": self.measurements.frequency_hz,
                "active_power_kw": self.measurements.active_power_kw,
                "reactive_power_kvar": self.measurements.reactive_power_kvar,
                "power_factor": self.measurements.power_factor,
            },
            "protection_functions": {
                name: {
                    "enabled": func.enabled,
                    "pickup_value": func.pickup_value,
                    "time_delay_s": func.time_delay_s,
                    "trip_count": func.trip_count,
                }
                for name, func in self.protection_functions.items()
            },
            "goose_messages": self.goose_messages[-10:],  # Last 10 messages
        }

        await self.data_store.bulk_write_memory(self.device_name, memory_map)

    async def get_telemetry(self) -> dict[str, Any]:
        """Get IED telemetry."""
        return {
            "device_name": self.device_name,
            "device_type": "ied",
            "ied_name": self.ied_name,
            "tripped": self.tripped,
            "trip_reason": self.trip_reason,
            "measurements": {
                "voltage_v": self.measurements.voltage_v,
                "current_a": self.measurements.current_a,
                "frequency_hz": self.measurements.frequency_hz,
                "active_power_kw": self.measurements.active_power_kw,
                "reactive_power_kvar": self.measurements.reactive_power_kvar,
                "power_factor": self.measurements.power_factor,
            },
            "protection_functions": {
                name: {
                    "enabled": func.enabled,
                    "pickup_value": func.pickup_value,
                    "trip_count": func.trip_count,
                }
                for name, func in self.protection_functions.items()
            },
            "goose_enabled": self.goose_enabled,
            "mms_enabled": self.mms_enabled,
        }
