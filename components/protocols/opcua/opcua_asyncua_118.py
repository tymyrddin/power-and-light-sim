#!/usr/bin/env python3
"""
OPC UA adapter using asyncua 1.1.8.

- Uses asyncua.Server as a real OPC UA simulator
- Fully asyncio-native
- Exposes a clean async lifecycle for the simulator manager
- Configurable security (None, Basic256Sha256, etc.)
"""

from pathlib import Path

from asyncua import Server
from asyncua.crypto import uacrypto
from asyncua.server.user_managers import CertificateUserManager


class OPCUAAsyncua118Adapter:
    """Async OPC UA simulator adapter (asyncua 1.1.8) with configurable security."""

    def __init__(
        self,
        endpoint="opc.tcp://0.0.0.0:4840/",
        namespace_uri="urn:simulator:opcua",
        simulator_mode=True,
        security_policy="None",
        certificate_path=None,
        private_key_path=None,
        allow_anonymous=True,
    ):
        """
        Initialize OPC UA adapter.

        Args:
            endpoint: OPC UA endpoint URL
            namespace_uri: Namespace URI for custom nodes
            simulator_mode: Run in simulator mode
            security_policy: Security policy ("None", "Basic256Sha256", "Aes256_Sha256_RsaPss")
            certificate_path: Path to server certificate (PEM format)
            private_key_path: Path to server private key (PEM format)
            allow_anonymous: Allow anonymous connections (True for insecure devices)
        """
        self.endpoint = endpoint
        self.namespace_uri = namespace_uri
        self.simulator_mode = simulator_mode
        self.security_policy = security_policy
        self.certificate_path = Path(certificate_path) if certificate_path else None
        self.private_key_path = Path(private_key_path) if private_key_path else None
        self.allow_anonymous = allow_anonymous

        self._server = None
        self._namespace_idx = None
        self._objects = {}
        self._running = False

    # ------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------

    async def connect(self) -> bool:
        """
        Start OPC UA simulator with optional security configuration.
        """
        if self._running or not self.simulator_mode:
            return True

        self._server = Server()
        await self._server.init()

        self._server.set_endpoint(self.endpoint)
        self._server.set_server_name("AsyncUA OPC UA Simulator")

        # Configure security if certificates are provided
        if self.security_policy != "None" and self.certificate_path and self.private_key_path:
            if self.certificate_path.exists() and self.private_key_path.exists():
                try:
                    # Load server certificate and private key
                    await self._server.load_certificate(str(self.certificate_path))
                    await self._server.load_private_key(str(self.private_key_path))

                    # Set security policy
                    self._server.set_security_policy([
                        f"http://opcfoundation.org/UA/SecurityPolicy#{self.security_policy}"
                    ])

                    # Configure user authentication
                    if not self.allow_anonymous:
                        # Require certificate-based authentication
                        user_manager = CertificateUserManager()
                        self._server.set_user_manager(user_manager)

                except Exception as e:
                    # Fall back to no security if certificate loading fails
                    import logging
                    logging.warning(f"Failed to load OPC UA certificates: {e}, falling back to no security")

        self._namespace_idx = await self._server.register_namespace(self.namespace_uri)

        objects = self._server.nodes.objects
        sim_obj = await objects.add_object(self._namespace_idx, "Simulator")

        temperature = await sim_obj.add_variable(
            self._namespace_idx, "Temperature", 20.0
        )
        pressure = await sim_obj.add_variable(self._namespace_idx, "Pressure", 1.0)

        await temperature.set_writable()
        await pressure.set_writable()

        self._objects["Temperature"] = temperature
        self._objects["Pressure"] = pressure

        await self._server.start()
        self._running = True
        return True

    async def disconnect(self) -> None:
        """
        Stop OPC UA simulator.
        """
        if not self._server:
            return

        await self._server.stop()
        self._server = None
        self._objects = {}  # Clear objects on disconnect
        self._running = False

    # ------------------------------------------------------------
    # async-facing helpers
    # ------------------------------------------------------------

    async def probe(self):
        """
        Minimal recon output.
        """
        return {
            "protocol": "OPC UA",
            "implementation": "asyncua",
            "version": "1.1.8",
            "listening": self._running,
            "endpoint": self.endpoint,
            "nodes": list(self._objects.keys()),
        }

    async def get_state(self):
        """
        Return current simulated variable state.
        """
        state = {}
        for name, node in self._objects.items():
            state[name] = await node.read_value()
        return state

    async def set_variable(self, name, value):
        """
        Set a simulated OPC UA variable.
        """
        node = self._objects.get(name)
        if not node:
            raise KeyError(f"No OPC UA variable named '{name}'")

        # Convert value to float to match the variable type
        # (Temperature and Pressure are initialized as floats)
        await node.write_value(float(value))

    # ------------------------------------------------------------
    # Protocol interface methods (for OPCUAProtocol)
    # ------------------------------------------------------------

    async def browse_root(self):
        """
        Browse root nodes (returns list of node names).
        Required by OPCUAProtocol.
        """
        if not self._running:
            return []
        return list(self._objects.keys())

    async def read_node(self, node_id):
        """
        Read a node value by name.
        Required by OPCUAProtocol.
        """
        if not self._running:
            raise RuntimeError("Server not running")

        node = self._objects.get(node_id)
        if not node:
            raise KeyError(f"No OPC UA variable named '{node_id}'")

        return await node.read_value()

    async def write_node(self, node_id, value):
        """
        Write a node value by name.
        Required by OPCUAProtocol.
        """
        if not self._running:
            raise RuntimeError("Server not running")

        node = self._objects.get(node_id)
        if not node:
            raise KeyError(f"No OPC UA variable named '{node_id}'")

        # Convert to float to match variable type
        await node.write_value(float(value))
        return True
