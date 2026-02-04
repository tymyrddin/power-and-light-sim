#!/usr/bin/env python3
"""
Test Write Permissions - Discovery of writable register addresses
Tests if holding registers can be written to (non-destructively)
"""

import time

from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10502)

print("Testing write permissions (non-destructive)")
print("-" * 50)

# Test 1: Read current value
print("Test 1: Read current value of Holding Register 0")
try:
    if not client.connect():
        print("[!] Connection failed")
        exit(1)

    client.slave_id = 1
    read_response = client.read_holding_registers(address=0, count=1)

    if not read_response.isError():
        current_value = read_response.registers[0]
        print(f"  Current value: {current_value}")

        # Test 2: Write the same value back (non-destructive)
        print(f"\nTest 2: Write same value back ({current_value})")
        time.sleep(0.2)

        write_response = client.write_register(address=0, value=current_value)

        if not write_response.isError():
            print("  ✓ Write accepted")

            # Verify it didn't change
            time.sleep(0.2)
            verify_response = client.read_holding_registers(address=0, count=1)

            if not verify_response.isError():
                new_value = verify_response.registers[0]
                print(f"  ✓ Verified value: {new_value}")
        else:
            print(f"  ✗ Write rejected: {write_response}")
    else:
        print(f"  ✗ Read error: {read_response}")

except Exception as e:
    print(f"  ✗ Error: {e}")
finally:
    client.close()

print("\n[*] Write permission tests complete.")
