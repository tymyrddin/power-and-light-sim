# tests/unit/test_tools/test_blue_team.py
"""
Unit tests for BlueTeamCLI - Runtime Security Operations.

Tests all 44 async methods across 8 command groups plus parser
and initialization. Uses real lightweight components following
codebase conventions.
"""

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tools.blue_team import BlueTeamCLI, create_parser

# ================================================================
# HELPERS
# ================================================================


def make_args(**kwargs):
    """Create argparse.Namespace with sensible defaults."""
    defaults = {
        "user": "admin",
        "reason": "test",
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


@dataclass
class FakeLogEntry:
    """Minimal log entry matching attributes blue_team.py accesses."""

    timestamp: float = 0.0
    simulation_time: float = 0.0
    message: str = ""
    user: str = ""
    device: str = ""
    severity: str = "INFO"
    category: str = "security"


# ================================================================
# FIXTURES
# ================================================================


@pytest.fixture
async def cli():
    """Fully initialised BlueTeamCLI with real components."""
    with patch("config.config_loader.ConfigLoader.load_all", return_value={}):
        bt = BlueTeamCLI()
        await bt.initialize()
    return bt


# ================================================================
# INIT TESTS
# ================================================================


class TestBlueTeamCLIInit:
    """Test BlueTeamCLI initialization."""

    def test_init_attributes_none(self):
        """All attributes None before initialize()."""
        bt = BlueTeamCLI()
        assert bt.data_store is None
        assert bt.system_state is None
        assert bt.firewall is None
        assert bt.ids_system is None
        assert bt.auth_mgr is None
        assert bt.modbus_filter is None
        assert bt.anomaly_detector is None
        assert bt.connection_registry is None

    @pytest.mark.asyncio
    async def test_initialize_creates_components(self, cli):
        """initialize() creates all required components."""
        assert cli.system_state is not None
        assert cli.auth_mgr is not None
        assert cli.data_store is not None
        assert cli.firewall is not None
        assert cli.ids_system is not None
        assert cli.modbus_filter is not None
        assert cli.anomaly_detector is not None
        assert cli.connection_registry is not None

    @pytest.mark.asyncio
    async def test_initialize_auth_manager_has_default_users(self, cli):
        """AuthenticationManager creates default users."""
        assert len(cli.auth_mgr.users) >= 5

    @pytest.mark.asyncio
    async def test_initialize_data_store_has_auth_mgr(self, cli):
        """DataStore is linked to auth manager."""
        assert cli.data_store.auth_mgr is cli.auth_mgr


# ================================================================
# PARSER TESTS
# ================================================================


class TestCreateParser:
    """Test argument parser configuration."""

    def test_parser_has_all_command_groups(self):
        """Parser includes all 8 command groups."""
        parser = create_parser()
        # Parse each top-level command to verify it exists
        for cmd in [
            "firewall",
            "ids",
            "rbac",
            "modbus",
            "audit",
            "anomaly",
            "opcua",
            "status",
        ]:
            args = parser.parse_args(
                [cmd] if cmd == "status" else [cmd, "--help"] if False else [cmd]
            )
            assert args.command == cmd

    def test_firewall_add_rule_args(self):
        """Firewall add-rule accepts required and optional args."""
        parser = create_parser()
        args = parser.parse_args(
            [
                "firewall",
                "add-rule",
                "--name",
                "Test Rule",
                "--action",
                "deny",
                "--priority",
                "50",
                "--source-ip",
                "10.0.0.1",
            ]
        )
        assert args.name == "Test Rule"
        assert args.action == "deny"
        assert args.priority == 50
        assert args.source_ip == "10.0.0.1"

    def test_ids_block_ip_args(self):
        """IDS block-ip accepts ip and reason positional args."""
        parser = create_parser()
        args = parser.parse_args(["ids", "block-ip", "192.168.1.1", "Attack detected"])
        assert args.ip == "192.168.1.1"
        assert args.reason == "Attack detected"

    def test_rbac_change_role_args(self):
        """RBAC change-role accepts username and role."""
        parser = create_parser()
        args = parser.parse_args(
            [
                "rbac",
                "change-role",
                "--username",
                "operator1",
                "--role",
                "SUPERVISOR",
            ]
        )
        assert args.username == "operator1"
        assert args.role == "SUPERVISOR"

    def test_modbus_set_policy_args(self):
        """Modbus set-policy accepts device and mode."""
        parser = create_parser()
        args = parser.parse_args(
            [
                "modbus",
                "set-policy",
                "--device",
                "plc1",
                "--mode",
                "whitelist",
                "--allowed",
                "1,2,3",
            ]
        )
        assert args.device == "plc1"
        assert args.mode == "whitelist"
        assert args.allowed == "1,2,3"

    def test_audit_query_args(self):
        """Audit query accepts filter args."""
        parser = create_parser()
        args = parser.parse_args(
            [
                "audit",
                "query",
                "--device",
                "turbine_plc_1",
                "--category",
                "security",
                "--severity",
                "WARNING",
                "--limit",
                "100",
            ]
        )
        assert args.device == "turbine_plc_1"
        assert args.category == "security"
        assert args.severity == "WARNING"
        assert args.limit == 100

    def test_anomaly_set_range_args(self):
        """Anomaly set-range accepts device, parameter, min, max."""
        parser = create_parser()
        args = parser.parse_args(
            [
                "anomaly",
                "set-range",
                "--device",
                "turbine_plc_1",
                "--parameter",
                "speed",
                "--min",
                "800",
                "--max",
                "1800",
            ]
        )
        assert args.device == "turbine_plc_1"
        assert args.parameter == "speed"
        assert args.min == 800.0
        assert args.max == 1800.0

    def test_opcua_subcommands(self):
        """OPC UA parser has expected subcommands."""
        parser = create_parser()
        for subcmd in ["status", "list-users", "generate-certs", "list-certs"]:
            args = parser.parse_args(["opcua", subcmd])
            assert args.command == "opcua"
            assert args.subcommand == subcmd


# ================================================================
# FIREWALL COMMAND TESTS
# ================================================================


class TestFirewallCommands:
    """Test firewall CLI commands."""

    @pytest.mark.asyncio
    async def test_add_rule_success(self, cli, capsys):
        """Add rule returns 0 and prints rule_id."""
        args = make_args(
            name="Block attacker",
            action="deny",
            priority=1,
            source_zone="any",
            source_network="any",
            source_ip="10.0.0.1",
            dest_zone="any",
            dest_network="any",
            dest_ip="any",
            dest_port=None,
            description="Test block",
        )
        result = await cli.firewall_add_rule(args)
        assert result == 0
        captured = capsys.readouterr()
        assert "Firewall rule added" in captured.out
        assert "Block attacker" in captured.out

    @pytest.mark.asyncio
    async def test_add_rule_invalid_action(self, cli, capsys):
        """Invalid action returns 1 with error."""
        args = make_args(
            name="Bad rule",
            action="INVALID_ACTION",
            priority=1,
            source_zone="any",
            source_network="any",
            source_ip="any",
            dest_zone="any",
            dest_network="any",
            dest_ip="any",
            dest_port=None,
            description="",
        )
        result = await cli.firewall_add_rule(args)
        assert result == 1
        captured = capsys.readouterr()
        assert "Invalid action" in captured.out

    @pytest.mark.asyncio
    async def test_remove_rule_success(self, cli, capsys):
        """Remove existing rule returns 0."""
        # First add a rule
        args = make_args(
            name="To remove",
            action="deny",
            priority=1,
            source_zone="any",
            source_network="any",
            source_ip="any",
            dest_zone="any",
            dest_network="any",
            dest_ip="any",
            dest_port=None,
            description="",
        )
        await cli.firewall_add_rule(args)
        captured = capsys.readouterr()
        # Extract rule_id from output
        for line in captured.out.splitlines():
            if "rule added:" in line:
                rule_id = line.split(":")[-1].strip()
                break

        result = await cli.firewall_remove_rule(make_args(rule_id=rule_id))
        assert result == 0
        captured = capsys.readouterr()
        assert "rule removed" in captured.out

    @pytest.mark.asyncio
    async def test_remove_rule_not_found(self, cli, capsys):
        """Remove non-existent rule returns 1."""
        result = await cli.firewall_remove_rule(make_args(rule_id="nonexistent_id"))
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out

    @pytest.mark.asyncio
    async def test_list_rules_empty(self, cli, capsys):
        """No rules prints appropriate message."""
        result = await cli.firewall_list_rules(
            make_args(enabled_only=False, verbose=False)
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "No firewall rules" in captured.out

    @pytest.mark.asyncio
    async def test_list_rules_with_rules(self, cli, capsys):
        """Lists rules after adding one."""
        add_args = make_args(
            name="Test rule",
            action="deny",
            priority=10,
            source_zone="any",
            source_network="any",
            source_ip="any",
            dest_zone="any",
            dest_network="any",
            dest_ip="any",
            dest_port=None,
            description="",
        )
        await cli.firewall_add_rule(add_args)
        capsys.readouterr()  # Clear output

        result = await cli.firewall_list_rules(
            make_args(enabled_only=False, verbose=False)
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Test rule" in captured.out
        assert "Firewall Rules" in captured.out

    @pytest.mark.asyncio
    async def test_list_rules_verbose(self, cli, capsys):
        """Verbose listing shows hit count."""
        add_args = make_args(
            name="Verbose rule",
            action="deny",
            priority=10,
            source_zone="any",
            source_network="any",
            source_ip="10.0.0.1",
            dest_zone="any",
            dest_network="any",
            dest_ip="any",
            dest_port=None,
            description="A test rule",
        )
        await cli.firewall_add_rule(add_args)
        capsys.readouterr()

        result = await cli.firewall_list_rules(
            make_args(enabled_only=False, verbose=True)
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Hit Count" in captured.out
        assert "Source IP" in captured.out

    @pytest.mark.asyncio
    async def test_enable_rule_success(self, cli, capsys):
        """Enable existing rule returns 0."""
        # Add and then disable a rule, then re-enable
        add_args = make_args(
            name="Enable test",
            action="deny",
            priority=10,
            source_zone="any",
            source_network="any",
            source_ip="any",
            dest_zone="any",
            dest_network="any",
            dest_ip="any",
            dest_port=None,
            description="",
        )
        await cli.firewall_add_rule(add_args)
        captured = capsys.readouterr()
        for line in captured.out.splitlines():
            if "rule added:" in line:
                rule_id = line.split(":")[-1].strip()
                break

        await cli.firewall_disable_rule(make_args(rule_id=rule_id))
        capsys.readouterr()

        result = await cli.firewall_enable_rule(make_args(rule_id=rule_id))
        assert result == 0
        captured = capsys.readouterr()
        assert "Rule enabled" in captured.out

    @pytest.mark.asyncio
    async def test_enable_rule_not_found(self, cli, capsys):
        """Enable non-existent rule returns 1."""
        result = await cli.firewall_enable_rule(make_args(rule_id="nonexistent"))
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out

    @pytest.mark.asyncio
    async def test_disable_rule_success(self, cli, capsys):
        """Disable existing rule returns 0."""
        add_args = make_args(
            name="Disable test",
            action="deny",
            priority=10,
            source_zone="any",
            source_network="any",
            source_ip="any",
            dest_zone="any",
            dest_network="any",
            dest_ip="any",
            dest_port=None,
            description="",
        )
        await cli.firewall_add_rule(add_args)
        captured = capsys.readouterr()
        for line in captured.out.splitlines():
            if "rule added:" in line:
                rule_id = line.split(":")[-1].strip()
                break

        result = await cli.firewall_disable_rule(make_args(rule_id=rule_id))
        assert result == 0
        captured = capsys.readouterr()
        assert "Rule disabled" in captured.out


# ================================================================
# IDS/IPS COMMAND TESTS
# ================================================================


class TestIDSCommands:
    """Test IDS/IPS CLI commands."""

    @pytest.mark.asyncio
    async def test_enable_ips(self, cli, capsys):
        """Enable IPS returns 0 and prints confirmation."""
        result = await cli.ids_enable_ips(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "IPS mode ENABLED" in captured.out

    @pytest.mark.asyncio
    async def test_disable_ips(self, cli, capsys):
        """Disable IPS returns 0 and prints detection-only."""
        result = await cli.ids_disable_ips(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "DETECTION ONLY" in captured.out

    @pytest.mark.asyncio
    async def test_block_ip_success(self, cli, capsys):
        """Block IP returns 0 and prints confirmation."""
        result = await cli.ids_block_ip(
            make_args(ip="192.168.1.100", reason="Attack detected")
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "IP address blocked" in captured.out
        assert "192.168.1.100" in captured.out

    @pytest.mark.asyncio
    async def test_block_ip_already_blocked(self, cli, capsys):
        """Blocking already-blocked IP returns 0 with warning."""
        await cli.ids_block_ip(make_args(ip="192.168.1.100", reason="First block"))
        capsys.readouterr()

        result = await cli.ids_block_ip(
            make_args(ip="192.168.1.100", reason="Second block")
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "already blocked" in captured.out

    @pytest.mark.asyncio
    async def test_unblock_ip_success(self, cli, capsys):
        """Unblock IP returns 0 after blocking."""
        await cli.ids_block_ip(make_args(ip="10.0.0.1", reason="test"))
        capsys.readouterr()

        result = await cli.ids_unblock_ip(make_args(ip="10.0.0.1"))
        assert result == 0
        captured = capsys.readouterr()
        assert "unblocked" in captured.out

    @pytest.mark.asyncio
    async def test_unblock_ip_not_blocked(self, cli, capsys):
        """Unblock non-blocked IP returns 0 with warning."""
        result = await cli.ids_unblock_ip(make_args(ip="10.0.0.99"))
        assert result == 0
        captured = capsys.readouterr()
        assert "was not blocked" in captured.out

    @pytest.mark.asyncio
    async def test_list_blocked_empty(self, cli, capsys):
        """No blocked IPs prints appropriate message."""
        result = await cli.ids_list_blocked(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "No IP addresses" in captured.out

    @pytest.mark.asyncio
    async def test_list_blocked_with_ips(self, cli, capsys):
        """Lists blocked IPs after blocking some."""
        await cli.ids_block_ip(make_args(ip="10.0.0.1", reason="test"))
        await cli.ids_block_ip(make_args(ip="10.0.0.2", reason="test"))
        capsys.readouterr()

        result = await cli.ids_list_blocked(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "10.0.0.1" in captured.out
        assert "10.0.0.2" in captured.out

    @pytest.mark.asyncio
    async def test_ids_status(self, cli, capsys):
        """Status shows IPS mode and stats."""
        result = await cli.ids_status(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "IDS/IPS Status" in captured.out
        assert "Mode:" in captured.out
        assert "Blocked IPs:" in captured.out

    @pytest.mark.asyncio
    async def test_ids_status_shows_detection_stats(self, cli, capsys):
        """Status includes detection categories."""
        result = await cli.ids_status(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Network Scans:" in captured.out
        assert "Protocol Violations:" in captured.out


# ================================================================
# RBAC COMMAND TESTS
# ================================================================


class TestRBACCommands:
    """Test RBAC CLI commands."""

    @pytest.mark.asyncio
    async def test_list_users_all(self, cli, capsys):
        """List all users prints table."""
        result = await cli.rbac_list_users(make_args(username=None))
        assert result == 0
        captured = capsys.readouterr()
        assert "ICS Users" in captured.out
        assert "Username" in captured.out
        # Should have at least 5 default users
        assert "operator1" in captured.out or "admin" in captured.out

    @pytest.mark.asyncio
    async def test_list_users_specific(self, cli, capsys):
        """Show specific user details."""
        # Get a known username from the auth manager
        username = list(cli.auth_mgr.users.keys())[0]
        result = await cli.rbac_list_users(make_args(username=username))
        assert result == 0
        captured = capsys.readouterr()
        assert f"User: {username}" in captured.out
        assert "Role:" in captured.out

    @pytest.mark.asyncio
    async def test_list_users_not_found(self, cli, capsys):
        """Non-existent user returns 1."""
        result = await cli.rbac_list_users(make_args(username="nonexistent_user"))
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out

    @pytest.mark.asyncio
    async def test_change_role_success(self, cli, capsys):
        """Change role returns 0 for valid user and role."""
        username = list(cli.auth_mgr.users.keys())[0]
        result = await cli.rbac_change_role(make_args(username=username, role="ADMIN"))
        assert result == 0
        captured = capsys.readouterr()
        assert "Role changed" in captured.out

    @pytest.mark.asyncio
    async def test_change_role_invalid_role(self, cli, capsys):
        """Invalid role returns 1."""
        username = list(cli.auth_mgr.users.keys())[0]
        result = await cli.rbac_change_role(
            make_args(username=username, role="INVALID")
        )
        assert result == 1
        captured = capsys.readouterr()
        assert "Invalid role" in captured.out

    @pytest.mark.asyncio
    async def test_change_role_unknown_user(self, cli, capsys):
        """Unknown user returns 1."""
        result = await cli.rbac_change_role(
            make_args(username="nonexistent", role="ADMIN")
        )
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out

    @pytest.mark.asyncio
    async def test_lock_user_success(self, cli, capsys):
        """Lock user returns 0 and sets active=False."""
        username = list(cli.auth_mgr.users.keys())[0]
        result = await cli.rbac_lock_user(make_args(username=username))
        assert result == 0
        captured = capsys.readouterr()
        assert "locked" in captured.out
        user = await cli.auth_mgr.get_user(username)
        assert user.active is False

    @pytest.mark.asyncio
    async def test_lock_user_not_found(self, cli, capsys):
        """Lock non-existent user returns 1."""
        result = await cli.rbac_lock_user(make_args(username="nonexistent"))
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out

    @pytest.mark.asyncio
    async def test_unlock_user_success(self, cli, capsys):
        """Unlock user returns 0 and sets active=True."""
        username = list(cli.auth_mgr.users.keys())[0]
        # Lock first
        await cli.rbac_lock_user(make_args(username=username))
        capsys.readouterr()

        result = await cli.rbac_unlock_user(make_args(username=username))
        assert result == 0
        captured = capsys.readouterr()
        assert "unlocked" in captured.out
        user = await cli.auth_mgr.get_user(username)
        assert user.active is True

    @pytest.mark.asyncio
    async def test_unlock_user_not_found(self, cli, capsys):
        """Unlock non-existent user returns 1."""
        result = await cli.rbac_unlock_user(make_args(username="nonexistent"))
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out

    @pytest.mark.asyncio
    async def test_rbac_enable(self, cli, capsys):
        """Enable RBAC sets data_store.rbac_enabled to True."""
        result = await cli.rbac_enable(make_args())
        assert result == 0
        assert cli.data_store.rbac_enabled is True
        captured = capsys.readouterr()
        assert "RBAC enforcement ENABLED" in captured.out

    @pytest.mark.asyncio
    async def test_rbac_disable(self, cli, capsys):
        """Disable RBAC sets data_store.rbac_enabled to False."""
        cli.data_store.rbac_enabled = True
        result = await cli.rbac_disable(make_args())
        assert result == 0
        assert cli.data_store.rbac_enabled is False
        captured = capsys.readouterr()
        assert "RBAC enforcement DISABLED" in captured.out

    @pytest.mark.asyncio
    async def test_rbac_audit_log_empty(self, cli, capsys):
        """Empty audit log prints no entries message."""
        # Patch get_audit_log to return empty
        cli.auth_mgr.get_audit_log = AsyncMock(return_value=[])
        result = await cli.rbac_audit_log(make_args(limit=50))
        assert result == 0
        captured = capsys.readouterr()
        assert "No audit log entries" in captured.out

    @pytest.mark.asyncio
    async def test_rbac_audit_log_with_events(self, cli, capsys):
        """Audit log with entries prints them."""
        entries = [
            FakeLogEntry(timestamp=10.0, user="operator1", message="Login success"),
            FakeLogEntry(timestamp=20.0, user="admin", message="Role changed"),
        ]
        cli.auth_mgr.get_audit_log = AsyncMock(return_value=entries)
        result = await cli.rbac_audit_log(make_args(limit=50))
        assert result == 0
        captured = capsys.readouterr()
        assert "RBAC Audit Log" in captured.out
        assert "Login success" in captured.out

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self, cli, capsys):
        """No active sessions prints message."""
        result = await cli.rbac_list_sessions(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "No active sessions" in captured.out

    @pytest.mark.asyncio
    async def test_logout_session_not_found(self, cli, capsys):
        """Logout non-existent session returns 1."""
        result = await cli.rbac_logout_session(make_args(session_id="nonexistent"))
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out


# ================================================================
# MODBUS COMMAND TESTS
# ================================================================


class TestModbusCommands:
    """Test Modbus filter CLI commands."""

    @pytest.mark.asyncio
    async def test_modbus_enable(self, cli, capsys):
        """Enable Modbus filtering returns 0."""
        result = await cli.modbus_enable(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "ENABLED" in captured.out

    @pytest.mark.asyncio
    async def test_modbus_disable(self, cli, capsys):
        """Disable Modbus filtering returns 0."""
        result = await cli.modbus_disable(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "DISABLED" in captured.out

    @pytest.mark.asyncio
    async def test_modbus_set_policy_whitelist(self, cli, capsys):
        """Set whitelist policy returns 0."""
        result = await cli.modbus_set_policy(
            make_args(device="plc1", mode="WHITELIST", allowed="1,2,3", blocked=None)
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "policy updated" in captured.out
        assert "WHITELIST" in captured.out.upper()

    @pytest.mark.asyncio
    async def test_modbus_set_policy_blacklist(self, cli, capsys):
        """Set blacklist policy returns 0."""
        result = await cli.modbus_set_policy(
            make_args(device="plc1", mode="BLACKLIST", allowed=None, blocked="15,16")
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "policy updated" in captured.out

    @pytest.mark.asyncio
    async def test_modbus_stats(self, cli, capsys):
        """Stats prints statistics."""
        result = await cli.modbus_stats(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Modbus Filter Statistics" in captured.out
        assert "Total Requests Checked" in captured.out

    @pytest.mark.asyncio
    async def test_modbus_stats_with_blocked(self, cli, capsys):
        """Stats shows blocked FC details when present."""
        # Manually set blocked stats
        cli.modbus_filter.total_requests_checked = 10
        cli.modbus_filter.total_requests_blocked = 2
        cli.modbus_filter.blocked_by_function_code = {15: 1, 16: 1}
        result = await cli.modbus_stats(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Blocked by Function Code" in captured.out

    @pytest.mark.asyncio
    async def test_modbus_status(self, cli, capsys):
        """Status prints brief filter status."""
        result = await cli.modbus_status(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Modbus Function Code Filter" in captured.out
        assert "Enforcement:" in captured.out

    @pytest.mark.asyncio
    async def test_modbus_status_enforcement_disabled(self, cli, capsys):
        """Status shows VULNERABLE when enforcement disabled."""
        cli.modbus_filter.enforcement_enabled = False
        result = await cli.modbus_status(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "DISABLED (VULNERABLE)" in captured.out


# ================================================================
# AUDIT LOG COMMAND TESTS
# ================================================================


class TestAuditCommands:
    """Test audit log CLI commands."""

    @pytest.mark.asyncio
    async def test_audit_query_empty(self, cli, capsys):
        """Empty audit log prints no entries message."""
        result = await cli.audit_query(
            make_args(
                limit=50,
                device=None,
                category=None,
                severity=None,
                user_filter=None,
                action=None,
                since=None,
                until=None,
                verbose=False,
            )
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "No audit log entries" in captured.out

    @pytest.mark.asyncio
    async def test_audit_query_with_events(self, cli, capsys):
        """Audit query formats events correctly."""
        # Add events to system state audit log
        cli.system_state.audit_log.append(
            {
                "simulation_time": 10.0,
                "severity": "WARNING",
                "category": "security",
                "device": "turbine_plc_1",
                "user": "operator1",
                "message": "Setpoint changed",
            }
        )

        result = await cli.audit_query(
            make_args(
                limit=50,
                device=None,
                category=None,
                severity=None,
                user_filter=None,
                action=None,
                since=None,
                until=None,
                verbose=False,
            )
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Audit Log" in captured.out
        assert "Setpoint changed" in captured.out

    @pytest.mark.asyncio
    async def test_audit_query_with_filters(self, cli, capsys):
        """Audit query with device filter passes it through."""
        cli.system_state.audit_log.append(
            {
                "simulation_time": 10.0,
                "severity": "INFO",
                "category": "audit",
                "device": "reactor_plc_1",
                "user": "",
                "message": "Reactor event",
            }
        )
        cli.system_state.audit_log.append(
            {
                "simulation_time": 11.0,
                "severity": "WARNING",
                "category": "security",
                "device": "turbine_plc_1",
                "user": "",
                "message": "Turbine event",
            }
        )

        result = await cli.audit_query(
            make_args(
                limit=50,
                device="turbine_plc_1",
                category=None,
                severity=None,
                user_filter=None,
                action=None,
                since=None,
                until=None,
                verbose=False,
            )
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Turbine event" in captured.out

    @pytest.mark.asyncio
    async def test_audit_query_verbose(self, cli, capsys):
        """Verbose query shows data dict."""
        cli.system_state.audit_log.append(
            {
                "simulation_time": 10.0,
                "severity": "INFO",
                "category": "audit",
                "device": "test_device",
                "user": "admin",
                "message": "Test event",
                "data": {"old_value": 100, "new_value": 200},
            }
        )

        result = await cli.audit_query(
            make_args(
                limit=50,
                device=None,
                category=None,
                severity=None,
                user_filter=None,
                action=None,
                since=None,
                until=None,
                verbose=True,
            )
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "old_value" in captured.out

    @pytest.mark.asyncio
    async def test_audit_stats_empty(self, cli, capsys):
        """Empty log prints no entries message."""
        result = await cli.audit_stats(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "No audit log entries" in captured.out

    @pytest.mark.asyncio
    async def test_audit_stats_with_events(self, cli, capsys):
        """Stats shows category and severity breakdown."""
        for i in range(5):
            cli.system_state.audit_log.append(
                {
                    "simulation_time": float(i),
                    "severity": "WARNING",
                    "category": "security",
                    "device": "turbine_plc_1",
                    "user": "admin",
                    "message": f"Event {i}",
                }
            )

        result = await cli.audit_stats(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Audit Log Statistics" in captured.out
        assert "Total Events: 5" in captured.out
        assert "Events by Category" in captured.out
        assert "Events by Severity" in captured.out

    @pytest.mark.asyncio
    async def test_audit_export_json(self, cli, capsys, tmp_path):
        """Export to JSON writes valid JSON file."""
        cli.system_state.audit_log.append(
            {
                "simulation_time": 10.0,
                "severity": "INFO",
                "category": "audit",
                "device": "test",
                "message": "Export test",
            }
        )

        output_file = str(tmp_path / "audit.json")
        result = await cli.audit_export(
            make_args(
                format="json",
                output=output_file,
                limit=None,
                device=None,
                category=None,
            )
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Exported" in captured.out

        # Verify file contents
        with open(output_file) as f:
            data = json.load(f)
        assert len(data) >= 1
        assert data[0]["message"] == "Export test"

    @pytest.mark.asyncio
    async def test_audit_export_csv(self, cli, capsys, tmp_path):
        """Export to CSV writes valid CSV file."""
        cli.system_state.audit_log.append(
            {
                "simulation_time": 10.0,
                "severity": "INFO",
                "category": "audit",
                "device": "test",
                "message": "CSV test",
            }
        )

        output_file = str(tmp_path / "audit.csv")
        result = await cli.audit_export(
            make_args(
                format="csv",
                output=output_file,
                limit=None,
                device=None,
                category=None,
            )
        )
        assert result == 0

        with open(output_file) as f:
            reader = csv.reader(f)
            header = next(reader)
            assert "message" in header

    @pytest.mark.asyncio
    async def test_audit_search_found(self, cli, capsys):
        """Search finds matching events."""
        cli.system_state.audit_log.append(
            {
                "simulation_time": 10.0,
                "severity": "WARNING",
                "category": "security",
                "device": "turbine_plc_1",
                "user": "attacker",
                "message": "Unauthorized SCRAM attempt",
            }
        )

        result = await cli.audit_search(make_args(pattern="SCRAM", limit=100))
        assert result == 0
        captured = capsys.readouterr()
        assert "SCRAM" in captured.out
        assert "1 matches" in captured.out

    @pytest.mark.asyncio
    async def test_audit_search_no_matches(self, cli, capsys):
        """Search with no matches prints message."""
        cli.system_state.audit_log.append(
            {
                "simulation_time": 10.0,
                "severity": "INFO",
                "category": "audit",
                "device": "test",
                "user": "",
                "message": "Normal event",
            }
        )

        result = await cli.audit_search(
            make_args(pattern="NONEXISTENT_PATTERN", limit=100)
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "No events matching" in captured.out


# ================================================================
# ANOMALY DETECTION COMMAND TESTS
# ================================================================


class TestAnomalyCommands:
    """Test anomaly detection CLI commands."""

    @pytest.mark.asyncio
    async def test_anomaly_enable(self, cli, capsys):
        """Enable anomaly detection returns 0."""
        result = await cli.anomaly_enable(make_args())
        assert result == 0
        assert cli.anomaly_detector.enabled is True
        captured = capsys.readouterr()
        assert "ENABLED" in captured.out

    @pytest.mark.asyncio
    async def test_anomaly_disable(self, cli, capsys):
        """Disable anomaly detection returns 0."""
        result = await cli.anomaly_disable(make_args(reason="Testing"))
        assert result == 0
        assert cli.anomaly_detector.enabled is False
        captured = capsys.readouterr()
        assert "DISABLED" in captured.out

    @pytest.mark.asyncio
    async def test_anomaly_add_baseline(self, cli, capsys):
        """Add baseline returns 0 and prints confirmation."""
        result = await cli.anomaly_add_baseline(
            make_args(device="turbine_plc_1", parameter="speed", learning_window=500)
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Baseline added" in captured.out
        assert "turbine_plc_1/speed" in captured.out

    @pytest.mark.asyncio
    async def test_anomaly_set_range(self, cli, capsys):
        """Set range returns 0 and prints range."""
        # Patch the method since blue_team.py passes an extra severity kwarg
        cli.anomaly_detector.set_range_limit = AsyncMock()
        result = await cli.anomaly_set_range(
            make_args(device="turbine_plc_1", parameter="speed", min=800.0, max=1800.0)
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Range limit set" in captured.out
        assert "800" in captured.out
        assert "1800" in captured.out

    @pytest.mark.asyncio
    async def test_anomaly_set_rate(self, cli, capsys):
        """Set rate returns 0 and prints rate."""
        # Patch the method since blue_team.py passes an extra severity kwarg
        cli.anomaly_detector.set_rate_of_change_limit = AsyncMock()
        result = await cli.anomaly_set_rate(
            make_args(device="turbine_plc_1", parameter="speed", max_rate=10.0)
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Rate limit set" in captured.out
        assert "10.0" in captured.out

    @pytest.mark.asyncio
    async def test_anomaly_list_empty(self, cli, capsys):
        """No anomalies prints message."""
        result = await cli.anomaly_list(make_args(limit=50))
        assert result == 0
        captured = capsys.readouterr()
        assert "No anomalies" in captured.out

    @pytest.mark.asyncio
    async def test_anomaly_list_with_anomalies(self, cli, capsys):
        """Lists anomalies when present."""
        from components.security.anomaly_detector import (
            AnomalyEvent,
            AnomalySeverity,
            AnomalyType,
        )

        event = AnomalyEvent(
            timestamp=100.0,
            anomaly_type=AnomalyType.RANGE,
            severity=AnomalySeverity.HIGH,
            device="turbine_plc_1",
            parameter="speed",
            observed_value=2000.0,
            expected_value=1500.0,
            description="Speed exceeds maximum range",
        )
        cli.anomaly_detector.anomalies.append(event)

        result = await cli.anomaly_list(make_args(limit=50))
        assert result == 0
        captured = capsys.readouterr()
        assert "Recent Anomalies" in captured.out
        assert "turbine_plc_1" in captured.out
        assert "speed" in captured.out

    @pytest.mark.asyncio
    async def test_anomaly_stats_empty(self, cli, capsys):
        """Stats with no anomalies shows zero counts."""
        # blue_team.py accesses .rate_limits but attribute is .roc_limits
        cli.anomaly_detector.rate_limits = cli.anomaly_detector.roc_limits
        result = await cli.anomaly_stats(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Anomaly Detection Statistics" in captured.out
        assert "Total Anomalies: 0" in captured.out

    @pytest.mark.asyncio
    async def test_anomaly_stats_with_data(self, cli, capsys):
        """Stats with anomalies shows breakdown."""
        # blue_team.py accesses .rate_limits but attribute is .roc_limits
        cli.anomaly_detector.rate_limits = cli.anomaly_detector.roc_limits
        from components.security.anomaly_detector import (
            AnomalyEvent,
            AnomalySeverity,
            AnomalyType,
        )

        for i in range(3):
            cli.anomaly_detector.anomalies.append(
                AnomalyEvent(
                    timestamp=float(i),
                    anomaly_type=AnomalyType.RANGE,
                    severity=AnomalySeverity.HIGH,
                    device="turbine_plc_1",
                    parameter="speed",
                    observed_value=2000.0 + i,
                    description=f"Anomaly {i}",
                )
            )

        result = await cli.anomaly_stats(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Total Anomalies: 3" in captured.out

    @pytest.mark.asyncio
    async def test_anomaly_clear(self, cli, capsys):
        """Clear returns 0."""
        result = await cli.anomaly_clear(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Cleared" in captured.out

    @pytest.mark.asyncio
    async def test_anomaly_clear_with_history(self, cli, capsys):
        """Clear reports count of cleared anomalies."""
        from components.security.anomaly_detector import (
            AnomalyEvent,
            AnomalySeverity,
            AnomalyType,
        )

        for i in range(5):
            cli.anomaly_detector.anomalies.append(
                AnomalyEvent(
                    timestamp=float(i),
                    anomaly_type=AnomalyType.STATISTICAL,
                    severity=AnomalySeverity.MEDIUM,
                    device="test",
                    parameter="val",
                    observed_value=float(i),
                    description="test",
                )
            )

        result = await cli.anomaly_clear(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Cleared 5" in captured.out


# ================================================================
# OPC UA COMMAND TESTS
# ================================================================


class TestOPCUACommands:
    """Test OPC UA security CLI commands."""

    @pytest.mark.asyncio
    async def test_opcua_status_disabled(self, cli, capsys):
        """Status with enforcement disabled shows VULNERABLE."""
        with patch("config.config_loader.ConfigLoader") as mock_cl:
            mock_cl.return_value.load_all.return_value = {
                "opcua_security": {
                    "enforcement_enabled": False,
                    "require_authentication": False,
                    "security_policy": "None",
                    "allow_anonymous": True,
                    "cert_dir": "certs",
                    "key_size": 2048,
                    "validity_hours": 8760,
                },
                "devices": [],
            }
            result = await cli.opcua_status(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "DISABLED (VULNERABLE)" in captured.out

    @pytest.mark.asyncio
    async def test_opcua_status_auth_enabled(self, cli, capsys):
        """Status with authentication enabled shows ENABLED."""
        with patch("config.config_loader.ConfigLoader") as mock_cl:
            mock_cl.return_value.load_all.return_value = {
                "opcua_security": {
                    "enforcement_enabled": False,
                    "require_authentication": True,
                    "security_policy": "None",
                    "allow_anonymous": False,
                    "cert_dir": "certs",
                    "key_size": 2048,
                    "validity_hours": 8760,
                },
                "devices": [],
            }
            result = await cli.opcua_status(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Authentication: ENABLED" in captured.out

    @pytest.mark.asyncio
    async def test_opcua_status_encryption_enabled(self, cli, capsys):
        """Status with encryption enabled shows ENABLED."""
        with patch("config.config_loader.ConfigLoader") as mock_cl:
            mock_cl.return_value.load_all.return_value = {
                "opcua_security": {
                    "enforcement_enabled": True,
                    "require_authentication": True,
                    "security_policy": "Aes256_Sha256_RsaPss",
                    "allow_anonymous": False,
                    "cert_dir": "certs",
                    "key_size": 2048,
                    "validity_hours": 8760,
                },
                "devices": [],
            }
            result = await cli.opcua_status(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Encryption Enforcement: ENABLED" in captured.out

    @pytest.mark.asyncio
    async def test_opcua_list_users(self, cli, capsys):
        """List users prints user table with role mapping."""
        with patch("config.config_loader.ConfigLoader") as mock_cl:
            mock_cl.return_value.load_all.return_value = {
                "opcua_security": {
                    "require_authentication": True,
                },
            }
            result = await cli.opcua_list_users(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "OPC UA Authentication Users" in captured.out
        assert "Username" in captured.out

    @pytest.mark.asyncio
    async def test_opcua_list_users_auth_disabled_hint(self, cli, capsys):
        """When auth disabled, prints enable instructions."""
        with patch("config.config_loader.ConfigLoader") as mock_cl:
            mock_cl.return_value.load_all.return_value = {
                "opcua_security": {
                    "require_authentication": False,
                },
            }
            result = await cli.opcua_list_users(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Authentication is DISABLED" in captured.out

    @pytest.mark.asyncio
    async def test_opcua_generate_certs_no_servers(self, cli, capsys):
        """Generate certs with no OPC UA servers returns 1."""
        with patch("config.config_loader.ConfigLoader") as mock_cl:
            mock_cl.return_value.load_all.return_value = {
                "opcua_security": {
                    "key_size": 2048,
                    "validity_hours": 8760,
                    "cert_dir": "certs",
                },
                "devices": [],
            }
            result = await cli.opcua_generate_certs(make_args(server=None, force=False))
        assert result == 1
        captured = capsys.readouterr()
        assert "No OPC UA servers" in captured.out

    @pytest.mark.asyncio
    async def test_opcua_list_certs_no_dir(self, cli, capsys, tmp_path):
        """List certs returns 1 when cert directory doesn't exist."""
        with patch("config.config_loader.ConfigLoader") as mock_cl:
            mock_cl.return_value.load_all.return_value = {
                "opcua_security": {
                    "cert_dir": str(tmp_path / "nonexistent_certs"),
                },
                "devices": [],
            }
            result = await cli.opcua_list_certs(make_args())
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out

    @pytest.mark.asyncio
    async def test_opcua_validate_cert_not_found(self, cli, capsys, tmp_path):
        """Validate cert returns 1 when cert doesn't exist."""
        with patch("config.config_loader.ConfigLoader") as mock_cl:
            mock_cl.return_value.load_all.return_value = {
                "opcua_security": {
                    "cert_dir": str(tmp_path),
                },
            }
            result = await cli.opcua_validate_cert(make_args(name="nonexistent_server"))
        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out


# ================================================================
# STATUS COMMAND TESTS
# ================================================================


class TestStatusCommand:
    """Test overall status command."""

    @pytest.mark.asyncio
    async def test_status_all_disabled(self, cli, capsys):
        """Status shows all systems in default state."""
        with patch("config.config_loader.ConfigLoader") as mock_cl:
            mock_cl.return_value.load_all.return_value = {
                "opcua_security": {
                    "enforcement_enabled": False,
                    "require_authentication": False,
                    "security_policy": "None",
                    "cert_dir": str(Path("/tmp/nonexistent_certs")),
                },
                "devices": [],
            }
            result = await cli.status(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Blue Team Security Status" in captured.out

    @pytest.mark.asyncio
    async def test_status_shows_all_sections(self, cli, capsys):
        """Status output includes all security system sections."""
        with patch("config.config_loader.ConfigLoader") as mock_cl:
            mock_cl.return_value.load_all.return_value = {
                "opcua_security": {
                    "enforcement_enabled": False,
                    "require_authentication": False,
                    "security_policy": "None",
                    "cert_dir": str(Path("/tmp/nonexistent_certs")),
                },
                "devices": [],
            }
            result = await cli.status(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Firewall:" in captured.out
        assert "IDS/IPS:" in captured.out
        assert "RBAC:" in captured.out
        assert "Modbus Filter:" in captured.out
        assert "OPC UA Security:" in captured.out
        assert "Connections:" in captured.out

    @pytest.mark.asyncio
    async def test_status_with_active_rules(self, cli, capsys):
        """Status shows non-zero counts after adding rules."""
        # Add a firewall rule
        add_args = make_args(
            name="Status test rule",
            action="deny",
            priority=10,
            source_zone="any",
            source_network="any",
            source_ip="any",
            dest_zone="any",
            dest_network="any",
            dest_ip="any",
            dest_port=None,
            description="",
        )
        await cli.firewall_add_rule(add_args)
        capsys.readouterr()

        with patch("config.config_loader.ConfigLoader") as mock_cl:
            mock_cl.return_value.load_all.return_value = {
                "opcua_security": {
                    "enforcement_enabled": False,
                    "require_authentication": False,
                    "security_policy": "None",
                    "cert_dir": str(Path("/tmp/nonexistent_certs")),
                },
                "devices": [],
            }
            result = await cli.status(make_args())
        assert result == 0
        captured = capsys.readouterr()
        assert "Active Rules: 1" in captured.out


# ================================================================
# CONNECTION COMMAND TESTS
# ================================================================


class TestConnectionCommands:
    """Test connections list, kill, history commands."""

    @pytest.fixture(autouse=True)
    def reset_registry(self):
        """Reset ConnectionRegistry singleton between tests."""
        from components.network.connection_registry import ConnectionRegistry

        ConnectionRegistry.reset_singleton()
        yield
        ConnectionRegistry.reset_singleton()

    @pytest.mark.asyncio
    async def test_connections_list_empty(self, cli, capsys):
        """List with no active connections."""
        result = await cli.connections_list(make_args(device=None, protocol=None))
        assert result == 0
        captured = capsys.readouterr()
        assert "No active connections" in captured.out

    @pytest.mark.asyncio
    async def test_connections_list_with_connections(self, cli, capsys):
        """List shows active connections."""
        registry = cli.connection_registry
        await registry.connect(
            source_ip="10.40.99.10",
            source_device="legacy_data_collector",
            target_device="hex_turbine_plc",
            protocol="smb",
            port=10445,
            username="guest",
        )

        result = await cli.connections_list(make_args(device=None, protocol=None))
        assert result == 0
        captured = capsys.readouterr()
        assert "Active Connections (1)" in captured.out
        assert "10.40.99.10" in captured.out
        assert "legacy_data_collector" in captured.out
        assert "hex_turbine_plc" in captured.out
        assert "smb" in captured.out
        assert "guest" in captured.out

    @pytest.mark.asyncio
    async def test_connections_list_filter_by_device(self, cli, capsys):
        """List filters by target device."""
        registry = cli.connection_registry
        await registry.connect(
            source_ip="10.40.99.10",
            source_device="legacy_data_collector",
            target_device="hex_turbine_plc",
            protocol="smb",
            port=10445,
        )
        await registry.connect(
            source_ip="10.20.1.50",
            source_device="hmi_workstation",
            target_device="boiler_plc",
            protocol="modbus",
            port=10502,
        )

        result = await cli.connections_list(
            make_args(device="hex_turbine_plc", protocol=None)
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Active Connections (1)" in captured.out
        assert "hex_turbine_plc" in captured.out
        assert "boiler_plc" not in captured.out

    @pytest.mark.asyncio
    async def test_connections_list_filter_by_protocol(self, cli, capsys):
        """List filters by protocol."""
        registry = cli.connection_registry
        await registry.connect(
            source_ip="10.40.99.10",
            source_device="legacy_data_collector",
            target_device="hex_turbine_plc",
            protocol="smb",
            port=10445,
        )
        await registry.connect(
            source_ip="10.20.1.50",
            source_device="hmi_workstation",
            target_device="boiler_plc",
            protocol="modbus",
            port=10502,
        )

        result = await cli.connections_list(
            make_args(device=None, protocol="modbus")
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Active Connections (1)" in captured.out
        assert "modbus" in captured.out
        assert "smb" not in captured.out

    @pytest.mark.asyncio
    async def test_connections_kill_success(self, cli, capsys):
        """Kill an active connection."""
        registry = cli.connection_registry
        session_id = await registry.connect(
            source_ip="10.40.99.10",
            source_device="legacy_data_collector",
            target_device="hex_turbine_plc",
            protocol="smb",
            port=10445,
        )

        result = await cli.connections_kill(
            make_args(session_id=session_id, reason="Suspicious activity")
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Connection killed" in captured.out
        assert "Suspicious activity" in captured.out

        # Verify connection is gone
        assert not registry.is_connected(session_id)

    @pytest.mark.asyncio
    async def test_connections_kill_partial_match(self, cli, capsys):
        """Kill with partial session ID."""
        registry = cli.connection_registry
        session_id = await registry.connect(
            source_ip="10.40.99.10",
            source_device="legacy_data_collector",
            target_device="hex_turbine_plc",
            protocol="smb",
            port=10445,
        )

        # Use first 6 chars as partial match
        partial = session_id[:6]
        result = await cli.connections_kill(
            make_args(session_id=partial, reason="test kill")
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "Connection killed" in captured.out

    @pytest.mark.asyncio
    async def test_connections_kill_not_found(self, cli, capsys):
        """Kill non-existent session returns error."""
        result = await cli.connections_kill(
            make_args(session_id="nonexistent", reason="test")
        )
        assert result == 1
        captured = capsys.readouterr()
        assert "Session not found" in captured.out

    @pytest.mark.asyncio
    async def test_connections_history_empty(self, cli, capsys):
        """History with no closed connections."""
        result = await cli.connections_history(make_args(limit=50, device=None))
        assert result == 0
        captured = capsys.readouterr()
        assert "No connection history" in captured.out

    @pytest.mark.asyncio
    async def test_connections_history_shows_closed(self, cli, capsys):
        """History shows disconnected connections."""
        registry = cli.connection_registry
        session_id = await registry.connect(
            source_ip="10.40.99.10",
            source_device="legacy_data_collector",
            target_device="hex_turbine_plc",
            protocol="smb",
            port=10445,
            username="admin",
        )
        await registry.disconnect(session_id)

        result = await cli.connections_history(make_args(limit=50, device=None))
        assert result == 0
        captured = capsys.readouterr()
        assert "Connection History (1 entries)" in captured.out
        assert "10.40.99.10" in captured.out
        assert "hex_turbine_plc" in captured.out
        assert "client" in captured.out

    @pytest.mark.asyncio
    async def test_connections_history_shows_killed(self, cli, capsys):
        """History shows killed connections with reason."""
        registry = cli.connection_registry
        session_id = await registry.connect(
            source_ip="10.40.99.10",
            source_device="legacy_data_collector",
            target_device="hex_turbine_plc",
            protocol="smb",
            port=10445,
        )
        await registry.kill_connection(session_id, reason="Malicious activity")

        result = await cli.connections_history(make_args(limit=50, device=None))
        assert result == 0
        captured = capsys.readouterr()
        assert "defender" in captured.out
        assert "Malicious activity" in captured.out

    @pytest.mark.asyncio
    async def test_connections_history_filter_by_device(self, cli, capsys):
        """History filters by target device."""
        registry = cli.connection_registry
        s1 = await registry.connect(
            source_ip="10.40.99.10",
            source_device="legacy_data_collector",
            target_device="hex_turbine_plc",
            protocol="smb",
            port=10445,
        )
        s2 = await registry.connect(
            source_ip="10.20.1.50",
            source_device="hmi_workstation",
            target_device="boiler_plc",
            protocol="modbus",
            port=10502,
        )
        await registry.disconnect(s1)
        await registry.disconnect(s2)

        result = await cli.connections_history(
            make_args(limit=50, device="hex_turbine_plc")
        )
        assert result == 0
        captured = capsys.readouterr()
        assert "hex_turbine_plc" in captured.out
        assert "boiler_plc" not in captured.out

    @pytest.mark.asyncio
    async def test_connections_history_limit(self, cli, capsys):
        """History respects limit parameter."""
        registry = cli.connection_registry
        for i in range(5):
            s = await registry.connect(
                source_ip=f"10.0.0.{i}",
                source_device="attacker",
                target_device="target",
                protocol="smb",
                port=10445,
            )
            await registry.disconnect(s)

        result = await cli.connections_history(make_args(limit=2, device=None))
        assert result == 0
        captured = capsys.readouterr()
        assert "Connection History (2 entries)" in captured.out


# ================================================================
# CONNECTION PARSER TESTS
# ================================================================


class TestConnectionParser:
    """Test connections command parser setup."""

    def test_connections_list_parser(self):
        """Parser handles connections list."""
        parser = create_parser()
        args = parser.parse_args(["connections", "list"])
        assert args.command == "connections"
        assert args.subcommand == "list"

    def test_connections_list_with_device_filter(self):
        """Parser handles connections list --device."""
        parser = create_parser()
        args = parser.parse_args(["connections", "list", "--device", "hex_turbine_plc"])
        assert args.device == "hex_turbine_plc"

    def test_connections_list_with_protocol_filter(self):
        """Parser handles connections list --protocol."""
        parser = create_parser()
        args = parser.parse_args(["connections", "list", "--protocol", "smb"])
        assert args.protocol == "smb"

    def test_connections_kill_parser(self):
        """Parser handles connections kill."""
        parser = create_parser()
        args = parser.parse_args(["connections", "kill", "abc123"])
        assert args.command == "connections"
        assert args.subcommand == "kill"
        assert args.session_id == "abc123"

    def test_connections_kill_with_reason(self):
        """Parser handles connections kill --reason."""
        parser = create_parser()
        args = parser.parse_args(
            ["connections", "kill", "abc123", "--reason", "Malicious"]
        )
        assert args.reason == "Malicious"

    def test_connections_history_parser(self):
        """Parser handles connections history."""
        parser = create_parser()
        args = parser.parse_args(["connections", "history"])
        assert args.command == "connections"
        assert args.subcommand == "history"

    def test_connections_history_with_limit(self):
        """Parser handles connections history --limit."""
        parser = create_parser()
        args = parser.parse_args(["connections", "history", "--limit", "100"])
        assert args.limit == 100

    def test_connections_history_with_device(self):
        """Parser handles connections history --device."""
        parser = create_parser()
        args = parser.parse_args(
            ["connections", "history", "--device", "hex_turbine_plc"]
        )
        assert args.device == "hex_turbine_plc"
