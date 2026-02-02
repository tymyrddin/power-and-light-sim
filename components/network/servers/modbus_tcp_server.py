# components/network/servers/modbus_tcp_server.py
"""
Modbus TCP Server - ICS Attack Surface

Opens a REAL network port that external attack tools can target.
This is a network-accessible attack surface for demonstrating ICS attacks.

External Attack Tools:
- mbtget: Modbus TCP client for read/write operations
- nmap: Port scanning and service detection
- Metasploit: exploit/scada/modbusdetect, modbus_write
- Custom Python: pymodbus AsyncModbusTcpClient

Example Attack from Terminal:
    # Reconnaissance
    $ nmap -p 10500-10600 localhost
    $ mbtget -r -a 0 -n 10 localhost:10502

    # Malicious write
    $ mbtget -w -a 1 -v 1 localhost:10502  # Trigger emergency trip

Based on pymodbus 3.11.4 async simulator.
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
        """Start Modbus TCP server with retry logic for port binding."""
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

        # Retry logic for port binding (handles TIME_WAIT from previous runs)
        max_retries = 3
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                # Create server task
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
                    except OSError as e:
                        if "Address already in use" not in str(e):
                            # Only suppress "address already in use" - log others
                            import logging
                            logging.getLogger(__name__).warning(
                                f"Modbus server error on {self.host}:{self.port}: {e}"
                            )
                    except Exception as e:
                        # Log unexpected errors
                        import logging
                        logging.getLogger(__name__).error(
                            f"Unexpected Modbus server error on {self.host}:{self.port}: {e}"
                        )

                self._server_task.add_done_callback(_handle_server_exception)

                # Give server time to bind
                await asyncio.sleep(retry_delay)

                # Create internal client for sync operations and verify connection
                self._client = AsyncModbusTcpClient(host=self.host, port=self.port)
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
                    await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff

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
                        f"Failed to start Modbus TCP server on {self.host}:{self.port} after {max_retries} attempts: {e}"
                    )

        raise RuntimeError(
            f"Failed to start Modbus TCP server on {self.host}:{self.port} - client connection failed"
        )

    async def stop(self) -> None:
        """Stop Modbus TCP server and release port."""
        # Close client connection first
        if self._client:
            self._client.close()
            self._client = None

        # Cancel and wait for server task to finish
        if self._server_task and not self._server_task.done():
            self._server_task.cancel()
            try:
                await asyncio.wait_for(self._server_task, timeout=2.0)
            except (TimeoutError, asyncio.CancelledError, RuntimeError, Exception):
                # Suppress all exceptions during shutdown - server is stopping anyway
                pass
            self._server_task = None

        # Give OS more time to release port (helps avoid TIME_WAIT conflicts)
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
