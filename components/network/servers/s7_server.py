# components/network/servers/s7_server.py
"""
Siemens S7 TCP Server - ICS Attack Surface

Opens a REAL network port that external attack tools can target.
Implements S7 protocol server functionality for demonstrating ICS attacks.

External Attack Tools:
- s7-client tools: Read/write S7 data blocks
- nmap: Port scanning and S7 service detection
- Metasploit: exploit/scada/s7_300_400_plc_control
- python-snap7: snap7.client for custom attacks
- Custom scripts: s7-python library

Example Attack from Terminal:
    # Reconnaissance
    $ nmap -p 102 -sV localhost

    # Read data block
    $ python -c "import snap7; c=snap7.client.Client(); c.connect('127.0.0.1',0,2); print(c.db_read(1,0,10))"

    # Stop PLC
    $ python -c "import snap7; c=snap7.client.Client(); c.connect('127.0.0.1',0,2); c.plc_stop()"

Based on snap7 library server functionality.
"""

import asyncio
import logging
from ctypes import c_uint8
from typing import Any

try:
    import snap7
    from snap7 import SrvArea
    from snap7.server import Server as Snap7Server
    from snap7.util import get_bool, get_int, set_bool, set_int
    SNAP7_AVAILABLE = True
except ImportError:
    SNAP7_AVAILABLE = False
    Snap7Server = None
    SrvArea = None
    c_uint8 = None

logger = logging.getLogger(__name__)

# snap7 server status codes (from snap7.server.server_statuses)
SRV_STOPPED = 0
SRV_RUNNING = 1
SRV_ERROR = 2


class S7TCPServer:
    """
    S7 TCP server using snap7 library.

    Opens a real network port (default 102) that external tools can connect to.
    Implements Siemens S7 protocol for PLC communication and attack simulation.

    Memory layout uses Data Blocks (DBs):
    - DB1: Input registers (read-only telemetry from PLC)
    - DB2: Holding registers (read-write setpoints)
    - DB3: Discrete inputs (read-only bits)
    - DB4: Coils (read-write bits/commands)
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 102,
        rack: int = 0,
        slot: int = 2,
        # DB sizes (bytes)
        db1_size: int = 256,  # Input registers
        db2_size: int = 256,  # Holding registers
        db3_size: int = 64,   # Discrete inputs
        db4_size: int = 64,   # Coils
    ):
        self.host = host
        self.port = port
        self.rack = rack
        self.slot = slot

        # DB configuration
        self.db_sizes = {
            1: db1_size,   # Input registers
            2: db2_size,   # Holding registers
            3: db3_size,   # Discrete inputs
            4: db4_size,   # Coils
        }

        # Server components
        self._server: Snap7Server | None = None
        self._running = False

        # Memory buffers (allocated when server starts)
        # Note: snap7 requires ctypes arrays, not Python bytearrays
        self._db_buffers: dict[int, Any] = {}

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> bool:
        """Start S7 TCP server with retry logic for port binding."""
        if not SNAP7_AVAILABLE:
            logger.error(
                "snap7 library not available - S7 server cannot start. "
                "Install with: pip install python-snap7"
            )
            return False

        if self._running:
            return True

        # Retry logic for port binding (handles TIME_WAIT from previous runs)
        max_retries = 3
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                # Create snap7 server
                self._server = Snap7Server()

                # Allocate memory for each DB
                # Note: snap7 requires ctypes arrays for register_area
                for db_num, size in self.db_sizes.items():
                    self._db_buffers[db_num] = (c_uint8 * size)()
                    # Register DB with snap7 server
                    self._server.register_area(
                        SrvArea.DB,              # Area type: Data Block
                        db_num,                  # DB number
                        self._db_buffers[db_num] # Memory buffer (ctypes array)
                    )

                # Start server in background thread
                def _start_server():
                    # Note: snap7 library binds to port 102 (privileged) and doesn't support
                    # custom ports without recompiling the library. Requires root or CAP_NET_BIND_SERVICE.
                    # start() takes no arguments - port is hardcoded in snap7 library.
                    self._server.start()
                    return self._server.get_status() == SRV_RUNNING

                # Await the server start and check result
                started = await asyncio.to_thread(_start_server)

                # Check if server started successfully
                if started and self._server and self._server.get_status() == SRV_RUNNING:
                    self._running = True
                    logger.info(f"S7 server started on {self.host}:{self.port}")
                    return True

                # Server didn't start, cleanup and retry
                if self._server:
                    try:
                        self._server.stop()
                    except Exception:
                        pass
                    self._server = None

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))  # Exponential backoff

            except Exception as e:
                logger.warning(
                    f"Failed to start S7 server on {self.host}:{self.port} "
                    f"(attempt {attempt + 1}/{max_retries}): {e}"
                )

                # Cleanup on error
                if self._server:
                    try:
                        self._server.stop()
                    except Exception:
                        pass
                    self._server = None
                    self._db_buffers.clear()

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    logger.error(
                        f"Failed to start S7 server on {self.host}:{self.port} "
                        f"after {max_retries} attempts"
                    )
                    return False

        return False

    async def stop(self) -> None:
        """Stop S7 TCP server and release port."""
        if not self._running:
            return

        # Stop snap7 server
        if self._server:
            try:
                await asyncio.to_thread(self._server.stop)
            except Exception as e:
                logger.debug(f"Error stopping S7 server: {e}")
            self._server = None

        # Clear buffers
        self._db_buffers.clear()

        # Give OS time to release port
        await asyncio.sleep(0.3)

        self._running = False

    # ------------------------------------------------------------------
    # Device sync methods (similar to ModbusTCPServer)
    # ------------------------------------------------------------------

    async def sync_from_device(self, device_registers: dict[int, Any], register_type: str) -> None:
        """
        Write device registers to S7 server (device → server telemetry).

        Args:
            device_registers: Dict of {address: value} from device
            register_type: "input_registers" or "discrete_inputs"
        """
        if not self._running or not self._server:
            return

        try:
            if register_type == "input_registers":
                # Write to DB1 (input registers): 2 bytes per register
                db_buffer = self._db_buffers[1]
                for address, value in device_registers.items():
                    byte_offset = address * 2
                    if byte_offset + 1 < len(db_buffer):
                        set_int(db_buffer, byte_offset, int(value))

            elif register_type == "discrete_inputs":
                # Write to DB3 (discrete inputs): 1 bit per input
                db_buffer = self._db_buffers[3]
                for address, value in device_registers.items():
                    byte_idx = address // 8
                    bit_idx = address % 8
                    if byte_idx < len(db_buffer):
                        set_bool(db_buffer, byte_idx, bit_idx, bool(value))

        except Exception as e:
            logger.debug(f"Error syncing from device to S7 server: {e}")

    async def sync_to_device(self, address: int, count: int, register_type: str) -> dict[int, Any]:
        """
        Read S7 server registers to sync back to device (server → device commands).

        Args:
            address: Starting address
            count: Number of registers to read
            register_type: "coils" or "holding_registers"

        Returns:
            Dict of {address: value}
        """
        if not self._running or not self._server:
            return {}

        result = {}

        try:
            if register_type == "coils":
                # Read from DB4 (coils)
                db_buffer = self._db_buffers[4]
                for i in range(count):
                    addr = address + i
                    byte_idx = addr // 8
                    bit_idx = addr % 8
                    if byte_idx < len(db_buffer):
                        result[addr] = get_bool(db_buffer, byte_idx, bit_idx)

            elif register_type == "holding_registers":
                # Read from DB2 (holding registers)
                db_buffer = self._db_buffers[2]
                for i in range(count):
                    addr = address + i
                    byte_offset = addr * 2
                    if byte_offset + 1 < len(db_buffer):
                        result[addr] = get_int(db_buffer, byte_offset)

        except Exception as e:
            logger.debug(f"Error syncing to device from S7 server: {e}")

        return result

    # ------------------------------------------------------------------
    # Attack primitives (exposed for external tool access)
    # ------------------------------------------------------------------

    async def read_db(self, db_number: int, start: int, size: int) -> bytes:
        """Read bytes from a Data Block (for testing/attacks)."""
        if not self._running or db_number not in self._db_buffers:
            raise RuntimeError(f"S7 server not running or DB{db_number} not available")

        db_buffer = self._db_buffers[db_number]
        if start + size > len(db_buffer):
            raise ValueError(f"Read beyond DB{db_number} bounds")

        return bytes(db_buffer[start:start + size])

    async def write_db(self, db_number: int, start: int, data: bytes) -> None:
        """Write bytes to a Data Block (for testing/attacks)."""
        if not self._running or db_number not in self._db_buffers:
            raise RuntimeError(f"S7 server not running or DB{db_number} not available")

        db_buffer = self._db_buffers[db_number]
        if start + len(data) > len(db_buffer):
            raise ValueError(f"Write beyond DB{db_number} bounds")

        db_buffer[start:start + len(data)] = data

    def get_info(self) -> dict[str, Any]:
        """Get server info."""
        return {
            "protocol": "s7",
            "host": self.host,
            "port": self.port,
            "rack": self.rack,
            "slot": self.slot,
            "running": self._running,
            "db_sizes": self.db_sizes,
        }
