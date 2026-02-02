"""
ICS Protocol Servers.

Protocol servers for industrial control systems that open REAL network ports.
External tools (pen-testing tools, SCADA clients) can connect and interact.

Structure:
    components/protocols/
    ├── modbus/
    │   ├── modbus_tcp_endpoint.py           # ModbusTCPServer (port 502)
    │   └── modbus_rtu_endpoint.py           # ModbusRTUServer (serial)
    ├── iec104/
    │   └── server.py        # IEC104Server (port 2404)
    ├── s7/
    │   └── server.py        # S7Server (port 102)
    ├── dnp3/
    │   └── server.py        # DNP3Server (TODO)
    ├── opcua/
    │   └── server.py        # OPCUAServer (TODO)
    └── iec61850/
        ├── mms.py           # IEC61850MMS (TODO)
        └── goose.py         # IEC61850GOOSE (TODO)

Usage:
    from components.protocols import ModbusTCPServer, IEC104Server, S7Server

    # Create server
    modbus = ModbusTCPServer(host="0.0.0.0", port=10502)
    await modbus.start()

    # Sync with device each scan cycle
    await modbus.sync_from_device(device.memory_map)  # Push state to network
    await modbus.sync_to_device(device.memory_map)    # Pull commands from network
"""

__all__: list[str] = []

# Modbus
try:
    from components.protocols.modbus import ModbusRTUServer, ModbusTCPServer

    __all__.extend(["ModbusTCPServer", "ModbusRTUServer"])
except ImportError:
    pass

# IEC 104
try:
    from components.protocols.iec104 import IEC104Server

    __all__.append("IEC104Server")
except ImportError:
    pass

# S7
try:
    from components.protocols.s7 import S7Server

    __all__.append("S7Server")
except ImportError:
    pass
