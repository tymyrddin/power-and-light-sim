import time

from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10520)

print("Snapshot of register 0 across multiple Unit IDs")
print("Unit ID | Value (Holding Reg 0) | Delta from ID 1")
print("-" * 50)

base_value = None

# Check a spread of IDs
unit_ids = [1, 2, 3, 16, 32, 64, 127, 255]

for unit_id in unit_ids:
    try:
        client.connect()
        response = client.read_holding_registers(address=0, count=1, device_id=unit_id)
        client.close()

        if not response.isError():
            value = response.registers[0]

            if base_value is None:
                base_value = value
                delta = 0
            else:
                delta = value - base_value

            print(f"{unit_id:6d} | {value:20d} | {delta:4d}")
        else:
            print(f"{unit_id:6d} | Error: {response.exception_code}")

    except Exception as e:
        print(f"{unit_id:6d} | ERROR: {e}")
        client.close()

    time.sleep(0.1)

print("\nChecking if values are changing...")
print("Reading ID 1 three times quickly:")

for i in range(3):
    try:
        client.connect()
        response = client.read_holding_registers(address=0, count=1, device_id=1)
        client.close()

        if not response.isError():
            print(f"  Attempt {i + 1}: {response.registers[0]}")
        else:
            print(f"  Attempt {i + 1}: Error")

    except Exception as e:
        print(f"  Attempt {i + 1}: {e}")
        client.close()

    if i < 2:
        time.sleep(0.05)  # Very short delay

print("Snapshot complete.")
