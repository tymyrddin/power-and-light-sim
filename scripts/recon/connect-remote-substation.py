#!/usr/bin/env python3
"""
Connect Remote Substation - OPC UA Reconnaissance
Tests connectivity to OPC UA servers and browses available objects
"""

import asyncio

from asyncua import Client


async def test_opcua():
    # Simulator: Primary SCADA Server on localhost:4840
    client = Client("opc.tcp://127.0.0.1:4840")

    print("[*] Connecting to OPC UA server at opc.tcp://127.0.0.1:4840...")

    try:
        async with client:
            print("[+] Connected!")

            # Get root node
            root = client.get_root_node()
            print(f"[+] Root node: {root}")

            # Browse available objects
            print("[*] Browsing objects...")
            objects = await root.get_children()
            for obj in objects:
                browse_name = await obj.read_browse_name()
                print(f"  - {browse_name}")

    except Exception as e:
        print(f"[!] Failed: {e}")


asyncio.run(test_opcua())
