# components/devices/enterprise_zone/ids_system.py
"""
IDS (Intrusion Detection System) for ICS networks.

Network-based intrusion detection specialized for industrial protocols.
Monitors network traffic, detects protocol violations, scanning attempts,
and known attack patterns targeting ICS/SCADA systems.

Common IDS products: Nozomi Networks, Claroty, Dragos Platform, Cisco Cyber Vision

Detection capabilities:
- ICS protocol violations (Modbus, DNP3, OPC UA, IEC 104)
- Network scanning and reconnaissance
- Unauthorized access attempts
- Man-in-the-middle attacks
- Known ICS malware signatures
- Anomalous traffic patterns
- Command injection attempts
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from components.devices.core.base_device import BaseDevice
from components.security.logging_system import (
    AlarmPriority,
    AlarmState,
    EventSeverity,
)
from components.state.data_store import DataStore


class AlertSeverity(Enum):
    """IDS alert severity levels."""

    CRITICAL = "critical"  # Active attack, immediate threat
    HIGH = "high"  # Serious vulnerability or attack attempt
    MEDIUM = "medium"  # Suspicious activity, policy violation
    LOW = "low"  # Informational, anomaly detected
    INFO = "info"  # Normal but noteworthy activity


class AlertStatus(Enum):
    """IDS alert lifecycle status."""

    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    FALSE_POSITIVE = "false_positive"
    CLOSED = "closed"


@dataclass
class IDSAlert:
    """IDS alert/detection."""

    alert_id: str
    timestamp: float
    severity: AlertSeverity
    status: AlertStatus
    rule_name: str
    category: str
    title: str
    description: str
    source_ip: str
    destination_ip: str
    protocol: str
    affected_devices: list[str] = field(default_factory=list)
    indicators: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    assigned_to: str = ""
    false_positive_reason: str = ""


class IDSSystem(BaseDevice):
    """
    Network-based IDS for ICS environments.

    Monitors network traffic for suspicious patterns, protocol violations,
    and known attack signatures. Generates alerts and logs to audit trail.

    Detection Rules:
    1. Network Scanning: Detects port scans and reconnaissance
    2. Protocol Violations: Invalid Modbus/DNP3/OPC UA commands
    3. Unauthorized Access: Access from unexpected sources
    4. Known Malware: ICS malware signatures (Stuxnet, Triton, etc.)
    5. Anomalous Traffic: Unusual patterns or volumes
    6. Command Injection: Malicious payloads in protocol messages

    Example:
        >>> ids = IDSSystem(
        ...     device_name="ids_primary",
        ...     device_id=400,
        ...     data_store=data_store,
        ...     analysis_interval=1.0
        ... )
        >>> await ids.start()
        >>> alerts = ids.get_active_alerts(severity=AlertSeverity.CRITICAL)
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        analysis_interval: float = 2.0,
        alert_history_limit: int = 1000,
        description: str = "",
        scan_interval: float = 1.0,
        log_dir: Path | None = None,
    ):
        """
        Initialize IDS system.

        Args:
            device_name: Unique device identifier
            device_id: Numeric ID for protocol addressing
            data_store: DataStore instance
            analysis_interval: How often to analyze traffic (seconds)
            alert_history_limit: Maximum alerts to retain
            description: Human-readable description
            scan_interval: Device scan cycle interval
            log_dir: Directory for log files
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
            log_dir=log_dir,
        )

        # Configuration
        self.analysis_interval = analysis_interval
        self.alert_history_limit = alert_history_limit

        # Detection state
        self.alerts: list[IDSAlert] = []
        self.total_packets_analyzed = 0
        self.total_alerts_generated = 0

        # Detection rule state tracking
        self.scan_tracker: dict[str, list[tuple[str, float]]] = (
            {}
        )  # source_ip -> [(dest_ip, timestamp), ...]
        self.protocol_violations: dict[str, int] = {}  # device -> count
        self.unauthorized_access_attempts: dict[str, int] = {}  # source_ip -> count
        self.traffic_baseline: dict[str, int] = {}  # device -> normal packet count

        # Detection thresholds
        self.scan_threshold = 5  # ports scanned in time window
        self.scan_time_window = 60.0  # seconds
        self.violation_threshold = 3  # protocol violations
        self.unauthorized_threshold = 3  # unauthorized access attempts
        self.traffic_anomaly_multiplier = 3.0  # 3x normal traffic

        # Known malware signatures (simplified patterns)
        self.malware_signatures = {
            "stuxnet": ["S7-315", "DB890", "FC1869"],
            "triton": ["TRISTATION", "TS_cnames.py", "inject.bin"],
            "industroyer": ["IEC-104", "MMS-GOOSE", "OPC-DA"],
            "havex": ["lighttpd", "OPC-Proxy", "remote-exec"],
        }

        # Alarm state
        self.critical_alerts_alarm_raised = False
        self.scan_detection_alarm_raised = False

        self.logger.info(
            f"IDS system '{device_name}' initialized "
            f"(analysis_interval={analysis_interval}s, alert_limit={alert_history_limit})"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return device type identifier."""
        return "ids_system"

    def _supported_protocols(self) -> list[str]:
        """
        IDS monitors multiple protocols.

        Returns:
            List of monitored protocols
        """
        return ["span", "tap", "syslog", "netflow", "snmp"]

    async def _initialise_memory_map(self) -> None:
        """Initialize IDS memory map with statistics."""
        self.memory_map.update(
            {
                "total_packets_analyzed": 0,
                "total_alerts_generated": 0,
                "active_alerts": 0,
                "critical_alerts": 0,
                "high_alerts": 0,
                "medium_alerts": 0,
                "low_alerts": 0,
                "analysis_interval": self.analysis_interval,
                "scan_detections": 0,
                "protocol_violations": 0,
                "unauthorized_access": 0,
                "malware_detections": 0,
            }
        )

        self.logger.debug("IDS memory map initialized")

    async def _scan_cycle(self) -> None:
        """
        Execute IDS scan cycle.

        Analyzes network traffic, runs detection rules, generates alerts,
        and monitors for alarm conditions.
        """
        try:
            # Simulate network packet capture and analysis
            await self._analyze_network_traffic()

            # Run detection rules
            await self._run_detection_rules()

            # Trim alert history
            self._trim_alert_history()

            # Check for alarm conditions
            await self._check_alarm_conditions()

            # Update memory map statistics
            await self._update_statistics()

        except Exception as e:
            self.logger.error(f"IDS scan cycle error: {e}", exc_info=True)
            await self.logger.log_alarm(
                message=f"IDS '{self.device_name}': Critical error in detection engine",
                priority=AlarmPriority.HIGH,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={"error": str(e)},
            )

    # ----------------------------------------------------------------
    # Network traffic analysis
    # ----------------------------------------------------------------

    async def _analyze_network_traffic(self) -> None:
        """
        Analyze captured network traffic.

        In a real IDS, this would process packets from SPAN/TAP.
        For simulation, we query network activity from DataStore.
        """
        try:
            # Get all online devices to simulate traffic
            devices = await self.data_store.get_all_device_states()

            # Simulate packet analysis
            for device_name, device_state in devices.items():
                if device_state.online:
                    # Simulate analyzing packets from this device
                    packet_count = len(device_state.protocols) * 10
                    self.total_packets_analyzed += packet_count

                    # Track baseline traffic
                    if device_name not in self.traffic_baseline:
                        self.traffic_baseline[device_name] = packet_count

        except Exception as e:
            self.logger.error(f"Traffic analysis error: {e}", exc_info=True)

    # ----------------------------------------------------------------
    # Detection rules
    # ----------------------------------------------------------------

    async def _run_detection_rules(self) -> None:
        """Run all detection rules against captured traffic."""
        await self._detect_network_scanning()
        await self._detect_protocol_violations()
        await self._detect_unauthorized_access()
        await self._detect_malware_signatures()
        await self._detect_traffic_anomalies()

    async def _detect_network_scanning(self) -> None:
        """
        Detect network scanning and reconnaissance.

        Detects port scans by tracking connection attempts from single source
        to multiple destinations in short time window.
        """
        try:
            # Simulate scanning detection by checking network simulator events
            network_events = await self.data_store.get_audit_log(
                limit=100, event_type="network_access"
            )

            current_time = self.sim_time.now()

            for event in network_events:
                if "DENIED" in str(event.get("data", {})):
                    source = event.get("data", {}).get("source_network", "unknown")
                    target = event.get("device", "unknown")
                    timestamp = event.get("simulation_time", current_time)

                    # Track scan attempts
                    if source not in self.scan_tracker:
                        self.scan_tracker[source] = []

                    self.scan_tracker[source].append((target, timestamp))

                    # Clean old entries
                    self.scan_tracker[source] = [
                        (t, ts)
                        for t, ts in self.scan_tracker[source]
                        if current_time - ts < self.scan_time_window
                    ]

                    # Check threshold
                    unique_targets = len({t for t, _ in self.scan_tracker[source]})
                    if unique_targets >= self.scan_threshold:
                        await self._generate_alert(
                            severity=AlertSeverity.HIGH,
                            rule_name="network_scanning",
                            category="reconnaissance",
                            title=f"Network Scan Detected from {source}",
                            description=f"Source {source} attempted to access {unique_targets} different targets in {self.scan_time_window}s window",
                            source_ip=source,
                            destination_ip="multiple",
                            protocol="multiple",
                            affected_devices=list(
                                {t for t, _ in self.scan_tracker[source]}
                            ),
                            indicators={
                                "targets_scanned": unique_targets,
                                "time_window": self.scan_time_window,
                                "threshold": self.scan_threshold,
                            },
                        )

                        # Clear tracker to avoid duplicate alerts
                        self.scan_tracker[source] = []

        except Exception as e:
            self.logger.error(f"Scan detection error: {e}", exc_info=True)

    async def _detect_protocol_violations(self) -> None:
        """
        Detect ICS protocol violations.

        Monitors for invalid commands, malformed packets, or protocol abuse
        in Modbus, DNP3, OPC UA, and other ICS protocols.
        """
        try:
            # Check for protocol violations in device diagnostics
            devices = await self.data_store.get_all_device_states()

            for device_name, device_state in devices.items():
                if not device_state.online:
                    continue

                # Check for diagnostic faults (simulated protocol violations)
                diagnostic_fault = device_state.memory_map.get(
                    "_diagnostic_fault", False
                )

                if diagnostic_fault:
                    self.protocol_violations[device_name] = (
                        self.protocol_violations.get(device_name, 0) + 1
                    )

                    if (
                        self.protocol_violations[device_name]
                        >= self.violation_threshold
                    ):
                        protocols = ", ".join(device_state.protocols)

                        await self._generate_alert(
                            severity=AlertSeverity.MEDIUM,
                            rule_name="protocol_violation",
                            category="protocol_abuse",
                            title=f"Protocol Violations Detected on {device_name}",
                            description=f"Device {device_name} has {self.protocol_violations[device_name]} protocol violations",
                            source_ip="local",
                            destination_ip=device_name,
                            protocol=protocols,
                            affected_devices=[device_name],
                            indicators={
                                "violation_count": self.protocol_violations[
                                    device_name
                                ],
                                "protocols": device_state.protocols,
                                "threshold": self.violation_threshold,
                            },
                        )

                        # Reset counter
                        self.protocol_violations[device_name] = 0

        except Exception as e:
            self.logger.error(f"Protocol violation detection error: {e}", exc_info=True)

    async def _detect_unauthorized_access(self) -> None:
        """
        Detect unauthorized access attempts.

        Monitors authentication failures and access from unexpected sources.
        """
        try:
            # Check audit log for failed authentication
            auth_events = await self.data_store.get_audit_log(limit=50)

            for event in auth_events:
                message = event.get("message", "").lower()
                if (
                    "denied" in message
                    or "unauthorized" in message
                    or "failed" in message
                ):
                    source = event.get("data", {}).get(
                        "source_ip", event.get("user", "unknown")
                    )

                    self.unauthorized_access_attempts[source] = (
                        self.unauthorized_access_attempts.get(source, 0) + 1
                    )

                    if (
                        self.unauthorized_access_attempts[source]
                        >= self.unauthorized_threshold
                    ):
                        device = event.get("device", "unknown")

                        await self._generate_alert(
                            severity=AlertSeverity.HIGH,
                            rule_name="unauthorized_access",
                            category="access_control",
                            title=f"Multiple Unauthorized Access Attempts from {source}",
                            description=f"Source {source} has {self.unauthorized_access_attempts[source]} failed access attempts",
                            source_ip=source,
                            destination_ip=device,
                            protocol="authentication",
                            affected_devices=[device],
                            indicators={
                                "attempt_count": self.unauthorized_access_attempts[
                                    source
                                ],
                                "threshold": self.unauthorized_threshold,
                            },
                        )

                        # Reset counter
                        self.unauthorized_access_attempts[source] = 0

        except Exception as e:
            self.logger.error(
                f"Unauthorized access detection error: {e}", exc_info=True
            )

    async def _detect_malware_signatures(self) -> None:
        """
        Detect known ICS malware signatures.

        Scans for patterns associated with Stuxnet, Triton, Industroyer, etc.
        """
        try:
            # In real IDS, this would scan packet payloads
            # For simulation, check audit log for suspicious patterns
            events = await self.data_store.get_audit_log(limit=100)

            for event in events:
                message = event.get("message", "").lower()
                device = event.get("device", "unknown")

                # Check against known malware signatures
                for malware_name, patterns in self.malware_signatures.items():
                    matches = [p.lower() for p in patterns if p.lower() in message]

                    if len(matches) >= 2:  # Multiple pattern matches = high confidence
                        await self._generate_alert(
                            severity=AlertSeverity.CRITICAL,
                            rule_name="malware_detection",
                            category="malware",
                            title=f"Suspected {malware_name.upper()} Malware Activity",
                            description=f"Detected patterns associated with {malware_name} malware on {device}",
                            source_ip="unknown",
                            destination_ip=device,
                            protocol="multiple",
                            affected_devices=[device],
                            indicators={
                                "malware_family": malware_name,
                                "matched_patterns": matches,
                                "confidence": "high",
                            },
                        )

                        # Raise critical alarm
                        await self.logger.log_alarm(
                            message=f"IDS '{self.device_name}': CRITICAL - {malware_name.upper()} malware detected on {device}",
                            priority=AlarmPriority.CRITICAL,
                            state=AlarmState.ACTIVE,
                            device=self.device_name,
                            data={
                                "malware_family": malware_name,
                                "affected_device": device,
                                "matched_patterns": matches,
                            },
                        )

        except Exception as e:
            self.logger.error(f"Malware detection error: {e}", exc_info=True)

    async def _detect_traffic_anomalies(self) -> None:
        """
        Detect traffic anomalies.

        Identifies unusual traffic volumes or patterns that deviate from baseline.
        """
        try:
            devices = await self.data_store.get_all_device_states()

            for device_name, device_state in devices.items():
                if not device_state.online or device_name not in self.traffic_baseline:
                    continue

                # Simulate current traffic volume
                current_traffic = len(device_state.protocols) * 10
                baseline = self.traffic_baseline[device_name]

                if current_traffic > baseline * self.traffic_anomaly_multiplier:
                    await self._generate_alert(
                        severity=AlertSeverity.MEDIUM,
                        rule_name="traffic_anomaly",
                        category="anomaly",
                        title=f"Traffic Anomaly on {device_name}",
                        description=f"Traffic volume {current_traffic} packets exceeds baseline {baseline} by {self.traffic_anomaly_multiplier}x",
                        source_ip=device_name,
                        destination_ip="network",
                        protocol="multiple",
                        affected_devices=[device_name],
                        indicators={
                            "current_traffic": current_traffic,
                            "baseline_traffic": baseline,
                            "multiplier": self.traffic_anomaly_multiplier,
                        },
                    )

        except Exception as e:
            self.logger.error(f"Traffic anomaly detection error: {e}", exc_info=True)

    # ----------------------------------------------------------------
    # Alert management
    # ----------------------------------------------------------------

    async def _generate_alert(
        self,
        severity: AlertSeverity,
        rule_name: str,
        category: str,
        title: str,
        description: str,
        source_ip: str,
        destination_ip: str,
        protocol: str,
        affected_devices: list[str],
        indicators: dict[str, Any],
    ) -> IDSAlert:
        """
        Generate and store IDS alert.

        Args:
            severity: Alert severity level
            rule_name: Detection rule that triggered
            category: Alert category
            title: Brief alert title
            description: Detailed description
            source_ip: Source IP/identifier
            destination_ip: Destination IP/identifier
            protocol: Protocol involved
            affected_devices: List of affected devices
            indicators: IOCs and detection indicators

        Returns:
            Created IDSAlert
        """
        alert = IDSAlert(
            alert_id=str(uuid4()),
            timestamp=self.sim_time.now(),
            severity=severity,
            status=AlertStatus.NEW,
            rule_name=rule_name,
            category=category,
            title=title,
            description=description,
            source_ip=source_ip,
            destination_ip=destination_ip,
            protocol=protocol,
            affected_devices=affected_devices,
            indicators=indicators,
        )

        self.alerts.append(alert)
        self.total_alerts_generated += 1

        # Log to audit trail
        await self.logger.log_audit(
            message=f"IDS Alert: {title}",
            user="ids_system",
            action="ids_detection",
            result="ALERT_GENERATED",
            data={
                "ids_system": self.device_name,
                "alert_id": alert.alert_id,
                "severity": severity.value,
                "rule_name": rule_name,
                "category": category,
                "source": source_ip,
                "destination": destination_ip,
                "protocol": protocol,
                "affected_devices": affected_devices,
                "indicators": indicators,
            },
        )

        self.logger.warning(f"IDS Alert [{severity.value.upper()}]: {title}")

        return alert

    async def update_alert_status(
        self,
        alert_id: str,
        status: AlertStatus,
        assigned_to: str = "",
        note: str = "",
        false_positive_reason: str = "",
    ) -> bool:
        """
        Update alert status and assignment.

        Args:
            alert_id: Alert to update
            status: New status
            assigned_to: Analyst assigned
            note: Status update note
            false_positive_reason: Reason if marking false positive

        Returns:
            True if updated successfully
        """
        for alert in self.alerts:
            if alert.alert_id == alert_id:
                old_status = alert.status
                alert.status = status

                if assigned_to:
                    alert.assigned_to = assigned_to

                if note:
                    alert.notes.append(f"[{self.sim_time.now():.1f}] {note}")

                if false_positive_reason:
                    alert.false_positive_reason = false_positive_reason

                # Audit log
                await self.logger.log_audit(
                    message=f"IDS alert {alert_id} status changed: {old_status.value} -> {status.value}",
                    user=assigned_to or "system",
                    action="ids_alert_update",
                    result="SUCCESS",
                    data={
                        "ids_system": self.device_name,
                        "alert_id": alert_id,
                        "old_status": old_status.value,
                        "new_status": status.value,
                        "assigned_to": assigned_to,
                        "note": note,
                    },
                )

                self.logger.info(f"Alert {alert_id} status updated to {status.value}")
                return True

        self.logger.warning(f"Alert {alert_id} not found")
        return False

    def get_active_alerts(
        self, severity: AlertSeverity | None = None, category: str | None = None
    ) -> list[IDSAlert]:
        """
        Get active (non-closed) alerts.

        Args:
            severity: Filter by severity (optional)
            category: Filter by category (optional)

        Returns:
            List of matching alerts
        """
        alerts = [
            a
            for a in self.alerts
            if a.status not in [AlertStatus.CLOSED, AlertStatus.FALSE_POSITIVE]
        ]

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        if category:
            alerts = [a for a in alerts if a.category == category]

        return alerts

    def get_all_alerts(
        self, severity: AlertSeverity | None = None, category: str | None = None
    ) -> list[IDSAlert]:
        """
        Get all alerts (including closed).

        Args:
            severity: Filter by severity (optional)
            category: Filter by category (optional)

        Returns:
            List of matching alerts
        """
        alerts = self.alerts.copy()

        if severity:
            alerts = [a for a in alerts if a.severity == severity]

        if category:
            alerts = [a for a in alerts if a.category == category]

        return alerts

    def _trim_alert_history(self) -> None:
        """Trim alert history to configured limit."""
        if len(self.alerts) > self.alert_history_limit:
            # Keep most recent alerts, prioritizing unresolved
            active = [
                a
                for a in self.alerts
                if a.status not in [AlertStatus.CLOSED, AlertStatus.FALSE_POSITIVE]
            ]
            closed = [
                a
                for a in self.alerts
                if a.status in [AlertStatus.CLOSED, AlertStatus.FALSE_POSITIVE]
            ]

            # Keep all active + recent closed
            closed.sort(key=lambda a: a.timestamp, reverse=True)
            max_closed = self.alert_history_limit - len(active)
            self.alerts = active + closed[:max_closed]

    # ----------------------------------------------------------------
    # Alarm conditions
    # ----------------------------------------------------------------

    async def _check_alarm_conditions(self) -> None:
        """Check for conditions requiring alarm escalation."""
        # Critical alerts alarm
        critical_count = len(
            [
                a
                for a in self.alerts
                if a.severity == AlertSeverity.CRITICAL and a.status == AlertStatus.NEW
            ]
        )

        if critical_count > 0 and not self.critical_alerts_alarm_raised:
            await self.logger.log_alarm(
                message=f"IDS '{self.device_name}': {critical_count} CRITICAL alert(s) require immediate attention",
                priority=AlarmPriority.CRITICAL,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={
                    "critical_alert_count": critical_count,
                    "alert_ids": [
                        a.alert_id
                        for a in self.alerts
                        if a.severity == AlertSeverity.CRITICAL
                        and a.status == AlertStatus.NEW
                    ],
                },
            )
            self.critical_alerts_alarm_raised = True

        elif critical_count == 0 and self.critical_alerts_alarm_raised:
            # Clear alarm
            await self.logger.log_alarm(
                message=f"IDS '{self.device_name}': All critical alerts resolved",
                priority=AlarmPriority.CRITICAL,
                state=AlarmState.CLEARED,
                device=self.device_name,
                data={"critical_alert_count": 0},
            )
            self.critical_alerts_alarm_raised = False

        # Network scanning alarm
        scan_detections = len(
            [
                a
                for a in self.alerts
                if a.rule_name == "network_scanning" and a.status == AlertStatus.NEW
            ]
        )

        if scan_detections >= 3 and not self.scan_detection_alarm_raised:
            await self.logger.log_alarm(
                message=f"IDS '{self.device_name}': Multiple network scans detected - possible reconnaissance",
                priority=AlarmPriority.HIGH,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={"scan_detection_count": scan_detections},
            )
            self.scan_detection_alarm_raised = True

        elif scan_detections < 3 and self.scan_detection_alarm_raised:
            await self.logger.log_alarm(
                message=f"IDS '{self.device_name}': Scan activity subsided",
                priority=AlarmPriority.HIGH,
                state=AlarmState.CLEARED,
                device=self.device_name,
                data={"scan_detection_count": scan_detections},
            )
            self.scan_detection_alarm_raised = False

    # ----------------------------------------------------------------
    # Statistics and reporting
    # ----------------------------------------------------------------

    async def _update_statistics(self) -> None:
        """Update memory map statistics."""
        active_alerts = self.get_active_alerts()

        self.memory_map.update(
            {
                "total_packets_analyzed": self.total_packets_analyzed,
                "total_alerts_generated": self.total_alerts_generated,
                "active_alerts": len(active_alerts),
                "critical_alerts": len(
                    [a for a in active_alerts if a.severity == AlertSeverity.CRITICAL]
                ),
                "high_alerts": len(
                    [a for a in active_alerts if a.severity == AlertSeverity.HIGH]
                ),
                "medium_alerts": len(
                    [a for a in active_alerts if a.severity == AlertSeverity.MEDIUM]
                ),
                "low_alerts": len(
                    [a for a in active_alerts if a.severity == AlertSeverity.LOW]
                ),
                "scan_detections": len(
                    [a for a in self.alerts if a.rule_name == "network_scanning"]
                ),
                "protocol_violations": sum(self.protocol_violations.values()),
                "unauthorized_access": sum(self.unauthorized_access_attempts.values()),
                "malware_detections": len(
                    [a for a in self.alerts if a.rule_name == "malware_detection"]
                ),
            }
        )

    def get_statistics(self) -> dict[str, Any]:
        """
        Get IDS statistics.

        Returns:
            Dictionary with traffic analysis and detection stats
        """
        active_alerts = self.get_active_alerts()

        return {
            "traffic": {
                "total_packets_analyzed": self.total_packets_analyzed,
                "analysis_interval": self.analysis_interval,
            },
            "alerts": {
                "total_generated": self.total_alerts_generated,
                "active": len(active_alerts),
                "by_severity": {
                    "critical": len(
                        [
                            a
                            for a in active_alerts
                            if a.severity == AlertSeverity.CRITICAL
                        ]
                    ),
                    "high": len(
                        [a for a in active_alerts if a.severity == AlertSeverity.HIGH]
                    ),
                    "medium": len(
                        [a for a in active_alerts if a.severity == AlertSeverity.MEDIUM]
                    ),
                    "low": len(
                        [a for a in active_alerts if a.severity == AlertSeverity.LOW]
                    ),
                },
            },
            "detections": {
                "scan_detections": len(
                    [a for a in self.alerts if a.rule_name == "network_scanning"]
                ),
                "protocol_violations": len(
                    [a for a in self.alerts if a.rule_name == "protocol_violation"]
                ),
                "unauthorized_access": len(
                    [a for a in self.alerts if a.rule_name == "unauthorized_access"]
                ),
                "malware_detections": len(
                    [a for a in self.alerts if a.rule_name == "malware_detection"]
                ),
                "traffic_anomalies": len(
                    [a for a in self.alerts if a.rule_name == "traffic_anomaly"]
                ),
            },
            "system": {
                "alert_history_size": len(self.alerts),
                "alert_history_limit": self.alert_history_limit,
            },
        }

    def get_summary(self) -> str:
        """
        Get human-readable summary.

        Returns:
            Formatted status string
        """
        stats = self.get_statistics()

        summary = f"""IDS System: {self.device_name}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Status: {'ONLINE' if self._online else 'OFFLINE'}
Analysis Interval: {self.analysis_interval}s

Traffic Analysis:
  Packets Analyzed: {stats['traffic']['total_packets_analyzed']}

Alerts:
  Total Generated: {stats['alerts']['total_generated']}
  Active: {stats['alerts']['active']}
  - CRITICAL: {stats['alerts']['by_severity']['critical']}
  - HIGH: {stats['alerts']['by_severity']['high']}
  - MEDIUM: {stats['alerts']['by_severity']['medium']}
  - LOW: {stats['alerts']['by_severity']['low']}

Detections:
  Network Scans: {stats['detections']['scan_detections']}
  Protocol Violations: {stats['detections']['protocol_violations']}
  Unauthorized Access: {stats['detections']['unauthorized_access']}
  Malware: {stats['detections']['malware_detections']}
  Traffic Anomalies: {stats['detections']['traffic_anomalies']}
"""
        return summary
