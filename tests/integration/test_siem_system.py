# tests/integration/test_siem_system.py
"""
Integration tests for SIEM system.

Tests the full audit trail pipeline:
ICSLogger → SystemState → DataStore → SIEM → Alerts
"""

import asyncio
import time

import pytest

from components.devices.enterprise_zone.siem_system import (
    AlertSeverity,
    IncidentStatus,
    SIEMSystem,
)
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


@pytest.fixture
async def siem_system():
    """Create SIEM system with dependencies."""
    sim_time = SimulationTime()
    system_state = SystemState()
    data_store = DataStore(system_state=system_state)

    siem = SIEMSystem(
        device_name="test_siem",
        device_id=9999,
        data_store=data_store,
        analysis_interval=0.5,  # Fast analysis for testing
        alert_history_limit=100,
    )

    await siem.start()

    yield siem, system_state, sim_time

    await siem.stop()


class TestSIEMLifecycle:
    """Test SIEM system lifecycle and initialization."""

    @pytest.mark.asyncio
    async def test_siem_initialization(self, siem_system):
        """Test SIEM system initializes correctly."""
        siem, _, _ = siem_system

        assert siem._running
        assert siem.device_name == "test_siem"
        assert siem.analysis_interval == 0.5
        assert siem.total_events_analyzed == 0
        assert siem.total_alerts_generated == 0
        assert len(siem.alerts) == 0

    @pytest.mark.asyncio
    async def test_siem_memory_map(self, siem_system):
        """Test SIEM exposes statistics in memory map."""
        siem, _, _ = siem_system

        assert "total_events_analyzed" in siem.memory_map
        assert "total_alerts_generated" in siem.memory_map
        assert "active_alerts" in siem.memory_map
        assert "critical_alerts" in siem.memory_map

    @pytest.mark.asyncio
    async def test_siem_device_type(self, siem_system):
        """Test SIEM device type and protocols."""
        siem, _, _ = siem_system

        assert siem._device_type() == "siem_system"
        assert "syslog" in siem._supported_protocols()
        assert "http_api" in siem._supported_protocols()


class TestFailedAuthDetection:
    """Test failed authentication detection rule."""

    @pytest.mark.asyncio
    async def test_detect_failed_auth(self, siem_system):
        """Test SIEM detects multiple failed authentication attempts."""
        siem, system_state, sim_time = siem_system

        # Inject 5 failed auth events
        for i in range(5):
            await system_state.append_audit_event({
                "simulation_time": sim_time.now(),
                "wall_time": time.time(),
                "message": f"Failed authentication attempt {i+1}",
                "device": "auth_system",
                "user": "attacker",
                "data": {
                    "action": "authenticate",
                    "result": "FAILED",
                    "source_ip": "192.168.1.100",
                },
            })
            await asyncio.sleep(0.05)

        # Wait for SIEM to analyze
        await asyncio.sleep(1.0)

        # Should detect failed auth pattern (3+ failures)
        alerts = siem.get_active_alerts(severity=AlertSeverity.HIGH)
        assert len(alerts) > 0

        # Check alert content
        auth_alerts = [a for a in alerts if "authentication" in a.category]
        assert len(auth_alerts) > 0

        alert = auth_alerts[0]
        assert alert.severity == AlertSeverity.HIGH
        assert "attacker" in alert.title.lower()
        assert alert.status == IncidentStatus.NEW
        assert len(alert.affected_devices) > 0

    @pytest.mark.asyncio
    async def test_no_alert_on_few_failures(self, siem_system):
        """Test SIEM doesn't alert on fewer than 3 failures."""
        siem, system_state, sim_time = siem_system

        # Inject only 2 failed auth events (below threshold)
        for i in range(2):
            await system_state.append_audit_event({
                "simulation_time": sim_time.now(),
                "wall_time": time.time(),
                "message": f"Failed authentication attempt {i+1}",
                "device": "auth_system",
                "user": "legitimate_user",
                "data": {
                    "action": "authenticate",
                    "result": "FAILED",
                },
            })

        await asyncio.sleep(1.0)

        # Should not generate alert (below threshold)
        initial_alert_count = siem.total_alerts_generated

        # Process events
        await asyncio.sleep(0.6)  # Wait for scan cycle

        # Alert count should not increase significantly
        # (may have increased from other test data, but shouldn't have new auth alerts)
        auth_alerts = [
            a for a in siem.alerts
            if "authentication" in a.category and "legitimate_user" in a.title
        ]
        assert len(auth_alerts) == 0


class TestSafetyBypassDetection:
    """Test safety bypass detection rule."""

    @pytest.mark.asyncio
    async def test_detect_safety_bypass(self, siem_system):
        """Test SIEM detects safety bypass activation."""
        siem, system_state, sim_time = siem_system

        # Inject safety bypass event
        await system_state.append_audit_event({
            "simulation_time": sim_time.now(),
            "wall_time": time.time(),
            "message": "Safety bypass activated on 'reactor_safety_1'",
            "device": "reactor_safety_1",
            "user": "supervisor1",
            "data": {
                "action": "activate_safety_bypass",
                "result": "SUCCESS",
                "bypass_reason": "maintenance",
            },
        })

        await asyncio.sleep(1.0)

        # Should generate HIGH priority alert
        alerts = siem.get_all_alerts(category="safety")
        assert len(alerts) > 0

        bypass_alert = alerts[0]
        assert bypass_alert.severity == AlertSeverity.HIGH
        assert "reactor_safety_1" in bypass_alert.affected_devices
        assert "bypass" in bypass_alert.title.lower()


class TestSCRAMDetection:
    """Test reactor SCRAM detection rule."""

    @pytest.mark.asyncio
    async def test_detect_scram(self, siem_system):
        """Test SIEM detects reactor SCRAM operations."""
        siem, system_state, sim_time = siem_system

        # Inject SCRAM event
        await system_state.append_audit_event({
            "simulation_time": sim_time.now(),
            "wall_time": time.time(),
            "message": "Reactor SCRAM initiated",
            "device": "reactor_plc_1",
            "user": "operator1",
            "data": {
                "action": "reactor_scram_initiate",
                "result": "SUCCESS",
                "trigger": "emergency",
            },
        })

        await asyncio.sleep(1.0)

        # Should generate CRITICAL priority alert
        alerts = siem.get_active_alerts(severity=AlertSeverity.CRITICAL)
        assert len(alerts) > 0

        scram_alert = alerts[0]
        assert scram_alert.severity == AlertSeverity.CRITICAL
        assert "scram" in scram_alert.title.lower()
        assert "reactor_plc_1" in scram_alert.affected_devices


class TestNetworkViolationDetection:
    """Test network segmentation violation detection."""

    @pytest.mark.asyncio
    async def test_detect_network_violations(self, siem_system):
        """Test SIEM detects repeated network segmentation violations."""
        siem, system_state, sim_time = siem_system

        # Inject 6 network denial events (above threshold of 5)
        for i in range(6):
            await system_state.append_audit_event({
                "simulation_time": sim_time.now(),
                "wall_time": time.time(),
                "message": "Connection denied by network segmentation",
                "device": "turbine_plc_1",
                "user": "",
                "data": {
                    "action": "network_access",
                    "result": "DENIED",
                    "source_network": "corporate_network",
                    "target_device": "turbine_plc_1",
                },
            })
            await asyncio.sleep(0.05)

        await asyncio.sleep(1.0)

        # Should generate MEDIUM priority alert
        alerts = siem.get_all_alerts(category="network_security")
        assert len(alerts) > 0

        network_alert = alerts[0]
        assert network_alert.severity == AlertSeverity.MEDIUM
        assert "segmentation" in network_alert.title.lower()


class TestUnusualWriteDetection:
    """Test unusual write pattern detection."""

    @pytest.mark.asyncio
    async def test_detect_unusual_writes(self, siem_system):
        """Test SIEM detects high-frequency write operations."""
        siem, system_state, sim_time = siem_system

        # Inject 55 write events (above threshold of 50)
        for i in range(55):
            await system_state.append_audit_event({
                "simulation_time": sim_time.now(),
                "wall_time": time.time(),
                "message": f"Memory write operation {i+1}",
                "device": "target_plc",
                "user": "unknown",
                "data": {
                    "action": "modbus_write",
                    "result": "SUCCESS",
                    "address": f"40001",
                },
            })

        await asyncio.sleep(1.0)

        # Should generate anomaly alert
        alerts = siem.get_all_alerts(category="anomaly")
        assert len(alerts) > 0

        write_alert = alerts[0]
        assert write_alert.severity == AlertSeverity.MEDIUM
        assert "write" in write_alert.title.lower()
        assert "target_plc" in write_alert.affected_devices


class TestAlertManagement:
    """Test alert management features."""

    @pytest.mark.asyncio
    async def test_update_alert_status(self, siem_system):
        """Test updating alert status and assignment."""
        siem, system_state, sim_time = siem_system

        # Generate an alert
        await system_state.append_audit_event({
            "simulation_time": sim_time.now(),
            "wall_time": time.time(),
            "message": "Safety bypass activated",
            "device": "test_device",
            "user": "test_user",
            "data": {
                "action": "activate_safety_bypass",
                "result": "SUCCESS",
            },
        })

        await asyncio.sleep(1.0)

        alerts = siem.get_active_alerts()
        assert len(alerts) > 0

        alert = alerts[0]
        original_status = alert.status

        # Update alert status
        success = await siem.update_alert_status(
            alert_id=alert.alert_id,
            status=IncidentStatus.INVESTIGATING,
            assigned_to="analyst1",
            note="Verifying maintenance authorization",
        )

        assert success
        assert alert.status == IncidentStatus.INVESTIGATING
        assert alert.assigned_to == "analyst1"
        assert len(alert.notes) == 1
        assert "Verifying" in alert.notes[0]

    @pytest.mark.asyncio
    async def test_get_alerts_by_severity(self, siem_system):
        """Test filtering alerts by severity."""
        siem, system_state, sim_time = siem_system

        # Generate HIGH alert
        await system_state.append_audit_event({
            "simulation_time": sim_time.now(),
            "wall_time": time.time(),
            "message": "Safety bypass",
            "device": "device1",
            "user": "user1",
            "data": {"action": "activate_safety_bypass", "result": "SUCCESS"},
        })

        # Generate CRITICAL alert
        await system_state.append_audit_event({
            "simulation_time": sim_time.now(),
            "wall_time": time.time(),
            "message": "SCRAM",
            "device": "device2",
            "user": "user2",
            "data": {"action": "reactor_scram", "result": "SUCCESS"},
        })

        await asyncio.sleep(1.0)

        high_alerts = siem.get_active_alerts(severity=AlertSeverity.HIGH)
        critical_alerts = siem.get_active_alerts(severity=AlertSeverity.CRITICAL)

        assert len(high_alerts) > 0
        assert len(critical_alerts) > 0
        assert all(a.severity == AlertSeverity.HIGH for a in high_alerts)
        assert all(a.severity == AlertSeverity.CRITICAL for a in critical_alerts)


class TestSIEMStatistics:
    """Test SIEM statistics and reporting."""

    @pytest.mark.asyncio
    async def test_statistics_tracking(self, siem_system):
        """Test SIEM tracks statistics correctly."""
        siem, system_state, sim_time = siem_system

        initial_events = siem.total_events_analyzed
        initial_alerts = siem.total_alerts_generated

        # Generate events
        for i in range(10):
            await system_state.append_audit_event({
                "simulation_time": sim_time.now(),
                "wall_time": time.time(),
                "message": f"Test event {i}",
                "device": "test_device",
                "user": "test_user",
                "data": {"action": "test_action", "result": "SUCCESS"},
            })

        await asyncio.sleep(1.0)

        # Events should be analyzed
        assert siem.total_events_analyzed > initial_events

        stats = siem.get_statistics()
        assert stats["events"]["total_analyzed"] > 0
        assert stats["events"]["analysis_interval"] == 0.5
        assert "alerts" in stats
        assert "detection_rules" in stats
        assert "system" in stats

    @pytest.mark.asyncio
    async def test_get_summary(self, siem_system):
        """Test SIEM summary generation."""
        siem, _, _ = siem_system

        summary = siem.get_summary()

        assert "SIEM System" in summary
        assert "test_siem" in summary
        assert "Events Analyzed" in summary
        assert "Total Alerts" in summary
        assert "Active Alerts" in summary
        assert "Status" in summary

    @pytest.mark.asyncio
    async def test_alert_history_limit(self, siem_system):
        """Test SIEM respects alert history limit."""
        siem, system_state, sim_time = siem_system

        # Set a small limit for testing
        siem.alert_history_limit = 5

        # Generate 10 alerts (more than limit)
        for i in range(10):
            await system_state.append_audit_event({
                "simulation_time": sim_time.now(),
                "wall_time": time.time(),
                "message": f"Safety bypass {i}",
                "device": f"device_{i}",
                "user": "user",
                "data": {"action": "activate_safety_bypass", "result": "SUCCESS"},
            })
            await asyncio.sleep(0.1)

        await asyncio.sleep(1.5)

        # Should only keep last 5 alerts
        assert len(siem.alerts) <= siem.alert_history_limit


class TestAuditTrailIntegration:
    """Test integration with audit trail pipeline."""

    @pytest.mark.asyncio
    async def test_audit_trail_consumption(self, siem_system):
        """Test SIEM correctly consumes audit trail from DataStore."""
        siem, system_state, sim_time = siem_system

        initial_index = siem._last_processed_event_index

        # Add events via SystemState
        for i in range(5):
            await system_state.append_audit_event({
                "simulation_time": sim_time.now(),
                "wall_time": time.time(),
                "message": f"Audit event {i}",
                "device": "test",
                "user": "test",
                "data": {"action": "test", "result": "SUCCESS"},
            })

        await asyncio.sleep(1.0)

        # SIEM should have processed new events
        assert siem._last_processed_event_index > initial_index
        assert siem.total_events_analyzed > 0

    @pytest.mark.asyncio
    async def test_incremental_processing(self, siem_system):
        """Test SIEM processes only new events incrementally."""
        siem, system_state, sim_time = siem_system

        # Add first batch
        for i in range(3):
            await system_state.append_audit_event({
                "simulation_time": sim_time.now(),
                "wall_time": time.time(),
                "message": f"Batch 1 event {i}",
                "device": "test",
                "user": "test",
                "data": {"action": "test", "result": "SUCCESS"},
            })

        await asyncio.sleep(1.0)
        count_after_batch1 = siem.total_events_analyzed
        index_after_batch1 = siem._last_processed_event_index

        # Add second batch
        for i in range(3):
            await system_state.append_audit_event({
                "simulation_time": sim_time.now(),
                "wall_time": time.time(),
                "message": f"Batch 2 event {i}",
                "device": "test",
                "user": "test",
                "data": {"action": "test", "result": "SUCCESS"},
            })

        await asyncio.sleep(1.0)

        # Should have processed 3 more events
        assert siem.total_events_analyzed == count_after_batch1 + 3
        assert siem._last_processed_event_index == index_after_batch1 + 3