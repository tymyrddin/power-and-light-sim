from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient('127.0.0.1', port=10520)

print("Scanning for responsive Unit IDs...")
print("Unit ID | Holding Reg 0 | Input Reg 0 | Responsive?")
print("-" * 55)

# Common Modbus Unit IDs to test
unit_ids_to_test = [1, 2, 3, 4, 5, 6, 7, 8, 16, 32, 64, 127, 255]

for unit_id in unit_ids_to_test:
    try:
        client.connect()

        # Try to read holding register 0
        hr_response = client.read_holding_registers(address=0, count=1, device_id=unit_id)

        # Brief pause between requests
        time.sleep(0.1)

        # Try input register 0
        ir_response = client.read_input_registers(address=0, count=1, device_id=unit_id)

        client.close()

        responsive = False
        hr_value = "N/A"
        ir_value = "N/A"

        if not hr_response.isError():
            hr_value = hr_response.registers[0]
            responsive = True
        else:
            hr_value = f"Err:{hr_response.exception_code if hasattr(hr_response, 'exception_code') else 'X'}"

        if not ir_response.isError():
            ir_value = ir_response.registers[0]
            responsive = True
        else:
            ir_value = f"Err:{ir_response.exception_code if hasattr(ir_response, 'exception_code') else 'X'}"

        status = "YES" if responsive else "NO"
        print(f"{unit_id:6d} | {str(hr_value):12s} | {str(ir_value):11s} | {status}")

    except Exception as e:
        print(f"{unit_id:6d} | ERROR: {e}")
        client.close()

    time.sleep(0.2)  # Gentle pacing between IDs

print("Unit ID scan complete.")
