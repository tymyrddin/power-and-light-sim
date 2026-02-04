import time

from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10520)

# Strategic checkpoints in the memory map
scan_points = [
    0,  # Known active
    100,  # Common input area
    300,  # Holding registers
    400,  # Classic 4xxxx area (adjusted to 0-based)
    500,
    1000,  # Extended memory
    2000,
    3000,
    4000,
    5000,
]

print("Starting sparse memory scan...")
print("Address : Values (first two registers)")
print("-" * 40)

for address in scan_points:
    try:
        client.connect()
        response = client.read_holding_registers(address=address, count=2, device_id=1)
        client.close()

        if not response.isError():
            values = response.registers
            # Only report non-zero findings
            if values[0] != 0 or values[1] != 0:
                print(f"{address:4d}    : {values}")
        else:
            # Errors are data too
            print(f"{address:4d}    : Modbus Error - {response}")

        time.sleep(0.5)  # Gentle pacing

    except Exception as e:
        print(f"{address:4d}    : Connection error - {e}")
        client.close()

print("Scan complete.")
