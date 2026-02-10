#!/usr/bin/env python3
"""
Example: Configuration Loading for Security Devices

Demonstrates how Firewall and IDS/IPS load baseline configuration from YAML files.
Respects architectural layering: ConfigLoader → Config Dict → Device

Configuration files (require restart):
  - config/firewall.yml
  - config/ids_ips.yml

Changes take effect after restart:
  python tools/simulator_manager.py
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from components.devices.enterprise_zone import Firewall, IDSSystem
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from config.config_loader import ConfigLoader


async def main():
    """Configuration loading demonstration."""

    print("=" * 70)
    print("Security Device Configuration Loading")
    print("=" * 70)
    print()

    # ================================================================
    # STEP 1: Load configuration (respects layering)
    # ================================================================
    print("[1/4] Loading configuration via ConfigLoader...")

    config_loader = ConfigLoader()
    config = config_loader.load_all()

    print("✓ Configuration loaded from config/*.yml")
    print(
        f"  • Firewall config: {len(config.get('firewall', {}).get('baseline_rules', []))} baseline rules"
    )
    print(
        f"  • IDS/IPS mode: {config.get('ids_ips', {}).get('prevention_mode', False)}"
    )
    print(
        f"  • Permanent blocks: {len(config.get('ids_ips', {}).get('permanent_blocked_ips', []))} IPs"
    )
    print()

    # ================================================================
    # STEP 2: Initialize devices
    # ================================================================
    print("[2/4] Initializing security devices...")

    system_state = SystemState()
    data_store = DataStore(system_state=system_state)

    # Create Firewall
    firewall = Firewall(
        device_name="firewall_primary",
        device_id=500,
        data_store=data_store,
    )

    # Create IDS/IPS
    ids_system = IDSSystem(
        device_name="ids_primary",
        device_id=400,
        data_store=data_store,
    )

    print("✓ Devices created")
    print()

    # ================================================================
    # STEP 3: Load configuration into devices
    # ================================================================
    print("[3/4] Loading configuration into devices...")

    # Load firewall config
    if "firewall" in config:
        await firewall.load_config(config["firewall"])
    else:
        print("  ⚠ No firewall.yml found, using defaults")

    # Load IDS/IPS config
    if "ids_ips" in config:
        await ids_system.load_config(config["ids_ips"])
    else:
        print("  ⚠ No ids_ips.yml found, using defaults")

    print()

    # ================================================================
    # STEP 4: Verify configuration loaded
    # ================================================================
    print("[4/4] Configuration status:")
    print()

    # Firewall status
    print("Firewall:")
    print(f"  • Default action: {firewall.default_action.value}")
    print(f"  • Baseline rules: {len(firewall.get_rules())} rules")
    for rule in firewall.get_rules()[:5]:  # Show first 5
        print(f"    - {rule.name} ({rule.action.value}) priority={rule.priority}")
    if len(firewall.get_rules()) > 5:
        print(f"    ... and {len(firewall.get_rules()) - 5} more")
    print()

    # IDS/IPS status
    print("IDS/IPS:")
    mode = (
        "IPS (Prevention - BLOCKS threats)"
        if ids_system.prevention_mode
        else "IDS (Detection only)"
    )
    print(f"  • Mode: {mode}")
    print(f"  • Auto-block on critical: {ids_system.auto_block_on_critical}")
    print(f"  • Permanent blocked IPs: {len(ids_system.get_blocked_ips())} IPs")
    for ip in ids_system.get_blocked_ips():
        print(f"    - {ip}")
    print("  • Detection thresholds:")
    print(f"    - Scan threshold: {ids_system.scan_threshold} ports")
    print(f"    - Violation threshold: {ids_system.violation_threshold} violations")
    print()

    print("=" * 70)
    print("Configuration Loaded Successfully!")
    print("=" * 70)
    print()

    print("To modify configuration:")
    print("  1. Edit config/firewall.yml or config/ids_ips.yml")
    print("  2. Restart simulator: python tools/simulator_manager.py")
    print()
    print("For runtime changes (incident response):")
    print("  await firewall.add_rule(...)")
    print("  await ids_system.block_ip(...)")
    print("  (Runtime changes are lost on restart unless added to config)")


if __name__ == "__main__":
    asyncio.run(main())
