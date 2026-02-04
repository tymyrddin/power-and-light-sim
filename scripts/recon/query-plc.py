#!/usr/bin/env python3
"""
Query PLC - Siemens S7 Protocol Reconnaissance
Tests connectivity and reads data from S7 PLC
"""

import snap7

# Simulator: Reactor PLC on localhost:102, rack 0, slot 2
plc = snap7.client.Client()
print("[*] Connecting to S7 PLC at 127.0.0.1:102...")

try:
    plc.connect("127.0.0.1", 0, 2)  # IP, rack, slot (port 102 is default)
    print("[+] Connected!")

    # Read CPU status
    cpu_status = plc.get_cpu_state()
    print(f"[+] PLC CPU Status: {cpu_status}")

    # Read data block 1, starting at byte 0, length 100
    try:
        data = plc.db_read(1, 0, 100)
        print(f"[+] Data Block 1 (first 20 bytes): {data[:20]}")
    except Exception as e:
        print(f"[!] Could not read DB1: {e}")

    plc.disconnect()
    print("[*] Disconnected")

except Exception as e:
    print(f"[!] Connection failed: {e}")
