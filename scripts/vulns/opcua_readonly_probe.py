#!/usr/bin/env python3
"""
OPC UA Anonymous Browse
Read-only reconnaissance of OPC UA server object hierarchy.
Tests against UU P&L simulator substation controller on port 63342.
"""

import asyncio
from asyncua import Client
from datetime import datetime
from pathlib import Path
import json


async def opcua_anonymous_browse():
    target_url = "opc.tcp://127.0.0.1:63342"

    print(f"[*] OPC UA Anonymous Browse")
    print(f"[*] Target: {target_url}")
    print(f"[*] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)

    client = Client(target_url)

    try:
        async with client:
            print("[*] Connected successfully")

            # Get server info
            server_node = client.get_server_node()
            server_status = await server_node.read_server_status()
            print(f"\n[*] Server Status:")
            print(f"    State: {server_status.State}")
            print(f"    Current Time: {server_status.CurrentTime}")
            print(f"    Build Info: {server_status.BuildInfo.ProductName}")

            # Browse root objects
            print(f"\n[*] Browsing Root Objects:")
            root = client.get_root_node()
            objects = await root.get_children()

            results = {
                "timestamp": datetime.now().isoformat(),
                "server_url": target_url,
                "server_status": str(server_status.State),
                "objects": []
            }

            for obj in objects:
                try:
                    browse_name = await obj.read_browse_name()
                    display_name = await obj.read_display_name()
                    node_class = await obj.read_node_class()

                    obj_info = {
                        "browse_name": browse_name.Name,
                        "display_name": display_name.Text,
                        "node_class": str(node_class)
                    }

                    print(f"    {browse_name.Name} ({display_name.Text})")

                    # Try to get children
                    try:
                        children = await obj.get_children()
                        if children:
                            print(f"      └─ {len(children)} child nodes")
                            obj_info["children_count"] = len(children)
                    except Exception:
                        pass

                    results["objects"].append(obj_info)

                except Exception as e:
                    print(f"    Error reading object: {e}")

            # Save results
            reports_dir = Path(__file__).parent.parent.parent / "reports"
            reports_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_file = reports_dir / f"opcua_browse_{timestamp}.json"

            with open(report_file, 'w') as f:
                json.dump(results, f, indent=2)

            print(f"\n[*] Browse results saved to: {report_file}")
            print("[*] Read-only OPC UA reconnaissance complete")

    except Exception as e:
        print(f"[!] Connection failed: {e}")
        print(f"[*] Make sure the OPC UA server is running on {target_url}")


if __name__ == "__main__":
    asyncio.run(opcua_anonymous_browse())
