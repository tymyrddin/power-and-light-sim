# tests/unit/security/test_logging_system.py
"""Comprehensive tests for ICS logging system.

Test Coverage:
- EventSeverity and EventCategory enums
- AlarmPriority and AlarmState enums
- LogEntry dataclass and serialisation
- SimTimeFormatter and JSONFormatter
- ICSLogger core functionality
- Audit trail management
- Logger factory (get_logger, configure_logging)
- Thread safety
"""

import asyncio
import json
import logging
import tempfile
import threading
from pathlib import Path

import pytest

from components.security.logging_system import (
    AlarmPriority,
    AlarmState,
    EventCategory,
    EventSeverity,
    ICSLogger,
    JSONFormatter,
    LogEntry,
    SimTimeFormatter,
    configure_logging,
    get_logger,
)


# ================================================================
# ENUM TESTS
# ================================================================
class TestEventSeverity:
    """Test EventSeverity enum."""

    def test_severity_values_ordered(self):
        """Test that severity values are ordered (lower = more severe).

        WHY: IEC 62443 requires severity ordering for prioritisation.
        """
        assert EventSeverity.CRITICAL.value < EventSeverity.ALERT.value
        assert EventSeverity.ALERT.value < EventSeverity.ERROR.value
        assert EventSeverity.ERROR.value < EventSeverity.WARNING.value
        assert EventSeverity.WARNING.value < EventSeverity.NOTICE.value
        assert EventSeverity.NOTICE.value < EventSeverity.INFO.value
        assert EventSeverity.INFO.value < EventSeverity.DEBUG.value

    def test_all_severities_have_unique_values(self):
        """Test that all severity levels have unique values.

        WHY: Prevents ambiguity in severity comparison.
        """
        values = [s.value for s in EventSeverity]
        assert len(values) == len(set(values))


class TestEventCategory:
    """Test EventCategory enum."""

    def test_security_category_exists(self):
        """Test that SECURITY category exists.

        WHY: Security events must be categorised for audit.
        """
        assert EventCategory.SECURITY.value == "security"

    def test_audit_category_exists(self):
        """Test that AUDIT category exists.

        WHY: Audit trail events need dedicated category.
        """
        assert EventCategory.AUDIT.value == "audit"

    def test_all_ics_categories_present(self):
        """Test all ICS-relevant categories are present.

        WHY: ICS systems need comprehensive event categorisation.
        """
        categories = {c.value for c in EventCategory}
        expected = {
            "security",
            "safety",
            "process",
            "alarm",
            "audit",
            "system",
            "communication",
            "diagnostic",
        }
        assert expected == categories


class TestAlarmPriority:
    """Test AlarmPriority enum."""

    def test_priority_ordering(self):
        """Test alarm priorities are correctly ordered.

        WHY: ISA 18.2 requires priority ordering.
        """
        assert AlarmPriority.CRITICAL.value < AlarmPriority.HIGH.value
        assert AlarmPriority.HIGH.value < AlarmPriority.MEDIUM.value
        assert AlarmPriority.MEDIUM.value < AlarmPriority.LOW.value


class TestAlarmState:
    """Test AlarmState enum."""

    def test_all_states_present(self):
        """Test all ISA 18.2 alarm states are present.

        WHY: Alarm lifecycle requires specific states.
        """
        states = {s.value for s in AlarmState}
        expected = {"ACTIVE", "ACKNOWLEDGED", "CLEARED", "SUPPRESSED"}
        assert expected == states


# ================================================================
# LOG ENTRY TESTS
# ================================================================
class TestLogEntry:
    """Test LogEntry dataclass."""

    def test_create_minimal_entry(self):
        """Test creating entry with minimal required fields.

        WHY: Core functionality - must be able to create entries.
        """
        entry = LogEntry(
            simulation_time=100.0,
            wall_time=1000.0,
            severity=EventSeverity.INFO,
            category=EventCategory.SYSTEM,
            message="Test message",
        )

        assert entry.simulation_time == 100.0
        assert entry.severity == EventSeverity.INFO
        assert entry.message == "Test message"

    def test_create_full_entry(self):
        """Test creating entry with all fields.

        WHY: All fields should be usable.
        """
        entry = LogEntry(
            simulation_time=100.0,
            wall_time=1000.0,
            severity=EventSeverity.WARNING,
            category=EventCategory.SECURITY,
            message="Security event",
            device="plc_1",
            component="auth",
            user="operator1",
            event_id="evt_001",
            correlation_id="corr_001",
            source_ip="192.168.1.10",
            data={"action": "login"},
            alarm_priority=AlarmPriority.HIGH,
            alarm_state=AlarmState.ACTIVE,
        )

        assert entry.device == "plc_1"
        assert entry.user == "operator1"
        assert entry.alarm_priority == AlarmPriority.HIGH
        assert entry.alarm_state == AlarmState.ACTIVE

    def test_to_dict_includes_required_fields(self):
        """Test to_dict includes all required fields.

        WHY: Serialisation must include core data.
        """
        entry = LogEntry(
            simulation_time=100.0,
            wall_time=1000.0,
            severity=EventSeverity.INFO,
            category=EventCategory.SYSTEM,
            message="Test",
        )

        d = entry.to_dict()

        assert "simulation_time" in d
        assert "wall_time" in d
        assert "severity" in d
        assert "category" in d
        assert "message" in d

    def test_to_dict_serialises_enums_as_strings(self):
        """Test that enums are serialised as strings.

        WHY: JSON doesn't support enums natively.
        """
        entry = LogEntry(
            simulation_time=100.0,
            wall_time=1000.0,
            severity=EventSeverity.CRITICAL,
            category=EventCategory.SECURITY,
            message="Test",
            alarm_priority=AlarmPriority.HIGH,
            alarm_state=AlarmState.ACTIVE,
        )

        d = entry.to_dict()

        assert d["severity"] == "CRITICAL"
        assert d["category"] == "security"
        assert d["alarm_priority"] == "HIGH"
        assert d["alarm_state"] == "ACTIVE"

    def test_to_dict_excludes_empty_optional_fields(self):
        """Test that empty optional fields are excluded.

        WHY: Keep serialised output clean.
        """
        entry = LogEntry(
            simulation_time=100.0,
            wall_time=1000.0,
            severity=EventSeverity.INFO,
            category=EventCategory.SYSTEM,
            message="Test",
        )

        d = entry.to_dict()

        assert "device" not in d
        assert "user" not in d
        assert "alarm_priority" not in d

    def test_to_json_produces_valid_json(self):
        """Test that to_json produces valid JSON.

        WHY: Must be parseable by external systems.
        """
        entry = LogEntry(
            simulation_time=100.0,
            wall_time=1000.0,
            severity=EventSeverity.INFO,
            category=EventCategory.SYSTEM,
            message="Test message",
            device="plc_1",
        )

        json_str = entry.to_json()
        parsed = json.loads(json_str)

        assert parsed["message"] == "Test message"
        assert parsed["device"] == "plc_1"

    def test_to_human_readable_format(self):
        """Test human-readable output format.

        WHY: Console output must be readable.
        """
        entry = LogEntry(
            simulation_time=100.5,
            wall_time=1000.0,
            severity=EventSeverity.WARNING,
            category=EventCategory.ALARM,
            message="High temperature",
            device="sensor_1",
        )

        readable = entry.to_human_readable()

        assert "100.50" in readable or "100.5" in readable
        assert "WARNING" in readable
        assert "sensor_1" in readable
        assert "High temperature" in readable


# ================================================================
# ICS LOGGER TESTS
# ================================================================
class TestICSLogger:
    """Test ICSLogger class."""

    def test_create_logger(self):
        """Test creating an ICS logger.

        WHY: Core functionality.
        """
        logger = ICSLogger("test_module", device="test_device")

        assert logger.name == "test_module"
        assert logger.device == "test_device"

    def test_standard_logging_methods(self):
        """Test standard logging methods work.

        WHY: Must support standard Python logging interface.
        """
        logger = ICSLogger("test", enable_console=False)

        # Should not raise
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        logger.critical("Critical message")

    @pytest.mark.asyncio
    async def test_log_event_returns_entry(self):
        """Test log_event returns LogEntry.

        WHY: Caller may need the created entry.
        """
        logger = ICSLogger("test", enable_console=False)

        entry = await logger.log_event(
            severity=EventSeverity.INFO,
            category=EventCategory.SYSTEM,
            message="Test event",
        )

        assert isinstance(entry, LogEntry)
        assert entry.message == "Test event"
        assert entry.severity == EventSeverity.INFO

    @pytest.mark.asyncio
    async def test_log_event_with_context(self):
        """Test log_event with additional context.

        WHY: Events need context for debugging.
        """
        logger = ICSLogger("test", device="plc_1", enable_console=False)

        entry = await logger.log_event(
            severity=EventSeverity.WARNING,
            category=EventCategory.PROCESS,
            message="Process deviation",
            user="operator1",
            data={"temperature": 105.5},
        )

        assert entry.device == "plc_1"
        assert entry.user == "operator1"
        assert entry.data["temperature"] == 105.5

    @pytest.mark.asyncio
    async def test_log_security_stores_in_audit_trail(self):
        """Test that security events are stored in audit trail.

        WHY: Security events must be auditable.
        """
        logger = ICSLogger("test", enable_console=False)

        await logger.log_security("Security event occurred")

        trail = await logger.get_audit_trail()
        assert len(trail) >= 1
        assert any(e.category == EventCategory.SECURITY for e in trail)

    @pytest.mark.asyncio
    async def test_log_audit_stores_in_audit_trail(self):
        """Test that audit events are stored in audit trail.

        WHY: Audit events must be retrievable.
        """
        logger = ICSLogger("test", enable_console=False)

        await logger.log_audit(
            message="User action",
            user="admin",
            action="login",
            result="ALLOWED",
        )

        trail = await logger.get_audit_trail()
        assert len(trail) >= 1
        assert any(e.category == EventCategory.AUDIT for e in trail)

    @pytest.mark.asyncio
    async def test_log_alarm_with_priority(self):
        """Test logging alarm with priority.

        WHY: Alarms need priority for ISA 18.2 compliance.
        """
        logger = ICSLogger("test", enable_console=False)

        entry = await logger.log_alarm(
            message="High pressure",
            priority=AlarmPriority.HIGH,
            state=AlarmState.ACTIVE,
        )

        assert entry.alarm_priority == AlarmPriority.HIGH
        assert entry.alarm_state == AlarmState.ACTIVE
        assert entry.category == EventCategory.ALARM

    @pytest.mark.asyncio
    async def test_audit_trail_limit(self):
        """Test that audit trail respects limit parameter.

        WHY: Need to limit returned entries.
        """
        logger = ICSLogger("test", enable_console=False)

        # Add multiple entries
        for i in range(10):
            await logger.log_security(f"Event {i}")

        trail = await logger.get_audit_trail(limit=5)
        assert len(trail) == 5

    @pytest.mark.asyncio
    async def test_audit_trail_filters_before_limiting(self):
        """Test that filtering happens before limiting.

        WHY: Fix for filter-after-slice bug.
        """
        logger = ICSLogger("test", enable_console=False)

        # Add mixed entries
        for i in range(10):
            await logger.log_security(f"Security {i}")

        await logger.log_event(
            severity=EventSeverity.INFO,
            category=EventCategory.SYSTEM,
            message="System event",
        )

        # Filter by category with limit
        trail = await logger.get_audit_trail(limit=5, category=EventCategory.SECURITY)

        # All returned should be security events
        assert all(e.category == EventCategory.SECURITY for e in trail)

    @pytest.mark.asyncio
    async def test_clear_audit_trail(self):
        """Test clearing audit trail.

        WHY: Need to reset for testing or rotation.
        """
        logger = ICSLogger("test", enable_console=False)

        await logger.log_security("Event 1")
        await logger.log_security("Event 2")

        count = await logger.clear_audit_trail()

        assert count == 2
        trail = await logger.get_audit_trail()
        assert len(trail) == 0

    @pytest.mark.asyncio
    async def test_max_audit_entries_configurable(self):
        """Test that max_audit_entries is configurable.

        WHY: Different deployments need different limits.
        """
        logger = ICSLogger("test", enable_console=False, max_audit_entries=5)

        # Add more than max
        for i in range(10):
            await logger.log_security(f"Event {i}")

        trail = await logger.get_audit_trail(limit=100)
        assert len(trail) <= 5


# ================================================================
# FORMATTER TESTS
# ================================================================
class TestSimTimeFormatter:
    """Test SimTimeFormatter."""

    def test_formatter_adds_sim_time(self):
        """Test that formatter adds simulation time to record.

        WHY: Logs need simulation time context.
        """
        from components.time.simulation_time import SimulationTime

        sim_time = SimulationTime()
        formatter = SimTimeFormatter(sim_time)

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)

        assert "SIM:" in formatted
        assert "Test message" in formatted


class TestJSONFormatter:
    """Test JSONFormatter."""

    def test_formatter_produces_valid_json(self):
        """Test that formatter produces valid JSON.

        WHY: JSON logs must be parseable.
        """
        formatter = JSONFormatter(device="test_device")

        record = logging.LogRecord(
            name="test",
            level=logging.WARNING,
            pathname="",
            lineno=0,
            msg="Test warning",
            args=(),
            exc_info=None,
        )

        formatted = formatter.format(record)
        parsed = json.loads(formatted)

        assert parsed["message"] == "Test warning"
        assert parsed["device"] == "test_device"
        assert parsed["severity"] == "WARNING"


# ================================================================
# LOGGER FACTORY TESTS
# ================================================================
class TestLoggerFactory:
    """Test get_logger and configure_logging."""

    def test_get_logger_returns_ics_logger(self):
        """Test that get_logger returns ICSLogger instance.

        WHY: Factory should create correct type.
        """
        logger = get_logger("test_factory")

        assert isinstance(logger, ICSLogger)

    def test_get_logger_same_name_returns_same_instance(self):
        """Test that same name returns same logger.

        WHY: Logger instances should be reused.
        """
        logger1 = get_logger("test_singleton", device="dev1")
        logger2 = get_logger("test_singleton", device="dev1")

        assert logger1 is logger2

    def test_get_logger_different_device_different_instance(self):
        """Test that different device creates different logger.

        WHY: Each device needs its own logger.
        """
        logger1 = get_logger("test_module", device="device_a")
        logger2 = get_logger("test_module", device="device_b")

        assert logger1 is not logger2

    def test_configure_logging_sets_defaults(self):
        """Test that configure_logging sets global defaults.

        WHY: Central configuration for all loggers.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            configure_logging(log_dir=tmpdir)

            # New logger should use configured log_dir
            logger = get_logger("test_configured", device="new_device")

            # Logger should have log_dir set
            assert logger.log_dir is not None


# ================================================================
# THREAD SAFETY TESTS
# ================================================================
class TestLoggerThreadSafety:
    """Test thread safety of logger factory."""

    def test_get_logger_thread_safe(self):
        """Test that get_logger is thread-safe.

        WHY: Multiple threads may request loggers simultaneously.
        """
        results = []
        errors = []

        def get_loggers():
            try:
                for i in range(10):
                    logger = get_logger(f"thread_test_{i}", device=f"dev_{i}")
                    results.append(logger)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_loggers) for _ in range(5)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert len(results) == 50


# ================================================================
# FILE LOGGING TESTS
# ================================================================
class TestFileLogging:
    """Test file-based logging."""

    def test_json_handler_creates_file(self):
        """Test that JSON handler creates log file.

        WHY: File logging must work for persistence.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir)
            logger = ICSLogger(
                "test_file",
                device="test_device",
                log_dir=log_dir,
                enable_json=True,
                enable_console=False,
            )

            logger.info("Test message")

            # Force flush
            for handler in logger.logger.handlers:
                handler.flush()

            log_file = log_dir / "test_device.json.log"
            assert log_file.exists()

    def test_log_dir_created_if_missing(self):
        """Test that log directory is created if it doesn't exist.

        WHY: Convenience - shouldn't require pre-creating directories.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "nested" / "logs"

            _logger = ICSLogger(  # Intentionally unused - just creating to trigger dir creation
                "test_nested",
                device="dev",
                log_dir=log_dir,
                enable_json=True,
                enable_console=False,
            )

            assert log_dir.exists()
