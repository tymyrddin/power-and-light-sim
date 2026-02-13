# components/network/servers/opcua_server.py
"""
OPC UA Server - ICS Attack Surface

Opens a REAL network port that external attack tools can target.
Implements OPC UA server functionality for SCADA/industrial data access.

Protocol: OPC UA (OPC Unified Architecture)
Common in: Industrial automation, SCADA systems, IoT
Default Port: 4840

External Attack Tools:
- UAExpert: Free OPC UA client for browsing/testing
- opcua-client-gui: Python GUI client
- nmap: Port scanning with opc-ua-discovery script
- Custom scripts: asyncua Python library

Example Attack from Terminal:
    # Reconnaissance
    $ nmap -p 4840 -sV --script=opc-ua-discover localhost

    # Browse OPC UA server
    $ python -c "from asyncua import Client; # Browse nodes"

    # Read/Write variables (unauthorized access)
    $ python attack_scripts/opcua_read_vars.py --endpoint opc.tcp://localhost:4840

Based on asyncua library (Python OPC UA implementation).
"""

import asyncio
from typing import Any

# import logging
from components.security.logging_system import get_logger

try:
    from components.protocols.opcua.opcua_asyncua_118 import OPCUAAsyncua118Adapter

    OPCUA_AVAILABLE = True
except ImportError:
    OPCUA_AVAILABLE = False
    OPCUAAsyncua118Adapter = None

from components.network.servers.base_server import BaseProtocolServer

logger = get_logger(__name__)


class OPCUAServer(BaseProtocolServer):
    """
    OPC UA server using asyncua library.

    Opens a real network port (default 4840) that external tools can connect to.
    Implements OPC UA server for industrial data access and control.

    OPC UA Features:
    - Hierarchical address space (Objects, Variables, Methods)
    - Read/Write access to process variables
    - Subscriptions for real-time data updates
    - Method calls for remote procedure execution

    Address Space Structure:
    - Objects/Simulator/Temperature: Temperature measurement
    - Objects/Simulator/Pressure: Pressure measurement
    - Custom variables can be added dynamically
    """

    def __init__(
        self,
        endpoint: str = "opc.tcp://127.0.0.1:4840/",
        namespace_uri: str = "urn:simulator:opcua",
        security_policy: str = "None",
        certificate_path: str | None = None,
        private_key_path: str | None = None,
        allow_anonymous: bool = True,
        auth_manager=None,
    ):
        """
        Initialize OPC UA server with optional security.

        Args:
            endpoint: OPC UA endpoint URL
            namespace_uri: Namespace URI for custom nodes
            security_policy: Security policy ("None", "Basic256Sha256", "Aes256_Sha256_RsaPss")
            certificate_path: Path to server certificate (PEM format)
            private_key_path: Path to server private key (PEM format)
            allow_anonymous: Allow anonymous connections (True for insecure devices)
            auth_manager: AuthenticationManager for username/password authentication
        """
        from urllib.parse import urlparse

        parsed = urlparse(endpoint)
        super().__init__(host=parsed.hostname or "127.0.0.1", port=parsed.port or 4840)
        self.endpoint = endpoint
        self.namespace_uri = namespace_uri
        self.security_policy = security_policy
        self.certificate_path = certificate_path
        self.private_key_path = private_key_path
        self.allow_anonymous = allow_anonymous
        self.auth_manager = auth_manager

        # OPC UA adapter (asyncua library)
        self._adapter: OPCUAAsyncua118Adapter | None = None
        self._running = False

    @property
    def running(self) -> bool:
        """Check if server is running."""
        return self._running

    async def start(self) -> bool:
        """
        Start OPC UA server with retry logic.

        Returns:
            True if server started successfully, False otherwise
        """
        if not OPCUA_AVAILABLE:
            logger.error(
                "asyncua library not available - OPC UA server cannot start. "
                "Install with: pip install asyncua"
            )
            return False

        if self._running:
            return True

        # Retry logic for port binding (handles TIME_WAIT from previous runs)
        max_retries = 3
        retry_delay = 0.1  # Fast retries for testing

        for attempt in range(max_retries):
            try:
                # Initialize OPC UA adapter with asyncua library
                self._adapter = OPCUAAsyncua118Adapter(
                    endpoint=self.endpoint,
                    namespace_uri=self.namespace_uri,
                    simulator_mode=True,
                    security_policy=self.security_policy,
                    certificate_path=self.certificate_path,
                    private_key_path=self.private_key_path,
                    allow_anonymous=self.allow_anonymous,
                    auth_manager=self.auth_manager,
                )

                # Start asyncua server
                success = await self._adapter.connect()

                if success:
                    self._running = True
                    logger.info(f"OPC UA server started on {self.endpoint}")
                    return True

                # Server didn't start, cleanup and retry
                if self._adapter:
                    try:
                        await self._adapter.disconnect()
                    except Exception:
                        pass
                    self._adapter = None

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay * (attempt + 1))

            except Exception as e:
                logger.warning(
                    f"Failed to start OPC UA server on {self.endpoint} "
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
            f"OPC UA server failed to start on {self.endpoint} after {max_retries} attempts"
        )
        return False

    async def stop(self) -> None:
        """Stop OPC UA server."""
        if not self._running:
            return

        try:
            if self._adapter:
                await self._adapter.disconnect()
                self._adapter = None

            self._running = False
            logger.info(f"OPC UA server stopped on {self.endpoint}")

        except Exception as e:
            logger.error(f"Error stopping OPC UA server: {e}")

    # ================================================================
    # Device Synchronization (Option C: Manual Sync)
    # ================================================================

    async def sync_from_device(self, data: dict[str, Any], data_type: str) -> None:
        """
        Sync data from device to OPC UA server.

        Called by SimulatorManager to push device telemetry to OPC UA variables.

        Args:
            data: Dictionary mapping variable names to values
            data_type: "variables" or data type identifier

        Example:
            # Push variables to OPC UA
            await server.sync_from_device({
                "Temperature": 45.2,
                "Pressure": 1.013
            }, "variables")
        """
        if not self._running or not self._adapter:
            return

        try:
            # Use set_variable to update OPC UA node values
            for var_name, value in data.items():
                await self._adapter.set_variable(var_name, value)

        except Exception as e:
            logger.error(f"Failed to sync data to OPC UA server: {e}")

    async def sync_to_device(
        self, variables: list[str], data_type: str
    ) -> dict[str, Any]:
        """
        Sync data from OPC UA server to device.

        Called by SimulatorManager to pull variable values from OPC UA.

        Args:
            variables: List of variable names to read
            data_type: Data type identifier

        Returns:
            Dictionary mapping variable names to values

        Example:
            # Pull variables from OPC UA
            values = await server.sync_to_device(["Temperature", "Pressure"], "variables")
        """
        if not self._running or not self._adapter:
            return {}

        try:
            result = {}
            for var_name in variables:
                value = await self._adapter.read_node(var_name)
                if value is not None:
                    result[var_name] = value
            return result

        except Exception as e:
            logger.error(f"Failed to sync data from OPC UA server: {e}")
            return {}

    # ================================================================
    # Server Status
    # ================================================================

    def get_status(self) -> dict[str, Any]:
        """
        Get server status information.

        Returns:
            Dictionary with server status, security info, and statistics
        """
        encrypted = self.security_policy not in ("None", None, "")
        status = {
            "running": self._running,
            "endpoint": self.endpoint,
            "namespace_uri": self.namespace_uri,
            "security_policy": self.security_policy,
            "encrypted": encrypted,
            "certificate_configured": self.certificate_path is not None,
            "allow_anonymous": self.allow_anonymous,
            "authentication_enabled": self.auth_manager is not None,
        }

        if self._adapter:
            status["adapter_running"] = self._adapter._running

        return status
