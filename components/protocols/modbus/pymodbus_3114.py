# protocols/modbus/pymodbus_3114.py
"""
Modbus TCP adapter using pymodbus 3.11.4

Transport-only adapter.
No device state.
No simulator.
No protocol semantics.
"""

from pymodbus.client import AsyncModbusTcpClient


class PyModbus3114Adapter:
    def __init__(
        self,
        host: str,
        port: int,
        device_id: int,
    ):
        self.host = host
        self.port = port
        self.device_id = device_id

        self.client: AsyncModbusTcpClient | None = None
        self.connected: bool = False

    # ------------------------------------------------------------------
    # Client lifecycle
    # ------------------------------------------------------------------
    async def connect(self) -> bool:
        if not self.client:
            self.client = AsyncModbusTcpClient(host=self.host, port=self.port)
            self.client.unit_id = self.device_id

        if not self.connected:
            self.connected = await self.client.connect()

        return self.connected

    async def disconnect(self) -> None:
        if self.client:
            self.client.close()
            self.client = None

        self.connected = False

    # ------------------------------------------------------------------
    # Modbus TCP primitives (no semantics)
    # ------------------------------------------------------------------
    async def read_coils(self, address: int, count: int = 1):
        if not self.client:
            raise RuntimeError("Client not connected")
        return await self.client.read_coils(address, count=count)

    async def read_discrete_inputs(self, address: int, count: int = 1):
        if not self.client:
            raise RuntimeError("Client not connected")
        return await self.client.read_discrete_inputs(address, count=count)

    async def read_holding_registers(self, address: int, count: int = 1):
        if not self.client:
            raise RuntimeError("Client not connected")
        return await self.client.read_holding_registers(address, count=count)

    async def read_input_registers(self, address: int, count: int = 1):
        if not self.client:
            raise RuntimeError("Client not connected")
        return await self.client.read_input_registers(address, count=count)

    async def write_coil(self, address: int, value: bool):
        if not self.client:
            raise RuntimeError("Client not connected")
        return await self.client.write_coil(address, value)

    async def write_register(self, address: int, value: int):
        if not self.client:
            raise RuntimeError("Client not connected")
        return await self.client.write_register(address, value)

    async def write_multiple_coils(self, address: int, values: list[bool]):
        if not self.client:
            raise RuntimeError("Client not connected")
        return await self.client.write_coils(address, values)

    async def write_multiple_registers(self, address: int, values: list[int]):
        if not self.client:
            raise RuntimeError("Client not connected")
        return await self.client.write_registers(address, values)

    # ------------------------------------------------------------------
    # Transport-level introspection only
    # ------------------------------------------------------------------
    async def probe(self) -> dict:
        return {
            "transport": "modbus-tcp",
            "host": self.host,
            "port": self.port,
            "device_id": self.device_id,
            "connected": self.connected,
        }
