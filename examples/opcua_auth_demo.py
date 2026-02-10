#!/usr/bin/env python3
"""
OPC UA Authentication Demo (Challenge 1: Password Protect the SCADA)

Demonstrates the OPCUAUserManager bridging asyncua to AuthenticationManager.
Tests user validation, role mapping, and rejection scenarios WITHOUT
starting an actual OPC UA server (avoids port conflicts).

Usage:
    python examples/opcua_auth_demo.py

This demo shows:
1. Valid user authentication with role mapping
2. Anonymous connection rejection
3. Unknown user rejection
4. Locked account rejection
5. Authentication statistics
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from components.security.authentication import AuthenticationManager
from components.security.opcua_user_manager import OPCUAUserManager


def main():
    print("=" * 70)
    print("OPC UA Authentication Demo")
    print("Challenge 1: Password Protect the SCADA")
    print("=" * 70)
    print()

    # Create AuthenticationManager with default users
    auth_mgr = AuthenticationManager()
    print(f"AuthenticationManager initialised with {len(auth_mgr.users)} users:")
    for username, user in auth_mgr.users.items():
        print(f"  {username:<16} {user.role.name:<12} {user.full_name}")
    print()

    # Create OPCUAUserManager wrapping the auth manager
    user_mgr = OPCUAUserManager(auth_mgr)
    print("OPCUAUserManager created (bridges asyncua to RBAC user database)")
    print()

    # Scenario 1: Valid users authenticate successfully
    print("-" * 70)
    print("Scenario 1: Valid User Authentication")
    print("-" * 70)
    print()

    test_users = ["operator1", "engineer1", "supervisor1", "admin", "viewer1"]
    for username in test_users:
        result = user_mgr.get_user(
            iserver=None, username=username, password="simulated"
        )
        if result:
            print(
                f"  {username:<16} -> OPC UA role: {result.name} (role={result.role.name})"
            )
        else:
            print(f"  {username:<16} -> REJECTED")
    print()

    # Scenario 2: Anonymous connection rejected
    print("-" * 70)
    print("Scenario 2: Anonymous Connection (no username)")
    print("-" * 70)
    print()

    result = user_mgr.get_user(iserver=None, username=None, password=None)
    print(f"  Anonymous -> {'ACCEPTED' if result else 'REJECTED (correct)'}")
    print()

    # Scenario 3: Unknown user rejected
    print("-" * 70)
    print("Scenario 3: Unknown User")
    print("-" * 70)
    print()

    result = user_mgr.get_user(
        iserver=None, username="attacker", password="password123"
    )
    print(f"  attacker -> {'ACCEPTED' if result else 'REJECTED (correct)'}")
    print()

    # Scenario 4: Locked account rejected
    print("-" * 70)
    print("Scenario 4: Locked Account")
    print("-" * 70)
    print()

    # Lock an account
    auth_mgr.users["operator1"].active = False
    result = user_mgr.get_user(iserver=None, username="operator1", password="simulated")
    print(f"  operator1 (locked) -> {'ACCEPTED' if result else 'REJECTED (correct)'}")
    # Unlock it again
    auth_mgr.users["operator1"].active = True
    print()

    # Statistics
    print("-" * 70)
    print("Authentication Statistics")
    print("-" * 70)
    print()

    stats = user_mgr.get_statistics()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    print()

    # Role mapping explanation
    print("-" * 70)
    print("Role Mapping: Simulator -> OPC UA")
    print("-" * 70)
    print()
    print("  ADMIN, SUPERVISOR  -> Admin  (full OPC UA access)")
    print("  ENGINEER, OPERATOR -> User   (standard read/write/browse)")
    print("  VIEWER             -> User   (standard access)")
    print()
    print("  asyncua has limited roles (Admin, Anonymous, User).")
    print("  Fine-grained permissions are handled by RBAC (Challenge 2)")
    print("  at the DataStore level, not the OPC UA protocol level.")
    print()

    # Defence in depth summary
    print("=" * 70)
    print("Defence in Depth: How Challenges Work Together")
    print("=" * 70)
    print()
    print("  Challenge 1 (Authentication): Controls WHO can connect to OPC UA")
    print("  Challenge 2 (RBAC):           Controls WHAT they can do once connected")
    print("  Challenge 7 (Encryption):     Protects DATA in transit (TLS)")
    print()
    print("  Without authentication: anyone can connect and read/write values")
    print("  Without RBAC: authenticated users have unrestricted access")
    print("  Without encryption: credentials and data visible on the network")
    print()
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
