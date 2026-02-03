from pymodbus.client import ModbusTcpClient
import time

client = ModbusTcpClient('127.0.0.1', port=10520)  # Constructor: only host and port

for i in range(5):
    client.connect()
    # Method: device_id goes here
    response = client.read_holding_registers(address=0, count=1, device_id=1)
    client.close()

    if not response.isError():
        print(f"Sample {i+1}: {response.registers[0]}")
    else:
        print(f"Sample {i+1}: Error - {response}")

    if i < 4:
        time.sleep(5)
