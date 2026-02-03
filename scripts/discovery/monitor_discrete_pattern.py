from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient('127.0.0.1', port=10520)

print("Monitoring discrete pattern over time...")
print("Time     | Coils (0-15)         | As Hex  | As Int")
print("-" * 55)

previous_pattern = None

for i in range(6):
    try:
        client.connect()
        response = client.read_coils(address=0, count=16, device_id=1)
        client.close()

        if not response.isError():
            bits = response.bits[:16]
            bits_str = ''.join(['1' if b else '0' for b in bits])

            # Convert to integer
            value = 0
            for j, bit in enumerate(bits):
                if bit:
                    value |= (1 << j)

            hex_str = f"0x{value:04X}"

            timestamp = time.strftime("%H:%M:%S")
            change = " (CHANGED)" if previous_pattern is not None and previous_pattern != bits_str else ""
            print(f"{timestamp} | {bits_str} | {hex_str:6s} | {value:5d}{change}")

            previous_pattern = bits_str

        else:
            print(f"Error: {response}")

    except Exception as e:
        print(f"Connection error: {e}")
        client.close()

    if i < 5:
        time.sleep(3)  # Check every 3 seconds

print("Monitoring complete.")
