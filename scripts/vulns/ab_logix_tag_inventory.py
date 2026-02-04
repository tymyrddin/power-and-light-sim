#!/usr/bin/env python3
"""
Allen-Bradley Logix Tag Inventory
Enumerate tags from Allen-Bradley ControlLogix/CompactLogix PLCs.

Two modes:
1. REAL HARDWARE: Use pycomm3 with real Allen-Bradley PLCs (port 44818)
2. SIMULATOR: Use simplified tag enumeration against UU P&L simulator

The simulator provides a simplified EtherNet/IP implementation that responds
to basic connection requests. For full CIP protocol testing, use real hardware.

Requires: pycomm3 (optional, for real hardware)
Install: pip install pycomm3
"""

import socket
import struct
import sys


def enumerate_tags_simple(plc_ip: str, port: int = 44818) -> list[dict]:
    """
    Simplified tag enumeration for simulator.
    Connects to EtherNet/IP server and retrieves tag list.
    """
    print(f"[*] Connecting to {plc_ip}:{port}...")

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        sock.connect((plc_ip, port))

        print("[+] Connected successfully")
        print("[*] Sending Register Session request...")

        # Send Register Session command (0x0065)
        register_cmd = struct.pack("<H", 0x0065)  # Command
        register_len = struct.pack("<H", 4)  # Length
        register_handle = struct.pack("<I", 0)  # Session handle
        register_status = struct.pack("<I", 0)  # Status
        register_context = b"\x00" * 8  # Sender context
        register_options = struct.pack("<I", 0)  # Options
        protocol_version = struct.pack("<H", 1)
        option_flags = struct.pack("<H", 0)

        packet = (
            register_cmd
            + register_len
            + register_handle
            + register_status
            + register_context
            + register_options
            + protocol_version
            + option_flags
        )

        sock.send(packet)

        # Receive response
        response = sock.recv(1024)

        if len(response) >= 24:
            print("[+] Session registered")
            print("[*] EtherNet/IP server is running")
            print("\n[*] Simulator Tag List (predefined):")
            print("    " + "-" * 60)

            # For simulator, return hardcoded tag list
            # (Real implementation would query via CIP protocol)
            tags = [
                {"tag_name": "SpeedSetpoint", "data_type": "DINT", "writable": True},
                {"tag_name": "PowerSetpoint", "data_type": "DINT", "writable": True},
                {"tag_name": "CurrentSpeed", "data_type": "DINT", "writable": False},
                {"tag_name": "CurrentPower", "data_type": "DINT", "writable": False},
                {"tag_name": "BearingTemp", "data_type": "INT", "writable": False},
                {"tag_name": "OilPressure", "data_type": "INT", "writable": False},
                {"tag_name": "Vibration", "data_type": "INT", "writable": False},
                {"tag_name": "GeneratorTemp", "data_type": "INT", "writable": False},
                {"tag_name": "GearboxTemp", "data_type": "INT", "writable": False},
                {"tag_name": "AmbientTemp", "data_type": "INT", "writable": False},
                {"tag_name": "ControlMode", "data_type": "BOOL", "writable": True},
                {"tag_name": "EmergencyStop", "data_type": "BOOL", "writable": True},
                {"tag_name": "MaintenanceMode", "data_type": "BOOL", "writable": True},
                {"tag_name": "OverspeedAlarm", "data_type": "BOOL", "writable": False},
                {"tag_name": "LowOilPressure", "data_type": "BOOL", "writable": False},
                {"tag_name": "HighBearingTemp", "data_type": "BOOL", "writable": False},
                {"tag_name": "HighVibration", "data_type": "BOOL", "writable": False},
                {"tag_name": "GeneratorFault", "data_type": "BOOL", "writable": False},
            ]

            return tags

        else:
            print("[!] Invalid response from server")
            return []

    except TimeoutError:
        print("[!] Connection timeout")
        return []
    except ConnectionRefusedError:
        print("[!] Connection refused - server not running")
        return []
    except Exception as e:
        print(f"[!] Error: {e}")
        return []
    finally:
        sock.close()


def enumerate_tags_pycomm3(plc_ip: str) -> list[dict]:
    """
    Full tag enumeration using pycomm3 (for real hardware).
    """
    try:
        from pycomm3 import LogixDriver
    except ImportError:
        print("[!] pycomm3 not installed")
        print("[*] Install with: pip install pycomm3")
        return []

    try:
        with LogixDriver(plc_ip) as plc:
            print("[+] Connected successfully")
            print("[*] Enumerating tags...")

            tags = plc.get_tag_list()

            if not tags:
                print("    No tags found")
                return []

            return tags

    except Exception as e:
        print(f"[!] Error: {e}")
        return []


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Enumerate Allen-Bradley PLC tags")
    parser.add_argument(
        "--ip",
        default="127.0.0.1",
        help="PLC IP address (default: 127.0.0.1 for simulator)",
    )
    parser.add_argument(
        "--port", type=int, default=44818, help="EtherNet/IP port (default: 44818)"
    )
    parser.add_argument(
        "--real-hardware",
        action="store_true",
        help="Use pycomm3 for real Allen-Bradley hardware",
    )

    args = parser.parse_args()

    print("[*] Allen-Bradley Logix Tag Inventory")
    print(f"[*] Target: {args.ip}:{args.port}")
    print("-" * 60)

    if args.real_hardware:
        print("[*] Mode: Real Hardware (pycomm3)")
        tags = enumerate_tags_pycomm3(args.ip)
    else:
        print("[*] Mode: Simulator (simplified protocol)")
        tags = enumerate_tags_simple(args.ip, args.port)

    if tags:
        print(f"\n[*] Found {len(tags)} tags:\n")
        for tag in tags:
            writable = tag.get("writable", "?")
            rw = "R/W" if writable else "R/O" if writable == False else "?"
            print(f"    {tag['tag_name']:<30} {tag['data_type']:<10} [{rw}]")

        print("\n[+] Tag enumeration complete")
    else:
        print("\n[!] No tags retrieved")
        sys.exit(1)


if __name__ == "__main__":
    main()
