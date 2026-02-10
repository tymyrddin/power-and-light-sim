#!/usr/bin/env python3
"""
Blue Team CLI - Runtime Security Operations

Command-line interface for incident response and security operations.
All changes are RUNTIME (immediate effect, lost on restart).

To make changes permanent, edit config files and restart:
  - config/firewall.yml
  - config/ids_ips.yml
  - config/rbac.yml
  - config/opcua_security.yml
  - python tools/simulator_manager.py

Usage:
  python tools/blue_team.py firewall add-rule --help
  python tools/blue_team.py ids enable-ips
  python tools/blue_team.py rbac list-users
  python tools/blue_team.py opcua status
  python tools/blue_team.py status
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from components.devices.enterprise_zone import (
    Firewall,
    IDSSystem,
    ModbusFilter,
    PolicyMode,
    RuleAction,
)
from components.security.authentication import AuthenticationManager, UserRole
from components.state.data_store import DataStore
from components.state.system_state import SystemState


class BlueTeamCLI:
    """Blue team command-line interface."""

    def __init__(self):
        self.data_store = None
        self.system_state = None
        self.firewall = None
        self.ids_system = None
        self.auth_mgr = None
        self.modbus_filter = None
        self.anomaly_detector = None

    async def initialize(self):
        """Initialize simulation components."""
        self.system_state = SystemState()
        self.auth_mgr = AuthenticationManager()
        self.data_store = DataStore(
            system_state=self.system_state, auth_mgr=self.auth_mgr
        )
        await self.auth_mgr.set_data_store(self.data_store)

        # Get or create firewall
        firewall_device = await self.system_state.get_device("firewall_primary")
        if firewall_device:
            # Device exists in running simulation
            self.firewall = firewall_device
        else:
            # Create new instance (for testing/standalone)
            self.firewall = Firewall(
                device_name="firewall_primary",
                device_id=500,
                data_store=self.data_store,
            )
            await self.firewall.start()

        # Get or create IDS
        ids_device = await self.system_state.get_device("ids_primary")
        if ids_device:
            self.ids_system = ids_device
        else:
            self.ids_system = IDSSystem(
                device_name="ids_primary",
                device_id=400,
                data_store=self.data_store,
            )
            await self.ids_system.start()

        # Get or create Modbus filter
        modbus_filter_device = await self.system_state.get_device(
            "modbus_filter_primary"
        )
        if modbus_filter_device:
            self.modbus_filter = modbus_filter_device
        else:
            self.modbus_filter = ModbusFilter(
                device_name="modbus_filter_primary",
                device_id=600,
                data_store=self.data_store,
            )
            # Load config if available
            from config.config_loader import ConfigLoader

            config = ConfigLoader().load_all()
            if "modbus_filtering" in config and config["modbus_filtering"]:
                try:
                    await self.modbus_filter.load_config(config["modbus_filtering"])
                except Exception as e:
                    print(f"Warning: Could not load Modbus filter config: {e}")

        # Initialize anomaly detector
        from components.security.anomaly_detector import AnomalyDetector

        self.anomaly_detector = AnomalyDetector(
            data_store=self.data_store,
            system_state=self.system_state,
        )

        # Load config if available
        if "anomaly_detection" in config and config["anomaly_detection"]:
            # Anomaly detector loads config automatically from ConfigLoader
            pass

    # ================================================================
    # Firewall Commands
    # ================================================================

    async def firewall_add_rule(self, args):
        """Add firewall rule (runtime, lost on restart)."""
        # Parse action
        try:
            action = RuleAction[args.action.upper()]
        except KeyError:
            print(f"❌ Invalid action: {args.action}")
            print("   Valid: allow, deny, drop, reject")
            return 1

        # Add rule
        rule_id = await self.firewall.add_rule(
            name=args.name,
            action=action,
            priority=args.priority,
            source_zone=args.source_zone,
            source_network=args.source_network,
            source_ip=args.source_ip,
            dest_zone=args.dest_zone,
            dest_network=args.dest_network,
            dest_ip=args.dest_ip,
            dest_port=args.dest_port,
            description=args.description,
            user=args.user,
            reason=args.reason,
        )

        print(f"✓ Firewall rule added: {rule_id}")
        print(f"  Name: {args.name}")
        print(f"  Action: {action.value}")
        print(f"  Priority: {args.priority}")
        if args.source_ip != "any":
            print(f"  Source IP: {args.source_ip}")
        if args.source_zone != "any":
            print(f"  Source Zone: {args.source_zone}")
        if args.dest_zone != "any":
            print(f"  Dest Zone: {args.dest_zone}")
        print()
        print("⚠ This rule is RUNTIME ONLY and will be lost on restart.")
        print("  To make permanent, add to config/firewall.yml and restart.")
        return 0

    async def firewall_remove_rule(self, args):
        """Remove firewall rule."""
        success = await self.firewall.remove_rule(
            rule_id=args.rule_id,
            user=args.user,
            reason=args.reason,
        )

        if success:
            print(f"✓ Firewall rule removed: {args.rule_id}")
            return 0
        else:
            print(f"❌ Rule not found: {args.rule_id}")
            return 1

    async def firewall_list_rules(self, args):
        """List firewall rules."""
        rules = self.firewall.get_rules(enabled_only=args.enabled_only)

        if not rules:
            print("No firewall rules configured.")
            return 0

        print(f"Firewall Rules ({len(rules)} total):")
        print()
        print(f"{'ID':<15} {'Name':<30} {'Action':<8} {'Priority':<10} {'Enabled':<8}")
        print("-" * 80)

        for rule in rules:
            enabled_str = "✓" if rule.enabled else "✗"
            print(
                f"{rule.rule_id:<15} {rule.name:<30} {rule.action.value:<8} {rule.priority:<10} {enabled_str:<8}"
            )

            # Show details if verbose
            if args.verbose:
                if rule.source_ip != "any":
                    print(f"  Source IP: {rule.source_ip}")
                if rule.source_zone != "any":
                    print(f"  Source Zone: {rule.source_zone}")
                if rule.dest_zone != "any":
                    print(f"  Dest Zone: {rule.dest_zone}")
                if rule.dest_port:
                    print(f"  Dest Port: {rule.dest_port}")
                if rule.description:
                    print(f"  Description: {rule.description}")
                print(f"  Hit Count: {rule.hit_count}")
                print()

        print()
        stats = self.firewall.get_statistics()
        print("Statistics:")
        print(f"  Total Checked: {stats['total_connections_checked']}")
        print(f"  Allowed: {stats['total_connections_allowed']}")
        print(f"  Blocked: {stats['total_connections_blocked']}")
        return 0

    async def firewall_enable_rule(self, args):
        """Enable firewall rule."""
        success = await self.firewall.enable_rule(args.rule_id, user=args.user)
        if success:
            print(f"✓ Rule enabled: {args.rule_id}")
            return 0
        else:
            print(f"❌ Rule not found: {args.rule_id}")
            return 1

    async def firewall_disable_rule(self, args):
        """Disable firewall rule."""
        success = await self.firewall.disable_rule(args.rule_id, user=args.user)
        if success:
            print(f"✓ Rule disabled: {args.rule_id}")
            return 0
        else:
            print(f"❌ Rule not found: {args.rule_id}")
            return 1

    # ================================================================
    # IDS/IPS Commands
    # ================================================================

    async def ids_enable_ips(self, args):
        """Enable IPS (prevention) mode."""
        await self.ids_system.set_prevention_mode(enabled=True, user=args.user)
        print("✓ IPS mode ENABLED")
        print("  IDS will now actively BLOCK detected threats")
        print("  Auto-block on CRITICAL alerts: Active")
        print()
        print("⚠ This is a RUNTIME change and will be lost on restart.")
        print("  To make permanent, edit config/ids_ips.yml:")
        print("    prevention_mode: true")
        return 0

    async def ids_disable_ips(self, args):
        """Disable IPS mode (return to IDS detection-only)."""
        await self.ids_system.set_prevention_mode(enabled=False, user=args.user)
        print("✓ IPS mode DISABLED")
        print("  IDS now in DETECTION ONLY mode")
        print("  Threats will be alerted but NOT blocked")
        print()
        print("⚠ This is a RUNTIME change and will be lost on restart.")
        return 0

    async def ids_block_ip(self, args):
        """Block IP address (IPS action)."""
        success = await self.ids_system.block_ip(
            ip_address=args.ip,
            reason=args.reason,
            user=args.user,
        )

        if success:
            print(f"✓ IP address blocked: {args.ip}")
            print(f"  Reason: {args.reason}")
            print()
            print("All connection attempts from this IP will be DROPPED.")
            print()
            print("⚠ This is a RUNTIME block and will be lost on restart.")
            print("  To make permanent, edit config/ids_ips.yml:")
            print("    permanent_blocked_ips:")
            print(f'      - "{args.ip}"')
            return 0
        else:
            print(f"⚠ IP already blocked: {args.ip}")
            return 0

    async def ids_unblock_ip(self, args):
        """Unblock IP address."""
        success = await self.ids_system.unblock_ip(
            ip_address=args.ip,
            user=args.user,
        )

        if success:
            print(f"✓ IP address unblocked: {args.ip}")
            print("  This IP can now connect again.")
            return 0
        else:
            print(f"⚠ IP was not blocked: {args.ip}")
            return 0

    async def ids_list_blocked(self, args):
        """List blocked IP addresses."""
        blocked_ips = self.ids_system.get_blocked_ips()

        if not blocked_ips:
            print("No IP addresses currently blocked.")
            return 0

        print(f"Blocked IP Addresses ({len(blocked_ips)} total):")
        print()
        for ip in blocked_ips:
            print(f"  • {ip}")

        print()
        stats = self.ids_system.get_statistics()
        print("IDS/IPS Statistics:")
        print(
            f"  Mode: {'IPS (Prevention)' if stats['ips']['prevention_mode'] else 'IDS (Detection Only)'}"
        )
        print(f"  Total IPs Blocked: {stats['ips']['total_ips_blocked']}")
        print(f"  Active Alerts: {stats['alerts']['active']}")
        return 0

    async def ids_status(self, args):
        """Show IDS/IPS status."""
        stats = self.ids_system.get_statistics()

        print("IDS/IPS Status:")
        print()
        print(
            f"Mode: {'IPS (Prevention)' if stats['ips']['prevention_mode'] else 'IDS (Detection Only)'}"
        )
        if stats["ips"]["prevention_mode"]:
            print("  ⚠ ACTIVE BLOCKING ENABLED")
            print("  Detected threats will be automatically blocked")
        else:
            print("  ℹ Detection only - threats alerted but not blocked")
        print()

        print("Blocking:")
        print(f"  Blocked IPs: {stats['ips']['blocked_ips']}")
        print(f"  Total Blocked: {stats['ips']['total_ips_blocked']}")
        print(
            f"  Auto-block on Critical: {'Enabled' if stats['ips']['auto_block_enabled'] else 'Disabled'}"
        )
        print()

        print("Alerts:")
        print(f"  Active: {stats['alerts']['active']}")
        print(f"  Total Generated: {stats['alerts']['total_generated']}")
        print("  By Severity:")
        print(f"    CRITICAL: {stats['alerts']['by_severity']['critical']}")
        print(f"    HIGH: {stats['alerts']['by_severity']['high']}")
        print(f"    MEDIUM: {stats['alerts']['by_severity']['medium']}")
        print(f"    LOW: {stats['alerts']['by_severity']['low']}")
        print()

        print("Detections:")
        print(f"  Network Scans: {stats['detections']['scan_detections']}")
        print(f"  Protocol Violations: {stats['detections']['protocol_violations']}")
        print(f"  Unauthorized Access: {stats['detections']['unauthorized_access']}")
        print(f"  Malware: {stats['detections']['malware_detections']}")
        return 0

    # ================================================================
    # RBAC Commands
    # ================================================================

    async def rbac_list_users(self, args):
        """List all users and their roles."""
        if hasattr(args, "username") and args.username:
            # Show specific user
            user = await self.auth_mgr.get_user(args.username)
            if not user:
                print(f"❌ User not found: {args.username}")
                return 1

            print(f"User: {user.username}")
            print(f"  Role: {user.role.name}")
            print(f"  Full Name: {user.full_name}")
            print(f"  Email: {user.email}")
            print(f"  Status: {'Active' if user.active else 'Locked'}")
            print(f"  Last Login: {user.last_login or 'Never'}")
            return 0

        # Show all users
        print(f"ICS Users ({len(self.auth_mgr.users)} total):")
        print()
        print(f"{'Username':<15} {'Role':<12} {'Status':<8} {'Full Name':<25}")
        print("-" * 70)

        for _username, user in sorted(self.auth_mgr.users.items()):
            status = "Active" if user.active else "Locked"
            print(
                f"{user.username:<15} {user.role.name:<12} {status:<8} {user.full_name:<25}"
            )

        print()
        print("Role Permissions:")
        print("  VIEWER      - Read-only access")
        print("  OPERATOR    - Control operations (setpoints, start/stop)")
        print("  ENGINEER    - Configuration and programming")
        print("  SUPERVISOR  - Safety bypass and elevated control")
        print("  ADMIN       - Full system access")
        return 0

    async def rbac_change_role(self, args):
        """Change user role (runtime, lost on restart)."""
        # Validate role
        try:
            new_role = UserRole[args.role.upper()]
        except KeyError:
            print(f"❌ Invalid role: {args.role}")
            print("   Valid: VIEWER, OPERATOR, ENGINEER, SUPERVISOR, ADMIN")
            return 1

        # Change role
        success = await self.auth_mgr.update_user_role(args.username, new_role)

        if success:
            print(f"✓ Role changed: {args.username} → {new_role.name}")
            print()
            print("⚠ This is a RUNTIME change and will be lost on restart.")
            print("  To make permanent, edit config/rbac.yml:")
            print("    user_role_overrides:")
            print(f"      {args.username}: {new_role.name}")
            return 0
        else:
            print(f"❌ User not found: {args.username}")
            return 1

    async def rbac_lock_user(self, args):
        """Lock user account (runtime, lost on restart)."""
        user = await self.auth_mgr.get_user(args.username)
        if not user:
            print(f"❌ User not found: {args.username}")
            return 1

        user.active = False
        print(f"✓ User account locked: {args.username}")
        print(f"  Reason: {args.reason}")
        print()
        print("User cannot authenticate until unlocked.")
        print()
        print("⚠ This is a RUNTIME lock and will be lost on restart.")
        return 0

    async def rbac_unlock_user(self, args):
        """Unlock user account (runtime, lost on restart)."""
        user = await self.auth_mgr.get_user(args.username)
        if not user:
            print(f"❌ User not found: {args.username}")
            return 1

        user.active = True
        print(f"✓ User account unlocked: {args.username}")
        print("  User can now authenticate.")
        return 0

    async def rbac_enable(self, args):
        """Enable RBAC enforcement (runtime, lost on restart)."""
        self.data_store.rbac_enabled = True
        print("✓ RBAC enforcement ENABLED")
        print()
        print("Permission checks are now active:")
        print("  • All write operations require valid session")
        print("  • Users must have appropriate role for actions")
        print("  • Permission denials logged to audit trail")
        print()
        print("⚠ This is a RUNTIME change and will be lost on restart.")
        print("  To make permanent, edit config/rbac.yml:")
        print("    enforcement_enabled: true")
        return 0

    async def rbac_disable(self, args):
        """Disable RBAC enforcement (runtime, DANGEROUS)."""
        self.data_store.rbac_enabled = False
        print("⚠ RBAC enforcement DISABLED")
        print()
        print("❌ WARNING: All write operations now allowed (VULNERABLE)")
        print("   Any user can modify any device")
        print("   No permission checks active")
        print()
        print("This should only be used for:")
        print("  • Emergency override during crisis")
        print("  • Troubleshooting RBAC issues")
        print()
        print("Re-enable as soon as possible:")
        print(
            "  python tools/blue_team.py rbac enable --user admin --reason 'Emergency resolved'"
        )
        return 0

    async def rbac_audit_log(self, args):
        """View RBAC audit log."""
        # Get audit log entries
        limit = args.limit if hasattr(args, "limit") else 50
        user_filter = args.user if hasattr(args, "user") else None

        entries = await self.auth_mgr.get_audit_log(limit=limit, user=user_filter)

        if not entries:
            print("No audit log entries found.")
            return 0

        # Filter by result if requested
        if hasattr(args, "filter") and args.filter:
            if args.filter.lower() == "denied":
                entries = [
                    e
                    for e in entries
                    if "DENIED" in e.message or "denied" in e.message.lower()
                ]

        print(f"RBAC Audit Log ({len(entries)} entries):")
        print()

        for entry in entries[-50:]:  # Show last 50
            timestamp = entry.timestamp
            user = entry.user or "system"
            message = entry.message
            print(f"[{timestamp:.0f}] {user}: {message}")

        return 0

    async def rbac_list_sessions(self, args):
        """List active authentication sessions."""
        sessions = self.auth_mgr.sessions

        if not sessions:
            print("No active sessions.")
            return 0

        print(f"Active Sessions ({len(sessions)}):")
        print("=" * 100)
        print()

        # Get current simulation time for timeout calculations
        from components.time.simulation_time import SimulationTime

        sim_time = SimulationTime()
        current_time = sim_time.now()

        for session_id, session in sessions.items():
            username = session.user.username
            role = session.user.role.value
            created = session.created_at
            expires = session.expires_at if session.expires_at else "Never"

            # Calculate time remaining if timeout set
            time_remaining = ""
            if session.expires_at:
                remaining = session.expires_at - current_time
                if remaining > 0:
                    hours = remaining / 3600
                    time_remaining = f"({hours:.1f}h remaining)"
                else:
                    time_remaining = "(EXPIRED)"

            # Truncate session ID for display
            short_id = session_id[:8]

            print(f"Session: {short_id}...")
            print(f"  User: {username}")
            print(f"  Role: {role}")
            print(f"  Created: {created:.0f}s")
            if session.expires_at:
                print(f"  Expires: {expires:.0f}s {time_remaining}")
            else:
                print("  Expires: Never")
            print()

        return 0

    async def rbac_logout_session(self, args):
        """Force logout a session (emergency/testing)."""
        session_id = args.session_id

        # Try to find session by full ID or partial match
        full_session_id = None
        if session_id in self.auth_mgr.sessions:
            full_session_id = session_id
        else:
            # Try partial match
            matches = [
                sid
                for sid in self.auth_mgr.sessions.keys()
                if sid.startswith(session_id)
            ]
            if len(matches) == 1:
                full_session_id = matches[0]
            elif len(matches) > 1:
                print(f"❌ Ambiguous session ID '{session_id}' - multiple matches:")
                for match in matches:
                    print(f"  {match}")
                return 1

        if not full_session_id:
            print(f"❌ Session not found: {session_id}")
            return 1

        # Get session info before logout
        session = self.auth_mgr.sessions.get(full_session_id)
        if session:
            username = session.user.username
            reason = getattr(args, "reason", "Forced logout by security admin")

            await self.auth_mgr.logout(full_session_id)

            print(f"✓ Session terminated: {username}")
            print(f"  Session ID: {full_session_id[:16]}...")
            print(f"  Reason: {reason}")
            print()
            print("⚠ User will need to re-authenticate for further operations.")

        return 0

    # ================================================================
    # Modbus Commands
    # ================================================================

    async def modbus_enable(self, args):
        """Enable Modbus function code filtering (runtime)."""
        await self.modbus_filter.set_enforcement(enabled=True, user=args.user)

        print("✓ Modbus function code filtering ENABLED")
        print()
        print("Protocol-level security is now active:")
        print("  • Function codes checked against whitelist/blacklist")
        print("  • Dangerous function codes blocked (FC 15/16/08)")
        print("  • Blocked requests logged to audit trail")
        print()
        print("⚠ This is a RUNTIME change and will be lost on restart.")
        print("  To make permanent, edit config/modbus_filtering.yml:")
        print("    enforcement_enabled: true")
        return 0

    async def modbus_disable(self, args):
        """Disable Modbus function code filtering (runtime, DANGEROUS)."""
        await self.modbus_filter.set_enforcement(enabled=False, user=args.user)

        print("⚠ Modbus function code filtering DISABLED")
        print()
        print("❌ WARNING: All function codes now allowed (VULNERABLE)")
        print("   Any device can use ANY function code")
        print("   No protocol-level protection")
        print()
        print("This should only be used for:")
        print("  • Emergency override during crisis")
        print("  • Troubleshooting filter issues")
        print()
        print("Re-enable as soon as possible:")
        print("  python tools/blue_team.py modbus enable --user admin")
        return 0

    async def modbus_set_policy(self, args):
        """Set device-specific policy (runtime)."""
        # Parse allowed codes
        allowed_codes = set()
        if hasattr(args, "allowed") and args.allowed:
            allowed_codes = {int(fc.strip()) for fc in args.allowed.split(",")}

        # Parse blocked codes
        blocked_codes = set()
        if hasattr(args, "blocked") and args.blocked:
            blocked_codes = {int(fc.strip()) for fc in args.blocked.split(",")}

        # Set policy
        mode = PolicyMode[args.mode.upper()]
        await self.modbus_filter.set_device_policy(
            device_name=args.device,
            mode=mode,
            allowed_codes=allowed_codes if mode == PolicyMode.WHITELIST else None,
            blocked_codes=blocked_codes if mode == PolicyMode.BLACKLIST else None,
            user=args.user,
        )

        print(f"✓ Modbus policy updated for '{args.device}'")
        print(f"  Mode: {mode.value}")
        if mode == PolicyMode.WHITELIST:
            print(f"  Allowed function codes: {sorted(allowed_codes)}")
        else:
            print(f"  Blocked function codes: {sorted(blocked_codes)}")
        print()
        print("⚠ This is a RUNTIME change and will be lost on restart.")
        return 0

    async def modbus_stats(self, args):
        """Show Modbus filter statistics."""
        stats = self.modbus_filter.get_statistics()

        print("=" * 70)
        print("Modbus Filter Statistics")
        print("=" * 70)
        print()

        print(
            f"Enforcement: {'ENABLED' if stats['enforcement_enabled'] else 'DISABLED (VULNERABLE)'}"
        )
        print(f"Global Policy Mode: {stats['global_policy']['mode']}")
        print()

        print(f"Total Requests Checked: {stats['total_requests_checked']}")
        print(f"Total Requests Blocked: {stats['total_requests_blocked']}")
        print(f"Block Rate: {stats['block_rate']:.1%}")
        print()

        if stats["blocked_by_function_code"]:
            print("Blocked by Function Code:")
            for fc, count in sorted(stats["blocked_by_function_code"].items()):
                from components.devices.enterprise_zone.modbus_filter import (
                    FUNCTION_CODE_NAMES,
                )

                fc_name = FUNCTION_CODE_NAMES.get(fc, f"Unknown (0x{fc:02X})")
                print(f"  FC {fc:02d} ({fc_name}): {count} attempts")
            print()

        print(f"Device-Specific Policies: {stats['device_policies']}")
        print(f"Block Mode: {stats['block_mode']}")
        return 0

    async def modbus_status(self, args):
        """Show Modbus filter status."""
        stats = self.modbus_filter.get_statistics()

        print("Modbus Function Code Filter:")
        print(
            f"  Enforcement: {'ENABLED' if stats['enforcement_enabled'] else 'DISABLED (VULNERABLE)'}"
        )
        print(f"  Policy Mode: {stats['global_policy']['mode']}")
        print(f"  Requests Checked: {stats['total_requests_checked']}")
        print(f"  Requests Blocked: {stats['total_requests_blocked']}")
        return 0

    # ================================================================
    # Audit Log Commands (Challenge 3)
    # ================================================================

    async def audit_query(self, args):
        """Query audit logs with filters."""
        # Build filters from args
        limit = getattr(args, "limit", 50)
        device = getattr(args, "device", None)
        category = getattr(args, "category", None)
        severity = getattr(args, "severity", None)
        user = getattr(args, "user_filter", None)
        action = getattr(args, "action", None)
        since = getattr(args, "since", None)
        until = getattr(args, "until", None)

        # Query audit log
        events = await self.data_store.get_audit_log(
            limit=limit,
            device=device,
            category=category,
            severity=severity,
            user=user,
            action=action,
            since=since,
            until=until,
        )

        if not events:
            print("No audit log entries found matching criteria.")
            return 0

        print(f"Audit Log ({len(events)} entries):")
        print("=" * 100)
        print()

        for event in events:
            sim_time = event.get("simulation_time", 0)
            severity_str = event.get("severity", "INFO")
            category_str = event.get("category", "")
            device_str = event.get("device", "system")
            user_str = event.get("user", "")
            message = event.get("message", "")

            # Format output
            time_str = f"[{sim_time:8.1f}s]"
            sev_str = f"[{severity_str:8s}]"
            cat_str = f"[{category_str:8s}]"
            dev_str = f"[{device_str:20s}]"
            user_prefix = f"{user_str}: " if user_str else ""

            print(f"{time_str} {sev_str} {cat_str} {dev_str} {user_prefix}{message}")

            # Show additional data if verbose
            if getattr(args, "verbose", False) and event.get("data"):
                data = event.get("data", {})
                for key, value in data.items():
                    if key not in ["action", "result"]:  # Already shown in message
                        print(f"    {key}: {value}")
                print()

        print()
        print(f"Total: {len(events)} events")
        return 0

    async def audit_stats(self, args):
        """Show audit log statistics."""
        # Get all events (no limit)
        events = await self.data_store.get_audit_log(limit=None)

        if not events:
            print("No audit log entries found.")
            return 0

        print("=" * 70)
        print("Audit Log Statistics")
        print("=" * 70)
        print()

        # Basic stats
        print(f"Total Events: {len(events)}")
        print()

        # Events by category
        categories = {}
        for event in events:
            cat = event.get("category", "unknown")
            categories[cat] = categories.get(cat, 0) + 1

        print("Events by Category:")
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            pct = (count / len(events)) * 100
            print(f"  {cat:15s}: {count:5d} ({pct:5.1f}%)")
        print()

        # Events by severity
        severities = {}
        for event in events:
            sev = event.get("severity", "INFO")
            severities[sev] = severities.get(sev, 0) + 1

        print("Events by Severity:")
        for sev in ["CRITICAL", "ALERT", "ERROR", "WARNING", "NOTICE", "INFO", "DEBUG"]:
            count = severities.get(sev, 0)
            if count > 0:
                pct = (count / len(events)) * 100
                print(f"  {sev:10s}: {count:5d} ({pct:5.1f}%)")
        print()

        # Events by device (top 10)
        devices = {}
        for event in events:
            dev = event.get("device", "system")
            if dev:  # Skip empty device names
                devices[dev] = devices.get(dev, 0) + 1

        print("Top 10 Devices by Event Count:")
        for dev, count in sorted(devices.items(), key=lambda x: x[1], reverse=True)[
            :10
        ]:
            pct = (count / len(events)) * 100
            print(f"  {dev:30s}: {count:5d} ({pct:5.1f}%)")
        print()

        # Events by user (top 10)
        users = {}
        for event in events:
            user = event.get("user", "")
            if user:  # Skip empty usernames
                users[user] = users.get(user, 0) + 1

        if users:
            print("Top 10 Users by Event Count:")
            for user, count in sorted(users.items(), key=lambda x: x[1], reverse=True)[
                :10
            ]:
                pct = (count / len(events)) * 100
                print(f"  {user:20s}: {count:5d} ({pct:5.1f}%)")
            print()

        # Time range
        if events:
            times = [e.get("simulation_time", 0) for e in events]
            print(f"Time Range: {min(times):.1f}s - {max(times):.1f}s")
            print()

        print("=" * 70)
        return 0

    async def audit_export(self, args):
        """Export audit logs to file."""
        import json
        from pathlib import Path

        # Get filters
        limit = getattr(args, "limit", None)
        device = getattr(args, "device", None)
        category = getattr(args, "category", None)

        # Query events
        events = await self.data_store.get_audit_log(
            limit=limit, device=device, category=category
        )

        if not events:
            print("No audit log entries found matching criteria.")
            return 0

        # Determine format
        output_format = getattr(args, "format", "json")
        output_file = getattr(args, "output", None)

        # Auto-generate filename if not specified
        if not output_file:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filter_str = ""
            if device:
                filter_str += f"_{device}"
            if category:
                filter_str += f"_{category}"
            output_file = f"audit_log_{timestamp}{filter_str}.{output_format}"

        output_path = Path(output_file)

        # Export based on format
        if output_format == "json":
            with open(output_path, "w") as f:
                json.dump(events, f, indent=2, default=str)
            print(f"✓ Exported {len(events)} events to {output_path} (JSON)")

        elif output_format == "csv":
            import csv

            with open(output_path, "w", newline="") as f:
                if events:
                    # Get all unique keys from all events
                    all_keys = set()
                    for event in events:
                        all_keys.update(event.keys())
                        if "data" in event and isinstance(event["data"], dict):
                            all_keys.update([f"data.{k}" for k in event["data"].keys()])

                    # Define column order (important fields first)
                    ordered_keys = [
                        "simulation_time",
                        "severity",
                        "category",
                        "device",
                        "user",
                        "message",
                    ]
                    remaining_keys = sorted(all_keys - set(ordered_keys))
                    fieldnames = ordered_keys + remaining_keys

                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()

                    for event in events:
                        # Flatten nested data dict
                        row = event.copy()
                        if "data" in row and isinstance(row["data"], dict):
                            data_dict = row.pop("data")
                            for k, v in data_dict.items():
                                row[f"data.{k}"] = v
                        writer.writerow(row)

            print(f"✓ Exported {len(events)} events to {output_path} (CSV)")

        else:
            print(f"❌ Unsupported format: {output_format}")
            return 1

        return 0

    async def audit_search(self, args):
        """Search audit logs with pattern."""
        import re

        pattern = args.pattern
        limit = getattr(args, "limit", 100)

        # Get events
        events = await self.data_store.get_audit_log(limit=limit)

        if not events:
            print("No audit log entries found.")
            return 0

        # Search pattern in message
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            print(f"❌ Invalid regex pattern: {e}")
            return 1

        matches = []
        for event in events:
            message = event.get("message", "")
            device = event.get("device", "")
            user = event.get("user", "")

            # Search in message, device, and user fields
            if regex.search(message) or regex.search(device) or regex.search(user):
                matches.append(event)

        if not matches:
            print(f"No events matching pattern: {pattern}")
            return 0

        print(f"Found {len(matches)} events matching '{pattern}':")
        print("=" * 100)
        print()

        for event in matches:
            sim_time = event.get("simulation_time", 0)
            severity_str = event.get("severity", "INFO")
            device_str = event.get("device", "system")
            user_str = event.get("user", "")
            message = event.get("message", "")

            time_str = f"[{sim_time:8.1f}s]"
            sev_str = f"[{severity_str:8s}]"
            dev_str = f"[{device_str:20s}]"
            user_prefix = f"{user_str}: " if user_str else ""

            print(f"{time_str} {sev_str} {dev_str} {user_prefix}{message}")

        print()
        print(f"Total: {len(matches)} matches")
        return 0

    # ================================================================
    # Anomaly Detection Commands (Challenge 4)
    # ================================================================

    async def anomaly_enable(self, args):
        """Enable anomaly detection (runtime)."""
        self.anomaly_detector.enabled = True

        print("✓ Anomaly detection ENABLED")
        print()
        print("Behavioural monitoring is now active:")
        print("  • Statistical baseline deviations detected")
        print("  • Range violations flagged")
        print("  • Rate-of-change anomalies detected")
        print("  • Alarm flood detection active")
        print()
        print("⚠ This is a RUNTIME change and will be lost on restart.")
        print("  To make permanent, edit config/anomaly_detection.yml:")
        print("    enabled: true")
        print()

        return 0

    async def anomaly_disable(self, args):
        """Disable anomaly detection (DANGEROUS)."""
        reason = getattr(args, "reason", "No reason provided")

        self.anomaly_detector.enabled = False

        print("⚠ Anomaly detection DISABLED (VULNERABLE)")
        print()
        print(f"Reason: {reason}")
        print()
        print("System is now vulnerable to:")
        print("  • Undetected overspeed attacks")
        print("  • Sensor manipulation")
        print("  • Gradual parameter drift")
        print("  • Alarm flooding attacks")
        print()
        print("To re-enable: python tools/blue_team.py anomaly enable")
        print()

        return 0

    async def anomaly_add_baseline(self, args):
        """Add parameter to baseline monitoring (runtime)."""
        device = args.device
        parameter = args.parameter
        learning_window = getattr(args, "learning_window", 1000)

        await self.anomaly_detector.add_baseline(
            device=device,
            parameter=parameter,
            learning_window=learning_window,
        )

        print(f"✓ Baseline added: {device}/{parameter}")
        print(f"  Learning window: {learning_window} samples")
        print()
        print("The system will learn normal behaviour for this parameter.")
        print(
            f"After {learning_window} samples, statistical anomalies will be detected."
        )
        print()

        return 0

    async def anomaly_set_range(self, args):
        """Set range limits for parameter (runtime)."""
        device = args.device
        parameter = args.parameter
        min_value = args.min
        max_value = args.max

        from components.security.anomaly_detector import AnomalySeverity

        severity = AnomalySeverity.HIGH  # Default

        await self.anomaly_detector.set_range_limit(
            device=device,
            parameter=parameter,
            min_value=min_value,
            max_value=max_value,
            severity=severity,
        )

        print(f"✓ Range limit set: {device}/{parameter}")
        print(f"  Min: {min_value}")
        print(f"  Max: {max_value}")
        print(f"  Severity: {severity.name}")
        print()
        print("Values outside this range will trigger anomaly alerts.")
        print()

        return 0

    async def anomaly_set_rate(self, args):
        """Set rate-of-change limit for parameter (runtime)."""
        device = args.device
        parameter = args.parameter
        max_rate = args.max_rate

        from components.security.anomaly_detector import AnomalySeverity

        severity = AnomalySeverity.HIGH  # Default

        await self.anomaly_detector.set_rate_of_change_limit(
            device=device,
            parameter=parameter,
            max_rate=max_rate,
            severity=severity,
        )

        print(f"✓ Rate limit set: {device}/{parameter}")
        print(f"  Max rate: {max_rate} per second")
        print(f"  Severity: {severity.name}")
        print()
        print("Changes faster than this rate will trigger anomaly alerts.")
        print()

        return 0

    async def anomaly_list(self, args):
        """List recent anomalies."""
        limit = getattr(args, "limit", 50)

        anomalies = await self.anomaly_detector.get_recent_anomalies(limit=limit)

        if not anomalies:
            print("No anomalies detected.")
            return 0

        print(f"Recent Anomalies ({len(anomalies)}):")
        print("=" * 100)
        print()

        for anomaly in anomalies:
            timestamp = anomaly.timestamp
            device = anomaly.device
            parameter = anomaly.parameter
            anomaly_type = anomaly.anomaly_type.value
            severity = anomaly.severity.name
            observed = anomaly.observed_value
            expected = anomaly.expected_value
            description = anomaly.description

            time_str = f"[{timestamp:8.1f}s]"
            sev_str = f"[{severity:8s}]"
            type_str = f"[{anomaly_type:15s}]"
            dev_str = f"[{device:20s}]"

            print(f"{time_str} {sev_str} {type_str} {dev_str}")
            print(f"  Parameter: {parameter}")
            print(f"  Observed: {observed}, Expected: {expected}")
            print(f"  {description}")
            print()

        print(f"Total: {len(anomalies)} anomalies")
        return 0

    async def anomaly_stats(self, args):
        """Show anomaly detection statistics."""
        stats = await self.anomaly_detector.get_anomaly_summary()

        print("=" * 70)
        print("Anomaly Detection Statistics")
        print("=" * 70)
        print()

        print(
            f"Detection Status: {'ENABLED' if self.anomaly_detector.enabled else 'DISABLED'}"
        )
        print(f"Sigma Threshold: {self.anomaly_detector.sigma_threshold}")
        print(f"Learning Window: {self.anomaly_detector.learning_window}")
        print()

        print(f"Total Anomalies: {stats['total_anomalies']}")
        print()

        # Anomalies by type
        by_type = stats.get("by_type", {})
        if by_type:
            print("Anomalies by Type:")
            for anom_type, count in sorted(
                by_type.items(), key=lambda x: x[1], reverse=True
            ):
                pct = (
                    (count / stats["total_anomalies"]) * 100
                    if stats["total_anomalies"] > 0
                    else 0
                )
                print(f"  {anom_type:20s}: {count:5d} ({pct:5.1f}%)")
            print()

        # Anomalies by severity
        by_severity = stats.get("by_severity", {})
        if by_severity:
            print("Anomalies by Severity:")
            for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                count = by_severity.get(severity, 0)
                if count > 0:
                    pct = (
                        (count / stats["total_anomalies"]) * 100
                        if stats["total_anomalies"] > 0
                        else 0
                    )
                    print(f"  {severity:10s}: {count:5d} ({pct:5.1f}%)")
            print()

        # Anomalies by device
        by_device = stats.get("by_device", {})
        if by_device:
            print("Top 10 Devices by Anomaly Count:")
            for device, count in sorted(
                by_device.items(), key=lambda x: x[1], reverse=True
            )[:10]:
                pct = (
                    (count / stats["total_anomalies"]) * 100
                    if stats["total_anomalies"] > 0
                    else 0
                )
                print(f"  {device:30s}: {count:5d} ({pct:5.1f}%)")
            print()

        # Active baselines
        baselines = len(self.anomaly_detector.baselines)
        print(f"Active Baselines: {baselines}")

        # Range limits
        range_limits = len(self.anomaly_detector.range_limits)
        print(f"Range Limits: {range_limits}")

        # Rate limits
        rate_limits = len(self.anomaly_detector.rate_limits)
        print(f"Rate Limits: {rate_limits}")
        print()

        print("=" * 70)
        return 0

    async def anomaly_clear(self, args):
        """Clear anomaly history."""
        count = await self.anomaly_detector.clear_anomalies()

        print(f"✓ Cleared {count} anomalies from history")
        print()
        print("Baseline learning data and limits are preserved.")
        print("Only the anomaly event history has been cleared.")
        print()

        return 0

    # ================================================================
    # OPC UA Security Commands (Challenge 7)
    # ================================================================

    async def opcua_status(self, args):
        """Show OPC UA security status."""
        from config.config_loader import ConfigLoader

        config = ConfigLoader().load_all()
        opcua_sec = config.get("opcua_security", {})

        print("=" * 70)
        print("OPC UA Security Status")
        print("=" * 70)
        print()

        enforcement = opcua_sec.get("enforcement_enabled", False)
        require_auth = opcua_sec.get("require_authentication", False)
        print(f"Encryption Enforcement: {'ENABLED' if enforcement else 'DISABLED (VULNERABLE)'}")
        print(f"Security Policy: {opcua_sec.get('security_policy', 'None')}")
        print(f"Allow Anonymous: {opcua_sec.get('allow_anonymous', True)}")
        print(f"Certificate Directory: {opcua_sec.get('cert_dir', 'certs')}")
        print(f"Key Size: {opcua_sec.get('key_size', 2048)} bits")
        print(f"Validity: {opcua_sec.get('validity_hours', 8760)} hours")
        print()

        # Authentication status (Challenge 1)
        auth_status = "ENABLED" if require_auth else "DISABLED (VULNERABLE)"
        print(f"Authentication: {auth_status}")
        if require_auth:
            auth_mgr = AuthenticationManager()
            active_users = [u for u in auth_mgr.users.values() if u.active]
            locked_users = [u for u in auth_mgr.users.values() if not u.active]
            print(f"  Active Users: {len(active_users)}")
            for user in active_users:
                print(f"    {user.username:<16} {user.role.name:<12} {user.full_name}")
            if locked_users:
                print(f"  Locked Users: {len(locked_users)}")
                for user in locked_users:
                    print(f"    {user.username:<16} {user.role.name:<12} (LOCKED)")
        print()

        # Per-server overrides
        overrides = opcua_sec.get("server_overrides", {})
        if overrides:
            print("Server Overrides:")
            for server_name, override in overrides.items():
                print(f"  {server_name}:")
                for key, value in override.items():
                    print(f"    {key}: {value}")
            print()

        # Discover OPC UA servers from devices.yml
        servers = []
        for device in config.get("devices", []):
            protocols = device.get("protocols", {})
            if "opcua" in protocols:
                servers.append(
                    {
                        "name": device["name"],
                        "zone": device.get("zone", "unknown"),
                        "opcua": protocols["opcua"],
                    }
                )

        if servers:
            print(f"OPC UA Servers ({len(servers)}):")
            print()
            print(f"{'Name':<30} {'Zone':<18} {'Policy':<22} {'Port':<8} {'Cert':<10}")
            print("-" * 90)

            cert_dir = opcua_sec.get("cert_dir", "certs")
            for srv in servers:
                opcua_cfg = srv["opcua"]

                # Determine effective policy
                if enforcement:
                    override = overrides.get(srv["name"], {})
                    eff_policy = override.get(
                        "security_policy",
                        opcua_sec.get("security_policy", "Aes256_Sha256_RsaPss"),
                    )
                else:
                    eff_policy = opcua_cfg.get("security_policy", "None")

                port = opcua_cfg.get("port", "?")

                # Check certificate
                cert_path = Path(cert_dir) / f"{srv['name']}.crt"
                cert_status = "Yes" if cert_path.exists() else "No"

                print(
                    f"{srv['name']:<30} {srv['zone']:<18} {eff_policy:<22} {port:<8} {cert_status:<10}"
                )

            print()

        if not enforcement:
            print("To enable OPC UA encryption (Challenge 7):")
            print(
                "  1. Generate certificates: python tools/blue_team.py opcua generate-certs"
            )
            print("  2. Edit config/opcua_security.yml: enforcement_enabled: true")
            print("  3. Restart simulation: python tools/simulator_manager.py")
            print()
        if not require_auth:
            print("To enable OPC UA authentication (Challenge 1):")
            print("  1. Edit config/opcua_security.yml: require_authentication: true")
            print("  2. Restart simulation: python tools/simulator_manager.py")
            print()
        if not enforcement or not require_auth:
            print("NOTE: OPC UA security settings require restart.")
            print("      You cannot change authentication/TLS on a live server.")
        print()
        print("=" * 70)
        return 0

    async def opcua_list_users(self, args):
        """List users that can authenticate to OPC UA servers."""
        from components.security.opcua_user_manager import OPCUAUserManager

        auth_mgr = AuthenticationManager()
        user_mgr = OPCUAUserManager(auth_mgr)

        print("=" * 70)
        print("OPC UA Authentication Users")
        print("=" * 70)
        print()
        print(f"{'Username':<16} {'Simulator Role':<14} {'OPC UA Role':<12} {'Status':<10} {'Name'}")
        print("-" * 75)

        from asyncua.server.user_managers import UserRole as OPCUAUserRole

        for username, user in auth_mgr.users.items():
            opcua_role = user_mgr._map_role(user.role)
            status = "Active" if user.active else "LOCKED"
            print(
                f"{username:<16} {user.role.name:<14} {opcua_role.name:<12} {status:<10} {user.full_name}"
            )

        print()
        print(f"Total: {len(auth_mgr.users)} users")

        from config.config_loader import ConfigLoader

        config = ConfigLoader().load_all()
        opcua_sec = config.get("opcua_security", {})
        require_auth = opcua_sec.get("require_authentication", False)

        if not require_auth:
            print()
            print("Authentication is DISABLED. Enable with:")
            print("  1. Edit config/opcua_security.yml: require_authentication: true")
            print("  2. Restart simulation")
        print()
        print("=" * 70)
        return 0

    async def opcua_generate_certs(self, args):
        """Generate certificates for OPC UA servers."""
        from config.config_loader import ConfigLoader

        config = ConfigLoader().load_all()
        opcua_sec = config.get("opcua_security", {})

        key_size = opcua_sec.get("key_size", 2048)
        validity_hours = opcua_sec.get("validity_hours", 8760)
        cert_dir_name = opcua_sec.get("cert_dir", "certs")

        # Discover OPC UA servers
        servers = []
        for device in config.get("devices", []):
            protocols = device.get("protocols", {})
            if "opcua" in protocols:
                servers.append(
                    {
                        "name": device["name"],
                        "description": device.get("description", ""),
                    }
                )

        if not servers:
            print("No OPC UA servers found in config/devices.yml")
            return 1

        # Filter by server name if specified
        server_name = getattr(args, "server", None)
        if server_name:
            servers = [s for s in servers if s["name"] == server_name]
            if not servers:
                print(f"Server not found: {server_name}")
                return 1

        force = getattr(args, "force", False)

        certs_dir = Path(cert_dir_name)
        certs_dir.mkdir(exist_ok=True)

        from cryptography.hazmat.primitives import serialization

        from components.security.encryption import CertificateInfo, CertificateManager

        cert_manager = CertificateManager(data_store=None, cert_dir=certs_dir)

        print("OPC UA Certificate Generator")
        print(f"Output directory: {certs_dir.absolute()}")
        print(f"Key size: {key_size} bits")
        print(f"Validity: {validity_hours} hours ({validity_hours / 24:.0f} days)")
        print()

        generated = 0
        for srv in servers:
            cert_path = certs_dir / f"{srv['name']}.crt"
            key_path = certs_dir / f"{srv['name']}.key"

            if cert_path.exists() and key_path.exists() and not force:
                print(f"  Skipping {srv['name']} (exists, use --force to overwrite)")
                continue

            print(f"Generating certificate for: {srv['name']}")

            certificate, private_key = cert_manager.generate_self_signed_cert(
                common_name=srv["name"],
                organization="Unseen University Power & Light Co.",
                validity_hours=validity_hours,
                key_size=key_size,
            )

            cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
            cert_path.write_bytes(cert_pem)

            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
            key_path.write_bytes(key_pem)

            cert_info = CertificateInfo.from_x509(certificate)

            print(f"  Certificate: {cert_path}")
            print(f"  Private Key: {key_path}")
            print(f"  Fingerprint: {cert_info.fingerprint_sha256}")
            print(f"  Valid until: {cert_info.not_valid_after}")
            print()
            generated += 1

        if generated > 0:
            print(f"Generated {generated} certificate(s)")
            print()
            print("To enable OPC UA encryption:")
            print("  1. Edit config/opcua_security.yml: enforcement_enabled: true")
            print("  2. Restart simulation: python tools/simulator_manager.py")
        else:
            print("No certificates generated (all exist, use --force to overwrite)")

        return 0

    async def opcua_list_certs(self, args):
        """List OPC UA certificates."""
        from config.config_loader import ConfigLoader

        config = ConfigLoader().load_all()
        opcua_sec = config.get("opcua_security", {})
        cert_dir_name = opcua_sec.get("cert_dir", "certs")
        certs_dir = Path(cert_dir_name)

        # Discover OPC UA servers
        servers = []
        for device in config.get("devices", []):
            protocols = device.get("protocols", {})
            if "opcua" in protocols:
                servers.append(device["name"])

        if not certs_dir.exists():
            print(f"Certificate directory not found: {certs_dir}")
            print("Run: python tools/blue_team.py opcua generate-certs")
            return 1

        print(f"OPC UA Certificates ({cert_dir_name}/):")
        print()
        print(f"{'Server':<30} {'Status':<12} {'Valid Until':<25} {'Key Size':<10}")
        print("-" * 80)

        from cryptography import x509

        found_any = False
        for server_name in servers:
            cert_path = certs_dir / f"{server_name}.crt"
            key_path = certs_dir / f"{server_name}.key"

            if cert_path.exists():
                found_any = True
                try:
                    with open(cert_path, "rb") as f:
                        cert = x509.load_pem_x509_certificate(f.read())

                    valid_until = cert.not_valid_after_utc.strftime(
                        "%Y-%m-%d %H:%M UTC"
                    )
                    pub_key = cert.public_key()
                    key_size_bits = pub_key.key_size

                    status = "OK" if key_path.exists() else "KEY MISSING"

                    print(
                        f"{server_name:<30} {status:<12} {valid_until:<25} {key_size_bits:<10}"
                    )
                except Exception as e:
                    print(f"{server_name:<30} {'ERROR':<12} {str(e)[:25]:<25}")
            else:
                print(f"{server_name:<30} {'Not found':<12}")

        if not found_any:
            print()
            print("No certificates found.")
            print("Run: python tools/blue_team.py opcua generate-certs")

        print()
        return 0

    async def opcua_validate_cert(self, args):
        """Validate a specific OPC UA certificate."""
        server_name = args.name

        from config.config_loader import ConfigLoader

        config = ConfigLoader().load_all()
        opcua_sec = config.get("opcua_security", {})
        cert_dir_name = opcua_sec.get("cert_dir", "certs")

        cert_path = Path(cert_dir_name) / f"{server_name}.crt"
        key_path = Path(cert_dir_name) / f"{server_name}.key"

        if not cert_path.exists():
            print(f"Certificate not found: {cert_path}")
            print(
                f"Run: python tools/blue_team.py opcua generate-certs --server {server_name}"
            )
            return 1

        from cryptography import x509
        from cryptography.hazmat.primitives import serialization

        print(f"Certificate Validation: {server_name}")
        print("=" * 70)
        print()

        try:
            with open(cert_path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read())

            from components.security.encryption import CertificateInfo

            cert_info = CertificateInfo.from_x509(cert)

            print(f"Subject: {cert_info.subject}")
            print(f"Issuer: {cert_info.issuer}")
            print(f"Serial Number: {cert_info.serial_number}")
            print(f"Not Valid Before: {cert_info.not_valid_before}")
            print(f"Not Valid After: {cert_info.not_valid_after}")
            print(f"Public Key Algorithm: {cert_info.public_key_algorithm}")
            print(f"Key Size: {cert.public_key().key_size} bits")
            print(f"Signature Algorithm: {cert_info.signature_algorithm}")
            print(f"SHA-256 Fingerprint: {cert_info.fingerprint_sha256}")
            print()

            # Check key file
            if key_path.exists():
                print(f"Private Key: {key_path} (present)")

                # Verify key matches certificate
                try:
                    with open(key_path, "rb") as f:
                        private_key = serialization.load_pem_private_key(
                            f.read(), password=None
                        )
                    cert_pub = cert.public_key().public_bytes(
                        serialization.Encoding.PEM,
                        serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                    key_pub = private_key.public_key().public_bytes(
                        serialization.Encoding.PEM,
                        serialization.PublicFormat.SubjectPublicKeyInfo,
                    )
                    if cert_pub == key_pub:
                        print("Key Match: OK (private key matches certificate)")
                    else:
                        print(
                            "Key Match: MISMATCH (private key does not match certificate)"
                        )
                except Exception as e:
                    print(f"Key Validation: ERROR ({e})")
            else:
                print(f"Private Key: MISSING ({key_path})")
            print()

            # SAN extensions
            try:
                san = cert.extensions.get_extension_for_class(
                    x509.SubjectAlternativeName
                )
                dns_names = san.value.get_values_for_type(x509.DNSName)
                if dns_names:
                    print("Subject Alternative Names:")
                    for name in dns_names:
                        print(f"  DNS: {name}")
                    print()
            except x509.ExtensionNotFound:
                pass

        except Exception as e:
            print(f"Error reading certificate: {e}")
            return 1

        print("=" * 70)
        return 0

    # ================================================================
    # General Commands
    # ================================================================

    async def status(self, args):
        """Show overall security status."""
        print("=" * 70)
        print("Blue Team Security Status")
        print("=" * 70)
        print()

        # Firewall status
        fw_stats = self.firewall.get_statistics()
        print("Firewall:")
        print(f"  Default Action: {self.firewall.default_action.value}")
        print(f"  Active Rules: {fw_stats['active_rules']}")
        print(f"  Connections Checked: {fw_stats['total_connections_checked']}")
        print(f"  Connections Blocked: {fw_stats['total_connections_blocked']}")
        print()

        # IDS/IPS status
        ids_stats = self.ids_system.get_statistics()
        mode_str = (
            "IPS (BLOCKING)"
            if ids_stats["ips"]["prevention_mode"]
            else "IDS (Detection Only)"
        )
        print("IDS/IPS:")
        print(f"  Mode: {mode_str}")
        print(f"  Blocked IPs: {ids_stats['ips']['blocked_ips']}")
        print(f"  Active Alerts: {ids_stats['alerts']['active']}")
        print()

        # RBAC status
        enforcement_status = (
            "ENABLED" if self.data_store.rbac_enabled else "DISABLED (VULNERABLE)"
        )
        print("RBAC:")
        print(f"  Enforcement: {enforcement_status}")
        print(f"  Active Users: {len(self.auth_mgr.users)}")
        print(f"  Active Sessions: {len(self.auth_mgr.sessions)}")
        print()

        # Modbus filter status
        modbus_stats = self.modbus_filter.get_statistics()
        modbus_enforcement = (
            "ENABLED"
            if modbus_stats["enforcement_enabled"]
            else "DISABLED (VULNERABLE)"
        )
        print("Modbus Filter:")
        print(f"  Enforcement: {modbus_enforcement}")
        print(f"  Policy Mode: {modbus_stats['global_policy']['mode']}")
        print(f"  Requests Checked: {modbus_stats['total_requests_checked']}")
        print(f"  Requests Blocked: {modbus_stats['total_requests_blocked']}")
        print()

        # OPC UA Security status
        from config.config_loader import ConfigLoader

        config = ConfigLoader().load_all()
        opcua_sec = config.get("opcua_security", {})
        opcua_enforcement = (
            "ENABLED"
            if opcua_sec.get("enforcement_enabled", False)
            else "DISABLED (VULNERABLE)"
        )
        opcua_policy = opcua_sec.get("security_policy", "None")

        # Count servers with certificates
        cert_dir = opcua_sec.get("cert_dir", "certs")
        opcua_servers = [
            d for d in config.get("devices", []) if "opcua" in d.get("protocols", {})
        ]
        certs_found = sum(
            1 for d in opcua_servers if Path(cert_dir, f"{d['name']}.crt").exists()
        )

        opcua_auth = (
            "ENABLED"
            if opcua_sec.get("require_authentication", False)
            else "DISABLED (VULNERABLE)"
        )

        print("OPC UA Security:")
        print(f"  Encryption: {opcua_enforcement}")
        print(f"  Authentication: {opcua_auth}")
        print(f"  Policy: {opcua_policy}")
        print(f"  Servers: {len(opcua_servers)}")
        print(f"  Certificates: {certs_found}/{len(opcua_servers)}")
        print()

        print("=" * 70)
        return 0


def create_parser():
    """Create argument parser with all commands."""
    parser = argparse.ArgumentParser(
        description="Blue Team CLI - Runtime Security Operations",
        epilog="""
Examples:
  # Block attacker IP immediately
  python tools/blue_team.py ids block-ip 192.168.1.100 "Active attack"

  # Enable IPS mode (active blocking)
  python tools/blue_team.py ids enable-ips

  # Add emergency firewall rule
  python tools/blue_team.py firewall add-rule \\
    --name "Emergency: Block attacker" \\
    --action DROP \\
    --source-ip 192.168.1.100 \\
    --reason "Malware detected"

  # Show security status
  python tools/blue_team.py status

Note: All changes are RUNTIME (immediate but lost on restart).
To make permanent, edit config/*.yml and restart simulator.
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--user",
        default="security_admin",
        help="User performing action (for audit trail)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # ================================================================
    # Firewall Commands
    # ================================================================
    fw_parser = subparsers.add_parser("firewall", help="Firewall operations")
    fw_subparsers = fw_parser.add_subparsers(dest="subcommand")

    # firewall add-rule
    add_rule_parser = fw_subparsers.add_parser(
        "add-rule",
        help="Add firewall rule (runtime, lost on restart)",
    )
    add_rule_parser.add_argument("--name", required=True, help="Rule name")
    add_rule_parser.add_argument(
        "--action",
        required=True,
        choices=["allow", "deny", "drop", "reject"],
        help="Rule action: allow, deny, drop (silent), reject (send RST)",
    )
    add_rule_parser.add_argument(
        "--priority",
        type=int,
        default=100,
        help="Rule priority (lower = higher priority, default: 100)",
    )
    add_rule_parser.add_argument(
        "--source-zone", default="any", help="Source zone name or 'any'"
    )
    add_rule_parser.add_argument(
        "--source-network", default="any", help="Source network name or 'any'"
    )
    add_rule_parser.add_argument(
        "--source-ip", default="any", help="Source IP address or 'any'"
    )
    add_rule_parser.add_argument(
        "--dest-zone", default="any", help="Destination zone name or 'any'"
    )
    add_rule_parser.add_argument(
        "--dest-network", default="any", help="Destination network name or 'any'"
    )
    add_rule_parser.add_argument(
        "--dest-ip", default="any", help="Destination IP address or 'any'"
    )
    add_rule_parser.add_argument(
        "--dest-port", type=int, help="Destination port number"
    )
    add_rule_parser.add_argument("--description", default="", help="Rule description")
    add_rule_parser.add_argument("--reason", default="", help="Reason for adding rule")

    # firewall remove-rule
    remove_rule_parser = fw_subparsers.add_parser(
        "remove-rule", help="Remove firewall rule"
    )
    remove_rule_parser.add_argument("rule_id", help="Rule ID to remove")
    remove_rule_parser.add_argument("--reason", default="", help="Reason for removal")

    # firewall list-rules
    list_rules_parser = fw_subparsers.add_parser(
        "list-rules", help="List firewall rules"
    )
    list_rules_parser.add_argument(
        "--enabled-only", action="store_true", help="Show only enabled rules"
    )
    list_rules_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed information"
    )

    # firewall enable-rule
    enable_rule_parser = fw_subparsers.add_parser(
        "enable-rule", help="Enable firewall rule"
    )
    enable_rule_parser.add_argument("rule_id", help="Rule ID to enable")

    # firewall disable-rule
    disable_rule_parser = fw_subparsers.add_parser(
        "disable-rule", help="Disable firewall rule"
    )
    disable_rule_parser.add_argument("rule_id", help="Rule ID to disable")

    # ================================================================
    # IDS/IPS Commands
    # ================================================================
    ids_parser = subparsers.add_parser("ids", help="IDS/IPS operations")
    ids_subparsers = ids_parser.add_subparsers(dest="subcommand")

    # ids enable-ips
    ids_subparsers.add_parser(
        "enable-ips",
        help="Enable IPS mode (active blocking)",
    )

    # ids disable-ips
    ids_subparsers.add_parser(
        "disable-ips",
        help="Disable IPS mode (return to detection-only)",
    )

    # ids block-ip
    block_ip_parser = ids_subparsers.add_parser("block-ip", help="Block IP address")
    block_ip_parser.add_argument("ip", help="IP address to block")
    block_ip_parser.add_argument("reason", help="Reason for blocking")

    # ids unblock-ip
    unblock_ip_parser = ids_subparsers.add_parser(
        "unblock-ip", help="Unblock IP address"
    )
    unblock_ip_parser.add_argument("ip", help="IP address to unblock")

    # ids list-blocked
    ids_subparsers.add_parser("list-blocked", help="List blocked IP addresses")

    # ids status
    ids_subparsers.add_parser("status", help="Show IDS/IPS status")

    # ================================================================
    # RBAC Commands
    # ================================================================
    rbac_parser = subparsers.add_parser("rbac", help="RBAC operations")
    rbac_subparsers = rbac_parser.add_subparsers(dest="subcommand")

    # rbac list-users
    list_users_parser = rbac_subparsers.add_parser(
        "list-users", help="List all users and roles"
    )
    list_users_parser.add_argument("--username", help="Show specific user details")

    # rbac change-role
    change_role_parser = rbac_subparsers.add_parser(
        "change-role", help="Change user role (runtime)"
    )
    change_role_parser.add_argument(
        "--username", required=True, help="Username to modify"
    )
    change_role_parser.add_argument(
        "--role",
        required=True,
        choices=["VIEWER", "OPERATOR", "ENGINEER", "SUPERVISOR", "ADMIN"],
        help="New role",
    )
    change_role_parser.add_argument(
        "--user", default="admin", help="Admin user making the change"
    )
    change_role_parser.add_argument(
        "--reason", default="", help="Reason for role change"
    )

    # rbac lock-user
    lock_user_parser = rbac_subparsers.add_parser(
        "lock-user", help="Lock user account (runtime)"
    )
    lock_user_parser.add_argument("--username", required=True, help="Username to lock")
    lock_user_parser.add_argument(
        "--user", default="admin", help="Admin user making the change"
    )
    lock_user_parser.add_argument(
        "--reason", required=True, help="Reason for locking account"
    )

    # rbac unlock-user
    unlock_user_parser = rbac_subparsers.add_parser(
        "unlock-user", help="Unlock user account (runtime)"
    )
    unlock_user_parser.add_argument(
        "--username", required=True, help="Username to unlock"
    )
    unlock_user_parser.add_argument(
        "--user", default="admin", help="Admin user making the change"
    )

    # rbac enable
    enable_rbac_parser = rbac_subparsers.add_parser(
        "enable", help="Enable RBAC enforcement (runtime)"
    )
    enable_rbac_parser.add_argument(
        "--user", default="admin", help="Admin user making the change"
    )
    enable_rbac_parser.add_argument(
        "--reason", default="", help="Reason for enabling RBAC"
    )

    # rbac disable
    disable_rbac_parser = rbac_subparsers.add_parser(
        "disable", help="Disable RBAC enforcement (DANGEROUS)"
    )
    disable_rbac_parser.add_argument(
        "--user", default="admin", help="Admin user making the change"
    )
    disable_rbac_parser.add_argument(
        "--reason", required=True, help="Reason for disabling RBAC (required)"
    )

    # rbac audit-log
    audit_log_parser = rbac_subparsers.add_parser(
        "audit-log", help="View RBAC audit log"
    )
    audit_log_parser.add_argument("--user", help="Filter by username")
    audit_log_parser.add_argument(
        "--limit", type=int, default=50, help="Maximum entries to show"
    )
    audit_log_parser.add_argument(
        "--filter", choices=["denied"], help="Filter by result (e.g., denied)"
    )

    # rbac list-sessions
    rbac_subparsers.add_parser(
        "list-sessions", help="List active authentication sessions"
    )

    # rbac logout-session
    logout_session_parser = rbac_subparsers.add_parser(
        "logout-session", help="Force logout a session (emergency/testing)"
    )
    logout_session_parser.add_argument(
        "session_id", help="Session ID (full or partial)"
    )
    logout_session_parser.add_argument(
        "--reason", default="Forced logout by security admin", help="Reason for logout"
    )

    # ================================================================
    # Anomaly Detection Commands (Challenge 4)
    # ================================================================
    anomaly_parser = subparsers.add_parser(
        "anomaly", help="Anomaly detection operations"
    )
    anomaly_subparsers = anomaly_parser.add_subparsers(dest="subcommand")

    # anomaly enable
    anomaly_subparsers.add_parser(
        "enable", help="Enable anomaly detection (runtime)"
    )

    # anomaly disable
    anomaly_disable_parser = anomaly_subparsers.add_parser(
        "disable", help="Disable anomaly detection (DANGEROUS)"
    )
    anomaly_disable_parser.add_argument(
        "--reason", required=True, help="Reason for disabling detection (required)"
    )

    # anomaly add-baseline
    add_baseline_parser = anomaly_subparsers.add_parser(
        "add-baseline", help="Add parameter to baseline monitoring"
    )
    add_baseline_parser.add_argument("--device", required=True, help="Device name")
    add_baseline_parser.add_argument(
        "--parameter", required=True, help="Parameter name"
    )
    add_baseline_parser.add_argument(
        "--learning-window",
        type=int,
        default=1000,
        help="Learning window size (default: 1000)",
    )

    # anomaly set-range
    set_range_parser = anomaly_subparsers.add_parser(
        "set-range", help="Set range limits for parameter"
    )
    set_range_parser.add_argument("--device", required=True, help="Device name")
    set_range_parser.add_argument("--parameter", required=True, help="Parameter name")
    set_range_parser.add_argument(
        "--min", type=float, required=True, help="Minimum allowed value"
    )
    set_range_parser.add_argument(
        "--max", type=float, required=True, help="Maximum allowed value"
    )

    # anomaly set-rate
    set_rate_parser = anomaly_subparsers.add_parser(
        "set-rate", help="Set rate-of-change limit for parameter"
    )
    set_rate_parser.add_argument("--device", required=True, help="Device name")
    set_rate_parser.add_argument("--parameter", required=True, help="Parameter name")
    set_rate_parser.add_argument(
        "--max-rate",
        type=float,
        required=True,
        help="Maximum rate of change per second",
    )

    # anomaly list
    list_anomalies_parser = anomaly_subparsers.add_parser(
        "list", help="List recent anomalies"
    )
    list_anomalies_parser.add_argument(
        "--limit", type=int, default=50, help="Maximum anomalies to show (default: 50)"
    )

    # anomaly stats
    anomaly_subparsers.add_parser(
        "stats", help="Show anomaly detection statistics"
    )

    # anomaly clear
    anomaly_subparsers.add_parser(
        "clear", help="Clear anomaly history"
    )

    # ================================================================
    # Modbus Commands
    # ================================================================
    modbus_parser = subparsers.add_parser(
        "modbus", help="Modbus function code filtering"
    )
    modbus_subparsers = modbus_parser.add_subparsers(dest="subcommand")

    # modbus enable
    modbus_enable_parser = modbus_subparsers.add_parser(
        "enable", help="Enable function code filtering (runtime)"
    )
    modbus_enable_parser.add_argument(
        "--user", default="admin", help="Admin user making the change"
    )
    modbus_enable_parser.add_argument(
        "--reason", default="", help="Reason for enabling filter"
    )

    # modbus disable
    modbus_disable_parser = modbus_subparsers.add_parser(
        "disable", help="Disable function code filtering (DANGEROUS)"
    )
    modbus_disable_parser.add_argument(
        "--user", default="admin", help="Admin user making the change"
    )
    modbus_disable_parser.add_argument(
        "--reason", required=True, help="Reason for disabling filter (required)"
    )

    # modbus set-policy
    set_policy_parser = modbus_subparsers.add_parser(
        "set-policy", help="Set device-specific policy (runtime)"
    )
    set_policy_parser.add_argument("--device", required=True, help="Device name")
    set_policy_parser.add_argument(
        "--mode", required=True, choices=["whitelist", "blacklist"], help="Policy mode"
    )
    set_policy_parser.add_argument(
        "--allowed", help="Comma-separated allowed function codes (whitelist mode)"
    )
    set_policy_parser.add_argument(
        "--blocked", help="Comma-separated blocked function codes (blacklist mode)"
    )
    set_policy_parser.add_argument(
        "--user", default="admin", help="Admin user making the change"
    )
    set_policy_parser.add_argument(
        "--reason", default="", help="Reason for policy change"
    )

    # modbus stats
    modbus_subparsers.add_parser(
        "stats", help="Show filter statistics"
    )

    # modbus status
    modbus_subparsers.add_parser(
        "status", help="Show filter status"
    )

    # ================================================================
    # Audit Log Commands (Challenge 3)
    # ================================================================
    audit_parser = subparsers.add_parser("audit", help="Audit log operations")
    audit_subparsers = audit_parser.add_subparsers(dest="subcommand")

    # audit query
    query_parser = audit_subparsers.add_parser(
        "query", help="Query audit logs with filters"
    )
    query_parser.add_argument(
        "--limit", type=int, default=50, help="Maximum events to show (default: 50)"
    )
    query_parser.add_argument("--device", help="Filter by device name")
    query_parser.add_argument(
        "--category",
        choices=[
            "security",
            "safety",
            "process",
            "alarm",
            "audit",
            "system",
            "communication",
            "diagnostic",
        ],
        help="Filter by event category",
    )
    query_parser.add_argument(
        "--severity",
        choices=["CRITICAL", "ALERT", "ERROR", "WARNING", "NOTICE", "INFO", "DEBUG"],
        help="Filter by severity level",
    )
    query_parser.add_argument("--user-filter", help="Filter by username")
    query_parser.add_argument("--action", help="Filter by action type")
    query_parser.add_argument(
        "--since", type=float, help="Show events after this simulation time"
    )
    query_parser.add_argument(
        "--until", type=float, help="Show events before this simulation time"
    )
    query_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show detailed information"
    )

    # audit stats
    audit_subparsers.add_parser(
        "stats", help="Show audit log statistics"
    )

    # audit export
    export_parser = audit_subparsers.add_parser(
        "export", help="Export audit logs to file"
    )
    export_parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json",
        help="Export format (default: json)",
    )
    export_parser.add_argument(
        "--output", help="Output filename (auto-generated if not specified)"
    )
    export_parser.add_argument("--limit", type=int, help="Maximum events to export")
    export_parser.add_argument("--device", help="Filter by device name")
    export_parser.add_argument("--category", help="Filter by category")

    # audit search
    search_parser = audit_subparsers.add_parser(
        "search", help="Search audit logs with regex pattern"
    )
    search_parser.add_argument("pattern", help="Regex pattern to search for")
    search_parser.add_argument(
        "--limit", type=int, default=100, help="Maximum events to search (default: 100)"
    )

    # ================================================================
    # OPC UA Security Commands (Challenge 7)
    # ================================================================
    opcua_parser = subparsers.add_parser(
        "opcua", help="OPC UA security and certificate management"
    )
    opcua_subparsers = opcua_parser.add_subparsers(dest="subcommand")

    # opcua status
    opcua_subparsers.add_parser(
        "status", help="Show OPC UA security configuration and server status"
    )

    # opcua generate-certs
    gen_certs_parser = opcua_subparsers.add_parser(
        "generate-certs", help="Generate certificates for OPC UA servers"
    )
    gen_certs_parser.add_argument(
        "--server", help="Generate certificate for specific server only"
    )
    gen_certs_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing certificates"
    )

    # opcua list-users (Challenge 1)
    opcua_subparsers.add_parser(
        "list-users", help="List users that can authenticate to OPC UA servers"
    )

    # opcua list-certs
    opcua_subparsers.add_parser(
        "list-certs", help="List OPC UA certificates and their status"
    )

    # opcua validate-cert
    validate_cert_parser = opcua_subparsers.add_parser(
        "validate-cert", help="Validate a specific OPC UA certificate"
    )
    validate_cert_parser.add_argument("name", help="Server name to validate")

    # ================================================================
    # General Commands
    # ================================================================
    subparsers.add_parser("status", help="Show overall security status")

    return parser


async def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    # Initialize CLI
    cli = BlueTeamCLI()
    try:
        await cli.initialize()
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        print("   Is the simulator running?")
        return 1

    # Route to command handler
    try:
        if args.command == "firewall":
            if args.subcommand == "add-rule":
                return await cli.firewall_add_rule(args)
            elif args.subcommand == "remove-rule":
                return await cli.firewall_remove_rule(args)
            elif args.subcommand == "list-rules":
                return await cli.firewall_list_rules(args)
            elif args.subcommand == "enable-rule":
                return await cli.firewall_enable_rule(args)
            elif args.subcommand == "disable-rule":
                return await cli.firewall_disable_rule(args)
            else:
                parser.parse_args(["firewall", "--help"])

        elif args.command == "ids":
            if args.subcommand == "enable-ips":
                return await cli.ids_enable_ips(args)
            elif args.subcommand == "disable-ips":
                return await cli.ids_disable_ips(args)
            elif args.subcommand == "block-ip":
                return await cli.ids_block_ip(args)
            elif args.subcommand == "unblock-ip":
                return await cli.ids_unblock_ip(args)
            elif args.subcommand == "list-blocked":
                return await cli.ids_list_blocked(args)
            elif args.subcommand == "status":
                return await cli.ids_status(args)
            else:
                parser.parse_args(["ids", "--help"])

        elif args.command == "rbac":
            if args.subcommand == "list-users":
                return await cli.rbac_list_users(args)
            elif args.subcommand == "change-role":
                return await cli.rbac_change_role(args)
            elif args.subcommand == "lock-user":
                return await cli.rbac_lock_user(args)
            elif args.subcommand == "unlock-user":
                return await cli.rbac_unlock_user(args)
            elif args.subcommand == "enable":
                return await cli.rbac_enable(args)
            elif args.subcommand == "disable":
                return await cli.rbac_disable(args)
            elif args.subcommand == "audit-log":
                return await cli.rbac_audit_log(args)
            elif args.subcommand == "list-sessions":
                return await cli.rbac_list_sessions(args)
            elif args.subcommand == "logout-session":
                return await cli.rbac_logout_session(args)
            else:
                parser.parse_args(["rbac", "--help"])

        elif args.command == "modbus":
            if args.subcommand == "enable":
                return await cli.modbus_enable(args)
            elif args.subcommand == "disable":
                return await cli.modbus_disable(args)
            elif args.subcommand == "set-policy":
                return await cli.modbus_set_policy(args)
            elif args.subcommand == "stats":
                return await cli.modbus_stats(args)
            elif args.subcommand == "status":
                return await cli.modbus_status(args)
            else:
                parser.parse_args(["modbus", "--help"])

        elif args.command == "audit":
            if args.subcommand == "query":
                return await cli.audit_query(args)
            elif args.subcommand == "stats":
                return await cli.audit_stats(args)
            elif args.subcommand == "export":
                return await cli.audit_export(args)
            elif args.subcommand == "search":
                return await cli.audit_search(args)
            else:
                parser.parse_args(["audit", "--help"])

        elif args.command == "anomaly":
            if args.subcommand == "enable":
                return await cli.anomaly_enable(args)
            elif args.subcommand == "disable":
                return await cli.anomaly_disable(args)
            elif args.subcommand == "add-baseline":
                return await cli.anomaly_add_baseline(args)
            elif args.subcommand == "set-range":
                return await cli.anomaly_set_range(args)
            elif args.subcommand == "set-rate":
                return await cli.anomaly_set_rate(args)
            elif args.subcommand == "list":
                return await cli.anomaly_list(args)
            elif args.subcommand == "stats":
                return await cli.anomaly_stats(args)
            elif args.subcommand == "clear":
                return await cli.anomaly_clear(args)
            else:
                parser.parse_args(["anomaly", "--help"])

        elif args.command == "opcua":
            if args.subcommand == "status":
                return await cli.opcua_status(args)
            elif args.subcommand == "list-users":
                return await cli.opcua_list_users(args)
            elif args.subcommand == "generate-certs":
                return await cli.opcua_generate_certs(args)
            elif args.subcommand == "list-certs":
                return await cli.opcua_list_certs(args)
            elif args.subcommand == "validate-cert":
                return await cli.opcua_validate_cert(args)
            else:
                parser.parse_args(["opcua", "--help"])

        elif args.command == "status":
            return await cli.status(args)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 130
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
