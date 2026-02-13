# components/network/servers/iec104_server.py
"""
IEC 60870-5-104 TCP Server - ICS Attack Surface

Opens a REAL network port that external attack tools can target.
Implements IEC 104 controlled station (server) functionality for RTU/SCADA simulation.

Protocol: IEC 60870-5-104 (TCP/IP variant of IEC 60870-5)
Common in: European power utilities, SCADA systems
Default Port: 2404

External Attack Tools:
- lib60870: Open source IEC 60870-5-104 client library
- QTester104: IEC 104 protocol tester
- nmap: Port scanning
- Custom Python clients using lib60870 or c104 library

Example Attack from Terminal:
    # Reconnaissance
    $ nmap -p 2404 -sV localhost

    # General interrogation (read all data)
    $ python attack_scripts/iec104_interrogation.py --host localhost --port 2404

    # Send command (unauthorized breaker control)
    $ python attack_scripts/iec104_command.py --host localhost --port 2404 --ioa 100 --cmd OFF

Based on c104 library (Fraunhofer IEC 60870-5-104 implementation).
"""

import asyncio
from typing import Any

# import logging
from components.security.logging_system import get_logger

try:
    from components.protocols.iec104.c104_221 import IEC104C104Adapter

    IEC104_AVAILABLE = True
except ImportError:
    IEC104_AVAILABLE = False
    IEC104C104Adapter = None

from components.network.servers.base_server import BaseProtocolServer

logger = get_logger(__name__)


class IEC104TCPServer(BaseProtocolServer):
    """
    IEC 60870-5-104 TCP server using c104 library.

    Opens a real network port (default 2404) that external tools can connect to.
    Implements IEC 104 controlled station (RTU/SCADA server) for monitoring and control.

    IEC 104 Data Model:
    - Single-point information (M_SP_NA_1): Digital status (breaker state, alarm)
    - Measured values (M_ME_NC_1): Analog measurements (voltage, current, power)
    - Single commands (C_SC_NA_1): Digital control (breaker trip/close)
    - General interrogation (C_IC_NA_1): Read all current data

    Information Object Addresses (IOA):
    - 1-100: Digital inputs (single-point information)
    - 101-200: Analog inputs (measured values)
    - 1000+: Control points (commands)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2404,
        common_address: int = 1,
    ):
        """
        Initialize IEC 104 TCP server.

        Args:
            host: Bind address (0.0.0.0 = all interfaces)
            port: TCP port (default 2404 for IEC 104)
            common_address: Common address of controlled station
        """
        super().__init__(host, port)
        self.common_address = common_address

        # IEC 104 adapter (c104 library)
        self._adapter: IEC104C104Adapter | None = None
        self._running = False

    @property
    def running(self) -> bool:
        """Check if server is running."""
        return self._running

    async def start(self) -> bool:
        """
        Start IEC 104 TCP server (controlled station) with retry logic.

        Returns:
            True if server started successfully, False otherwise
        """
        if not IEC104_AVAILABLE:
            logger.error(
                "c104 library not available - IEC 104 server cannot start. "
                "Install with: pip install c104"
            )
            return False

        if self._running:
            return True

        # Retry logic for port binding (handles TIME_WAIT from previous runs)
        max_retries = 3
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                # Initialize IEC 104 adapter with c104 library
                self._adapter = IEC104C104Adapter(
                    bind_host=self.host,
                    bind_port=self.port,
                    common_address=self.common_address,
                    simulator_mode=True,
                )

                # Start c104 server
                success = await self._adapter.connect()

                if success:
                    self._running = True
                    logger.info(
                        f"IEC 104 server started on {self.host}:{self.port} "
                        f"(CA: {self.common_address})"
                    )
                    return True

                # Server didn't start, cleanup and retry
                if self._adapter:
                    try:
                        await self._adapter.disconnect()
                    except Exception:
                        pass
                    self._adapter = None

                if attempt < max_retries - 1:
                    await asyncio.sleep(
                        retry_delay * (attempt + 1)
                    )  # Exponential backoff

            except Exception as e:
                logger.warning(
                    f"Failed to start IEC 104 server on {self.host}:{self.port} "
                    f"(attempt {attempt + 1}/{max_retries}): {e}"
                )

                # Cleanup on error
                if self._adapter:
                    try:
                        await self._adapter.disconnect()
                    except Exception:
                        pass
                    self._adapter = None

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))

        logger.error(
            f"IEC 104 server failed to start on {self.host}:{self.port} after {max_retries} attempts"
        )
        return False

    async def stop(self) -> None:
        """Stop IEC 104 TCP server."""
        if not self._running:
            return

        try:
            if self._adapter:
                await self._adapter.disconnect()
                self._adapter = None

            self._running = False
            logger.info(f"IEC 104 server stopped on {self.host}:{self.port}")

        except Exception as e:
            logger.error(f"Error stopping IEC 104 server: {e}")

    # ================================================================
    # Device Synchronization (Option C: Manual Sync)
    # ================================================================

    async def sync_from_device(self, data: dict[int, Any], data_type: str) -> None:
        """
        Sync data from device to IEC 104 server.

        Called by SimulatorManager to push device telemetry to protocol server.

        Args:
            data: Dictionary mapping IOA to values
            data_type: "analog_inputs" or "binary_inputs"

        Example:
            # Push analog inputs to IEC 104
            await server.sync_from_device({101: 13.8, 102: 120.5}, "analog_inputs")
        """
        if not self._running or not self._adapter:
            return

        try:
            # Use set_point to update IOA values
            for ioa, value in data.items():
                await self._adapter.set_point(ioa, value)

        except Exception as e:
            logger.error(f"Failed to sync data to IEC 104 server: {e}")

    async def sync_to_device(
        self, start_addr: int, count: int, data_type: str
    ) -> dict[int, Any]:
        """
        Sync data from IEC 104 server to device.

        Called by SimulatorManager to pull control commands from protocol server.

        Args:
            start_addr: Starting IOA
            count: Number of points to read
            data_type: Data type identifier

        Returns:
            Dictionary mapping IOA to values

        Note: c104 adapter handles commands via callbacks, so this returns empty dict.
              Command handling should be done through c104's event system.
        """
        if not self._running or not self._adapter:
            return {}

        # c104 library handles commands through callbacks/events
        # For now, return empty dict - command handling needs to be
        # integrated with c104's event system
        return {}

    # ================================================================
    # Server Status
    # ================================================================

    def get_status(self) -> dict[str, Any]:
        """
        Get server status information.

        Returns:
            Dictionary with server status and statistics
        """
        status = {
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "common_address": self.common_address,
        }

        if self._adapter:
            status["adapter_running"] = self._adapter._running

        return status
