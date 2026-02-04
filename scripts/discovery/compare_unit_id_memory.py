import time

from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10520)

print("Comparing memory layout between Unit ID 1 and Unit ID 2")
print("Address | Unit 1 (Holding) | Unit 2 (Holding) | Match?")
print("-" * 55)

# Test a few key addresses
test_addresses = [0, 1, 10, 100, 400, 500]

for address in test_addresses:
    try:
        client.connect()

        # Read from Unit ID 1
        response1 = client.read_holding_registers(address=address, count=1, device_id=1)

        time.sleep(0.1)

        # Read from Unit ID 2
        response2 = client.read_holding_registers(address=address, count=1, device_id=2)

        client.close()

        if not response1.isError() and not response2.isError():
            val1 = response1.registers[0]
            val2 = response2.registers[0]
            match = "YES" if val1 == val2 else f"NO ({val1} vs {val2})"
            print(f"{address:6d} | {val1:15d} | {val2:15d} | {match}")
        else:
            # Handle errors
            err1 = (
                "OK" if not response1.isError() else f"Err:{response1.exception_code}"
            )
            err2 = (
                "OK" if not response2.isError() else f"Err:{response2.exception_code}"
            )
            print(f"{address:6d} | {err1:15s} | {err2:15s} | N/A")

    except Exception as e:
        print(f"{address:6d} | ERROR: {e}")
        client.close()

    time.sleep(0.2)

print("Comparison complete.")
