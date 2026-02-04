#!/usr/bin/env python3
"""
Scan Unit IDs - Modbus Unit ID Discovery
Scans for responsive unit IDs on a Modbus TCP server
"""

import time

from pymodbus.client import ModbusTcpClient

# Scan multiple ports to find all devices
ports = [10502, 10503, 10504, 10505, 10506, 10510, 10520]

print("Scanning for responsive Unit IDs across all simulator ports...")
print(f"{'Port':<7} | {'Unit ID':<8} | {'HR[0]':<12} | {'IR[0]':<12} | Responsive?")
print("-" * 70)

# Common Modbus Unit IDs to test
unit_ids_to_test = [1, 2, 3, 10, 20, 21, 100, 200]

for port in ports:
    client = ModbusTcpClient("127.0.0.1", port=port)

    for unit_id in unit_ids_to_test:
        try:
            if not client.connect():
                break

            # Set unit ID for pymodbus 3.x
            client.slave_id = unit_id

            # Try to read holding register 0
            hr_response = client.read_holding_registers(address=0, count=1)

            # Brief pause between requests
            time.sleep(0.05)

            # Try input register 0
            ir_response = client.read_input_registers(address=0, count=1)

            responsive = False
            hr_value = "N/A"
            ir_value = "N/A"

            if not hr_response.isError():
                hr_value = hr_response.registers[0]
                responsive = True

            if not ir_response.isError():
                ir_value = ir_response.registers[0]
                responsive = True

            if responsive:
                status = "YES"
                print(
                    f"{port:<7} | {unit_id:<8} | {str(hr_value):<12} | {str(ir_value):<12} | {status}"
                )

        except Exception:
            pass  # Suppress errors for non-responsive unit IDs

    client.close()
    time.sleep(0.1)

print("\n[*] Unit ID scan complete.")
