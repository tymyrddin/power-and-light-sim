# components/security/logging_system.py
"""
Structured logging system for ICS simulator.

Provides:
- Structured logging (JSON, syslog, plain text formats)
- Audit trail management
- Alarm and event classification
- Log rotation and retention
- Security event logging
- Integration with SimulationTime and DataStore

ICS-specific features:
- Event severity levels (IEC 62443)
- Alarm priorities
- Correlation IDs for tracing
- Device/system context
- Protocol-specific logging
"""

import asyncio
import json
import logging
import logging.handlers
import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime

__all__ = [
    "EventSeverity",
    "EventCategory",
    "AlarmPriority",
    "AlarmState",
    "LogEntry",
    "SimTimeFormatter",
    "JSONFormatter",
    "ICSLogger",
    "configure_logging",
    "get_logger",
]

# ----------------------------------------------------------------
# ICS Event Classification
# ----------------------------------------------------------------


class EventSeverity(Enum):
    """
    ICS event severity levels (aligned with IEC 62443).

    Lower number = higher severity
    """

    CRITICAL = 1  # Safety system failure, process shutdown
    ALERT = 2  # Immediate action required
    ERROR = 3  # Error conditions, degraded operation
    WARNING = 4  # Warning conditions, potential issues
    NOTICE = 5  # Normal but significant events
    INFO = 6  # Informational messages
    DEBUG = 7  # Debug/diagnostic information


class EventCategory(Enum):
    """ICS event categories."""

    SECURITY = "security"  # Security-related events
    SAFETY = "safety"  # Safety system events
    PROCESS = "process"  # Process control events
    ALARM = "alarm"  # Alarm conditions
    AUDIT = "audit"  # Audit trail events
    SYSTEM = "system"  # System/infrastructure events
    COMMUNICATION = "communication"  # Network/protocol events
    DIAGNOSTIC = "diagnostic"  # Diagnostic/maintenance events


class AlarmPriority(Enum):
    """Alarm priority levels (ISA 18.2)."""

    CRITICAL = 1  # Life-threatening or major equipment damage
    HIGH = 2  # Significant impact on safety/production
    MEDIUM = 3  # Moderate impact
    LOW = 4  # Minor impact, for awareness


class AlarmState(Enum):
    """Alarm states per ISA 18.2."""

    ACTIVE = "ACTIVE"  # Alarm condition present
    ACKNOWLEDGED = "ACKNOWLEDGED"  # Operator acknowledged
    CLEARED = "CLEARED"  # Alarm condition no longer present
    SUPPRESSED = "SUPPRESSED"  # Temporarily suppressed


# Map Python logging levels to ICS severity
LOGGING_TO_SEVERITY = {
    logging.CRITICAL: EventSeverity.CRITICAL,
    logging.ERROR: EventSeverity.ERROR,
    logging.WARNING: EventSeverity.WARNING,
    logging.INFO: EventSeverity.INFO,
    logging.DEBUG: EventSeverity.DEBUG,
}


# ----------------------------------------------------------------
# Structured Log Entry
# ----------------------------------------------------------------


@dataclass
class LogEntry:
    """Structured log entry for ICS events."""

    simulation_time: float  # Simulation time when event occurred
    wall_time: float  # Wall clock time
    severity: EventSeverity
    category: EventCategory
    message: str

    # Context
    device: str = ""  # Device name
    component: str = ""  # Component/subsystem
    user: str = ""  # User if applicable

    # Technical details
    event_id: str = ""  # Unique event identifier
    correlation_id: str = ""  # For tracing related events
    source_ip: str = ""  # Network source

    # Additional data
    data: dict[str, Any] = field(default_factory=dict)

    # Alarm-specific
    alarm_priority: AlarmPriority | None = None
    alarm_state: AlarmState | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialisation."""
        entry_dict = {
            "simulation_time": self.simulation_time,
            "wall_time": self.wall_time,
            "severity": self.severity.name,
            "category": self.category.value,
            "message": self.message,
        }

        # Add optional fields if present
        if self.device:
            entry_dict["device"] = self.device
        if self.component:
            entry_dict["component"] = self.component
        if self.user:
            entry_dict["user"] = self.user
        if self.event_id:
            entry_dict["event_id"] = self.event_id
        if self.correlation_id:
            entry_dict["correlation_id"] = self.correlation_id
        if self.source_ip:
            entry_dict["source_ip"] = self.source_ip
        if self.data:
            # Convert data dict to JSON string for type compatibility
            entry_dict["data"] = json.dumps(self.data)
        if self.alarm_priority:
            entry_dict["alarm_priority"] = self.alarm_priority.name
        if self.alarm_state:
            entry_dict["alarm_state"] = self.alarm_state.value

        return entry_dict

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    def to_human_readable(self) -> str:
        """Convert to human-readable format."""
        sim_time_str = f"[SIM:{self.simulation_time:10.2f}s]"
        severity_str = f"[{self.severity.name:8s}]"
        device_str = f"{self.device}:" if self.device else ""
        component_str = f"{self.component}:" if self.component else ""

        return (
            f"{sim_time_str} {severity_str} {device_str}{component_str} {self.message}"
        )


# ----------------------------------------------------------------
# JSON Formatter for Python logging (with SimulationTime)
# ----------------------------------------------------------------


class SimTimeFormatter(logging.Formatter):
    """Format log records with simulation time prefix."""

    def __init__(self, sim_time: SimulationTime):
        super().__init__(
            fmt="[SIM:%(sim_time)8.2fs] [%(levelname)8s] %(name)s: %(message)s"
        )
        self.sim_time = sim_time

    def format(self, record: logging.LogRecord) -> str:
        """Format with simulation time."""
        record.sim_time = self.sim_time.now()
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """Format log records as JSON with simulation time."""

    def __init__(self, device: str = ""):
        super().__init__()
        self.device = device
        self.sim_time = SimulationTime()

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        severity = LOGGING_TO_SEVERITY.get(record.levelno, EventSeverity.INFO)

        log_entry = LogEntry(
            simulation_time=self.sim_time.now(),
            wall_time=record.created,
            severity=severity,
            category=EventCategory.SYSTEM,  # Default
            message=record.getMessage(),
            device=self.device,
            component=record.name,
        )

        # Add exception info if present
        if record.exc_info:
            log_entry.data["exception"] = self.formatException(record.exc_info)

        return log_entry.to_json()


# ----------------------------------------------------------------
# ICS Logger - Enhanced logging with structured output
# ----------------------------------------------------------------


class ICSLogger:
    """
    Enhanced logger for ICS devices.

    Wraps Python's logging with ICS-specific features:
    - Structured logging (JSON, syslog)
    - Event classification
    - Audit trail support
    - Alarm logging
    - SimulationTime integration
    - DataStore integration (optional)
    """

    def __init__(
        self,
        name: str,
        device: str = "",
        log_dir: Path | None = None,
        enable_json: bool = True,
        enable_console: bool = True,
        data_store: DataStore | None = None,
        max_audit_entries: int = 10000,
    ):
        """
        Initialise ICS logger.

        Args:
            name: Logger name (typically module name)
            device: Device name for context
            log_dir: Directory for log files (None = no file logging)
            enable_json: Enable JSON formatted logs (requires log_dir)
            enable_console: Enable console output
            data_store: Optional DataStore for centralised logging
            max_audit_entries: Maximum audit trail entries to retain
        """
        self.name = name
        self.device = device
        self.log_dir = log_dir
        self.data_store = data_store

        # Simulation time integration
        self.sim_time = SimulationTime()

        # Create Python logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False  # Don't propagate to root logger

        # Remove existing handlers
        self.logger.handlers.clear()

        # Add handlers based on configuration
        if enable_console:
            self._add_console_handler()

        if enable_json and log_dir:
            self._add_json_handler()

        # Audit trail storage (in-memory)
        self.audit_trail: list[LogEntry] = []
        self._audit_lock = asyncio.Lock()
        self._max_audit_entries = max_audit_entries

    def _add_console_handler(self) -> None:
        """Add console handler with simulation time."""
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(SimTimeFormatter(self.sim_time))
        self.logger.addHandler(handler)

    def _add_json_handler(self) -> None:
        """Add JSON file handler with rotation."""
        if not self.log_dir:
            return

        self.log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self.log_dir / f"{self.device or 'system'}.json.log"

        # Rotating file handler (10MB max, 5 backups)
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
        )
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(JSONFormatter(device=self.device))
        self.logger.addHandler(handler)

    # ----------------------------------------------------------------
    # Standard logging methods
    # ----------------------------------------------------------------

    def debug(self, message: str, **kwargs) -> None:
        """Log debug message."""
        self.logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs) -> None:
        """Log info message."""
        self.logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs) -> None:
        """Log warning message."""
        self.logger.warning(message, **kwargs)

    def error(self, message: str, **kwargs) -> None:
        """Log error message."""
        self.logger.error(message, **kwargs)

    def critical(self, message: str, **kwargs) -> None:
        """Log critical message."""
        self.logger.critical(message, **kwargs)

    def exception(self, message: str, **kwargs) -> None:
        """Log exception with traceback."""
        self.logger.exception(message, **kwargs)

    # ----------------------------------------------------------------
    # ICS-specific logging methods
    # ----------------------------------------------------------------

    async def log_event(
        self,
        severity: EventSeverity,
        category: EventCategory,
        message: str,
        store_in_datastore: bool = False,
        **kwargs,
    ) -> LogEntry:
        """
        Log structured ICS event.

        Args:
            severity: Event severity level
            category: Event category
            message: Event message
            store_in_datastore: Store in DataStore for centralised access
            **kwargs: Additional context (user, component, data, etc.)

        Returns:
            LogEntry that was created
        """
        # Allow kwargs to override default device
        device = kwargs.pop("device", self.device)

        entry = LogEntry(
            simulation_time=self.sim_time.now(),
            wall_time=self.sim_time.wall_elapsed(),
            severity=severity,
            category=category,
            message=message,
            device=device,
            **kwargs,
        )

        # Log to Python logger
        level_map = {
            EventSeverity.CRITICAL: logging.CRITICAL,
            EventSeverity.ALERT: logging.CRITICAL,
            EventSeverity.ERROR: logging.ERROR,
            EventSeverity.WARNING: logging.WARNING,
            EventSeverity.NOTICE: logging.INFO,
            EventSeverity.INFO: logging.INFO,
            EventSeverity.DEBUG: logging.DEBUG,
        }
        log_level = level_map.get(severity, logging.INFO)
        self.logger.log(log_level, entry.to_human_readable())

        # Store in audit trail if audit category
        if category == EventCategory.AUDIT or category == EventCategory.SECURITY:
            async with self._audit_lock:
                self.audit_trail.append(entry)
                # Trim if too long
                if len(self.audit_trail) > self._max_audit_entries:
                    self.audit_trail = self.audit_trail[-self._max_audit_entries :]

        # Store in DataStore if requested
        if store_in_datastore and self.data_store:
            await self._store_in_datastore(entry)

        return entry

    async def _store_in_datastore(self, entry: LogEntry) -> None:
        """Store log entry in DataStore for centralised access."""
        try:
            # Store in central audit log
            await self.data_store.system_state.append_audit_event(
                entry.to_dict()
            )
        except Exception:
            self.logger.exception("Failed to store log in central audit log")

    async def log_audit(
        self, message: str, user: str = "", action: str = "", result: str = "", **kwargs
    ) -> LogEntry:
        """
        Log audit trail event.

        Args:
            message: Audit message
            user: User who performed action
            action: Action performed
            result: Result of action (ALLOWED, DENIED, etc.)
            **kwargs: Additional context

        Returns:
            LogEntry that was created
        """
        data = kwargs.get("data", {})
        data.update(
            {
                "action": action,
                "result": result,
            }
        )
        kwargs["data"] = data

        return await self.log_event(
            severity=EventSeverity.NOTICE,
            category=EventCategory.AUDIT,
            message=message,
            user=user,
            store_in_datastore=True,  # Always store audit events
            **kwargs,
        )

    async def log_alarm(
        self,
        message: str,
        priority: AlarmPriority,
        state: AlarmState = AlarmState.ACTIVE,
        **kwargs,
    ) -> LogEntry:
        """
        Log alarm event.

        Args:
            message: Alarm message
            priority: Alarm priority
            state: Alarm state
            **kwargs: Additional context

        Returns:
            LogEntry that was created
        """
        # Map alarm priority to severity
        severity_map = {
            AlarmPriority.CRITICAL: EventSeverity.CRITICAL,
            AlarmPriority.HIGH: EventSeverity.ALERT,
            AlarmPriority.MEDIUM: EventSeverity.WARNING,
            AlarmPriority.LOW: EventSeverity.NOTICE,
        }
        severity = severity_map.get(priority, EventSeverity.WARNING)

        return await self.log_event(
            severity=severity,
            category=EventCategory.ALARM,
            message=message,
            alarm_priority=priority,
            alarm_state=state,
            store_in_datastore=True,  # Always store alarms
            **kwargs,
        )

    async def log_security(
        self, message: str, severity: EventSeverity = EventSeverity.WARNING, **kwargs
    ) -> LogEntry:
        """
        Log security event.

        Args:
            message: Security event message
            severity: Event severity
            **kwargs: Additional context

        Returns:
            LogEntry that was created
        """
        return await self.log_event(
            severity=severity,
            category=EventCategory.SECURITY,
            message=message,
            store_in_datastore=True,  # Always store security events
            **kwargs,
        )

    # ----------------------------------------------------------------
    # Audit trail access
    # ----------------------------------------------------------------

    async def get_audit_trail(
        self,
        limit: int = 100,
        severity: EventSeverity | None = None,
        category: EventCategory | None = None,
    ) -> list[LogEntry]:
        """
        Get audit trail entries.

        Args:
            limit: Maximum number of entries to return
            severity: Filter by severity
            category: Filter by category

        Returns:
            List of log entries (most recent last)
        """
        async with self._audit_lock:
            entries = self.audit_trail

            # Apply filters first, then limit
            if severity:
                entries = [e for e in entries if e.severity == severity]
            if category:
                entries = [e for e in entries if e.category == category]

            return entries[-limit:]

    async def clear_audit_trail(self) -> int:
        """
        Clear audit trail.

        Returns:
            Number of entries cleared
        """
        async with self._audit_lock:
            count = len(self.audit_trail)
            self.audit_trail.clear()
            return count


# ----------------------------------------------------------------
# Global logger factory
# ----------------------------------------------------------------

_loggers: dict[str, ICSLogger] = {}
_loggers_lock = threading.Lock()
_default_log_dir: Path | None = None
_default_data_store: DataStore | None = None


def configure_logging(
    log_dir: Path | str | None = None,
    data_store: DataStore | None = None,
) -> None:
    """
    Configure global logging settings.

    Args:
        log_dir: Directory for log files
        data_store: DataStore instance for centralised logging
    """
    global _default_log_dir, _default_data_store

    if log_dir:
        _default_log_dir = Path(log_dir)
        _default_log_dir.mkdir(parents=True, exist_ok=True)

    _default_data_store = data_store


def get_logger(name: str, device: str = "", **kwargs) -> ICSLogger:
    """
    Get or create an ICS logger.

    Thread-safe logger factory.

    Args:
        name: Logger name (typically __name__)
        device: Device name for context
        **kwargs: Additional ICSLogger arguments

    Returns:
        ICSLogger instance
    """
    logger_key = f"{name}:{device}"

    with _loggers_lock:
        if logger_key not in _loggers:
            # Use global defaults if not specified
            if "log_dir" not in kwargs and _default_log_dir:
                kwargs["log_dir"] = _default_log_dir
            if "data_store" not in kwargs and _default_data_store:
                kwargs["data_store"] = _default_data_store

            _loggers[logger_key] = ICSLogger(name, device, **kwargs)

        return _loggers[logger_key]
