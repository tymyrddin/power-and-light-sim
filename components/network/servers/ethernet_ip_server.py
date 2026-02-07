# components/network/servers/ethernet_ip_server.py
"""
EtherNet/IP (CIP) Server - Allen-Bradley Protocol Simulation

Opens a REAL network port (44818) that external attack tools can target.
Implements EtherNet/IP (Common Industrial Protocol) for Allen-Bradley PLCs.

External Attack Tools:
- pycomm3: Read/write tags on ControlLogix/CompactLogix
- cpppo: EtherNet/IP client for custom attacks
- nmap: Port scanning and EtherNet/IP service detection
- Wireshark: Protocol analysis (filter: enip or cip)

Example Attack from Terminal:
    # Tag enumeration
    $ python -c "from pycomm3 import LogixDriver; plc=LogixDriver('127.0.0.1'); plc.open(); print(plc.get_tag_list())"

    # Read tag value
    $ python -c "from pycomm3 import LogixDriver; plc=LogixDriver('127.0.0.1'); plc.open(); print(plc.read('SpeedSetpoint'))"

    # Write tag value
    $ python -c "from pycomm3 import LogixDriver; plc=LogixDriver('127.0.0.1'); plc.open(); plc.write('SpeedSetpoint', 2000)"

Based on cpppo library server functionality.
"""

import asyncio
import struct
from typing import Any

# import logging
from components.security.logging_system import get_logger

try:
    import cpppo
    from cpppo.server.enip import parser as enip_parser
    from cpppo.server.enip.get_attribute import proxy

    CPPPO_AVAILABLE = True
except ImportError:
    CPPPO_AVAILABLE = False
    proxy = None

logger = get_logger(__name__)


class EtherNetIPServer:
    """
    EtherNet/IP (CIP) server for Allen-Bradley protocol simulation.

    Opens a real network port (default 44818) that external tools can connect to.
    Implements tag-based addressing similar to Allen-Bradley ControlLogix PLCs.

    Tag structure maps to device registers:
    - SpeedSetpoint: Holding Register 0 (DINT - 32-bit int)
    - PowerSetpoint: Holding Register 1 (DINT - 32-bit int)
    - CurrentSpeed: Input Register 0 (DINT - read-only)
    - CurrentPower: Input Register 1 (DINT - read-only)
    - BearingTemp: Input Register 2 (INT - 16-bit)
    - OilPressure: Input Register 3 (INT - 16-bit)
    - Vibration: Input Register 4 (INT - 16-bit)
    - GeneratorTemp: Input Register 5 (INT - 16-bit)
    - GearboxTemp: Input Register 6 (INT - 16-bit)
    - AmbientTemp: Input Register 7 (INT - 16-bit)
    - ControlMode: Coil 0 (BOOL)
    - EmergencyStop: Coil 1 (BOOL)
    - MaintenanceMode: Coil 2 (BOOL)
    - OverspeedAlarm: Discrete Input 0 (BOOL)
    - LowOilPressure: Discrete Input 1 (BOOL)
    - HighBearingTemp: Discrete Input 2 (BOOL)
    - HighVibration: Discrete Input 3 (BOOL)
    - GeneratorFault: Discrete Input 4 (BOOL)
    """

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 44818,
        slot: int = 0,
    ):
        self.host = host
        self.port = port
        self.slot = slot

        # Server state
        self._server_task: asyncio.Task | None = None
        self._running = False

        # Tag database - maps tag names to (type, value, writable)
        # Types: DINT (32-bit signed), INT (16-bit signed), BOOL
        self._tags: dict[str, tuple[str, Any, bool]] = {}

        # Initialize default tags
        self._initialize_tags()

    def _initialize_tags(self):
        """Initialize default tag set for turbine PLC."""
        # Setpoints (writable)
        self._tags["SpeedSetpoint"] = ("DINT", 1500, True)
        self._tags["PowerSetpoint"] = ("DINT", 0, True)

        # Telemetry (read-only)
        self._tags["CurrentSpeed"] = ("DINT", 1500, False)
        self._tags["CurrentPower"] = ("DINT", 15, False)
        self._tags["BearingTemp"] = ("INT", 45, False)
        self._tags["OilPressure"] = ("INT", 8, False)
        self._tags["Vibration"] = ("INT", 2, False)
        self._tags["GeneratorTemp"] = ("INT", 62, False)
        self._tags["GearboxTemp"] = ("INT", 58, False)
        self._tags["AmbientTemp"] = ("INT", 22, False)

        # Control flags (writable)
        self._tags["ControlMode"] = ("BOOL", True, True)
        self._tags["EmergencyStop"] = ("BOOL", False, True)
        self._tags["MaintenanceMode"] = ("BOOL", False, True)

        # Alarm states (read-only)
        self._tags["OverspeedAlarm"] = ("BOOL", False, False)
        self._tags["LowOilPressure"] = ("BOOL", False, False)
        self._tags["HighBearingTemp"] = ("BOOL", False, False)
        self._tags["HighVibration"] = ("BOOL", False, False)
        self._tags["GeneratorFault"] = ("BOOL", False, False)

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> bool:
        """Start EtherNet/IP server."""
        if not CPPPO_AVAILABLE:
            logger.error(
                "cpppo library not available - EtherNet/IP server cannot start. "
                "Install with: pip install cpppo"
            )
            return False

        if self._running:
            return True

        try:
            # Note: cpppo server implementation is complex and requires
            # significant setup. For this simulator, we'll use a simplified
            # approach with a socket server that responds to basic CIP requests.

            # Start server task
            self._server_task = asyncio.create_task(self._run_server())
            self._running = True

            logger.info(f"EtherNet/IP server started on {self.host}:{self.port}")
            return True

        except Exception as e:
            logger.error(
                f"Failed to start EtherNet/IP server on {self.host}:{self.port}: {e}"
            )
            return False

    async def _run_server(self):
        """Run the EtherNet/IP server loop."""
        try:
            server = await asyncio.start_server(
                self._handle_client, self.host, self.port
            )

            async with server:
                logger.info(f"EtherNet/IP server listening on {self.host}:{self.port}")
                await server.serve_forever()

        except asyncio.CancelledError:
            logger.debug("EtherNet/IP server task cancelled")
        except Exception as e:
            logger.error(f"EtherNet/IP server error: {e}")
            self._running = False

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        """Handle individual client connection."""
        addr = writer.get_extra_info("peername")
        logger.debug(f"EtherNet/IP client connected from {addr}")

        try:
            while True:
                # Read EtherNet/IP encapsulation header (24 bytes minimum)
                header = await reader.readexactly(24)

                if not header:
                    break

                # Parse basic header
                command = struct.unpack("<H", header[0:2])[0]
                length = struct.unpack("<H", header[2:4])[0]

                # Read payload if present
                payload = b""
                if length > 0:
                    payload = await reader.readexactly(length)

                # Process command and generate response
                response = await self._process_command(command, payload)

                if response:
                    writer.write(response)
                    await writer.drain()

        except asyncio.IncompleteReadError:
            logger.debug(f"EtherNet/IP client {addr} disconnected")
        except Exception as e:
            logger.debug(f"Error handling EtherNet/IP client {addr}: {e}")
        finally:
            writer.close()
            await writer.wait_closed()

    async def _process_command(self, command: int, payload: bytes) -> bytes:
        """
        Process EtherNet/IP command and generate response.

        Command codes:
        - 0x0065: Register Session
        - 0x0066: Unregister Session
        - 0x006F: SendRRData (most tag operations)
        - 0x0070: SendUnitData
        """
        if command == 0x0065:  # Register Session
            # Return session handle
            return self._build_register_session_response()

        elif command == 0x0066:  # Unregister Session
            # Acknowledge unregister
            return self._build_unregister_session_response()

        elif command == 0x006F:  # SendRRData (tag read/write)
            return await self._handle_tag_operation(payload)

        else:
            # Unknown command - return error
            return self._build_error_response(command)

    def _build_register_session_response(self) -> bytes:
        """Build Register Session response."""
        # EtherNet/IP encapsulation header
        command = struct.pack("<H", 0x0065)  # Register Session
        length = struct.pack("<H", 4)  # Protocol version + options
        session_handle = struct.pack("<I", 0x00010001)  # Session handle
        status = struct.pack("<I", 0x00000000)  # Success
        sender_context = b"\x00" * 8
        options = struct.pack("<I", 0x00000000)

        # Payload: protocol version + options
        protocol_version = struct.pack("<H", 1)
        option_flags = struct.pack("<H", 0)

        header = command + length + session_handle + status + sender_context + options
        payload = protocol_version + option_flags

        return header + payload

    def _build_unregister_session_response(self) -> bytes:
        """Build Unregister Session response."""
        command = struct.pack("<H", 0x0066)
        length = struct.pack("<H", 0)
        session_handle = struct.pack("<I", 0x00000000)
        status = struct.pack("<I", 0x00000000)
        sender_context = b"\x00" * 8
        options = struct.pack("<I", 0x00000000)

        return command + length + session_handle + status + sender_context + options

    def _build_error_response(self, original_command: int) -> bytes:
        """Build error response for unsupported command."""
        command = struct.pack("<H", original_command)
        length = struct.pack("<H", 0)
        session_handle = struct.pack("<I", 0x00000000)
        status = struct.pack("<I", 0x00000001)  # Error status
        sender_context = b"\x00" * 8
        options = struct.pack("<I", 0x00000000)

        return command + length + session_handle + status + sender_context + options

    async def _handle_tag_operation(self, payload: bytes) -> bytes:
        """
        Handle tag read/write operations.

        This is a simplified implementation that responds to tag enumeration
        requests with the tag list. Full CIP implementation would be much more complex.
        """
        # For tag list requests, return all tag names and types
        # This is what ab_logix_tag_inventory.py queries

        # Build tag list response (simplified)
        tag_list = []
        for tag_name, (tag_type, _value, writable) in self._tags.items():
            tag_list.append(
                {"tag_name": tag_name, "data_type": tag_type, "writable": writable}
            )

        # Note: This is a simplified response. Full CIP protocol encoding
        # would require proper CIP packet structure with service codes,
        # class/instance/attribute addressing, etc.

        # Return a basic success response
        # Real implementation would encode tag list in CIP format
        return self._build_simple_response(0x006F, b"")

    def _build_simple_response(self, command: int, data: bytes) -> bytes:
        """Build a simple response packet."""
        cmd = struct.pack("<H", command)
        length = struct.pack("<H", len(data))
        session_handle = struct.pack("<I", 0x00010001)
        status = struct.pack("<I", 0x00000000)
        sender_context = b"\x00" * 8
        options = struct.pack("<I", 0x00000000)

        return cmd + length + session_handle + status + sender_context + options + data

    async def stop(self) -> None:
        """Stop EtherNet/IP server."""
        if not self._running:
            return

        # Cancel server task
        if self._server_task:
            self._server_task.cancel()
            try:
                await self._server_task
            except asyncio.CancelledError:
                pass
            self._server_task = None

        # Give OS time to release port
        await asyncio.sleep(0.3)

        self._running = False
        logger.info("EtherNet/IP server stopped")

    # ------------------------------------------------------------------
    # Device sync methods (similar to Modbus/S7 servers)
    # ------------------------------------------------------------------

    async def sync_from_device(
        self, device_registers: dict[int, Any], register_type: str
    ) -> None:
        """
        Write device registers to EtherNet/IP tags (device → server telemetry).

        Args:
            device_registers: Dict of {address: value} from device
            register_type: "input_registers" or "discrete_inputs"
        """
        if not self._running:
            return

        try:
            if register_type == "input_registers":
                # Map registers to tags
                tag_map = {
                    0: ("CurrentSpeed", "DINT"),
                    1: ("CurrentPower", "DINT"),
                    2: ("BearingTemp", "INT"),
                    3: ("OilPressure", "INT"),
                    4: ("Vibration", "INT"),
                    5: ("GeneratorTemp", "INT"),
                    6: ("GearboxTemp", "INT"),
                    7: ("AmbientTemp", "INT"),
                }

                for address, value in device_registers.items():
                    if address in tag_map:
                        tag_name, tag_type = tag_map[address]
                        if tag_name in self._tags:
                            self._tags[tag_name] = (tag_type, int(value), False)

            elif register_type == "discrete_inputs":
                # Map discrete inputs to alarm tags
                tag_map = {
                    0: "OverspeedAlarm",
                    1: "LowOilPressure",
                    2: "HighBearingTemp",
                    3: "HighVibration",
                    4: "GeneratorFault",
                }

                for address, value in device_registers.items():
                    if address in tag_map:
                        tag_name = tag_map[address]
                        if tag_name in self._tags:
                            self._tags[tag_name] = ("BOOL", bool(value), False)

        except Exception as e:
            logger.debug(f"Error syncing from device to EtherNet/IP server: {e}")

    async def sync_to_device(
        self, address: int, count: int, register_type: str
    ) -> dict[int, Any]:
        """
        Read EtherNet/IP tags to sync back to device (server → device commands).

        Args:
            address: Starting address
            count: Number of registers to read
            register_type: "coils" or "holding_registers"

        Returns:
            Dict of {address: value}
        """
        if not self._running:
            return {}

        result = {}

        try:
            if register_type == "coils":
                # Map coil addresses to control tags
                tag_map = {
                    0: "ControlMode",
                    1: "EmergencyStop",
                    2: "MaintenanceMode",
                }

                for i in range(count):
                    addr = address + i
                    if addr in tag_map:
                        tag_name = tag_map[addr]
                        if tag_name in self._tags:
                            _, value, _ = self._tags[tag_name]
                            result[addr] = value

            elif register_type == "holding_registers":
                # Map holding registers to setpoint tags
                tag_map = {
                    0: "SpeedSetpoint",
                    1: "PowerSetpoint",
                }

                for i in range(count):
                    addr = address + i
                    if addr in tag_map:
                        tag_name = tag_map[addr]
                        if tag_name in self._tags:
                            _, value, _ = self._tags[tag_name]
                            result[addr] = value

        except Exception as e:
            logger.debug(f"Error syncing to device from EtherNet/IP server: {e}")

        return result

    def get_tag(self, tag_name: str) -> tuple[str, Any, bool] | None:
        """Get tag value and metadata."""
        return self._tags.get(tag_name)

    def set_tag(self, tag_name: str, value: Any) -> bool:
        """Set tag value (if writable)."""
        if tag_name not in self._tags:
            return False

        tag_type, _, writable = self._tags[tag_name]
        if not writable:
            return False

        self._tags[tag_name] = (tag_type, value, writable)
        return True

    def get_tag_list(self) -> list[dict[str, Any]]:
        """Get list of all tags with metadata."""
        return [
            {
                "tag_name": name,
                "data_type": tag_type,
                "value": value,
                "writable": writable,
            }
            for name, (tag_type, value, writable) in self._tags.items()
        ]

    def get_info(self) -> dict[str, Any]:
        """Get server info."""
        return {
            "protocol": "ethernet_ip",
            "host": self.host,
            "port": self.port,
            "slot": self.slot,
            "running": self._running,
            "tag_count": len(self._tags),
        }
