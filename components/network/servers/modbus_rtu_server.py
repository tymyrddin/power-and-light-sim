# components/network/servers/modbus_rtu_server.py
"""
Modbus RTU Server - Serial Attack Surface

Opens a REAL serial port that external tools can target.
Simulates RTU devices accessible via serial/RS-485.

External Attack Tools:
- mbtget with serial port: Read/write Modbus RTU
- Custom Python: pymodbus ModbusSerialClient

Based on pymodbus 3.11.4 async simulator.
"""

import asyncio
from typing import Any

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.datastore import ModbusServerContext
from pymodbus.datastore.simulator import ModbusSimulatorContext
from pymodbus.server import StartAsyncSerialServer


class ModbusRTUServer:
    """
    Modbus RTU server using pymodbus simulator.

    Opens a real serial port that external tools can connect to.
    Syncs with device memory_map each scan cycle.
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        unit_id: int = 1,
        baudrate: int = 9600,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: int = 1,
        num_coils: int = 64,
        num_discrete_inputs: int = 64,
        num_holding_registers: int = 64,
        num_input_registers: int = 64,
    ):
        self.port = port
        self.unit_id = unit_id
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits

        # Memory sizes
        self.num_coils = num_coils
        self.num_discrete_inputs = num_discrete_inputs
        self.num_holding_registers = num_holding_registers
        self.num_input_registers = num_input_registers

        # Server components
        self._simulator: ModbusSimulatorContext | None = None
        self._context: ModbusServerContext | None = None
        self._server_task: asyncio.Task | None = None
        self._client: AsyncModbusSerialClient | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> bool:
        """Start Modbus RTU server with retry logic."""
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

        # Retry logic for serial port access
        max_retries = 3
        retry_delay = 0.3

        for attempt in range(max_retries):
            try:
                self._server_task = asyncio.create_task(
                    StartAsyncSerialServer(
                        context=self._context,
                        port=self.port,
                        baudrate=self.baudrate,
                        bytesize=self.bytesize,
                        parity=self.parity,
                        stopbits=self.stopbits,
                    )
                )

                # Give server time to open serial port
                await asyncio.sleep(retry_delay)

                # Create internal client for sync operations and verify connection
                self._client = AsyncModbusSerialClient(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                )
                self._client.unit_id = self.unit_id
                connected = await self._client.connect()

                if connected:
                    self._running = True
                    return True

                # Connection failed, cleanup and retry
                if self._server_task and not self._server_task.done():
                    self._server_task.cancel()
                    try:
                        await asyncio.wait_for(self._server_task, timeout=1.0)
                    except (asyncio.CancelledError, TimeoutError):
                        pass

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))

            except Exception as e:
                # Cleanup on error
                if self._client:
                    self._client.close()
                    self._client = None
                if self._server_task and not self._server_task.done():
                    self._server_task.cancel()
                    try:
                        await asyncio.wait_for(self._server_task, timeout=1.0)
                    except (asyncio.CancelledError, TimeoutError):
                        pass
                    self._server_task = None

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    raise RuntimeError(
                        f"Failed to start Modbus RTU server on {self.port} after {max_retries} attempts: {e}"
                    ) from e

        raise RuntimeError(
            f"Failed to start Modbus RTU server on {self.port} - client connection failed"
        )

    async def stop(self) -> None:
        """Stop Modbus RTU server and release serial port."""
        # Close client connection first
        if self._client:
            self._client.close()
            self._client = None

        # Cancel and wait for server task to finish
        if self._server_task and not self._server_task.done():
            self._server_task.cancel()
            try:
                await asyncio.wait_for(self._server_task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError):
                pass
            self._server_task = None

        # Give OS time to release serial port
        await asyncio.sleep(0.3)

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

    async def read_discrete_inputs(self, address: int, count: int = 1):
        """Read discrete inputs (for testing)."""
        if not self._client:
            raise RuntimeError("Server not running")
        return await self._client.read_discrete_inputs(address, count=count)

    async def read_holding_registers(self, address: int, count: int = 1):
        """Read holding registers (for testing)."""
        if not self._client:
            raise RuntimeError("Server not running")
        return await self._client.read_holding_registers(address, count=count)

    async def read_input_registers(self, address: int, count: int = 1):
        """Read input registers (for testing)."""
        if not self._client:
            raise RuntimeError("Server not running")
        return await self._client.read_input_registers(address, count=count)

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
            "protocol": "modbus_rtu",
            "port": self.port,
            "unit_id": self.unit_id,
            "baudrate": self.baudrate,
            "running": self._running,
        }
