from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10520)
client.connect()
result = client.read_holding_registers(address=0, count=1)
print(result)
client.close()
