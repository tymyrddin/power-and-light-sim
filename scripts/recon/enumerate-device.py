#!/usr/bin/env python3
"""
Enumerate Device - EtherNet/IP Device Identification
Queries device identity using EtherNet/IP protocol (CIP)


sudo setcap cap_net_raw=eip .venv/bin/python3
"""

from cpppo.server.enip import client

# Simulator: Hex Turbine PLC on localhost:44818 (EtherNet/IP)
host = "127.0.0.1"
port = 44818

print(f"[*] Connecting to EtherNet/IP device at {host}:{port}...")

try:
    with client.connector(host=host, port=port) as conn:
        # Get_Attribute_All for Identity Object (Class 0x01, Instance 1)
        ops = client.parse_operations("get-attribute-all@1/1")

        for _index, _descr, op in ops:
            conn.write(op)
            reply = conn.read()
            print(f"[+] Identity object: {reply}")

except Exception as e:
    print(f"[!] Failed: {e}")
