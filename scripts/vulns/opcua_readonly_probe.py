#!/usr/bin/env python3
"""
OPC UA Anonymous Browse
Read-only reconnaissance of OPC UA server object hierarchy.
Tests against UU P&L simulator SCADA server on port 4840.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from asyncua import Client


async def opcua_anonymous_browse():
    target_url = "opc.tcp://127.0.0.1:4840"

    print("[*] OPC UA Anonymous Browse")
    print(f"[*] Target: {target_url}")
    print(f"[*] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)

    client = Client(target_url)

    try:
        async with client:
            print("[*] Connected successfully")

            # Read server status using standard node IDs
            try:
                # ServerStatus node (ns=0;i=2256)
                from asyncua import ua
                server_status_node = client.get_node(ua.NodeId(2256, 0))

                # Read individual status attributes
                state_node = client.get_node(ua.NodeId(2259, 0))  # ServerState
                current_time_node = client.get_node(ua.NodeId(2258, 0))  # CurrentTime

                state = await state_node.read_value()
                current_time = await current_time_node.read_value()

                print("\n[*] Server Status:")
                print(f"    State: {state}")
                print(f"    Current Time: {current_time}")

            except Exception as e:
                print(f"\n[!] Could not read server status: {e}")

            # Browse root objects
            print("\n[*] Browsing Root Objects:")
            root = client.get_root_node()
            objects = await root.get_children()

            results = {
                "timestamp": datetime.now().isoformat(),
                "server_url": target_url,
                "server_state": str(state) if 'state' in locals() else "Unknown",
                "objects": [],
            }

            for obj in objects:
                try:
                    browse_name = await obj.read_browse_name()
                    display_name = await obj.read_display_name()
                    node_class = await obj.read_node_class()

                    obj_info = {
                        "browse_name": browse_name.Name,
                        "display_name": display_name.Text,
                        "node_class": str(node_class),
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

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = reports_dir / f"opcua_browse_{timestamp}.json"

            with open(report_file, "w") as f:
                json.dump(results, f, indent=2)

            print(f"\n[*] Browse results saved to: {report_file}")
            print("[*] Read-only OPC UA reconnaissance complete")

    except Exception as e:
        print(f"[!] Connection failed: {e}")
        print(f"[*] Make sure the OPC UA server is running on {target_url}")


if __name__ == "__main__":
    asyncio.run(opcua_anonymous_browse())
