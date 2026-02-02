# components/protocols/modbus/modbus_tcp_endpoint.py
"""
Modbus TCP Server using PyModbus 3.11.4 simulator.

Opens a REAL network port. External tools can connect and interact.
Based on pymodbus_3114.py - the working pymodbus async simulator.
"""

import asyncio
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.datastore import ModbusServerContext
from pymodbus.datastore.simulator import ModbusSimulatorContext
from pymodbus.server import StartAsyncTcpServer


class ModbusTCPServer:
    """
    Modbus TCP server using pymodbus simulator.

    Opens a real network port that external tools can connect to.
    Syncs with device memory_map each scan cycle.
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 502,
        unit_id: int = 1,
        num_coils: int = 64,
        num_discrete_inputs: int = 64,
        num_holding_registers: int = 64,
        num_input_registers: int = 64,
    ):
        self.host = host
        self.port = port
        self.unit_id = unit_id

        # Memory sizes
        self.num_coils = num_coils
        self.num_discrete_inputs = num_discrete_inputs
        self.num_holding_registers = num_holding_registers
        self.num_input_registers = num_input_registers

        # Server components
        self._simulator: ModbusSimulatorContext | None = None
        self._context: ModbusServerContext | None = None
        self._server_task: asyncio.Task | None = None
        self._client: AsyncModbusTcpClient | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> bool:
        """Start Modbus TCP server."""
        if self._running:
            return True

        max_size = max(
            self.num_coils,
            self.num_discrete_inputs,
            self.num_holding_registers,
            self.num_input_registers,
        )

        config = {
            "setup": {
                "co size": self.num_coils,
                "di size": self.num_discrete_inputs,
                "hr size": self.num_holding_registers,
                "ir size": self.num_input_registers,
                "shared blocks": True,
                "type exception": False,
                "defaults": {
                    "value": {
                        "bits": 0,
                        "uint16": 0,
                        "uint32": 0,
                        "float32": 0.0,
                        "string": " ",
                    },
                    "action": {
                        "bits": None,
                        "uint16": None,
                        "uint32": None,
                        "float32": None,
                        "string": None,
                    },
                },
            },
            "invalid": [],
            "write": [[0, max_size - 1]] if max_size > 0 else [],
            "uint16": [{"addr": [0, max_size - 1], "value": 0}] if max_size > 0 else [],
            "bits": [],
            "uint32": [],
            "float32": [],
            "string": [],
            "repeat": [],
        }

        self._simulator = ModbusSimulatorContext(config=config, custom_actions=None)
        self._context = ModbusServerContext(self._simulator, single=True)

        # Create server task with exception callback
        self._server_task = asyncio.create_task(
            StartAsyncTcpServer(
                context=self._context,
                address=(self.host, self.port),
            )
        )

        # Add callback to catch unhandled exceptions
        def _handle_server_exception(task):
            try:
                task.result()
            except asyncio.CancelledError:
                pass  # Expected during shutdown
            except Exception:
                pass  # Server errors are logged by pymodbus

        self._server_task.add_done_callback(_handle_server_exception)

        # Give server time to bind
        await asyncio.sleep(0.5)

        # Create internal client for sync operations
        self._client = AsyncModbusTcpClient(host=self.host, port=self.port)
        self._client.unit_id = self.unit_id
        await self._client.connect()

        self._running = True
        return True

    async def stop(self) -> None:
        """Stop Modbus TCP server."""
        if self._client:
            self._client.close()
            self._client = None

        if self._server_task and not self._server_task.done():
            self._server_task.cancel()
            try:
                await asyncio.wait_for(self._server_task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError, RuntimeError, Exception):
                # Suppress all exceptions during shutdown - server is stopping anyway
                pass
            self._server_task = None
            await asyncio.sleep(0.1)  # Let OS release port

        self._running = False
        self._simulator = None
        self._context = None

    # ------------------------------------------------------------------
    # Direct access for external tools testing
    # ------------------------------------------------------------------

    async def read_coils(self, address: int, count: int = 1):
        """Read coils (for testing)."""
        if not self._client:
            raise RuntimeError("Server not running")
        return await self._client.read_coils(address, count=count)

    async def read_holding_registers(self, address: int, count: int = 1):
        """Read holding registers (for testing)."""
        if not self._client:
            raise RuntimeError("Server not running")
        return await self._client.read_holding_registers(address, count=count)

    async def write_coil(self, address: int, value: bool):
        """Write coil (for testing)."""
        if not self._client:
            raise RuntimeError("Server not running")
        return await self._client.write_coil(address, value)

    async def write_register(self, address: int, value: int):
        """Write holding register (for testing)."""
        if not self._client:
            raise RuntimeError("Server not running")
        return await self._client.write_register(address, value)

    def get_info(self) -> dict[str, Any]:
        """Get server info."""
        return {
            "protocol": "modbus_tcp",
            "host": self.host,
            "port": self.port,
            "unit_id": self.unit_id,
            "running": self._running,
        }

    # ------------------------------------------------------------------
    # Sync methods for SimulatorManager (device ↔ server)
    # ------------------------------------------------------------------

    async def sync_from_device(self, device_registers: dict[int, Any], register_type: str) -> None:
        """
        Write device registers to server (device → server telemetry).

        Args:
            device_registers: Dict of {address: value} from device
            register_type: "input_registers" or "discrete_inputs"
        """
        if not self._client:
            return

        if register_type == "input_registers":
            # Input registers are read-only from client perspective
            # We use write_register which actually writes to holding registers
            # Then we'll need to use the context directly
            for address, value in device_registers.items():
                if self._context:
                    # Access simulator context directly to write input registers
                    slave = self._context[self.unit_id]
                    slave.setValues(4, address, [int(value)])  # Function code 4 = input registers

        elif register_type == "discrete_inputs":
            for address, value in device_registers.items():
                if self._context:
                    # Access simulator context directly to write discrete inputs
                    slave = self._context[self.unit_id]
                    slave.setValues(2, address, [bool(value)])  # Function code 2 = discrete inputs

    async def sync_to_device(self, address: int, count: int, register_type: str) -> dict[int, Any]:
        """
        Read server registers to sync back to device (server → device commands).

        Args:
            address: Starting address
            count: Number of registers to read
            register_type: "coils" or "holding_registers"

        Returns:
            Dict of {address: value}
        """
        if not self._client:
            return {}

        result = {}

        if register_type == "coils":
            response = await self.read_coils(address, count)
            if hasattr(response, "bits"):
                for i, value in enumerate(response.bits[:count]):
                    result[address + i] = bool(value)

        elif register_type == "holding_registers":
            response = await self.read_holding_registers(address, count)
            if hasattr(response, "registers"):
                for i, value in enumerate(response.registers[:count]):
                    result[address + i] = int(value)

        return result
