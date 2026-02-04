#!/usr/bin/env python3
"""
Siemens S7 PLC Connection Test
Tests connection and reads CPU information from S7 reactor PLC.

Tests against UU P&L simulator reactor PLC on port 102.
REQUIRES ROOT: S7 protocol uses privileged port 102.

Run with: sudo .venv/bin/python scripts/vulns/testing-turbine-control-plcs.py

Requires: python-snap7
"""

import snap7

# UU P&L simulator reactor PLC (S7 protocol)
PLC_IP = '127.0.0.1'
RACK = 0
SLOT = 2  # Slot 2 for S7-400 CPUs (per protocols.yml)

print("[*] Siemens S7 PLC Connection Test")
print(f"[*] Target: {PLC_IP} (Rack {RACK}, Slot {SLOT})")
print("[!] Note: Requires sudo for port 102 access")
print("-" * 50)

plc = snap7.client.Client()

try:
    plc.connect(PLC_IP, RACK, SLOT)

    if not plc.get_connected():
        raise RuntimeError("Connection failed")

    print("[+] Connected successfully")

    # Check connection
    cpu_state = plc.get_cpu_state()
    print(f"\n[*] CPU State: {cpu_state}")

    # Read CPU information
    cpu_info = plc.get_cpu_info()
    print(f"[*] CPU Type: {cpu_info.ModuleTypeName}")
    print(f"[*] Serial Number: {cpu_info.SerialNumber}")
    print(f"[*] Module Name: {cpu_info.ModuleName}")

    print("\n[+] Connection test successful")

except PermissionError as e:
    print(f"\n[!] Permission denied: {e}")
    print("[*] S7 protocol requires root access for port 102")
    print("[*] Run with: sudo .venv/bin/python scripts/vulns/testing-turbine-control-plcs.py")

except Exception as e:
    print(f"\n[!] Error: {e}")
    print("[*] Make sure the simulator is running")
    print("[*] Check that S7 server started successfully")

finally:
    if plc.get_connected():
        plc.disconnect()
