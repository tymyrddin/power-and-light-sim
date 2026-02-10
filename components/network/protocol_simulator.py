# components/network/protocol_simulator.py
"""
Async protocol socket dispatcher.

Manages TCP listeners for protocol servers with network enforcement.
Delegates connections to protocol-specific handlers.

Responsibilities:
- TCP listener lifecycle
- Network reachability enforcement
- Connection routing to protocol handlers
- Connection tracking and logging
"""

import asyncio
from collections.abc import Callable
from typing import Any, Protocol

from components.network.network_simulator import NetworkSimulator
from components.security.logging_system import (
    AlarmPriority,
    AlarmState,
    EventSeverity,
    ICSLogger,
    get_logger,
)

__all__ = ["ProtocolHandler", "ProtocolSimulator"]


class ProtocolHandler(Protocol):
    """Protocol for handler instances that serve client connections."""

    async def serve(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a client connection.

        Args:
            reader: Stream reader for receiving data
            writer: Stream writer for sending data
        """
        ...


class ProtocolSimulator:
    """
    Protocol server dispatcher with network enforcement.

    Manages multiple TCP listeners and enforces network segmentation rules
    before delegating to protocol-specific handlers.

    Example:
        >>> protocol_sim = ProtocolSimulator(network_sim)
        >>> await protocol_sim.register(
        ...     node="turbine_plc_1",
        ...     network="plant_network",
        ...     port=502,
        ...     protocol="modbus",
        ...     handler_factory=ModbusServerHandler
        ... )
        >>> await protocol_sim.start()
    """

    def __init__(self, network: NetworkSimulator, firewall=None, ids_system=None):
        """Initialise protocol simulator.

        Args:
            network: NetworkSimulator instance for reachability checks
            firewall: Optional Firewall device for connection enforcement
            ids_system: Optional IDS/IPS device for threat blocking
        """
        self.network = network
        self.firewall = firewall
        self.ids_system = ids_system
        self.listeners: list[_Listener] = []
        self.logger: ICSLogger = get_logger(__name__, device="protocol_simulator")

    # ----------------------------------------------------------------
    # Listener registration
    # ----------------------------------------------------------------

    async def register(
        self,
        *,
        node: str,
        network: str,
        port: int,
        protocol: str,
        handler_factory: Callable[[], ProtocolHandler],
    ) -> None:
        """Register a protocol listener on a device.

        Args:
            node: Device name hosting the service
            network: Network the device is primarily on (for logging)
            port: TCP port to listen on
            protocol: Protocol name (modbus, opcua, iec104, etc.)
            handler_factory: Factory function that creates handler instances

        Raises:
            ValueError: If parameters are invalid
        """
        if not node:
            raise ValueError("node cannot be empty")
        if not network:
            raise ValueError("network cannot be empty")
        if not protocol:
            raise ValueError("protocol cannot be empty")
        if not (0 < port < 65536):
            raise ValueError(f"port must be 1-65535, got {port}")
        if not callable(handler_factory):
            raise ValueError("handler_factory must be callable")

        # Expose service in network simulator
        await self.network.expose_service(node, protocol, port)

        # Create listener
        listener = _Listener(
            node=node,
            network=network,
            port=port,
            protocol=protocol,
            handler_factory=handler_factory,
            network_sim=self.network,
            firewall=self.firewall,
            ids_system=self.ids_system,
        )

        self.listeners.append(listener)

        self.logger.info(
            f"Registered protocol listener: {node}:{port} ({protocol}) on {network}"
        )

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def start(self) -> None:
        """Start all registered protocol listeners.

        Starts TCP servers for all registered protocols.
        """
        if not self.listeners:
            self.logger.warning("No protocol listeners registered")
            return

        self.logger.info(f"Starting {len(self.listeners)} protocol listener(s)")

        results = await asyncio.gather(
            *(listener.start() for listener in self.listeners), return_exceptions=True
        )

        # Check for failures
        failed = sum(1 for r in results if isinstance(r, Exception))
        if failed:
            await self.logger.log_alarm(
                message=f"Failed to start {failed} protocol listener(s)",
                priority=AlarmPriority.HIGH,
                state=AlarmState.ACTIVE,
                device="protocol_simulator",
                data={
                    "failed_count": failed,
                    "total_listeners": len(self.listeners),
                },
            )
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    listener = self.listeners[i]
                    self.logger.error(
                        f"Listener {listener.node}:{listener.port} failed: {result}"
                    )
        else:
            self.logger.info(
                f"All {len(self.listeners)} listener(s) started successfully"
            )

    async def stop(self) -> None:
        """Stop all protocol listeners.

        Gracefully shuts down all TCP servers.
        """
        if not self.listeners:
            return

        self.logger.info(f"Stopping {len(self.listeners)} protocol listener(s)")

        await asyncio.gather(
            *(listener.stop() for listener in self.listeners), return_exceptions=True
        )

        self.logger.info("All protocol listeners stopped")

    # ----------------------------------------------------------------
    # Status
    # ----------------------------------------------------------------

    def get_summary(self) -> dict[str, Any]:
        """Get protocol listener summary.

        Returns:
            Dictionary with listener statistics
        """
        return {
            "listeners": {
                "count": len(self.listeners),
                "details": [
                    {
                        "node": listener.node,
                        "network": listener.network,
                        "port": listener.port,
                        "protocol": listener.protocol,
                        "active_connections": listener.active_connections,
                        "total_connections": listener.total_connections,
                        "denied_connections": listener.denied_connections,
                    }
                    for listener in self.listeners
                ],
            }
        }


# ======================================================================
# Internal listener implementation
# ======================================================================


class _Listener:
    """Internal TCP listener with network enforcement."""

    def __init__(
        self,
        *,
        node: str,
        network: str,
        port: int,
        protocol: str,
        handler_factory: Callable[[], ProtocolHandler],
        network_sim: NetworkSimulator,
        firewall=None,
        ids_system=None,
    ):
        self.node = node
        self.network = network
        self.port = port
        self.protocol = protocol
        self.handler_factory = handler_factory
        self.network_sim = network_sim
        self.firewall = firewall
        self.ids_system = ids_system

        self.server: asyncio.AbstractServer | None = None
        self.active_connections = 0
        self.total_connections = 0
        self.denied_connections = 0
        self.logger: ICSLogger = get_logger(f"{__name__}.{node}", device=node)

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def start(self) -> None:
        """Start TCP listener."""
        self.server = await asyncio.start_server(
            self._handle_connection,
            host="0.0.0.0",
            port=self.port,
        )

        self.logger.info(f"Listener started: {self.node}:{self.port} ({self.protocol})")

    async def stop(self) -> None:
        """Stop TCP listener and close active connections."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()

            self.logger.info(
                f"Listener stopped: {self.node}:{self.port} "
                f"(handled {self.total_connections} connections, "
                f"denied {self.denied_connections})"
            )

    # ----------------------------------------------------------------
    # Connection handling
    # ----------------------------------------------------------------

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming TCP connection with network enforcement.

        Args:
            reader: Stream reader for receiving data
            writer: Stream writer for sending data
        """
        self.total_connections += 1

        # Get client address
        peername = writer.get_extra_info("peername")
        client_addr = f"{peername[0]}:{peername[1]}" if peername else "unknown"

        # Determine source network
        # TODO: In real implementation, map client IP to network
        # For simulation, we assume connections from corporate network
        # unless coming from localhost (which might be another simulated device)
        src_network = self._determine_source_network(peername[0] if peername else None)

        self.logger.debug(
            f"Connection attempt: {client_addr} ({src_network}) -> "
            f"{self.node}:{self.port} ({self.protocol})"
        )

        # Check network reachability
        allowed = await self.network_sim.can_reach(
            src_network,
            self.node,
            self.protocol,
            self.port,
        )

        if not allowed:
            self.denied_connections += 1
            await self.logger.log_security(
                f"Connection denied by network segmentation: {client_addr} "
                f"({src_network}) -> {self.node}:{self.port}",
                severity=EventSeverity.WARNING,
                data={
                    "source_network": src_network,
                    "client_address": client_addr,
                    "target_port": self.port,
                    "protocol": self.protocol,
                },
            )
            writer.close()
            await writer.wait_closed()
            return

        # Check IDS/IPS blacklist
        if self.ids_system:
            source_ip = peername[0] if peername else "unknown"
            if self.ids_system.is_blocked(source_ip):
                self.denied_connections += 1
                await self.logger.log_security(
                    f"Connection denied by IDS/IPS: {client_addr} -> {self.node}:{self.port} (IP blocked)",
                    severity=EventSeverity.ALERT,
                    data={
                        "source_ip": source_ip,
                        "client_address": client_addr,
                        "target_port": self.port,
                        "protocol": self.protocol,
                        "reason": "IP blocked by IDS/IPS",
                    },
                )
                writer.close()
                await writer.wait_closed()
                return

        # Check Firewall rules
        if self.firewall:
            source_ip = peername[0] if peername else "unknown"
            # Get destination info for firewall check
            dest_networks = await self.network_sim.get_device_networks(self.node)
            dest_network = list(dest_networks)[0] if dest_networks else "unknown"
            dest_zone = self.network_sim.network_to_zone.get(dest_network, "unknown")
            src_zone = self.network_sim.network_to_zone.get(src_network, "unknown")

            fw_allowed, fw_reason = await self.firewall.check_connection(
                source_ip=source_ip,
                source_network=src_network,
                source_zone=src_zone,
                dest_ip=self.node,
                dest_network=dest_network,
                dest_zone=dest_zone,
                dest_port=self.port,
                protocol=self.protocol,
            )

            if not fw_allowed:
                self.denied_connections += 1
                await self.logger.log_security(
                    f"Connection denied by firewall: {client_addr} -> {self.node}:{self.port} ({fw_reason})",
                    severity=EventSeverity.WARNING,
                    data={
                        "source_ip": source_ip,
                        "source_zone": src_zone,
                        "client_address": client_addr,
                        "target_port": self.port,
                        "protocol": self.protocol,
                        "firewall_reason": fw_reason,
                    },
                )
                writer.close()
                await writer.wait_closed()
                return

        # Connection allowed - delegate to protocol handler
        self.logger.info(
            f"Connection accepted: {client_addr} ({src_network}) -> "
            f"{self.node}:{self.port} ({self.protocol})"
        )

        self.active_connections += 1

        try:
            handler = self.handler_factory()
            await handler.serve(reader, writer)
        except Exception as e:
            self.logger.error(
                f"Handler error for {client_addr} -> {self.node}:{self.port}: {e}",
                exc_info=True,
            )
        finally:
            self.active_connections -= 1
            # Ensure writer is closed
            if not writer.is_closing():
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass  # Ignore errors during cleanup
            self.logger.debug(
                f"Connection closed: {client_addr} -> {self.node}:{self.port}"
            )

    @staticmethod
    def _determine_source_network(client_ip: str | None) -> str:
        """Determine source network from client IP.

        In a real implementation, this would map IP addresses to networks.
        For simulation purposes, we use simple heuristics.

        Args:
            client_ip: Client IP address

        Returns:
            Network name
        """
        if not client_ip:
            return "corporate_network"

        # Localhost connections might be from other simulated devices
        if client_ip in ("127.0.0.1", "::1"):
            # TODO: Track which device is making the connection
            # For now, assume localhost is a simulated device on plant network
            return "plant_network"

        # External connections assumed from corporate network
        # In real testing scenarios, this would be configured
        return "corporate_network"
