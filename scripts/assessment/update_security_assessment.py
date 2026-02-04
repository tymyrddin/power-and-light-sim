#!/usr/bin/env python3
"""
Software Update Security Assessment
Demonstrates vulnerabilities in vendor update mechanisms
"""

import hashlib
import hmac
import json
from datetime import datetime
from pathlib import Path
from typing import Any

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    "demo_mode": True,  # Create demo files for testing
    "vendors": {
        "scada_vendor": {
            "name": "SCADA Systems Inc",
            "update_method": "Website download with MD5",
            "security_level": "WEAK",
        },
        "plc_vendor": {
            "name": "Industrial Controls Corp",
            "update_method": "Vendor remote access",
            "security_level": "POOR",
        },
        "turbine_vendor": {
            "name": "TurbineTech",
            "update_method": "Automatic push",
            "security_level": "CRITICAL",
        },
    },
}


# ============================================================================
# DEMO UPDATE FILE CREATION
# ============================================================================


def create_demo_update_file(
    filename: str, content: str = "LEGITIMATE"
) -> tuple[bytes, str, str, str]:
    """
    Create a demo update file with various hashes

    Returns:
        Tuple of (file_data, md5, sha1, sha256)
    """
    file_data = (
        f"UPDATE_FILE_{content}_VERSION_3.2.1_{datetime.now().isoformat()}".encode()
    )

    md5_hash = hashlib.md5(file_data).hexdigest()
    sha1_hash = hashlib.sha1(file_data).hexdigest()
    sha256_hash = hashlib.sha256(file_data).hexdigest()

    with open(filename, "wb") as f:
        f.write(file_data)

    return file_data, md5_hash, sha1_hash, sha256_hash


def demonstrate_md5_collision() -> None:
    """
    Demonstrate why MD5 is insecure (conceptually)
    """
    print("\n" + "=" * 70)
    print("[*] DEMONSTRATION: Why MD5 is Insecure")
    print("=" * 70)

    print("\n[*] MD5 collision attacks allow creating two different files")
    print("    with the SAME MD5 hash")
    print("\n[*] Example scenario:")
    print("    1. Attacker gets legitimate update file")
    print("    2. Creates malicious update with SAME MD5 hash")
    print("    3. Compromises vendor website")
    print("    4. Replaces legitimate file with malicious one")
    print("    5. MD5 verification PASSES despite malicious content")

    print("\n[!] This is NOT theoretical - MD5 collisions exist:")
    print("    • First collision: 2004 (Wang et al.)")
    print("    • Practical attacks: 2008 onwards")
    print("    • Tools publicly available")

    print("\n[*] Creating two different 'updates' with similar MD5 prefixes...")

    # Create two different files
    legitimate = b"LEGITIMATE_UPDATE_VERSION_3.2.1_SAFE"
    malicious = b"MALICIOUS_UPDATE_VERSION_3.2.1_PWNED"

    md5_legit = hashlib.md5(legitimate).hexdigest()
    md5_malicious = hashlib.md5(malicious).hexdigest()

    print(f"    Legitimate MD5:  {md5_legit}")
    print(f"    Malicious MD5:   {md5_malicious}")
    print(f"    Match: {md5_legit == md5_malicious}")

    print("\n[!] Note: While these specific files don't collide,")
    print("    attackers CAN create colliding files with tools like:")
    print("    • HashClash")
    print("    • FastColl")
    print("    • UniColl")


# ============================================================================
# UPDATE VERIFICATION TESTS
# ============================================================================


def test_no_verification() -> dict[str, Any]:
    """Test scenario: No verification at all (worst case)"""

    print("\n" + "=" * 70)
    print("[*] TEST 1: No Verification (Turbine Vendor)")
    print("=" * 70)

    print("\n[*] Scenario: Automatic updates with no verification")
    print("[*] Vendor pushes updates directly to production PLCs")
    print("[*] No hash, no signature, no approval process")

    results = {
        "test": "no_verification",
        "vendor": "TurbineTech",
        "security_level": "CRITICAL",
        "vulnerabilities": [],
    }

    print("\n[!] VULNERABILITIES:")

    vulns = [
        "Compromised vendor server → Malicious updates to all customers",
        "Rogue employee at vendor → Deploy malicious code",
        "Man-in-the-middle attack → Inject malicious update in transit",
        "No audit trail → Cannot detect unauthorized changes",
        "No rollback capability → Cannot recover from bad update",
    ]

    for i, vuln in enumerate(vulns, 1):
        print(f"    {i}. {vuln}")
        results["vulnerabilities"].append(vuln)

    print("\n[!] RISK: CRITICAL - Complete lack of update security")
    results["risk"] = "CRITICAL"

    return results


def test_md5_verification() -> dict[str, Any]:
    """Test scenario: MD5 hash verification"""

    print("\n" + "=" * 70)
    print("[*] TEST 2: MD5 Hash Verification (SCADA Vendor)")
    print("=" * 70)

    results = {
        "test": "md5_verification",
        "vendor": "SCADA Systems Inc",
        "security_level": "WEAK",
        "vulnerabilities": [],
    }

    # Create demo files
    print("\n[*] Creating demo update files...")
    legit_data, legit_md5, legit_sha1, legit_sha256 = create_demo_update_file(
        "scada_update_legitimate.bin", "LEGITIMATE"
    )

    print("[*] Legitimate update created")
    print(f"    MD5:    {legit_md5}")
    print(f"    SHA256: {legit_sha256}")

    # Simulate download
    print("\n[*] Simulating update download...")
    print("[*] Calculating MD5 hash of downloaded file...")

    calc_md5 = hashlib.md5(legit_data).hexdigest()

    print(f"    Published MD5:   {legit_md5}")
    print(f"    Calculated MD5:  {calc_md5}")

    if calc_md5 == legit_md5:
        print("[✓] MD5 verification PASSED")

    print("\n[!] But MD5 is cryptographically broken:")

    vulns = [
        "MD5 collisions can be generated (same hash, different content)",
        "If website is compromised, attacker can replace both file AND hash",
        "No authentication - cannot verify file came from vendor",
        "Collision attacks demonstrated since 2004",
        "NIST deprecated MD5 in 2011",
    ]

    for i, vuln in enumerate(vulns, 1):
        print(f"    {i}. {vuln}")
        results["vulnerabilities"].append(vuln)

    print("\n[!] RISK: WEAK - Better than nothing, but not secure")
    results["risk"] = "WEAK"

    return results


def test_sha256_verification() -> dict[str, Any]:
    """Test scenario: SHA-256 hash verification"""

    print("\n" + "=" * 70)
    print("[*] TEST 3: SHA-256 Hash Verification")
    print("=" * 70)

    results = {
        "test": "sha256_verification",
        "security_level": "MODERATE",
        "vulnerabilities": [],
    }

    # Create demo file
    print("\n[*] Creating demo update file...")
    legit_data, legit_md5, legit_sha1, legit_sha256 = create_demo_update_file(
        "update_sha256.bin", "LEGITIMATE"
    )

    print("[*] Update created")
    print(f"    SHA-256: {legit_sha256}")

    # Verify integrity
    print("\n[*] Verifying update integrity...")
    calc_sha256 = hashlib.sha256(legit_data).hexdigest()

    if calc_sha256 == legit_sha256:
        print("[✓] SHA-256 verification PASSED")
        print("[✓] File integrity confirmed")

    print("\n[*] SHA-256 is much stronger than MD5:")
    print("    • No known collision attacks")
    print("    • 256-bit hash space (vs 128-bit for MD5)")
    print("    • Computationally infeasible to find collisions")

    print("\n[!] However, still has limitations:")

    vulns = [
        "If website is compromised, attacker can replace file AND hash",
        "No authentication - cannot verify file came from legitimate vendor",
        "No protection against compromised vendor infrastructure",
        "Requires secure channel to obtain hash",
    ]

    for i, vuln in enumerate(vulns, 1):
        print(f"    {i}. {vuln}")
        results["vulnerabilities"].append(vuln)

    print("\n[*] RISK: MODERATE - Good integrity, but no authentication")
    results["risk"] = "MODERATE"

    return results


def test_cryptographic_signature() -> dict[str, Any]:
    """Test scenario: Cryptographic signature verification"""

    print("\n" + "=" * 70)
    print("[*] TEST 4: Cryptographic Signature Verification (BEST)")
    print("=" * 70)

    results = {
        "test": "signature_verification",
        "security_level": "STRONG",
        "vulnerabilities": [],
    }

    print("\n[*] Cryptographic signatures provide:")
    print("    • Integrity: Detects any modification")
    print("    • Authentication: Proves file came from vendor")
    print("    • Non-repudiation: Vendor cannot deny creating file")

    # Create demo file
    print("\n[*] Creating demo signed update...")
    update_data, _, _, sha256 = create_demo_update_file(
        "update_signed.bin", "LEGITIMATE"
    )

    # Simulate signature (in reality, vendor signs with private key)
    vendor_private_key = b"VENDOR_PRIVATE_KEY_SECRET"
    signature = hmac.new(vendor_private_key, update_data, hashlib.sha256).hexdigest()

    print(f"[*] Update SHA-256: {sha256}")
    print(f"[*] Signature: {signature[:32]}...")

    # Verify signature (customers verify with vendor's public key)
    print("\n[*] Verifying signature with vendor's public key...")
    vendor_public_key = b"VENDOR_PRIVATE_KEY_SECRET"  # In reality, public key
    calc_signature = hmac.new(
        vendor_public_key, update_data, hashlib.sha256
    ).hexdigest()

    if calc_signature == signature:
        print("[✓] Signature verification PASSED")
        print("[✓] Update authenticity confirmed")
        print("[✓] File came from legitimate vendor")

    print("\n[*] Why this is secure:")
    print("    • Attacker cannot forge signature without private key")
    print("    • Even if website is compromised, cannot create valid signature")
    print("    • Public key can be distributed via multiple channels")

    print("\n[!] Remaining risks (minimal):")

    vulns = [
        "Vendor private key compromise (very rare, high-value target)",
        "Weak key management at vendor",
        "Incorrect public key distribution (MITM during initial setup)",
    ]

    for i, vuln in enumerate(vulns, 1):
        print(f"    {i}. {vuln}")
        results["vulnerabilities"].append(vuln)

    print("\n[✓] RISK: LOW - Best practice for software updates")
    results["risk"] = "LOW"

    return results


# ============================================================================
# ATTACK SCENARIOS
# ============================================================================


def demonstrate_website_compromise_attack() -> None:
    """Demonstrate attack via compromised vendor website"""

    print("\n" + "=" * 70)
    print("[*] ATTACK SCENARIO: Compromised Vendor Website")
    print("=" * 70)

    print("\n[*] Attack flow:")
    print("    1. Attacker compromises vendor website (phishing, SQLi, etc.)")
    print("    2. Replaces legitimate update with malicious version")
    print("    3. If only MD5 used: Replaces MD5 hash too")
    print("    4. Customer downloads 'verified' malicious update")
    print("    5. Malicious code deployed to production ICS")

    print("\n[*] Creating scenario...")

    # Legitimate update
    legit_data = b"LEGITIMATE_UPDATE_V3.2.1"
    legit_md5 = hashlib.md5(legit_data).hexdigest()

    print("\n[*] Original legitimate update:")
    print(f"    Content: {legit_data.decode()}")
    print(f"    MD5: {legit_md5}")

    # Attacker replaces it
    malicious_data = b"MALICIOUS_BACKDOOR_V3.2.1"
    malicious_md5 = hashlib.md5(malicious_data).hexdigest()

    print("\n[!] Attacker replaces with malicious update:")
    print(f"    Content: {malicious_data.decode()}")
    print(f"    MD5: {malicious_md5}")
    print("    (Attacker also updates MD5 on website)")

    print("\n[*] Customer downloads and verifies:")
    print(f"    Downloaded MD5: {malicious_md5}")
    print(f"    Website MD5: {malicious_md5}")
    print("    Verification: PASSES ✓")

    print("\n[!] Result: Malicious update installed despite 'verification'")

    print("\n[*] Defense: Cryptographic signatures")
    print("    • Attacker cannot forge signature without vendor's private key")
    print("    • Website compromise alone is insufficient")
    print("    • Customer verification would FAIL")


# ============================================================================
# MAIN ASSESSMENT
# ============================================================================


def assess_update_security() -> dict[str, Any]:
    """
    Main assessment function
    """
    assessment_start = datetime.now()

    print("=" * 70)
    print("[*] SOFTWARE UPDATE SECURITY ASSESSMENT")
    print("=" * 70)
    print(f"[*] Assessment start: {assessment_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print("\n[*] This assessment tests vendor update mechanisms")
    print("[*] Identifies vulnerabilities in update delivery and verification")

    results: dict[str, Any] = {
        "assessment_start": assessment_start.isoformat(),
        "tests": {},
        "summary": {},
    }

    # Run all tests
    results["tests"]["no_verification"] = test_no_verification()
    results["tests"]["md5_verification"] = test_md5_verification()
    results["tests"]["sha256_verification"] = test_sha256_verification()
    results["tests"]["signature_verification"] = test_cryptographic_signature()

    # Demonstrate why MD5 is broken
    demonstrate_md5_collision()

    # Show attack scenario
    demonstrate_website_compromise_attack()

    # Generate summary
    print("\n" + "=" * 70)
    print("[*] ASSESSMENT SUMMARY")
    print("=" * 70)

    print("\n[*] Vendor Update Security Levels:")
    for _vendor, details in CONFIG["vendors"].items():
        print(f"\n    {details['name']}:")
        print(f"      Method: {details['update_method']}")
        print(f"      Security: {details['security_level']}")

    print("\n[*] RECOMMENDATIONS:")
    recommendations = [
        "Require cryptographic signatures for all updates",
        "Use SHA-256 minimum for hashes (never MD5 or SHA-1)",
        "Implement air-gapped update verification process",
        "Test all updates in non-production environment first",
        "Require multi-party approval for production updates",
        "Maintain update audit log with cryptographic evidence",
        "Disable automatic updates - require explicit approval",
        "Establish trusted public key distribution mechanism",
        "Monitor for unauthorized update attempts",
        "Implement rollback capability for failed updates",
    ]

    for i, rec in enumerate(recommendations, 1):
        print(f"    {i}. {rec}")

    results["recommendations"] = recommendations

    # Save report
    assessment_end = datetime.now()
    results["assessment_end"] = assessment_end.isoformat()
    results["duration_seconds"] = (assessment_end - assessment_start).total_seconds()

    # Ensure reports directory exists
    reports_dir = Path(__file__).parent.parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    report_file = (
        reports_dir
        / f'update_security_assessment_{assessment_start.strftime("%Y%m%d_%H%M%S")}.json'
    )
    try:
        with open(report_file, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\n[*] Detailed report saved: {report_file}")
    except OSError as e:
        print(f"\n[!] Could not save report: {e}")

    # Cleanup demo files
    print("\n[*] Cleaning up demo files...")
    for filename in [
        "scada_update_legitimate.bin",
        "update_sha256.bin",
        "update_signed.bin",
    ]:
        try:
            Path(filename).unlink()
        except FileNotFoundError:
            pass

    print("\n" + "=" * 70)

    return results


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("\n[*] Software Update Security Assessment Tool")
    print("[*] Tests vendor update verification mechanisms")
    print("[*] Demonstrates why weak verification is dangerous\n")

    response = input("Run assessment? (yes/no): ")
    if response.lower() in ["yes", "y"]:
        assess_update_security()
    else:
        print("[*] Assessment cancelled")
