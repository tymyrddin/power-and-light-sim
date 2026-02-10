#!/usr/bin/env python3
"""
Example: Dual Authorisation (Two-Person Rule) Demonstration

Shows how dual authorisation protects safety-critical operations.
Demonstrates the two-person rule for safety bypass operations.

Workshop Flow:
1. Single-user attempt: DENIED (requires two users)
2. Two users, both operators: DENIED (insufficient privileges)
3. Two users, both supervisors: GRANTED (two-person rule satisfied)
4. Same user twice: DENIED (must be different users)
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from components.security.authentication import (
    AuthenticationManager,
    PermissionType,
)
from components.state.data_store import DataStore
from components.state.system_state import SystemState


async def main():
    """Dual authorisation demonstration."""

    print("=" * 70)
    print("Dual Authorisation (Two-Person Rule) Demonstration")
    print("=" * 70)
    print()

    # ================================================================
    # INITIALISE SIMULATION
    # ================================================================
    print("[1/6] Initialising authentication system...")

    system_state = SystemState()
    auth_mgr = AuthenticationManager()
    data_store = DataStore(system_state=system_state, auth_mgr=auth_mgr)
    await auth_mgr.set_data_store(data_store)

    print("✓ Authentication system initialised")
    print()

    # ================================================================
    # DISPLAY USERS AND PERMISSIONS
    # ================================================================
    print("[2/6] Available users and their permissions:")
    print()

    for username, user in auth_mgr.users.items():
        role = user.role.value
        bypass_perm = "✓" if PermissionType.SAFETY_BYPASS in user.permissions else "✗"
        print(f"  {username:15s} ({role:10s}) - SAFETY_BYPASS: {bypass_perm}")

    print()
    print("Key: operator = no bypass, supervisor/admin = can bypass")
    print()

    # ================================================================
    # SCENARIO 1: Single User Attempt (Should FAIL)
    # ================================================================
    print("[3/6] Scenario 1: Single supervisor attempts safety bypass (should FAIL)")
    print()

    # Login supervisor1
    session1 = await auth_mgr.authenticate("supervisor1", "super123")
    print(f"  Logged in: supervisor1 (session: {session1[:8]}...)")
    print()

    # Try to bypass with single authorization - won't work with dual auth
    print("  Attempting safety bypass with single authorisation...")
    # NOTE: We're calling authorize_with_dual_auth with same session twice to demonstrate failure
    authorized = await auth_mgr.authorize_with_dual_auth(
        session1,
        session1,  # Same session - will fail
        PermissionType.SAFETY_BYPASS,
        resource="reactor_safety_plc_1",
        reason="Test single user attempt",
    )

    if authorized:
        print("  ❌ UNEXPECTED: Bypass granted with single user!")
    else:
        print("  ✓ DENIED: Two-person rule requires two different users")

    print()

    # ================================================================
    # SCENARIO 2: Two Operators (Should FAIL - Insufficient Privileges)
    # ================================================================
    print(
        "[4/6] Scenario 2: Two operators attempt bypass (should FAIL - insufficient privileges)"
    )
    print()

    # Login two operators
    session_op1 = await auth_mgr.authenticate("operator1", "pass123")
    session_op2 = await auth_mgr.authenticate("operator2", "pass123")

    print(f"  Logged in: operator1 (session: {session_op1[:8]}...)")
    print(f"  Logged in: operator2 (session: {session_op2[:8]}...)")
    print()

    print("  Attempting safety bypass with two operators...")
    authorized = await auth_mgr.authorize_with_dual_auth(
        session_op1,
        session_op2,
        PermissionType.SAFETY_BYPASS,
        resource="reactor_safety_plc_1",
        reason="Two operators test",
    )

    if authorized:
        print("  ❌ UNEXPECTED: Bypass granted to operators!")
    else:
        print("  ✓ DENIED: Operators lack SAFETY_BYPASS permission (need supervisor)")

    print()

    # ================================================================
    # SCENARIO 3: Two Supervisors (Should SUCCEED)
    # ================================================================
    print(
        "[5/6] Scenario 3: Two supervisors attempt bypass (should SUCCEED - two-person rule)"
    )
    print()

    # Login second supervisor
    session2 = await auth_mgr.authenticate("supervisor2", "super123")

    print(f"  Logged in: supervisor1 (session: {session1[:8]}...)")
    print(f"  Logged in: supervisor2 (session: {session2[:8]}...)")
    print()

    print("  Attempting safety bypass with two different supervisors...")
    authorized = await auth_mgr.authorize_with_dual_auth(
        session1,
        session2,
        PermissionType.SAFETY_BYPASS,
        resource="reactor_safety_plc_1",
        reason="Maintenance - planned safety system bypass",
    )

    if authorized:
        print("  ✓ GRANTED: Two-person rule satisfied")
        print("  • Both users have SAFETY_BYPASS permission")
        print("  • Both users are different people")
        print("  • Both sessions are active and valid")
        print()
        print("  Safety bypass is now ACTIVE on reactor_safety_plc_1")
    else:
        print("  ❌ UNEXPECTED: Bypass denied with two supervisors!")

    print()

    # ================================================================
    # SCENARIO 4: Mixed Roles (Supervisor + Admin)
    # ================================================================
    print(
        "[6/6] Scenario 4: Supervisor + Admin attempt bypass (should SUCCEED - role separation)"
    )
    print()

    # Login admin
    session_admin = await auth_mgr.authenticate("admin", "admin123")

    print(f"  Logged in: supervisor1 (session: {session1[:8]}...)")
    print(f"  Logged in: admin (session: {session_admin[:8]}...)")
    print()

    print("  Attempting safety bypass with supervisor + admin (role separation)...")
    authorized = await auth_mgr.authorize_with_dual_auth(
        session1,
        session_admin,
        PermissionType.SAFETY_BYPASS,
        resource="turbine_safety_plc_1",
        reason="Emergency maintenance - turbine safety bypass",
    )

    if authorized:
        print("  ✓ GRANTED: Role separation satisfied")
        print("  • supervisor1: has SAFETY_BYPASS")
        print("  • admin: has all permissions")
        print("  • Different users with different roles")
    else:
        print("  ❌ UNEXPECTED: Bypass denied with different roles!")

    print()

    # ================================================================
    # CLEANUP
    # ================================================================
    await auth_mgr.logout(session1)
    await auth_mgr.logout(session2)
    await auth_mgr.logout(session_op1)
    await auth_mgr.logout(session_op2)
    await auth_mgr.logout(session_admin)

    # ================================================================
    # SUMMARY
    # ================================================================
    print("=" * 70)
    print("Dual Authorisation Demo Complete!")
    print("=" * 70)
    print()

    print("Key Learnings:")
    print("  1. Two-person rule prevents single insider from bypassing safety")
    print("  2. Both users must have the required permission")
    print("  3. Must be two different users (can't authorise with yourself)")
    print("  4. Role separation adds another layer (supervisor + admin)")
    print("  5. All dual auth attempts are logged to audit trail")
    print()

    print("Trade-offs:")
    print("  • Security: Prevents single-person abuse ✓")
    print("  • Usability: Requires two people (slower) ✗")
    print("  • Emergencies: Delays critical actions ✗")
    print("  • Collusion: Two insiders can still collude ✗")
    print()

    print("Real-World Considerations:")
    print("  • What if only one supervisor on shift?")
    print("  • Emergency override procedures?")
    print("  • How to detect collusion patterns?")
    print("  • Video recording of critical operations?")
    print()

    print("Testing with Blue Team CLI:")
    print("  python tools/blue_team.py rbac list-sessions")
    print("  python tools/blue_team.py rbac list-users")
    print("  python tools/blue_team.py audit query --category security")
    print()


if __name__ == "__main__":
    asyncio.run(main())
