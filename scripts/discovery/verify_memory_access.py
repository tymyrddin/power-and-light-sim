from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10520)

# Test specific addresses that showed data before
test_addresses = [0, 400, 500]

print("Verifying access to specific addresses...")
print("-" * 40)

for address in test_addresses:
    try:
        client.connect()
        # Try to read just one register
        response = client.read_holding_registers(address=address, count=1, device_id=1)
        client.close()

        if not response.isError():
            print(f"Address {address:4d} : OK - Value = {response.registers[0]}")
        else:
            # Decode the exception
            print(f"Address {address:4d} : Exception - {response}")

    except Exception as e:
        print(f"Address {address:4d} : Connection error - {e}")
        client.close()

print("Verification complete.")
