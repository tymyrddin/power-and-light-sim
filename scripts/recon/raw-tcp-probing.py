#!/usr/bin/env python3
"""
Raw TCP Probing - Basic Modbus connectivity test
Tests if we can connect to and read from a Modbus device
"""

from pymodbus.client import ModbusTcpClient

# Simulator: Hex Turbine PLC on localhost:10502
client = ModbusTcpClient("127.0.0.1", port=10502)
client.slave_id = 1  # Unit ID for turbine PLC

if not client.connect():
    print("[!] Failed to connect")
    exit(1)

print("[*] Connected to Modbus server")

# Read holding register 0 (speed setpoint)
result = client.read_holding_registers(address=0, count=1)

if not result.isError():
    print(f"[+] Current setpoint: {result.registers[0]} RPM")
else:
    print(f"[!] Error: {result}")

client.close()
print("[*] Connection closed")
