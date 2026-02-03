from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient('127.0.0.1', port=10520)

print("Testing write permissions (non-destructive)")
print("-" * 50)

# Test 1: Read current value of holding register 0 for ID 1
print("Test 1: Read current value of Holding Register 0 (ID 1)")
try:
    client.connect()
    read_response = client.read_holding_registers(address=0, count=1, device_id=1)
    client.close()

    if not read_response.isError():
        current_value = read_response.registers[0]
        print(f"  Current value: {current_value}")

        # Test 2: Write the same value back (non-destructive)
        print(f"\nTest 2: Write same value back ({current_value}) to Holding Register 0 (ID 1)")
        time.sleep(0.5)

        client.connect()
        write_response = client.write_register(address=0, value=current_value, device_id=1)
        client.close()

        if not write_response.isError():
            print(f"  SUCCESS: Write accepted")

            # Verify it didn't change
            time.sleep(0.5)
            client.connect()
            verify_response = client.read_holding_registers(address=0, count=1, device_id=1)
            client.close()

            if not verify_response.isError():
                new_value = verify_response.registers[0]
                print(f"  Verified value: {new_value} (change: {new_value - current_value})")
            else:
                print(f"  Verification error: {verify_response}")

        else:
            print(f"  Write rejected: {write_response}")

    else:
        print(f"  Read error: {read_response}")

except Exception as e:
    print(f"  Connection error: {e}")
    client.close()

print("\n" + "=" * 50)

# Test 3: Try writing to a different Unit ID
print("\nTest 3: Test write to different Unit ID (ID 2)")
try:
    client.connect()
    read_id2 = client.read_holding_registers(address=0, count=1, device_id=2)
    client.close()

    if not read_id2.isError():
        val_id2 = read_id2.registers[0]
        print(f"  ID 2 current value: {val_id2}")

        # Try writing same value to ID 2
        time.sleep(0.5)
        client.connect()
        write_id2 = client.write_register(address=0, value=val_id2, device_id=2)
        client.close()

        if not write_id2.isError():
            print(f"  SUCCESS: Write to ID 2 accepted")
        else:
            print(f"  Write to ID 2 rejected: {write_id2}")

    else:
        print(f"  Read ID 2 error: {read_id2}")

except Exception as e:
    print(f"  Connection error: {e}")
    client.close()

print("\nWrite permission tests complete.")
