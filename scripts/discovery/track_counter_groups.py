from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient('127.0.0.1', port=10520)

print("Tracking counter values across ID groups over time")
print("Time     | Group A (ID 1) | Group B (ID 32) | Group C (ID 255) | A-B Diff | A-C Diff")
print("-" * 80)

# Representative IDs for each group
group_a_id = 1  # IDs 1-2
group_b_id = 32  # IDs 3-127
group_c_id = 255  # ID 255

previous_values = {}

for sample in range(6):
    try:
        client.connect()

        # Read all three groups
        response_a = client.read_holding_registers(address=0, count=1, device_id=group_a_id)
        time.sleep(0.05)

        response_b = client.read_holding_registers(address=0, count=1, device_id=group_b_id)
        time.sleep(0.05)

        response_c = client.read_holding_registers(address=0, count=1, device_id=group_c_id)

        client.close()

        if (not response_a.isError() and
                not response_b.isError() and
                not response_c.isError()):

            val_a = response_a.registers[0]
            val_b = response_b.registers[0]
            val_c = response_c.registers[0]

            diff_ab = val_b - val_a
            diff_ac = val_c - val_a

            timestamp = time.strftime("%H:%M:%S")
            print(f"{timestamp} | {val_a:13d} | {val_b:13d} | {val_c:13d} | {diff_ab:8d} | {diff_ac:8d}")

            # Store for change detection
            current = (val_a, val_b, val_c)
            if sample > 0 and current != previous_values.get(sample - 1):
                print(f"          ^ Changed from previous sample")

            previous_values[sample] = current

        else:
            errors = []
            if response_a.isError():
                errors.append(f"A: {response_a.exception_code}")
            if response_b.isError():
                errors.append(f"B: {response_b.exception_code}")
            if response_c.isError():
                errors.append(f"C: {response_c.exception_code}")
            print(f"Read errors: {', '.join(errors)}")

    except Exception as e:
        print(f"Connection error: {e}")
        client.close()

    if sample < 5:
        time.sleep(3)  # Sample every 3 seconds

print("Tracking complete.")
