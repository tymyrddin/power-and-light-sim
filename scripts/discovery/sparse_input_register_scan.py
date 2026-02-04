import time

from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10520)

# Checkpoints in input register space
# We know 0 and 100 exist. Let's find boundaries.
scan_points = [
    0,  # Known active
    1,  # Adjacent to active
    2,
    10,  # Small offset
    50,
    100,  # Known exists (zero)
    101,
    150,
    200,
    300,  # Common area for process variables
    400,
    500,
    1000,
]

print("Sparse scan of Input Registers...")
print("Address : Value | Note")
print("-" * 50)

for address in scan_points:
    try:
        client.connect()
        response = client.read_input_registers(address=address, count=1, device_id=1)
        client.close()

        if not response.isError():
            value = response.registers[0]
            note = ""
            if value != 0:
                note = "ACTIVE"
            print(f"{address:4d}    : {value:5d} | {note}")
        else:
            # Check if it's illegal address or other error
            if hasattr(response, "exception_code"):
                if response.exception_code == 2:
                    print(f"{address:4d}    : ILLEGAL ADDRESS")
                else:
                    print(f"{address:4d}    : Exception {response.exception_code}")
            else:
                print(f"{address:4d}    : Error - {response}")

        time.sleep(0.3)  # Gentle

    except Exception as e:
        print(f"{address:4d}    : Connection error - {e}")
        client.close()

print("Scan complete.")
