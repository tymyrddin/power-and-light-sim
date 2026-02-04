import struct

from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10520)
client.connect()

# Read registers 0 and 1 as a potential 32-bit value
response = client.read_holding_registers(address=0, count=2, device_id=1)
client.close()

if not response.isError():
    reg0, reg1 = response.registers
    print(f"Register 0 (low word): {reg0}")
    print(f"Register 1 (high word): {reg1}")

    # Combine into a 32-bit integer (assuming big-endian)
    combined_value = (reg1 << 16) | reg0
    print(f"Combined 32-bit value: {combined_value}")

    # Also try interpreting as a 32-bit float (IEEE 754)
    # Pack the two registers as big-endian 16-bit values, then interpret as 32-bit float
    bytes_for_float = reg0.to_bytes(2, byteorder="big") + reg1.to_bytes(
        2, byteorder="big"
    )
    try:
        float_value = struct.unpack(">f", bytes_for_float)[0]  # '>' for big-endian
        print(f"As 32-bit float: {float_value}")
    except Exception as e:
        print(f"Could not interpret as float: {e}")
else:
    print("Modbus exception:", response)
