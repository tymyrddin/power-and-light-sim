#!/usr/bin/env python3
"""
Example: Blue Team Defensive Actions

Demonstrates how blue team defenders use Firewall and IDS/IPS devices
to respond to attacks. Defenders are INSIDE the simulation, attackers
are OUTSIDE (running scripts from terminal).

Workshop Flow:
1. Initial state: All defenses disabled (attacks succeed)
2. Configure defenses: Enable IPS, add firewall rules, enable OPC UA auth
3. Re-run attacks: Attacks now fail (blocked by defenses)
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from components.devices.enterprise_zone import IDSSystem
from components.devices.enterprise_zone.firewall import (
    Firewall,
    RuleAction,
    RuleProtocol,
)
from components.network.protocol_simulator import ProtocolSimulator
from components.state.data_store import DataStore
from components.state.system_state import SystemState


async def main():
    """Blue team defensive operations demonstration."""

    print("=" * 70)
    print("Blue Team Defensive Operations")
    print("=" * 70)
    print()

    # ================================================================
    # INITIALIZE SIMULATION
    # ================================================================
    print("[1/5] Initializing simulation...")

    # Create core components
    system_state = SystemState()
    data_store = DataStore(system_state=system_state)

    print("✓ Simulation initialized")
    print()

    # ================================================================
    # CREATE SECURITY DEVICES (Blue Team Infrastructure)
    # ================================================================
    print("[2/5] Deploying blue team security devices...")

    # Create Firewall device
    firewall = Firewall(
        device_name="firewall_primary",
        device_id=500,
        data_store=data_store,
        description="Industrial Firewall - Zone boundary protection",
    )
    await firewall.start()
    print("✓ Firewall deployed")

    # Create IDS device (starts in detection-only mode)
    ids_system = IDSSystem(
        device_name="ids_primary",
        device_id=400,
        data_store=data_store,
        description="IDS/IPS - Network threat detection",
    )
    await ids_system.start()
    print("✓ IDS deployed (detection mode)")
    print()

    # ================================================================
    # INITIAL STATE: Vulnerable (attacks will succeed)
    # ================================================================
    print("[3/5] Initial configuration (VULNERABLE)...")
    print()

    print("Current security posture:")
    print(
        f"  • IDS Mode: {'IPS (blocking)' if ids_system.prevention_mode else 'IDS (detection only)'}"
    )
    print(f"  • Firewall Rules: {len(firewall.get_rules())} rules configured")
    print(f"  • Blocked IPs: {len(ids_system.get_blocked_ips())} IPs blocked")
    print("  • OPC UA Auth: Anonymous allowed (vulnerable)")
    print()
    print(">>> AT THIS POINT: Attack scripts from terminal will SUCCEED <<<")
    print()

    # ================================================================
    # BLUE TEAM RESPONSE: Enable Defenses
    # ================================================================
    print("[4/5] Blue team response: Configuring defenses...")
    print()

    # Action 1: Enable IPS mode on IDS
    print("Action 1: Enable IPS (Intrusion Prevention) mode")
    await ids_system.set_prevention_mode(enabled=True, user="security_admin")
    print("  ✓ IDS now in PREVENTION mode - will block threats")
    print()

    # Action 2: Block known attacker IP
    print("Action 2: Block known attacker IP")
    attacker_ip = "192.168.1.100"
    await ids_system.block_ip(
        ip_address=attacker_ip,
        reason="Suspicious scanning detected from security audit",
        user="security_admin",
    )
    print(f"  ✓ Blocked {attacker_ip}")
    print()

    # Action 3: Add firewall rule to block protocol from untrusted zone
    print("Action 3: Add firewall rule to block Modbus from corporate network")
    rule_id = await firewall.add_rule(
        name="Block Modbus from Corporate",
        action=RuleAction.DROP,
        source_zone="enterprise_zone",
        dest_zone="control_zone",
        protocol=RuleProtocol.MODBUS_TCP,
        description="Corporate network should not access control zone PLCs directly",
        user="security_admin",
        reason="Defense in depth - enforce zone segmentation",
    )
    print(f"  ✓ Added firewall rule {rule_id}")
    print()

    # Action 4: Block all traffic from DMZ to control zone
    print("Action 4: Emergency lockdown - block suspicious source")
    rule_id2 = await firewall.add_rule(
        name="Emergency: Block suspicious host",
        action=RuleAction.REJECT,
        source_ip="10.30.1.50",
        priority=1,  # High priority
        description="Emergency response to detected compromise",
        user="security_admin",
        reason="Host showing indicators of compromise",
    )
    print(f"  ✓ Added emergency rule {rule_id2}")
    print()

    # ================================================================
    # VERIFY DEFENSES ACTIVE
    # ================================================================
    print("[5/5] Security posture after blue team response:")
    print()

    # Get statistics
    fw_stats = firewall.get_statistics()
    ids_stats = ids_system.get_statistics()

    print("Firewall Status:")
    print(f"  • Active Rules: {fw_stats['active_rules']}")
    print(f"  • Connections Checked: {fw_stats['total_connections_checked']}")
    print(f"  • Connections Blocked: {fw_stats['total_connections_blocked']}")
    print()

    print("IDS/IPS Status:")
    print(
        f"  • Mode: {'IPS (PREVENTION)' if ids_stats['ips']['prevention_mode'] else 'IDS (DETECTION)'}"
    )
    print(f"  • Blocked IPs: {ids_stats['ips']['blocked_ips']}")
    print(f"  • Auto-block on Critical: {ids_stats['ips']['auto_block_enabled']}")
    print(f"  • Active Alerts: {ids_stats['alerts']['active']}")
    print()

    print(">>> NOW: Attack scripts from terminal will FAIL <<<")
    print()

    print("=" * 70)
    print("Blue Team Defenses Configured!")
    print("=" * 70)
    print()

    print("What happens now:")
    print("  1. Attacker from 192.168.1.100 → Connection DROPPED by IDS/IPS")
    print("  2. Modbus from enterprise_zone → Connection BLOCKED by Firewall")
    print("  3. Traffic from 10.30.1.50 → Connection REJECTED by Firewall")
    print("  4. Critical IDS alerts → Source IP auto-blocked")
    print()

    print("Try running attack scripts:")
    print("  $ python scripts/vulns/modbus_write.py --target hex_turbine_plc")
    print("  $ python scripts/vulns/opcua_readonly_probe.py")
    print()
    print("Attacks will be blocked and logged by blue team devices.")
    print()

    # Cleanup
    await firewall.stop()
    await ids_system.stop()


if __name__ == "__main__":
    asyncio.run(main())
