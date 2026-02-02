# tests/unit/security/test_anomaly_detector.py
"""Comprehensive tests for anomaly detection system.

Test Coverage:
- AnomalyType and AnomalySeverity enums
- AnomalyEvent dataclass
- StatisticalBaseline learning and detection
- AnomalyDetector configuration
- Statistical anomaly detection
- Range violation detection
- Rate of change detection
- Alarm flood detection
- Anomaly retrieval and filtering
- Baseline export/import
- ICSLogger integration
"""

import asyncio
from collections import deque
from unittest.mock import AsyncMock, MagicMock

import pytest

from components.security.anomaly_detector import (
    ANOMALY_TO_EVENT_SEVERITY,
    AnomalyDetector,
    AnomalyEvent,
    AnomalySeverity,
    AnomalyType,
    StatisticalBaseline,
)
from components.security.logging_system import EventSeverity


# ================================================================
# ENUM TESTS
# ================================================================
class TestAnomalyType:
    """Test AnomalyType enum."""

    def test_all_types_present(self):
        """Test all anomaly types are present.

        WHY: Comprehensive detection requires all types.
        """
        types = {t.value for t in AnomalyType}
        expected = {
            "statistical",
            "range",
            "rate_of_change",
            "pattern",
            "protocol",
            "communication",
            "alarm_flood",
            "control_logic",
        }
        assert expected == types


class TestAnomalySeverity:
    """Test AnomalySeverity enum."""

    def test_severity_ordering(self):
        """Test that severity values are properly ordered.

        WHY: Higher severity should have higher value.
        """
        assert AnomalySeverity.LOW.value < AnomalySeverity.MEDIUM.value
        assert AnomalySeverity.MEDIUM.value < AnomalySeverity.HIGH.value
        assert AnomalySeverity.HIGH.value < AnomalySeverity.CRITICAL.value


class TestSeverityMapping:
    """Test ANOMALY_TO_EVENT_SEVERITY mapping."""

    def test_all_severities_mapped(self):
        """Test all anomaly severities map to event severities.

        WHY: Logging requires severity mapping.
        """
        for severity in AnomalySeverity:
            assert severity in ANOMALY_TO_EVENT_SEVERITY
            assert isinstance(ANOMALY_TO_EVENT_SEVERITY[severity], EventSeverity)

    def test_critical_maps_to_critical(self):
        """Test that CRITICAL maps to EventSeverity.CRITICAL.

        WHY: Critical anomalies are critical events.
        """
        assert (
            ANOMALY_TO_EVENT_SEVERITY[AnomalySeverity.CRITICAL]
            == EventSeverity.CRITICAL
        )


# ================================================================
# ANOMALY EVENT TESTS
# ================================================================
class TestAnomalyEvent:
    """Test AnomalyEvent dataclass."""

    def test_create_minimal_event(self):
        """Test creating event with minimal fields.

        WHY: Core functionality.
        """
        event = AnomalyEvent(
            timestamp=100.0,
            anomaly_type=AnomalyType.STATISTICAL,
            severity=AnomalySeverity.MEDIUM,
            device="plc_1",
            parameter="temperature",
            observed_value=105.5,
        )

        assert event.timestamp == 100.0
        assert event.anomaly_type == AnomalyType.STATISTICAL
        assert event.device == "plc_1"

    def test_create_full_event(self):
        """Test creating event with all fields.

        WHY: All fields should be usable.
        """
        event = AnomalyEvent(
            timestamp=100.0,
            anomaly_type=AnomalyType.RANGE,
            severity=AnomalySeverity.HIGH,
            device="plc_1",
            parameter="pressure",
            observed_value=150.0,
            expected_value=100.0,
            baseline_mean=100.0,
            baseline_std=5.0,
            deviation_magnitude=10.0,
            description="Pressure exceeded limit",
            data={"limit": 120.0},
        )

        assert event.baseline_mean == 100.0
        assert event.deviation_magnitude == 10.0
        assert event.data["limit"] == 120.0

    def test_to_dict(self):
        """Test converting event to dictionary.

        WHY: Serialisation for storage/transmission.
        """
        event = AnomalyEvent(
            timestamp=100.0,
            anomaly_type=AnomalyType.STATISTICAL,
            severity=AnomalySeverity.MEDIUM,
            device="plc_1",
            parameter="temp",
            observed_value=105.5,
        )

        d = event.to_dict()

        assert d["timestamp"] == 100.0
        assert d["anomaly_type"] == "statistical"
        assert d["severity"] == 2  # MEDIUM value
        assert d["device"] == "plc_1"


# ================================================================
# STATISTICAL BASELINE TESTS
# ================================================================
class TestStatisticalBaseline:
    """Test StatisticalBaseline class."""

    def test_create_baseline(self):
        """Test creating a baseline.

        WHY: Core functionality.
        """
        baseline = StatisticalBaseline(
            parameter="temperature",
            device="sensor_1",
        )

        assert baseline.parameter == "temperature"
        assert baseline.device == "sensor_1"
        assert baseline.is_learned is False

    def test_update_tracks_min_max(self):
        """Test that update tracks min/max values.

        WHY: Range tracking for anomalies.
        """
        baseline = StatisticalBaseline(parameter="temp", device="dev")

        baseline.update(10.0)
        baseline.update(20.0)
        baseline.update(15.0)

        assert baseline.min_value == 10.0
        assert baseline.max_value == 20.0

    def test_update_calculates_mean(self):
        """Test that update calculates mean.

        WHY: Statistical analysis requires mean.
        """
        baseline = StatisticalBaseline(
            parameter="temp", device="dev", learning_window=5
        )

        for v in [10.0, 20.0, 30.0, 40.0, 50.0]:
            baseline.update(v)

        assert baseline.mean == 30.0  # (10+20+30+40+50)/5

    def test_update_calculates_std(self):
        """Test that update calculates standard deviation.

        WHY: Statistical analysis requires std.
        """
        baseline = StatisticalBaseline(
            parameter="temp", device="dev", learning_window=5
        )

        for v in [10.0, 20.0, 30.0, 40.0, 50.0]:
            baseline.update(v)

        # std of [10,20,30,40,50] = 15.811...
        assert 15.0 < baseline.std < 16.0

    def test_is_learned_after_window(self):
        """Test that baseline is learned after window fills.

        WHY: Need enough data before detection.
        """
        baseline = StatisticalBaseline(
            parameter="temp", device="dev", learning_window=10
        )

        for i in range(9):
            baseline.update(float(i))

        assert baseline.is_learned is False

        baseline.update(9.0)

        assert baseline.is_learned is True

    def test_is_anomalous_before_learned(self):
        """Test that nothing is anomalous before learning.

        WHY: Can't detect without baseline.
        """
        baseline = StatisticalBaseline(
            parameter="temp", device="dev", learning_window=100
        )

        for i in range(10):
            baseline.update(float(i))

        # Even extreme value shouldn't be flagged
        assert baseline.is_anomalous(1000.0) is False

    def test_is_anomalous_within_threshold(self):
        """Test that values within threshold are not anomalous.

        WHY: Normal values should pass.
        """
        baseline = StatisticalBaseline(
            parameter="temp", device="dev", learning_window=10
        )

        # Train with consistent values
        for _ in range(20):
            baseline.update(100.0 + (hash(str(_)) % 10) - 5)  # 95-105

        # Recalculate with exact values for testing
        baseline._values = deque([100.0] * 10, maxlen=1000)
        baseline.mean = 100.0
        baseline.std = 1.0
        baseline.is_learned = True

        # Within 3 sigma
        assert baseline.is_anomalous(102.0, sigma_threshold=3.0) is False

    def test_is_anomalous_beyond_threshold(self):
        """Test that values beyond threshold are anomalous.

        WHY: Outliers should be detected.
        """
        baseline = StatisticalBaseline(
            parameter="temp", device="dev", learning_window=10
        )

        baseline._values = deque([100.0] * 10, maxlen=1000)
        baseline.mean = 100.0
        baseline.std = 1.0
        baseline.is_learned = True

        # Beyond 3 sigma
        assert baseline.is_anomalous(105.0, sigma_threshold=3.0) is True

    def test_get_deviation_magnitude(self):
        """Test getting deviation magnitude.

        WHY: Severity depends on magnitude.
        """
        baseline = StatisticalBaseline(parameter="temp", device="dev")
        baseline.mean = 100.0
        baseline.std = 10.0

        magnitude = baseline.get_deviation_magnitude(130.0)

        assert magnitude == 3.0  # (130-100)/10


# ================================================================
# ANOMALY DETECTOR TESTS
# ================================================================
class TestAnomalyDetector:
    """Test AnomalyDetector class."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for testing."""
        data_store = MagicMock()
        data_store.update_metadata = AsyncMock()
        data_store.read_metadata = AsyncMock(return_value={})

        system_state = MagicMock()
        system_state.get_device = AsyncMock(return_value=None)

        return data_store, system_state

    @pytest.fixture
    def detector(self, mock_dependencies):
        """Create detector with mock dependencies."""
        data_store, system_state = mock_dependencies
        return AnomalyDetector(data_store, system_state)

    def test_create_detector(self, mock_dependencies):
        """Test creating an anomaly detector.

        WHY: Core functionality.
        """
        data_store, system_state = mock_dependencies
        detector = AnomalyDetector(data_store, system_state)

        assert detector.enabled is True
        assert len(detector.baselines) == 0

    @pytest.mark.asyncio
    async def test_add_baseline(self, detector):
        """Test adding a baseline.

        WHY: Must be able to monitor parameters.
        """
        await detector.add_baseline("plc_1", "temperature")

        assert ("plc_1", "temperature") in detector.baselines

    @pytest.mark.asyncio
    async def test_set_range_limit(self, detector):
        """Test setting range limits.

        WHY: Range checking requires limits.
        """
        await detector.set_range_limit("plc_1", "pressure", 0.0, 100.0)

        assert detector.range_limits[("plc_1", "pressure")] == (0.0, 100.0)

    @pytest.mark.asyncio
    async def test_set_rate_of_change_limit(self, detector):
        """Test setting rate of change limits.

        WHY: Rate checking requires limits.
        """
        await detector.set_rate_of_change_limit("plc_1", "temperature", 5.0)

        assert detector.roc_limits[("plc_1", "temperature")] == 5.0


# ================================================================
# DETECTION TESTS
# ================================================================
class TestAnomalyDetection:
    """Test anomaly detection functionality."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for testing."""
        data_store = MagicMock()
        data_store.update_metadata = AsyncMock()
        data_store.read_metadata = AsyncMock(return_value={})

        system_state = MagicMock()
        system_state.get_device = AsyncMock(return_value=None)

        return data_store, system_state

    @pytest.fixture
    def detector(self, mock_dependencies):
        """Create detector with mock dependencies."""
        data_store, system_state = mock_dependencies
        return AnomalyDetector(data_store, system_state)

    @pytest.mark.asyncio
    async def test_check_value_no_anomaly(self, detector):
        """Test checking value with no anomaly.

        WHY: Normal values should pass.
        """
        await detector.set_range_limit("plc_1", "temp", 0.0, 100.0)

        anomalies = await detector.check_value("plc_1", "temp", 50.0)

        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_check_value_range_violation(self, detector):
        """Test detecting range violation.

        WHY: Out-of-range values should be detected.
        """
        await detector.set_range_limit("plc_1", "temp", 0.0, 100.0)

        anomalies = await detector.check_value("plc_1", "temp", 150.0)

        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.RANGE

    @pytest.mark.asyncio
    async def test_check_value_range_below_minimum(self, detector):
        """Test detecting value below minimum.

        WHY: Low values are also violations.
        """
        await detector.set_range_limit("plc_1", "temp", 10.0, 100.0)

        anomalies = await detector.check_value("plc_1", "temp", 5.0)

        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == AnomalyType.RANGE

    @pytest.mark.asyncio
    async def test_check_value_statistical_anomaly(self, detector):
        """Test detecting statistical anomaly.

        WHY: Statistical outliers should be detected.
        """
        await detector.add_baseline("plc_1", "temp", learning_window=10)

        # Train baseline
        for _ in range(10):
            await detector.check_value("plc_1", "temp", 100.0)

        # Force baseline to be learned with known values
        baseline = detector.baselines[("plc_1", "temp")]
        baseline.mean = 100.0
        baseline.std = 1.0
        baseline.is_learned = True

        # Check anomalous value
        anomalies = await detector.check_value("plc_1", "temp", 110.0)

        assert len(anomalies) >= 1
        assert any(a.anomaly_type == AnomalyType.STATISTICAL for a in anomalies)

    @pytest.mark.asyncio
    async def test_check_value_rate_of_change(self, detector):
        """Test detecting rate of change anomaly.

        WHY: Rapid changes may indicate problems.
        """
        await detector.set_rate_of_change_limit("plc_1", "temp", 1.0)

        # First value sets baseline
        await detector.check_value("plc_1", "temp", 100.0)

        # Rapid change (more than 1.0/s)
        # Simulate time passing by manipulating last_values
        detector.last_values[("plc_1", "temp")] = (100.0, detector.sim_time.now() - 1.0)

        anomalies = await detector.check_value("plc_1", "temp", 110.0)

        assert len(anomalies) >= 1
        assert any(a.anomaly_type == AnomalyType.RATE_OF_CHANGE for a in anomalies)

    @pytest.mark.asyncio
    async def test_check_value_disabled(self, detector):
        """Test that disabled detector returns no anomalies.

        WHY: Should be able to disable detection.
        """
        detector.enabled = False
        await detector.set_range_limit("plc_1", "temp", 0.0, 100.0)

        anomalies = await detector.check_value("plc_1", "temp", 200.0)

        assert len(anomalies) == 0


# ================================================================
# ALARM FLOOD TESTS
# ================================================================
class TestAlarmFloodDetection:
    """Test alarm flood detection."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for testing."""
        data_store = MagicMock()
        data_store.update_metadata = AsyncMock()

        system_state = MagicMock()

        return data_store, system_state

    @pytest.fixture
    def detector(self, mock_dependencies):
        """Create detector with mock dependencies."""
        data_store, system_state = mock_dependencies
        det = AnomalyDetector(data_store, system_state)
        det.alarm_flood_threshold = 5
        det.alarm_flood_window = 10.0
        return det

    @pytest.mark.asyncio
    async def test_no_flood_below_threshold(self, detector):
        """Test no flood when below threshold.

        WHY: Normal alarm rates should pass.
        """
        for _ in range(4):
            result = await detector.check_alarm_flood("plc_1")

        assert result is None

    @pytest.mark.asyncio
    async def test_flood_detected_at_threshold(self, detector):
        """Test flood detected at threshold.

        WHY: Excessive alarms should trigger.
        """
        for i in range(5):
            result = await detector.check_alarm_flood("plc_1")

        assert result is not None
        assert result.anomaly_type == AnomalyType.ALARM_FLOOD

    @pytest.mark.asyncio
    async def test_flood_disabled(self, detector):
        """Test flood detection when disabled.

        WHY: Should respect enabled flag.
        """
        detector.enabled = False

        for _ in range(10):
            result = await detector.check_alarm_flood("plc_1")

        assert result is None


# ================================================================
# ANOMALY RETRIEVAL TESTS
# ================================================================
class TestAnomalyRetrieval:
    """Test anomaly retrieval functionality."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for testing."""
        data_store = MagicMock()
        data_store.update_metadata = AsyncMock()

        system_state = MagicMock()

        return data_store, system_state

    @pytest.fixture
    def detector(self, mock_dependencies):
        """Create detector with mock dependencies."""
        data_store, system_state = mock_dependencies
        return AnomalyDetector(data_store, system_state)

    @pytest.mark.asyncio
    async def test_get_recent_anomalies(self, detector):
        """Test getting recent anomalies.

        WHY: Need to review detected anomalies.
        """
        await detector.set_range_limit("plc_1", "temp", 0.0, 100.0)

        await detector.check_value("plc_1", "temp", 150.0)
        await detector.check_value("plc_1", "temp", 200.0)

        anomalies = await detector.get_recent_anomalies()

        assert len(anomalies) == 2

    @pytest.mark.asyncio
    async def test_get_recent_anomalies_with_limit(self, detector):
        """Test limiting returned anomalies.

        WHY: May only want recent subset.
        """
        await detector.set_range_limit("plc_1", "temp", 0.0, 100.0)

        for i in range(10):
            await detector.check_value("plc_1", "temp", 150.0 + i)

        anomalies = await detector.get_recent_anomalies(limit=5)

        assert len(anomalies) == 5

    @pytest.mark.asyncio
    async def test_get_recent_anomalies_filter_by_device(self, detector):
        """Test filtering anomalies by device.

        WHY: May only want specific device.
        """
        await detector.set_range_limit("plc_1", "temp", 0.0, 100.0)
        await detector.set_range_limit("plc_2", "temp", 0.0, 100.0)

        await detector.check_value("plc_1", "temp", 150.0)
        await detector.check_value("plc_2", "temp", 150.0)
        await detector.check_value("plc_1", "temp", 160.0)

        anomalies = await detector.get_recent_anomalies(device="plc_1")

        assert len(anomalies) == 2
        assert all(a.device == "plc_1" for a in anomalies)

    @pytest.mark.asyncio
    async def test_get_recent_anomalies_filter_by_severity(self, detector):
        """Test filtering anomalies by severity.

        WHY: May only want critical anomalies.
        """
        await detector.set_range_limit("plc_1", "temp", 0.0, 100.0)

        # Generate anomalies with different severities
        await detector.check_value("plc_1", "temp", 110.0)  # Low violation
        await detector.check_value("plc_1", "temp", 200.0)  # High violation

        anomalies = await detector.get_recent_anomalies(
            severity=AnomalySeverity.CRITICAL
        )

        assert all(a.severity == AnomalySeverity.CRITICAL for a in anomalies)

    @pytest.mark.asyncio
    async def test_get_recent_anomalies_filters_before_limiting(self, detector):
        """Test that filtering happens before limiting.

        WHY: Fix for filter-after-slice bug.
        """
        await detector.set_range_limit("plc_1", "temp", 0.0, 100.0)
        await detector.set_range_limit("plc_2", "temp", 0.0, 100.0)

        # Add many anomalies for plc_2
        for i in range(20):
            await detector.check_value("plc_2", "temp", 150.0 + i)

        # Add few anomalies for plc_1
        for i in range(3):
            await detector.check_value("plc_1", "temp", 150.0 + i)

        # Request 10 from plc_1 - should get all 3
        anomalies = await detector.get_recent_anomalies(limit=10, device="plc_1")

        assert len(anomalies) == 3

    @pytest.mark.asyncio
    async def test_get_anomaly_summary(self, detector):
        """Test getting anomaly summary.

        WHY: Overview of all anomalies.
        """
        await detector.set_range_limit("plc_1", "temp", 0.0, 100.0)
        await detector.set_range_limit("plc_1", "pressure", 0.0, 50.0)

        await detector.check_value("plc_1", "temp", 150.0)
        await detector.check_value("plc_1", "pressure", 100.0)

        summary = await detector.get_anomaly_summary()

        assert summary["total_anomalies"] == 2
        assert "by_type" in summary
        assert "by_severity" in summary
        assert "by_device" in summary

    @pytest.mark.asyncio
    async def test_clear_anomalies(self, detector):
        """Test clearing anomaly history.

        WHY: Reset for new session.
        """
        await detector.set_range_limit("plc_1", "temp", 0.0, 100.0)

        await detector.check_value("plc_1", "temp", 150.0)
        await detector.check_value("plc_1", "temp", 200.0)

        count = await detector.clear_anomalies()

        assert count == 2
        anomalies = await detector.get_recent_anomalies()
        assert len(anomalies) == 0


# ================================================================
# BASELINE EXPORT TESTS
# ================================================================
class TestBaselineExport:
    """Test baseline export/import functionality."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for testing."""
        data_store = MagicMock()
        data_store.update_metadata = AsyncMock()
        data_store.read_metadata = AsyncMock(return_value={})

        system_state = MagicMock()

        return data_store, system_state

    @pytest.fixture
    def detector(self, mock_dependencies):
        """Create detector with mock dependencies."""
        data_store, system_state = mock_dependencies
        return AnomalyDetector(data_store, system_state)

    @pytest.mark.asyncio
    async def test_export_baselines(self, detector):
        """Test exporting learned baselines.

        WHY: Persistence across restarts.
        """
        await detector.add_baseline("plc_1", "temp", learning_window=5)

        # Train baseline
        for i in range(10):
            await detector.check_value("plc_1", "temp", 100.0 + i)

        exported = await detector.export_baselines()

        assert "plc_1:temp" in exported
        assert "mean" in exported["plc_1:temp"]
        assert "std" in exported["plc_1:temp"]

    @pytest.mark.asyncio
    async def test_export_only_learned_baselines(self, detector):
        """Test that only learned baselines are exported.

        WHY: Unlearned baselines aren't useful.
        """
        await detector.add_baseline("plc_1", "temp", learning_window=100)
        await detector.add_baseline("plc_2", "temp", learning_window=5)

        # Only train plc_2
        for i in range(10):
            await detector.check_value("plc_2", "temp", 100.0)

        exported = await detector.export_baselines()

        assert "plc_1:temp" not in exported
        assert "plc_2:temp" in exported

    @pytest.mark.asyncio
    async def test_store_baselines_in_datastore(self, detector, mock_dependencies):
        """Test storing baselines in DataStore.

        WHY: Persistence via DataStore.
        """
        data_store, _ = mock_dependencies

        await detector.add_baseline("plc_1", "temp", learning_window=5)
        for i in range(10):
            await detector.check_value("plc_1", "temp", 100.0)

        await detector.store_baselines_in_datastore()

        data_store.update_metadata.assert_called()


# ================================================================
# LOGGING INTEGRATION TESTS
# ================================================================
class TestAnomalyLogging:
    """Test ICSLogger integration."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for testing."""
        data_store = MagicMock()
        data_store.update_metadata = AsyncMock()

        system_state = MagicMock()

        return data_store, system_state

    @pytest.fixture
    def detector(self, mock_dependencies):
        """Create detector with mock dependencies."""
        data_store, system_state = mock_dependencies
        return AnomalyDetector(data_store, system_state)

    @pytest.mark.asyncio
    async def test_anomaly_logged(self, detector):
        """Test that detected anomalies are logged.

        WHY: Security events must be auditable.
        """
        await detector.set_range_limit("plc_1", "temp", 0.0, 100.0)

        await detector.check_value("plc_1", "temp", 150.0)

        # Check that logger's audit trail has entries
        trail = await detector.logger.get_audit_trail()
        assert len(trail) > 0

    @pytest.mark.asyncio
    async def test_alarm_flood_logged(self, detector):
        """Test that alarm floods are logged.

        WHY: Flood events are security-relevant.
        """
        detector.alarm_flood_threshold = 3

        for _ in range(5):
            await detector.check_alarm_flood("plc_1")

        trail = await detector.logger.get_audit_trail()
        assert len(trail) > 0
