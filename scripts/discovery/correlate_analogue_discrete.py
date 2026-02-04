import time

from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10520)

print("Correlating analogue counter with discrete pattern")
print("Time     | Analogue | Discrete Lower | Discrete Upper | Notes")
print("-" * 65)

for i in range(4):
    try:
        client.connect()

        # Read analogue counter (holding register 0)
        analogue_response = client.read_holding_registers(
            address=0, count=1, device_id=1
        )

        # Read discrete pattern (coils 0-15)
        discrete_response = client.read_coils(address=0, count=16, device_id=1)

        client.close()

        if not analogue_response.isError() and not discrete_response.isError():
            analogue_val = analogue_response.registers[0]
            bits = discrete_response.bits[:16]

            # Convert discrete to two bytes
            lower_byte = 0
            upper_byte = 0
            for j in range(8):
                if bits[j]:
                    lower_byte |= 1 << j
                if bits[j + 8]:
                    upper_byte |= 1 << j

            # Calculate what the discrete bits would represent as a 16-bit integer
            discrete_as_int = (upper_byte << 8) | lower_byte

            # Check relationships
            notes = []
            if upper_byte == 210:  # 0xD2
                notes.append("Upper fixed=210")

            # Is the discrete value somehow derived from the analogue?
            diff = abs(analogue_val - discrete_as_int)
            if diff < 100:
                notes.append(f"Close to analogue (diff={diff})")

            timestamp = time.strftime("%H:%M:%S")
            print(
                f"{timestamp} | {analogue_val:8d} | {lower_byte:3d} (0x{lower_byte:02X}) | {upper_byte:3d} (0x{upper_byte:02X}) | {', '.join(notes)}"
            )

        else:
            print(
                f"Read error: Analogue={analogue_response}, Discrete={discrete_response}"
            )

    except Exception as e:
        print(f"Connection error: {e}")
        client.close()

    if i < 3:
        time.sleep(3)

print("Correlation complete.")
