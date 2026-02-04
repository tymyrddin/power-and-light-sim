#!/usr/bin/env python3
"""
Modbus Memory Census - Memory Map Discovery
Discovers what memory regions are accessible on a Modbus device
"""

from pymodbus.client import ModbusTcpClient

client = ModbusTcpClient("127.0.0.1", port=10502)
client.slave_id = 1

if not client.connect():
    print("[!] Connection failed")
    exit(1)

print("[*] Reading holding registers 0-9...")
response = client.read_holding_registers(address=0, count=10)

if not response.isError():
    print(f"[+] Register block 0-9 values: {response.registers}")
else:
    print(f"[!] Modbus exception: {response}")

client.close()
print("[*] Census complete")
