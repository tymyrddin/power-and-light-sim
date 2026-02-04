#!/usr/bin/env python3
"""
Modbus Device Identity Probe

Queries Modbus devices for identity information using Function Code 43 (Read Device Identification).
This reveals vendor, product code, firmware version, and other identifying information.

Security Impact:
- Device fingerprinting without authentication
- Reveals firmware versions (may have known vulnerabilities)
- Identifies legacy/EOL equipment
- Enables targeted exploits
"""

import json
from datetime import datetime
from pathlib import Path

from pymodbus.client import ModbusTcpClient
from pymodbus.constants import DeviceInformation


def probe_device_identity(host: str, port: int, unit_id: int = 1) -> dict:
    """
    Query Modbus device for identity information.

    Args:
        host: Target IP address
        port: Modbus TCP port
        unit_id: Modbus unit ID (slave address)

    Returns:
        Dictionary with device information or error status
    """
    result = {
        "host": host,
        "port": port,
        "unit_id": unit_id,
        "supported": False,
        "information": {},
        "error": None,
    }

    client = ModbusTcpClient(host=host, port=port)

    if not client.connect():
        result["error"] = "Connection failed"
        return result

    # Set unit ID for pymodbus 3.x
    client.slave_id = unit_id

    try:
        # Read basic device identification (Function 43 / MEI 14)
        response = client.read_device_information(read_code=DeviceInformation.BASIC)

        if response.isError():
            result["error"] = (
                "Device does not support Read Device Identification (FC 43)"
            )
        else:
            result["supported"] = True
            # Extract device information (decode bytes to strings for JSON)
            if hasattr(response, "information"):
                result["information"] = {
                    k: v.decode("utf-8") if isinstance(v, bytes) else v
                    for k, v in response.information.items()
                }

    except Exception as e:
        result["error"] = f"Exception: {str(e)}"
    finally:
        client.close()

    return result


def main():
    """Probe all simulator devices for identity information."""

    print("=" * 70)
    print("[*] Modbus Device Identity Probe (Function Code 43)")
    print("[*] Scanning ICS Simulator Devices")
    print("=" * 70 + "\n")

    # Define target devices from simulator
    targets = [
        (1, "Hex Steam Turbine PLC", 10502),
        (2, "Hex Turbine Safety PLC", 10503),
        (10, "Alchemical Reactor PLC", 10504),
        (20, "Library HVAC PLC", 10505),
        (21, "Library L-Space Monitor", 10506),
        (100, "Main Substation RTU", 10510),
        (200, "Primary SCADA Server", 10520),
    ]

    results = []
    supported_count = 0

    for unit_id, name, port in targets:
        print(f"[*] Probing {name} (127.0.0.1:{port}, Unit ID {unit_id})...")

        result = probe_device_identity("127.0.0.1", port, unit_id)
        result["device_name"] = name
        results.append(result)

        if result["supported"]:
            supported_count += 1
            print("    ✓ Device Identification Supported")
            for obj_id, value in result["information"].items():
                print(f"      {obj_id}: {value}")
        else:
            print(f"    ✗ {result['error']}")
        print()

    # Summary
    print("=" * 70)
    print(
        f"[*] Scan Complete: {supported_count}/{len(targets)} devices support Device Identification"
    )
    print("=" * 70)

    # Ensure reports directory exists
    reports_dir = Path(__file__).parent.parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "scan_type": "modbus_device_identification",
        "targets_scanned": len(targets),
        "devices_supporting_fc43": supported_count,
        "results": results,
        "security_impact": {
            "information_disclosure": [
                "Vendor and model information exposed without authentication",
                "Firmware versions may reveal known vulnerabilities",
                "Product codes enable targeted exploit searches",
                "Identifies legacy/unsupported equipment",
            ],
            "attack_enablement": [
                "Device fingerprinting for exploit selection",
                "Firmware version matching against CVE databases",
                "Identification of weak/outdated devices to target first",
                "Supply chain and vendor enumeration",
            ],
        },
    }

    filename = (
        reports_dir
        / f"device_identity_probe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    with open(filename, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n[*] Results saved to {filename}")

    if supported_count == 0:
        print("\n[!] NOTE: No devices support Modbus Device Identification.")
        print("[!] This is common for basic/legacy devices.")
        print("[!] Alternative fingerprinting methods:")
        print("    - Analyze response timing and error codes")
        print("    - Memory map structure analysis")
        print("    - Protocol-specific queries (e.g., S7 SZL reads)")


if __name__ == "__main__":
    main()
