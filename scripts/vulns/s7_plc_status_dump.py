#!/usr/bin/env python3
"""
S7 PLC Status Dump
Read-only reconnaissance of S7 PLC status and configuration.
Tests against UU P&L simulator reactor PLC on port 102.

REQUIRES ROOT: S7 protocol uses privileged port 102.
Run with: sudo .venv/bin/python scripts/vulns/s7_plc_status_dump.py
"""

import json
from datetime import datetime
from pathlib import Path

import snap7


def main():
    plc_ip = "127.0.0.1"
    rack = 0
    slot = 2

    print("[*] S7 PLC Status Dump")
    print(f"[*] Target: {plc_ip} (Rack {rack}, Slot {slot})")
    print(f"[*] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("[!] Note: Requires sudo for port 102 access")
    print("-" * 50)

    plc = snap7.client.Client()

    try:
        plc.connect(plc_ip, rack, slot)

        if not plc.get_connected():
            raise RuntimeError("Failed to connect to PLC")

        print("[+] Connected successfully\n")

        # Get CPU state
        cpu_state = plc.get_cpu_state()
        print(f"[*] CPU State: {cpu_state}")

        # Get CPU information
        cpu_info = plc.get_cpu_info()
        print("\n[*] CPU Information:")
        print(f"    Module Type: {cpu_info.ModuleTypeName}")
        print(f"    Serial Number: {cpu_info.SerialNumber}")
        print(f"    Module Name: {cpu_info.ModuleName}")
        print(f"    AS Name: {cpu_info.ASName}")
        print(f"    Copyright: {cpu_info.Copyright}")

        # Save results
        results = {
            "timestamp": datetime.now().isoformat(),
            "target": f"{plc_ip}:{102}",
            "rack": rack,
            "slot": slot,
            "cpu_state": str(cpu_state),
            "cpu_info": {
                "module_type": cpu_info.ModuleTypeName,
                "serial_number": cpu_info.SerialNumber,
                "module_name": cpu_info.ModuleName,
                "as_name": cpu_info.ASName,
                "copyright": cpu_info.Copyright,
            },
        }

        # Save to reports
        reports_dir = Path(__file__).parent.parent.parent / "reports"
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = reports_dir / f"s7_status_{timestamp}.json"

        with open(report_file, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n[*] Status dump saved to: {report_file}")
        print("[*] Reconnaissance complete")

    except PermissionError as e:
        print(f"\n[!] Permission denied: {e}")
        print("[*] S7 protocol requires root access for port 102")
        print("[*] Run with: sudo .venv/bin/python scripts/vulns/s7_plc_status_dump.py")

    except Exception as e:
        print(f"\n[!] Error: {e}")

    finally:
        if plc.get_connected():
            plc.disconnect()


if __name__ == "__main__":
    main()
