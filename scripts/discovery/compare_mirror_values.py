import time

from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10520)

print("Comparing Holding Register 0 vs Input Register 0")
print("Time             | Holding Reg 0 | Input Reg 0 | Match?")
print("-" * 55)

for i in range(5):
    try:
        client.connect()

        # Read both at nearly the same time
        holding_response = client.read_holding_registers(
            address=0, count=1, device_id=1
        )
        input_response = client.read_input_registers(address=0, count=1, device_id=1)

        client.close()

        if not holding_response.isError() and not input_response.isError():
            holding_val = holding_response.registers[0]
            input_val = input_response.registers[0]
            match = (
                "YES"
                if holding_val == input_val
                else f"NO (diff: {abs(holding_val - input_val)})"
            )

            timestamp = time.strftime("%H:%M:%S")
            print(f"{timestamp} | {holding_val:13d} | {input_val:11d} | {match}")
        else:
            print(f"Error: Holding={holding_response}, Input={input_response}")

    except Exception as e:
        print(f"Connection error: {e}")
        client.close()

    if i < 4:
        time.sleep(2)  # Short interval

print("Comparison complete.")
