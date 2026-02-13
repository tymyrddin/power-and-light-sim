# components/network/protocol_simulator.py
"""
NetworkGateway — virtual network layer for ICS simulation.

Each protocol server (Modbus, S7, SMB, etc.) binds to 127.0.0.1.
The gateway opens the external port on 0.0.0.0 and acts as the
simulated network path: switch + firewall + routing in one.

Per-connection enforcement:
1. _get_attacker_networks() → ConnectionRegistry lookup
2. can_reach() → zone/subnet reachability
3. firewall.check_connection() → firewall rules
4. ids.is_blocked() → IDS/IPS blacklist
5. ALLOW → bidirectional TCP pipe to loopback
6. DENY → close (packet dropped)

Invisible to both attacker and protocol server.
"""

import asyncio
from typing import Any

from components.network.connection_registry import ConnectionRegistry
from components.network.network_simulator import NetworkSimulator
from components.security.logging_system import (
    AlarmPriority,
    AlarmState,
    EventSeverity,
    ICSLogger,
    get_logger,
)

__all__ = ["ProtocolSimulator"]

INTERNAL_PORT_OFFSET = 30000


class ProtocolSimulator:
    """
    Network gateway manager.

    Creates _Listener instances that virtualise network connectivity.
    Protocol servers bind to loopback; gateways open external ports
    and pipe through after enforcement.

    Example:
        >>> protocol_sim = ProtocolSimulator(network_sim)
        >>> await protocol_sim.register(
        ...     node="hex_turbine_plc",
        ...     network="turbine_network",
        ...     port=10502,
        ...     protocol="modbus",
        ... )
        >>> await protocol_sim.start()
    """

    def __init__(self, network: NetworkSimulator, firewall=None, ids_system=None):
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
    ) -> None:
        """Register a gateway for a protocol server.

        Creates a _Listener on 0.0.0.0:<port> that pipes to
        127.0.0.1:<port + INTERNAL_PORT_OFFSET> after enforcement.

        Args:
            node: Device name hosting the service
            network: Network the device is primarily on (for logging)
            port: External TCP port (the one attackers connect to)
            protocol: Protocol name (modbus, s7, smb, etc.)
        """
        if not node:
            raise ValueError("node cannot be empty")
        if not network:
            raise ValueError("network cannot be empty")
        if not protocol:
            raise ValueError("protocol cannot be empty")
        if not (0 < port < 65536):
            raise ValueError(f"port must be 1-65535, got {port}")

        # Expose service in network simulator
        await self.network.expose_service(node, protocol, port)

        internal_port = port + INTERNAL_PORT_OFFSET

        listener = _Listener(
            node=node,
            network=network,
            port=port,
            internal_port=internal_port,
            protocol=protocol,
            network_sim=self.network,
            firewall=self.firewall,
            ids_system=self.ids_system,
        )

        self.listeners.append(listener)

        self.logger.info(
            f"Registered gateway: {node}:{port} ({protocol}) on {network} "
            f"→ 127.0.0.1:{internal_port}"
        )

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def start(self) -> None:
        """Start all gateways."""
        if not self.listeners:
            self.logger.warning("No gateways registered")
            return

        self.logger.info(f"Starting {len(self.listeners)} gateway(s)")

        results = await asyncio.gather(
            *(listener.start() for listener in self.listeners), return_exceptions=True
        )

        failed = sum(1 for r in results if isinstance(r, Exception))
        if failed:
            await self.logger.log_alarm(
                message=f"Failed to start {failed} gateway(s)",
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
                        f"Gateway {listener.node}:{listener.port} failed: {result}"
                    )
        else:
            self.logger.info(
                f"All {len(self.listeners)} gateway(s) started successfully"
            )

    async def stop(self) -> None:
        """Stop all gateways."""
        if not self.listeners:
            return

        self.logger.info(f"Stopping {len(self.listeners)} gateway(s)")

        await asyncio.gather(
            *(listener.stop() for listener in self.listeners), return_exceptions=True
        )

        self.logger.info("All gateways stopped")

    # ----------------------------------------------------------------
    # Connection management
    # ----------------------------------------------------------------

    async def kill_connection(self, session_id: str) -> bool:
        """Kill a proxied connection by session ID.

        Finds the listener holding this session and closes both ends
        of the pipe. The ConnectionRegistry deregistration happens
        automatically when the pipe closes.

        Returns True if found and killed.
        """
        for listener in self.listeners:
            if await listener.kill_connection(session_id):
                return True
        return False

    # ----------------------------------------------------------------
    # Status
    # ----------------------------------------------------------------

    def get_summary(self) -> dict[str, Any]:
        return {
            "listeners": {
                "count": len(self.listeners),
                "details": [
                    {
                        "node": listener.node,
                        "network": listener.network,
                        "port": listener.port,
                        "internal_port": listener.internal_port,
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
    """TCP gateway with per-connection network enforcement.

    Opens external port on 0.0.0.0. For each incoming connection:
    1. Determine attacker's reachable networks (from ConnectionRegistry)
    2. Check if any can reach this device (NetworkSimulator.can_reach)
    3. Check firewall rules
    4. Check IDS/IPS blacklist
    5. If allowed: pipe bidirectionally to 127.0.0.1:<internal_port>
    6. If denied: close connection

    When segmentation is disabled, skips enforcement and pipes immediately.
    """

    def __init__(
        self,
        *,
        node: str,
        network: str,
        port: int,
        internal_port: int,
        protocol: str,
        network_sim: NetworkSimulator,
        firewall=None,
        ids_system=None,
    ):
        self.node = node
        self.network = network
        self.port = port
        self.internal_port = internal_port
        self.protocol = protocol
        self.network_sim = network_sim
        self.firewall = firewall
        self.ids_system = ids_system

        self.server: asyncio.AbstractServer | None = None
        self.active_connections = 0
        self.total_connections = 0
        self.denied_connections = 0
        self.logger: ICSLogger = get_logger(f"{__name__}.{node}", device=node)

        # Track active pipes by session_id for kill_connection()
        self._active_pipes: dict[str, tuple[asyncio.StreamWriter, asyncio.StreamWriter]] = {}
        self._registry = ConnectionRegistry()

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def start(self) -> None:
        self.server = await asyncio.start_server(
            self._handle_connection,
            host="0.0.0.0",
            port=self.port,
        )
        self.logger.info(
            f"Gateway started: 0.0.0.0:{self.port} → 127.0.0.1:{self.internal_port} "
            f"({self.protocol} for {self.node})"
        )

    async def stop(self) -> None:
        # Close all active pipes
        for session_id, (client_writer, backend_writer) in list(self._active_pipes.items()):
            _close_writer(client_writer)
            _close_writer(backend_writer)
        self._active_pipes.clear()

        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.logger.info(
                f"Gateway stopped: {self.node}:{self.port} "
                f"(handled {self.total_connections}, denied {self.denied_connections})"
            )

    async def kill_connection(self, session_id: str) -> bool:
        """Kill a specific proxied connection."""
        pipe = self._active_pipes.get(session_id)
        if pipe is None:
            return False
        client_writer, backend_writer = pipe
        _close_writer(client_writer)
        _close_writer(backend_writer)
        # Cleanup happens in _handle_connection's finally block
        return True

    # ----------------------------------------------------------------
    # Connection handling
    # ----------------------------------------------------------------

    async def _handle_connection(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        self.total_connections += 1

        peername = client_writer.get_extra_info("peername")
        client_addr = f"{peername[0]}:{peername[1]}" if peername else "unknown"
        client_ip = peername[0] if peername else "unknown"

        # --- Enforcement ---
        if not await self._check_allowed(client_ip, client_addr):
            self.denied_connections += 1
            client_writer.close()
            await client_writer.wait_closed()
            return

        # --- Pipe to backend ---
        session_id = None
        backend_reader = None
        backend_writer = None
        try:
            backend_reader, backend_writer = await asyncio.open_connection(
                "127.0.0.1", self.internal_port
            )
        except (ConnectionRefusedError, OSError) as e:
            self.logger.error(
                f"Backend connection failed: 127.0.0.1:{self.internal_port} ({e})"
            )
            client_writer.close()
            await client_writer.wait_closed()
            return

        # Register in ConnectionRegistry
        session_id = await self._registry.connect(
            source_ip=client_ip,
            source_device="external",
            target_device=self.node,
            protocol=self.protocol,
            port=self.port,
            metadata={"client_address": client_addr},
        )

        self._active_pipes[session_id] = (client_writer, backend_writer)
        self.active_connections += 1

        self.logger.info(
            f"Connection piped: {client_addr} → {self.node}:{self.port} "
            f"({self.protocol}) [session={session_id}]"
        )

        try:
            # Bidirectional pipe — when either side closes, both tasks end
            await asyncio.gather(
                _pipe(client_reader, backend_writer),
                _pipe(backend_reader, client_writer),
            )
        except Exception:
            pass  # Connection closed (normal)
        finally:
            self.active_connections -= 1
            self._active_pipes.pop(session_id, None)

            _close_writer(client_writer)
            _close_writer(backend_writer)

            # Deregister from ConnectionRegistry
            if session_id:
                await self._registry.disconnect(session_id)

            self.logger.debug(
                f"Connection closed: {client_addr} → {self.node}:{self.port} "
                f"[session={session_id}]"
            )

    async def _check_allowed(self, client_ip: str, client_addr: str) -> bool:
        """Run the full enforcement chain. Returns True if allowed."""

        # Segmentation disabled = flat network, allow everything
        if not self.network_sim.segmentation_enabled:
            return True

        # Get attacker's reachable networks
        attacker_networks = await self._get_attacker_networks()

        # Check if any attacker network can reach this device
        allowed = False
        for src_network in attacker_networks:
            if await self.network_sim.can_reach(
                src_network, self.node, self.protocol, self.port
            ):
                allowed = True
                break

        if not allowed:
            await self.logger.log_security(
                f"Connection denied by network topology: {client_addr} → "
                f"{self.node}:{self.port} ({self.protocol})",
                severity=EventSeverity.WARNING,
                data={
                    "client_address": client_addr,
                    "target_node": self.node,
                    "target_port": self.port,
                    "protocol": self.protocol,
                    "attacker_networks": list(attacker_networks),
                    "reason": "no_reachable_path",
                },
            )
            return False

        # Check IDS/IPS blacklist
        if self.ids_system and self.ids_system.is_blocked(client_ip):
            self.denied_connections += 1
            await self.logger.log_security(
                f"Connection denied by IDS/IPS: {client_addr} → {self.node}:{self.port}",
                severity=EventSeverity.ALERT,
                data={
                    "source_ip": client_ip,
                    "target_port": self.port,
                    "protocol": self.protocol,
                    "reason": "IP blocked by IDS/IPS",
                },
            )
            return False

        # Check Firewall rules
        if self.firewall:
            dest_networks = await self.network_sim.get_device_networks(self.node)
            dest_network = next(iter(dest_networks), "unknown")
            dest_zone = self.network_sim.network_to_zone.get(dest_network, "unknown")

            # Use first matching attacker network for firewall src zone
            src_network = next(iter(attacker_networks), "unknown")
            src_zone = self.network_sim.network_to_zone.get(src_network, "unknown")

            fw_allowed, fw_reason = await self.firewall.check_connection(
                source_ip=client_ip,
                source_network=src_network,
                source_zone=src_zone,
                dest_ip=self.node,
                dest_network=dest_network,
                dest_zone=dest_zone,
                dest_port=self.port,
                protocol=self.protocol,
            )

            if not fw_allowed:
                await self.logger.log_security(
                    f"Connection denied by firewall: {client_addr} → "
                    f"{self.node}:{self.port} ({fw_reason})",
                    severity=EventSeverity.WARNING,
                    data={
                        "source_ip": client_ip,
                        "source_zone": src_zone,
                        "target_port": self.port,
                        "protocol": self.protocol,
                        "firewall_reason": fw_reason,
                    },
                )
                return False

        return True

    async def _get_attacker_networks(self) -> set[str]:
        """Attacker's reachable networks = externally reachable zones + compromised device networks."""
        networks = set()

        # Externally reachable zones (enterprise_zone, dmz) are always reachable
        externally_reachable = self.network_sim.externally_reachable_zones
        for net_name, zone_name in self.network_sim.network_to_zone.items():
            if zone_name in externally_reachable:
                networks.add(net_name)

        # Add networks from all devices with active sessions
        active = await self._registry.get_active_connections()
        for conn in active:
            device_networks = await self.network_sim.get_device_networks(
                conn["target_device"]
            )
            networks.update(device_networks)

        return networks


# ======================================================================
# Helpers
# ======================================================================


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Shovel bytes from reader to writer until EOF or error."""
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        _close_writer(writer)


def _close_writer(writer: asyncio.StreamWriter) -> None:
    """Close a writer, ignoring errors."""
    if not writer.is_closing():
        writer.close()
