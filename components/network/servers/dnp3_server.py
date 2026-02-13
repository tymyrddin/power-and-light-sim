# components/network/servers/dnp3_server.py
"""
DNP3 TCP Server - ICS Attack Surface

Opens a REAL network port that external attack tools can target.
Implements DNP3 outstation (slave) functionality for RTU/IED simulation.

External Attack Tools:
- dnp3-test-harness: DNP3 master for testing
- pydnp3: Python DNP3 master client
- nmap: Port scanning with dnp3-info script
- Custom scripts: dnp3-python library

Example Attack from Terminal:
    # Reconnaissance
    $ nmap -p 20000 -sV --script=dnp3-info localhost

    # Read data with pydnp3
    $ python -c "from pydnp3 import opendnp3; # Read RTU data"

    # Write commands (SCADA attack)
    $ python -c "# Send control commands to RTU"

Based on dnp3py library outstation (server) functionality.
"""

import asyncio
from typing import Any

# import logging
from components.security.logging_system import get_logger

try:
    from components.protocols.dnp3.dnp3_adapter import DNP3Adapter

    DNP3_AVAILABLE = True
except ImportError:
    DNP3_AVAILABLE = False
    DNP3Adapter = None

from components.network.servers.base_server import BaseProtocolServer

logger = get_logger(__name__)


class DNP3TCPServer(BaseProtocolServer):
    """
    DNP3 TCP server using dnp3py library.

    Opens a real network port (default 20000) that external tools can connect to.
    Implements DNP3 outstation (RTU/IED server) for SCADA communication.

    DNP3 Data Model:
    - Binary Inputs: Digital status points (breaker state, alarm conditions)
    - Analog Inputs: Measurement values (voltage, current, power)
    - Counters: Accumulated values (energy meter readings)
    - Binary Outputs: Control points (breaker trip/close commands)
    - Analog Outputs: Setpoints (voltage regulation, tap position)
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 20000,
        master_address: int = 1,
        outstation_address: int = 100,
        # Point counts
        num_binary_inputs: int = 64,
        num_analog_inputs: int = 32,
        num_counters: int = 16,
    ):
        super().__init__(host, port)
        self.master_address = master_address
        self.outstation_address = outstation_address

        # Point counts
        self.num_binary_inputs = num_binary_inputs
        self.num_analog_inputs = num_analog_inputs
        self.num_counters = num_counters

        # DNP3 adapter (outstation mode)
        self._adapter: DNP3Adapter | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    async def start(self) -> bool:
        """Start DNP3 TCP server (outstation) with retry logic."""
        if not DNP3_AVAILABLE:
            logger.error(
                "dnp3py library not available - DNP3 server cannot start. "
                "Install with: pip install dnp3-python"
            )
            return False

        if self._running:
            return True

        # Retry logic for port binding (handles TIME_WAIT from previous runs)
        max_retries = 3
        retry_delay = 0.5

        for attempt in range(max_retries):
            try:
                # Initialize DNP3 adapter in outstation (server) mode
                setup = {
                    "binary_inputs": dict.fromkeys(
                        range(self.num_binary_inputs), False
                    ),
                    "analog_inputs": dict.fromkeys(range(self.num_analog_inputs), 0.0),
                    "counters": dict.fromkeys(range(self.num_counters), 0),
                }

                self._adapter = DNP3Adapter(
                    mode="outstation",
                    host=self.host,
                    port=self.port,
                    simulator_mode=True,
                    setup=setup,
                )

                # Start outstation server
                await self._adapter.start_outstation()

                # Give server time to bind
                await asyncio.sleep(retry_delay)

                # Check if connected
                if self._adapter.connected:
                    self._running = True
                    logger.info(
                        f"DNP3 outstation started on {self.host}:{self.port} "
                        f"(outstation address: {self.outstation_address})"
                    )
                    return True

                # Server didn't start, cleanup and retry
                if self._adapter:
                    try:
                        await self._adapter.stop_outstation()
                    except Exception:
                        pass
                    self._adapter = None

                if attempt < max_retries - 1:
                    await asyncio.sleep(
                        retry_delay * (attempt + 1)
                    )  # Exponential backoff

            except Exception as e:
                logger.warning(
                    f"Failed to start DNP3 server on {self.host}:{self.port} "
                    f"(attempt {attempt + 1}/{max_retries}): {e}"
                )

                # Cleanup on error
                if self._adapter:
                    try:
                        await self._adapter.stop_outstation()
                    except Exception:
                        pass
                    self._adapter = None

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))
                else:
                    logger.error(
                        f"Failed to start DNP3 server on {self.host}:{self.port} "
                        f"after {max_retries} attempts"
                    )
                    return False

        return False

    async def stop(self) -> None:
        """Stop DNP3 TCP server and release port."""
        if not self._running:
            return

        # Stop DNP3 outstation
        if self._adapter:
            try:
                await self._adapter.stop_outstation()
            except Exception as e:
                logger.debug(f"Error stopping DNP3 server: {e}")
            self._adapter = None

        # Give OS time to release port
        await asyncio.sleep(0.3)

        self._running = False

    # ------------------------------------------------------------------
    # Device sync methods (similar to ModbusTCPServer / S7TCPServer)
    # ------------------------------------------------------------------

    async def sync_from_device(
        self, device_registers: dict[int, Any], register_type: str
    ) -> None:
        """
        Write device registers to DNP3 server (device → server telemetry).

        Args:
            device_registers: Dict of {address: value} from device
            register_type: "binary_inputs", "analog_inputs", or "counters"
        """
        if not self._running or not self._adapter:
            return

        try:
            if register_type == "binary_inputs":
                # Update binary inputs (digital status)
                for index, value in device_registers.items():
                    if index < self.num_binary_inputs:
                        await self._adapter.update_binary_input(index, bool(value))

            elif register_type == "analog_inputs":
                # Update analog inputs (measurements)
                for index, value in device_registers.items():
                    if index < self.num_analog_inputs:
                        await self._adapter.update_analog_input(index, float(value))

            elif register_type == "counters":
                # Update counters (accumulated values)
                for index, value in device_registers.items():
                    if index < self.num_counters:
                        await self._adapter.update_counter(index, int(value))

        except Exception as e:
            logger.debug(f"Error syncing from device to DNP3 server: {e}")

    async def sync_to_device(
        self, address: int, count: int, register_type: str
    ) -> dict[int, Any]:
        """
        Read DNP3 server data to sync back to device (server → device commands).

        Note: DNP3 outstation receives commands from master, but the current
        dnp3py adapter doesn't expose command handlers yet. This is a placeholder
        for when command handling is implemented.

        Args:
            address: Starting address
            count: Number of points to read
            register_type: "binary_outputs" or "analog_outputs"

        Returns:
            Dict of {address: value}
        """
        if not self._running or not self._adapter:
            return {}

        result = {}

        # TODO: Implement command reading when dnp3py exposes command handlers
        # For now, return empty dict (no commands received)
        # In a full implementation, this would check for:
        # - Binary Output commands (CROB - Control Relay Output Block)
        # - Analog Output commands (setpoints)

        return result

    # ------------------------------------------------------------------
    # Attack primitives (exposed for external tool access)
    # ------------------------------------------------------------------

    async def read_binary_input(self, index: int) -> bool:
        """Read binary input value (for testing)."""
        if not self._running or not self._adapter:
            raise RuntimeError("DNP3 server not running")

        if index >= self.num_binary_inputs:
            raise ValueError(f"Binary input index {index} out of range")

        return self._adapter.setup["binary_inputs"].get(index, False)

    async def read_analog_input(self, index: int) -> float:
        """Read analog input value (for testing)."""
        if not self._running or not self._adapter:
            raise RuntimeError("DNP3 server not running")

        if index >= self.num_analog_inputs:
            raise ValueError(f"Analog input index {index} out of range")

        return self._adapter.setup["analog_inputs"].get(index, 0.0)

    async def read_counter(self, index: int) -> int:
        """Read counter value (for testing)."""
        if not self._running or not self._adapter:
            raise RuntimeError("DNP3 server not running")

        if index >= self.num_counters:
            raise ValueError(f"Counter index {index} out of range")

        return self._adapter.setup["counters"].get(index, 0)

    def get_info(self) -> dict[str, Any]:
        """Get server info."""
        return {
            "protocol": "dnp3",
            "host": self.host,
            "port": self.port,
            "master_address": self.master_address,
            "outstation_address": self.outstation_address,
            "running": self._running,
            "points": {
                "binary_inputs": self.num_binary_inputs,
                "analog_inputs": self.num_analog_inputs,
                "counters": self.num_counters,
            },
        }
