#!/usr/bin/env python3
"""
OPC UA Security Demo - Certificate Generation and Validation

Demonstrates the OPC UA certificate management workflow without
starting actual OPC UA servers (avoids port conflicts).

Usage:
    python examples/opcua_security_demo.py

Covers:
1. Viewing current OPC UA security configuration
2. Generating certificates for OPC UA servers
3. Validating generated certificates
4. Checking enforcement status
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from components.security.encryption import (
    CertificateInfo,
    CertificateManager,
    OPCUASecurityPolicy,
    SecurityLevel,
)
from config.config_loader import ConfigLoader


async def main():
    """Run OPC UA security demonstration."""

    print("=" * 70)
    print("OPC UA Security Demonstration")
    print("Challenge 7: Encrypt SCADA Communications")
    print("=" * 70)
    print()

    # ================================================================
    # Step 1: View current configuration
    # ================================================================
    print("Step 1: Current OPC UA Security Configuration")
    print("-" * 50)
    print()

    config = ConfigLoader().load_all()
    opcua_sec = config.get("opcua_security", {})

    enforcement = opcua_sec.get("enforcement_enabled", False)
    policy = opcua_sec.get("security_policy", "None")
    cert_dir = opcua_sec.get("cert_dir", "certs")
    key_size = opcua_sec.get("key_size", 2048)
    validity_hours = opcua_sec.get("validity_hours", 8760)

    print(f"  Enforcement: {'ENABLED' if enforcement else 'DISABLED (vulnerable)'}")
    print(f"  Security Policy: {policy}")
    print(f"  Certificate Dir: {cert_dir}")
    print(f"  Key Size: {key_size} bits")
    print(f"  Validity: {validity_hours} hours ({validity_hours / 24:.0f} days)")
    print()

    # Discover OPC UA servers
    servers = []
    for device in config.get("devices", []):
        protocols = device.get("protocols", {})
        if "opcua" in protocols:
            servers.append(
                {
                    "name": device["name"],
                    "description": device.get("description", ""),
                    "opcua": protocols["opcua"],
                }
            )

    print(f"  OPC UA Servers Found: {len(servers)}")
    for srv in servers:
        opcua_cfg = srv["opcua"]
        srv_policy = opcua_cfg.get("security_policy", "None")
        port = opcua_cfg.get("port", "?")
        anon = opcua_cfg.get("allow_anonymous", True)
        print(f"    {srv['name']}:")
        print(f"      Port: {port}")
        print(f"      Policy: {srv_policy}")
        print(f"      Anonymous: {anon}")
    print()

    # ================================================================
    # Step 2: Available security policies
    # ================================================================
    print("Step 2: Available OPC UA Security Policies")
    print("-" * 50)
    print()

    for sp in OPCUASecurityPolicy:
        recommended = (
            " (RECOMMENDED)" if sp == OPCUASecurityPolicy.AES256_SHA256_RSAPSS else ""
        )
        deprecated = (
            " (DEPRECATED)" if sp.value in ("Basic128Rsa15", "Basic256") else ""
        )
        print(f"  {sp.value:<30}{recommended}{deprecated}")

    print()
    print("  Security Levels (IEC 62443):")
    for sl in SecurityLevel:
        print(f"    Level {sl.value}: {sl.name}")
    print()

    # ================================================================
    # Step 3: Generate certificates
    # ================================================================
    print("Step 3: Certificate Generation")
    print("-" * 50)
    print()

    # Use a demo directory to avoid overwriting real certs
    demo_cert_dir = Path("certs/demo")
    demo_cert_dir.mkdir(parents=True, exist_ok=True)

    cert_manager = CertificateManager(data_store=None, cert_dir=demo_cert_dir)

    # Generate a demo certificate
    demo_name = "demo_scada_server"
    print(f"  Generating certificate for: {demo_name}")

    cert, private_key = cert_manager.generate_self_signed_cert(
        common_name=demo_name,
        organization="Unseen University Power & Light Co.",
        validity_hours=validity_hours,
        key_size=key_size,
    )

    # Save to files
    cert_manager.save_certificate(cert, private_key, demo_name)

    cert_info = CertificateInfo.from_x509(cert)
    print(f"  Subject: {cert_info.subject}")
    print(f"  Issuer: {cert_info.issuer}")
    print(f"  Valid From: {cert_info.not_valid_before}")
    print(f"  Valid Until: {cert_info.not_valid_after}")
    print(f"  Key Algorithm: {cert_info.public_key_algorithm}")
    print(f"  Signature Algorithm: {cert_info.signature_algorithm}")
    print(f"  SHA-256 Fingerprint: {cert_info.fingerprint_sha256[:32]}...")
    print()

    # ================================================================
    # Step 4: Validate certificate
    # ================================================================
    print("Step 4: Certificate Validation")
    print("-" * 50)
    print()

    is_valid = cert_manager.validate_certificate(cert)
    print(f"  Certificate valid: {is_valid}")

    # Load it back from file
    loaded = cert_manager.load_certificate(demo_name)
    if loaded:
        loaded_cert, loaded_key = loaded
        loaded_info = CertificateInfo.from_x509(loaded_cert)
        print("  Loaded from file: OK")
        print(
            f"  Fingerprint matches: {loaded_info.fingerprint_sha256 == cert_info.fingerprint_sha256}"
        )
    else:
        print("  Failed to load certificate from file")
    print()

    # ================================================================
    # Step 5: Summary
    # ================================================================
    print("Step 5: Workshop Workflow Summary")
    print("-" * 50)
    print()
    print("  1. Attack: Probe insecure OPC UA (anonymous, cleartext)")
    print("     python tools/blue_team.py opcua status")
    print()
    print("  2. Defend: Generate certificates")
    print("     python tools/blue_team.py opcua generate-certs")
    print()
    print("  3. Defend: Enable enforcement (edit config, RESTART required)")
    print("     config/opcua_security.yml: enforcement_enabled: true")
    print("     python tools/simulator_manager.py")
    print()
    print("  4. Verify: Attack should now fail")
    print("     python tools/blue_team.py opcua status")
    print()

    # Cleanup demo certs
    import shutil

    shutil.rmtree(demo_cert_dir, ignore_errors=True)

    print("=" * 70)
    print("Demo complete. Demo certificates cleaned up.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
