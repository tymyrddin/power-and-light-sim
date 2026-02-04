from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10520)

print("Checking discrete points...")
print("-" * 40)

# Check first 16 coils (discrete outputs, function 01)
print("Coils (addresses 0-15):")
try:
    client.connect()
    coil_response = client.read_coils(address=0, count=16, device_id=1)
    client.close()

    if not coil_response.isError():
        coils = coil_response.bits[:16]  # First 16 bits
        for i in range(0, 16, 8):  # Print in groups of 8
            group = coils[i : i + 8]
            bits_str = " ".join(["1" if b else "0" for b in group])
            print(f"  Coils {i:2d}-{i + 7:2d}: {bits_str}")
    else:
        print(f"  Error: {coil_response}")

except Exception as e:
    print(f"  Connection error: {e}")
    client.close()

print()

# Check first 16 discrete inputs (function 02)
print("Discrete Inputs (addresses 0-15):")
try:
    client.connect()
    di_response = client.read_discrete_inputs(address=0, count=16, device_id=1)
    client.close()

    if not di_response.isError():
        discrete_inputs = di_response.bits[:16]
        for i in range(0, 16, 8):
            group = discrete_inputs[i : i + 8]
            bits_str = " ".join(["1" if b else "0" for b in group])
            print(f"  DI {i:2d}-{i + 7:2d}: {bits_str}")
    else:
        print(f"  Error: {di_response}")

except Exception as e:
    print(f"  Connection error: {e}")
    client.close()

print("Discrete points check complete.")
