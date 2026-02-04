#!/usr/bin/env python3
"""
Safety PLC Configuration Analysis (offline only)
Reviews exported PLC project for security issues
"""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================================
# CONFIGURATION
# ============================================================================

CONFIG = {
    "file_formats": {
        "allen_bradley": [".L5K", ".ACD"],
        "siemens": [".zip", ".zap16"],
        "schneider": [".xef"],
        "generic": [".xml", ".txt"],
    },
    "checks": {
        "weak_passwords": True,
        "hard_coded_values": True,
        "undocumented_functions": True,
        "remote_access": True,
        "bypass_logic": True,
        "safety_limits": True,
    },
}


# ============================================================================
# SECURITY FINDING CLASSES
# ============================================================================


class Finding:
    """Represents a security finding"""

    def __init__(
        self,
        category: str,
        location: str,
        issue: str,
        impact: str,
        severity: str = "MEDIUM",
        value: str | None = None,
    ):
        self.category = category
        self.location = location
        self.issue = issue
        self.impact = impact
        self.severity = severity
        self.value = value

    def to_dict(self) -> dict[str, str]:
        """Convert finding to dictionary"""
        result = {
            "category": self.category,
            "location": self.location,
            "issue": self.issue,
            "impact": self.impact,
            "severity": self.severity,
        }
        if self.value:
            result["value"] = self.value
        return result


# ============================================================================
# FILE PARSING FUNCTIONS
# ============================================================================


def detect_file_format(filepath: Path) -> str | None:
    """
    Detect PLC project file format

    Args:
        filepath: Path to project file

    Returns:
        Vendor name or None if unknown
    """
    suffix = filepath.suffix.upper()

    for vendor, formats in CONFIG["file_formats"].items():
        if suffix in formats:
            return vendor

    return None


def parse_l5k_file(filepath: Path) -> dict[str, Any]:
    """
    Parse Allen-Bradley L5K (RSLogix 5000) file

    Args:
        filepath: Path to L5K file

    Returns:
        Dictionary with parsed content
    """
    print("[*] Parsing Allen-Bradley L5K file...")

    parsed: dict[str, Any] = {
        "format": "L5K",
        "vendor": "Allen-Bradley",
        "project_name": "Unknown",
        "rungs": [],
        "tags": [],
        "raw_content": "",
    }

    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            content = f.read()
            parsed["raw_content"] = content

            # Extract project name
            project_match = re.search(r"PROJECT\s+(\S+)", content)
            if project_match:
                parsed["project_name"] = project_match.group(1)

            # Count rungs (simplified - real parsing is more complex)
            rungs = re.findall(r"RUNG\s+(\d+)", content)
            parsed["rungs"] = [int(r) for r in rungs]

            # Extract tags (simplified)
            tags = re.findall(r"TAG\s+(\S+)", content)
            parsed["tags"] = tags

            print(f"    Project: {parsed['project_name']}")
            print(f"    Rungs found: {len(parsed['rungs'])}")
            print(f"    Tags found: {len(parsed['tags'])}")

    except FileNotFoundError:
        print(f"    [!] File not found: {filepath}")
    except PermissionError:
        print(f"    [!] Permission denied: {filepath}")
    except UnicodeDecodeError:
        print("    [!] File encoding error (binary file?)")
    except Exception as e:
        print(f"    [!] Error parsing file: {e}")

    return parsed


def create_demo_file(filepath: Path) -> bool:
    """
    Create a demo PLC project file for testing

    Args:
        filepath: Path where demo file should be created

    Returns:
        True if successful
    """
    print(f"[*] Creating demo file: {filepath}")

    demo_content = """PROJECT SafetyPLC_Turbine

CONTROLLER SafetyPLC
    PASSWORD "1234"
    REVISION 32.01

TAG SpeedSetpoint DINT
TAG HighPressureLimit DINT 150
TAG EmergencyStop BOOL
TAG DiagnosticMode BOOL

PROGRAM MainProgram
    RUNG 1
        ; Speed monitoring
        ; Compare actual speed to setpoint

    RUNG 45
        ; High pressure trip
        ; Hard-coded limit: 150 PSI
        CMP HighPressureLimit > 150 THEN SET EmergencyStop

    RUNG 127
        ; Emergency shutdown logic
        ; Multiple safety checks

    RUNG 347
        ; Unlabeled section - purpose unclear
        ; Added 2023-05-15 by unknown
        ; No documentation

    RUNG 500
        ; Remote access enable
        ; RemoteAccess = TRUE allows external control

END_PROGRAM

NETWORK_CONFIG
    IP_ADDRESS 192.168.10.50
    REMOTE_ACCESS ENABLED
    AUTHENTICATION BASIC

END_PROJECT
"""

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(demo_content)
        print("    [✓] Demo file created")
        return True
    except OSError as e:
        print(f"    [!] Failed to create demo file: {e}")
        return False


# ============================================================================
# SECURITY ANALYSIS FUNCTIONS
# ============================================================================


def check_weak_passwords(content: str) -> list[Finding]:
    """Check for weak passwords in configuration"""
    findings: list[Finding] = []

    weak_patterns = [
        (r'PASSWORD\s+"(\d{4})"', "Numeric password only"),
        (r'PASSWORD\s+"(password|admin|1234|0000)"', "Default/common password"),
        (r'PASSWORD\s+""', "Empty password"),
    ]

    for pattern, description in weak_patterns:
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            findings.append(
                Finding(
                    category="Weak Authentication",
                    location="PLC Protection Settings",
                    issue=f'{description}: "{match.group(1)}"',
                    impact="Unauthorized logic modification possible",
                    severity="CRITICAL",
                )
            )

    return findings


def check_hard_coded_values(content: str) -> list[Finding]:
    """Check for hard-coded safety limits"""
    findings: list[Finding] = []

    # Look for hard-coded numerical values in safety-related contexts
    safety_patterns = [
        (r"RUNG\s+(\d+).*?(pressure|temperature|speed).*?(\d+)", "Safety limit"),
        (r"HighPressureLimit.*?(\d+)", "Pressure limit"),
        (r"HighTemperature.*?(\d+)", "Temperature limit"),
    ]

    for pattern, description in safety_patterns:
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            rung = match.group(1) if len(match.groups()) >= 1 else "unknown"
            value = match.groups()[-1]

            findings.append(
                Finding(
                    category="Hard-coded Values",
                    location=f"Rung {rung}",
                    issue="Hard-coded safety limit (should be configurable parameter)",
                    impact="Logic change required to adjust safety limit",
                    severity="HIGH",
                    value=value,
                )
            )

    return findings


def check_undocumented_code(content: str, parsed: dict[str, Any]) -> list[Finding]:
    """Check for undocumented or suspicious code sections"""
    findings: list[Finding] = []

    # Look for unlabeled sections
    unlabeled = re.finditer(r"RUNG\s+(\d+)\s*\n\s*;?\s*$", content, re.MULTILINE)
    for match in unlabeled:
        rung = match.group(1)
        findings.append(
            Finding(
                category="Undocumented Functions",
                location=f"Rung {rung}",
                issue="No documentation or comments",
                impact="Purpose unclear, may be test code or backdoor",
                severity="MEDIUM",
            )
        )

    # Look for suspicious patterns
    suspicious_patterns = [
        (r"(diagnostic|debug|test).*?mode", "Debug/test mode"),
        (r"unlock|bypass", "Potential bypass logic"),
        (r"backdoor|hidden", "Suspicious naming"),
    ]

    for pattern, description in suspicious_patterns:
        matches = re.finditer(pattern, content, re.IGNORECASE)
        for match in matches:
            findings.append(
                Finding(
                    category="Suspicious Code",
                    location="Configuration",
                    issue=f"{description} detected: {match.group(0)}",
                    impact="Potential security backdoor or debugging remnant",
                    severity="HIGH",
                )
            )

    return findings


def check_remote_access(content: str) -> list[Finding]:
    """Check for insecure remote access configuration"""
    findings: list[Finding] = []

    if re.search(r"REMOTE_ACCESS\s+ENABLED", content, re.IGNORECASE):
        findings.append(
            Finding(
                category="Remote Access",
                location="Network Configuration",
                issue="Remote access enabled without strong authentication",
                impact="Unauthorized remote control possible",
                severity="CRITICAL",
            )
        )

    if re.search(r"AUTHENTICATION\s+(BASIC|NONE)", content, re.IGNORECASE):
        findings.append(
            Finding(
                category="Remote Access",
                location="Network Configuration",
                issue="Weak authentication method (Basic or None)",
                impact="Credentials easily intercepted or bypassed",
                severity="CRITICAL",
            )
        )

    return findings


# ============================================================================
# MAIN ANALYSIS FUNCTION
# ============================================================================


def analyse_safety_logic(project_file: str) -> dict[str, Any]:
    """
    Analyse safety PLC logic for security concerns
    This is offline analysis of exported configuration
    NEVER connects to actual PLC

    Args:
        project_file: Path to PLC project file

    Returns:
        Dictionary with analysis results
    """
    analysis_start = datetime.now()
    filepath = Path(project_file)

    print("=" * 70)
    print("[*] Safety System Configuration Analysis")
    print("=" * 70)
    print("[*] OFFLINE REVIEW ONLY - No connection to SIS")
    print(f"[*] File: {filepath.name}")
    print(f"[*] Analysis start: {analysis_start.strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    results: dict[str, Any] = {
        "analysis_start": analysis_start.isoformat(),
        "file": str(filepath),
        "findings": {
            "weak_passwords": [],
            "hard_coded_values": [],
            "undocumented_functions": [],
            "remote_access": [],
            "suspicious_code": [],
        },
        "statistics": {},
        "success": False,
    }

    # Check if file exists, create demo if not
    if not filepath.exists():
        print(f"[!] File not found: {filepath}")
        print("[*] Creating demo file for analysis...")
        if not create_demo_file(filepath):
            print("[!] Could not create demo file")
            return results
        print()

    # Detect file format
    file_format = detect_file_format(filepath)
    if file_format:
        print(f"[*] Detected format: {file_format}")
    else:
        print(f"[!] Unknown file format: {filepath.suffix}")
    print()

    # Parse file
    if filepath.suffix.upper() == ".L5K" or file_format == "allen_bradley":
        parsed = parse_l5k_file(filepath)
    else:
        print("[!] Unsupported file format for detailed parsing")
        print("[*] Performing basic text analysis...")
        try:
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                parsed = {"format": "generic", "raw_content": f.read()}
        except OSError as e:
            print(f"[!] Could not read file: {e}")
            return results

    content = parsed.get("raw_content", "")
    if not content:
        print("[!] No content to analyze")
        return results

    results["success"] = True

    # Perform security checks
    print("\n" + "=" * 70)
    print("[*] PERFORMING SECURITY ANALYSIS")
    print("=" * 70)

    all_findings: list[Finding] = []

    # Check 1: Weak passwords
    print("\n[*] Checking for weak authentication...")
    pwd_findings = check_weak_passwords(content)
    all_findings.extend(pwd_findings)
    print(f"    Found {len(pwd_findings)} issue(s)")

    # Check 2: Hard-coded values
    print("[*] Checking for hard-coded safety limits...")
    hardcoded_findings = check_hard_coded_values(content)
    all_findings.extend(hardcoded_findings)
    print(f"    Found {len(hardcoded_findings)} issue(s)")

    # Check 3: Undocumented code
    print("[*] Checking for undocumented code...")
    undoc_findings = check_undocumented_code(content, parsed)
    all_findings.extend(undoc_findings)
    print(f"    Found {len(undoc_findings)} issue(s)")

    # Check 4: Remote access
    print("[*] Checking remote access configuration...")
    remote_findings = check_remote_access(content)
    all_findings.extend(remote_findings)
    print(f"    Found {len(remote_findings)} issue(s)")

    # Organize findings by category
    for finding in all_findings:
        category_key = finding.category.lower().replace(" ", "_")
        if category_key not in results["findings"]:
            results["findings"][category_key] = []
        results["findings"][category_key].append(finding.to_dict())

    # Generate statistics
    severity_counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for finding in all_findings:
        severity_counts[finding.severity] = severity_counts.get(finding.severity, 0) + 1

    results["statistics"] = {
        "total_findings": len(all_findings),
        "by_severity": severity_counts,
        "by_category": {
            cat: len(findings) for cat, findings in results["findings"].items()
        },
    }

    # Print findings
    print("\n" + "=" * 70)
    print("[*] SECURITY FINDINGS")
    print("=" * 70)

    critical_findings = [f for f in all_findings if f.severity == "CRITICAL"]
    high_findings = [f for f in all_findings if f.severity == "HIGH"]

    if critical_findings:
        print("\n[!] CRITICAL ISSUES:")
        for finding in critical_findings:
            print(f"\n    Category: {finding.category}")
            print(f"    Location: {finding.location}")
            print(f"    Issue: {finding.issue}")
            if finding.value:
                print(f"    Value: {finding.value}")
            print(f"    Impact: {finding.impact}")

    if high_findings:
        print("\n[!] HIGH PRIORITY ISSUES:")
        for finding in high_findings:
            print(f"\n    Category: {finding.category}")
            print(f"    Location: {finding.location}")
            print(f"    Issue: {finding.issue}")
            if finding.value:
                print(f"    Value: {finding.value}")
            print(f"    Impact: {finding.impact}")

    # Summary
    print("\n" + "=" * 70)
    print("[*] ANALYSIS SUMMARY")
    print("=" * 70)
    print(f"Total findings: {len(all_findings)}")
    print(f"  • CRITICAL: {severity_counts['CRITICAL']}")
    print(f"  • HIGH: {severity_counts['HIGH']}")
    print(f"  • MEDIUM: {severity_counts['MEDIUM']}")
    print(f"  • LOW: {severity_counts['LOW']}")

    # Save report
    analysis_end = datetime.now()
    results["analysis_end"] = analysis_end.isoformat()
    results["duration_seconds"] = (analysis_end - analysis_start).total_seconds()

    # Ensure reports directory exists
    reports_dir = Path(__file__).parent.parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    report_file = (
        reports_dir
        / f'safety_plc_analysis_{analysis_start.strftime("%Y%m%d_%H%M%S")}.json'
    )
    try:
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\n[*] Detailed report saved: {report_file}")
    except OSError as e:
        print(f"\n[!] Could not save report: {e}")

    print("\n" + "=" * 70)

    return results


# ============================================================================
# MAIN EXECUTION
# ============================================================================

if __name__ == "__main__":
    print("\n[*] Safety PLC Configuration Security Analysis")
    print("[*] Offline analysis tool - never connects to live systems")
    print()

    # Analysis of exported configuration only
    project_file = "turbine_sis_backup.L5K"

    print(f"[*] Target file: {project_file}")
    print("[*] If file doesn't exist, a demo file will be created")
    print()

    response = input("Proceed with analysis? (yes/no): ")
    if response.lower() in ["yes", "y"]:
        analyse_safety_logic(project_file)
    else:
        print("[*] Analysis cancelled")
