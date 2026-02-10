#!/usr/bin/env python3
"""
Example: RBAC (Role-Based Access Control) Demonstration

Shows how RBAC enforcement prevents unauthorized write operations.
Demonstrates different user roles and their permission boundaries.

Workshop Flow:
1. Initial state: RBAC disabled (all writes succeed - VULNERABLE)
2. Enable RBAC: Viewers blocked, operators/engineers allowed
3. Runtime changes: Downgrade compromised accounts, emergency overrides
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from components.security.authentication import AuthenticationManager, UserRole
from components.state.data_store import DataStore
from components.state.system_state import SystemState


async def main():
    """RBAC demonstration."""

    print("=" * 70)
    print("RBAC (Role-Based Access Control) Demonstration")
    print("=" * 70)
    print()

    # ================================================================
    # INITIALIZE SIMULATION
    # ================================================================
    print("[1/5] Initializing simulation...")

    system_state = SystemState()
    auth_mgr = AuthenticationManager()
    data_store = DataStore(system_state=system_state, auth_mgr=auth_mgr)
    await auth_mgr.set_data_store(data_store)

    # Register a test device (PLC)
    await data_store.register_device(
        device_name="test_plc",
        device_type="plc",
        device_id=100,
        protocols=["modbus"],
    )

    print("✓ Simulation initialized")
    print()

    # ================================================================
    # INITIAL STATE: RBAC DISABLED (Vulnerable)
    # ================================================================
    print("[2/5] Initial state: RBAC DISABLED (VULNERABLE)")
    print()

    print(f"RBAC Enforcement: {'ENABLED' if data_store.rbac_enabled else 'DISABLED'}")
    print()

    # Try write as viewer (should SUCCEED because RBAC disabled)
    viewer_session = await auth_mgr.authenticate("viewer1")
    viewer_user = await auth_mgr.get_session(viewer_session)

    print(
        f"Test: {viewer_user.user.username} ({viewer_user.user.role.name}) writes setpoint..."
    )

    success = await data_store.write_memory(
        device_name="test_plc",
        address="holding_registers[0]",
        value=3600,
        session_id=viewer_session,
    )

    if success:
        print("  ✓ Write SUCCEEDED - RBAC disabled, all writes allowed")
        print()
        print(">>> VULNERABILITY: Viewer with read-only role can modify PLCs!")
    else:
        print("  ❌ Write FAILED")

    print()

    # ================================================================
    # ENABLE RBAC ENFORCEMENT
    # ================================================================
    print("[3/5] Enabling RBAC enforcement...")
    print()

    # Enable RBAC (simulates editing config/rbac.yml and restarting)
    data_store.rbac_enabled = True

    print("✓ RBAC enforcement ENABLED")
    print("  • All write operations now require permissions")
    print("  • Users restricted to their role's capabilities")
    print()

    # ================================================================
    # TEST PERMISSION BOUNDARIES
    # ================================================================
    print("[4/5] Testing permission boundaries...")
    print()

    # Test 1: Viewer (should FAIL)
    print("Test 1: Viewer attempts setpoint write")
    viewer_session = await auth_mgr.authenticate("viewer1")
    success = await data_store.write_memory(
        device_name="test_plc",
        address="holding_registers[0]",
        value=3600,
        session_id=viewer_session,
    )
    result = "FAILED (Expected)" if not success else "SUCCEEDED (Unexpected)"
    print(f"  Result: {result}")
    print("  Reason: VIEWER role lacks CONTROL_SETPOINT permission")
    print()

    # Test 2: Operator (should SUCCEED)
    print("Test 2: Operator attempts setpoint write")
    operator_session = await auth_mgr.authenticate("operator1")
    success = await data_store.write_memory(
        device_name="test_plc",
        address="holding_registers[0]",
        value=3600,
        session_id=operator_session,
    )
    result = "SUCCEEDED (Expected)" if success else "FAILED (Unexpected)"
    print(f"  Result: {result}")
    print("  Reason: OPERATOR role has CONTROL_SETPOINT permission")
    print()

    # Test 3: Operator attempts PLC programming (should FAIL)
    print("Test 3: Operator attempts PLC programming")
    operator_session = await auth_mgr.authenticate("operator1")
    success = await data_store.write_memory(
        device_name="test_plc",
        address="DB1.setpoint",  # S7 PLC data block
        value=350,
        session_id=operator_session,
    )
    result = "FAILED (Expected)" if not success else "SUCCEEDED (Unexpected)"
    print(f"  Result: {result}")
    print("  Reason: OPERATOR role lacks CONFIG_PROGRAM permission")
    print()

    # Test 4: Engineer attempts PLC programming (should SUCCEED)
    print("Test 4: Engineer attempts PLC programming")
    engineer_session = await auth_mgr.authenticate("engineer1")
    success = await data_store.write_memory(
        device_name="test_plc",
        address="DB1.setpoint",
        value=350,
        session_id=engineer_session,
    )
    result = "SUCCEEDED (Expected)" if success else "FAILED (Unexpected)"
    print(f"  Result: {result}")
    print("  Reason: ENGINEER role has CONFIG_PROGRAM permission")
    print()

    # ================================================================
    # RUNTIME INCIDENT RESPONSE
    # ================================================================
    print("[5/5] Runtime incident response scenario...")
    print()

    print("Scenario: operator1 account compromised, attempting privilege escalation")
    print()

    # Attacker tries programming with operator credentials (FAILS)
    print("Action 1: Attacker attempts PLC programming with operator1 credentials")
    operator_session = await auth_mgr.authenticate("operator1")
    success = await data_store.write_memory(
        device_name="test_plc",
        address="DB1.malicious",
        value=999,
        session_id=operator_session,
    )
    print(f"  Result: {'BLOCKED by RBAC' if not success else 'SUCCEEDED (problem!)'}")
    print()

    # Blue team response: Downgrade to viewer role
    print("Action 2: Blue team downgrades operator1 to VIEWER role")
    await auth_mgr.update_user_role("operator1", UserRole.VIEWER)
    print("  ✓ Role changed: operator1 → VIEWER")
    print()

    # Attacker can no longer write setpoints
    print("Action 3: Attacker attempts setpoint write (now as VIEWER)")
    operator_session = await auth_mgr.authenticate(
        "operator1"
    )  # New session with new role
    success = await data_store.write_memory(
        device_name="test_plc",
        address="holding_registers[0]",
        value=9999,
        session_id=operator_session,
    )
    print(f"  Result: {'BLOCKED by RBAC' if not success else 'SUCCEEDED (problem!)'}")
    print("  ✓ Compromise contained - attacker neutralized")
    print()

    # ================================================================
    # SUMMARY
    # ================================================================
    print("=" * 70)
    print("RBAC Demonstration Complete!")
    print("=" * 70)
    print()

    print("Key Takeaways:")
    print("  1. RBAC disabled = VULNERABLE (any user can do anything)")
    print("  2. RBAC enabled = Users restricted to role permissions")
    print("  3. VIEWER = Read-only (cannot write)")
    print("  4. OPERATOR = Control setpoints (cannot program PLCs)")
    print("  5. ENGINEER = Program PLCs (cannot bypass safety)")
    print("  6. SUPERVISOR = Safety bypass and elevated control")
    print("  7. Runtime role changes = Immediate incident response")
    print()

    print("Next Steps:")
    print("  • Enable RBAC in config/rbac.yml (enforcement_enabled: true)")
    print("  • Configure address permission mappings")
    print("  • Test attack scripts with different user roles")
    print("  • Use Blue Team CLI for runtime incident response:")
    print("    python tools/blue_team.py rbac list-users")
    print(
        "    python tools/blue_team.py rbac change-role --username operator1 --role VIEWER"
    )
    print()


if __name__ == "__main__":
    asyncio.run(main())
