# components/security/anomaly_detector.py
"""
Anomaly detection system for ICS simulator.

Provides:
- Behaviour baseline learning
- Statistical anomaly detection
- Protocol anomaly detection
- Process anomaly detection
- Integration with IDS/SIEM systems

Integrations:
- SimulationTime: Time-series analysis and pattern detection
- DataStore: Store baselines and anomaly history
- SystemState: Monitor system-wide patterns
- ConfigLoader: Load detection thresholds from YAML

ICS-specific features:
- Process value range violations
- Communication pattern anomalies
- Control logic anomalies
- Time-series forecasting
- Alarm flood detection
"""

import asyncio
import json
import statistics
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from components.security.logging_system import (
    EventCategory,
    EventSeverity,
    ICSLogger,
    get_logger,
)
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime
from config.config_loader import ConfigLoader

__all__ = [
    "AnomalyType",
    "AnomalySeverity",
    "AnomalyEvent",
    "StatisticalBaseline",
    "AnomalyDetector",
]

# ----------------------------------------------------------------
# Anomaly Classification
# ----------------------------------------------------------------


class AnomalyType(Enum):
    """Types of anomalies detected."""

    STATISTICAL = "statistical"  # Value outside statistical bounds
    RANGE = "range"  # Value outside allowed range
    RATE_OF_CHANGE = "rate_of_change"  # Value changing too fast
    PATTERN = "pattern"  # Unexpected pattern/sequence
    PROTOCOL = "protocol"  # Protocol violation
    COMMUNICATION = "communication"  # Network/comms anomaly
    ALARM_FLOOD = "alarm_flood"  # Excessive alarms
    CONTROL_LOGIC = "control_logic"  # Unexpected control behaviour


class AnomalySeverity(Enum):
    """Severity of detected anomaly."""

    LOW = 1  # Minor deviation, informational
    MEDIUM = 2  # Moderate deviation, investigate
    HIGH = 3  # Significant deviation, likely issue
    CRITICAL = 4  # Severe deviation, immediate action


# Map AnomalySeverity to EventSeverity for ICS logging
ANOMALY_TO_EVENT_SEVERITY = {
    AnomalySeverity.LOW: EventSeverity.NOTICE,
    AnomalySeverity.MEDIUM: EventSeverity.WARNING,
    AnomalySeverity.HIGH: EventSeverity.ALERT,
    AnomalySeverity.CRITICAL: EventSeverity.CRITICAL,
}


# ----------------------------------------------------------------
# Anomaly Event
# ----------------------------------------------------------------


@dataclass
class AnomalyEvent:
    """Detected anomaly event."""

    timestamp: float  # Simulation time when detected
    anomaly_type: AnomalyType
    severity: AnomalySeverity

    # Context
    device: str
    parameter: str

    # Details
    observed_value: Any
    expected_value: Any | None = None
    baseline_mean: float | None = None
    baseline_std: float | None = None
    deviation_magnitude: float | None = None

    # Description
    description: str = ""

    # Additional data
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "timestamp": self.timestamp,
            "anomaly_type": self.anomaly_type.value,
            "severity": self.severity.value,
            "device": self.device,
            "parameter": self.parameter,
            "observed_value": str(self.observed_value),
            "expected_value": (
                str(self.expected_value) if self.expected_value is not None else None
            ),
            "baseline_mean": self.baseline_mean,
            "baseline_std": self.baseline_std,
            "deviation_magnitude": self.deviation_magnitude,
            "description": self.description,
            "data": self.data,
        }


# ----------------------------------------------------------------
# Statistical Baseline
# ----------------------------------------------------------------


@dataclass
class StatisticalBaseline:
    """Statistical baseline for a parameter."""

    parameter: str
    device: str

    # Statistical measures
    mean: float = 0.0
    std: float = 0.0
    min_value: float = float("inf")
    max_value: float = float("-inf")

    # Learning
    sample_count: int = 0
    learning_window: int = 1000  # Number of samples for baseline
    is_learned: bool = False

    # History (for online learning)
    _values: deque = field(default_factory=lambda: deque(maxlen=1000))

    def update(self, value: float) -> None:
        """Update baseline with new value."""
        self._values.append(value)
        self.sample_count += 1

        # Update min/max
        self.min_value = min(self.min_value, value)
        self.max_value = max(self.max_value, value)

        # Recalculate statistics if enough samples
        if len(self._values) >= min(100, self.learning_window):
            self.mean = statistics.mean(self._values)
            if len(self._values) > 1:
                self.std = statistics.stdev(self._values)

            # Mark as learned when window is full
            if len(self._values) >= self.learning_window:
                self.is_learned = True

    def is_anomalous(self, value: float, sigma_threshold: float = 3.0) -> bool:
        """
        Check if value is anomalous (beyond sigma threshold).

        Args:
            value: Value to check
            sigma_threshold: Number of standard deviations

        Returns:
            True if anomalous
        """
        if not self.is_learned or self.std == 0:
            return False

        deviation = abs(value - self.mean)
        return deviation > (sigma_threshold * self.std)

    def get_deviation_magnitude(self, value: float) -> float:
        """
        Get deviation in terms of standard deviations.

        Args:
            value: Value to check

        Returns:
            Number of standard deviations from mean
        """
        if self.std == 0:
            return 0.0
        return abs(value - self.mean) / self.std


# ----------------------------------------------------------------
# Anomaly Detector
# ----------------------------------------------------------------


class AnomalyDetector:
    """
    Multi-method anomaly detection for ICS systems.

    Integrates with:
    - SimulationTime: Time-series analysis
    - DataStore: Read device telemetry
    - SystemState: Monitor system-wide patterns
    - ConfigLoader: Load detection thresholds
    - ICSLogger: Security event logging
    """

    def __init__(
        self,
        data_store: DataStore,
        system_state: SystemState,
    ):
        """
        Initialise anomaly detector.

        Args:
            data_store: DataStore for reading telemetry
            system_state: SystemState for system-wide monitoring
        """
        self.data_store = data_store
        self.system_state = system_state
        self.sim_time = SimulationTime()
        self.logger: ICSLogger = get_logger(__name__, device="anomaly_detector")

        # Configuration
        self.config = ConfigLoader().load_all()
        self._load_config()

        # Baselines (protected by _lock)
        self.baselines: dict[tuple[str, str], StatisticalBaseline] = {}

        # Anomaly history
        self.anomalies: deque[AnomalyEvent] = deque(maxlen=10000)

        # Range limits (from configuration)
        self.range_limits: dict[tuple[str, str], tuple[float, float]] = {}

        # Rate of change limits
        self.roc_limits: dict[tuple[str, str], float] = {}

        # Last values (for rate of change detection)
        self.last_values: dict[tuple[str, str], tuple[float, float]] = (
            {}
        )  # (value, timestamp)

        # Alarm flood detection
        self.alarm_counts: dict[str, deque] = {}  # device -> timestamps

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Detection enabled flag
        self.enabled = True

        self.logger.info("AnomalyDetector initialised")

    def _load_config(self) -> None:
        """Load configuration from YAML."""
        anomaly_cfg = self.config.get("simulation", {}).get("anomaly_detection", {})

        # Detection thresholds
        self.sigma_threshold = anomaly_cfg.get("sigma_threshold", 3.0)
        self.learning_window = anomaly_cfg.get("learning_window", 1000)

        # Alarm flood detection
        self.alarm_flood_threshold = anomaly_cfg.get(
            "alarm_flood_threshold", 10
        )  # alarms per minute
        self.alarm_flood_window = anomaly_cfg.get("alarm_flood_window", 60.0)  # seconds

        # Enable/disable
        self.enabled = anomaly_cfg.get("enabled", True)

    async def _log_anomaly(self, anomaly: AnomalyEvent) -> None:
        """Log anomaly to ICS logging system."""
        event_severity = ANOMALY_TO_EVENT_SEVERITY.get(
            anomaly.severity, EventSeverity.WARNING
        )

        await self.logger.log_event(
            severity=event_severity,
            category=EventCategory.SECURITY,
            message=anomaly.description,
            device=anomaly.device,
            component="anomaly_detector",
            data={
                "anomaly_type": anomaly.anomaly_type.value,
                "parameter": anomaly.parameter,
                "observed_value": str(anomaly.observed_value),
                "expected_value": str(anomaly.expected_value),
                "deviation_magnitude": anomaly.deviation_magnitude,
                **anomaly.data,
            },
            store_in_datastore=True,
        )

    # ----------------------------------------------------------------
    # Baseline Management
    # ----------------------------------------------------------------

    async def add_baseline(
        self,
        device: str,
        parameter: str,
        learning_window: int | None = None,
    ) -> None:
        """
        Add parameter to baseline monitoring.

        Args:
            device: Device name
            parameter: Parameter name
            learning_window: Number of samples for learning (None = use default)
        """
        key = (device, parameter)
        async with self._lock:
            if key not in self.baselines:
                baseline = StatisticalBaseline(
                    parameter=parameter,
                    device=device,
                    learning_window=learning_window or self.learning_window,
                )
                self.baselines[key] = baseline
                self.logger.debug(
                    f"Added baseline monitoring for {device}:{parameter}"
                )

    async def set_range_limit(
        self,
        device: str,
        parameter: str,
        min_value: float,
        max_value: float,
    ) -> None:
        """
        Set allowed range for a parameter.

        Args:
            device: Device name
            parameter: Parameter name
            min_value: Minimum allowed value
            max_value: Maximum allowed value
        """
        key = (device, parameter)
        async with self._lock:
            self.range_limits[key] = (min_value, max_value)
        self.logger.debug(
            f"Set range limit for {device}:{parameter}: [{min_value}, {max_value}]"
        )

    async def set_rate_of_change_limit(
        self,
        device: str,
        parameter: str,
        max_rate: float,
    ) -> None:
        """
        Set maximum rate of change for a parameter.

        Args:
            device: Device name
            parameter: Parameter name
            max_rate: Maximum rate of change per second
        """
        key = (device, parameter)
        async with self._lock:
            self.roc_limits[key] = max_rate
        self.logger.debug(
            f"Set rate-of-change limit for {device}:{parameter}: {max_rate}/s"
        )

    # ----------------------------------------------------------------
    # Anomaly Detection Methods
    # ----------------------------------------------------------------

    async def check_value(
        self,
        device: str,
        parameter: str,
        value: float,
    ) -> list[AnomalyEvent]:
        """
        Check a value for anomalies using multiple detection methods.

        Args:
            device: Device name
            parameter: Parameter name
            value: Value to check

        Returns:
            List of detected anomalies (empty if none)
        """
        if not self.enabled:
            return []

        anomalies = []
        key = (device, parameter)
        current_time = self.sim_time.now()

        async with self._lock:
            # 1. Statistical anomaly detection
            if key in self.baselines:
                baseline = self.baselines[key]

                # Update baseline
                baseline.update(value)

                # Check for anomaly (only if learned)
                if baseline.is_learned and baseline.is_anomalous(
                    value, self.sigma_threshold
                ):
                    deviation = baseline.get_deviation_magnitude(value)

                    # Determine severity based on deviation magnitude
                    if deviation > 6.0:
                        severity = AnomalySeverity.CRITICAL
                    elif deviation > 4.0:
                        severity = AnomalySeverity.HIGH
                    elif deviation > 3.0:
                        severity = AnomalySeverity.MEDIUM
                    else:
                        severity = AnomalySeverity.LOW

                    anomaly = AnomalyEvent(
                        timestamp=current_time,
                        anomaly_type=AnomalyType.STATISTICAL,
                        severity=severity,
                        device=device,
                        parameter=parameter,
                        observed_value=value,
                        expected_value=baseline.mean,
                        baseline_mean=baseline.mean,
                        baseline_std=baseline.std,
                        deviation_magnitude=deviation,
                        description=f"{parameter} = {value:.2f} is {deviation:.1f}σ from baseline mean {baseline.mean:.2f}",
                    )
                    anomalies.append(anomaly)

            # 2. Range violation detection
            if key in self.range_limits:
                min_val, max_val = self.range_limits[key]

                if value < min_val or value > max_val:
                    # Determine severity based on how far outside range
                    range_span = max_val - min_val
                    if value < min_val:
                        violation = (min_val - value) / range_span
                    else:
                        violation = (value - max_val) / range_span

                    if violation > 0.5:
                        severity = AnomalySeverity.CRITICAL
                    elif violation > 0.2:
                        severity = AnomalySeverity.HIGH
                    elif violation > 0.1:
                        severity = AnomalySeverity.MEDIUM
                    else:
                        severity = AnomalySeverity.LOW

                    anomaly = AnomalyEvent(
                        timestamp=current_time,
                        anomaly_type=AnomalyType.RANGE,
                        severity=severity,
                        device=device,
                        parameter=parameter,
                        observed_value=value,
                        expected_value=None,
                        description=f"{parameter} = {value:.2f} outside allowed range [{min_val:.2f}, {max_val:.2f}]",
                        data={"min_limit": min_val, "max_limit": max_val},
                    )
                    anomalies.append(anomaly)

            # 3. Rate of change detection
            if key in self.roc_limits:
                if key in self.last_values:
                    last_value, last_time = self.last_values[key]
                    time_delta = current_time - last_time

                    if time_delta > 0:
                        rate = abs(value - last_value) / time_delta
                        max_rate = self.roc_limits[key]

                        if rate > max_rate:
                            severity = (
                                AnomalySeverity.HIGH
                                if rate > (max_rate * 2)
                                else AnomalySeverity.MEDIUM
                            )

                            anomaly = AnomalyEvent(
                                timestamp=current_time,
                                anomaly_type=AnomalyType.RATE_OF_CHANGE,
                                severity=severity,
                                device=device,
                                parameter=parameter,
                                observed_value=value,
                                expected_value=None,
                                description=f"{parameter} rate of change {rate:.2f}/s exceeds limit {max_rate:.2f}/s",
                                data={
                                    "rate": rate,
                                    "max_rate": max_rate,
                                    "time_delta": time_delta,
                                },
                            )
                            anomalies.append(anomaly)

                # Update last value
                self.last_values[key] = (value, current_time)

            # Store anomalies
            for anomaly in anomalies:
                self.anomalies.append(anomaly)

        # Log anomalies outside the lock
        for anomaly in anomalies:
            await self._log_anomaly(anomaly)

        return anomalies

    async def check_alarm_flood(self, device: str) -> AnomalyEvent | None:
        """
        Check for alarm flooding on a device.

        Args:
            device: Device name

        Returns:
            AnomalyEvent if alarm flood detected, None otherwise
        """
        if not self.enabled:
            return None

        current_time = self.sim_time.now()

        async with self._lock:
            # Initialize alarm count for device if needed
            if device not in self.alarm_counts:
                self.alarm_counts[device] = deque()

            # Add current alarm timestamp
            self.alarm_counts[device].append(current_time)

            # Remove old alarms outside the window
            window_start = current_time - self.alarm_flood_window
            while (
                self.alarm_counts[device]
                and self.alarm_counts[device][0] < window_start
            ):
                self.alarm_counts[device].popleft()

            # Check if threshold exceeded
            alarm_count = len(self.alarm_counts[device])
            if alarm_count >= self.alarm_flood_threshold:
                anomaly = AnomalyEvent(
                    timestamp=current_time,
                    anomaly_type=AnomalyType.ALARM_FLOOD,
                    severity=AnomalySeverity.HIGH,
                    device=device,
                    parameter="alarm_rate",
                    observed_value=alarm_count,
                    expected_value=self.alarm_flood_threshold,
                    description=f"Alarm flood detected: {alarm_count} alarms in {self.alarm_flood_window}s",
                    data={
                        "alarm_count": alarm_count,
                        "window_seconds": self.alarm_flood_window,
                        "threshold": self.alarm_flood_threshold,
                    },
                )

                self.anomalies.append(anomaly)

                # Log alarm flood anomaly
                await self._log_anomaly(anomaly)
                return anomaly

        return None

    async def check_communication_pattern(
        self,
        device: str,
        expected_interval: float,
        tolerance: float = 0.2,
    ) -> AnomalyEvent | None:
        """
        Check if device is communicating at expected interval.

        Args:
            device: Device name
            expected_interval: Expected communication interval in seconds
            tolerance: Acceptable deviation (0.2 = ±20%)

        Returns:
            AnomalyEvent if pattern anomaly detected, None otherwise
        """
        if not self.enabled:
            return None

        # Get device state from SystemState
        device_state = await self.system_state.get_device(device)
        if not device_state:
            return None

        current_time = self.sim_time.now()
        last_update_time = (
            device_state.last_update.timestamp() if device_state.last_update else 0
        )

        # Calculate actual interval
        # Note: In real system, would track multiple intervals
        # This is simplified for simulation

        return None  # Placeholder - would need communication history

    # ----------------------------------------------------------------
    # Anomaly Retrieval
    # ----------------------------------------------------------------

    async def get_recent_anomalies(
        self,
        limit: int = 100,
        device: str | None = None,
        severity: AnomalySeverity | None = None,
    ) -> list[AnomalyEvent]:
        """
        Get recent anomalies.

        Args:
            limit: Maximum number to return
            device: Filter by device (None = all devices)
            severity: Filter by severity (None = all severities)

        Returns:
            List of anomaly events (most recent last)
        """
        async with self._lock:
            anomalies = list(self.anomalies)

            # Apply filters first, then limit
            if device:
                anomalies = [a for a in anomalies if a.device == device]
            if severity:
                anomalies = [a for a in anomalies if a.severity == severity]

            return anomalies[-limit:]

    async def get_anomaly_summary(self) -> dict[str, Any]:
        """
        Get summary of detected anomalies.

        Returns:
            Dictionary with anomaly statistics
        """
        async with self._lock:
            total = len(self.anomalies)

            # Count by type
            by_type = {}
            for anomaly in self.anomalies:
                type_name = anomaly.anomaly_type.value
                by_type[type_name] = by_type.get(type_name, 0) + 1

            # Count by severity
            by_severity = {}
            for anomaly in self.anomalies:
                severity_name = anomaly.severity.name
                by_severity[severity_name] = by_severity.get(severity_name, 0) + 1

            # Count by device
            by_device = {}
            for anomaly in self.anomalies:
                by_device[anomaly.device] = by_device.get(anomaly.device, 0) + 1

            return {
                "total_anomalies": total,
                "by_type": by_type,
                "by_severity": by_severity,
                "by_device": by_device,
                "baselines_learned": sum(
                    1 for b in self.baselines.values() if b.is_learned
                ),
                "total_baselines": len(self.baselines),
            }

    async def clear_anomalies(self) -> int:
        """
        Clear anomaly history.

        Returns:
            Number of anomalies cleared
        """
        async with self._lock:
            count = len(self.anomalies)
            self.anomalies.clear()
            return count

    # ----------------------------------------------------------------
    # Baseline Export/Import
    # ----------------------------------------------------------------

    async def export_baselines(self) -> dict[str, Any]:
        """
        Export learned baselines for persistence.

        Returns:
            Dictionary of baselines
        """
        async with self._lock:
            baselines_export = {}
            for (device, parameter), baseline in self.baselines.items():
                if baseline.is_learned:
                    key = f"{device}:{parameter}"
                    baselines_export[key] = {
                        "mean": baseline.mean,
                        "std": baseline.std,
                        "min": baseline.min_value,
                        "max": baseline.max_value,
                        "sample_count": baseline.sample_count,
                    }
            return baselines_export

    async def store_baselines_in_datastore(
        self, device: str = "anomaly_detector"
    ) -> None:
        """
        Store baselines in DataStore for persistence.

        Args:
            device: Device name for storage context
        """
        baselines_data = await self.export_baselines()
        baselines_json = json.dumps(baselines_data)

        await self.data_store.update_metadata(
            device,
            {"baselines": baselines_json},
        )

        self.logger.info(
            f"Stored {len(baselines_data)} baselines to DataStore"
        )
