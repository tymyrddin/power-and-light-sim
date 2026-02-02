"""
Async DNP3 adapter using the real dnp3py API.

Supports:
- Outstation (server)
- Master (client)
- Async database updates
"""

import asyncio
from collections import defaultdict

from dnp3.database import AnalogInputConfig, BinaryInputConfig, CounterConfig, Database
from dnp3.master import DefaultSOEHandler, Master
from dnp3.outstation import Outstation
from dnp3.transport_io import TcpClientChannel, TcpConfig, TcpServer, TcpServerConfig


class DNP3Adapter:
    def __init__(
        self,
        mode: str = "outstation",  # "outstation" or "master"
        host: str = "0.0.0.0",
        port: int = 20000,
        simulator_mode: bool = True,
        setup: dict | None = None,
    ):
        self.mode = mode
        self.host = host
        self.port = port
        self.simulator_mode = simulator_mode

        self.setup = setup or {
            "binary_inputs": {},
            "analog_inputs": {},
            "counters": {},
        }

        self.connected = False
        self.received_data = defaultdict(dict)

        self.database: Database | None = None
        self.outstation: Outstation | None = None
        self.server: TcpServer | None = None

        self.master: Master | None = None
        self.client_channel: TcpClientChannel | None = None

    # ------------------------------------------------------------------
    # Outstation (server) lifecycle
    # ------------------------------------------------------------------
    async def start_outstation(self) -> None:
        if self.outstation:
            return

        # create and populate database in thread
        self.database = Database()
        for idx, val in self.setup["binary_inputs"].items():
            self.database.add_binary_input(idx, BinaryInputConfig())
            await asyncio.to_thread(self.database.update_binary_input, idx, val)

        for idx, val in self.setup["analog_inputs"].items():
            self.database.add_analog_input(idx, AnalogInputConfig())
            await asyncio.to_thread(self.database.update_analog_input, idx, val)

        for idx, val in self.setup["counters"].items():
            self.database.add_counter(idx, CounterConfig())
            await asyncio.to_thread(self.database.update_counter, idx, val)

        self.outstation = Outstation(database=self.database)

        # start TCP server (async) - pass host and port as keyword arguments
        server_config = TcpServerConfig(host=self.host, port=self.port)
        self.server = TcpServer(server_config)
        await self.server.start()
        self.connected = True

    async def stop_outstation(self) -> None:
        if self.server:
            await self.server.stop()
        self.server = None
        self.outstation = None
        self.database = None
        self.connected = False

    # ------------------------------------------------------------------
    # Master (client) lifecycle
    # ------------------------------------------------------------------
    async def start_master(self) -> None:
        if self.master:
            return

        self.master = Master(handler=DefaultSOEHandler())
        client_config = TcpConfig(host=self.host, port=self.port)
        self.client_channel = TcpClientChannel(client_config)

        # In simulator mode, don't attempt real TCP connections
        # Tests and simulations don't need actual network connectivity
        if self.simulator_mode:
            self.connected = True
        else:
            # Only attempt real connection in non-simulator mode
            await self.client_channel.open()
            self.connected = True

    async def stop_master(self) -> None:
        if self.client_channel:
            await self.client_channel.close()
        self.master = None
        self.client_channel = None
        self.connected = False

    # ------------------------------------------------------------------
    # Generic connect/disconnect
    # ------------------------------------------------------------------
    async def connect(self) -> bool:
        if self.mode == "outstation":
            await self.start_outstation()
        else:
            await self.start_master()
        return self.connected

    async def disconnect(self) -> None:
        if self.mode == "outstation":
            await self.stop_outstation()
        else:
            await self.stop_master()

    # ------------------------------------------------------------------
    # Master operations (placeholders)
    # ------------------------------------------------------------------
    async def integrity_scan(self) -> bool:
        if not self.master or not self.client_channel:
            raise RuntimeError("Master not connected")
        # TODO: Implement integrity scan when dnp3py provides helper
        return False

    async def event_scan(self) -> bool:
        if not self.master or not self.client_channel:
            raise RuntimeError("Master not connected")
        # TODO: Implement event scan when dnp3py provides helper
        return False

    async def read_binary_inputs(self, start: int, count: int) -> list:
        """Read binary inputs (master mode)."""
        if not self.master or not self.client_channel:
            raise RuntimeError("Master not connected")
        # TODO: Implement when dnp3py provides helper
        return []

    async def read_analog_inputs(self, start: int, count: int) -> list:
        """Read analog inputs (master mode)."""
        if not self.master or not self.client_channel:
            raise RuntimeError("Master not connected")
        # TODO: Implement when dnp3py provides helper
        return []

    async def write_binary_output(self, index: int, value: bool) -> bool:
        """Write binary output command."""
        if not self.master or not self.client_channel:
            raise RuntimeError("Master not connected")
        # TODO: Implement using index and value when dnp3py provides helper
        _ = (index, value)  # Will be used in actual implementation
        return False

    async def write_analog_output(self, index: int, value: float) -> bool:
        """Write analogue output command."""
        if not self.master or not self.client_channel:
            raise RuntimeError("Master not connected")
        # TODO: Implement using index and value when dnp3py provides helper
        _ = (index, value)  # Will be used in actual implementation
        return False

    # ------------------------------------------------------------------
    # Outstation updates
    # ------------------------------------------------------------------
    async def update_binary_input(self, index: int, value: bool) -> None:
        if not self.database:
            raise RuntimeError("Outstation not started")
        await asyncio.to_thread(self.database.update_binary_input, index, value)
        self.setup["binary_inputs"][index] = value

    async def update_analog_input(self, index: int, value: float) -> None:
        if not self.database:
            raise RuntimeError("Outstation not started")
        await asyncio.to_thread(self.database.update_analog_input, index, value)
        self.setup["analog_inputs"][index] = value

    async def update_counter(self, index: int, value: int) -> None:
        if not self.database:
            raise RuntimeError("Outstation not started")
        await asyncio.to_thread(self.database.update_counter, index, value)
        self.setup["counters"][index] = value

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    async def probe(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "host": self.host,
            "port": self.port,
            "simulator": self.simulator_mode,
            "connected": self.connected,
            "setup": self.setup,
        }
