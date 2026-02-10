# components/devices/enterprise_zone/firewall.py
"""
Industrial Firewall for ICS/OT networks.

Network firewall specialized for industrial control systems.
Enforces zone-based segmentation, protocol filtering, and IP blocking.

Common ICS Firewalls:
- Palo Alto Networks (with ICS security profiles)
- Fortinet FortiGate (OT edition)
- Cisco Firepower with ICS add-ons
- Tofino Industrial Security Appliance
- Claroty Continuous Threat Detection

Capabilities:
- Zone-based policies (Purdue model enforcement)
- Protocol allow/deny rules
- Source IP blocking
- Rate limiting and connection tracking
- Deep packet inspection (DPI) for ICS protocols
- Stateful inspection
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from components.devices.core.base_device import BaseDevice
from components.security.logging_system import AlarmPriority, AlarmState, EventSeverity
from components.state.data_store import DataStore


class RuleAction(Enum):
    """Firewall rule action."""

    ALLOW = "allow"
    DENY = "deny"
    DROP = "drop"  # Silent drop (no response)
    REJECT = "reject"  # Explicit rejection (TCP RST)


class RuleProtocol(Enum):
    """Protocol identifiers for firewall rules."""

    ANY = "any"
    MODBUS_TCP = "modbus_tcp"
    DNP3 = "dnp3"
    S7 = "s7"
    OPCUA = "opcua"
    ETHERNET_IP = "ethernet_ip"
    IEC104 = "iec104"
    GOOSE = "goose"
    HTTP = "http"
    HTTPS = "https"
    SSH = "ssh"
    TELNET = "telnet"
    FTP = "ftp"
    SMB = "smb"


@dataclass
class FirewallRule:
    """Firewall rule definition."""

    rule_id: str
    name: str
    enabled: bool
    priority: int  # Lower number = higher priority
    action: RuleAction

    # Source criteria
    source_zone: str = "any"
    source_network: str = "any"
    source_ip: str = "any"

    # Destination criteria
    dest_zone: str = "any"
    dest_network: str = "any"
    dest_ip: str = "any"
    dest_port: int | None = None

    # Protocol
    protocol: RuleProtocol = RuleProtocol.ANY

    # Metadata
    description: str = ""
    created_by: str = "system"
    created_at: float = 0.0
    hit_count: int = 0
    last_hit: float = 0.0

    # Logging
    log_matches: bool = True


@dataclass
class BlockedConnection:
    """Blocked connection attempt log."""

    timestamp: float
    source_ip: str
    dest_ip: str
    dest_port: int
    protocol: str
    rule_id: str
    reason: str


class Firewall(BaseDevice):
    """
    Industrial network firewall.

    Enforces zone-based segmentation and protocol filtering for ICS networks.
    Integrates with protocol_simulator to block unauthorized connections.

    Detection and Prevention:
    - Zone boundary enforcement (Purdue model)
    - Protocol whitelisting/blacklisting
    - IP address blocking (attacker containment)
    - Rate limiting (DoS prevention)
    - Connection state tracking

    Example:
        >>> firewall = Firewall(
        ...     device_name="firewall_primary",
        ...     device_id=500,
        ...     data_store=data_store
        ... )
        >>> await firewall.start()
        >>> # Add rule to block attacker
        >>> await firewall.add_rule(
        ...     name="Block attacker IP",
        ...     action=RuleAction.DROP,
        ...     source_ip="192.168.1.100",
        ...     reason="Malicious scanning detected"
        ... )
        >>> # Check if connection allowed
        >>> allowed = await firewall.check_connection(
        ...     source_ip="192.168.1.100",
        ...     dest_ip="10.10.1.5",
        ...     dest_port=502,
        ...     protocol="modbus_tcp"
        ... )
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        description: str = "Industrial Firewall",
        scan_interval: float = 1.0,
        log_dir: Path | None = None,
        block_history_limit: int = 1000,
    ):
        """
        Initialize firewall.

        Args:
            device_name: Unique device identifier
            device_id: Numeric ID
            data_store: DataStore instance
            description: Human-readable description
            scan_interval: Device scan cycle interval
            log_dir: Directory for log files
            block_history_limit: Maximum blocked connections to retain
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
        self.block_history_limit = block_history_limit
        self.default_action = RuleAction.ALLOW  # Default allow (can be changed)

        # Firewall rules (priority sorted)
        self.rules: list[FirewallRule] = []
        self._next_rule_id = 1

        # Statistics
        self.total_connections_checked = 0
        self.total_connections_allowed = 0
        self.total_connections_blocked = 0
        self.blocked_connections: list[BlockedConnection] = []

        # Alarm state
        self.block_rate_alarm_raised = False

        self.logger.info(
            f"Firewall '{device_name}' initialized (default_action={self.default_action.value})"
        )

    # ----------------------------------------------------------------
    # Configuration Loading
    # ----------------------------------------------------------------

    async def load_config(self, config: dict[str, Any]) -> None:
        """
        Load baseline configuration from config dict.

        Called during start() to load baseline rules and settings.
        Config is provided by ConfigLoader (respects layering).

        Args:
            config: Configuration dict with keys:
                - default_action: "allow" or "deny"
                - baseline_rules: List of rule definitions
        """
        # Set default action
        default_action_str = config.get("default_action", "allow")
        try:
            self.default_action = RuleAction[default_action_str.upper()]
        except KeyError:
            self.logger.warning(
                f"Invalid default_action '{default_action_str}', using ALLOW"
            )
            self.default_action = RuleAction.ALLOW

        # Load baseline rules
        baseline_rules = config.get("baseline_rules", [])
        for rule_def in baseline_rules:
            try:
                # Parse protocol
                protocol_str = rule_def.get("protocol", "ANY")
                try:
                    protocol = RuleProtocol[protocol_str.upper()]
                except KeyError:
                    self.logger.warning(
                        f"Invalid protocol '{protocol_str}' in rule '{rule_def.get('name')}', using ANY"
                    )
                    protocol = RuleProtocol.ANY

                # Parse action
                action_str = rule_def.get("action", "ALLOW")
                try:
                    action = RuleAction[action_str.upper()]
                except KeyError:
                    self.logger.warning(
                        f"Invalid action '{action_str}' in rule '{rule_def.get('name')}', using ALLOW"
                    )
                    action = RuleAction.ALLOW

                # Add rule (don't use await here to avoid audit log spam during startup)
                rule_id = f"BASELINE-{self._next_rule_id:05d}"
                self._next_rule_id += 1

                rule = FirewallRule(
                    rule_id=rule_id,
                    name=rule_def.get("name", f"Rule {rule_id}"),
                    enabled=rule_def.get("enabled", True),
                    priority=rule_def.get("priority", 100),
                    action=action,
                    source_zone=rule_def.get("source_zone", "any"),
                    source_network=rule_def.get("source_network", "any"),
                    source_ip=rule_def.get("source_ip", "any"),
                    dest_zone=rule_def.get("dest_zone", "any"),
                    dest_network=rule_def.get("dest_network", "any"),
                    dest_ip=rule_def.get("dest_ip", "any"),
                    dest_port=rule_def.get("dest_port"),
                    protocol=protocol,
                    description=rule_def.get("description", ""),
                    created_by="config",
                    created_at=self.sim_time.now(),
                )

                self.rules.append(rule)

                self.logger.info(
                    f"Loaded baseline rule: {rule.name} (priority {rule.priority}, action {rule.action.value})"
                )

            except Exception as e:
                self.logger.error(
                    f"Failed to load baseline rule '{rule_def.get('name', 'unknown')}': {e}"
                )

        # Sort rules by priority
        self._sort_rules()

        self.logger.info(
            f"Firewall config loaded: default_action={self.default_action.value}, "
            f"baseline_rules={len(self.rules)}"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return device type identifier."""
        return "firewall"

    def _supported_protocols(self) -> list[str]:
        """Firewall management protocols."""
        return ["https", "ssh", "snmp"]

    async def _initialise_memory_map(self) -> None:
        """Initialize firewall memory map with statistics."""
        self.memory_map.update(
            {
                "enabled": True,
                "default_action": self.default_action.value,
                "total_rules": 0,
                "active_rules": 0,
                "total_connections_checked": 0,
                "total_connections_allowed": 0,
                "total_connections_blocked": 0,
                "block_rate_per_minute": 0.0,
            }
        )

    async def _scan_cycle(self) -> None:
        """Periodic scan cycle - check alarm conditions."""
        # Update statistics in memory map
        self.memory_map["total_rules"] = len(self.rules)
        self.memory_map["active_rules"] = sum(1 for r in self.rules if r.enabled)
        self.memory_map["total_connections_checked"] = self.total_connections_checked
        self.memory_map["total_connections_allowed"] = self.total_connections_allowed
        self.memory_map["total_connections_blocked"] = self.total_connections_blocked

        # Calculate block rate (blocks per minute)
        recent_blocks = [
            b
            for b in self.blocked_connections
            if self.sim_time.now() - b.timestamp < 60.0
        ]
        block_rate = len(recent_blocks)
        self.memory_map["block_rate_per_minute"] = block_rate

        # Alarm if high block rate (possible attack)
        if block_rate > 50 and not self.block_rate_alarm_raised:
            await self.logger.log_alarm(
                message=f"Firewall '{self.device_name}': High block rate - {block_rate} blocks/min",
                priority=AlarmPriority.HIGH,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={"block_rate": block_rate, "threshold": 50},
            )
            self.block_rate_alarm_raised = True
        elif block_rate < 30 and self.block_rate_alarm_raised:
            await self.logger.log_alarm(
                message=f"Firewall '{self.device_name}': Block rate normalized",
                priority=AlarmPriority.HIGH,
                state=AlarmState.CLEARED,
                device=self.device_name,
                data={"block_rate": block_rate},
            )
            self.block_rate_alarm_raised = False

    # ----------------------------------------------------------------
    # Rule Management
    # ----------------------------------------------------------------

    async def add_rule(
        self,
        name: str,
        action: RuleAction,
        priority: int = 100,
        source_zone: str = "any",
        source_network: str = "any",
        source_ip: str = "any",
        dest_zone: str = "any",
        dest_network: str = "any",
        dest_ip: str = "any",
        dest_port: int | None = None,
        protocol: RuleProtocol = RuleProtocol.ANY,
        description: str = "",
        user: str = "system",
        reason: str = "",
    ) -> str:
        """
        Add firewall rule.

        Args:
            name: Rule name
            action: Rule action (ALLOW, DENY, DROP, REJECT)
            priority: Rule priority (lower = higher priority)
            source_zone: Source zone name or "any"
            source_network: Source network name or "any"
            source_ip: Source IP address or "any"
            dest_zone: Destination zone name or "any"
            dest_network: Destination network name or "any"
            dest_ip: Destination IP address or "any"
            dest_port: Destination port or None for any
            protocol: Protocol to match
            description: Rule description
            user: User adding the rule
            reason: Reason for adding rule

        Returns:
            Rule ID
        """
        rule_id = f"FW-{self._next_rule_id:05d}"
        self._next_rule_id += 1

        rule = FirewallRule(
            rule_id=rule_id,
            name=name,
            enabled=True,
            priority=priority,
            action=action,
            source_zone=source_zone,
            source_network=source_network,
            source_ip=source_ip,
            dest_zone=dest_zone,
            dest_network=dest_network,
            dest_ip=dest_ip,
            dest_port=dest_port,
            protocol=protocol,
            description=description,
            created_by=user,
            created_at=self.sim_time.now(),
        )

        self.rules.append(rule)
        self._sort_rules()

        await self.logger.log_audit(
            message=f"Firewall rule added: {name} ({action.value}) by {user}",
            user=user,
            action="add_firewall_rule",
            data={
                "rule_id": rule_id,
                "name": name,
                "action": action.value,
                "priority": priority,
                "source_ip": source_ip,
                "dest_ip": dest_ip,
                "dest_port": dest_port,
                "protocol": protocol.value,
                "reason": reason,
            },
        )

        self.logger.info(
            f"Firewall rule added: {rule_id} - {name} (priority {priority}, action {action.value})"
        )

        return rule_id

    async def remove_rule(
        self, rule_id: str, user: str = "system", reason: str = ""
    ) -> bool:
        """
        Remove firewall rule.

        Args:
            rule_id: Rule ID to remove
            user: User removing the rule
            reason: Reason for removal

        Returns:
            True if rule removed, False if not found
        """
        for i, rule in enumerate(self.rules):
            if rule.rule_id == rule_id:
                self.rules.pop(i)

                await self.logger.log_audit(
                    message=f"Firewall rule removed: {rule.name} by {user}",
                    user=user,
                    action="remove_firewall_rule",
                    data={
                        "rule_id": rule_id,
                        "name": rule.name,
                        "reason": reason,
                    },
                )

                self.logger.info(f"Firewall rule removed: {rule_id}")
                return True

        return False

    async def enable_rule(self, rule_id: str, user: str = "system") -> bool:
        """Enable firewall rule."""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                rule.enabled = True
                await self.logger.log_audit(
                    message=f"Firewall rule enabled: {rule.name} by {user}",
                    user=user,
                    action="enable_firewall_rule",
                    data={"rule_id": rule_id},
                )
                return True
        return False

    async def disable_rule(self, rule_id: str, user: str = "system") -> bool:
        """Disable firewall rule."""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                rule.enabled = False
                await self.logger.log_audit(
                    message=f"Firewall rule disabled: {rule.name} by {user}",
                    user=user,
                    action="disable_firewall_rule",
                    data={"rule_id": rule_id},
                )
                return True
        return False

    def _sort_rules(self) -> None:
        """Sort rules by priority (lower number = higher priority)."""
        self.rules.sort(key=lambda r: r.priority)

    # ----------------------------------------------------------------
    # Connection Checking (Called by protocol_simulator)
    # ----------------------------------------------------------------

    async def check_connection(
        self,
        source_ip: str,
        source_network: str = "unknown",
        source_zone: str = "unknown",
        dest_ip: str = "unknown",
        dest_network: str = "unknown",
        dest_zone: str = "unknown",
        dest_port: int = 0,
        protocol: str = "unknown",
    ) -> tuple[bool, str]:
        """
        Check if connection is allowed by firewall rules.

        Called by protocol_simulator before accepting connection.

        Args:
            source_ip: Source IP address
            source_network: Source network name
            source_zone: Source zone name
            dest_ip: Destination IP address
            dest_network: Destination network name
            dest_zone: Destination zone name
            dest_port: Destination port
            protocol: Protocol name

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        self.total_connections_checked += 1

        # Check each rule in priority order
        for rule in self.rules:
            if not rule.enabled:
                continue

            # Check if rule matches
            if self._rule_matches(
                rule,
                source_ip,
                source_network,
                source_zone,
                dest_ip,
                dest_network,
                dest_zone,
                dest_port,
                protocol,
            ):
                # Rule matched - apply action
                rule.hit_count += 1
                rule.last_hit = self.sim_time.now()

                if rule.action in (RuleAction.ALLOW,):
                    self.total_connections_allowed += 1

                    if rule.log_matches:
                        self.logger.debug(
                            f"Firewall ALLOW: {source_ip} -> {dest_ip}:{dest_port} "
                            f"({protocol}) - Rule: {rule.name}"
                        )

                    return True, f"Allowed by rule {rule.rule_id}: {rule.name}"

                else:  # DENY, DROP, REJECT
                    self.total_connections_blocked += 1

                    # Log blocked connection
                    blocked = BlockedConnection(
                        timestamp=self.sim_time.now(),
                        source_ip=source_ip,
                        dest_ip=dest_ip,
                        dest_port=dest_port,
                        protocol=protocol,
                        rule_id=rule.rule_id,
                        reason=rule.name,
                    )
                    self.blocked_connections.append(blocked)

                    # Trim history
                    if len(self.blocked_connections) > self.block_history_limit:
                        self.blocked_connections = self.blocked_connections[
                            -self.block_history_limit :
                        ]

                    if rule.log_matches:
                        await self.logger.log_security(
                            f"Firewall BLOCK: {source_ip} -> {dest_ip}:{dest_port} "
                            f"({protocol}) - Rule: {rule.name}",
                            severity=EventSeverity.WARNING,
                            data={
                                "source_ip": source_ip,
                                "source_zone": source_zone,
                                "dest_ip": dest_ip,
                                "dest_port": dest_port,
                                "protocol": protocol,
                                "rule_id": rule.rule_id,
                                "rule_name": rule.name,
                                "action": rule.action.value,
                            },
                        )

                    return False, f"Blocked by rule {rule.rule_id}: {rule.name}"

        # No rule matched - apply default action
        if self.default_action == RuleAction.ALLOW:
            self.total_connections_allowed += 1
            return True, "Allowed by default policy"
        else:
            self.total_connections_blocked += 1
            return False, "Blocked by default policy"

    def _rule_matches(
        self,
        rule: FirewallRule,
        source_ip: str,
        source_network: str,
        source_zone: str,
        dest_ip: str,
        dest_network: str,
        dest_zone: str,
        dest_port: int,
        protocol: str,
    ) -> bool:
        """Check if rule matches connection criteria."""
        # Source IP
        if rule.source_ip != "any" and rule.source_ip != source_ip:
            return False

        # Source network
        if rule.source_network != "any" and rule.source_network != source_network:
            return False

        # Source zone
        if rule.source_zone != "any" and rule.source_zone != source_zone:
            return False

        # Dest IP
        if rule.dest_ip != "any" and rule.dest_ip != dest_ip:
            return False

        # Dest network
        if rule.dest_network != "any" and rule.dest_network != dest_network:
            return False

        # Dest zone
        if rule.dest_zone != "any" and rule.dest_zone != dest_zone:
            return False

        # Dest port
        if rule.dest_port is not None and rule.dest_port != dest_port:
            return False

        # Protocol
        if rule.protocol != RuleProtocol.ANY and rule.protocol.value != protocol:
            return False

        return True

    # ----------------------------------------------------------------
    # Query Methods
    # ----------------------------------------------------------------

    def get_rules(self, enabled_only: bool = False) -> list[FirewallRule]:
        """Get all firewall rules."""
        if enabled_only:
            return [r for r in self.rules if r.enabled]
        return self.rules.copy()

    def get_rule(self, rule_id: str) -> FirewallRule | None:
        """Get specific rule by ID."""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                return rule
        return None

    def get_blocked_connections(
        self, limit: int = 100, source_ip: str | None = None
    ) -> list[BlockedConnection]:
        """Get recent blocked connections."""
        connections = self.blocked_connections[-limit:]
        if source_ip:
            connections = [c for c in connections if c.source_ip == source_ip]
        return connections

    def get_statistics(self) -> dict[str, Any]:
        """Get firewall statistics."""
        return {
            "total_rules": len(self.rules),
            "active_rules": sum(1 for r in self.rules if r.enabled),
            "total_connections_checked": self.total_connections_checked,
            "total_connections_allowed": self.total_connections_allowed,
            "total_connections_blocked": self.total_connections_blocked,
            "block_rate_per_minute": self.memory_map.get("block_rate_per_minute", 0.0),
            "blocked_connections_history": len(self.blocked_connections),
        }
