# components/devices/control_zone/rtu/base_rtu.py
"""
Base class for Remote Telemetry Units (RTUs).

RTUs are specialised field devices that:
- Collect data from remote sensors
- Transmit telemetry to SCADA masters
- Execute simple local control logic
- Support protocols like Modbus RTU, DNP3, IEC 60870-5-104

Unlike PLCs which focus on control logic, RTUs focus on:
- Data acquisition and transmission
- Protocol translation
- Event detection and reporting
- Time-stamped data logging
"""

from abc import abstractmethod
from typing import Any

from components.devices.core.base_device import BaseDevice
from components.state.data_store import DataStore


class BaseRTU(BaseDevice):
    """
    Base class for all RTU devices.

    RTUs bridge between:
    - Field sensors/actuators
    - SCADA master stations

    Key differences from PLCs:
    - Focus on data collection vs. control logic
    - Event-driven reporting (report-by-exception)
    - Protocol-specific addressing (DNP3 points, IEC104 IOAs)
    - Time synchronisation and timestamping

    Subclasses must implement:
    - _initialise_memory_map(): Define protocol point map
    - _read_inputs(): Poll sensors/field devices
    - _process_data(): Data validation, scaling, alarming
    - _report_to_master(): Send updates to SCADA (if needed)
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        description: str = "",
        scan_interval: float = 1.0,  # RTUs typically scan slower than PLCs (1s)
        report_by_exception: bool = True,
    ):
        """
        Initialise RTU device.

        Args:
            device_name: Unique RTU identifier
            device_id: Protocol-specific address (DNP3 address, IEC104 common address, etc.)
            data_store: Reference to DataStore
            description: RTU description
            scan_interval: Data acquisition cycle time in seconds
            report_by_exception: Only report changes vs. periodic polling
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
        )

        self.report_by_exception = report_by_exception

        # RTU-specific state
        # Note: BaseDevice.metadata["scan_count"] tracks poll count
        self.event_count = 0  # RTU-specific: number of events detected
        self.last_report_time = 0.0  # RTU-specific: last report to master

        # Event detection (for report-by-exception)
        self.previous_values: dict[str, Any] = {}
        self.deadbands: dict[str, float] = {}  # Analogue deadbands

        self.logger.info(
            f"BaseRTU '{device_name}' initialised "
            f"(report-by-exception: {report_by_exception})"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return 'rtu' as base type (override for specific types like 'substation_rtu')."""
        return "rtu"

    async def _scan_cycle(self) -> None:
        """
        Execute RTU data acquisition cycle.

        Order of operations:
        1. Read inputs from field devices/sensors
        2. Process data (scaling, validation, alarming)
        3. Detect events (if report-by-exception)
        4. Report to SCADA master (if needed)

        Note: BaseDevice._scan_loop() already handles:
        - Incrementing scan_count (our poll count)
        - Updating last_scan_time
        - Incrementing error_count on exceptions
        - Writing memory_map to DataStore
        """
        # Read field data
        await self._read_inputs()

        # Process and validate
        await self._process_data()

        # Detect changes for event reporting
        events_detected = self._detect_events()

        # Report to master if needed
        if events_detected or not self.report_by_exception:
            await self._report_to_master()
            self.last_report_time = self.sim_time.now()

        # BaseDevice handles scan_count increment automatically
        # We only track RTU-specific event_count

    # ----------------------------------------------------------------
    # Abstract methods for RTU cycle - must be implemented
    # ----------------------------------------------------------------

    @abstractmethod
    async def _read_inputs(self) -> None:
        """
        Read inputs from field devices.

        Typically:
        - Poll sensors via local I/O
        - Read from physics engines
        - Update point values in memory map
        """
        pass

    @abstractmethod
    async def _process_data(self) -> None:
        """
        Process acquired data.

        Typically:
        - Scale raw values to engineering units
        - Validate data quality
        - Check alarm limits
        - Update timestamps
        """
        pass

    @abstractmethod
    async def _report_to_master(self) -> None:
        """
        Report data to SCADA master.

        Typically:
        - Format data per protocol (DNP3, IEC104, Modbus)
        - Send unsolicited responses or wait for poll
        - Update communications statistics
        """
        pass

    # ----------------------------------------------------------------
    # Event detection (for report-by-exception)
    # ----------------------------------------------------------------

    def _detect_events(self) -> bool:
        """
        Detect significant changes in data values.

        Returns:
            True if any events detected
        """
        if not self.report_by_exception:
            return True  # Always report in polling mode

        events = False

        for key, current_value in self.memory_map.items():
            # Skip internal diagnostics
            if key.startswith("_"):
                continue

            previous_value = self.previous_values.get(key)

            # Digital points - report on change
            if isinstance(current_value, bool):
                if current_value != previous_value:
                    events = True
                    self.event_count += 1
                    self.logger.debug(
                        f"RTU '{self.device_name}': Digital event on {key}: "
                        f"{previous_value} → {current_value}"
                    )

            # Analogue points - report if exceeds deadband
            elif isinstance(current_value, (int, float)):
                if previous_value is not None:
                    deadband = self.deadbands.get(key, 0.0)
                    if abs(current_value - previous_value) > deadband:
                        events = True
                        self.event_count += 1
                        self.logger.debug(
                            f"RTU '{self.device_name}': Analogue event on {key}: "
                            f"{previous_value} → {current_value} (deadband: {deadband})"
                        )

            # Store current value for next comparison
            self.previous_values[key] = current_value

        return events

    def set_deadband(self, point: str, deadband: float) -> None:
        """
        Set analogue deadband for a point.

        Args:
            point: Point name/address
            deadband: Minimum change to trigger event
        """
        self.deadbands[point] = deadband
        self.logger.debug(f"RTU '{self.device_name}': Set deadband {point} = {deadband}")

    # ----------------------------------------------------------------
    # RTU status and diagnostics
    # ----------------------------------------------------------------

    async def get_rtu_status(self) -> dict[str, Any]:
        """Get RTU-specific status information."""
        base_status = await self.get_status()
        rtu_status = {
            **base_status,
            # base_status already includes scan_count (our poll count)
            "event_count": self.event_count,
            "last_report_time": self.last_report_time,
            "report_by_exception": self.report_by_exception,
            "active_deadbands": len(self.deadbands),
        }
        return rtu_status

    def reset_event_count(self) -> None:
        """Reset RTU event counter."""
        self.event_count = 0
        self.logger.info(f"RTU '{self.device_name}' event counter reset")
