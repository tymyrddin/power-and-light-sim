#!/usr/bin/env python3
"""
S7 Memory Read
Read various memory areas from S7 PLC for reconnaissance.
Tests against UU P&L simulator reactor PLC on port 102.

REQUIRES ROOT: S7 protocol uses privileged port 102.
Run with: sudo .venv/bin/python scripts/vulns/s7_read_memory.py

Memory Areas:
- 0x81: Process inputs (PE)
- 0x82: Process outputs (PA)
- DB1: Data Block 1 (input registers/telemetry)
"""

import snap7
from datetime import datetime


def main():
    plc_ip = "127.0.0.1"
    rack = 0
    slot = 2

    print("[*] S7 Memory Read")
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

        # Note: python-snap7 ships incomplete / mismatched type hints

        # Read 10 bytes of inputs (PE - Process Inputs)
        print("[*] Reading Process Inputs (PE area, 10 bytes)...")
        try:
            inputs = plc.read_area(0x81, 0, 0, 10)
            print(f"    PE data: {inputs.hex()}")
        except Exception as e:
            print(f"    Error: {e}")

        # Read 10 bytes of outputs (PA - Process Outputs)
        print("[*] Reading Process Outputs (PA area, 10 bytes)...")
        try:
            outputs = plc.read_area(0x82, 0, 0, 10)
            print(f"    PA data: {outputs.hex()}")
        except Exception as e:
            print(f"    Error: {e}")

        # Read 100 bytes from DB1 (Data Block 1 - Input Registers)
        print("[*] Reading Data Block 1 (100 bytes)...")
        try:
            db_data = plc.db_read(1, 0, 100)
            print(f"    DB1 data (first 20 bytes): {db_data[:20].hex()}")
            print(f"    Total DB1 bytes read: {len(db_data)}")
        except Exception as e:
            print(f"    Error: {e}")

        print("\n[*] Memory read reconnaissance complete")

    except PermissionError as e:
        print(f"\n[!] Permission denied: {e}")
        print("[*] S7 protocol requires root access for port 102")
        print("[*] Run with: sudo .venv/bin/python scripts/vulns/s7_read_memory.py")

    except Exception as e:
        print(f"\n[!] Error: {e}")

    finally:
        if plc.get_connected():
            plc.disconnect()


if __name__ == "__main__":
    main()
