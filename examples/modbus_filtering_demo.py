#!/usr/bin/env python3
"""
Example: Modbus Function Code Filtering Demonstration

Shows how protocol-level filtering blocks dangerous Modbus operations.
Demonstrates whitelist policy blocking FC 15/16 (batch writes) and FC 08 (diagnostics).

Workshop Flow:
1. Initial state: Filtering disabled (all function codes allowed - VULNERABLE)
2. Enable filtering: Whitelist blocks dangerous function codes
3. Runtime changes: Emergency lockdown, temporary engineering access
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from components.devices.enterprise_zone import ModbusFilter, PolicyMode
from components.state.data_store import DataStore
from components.state.system_state import SystemState


async def main():
    """Modbus function code filtering demonstration."""

    print("=" * 70)
    print("Modbus Function Code Filtering Demonstration")
    print("=" * 70)
    print()

    # ================================================================
    # INITIALIZE SIMULATION
    # ================================================================
    print("[1/5] Initializing simulation...")

    system_state = SystemState()
    data_store = DataStore(system_state=system_state)

    # Create Modbus filter
    modbus_filter = ModbusFilter(
        device_name="modbus_filter_primary",
        device_id=600,
        data_store=data_store,
        description="Modbus Function Code Filter - Protocol Security",
    )

    print("✓ Simulation initialized")
    print()

    # ================================================================
    # INITIAL STATE: FILTERING DISABLED (Vulnerable)
    # ================================================================
    print("[2/5] Initial state: Function code filtering DISABLED (VULNERABLE)")
    print()

    print(
        f"Enforcement: {'ENABLED' if modbus_filter.enforcement_enabled else 'DISABLED'}"
    )
    print()

    # Try dangerous function codes (should SUCCEED because filtering disabled)
    test_function_codes = [
        (3, "Read Holding Registers", "Safe"),
        (6, "Write Single Register", "Controlled Risk"),
        (15, "Write Multiple Coils", "DANGEROUS"),
        (16, "Write Multiple Registers", "DANGEROUS"),
        (8, "Diagnostics", "CRITICAL RISK"),
    ]

    print("Testing function codes with filtering DISABLED:")
    for fc, name, _risk in test_function_codes:
        allowed, reason = await modbus_filter.check_function_code(
            function_code=fc,
            device_name="test_plc",
            source_ip="192.168.1.100",
        )
        result = "✓ ALLOWED" if allowed else "❌ BLOCKED"
        print(f"  FC {fc:02d} ({name}): {result}")

    print()
    print(
        ">>> VULNERABILITY: All function codes allowed (including dangerous FC 15/16/08)!"
    )
    print()

    # ================================================================
    # ENABLE FILTERING WITH WHITELIST POLICY
    # ================================================================
    print("[3/5] Enabling function code filtering with whitelist policy...")
    print()

    # Enable enforcement
    await modbus_filter.set_enforcement(enabled=True, user="security_admin")

    # Set whitelist policy (only allow safe function codes)
    await modbus_filter.set_device_policy(
        device_name="test_plc",
        mode=PolicyMode.WHITELIST,
        allowed_codes={1, 2, 3, 4, 5, 6},  # Reads and single writes only
        user="security_admin",
    )

    print("✓ Filtering ENABLED with whitelist policy")
    print("  Allowed: FC 01-06 (read operations + single writes)")
    print("  Blocked: FC 15/16 (batch writes), FC 08 (diagnostics)")
    print()

    # ================================================================
    # TEST FUNCTION CODE FILTERING
    # ================================================================
    print("[4/5] Testing function codes with filtering ENABLED:")
    print()

    for fc, name, _risk in test_function_codes:
        allowed, reason = await modbus_filter.check_function_code(
            function_code=fc,
            device_name="test_plc",
            source_ip="192.168.1.100",
        )
        result = "✓ ALLOWED" if allowed else "❌ BLOCKED"
        status = (
            "(Expected)"
            if (fc <= 6 and allowed) or (fc > 6 and not allowed)
            else "(Unexpected)"
        )
        print(f"  FC {fc:02d} ({name}): {result} {status}")

    print()

    # ================================================================
    # RUNTIME INCIDENT RESPONSE SCENARIOS
    # ================================================================
    print("[5/5] Runtime incident response scenarios...")
    print()

    # Scenario 1: Emergency lockdown (read-only mode)
    print("Scenario 1: Emergency lockdown - switch to read-only")
    await modbus_filter.set_device_policy(
        device_name="test_plc",
        mode=PolicyMode.WHITELIST,
        allowed_codes={1, 2, 3, 4},  # Read only, no writes
        user="security_admin",
    )
    print("  ✓ Policy updated: Read-only mode (FC 01-04 only)")

    # Test write operation (should now be blocked)
    allowed, reason = await modbus_filter.check_function_code(
        function_code=6,
        device_name="test_plc",
        source_ip="192.168.1.100",
    )
    result = "BLOCKED" if not allowed else "ALLOWED (unexpected)"
    print(f"  Test FC 06 (Write Single Register): {result}")
    print()

    # Scenario 2: Temporary engineering access (allow diagnostics)
    print("Scenario 2: Temporary engineering access - allow FC 08 diagnostics")
    await modbus_filter.set_device_policy(
        device_name="test_plc",
        mode=PolicyMode.WHITELIST,
        allowed_codes={1, 2, 3, 4, 8},  # Read + diagnostics
        user="engineer1",
    )
    print("  ✓ Policy updated: Diagnostics temporarily allowed")

    # Test diagnostics operation (should now be allowed)
    allowed, reason = await modbus_filter.check_function_code(
        function_code=8,
        device_name="test_plc",
        source_ip="192.168.1.100",
    )
    result = "ALLOWED" if allowed else "BLOCKED (unexpected)"
    print(f"  Test FC 08 (Diagnostics): {result}")
    print()

    # Revoke diagnostics access
    print("  Troubleshooting complete - revoking diagnostics access")
    await modbus_filter.set_device_policy(
        device_name="test_plc",
        mode=PolicyMode.WHITELIST,
        allowed_codes={1, 2, 3, 4, 5, 6},  # Back to normal policy
        user="engineer1",
    )
    print("  ✓ Policy restored: Diagnostics blocked again")
    print()

    # ================================================================
    # STATISTICS
    # ================================================================
    print("=" * 70)
    print("Modbus Filter Statistics")
    print("=" * 70)
    print()

    stats = modbus_filter.get_statistics()
    print(f"Enforcement: {'ENABLED' if stats['enforcement_enabled'] else 'DISABLED'}")
    print(f"Global Policy Mode: {stats['global_policy']['mode']}")
    print(f"Total Requests Checked: {stats['total_requests_checked']}")
    print(f"Total Requests Blocked: {stats['total_requests_blocked']}")
    print(f"Block Rate: {stats['block_rate']:.1%}")
    print()

    if stats["blocked_by_function_code"]:
        print("Blocked by Function Code:")
        for fc, count in sorted(stats["blocked_by_function_code"].items()):
            fc_name = {
                8: "Diagnostics",
                15: "Write Multiple Coils",
                16: "Write Multiple Registers",
            }.get(fc, f"FC {fc}")
            print(f"  FC {fc:02d} ({fc_name}): {count} attempts")
        print()

    # ================================================================
    # SUMMARY
    # ================================================================
    print("=" * 70)
    print("Modbus Function Code Filtering Demo Complete!")
    print("=" * 70)
    print()

    print("Key Takeaways:")
    print("  1. Filtering disabled = VULNERABLE (all function codes allowed)")
    print("  2. Whitelist mode = Least privilege (allow only needed FCs)")
    print("  3. FC 01-06 = Standard operations (reads + single writes)")
    print("  4. FC 15-16 = DANGEROUS (batch writes, malware)")
    print("  5. FC 08 = CRITICAL (diagnostics, firmware access)")
    print("  6. Runtime policy changes = Immediate incident response")
    print("  7. Defense in Depth = Protocol filtering + RBAC + Firewall")
    print()

    print("Next Steps:")
    print(
        "  • Enable filtering in config/modbus_filtering.yml (enforcement_enabled: true)"
    )
    print("  • Configure whitelist policy (allowed_function_codes: [1, 2, 3, 4, 5, 6])")
    print("  • Test attack scripts with different function codes")
    print("  • Use Blue Team CLI for runtime incident response:")
    print("    python tools/blue_team.py modbus enable --user admin")
    print(
        "    python tools/blue_team.py modbus set-policy --device test_plc --mode whitelist --allowed 1,2,3,4"
    )
    print()


if __name__ == "__main__":
    asyncio.run(main())
