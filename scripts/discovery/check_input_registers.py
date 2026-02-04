#!/usr/bin/env python3
"""
Check Input Registers - Discovery of readable input register addresses
Tests which input register addresses are accessible
"""

from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10502)
client.slave_id = 1

print("Probing Input Registers (function code 04)...")
print("Address : Value (if accessible)")
print("-" * 40)

# Try a few strategic starting points for input registers
# In pymodbus 3.x, we use the actual address (0-based)
test_addresses = [0, 1, 2, 5, 10, 50, 100]

for address in test_addresses:
    try:
        if not client.connect():
            print("[!] Connection failed")
            break
        # read_input_registers for function code 04
        response = client.read_input_registers(address=address, count=1)
        client.close()

        if not response.isError():
            print(f"Input Register {address:4d} : OK - Value = {response.registers[0]}")
        else:
            # Don't print errors for all addresses - too noisy
            # Just note if we get a different error than illegal address
            if hasattr(response, "exception_code"):
                if response.exception_code != 2:  # Not "Illegal Data Address"
                    print(f"Input Register {address:4d} : Exception - {response}")
            else:
                print(f"Input Register {address:4d} : Error - {response}")

    except Exception as e:
        print(f"Input Register {address:4d} : Connection error - {e}")
        client.close()

print("Input register probe complete.")
