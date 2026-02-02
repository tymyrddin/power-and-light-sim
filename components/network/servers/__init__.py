# components/network/servers/__init__.py
"""
Network protocol servers - ICS attack surfaces.

These servers open REAL network ports that external attack tools can target.
Used for demonstrating realistic ICS attack scenarios.

Attack Tools That Can Connect:
- mbtget: Modbus TCP client
- nmap: Port scanning
- Metasploit: SCADA exploits
- Custom Python: pymodbus, python-snap7

Example Attack:
    # Terminal 1: Run simulation
    $ python tools/simulator_manager.py

    # Terminal 2: Attack Modbus device
    $ mbtget -r -a 0 -n 10 localhost:10502
    $ mbtget -w -a 1 -v 1 localhost:10502  # Trigger trip
"""

from components.network.servers.modbus_rtu_server import ModbusRTUServer
from components.network.servers.modbus_tcp_server import ModbusTCPServer
from components.network.servers.s7_server import S7TCPServer
from components.network.servers.dnp3_server import DNP3TCPServer
from components.network.servers.iec104_server import IEC104TCPServer
from components.network.servers.opcua_server import OPCUAServer

__all__ = [
    "ModbusTCPServer",
    "ModbusRTUServer",
    "S7TCPServer",
    "DNP3TCPServer",
    "IEC104TCPServer",
    "OPCUAServer",
]
