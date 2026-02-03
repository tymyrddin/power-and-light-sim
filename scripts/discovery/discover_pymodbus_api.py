import pymodbus.client
import inspect

# Inspect the signature of the read_holding_registers method
sig = inspect.signature(pymodbus.client.ModbusTcpClient.read_holding_registers)
print("Method signature:", sig)

# Also check the client constructor
client_sig = inspect.signature(pymodbus.client.ModbusTcpClient)
print("Client constructor signature:", client_sig)
