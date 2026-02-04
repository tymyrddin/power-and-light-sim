#!/usr/bin/env python3
"""
S7 Read-Only Block Dump
Read-only PLC program block upload from Siemens S7-300/400.
Tests against UU P&L simulator reactor PLC on port 102.

REQUIRES ROOT: S7 protocol uses privileged port 102.
Run with: sudo .venv/bin/python scripts/vulns/s7_readonly_block_dump.py

LAB USE ONLY - Demonstrates block enumeration and upload capabilities.

Block Types:
- OB: Organization Blocks (main program logic)
- FC: Functions (callable subroutines)
- FB: Function Blocks (with instance data)
- DB: Data Blocks (memory storage)
"""

from datetime import datetime
from pathlib import Path

import snap7

PLC_IP = "127.0.0.1"
RACK = 0
SLOT = 2

# Define protocol block type codes
BLOCK_TYPE_MAP = {"OB": 0x38, "FC": 0x43, "FB": 0x45, "DB": 0x41}

print("[*] S7 Read-Only Block Dump")
print(f"[*] Target: {PLC_IP} (Rack {RACK}, Slot {SLOT})")
print(f"[*] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("[!] Note: Requires sudo for port 102 access")
print("-" * 50)

plc = snap7.client.Client()

try:
    plc.connect(PLC_IP, RACK, SLOT)

    if not plc.get_connected():
        raise RuntimeError("Failed to connect to PLC")

    print("[+] Connected to PLC")
    cpu_state = plc.get_cpu_state()
    print(f"[*] CPU state: {cpu_state}\n")

    # Create output directory for blocks
    output_dir = Path(__file__).parent.parent.parent / "reports" / "s7_blocks"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Enumerate blocks
    print("[*] Enumerating PLC blocks...")
    blocks = plc.list_blocks()

    block_count = 0
    for block_name, block_numbers in [
        ("OB", blocks.OB),
        ("FC", blocks.FC),
        ("FB", blocks.FB),
        ("DB", blocks.DB),
    ]:
        if not block_numbers:
            print(f"    {block_name}: No blocks found")
            continue

        print(f"    {block_name}: {len(block_numbers)} blocks")
        block_type_code = BLOCK_TYPE_MAP[block_name]

        for block_num in block_numbers:
            try:
                data, size = plc.full_upload(block_type_code, block_num)
                filename = output_dir / f"block_{block_name}_{block_num}.bin"
                with open(filename, "wb") as f:
                    f.write(data)
                print(f"        Dumped {filename.name} ({size} bytes)")
                block_count += 1
            except Exception as e:
                print(f"        Error dumping {block_name}{block_num}: {e}")

    print(f"\n[+] Successfully dumped {block_count} blocks to {output_dir}")
    print("[*] Block dump complete")

except PermissionError as e:
    print(f"\n[!] Permission denied: {e}")
    print("[*] S7 protocol requires root access for port 102")
    print("[*] Run with: sudo .venv/bin/python scripts/vulns/s7_readonly_block_dump.py")

except Exception as e:
    print(f"\n[!] Error: {e}")

finally:
    if plc.get_connected():
        plc.disconnect()
