from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient('127.0.0.1', port=10520)
client.connect()

# The method signature shows the parameter is 'device_id'
response = client.read_holding_registers(address=0, count=10, device_id=1)

if not response.isError():
    print("Register block 0-9 values:", response.registers)
else:
    print("Modbus exception:", response)

client.close()