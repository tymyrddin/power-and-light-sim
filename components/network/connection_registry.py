# components/network/connection_registry.py
"""
Connection registry for tracking active sessions.

Tracks who is connected to what device, when, and how. Connections are
visible to defenders via the Blue Team CLI. Attack scripts create
connections; defenders can query and kill them.

Event-driven (not tick-based). Connections happen on demand.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from components.security.logging_system import EventSeverity, get_logger
from components.time.simulation_time import SimulationTime


@dataclass
class Connection:
    """An active connection to a device."""

    session_id: str
    source_ip: str
    source_device: str  # Device name the attacker is "on"
    target_device: str
    protocol: str
    port: int
    connected_at: float  # Simulation time
    username: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class ConnectionRegistry:
    """
    Singleton registry of active connections.

    Created by attack scripts when they connect to a device.
    Queried by defenders via Blue Team CLI.
    Connections logged via ICSLogger.

    Example:
        >>> registry = ConnectionRegistry()
        >>> session = await registry.connect(
        ...     source_ip="10.40.99.10",
        ...     source_device="legacy_data_collector",
        ...     target_device="hex_turbine_plc",
        ...     protocol="modbus",
        ...     port=10502,
        ... )
        >>> active = await registry.get_active_connections()
        >>> await registry.disconnect(session)
    """

    _instance: "ConnectionRegistry | None" = None
    _lock = asyncio.Lock()

    def __new__(cls) -> "ConnectionRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialised = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialised:
            return
        self._connections: dict[str, Connection] = {}
        self._history: list[dict[str, Any]] = []  # Closed connections for forensics
        self._max_history = 1000
        self.sim_time = SimulationTime()
        self.logger = get_logger(__name__, device="connection_registry")
        self._initialised = True

    async def connect(
        self,
        source_ip: str,
        source_device: str,
        target_device: str,
        protocol: str,
        port: int,
        username: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Register a new connection.

        Returns session_id for the connection.
        """
        session_id = str(uuid.uuid4())[:12]
        now = self.sim_time.now()

        conn = Connection(
            session_id=session_id,
            source_ip=source_ip,
            source_device=source_device,
            target_device=target_device,
            protocol=protocol,
            port=port,
            connected_at=now,
            username=username,
            metadata=metadata or {},
        )

        self._connections[session_id] = conn

        await self.logger.log_security(
            message=(
                f"Connection established: {source_ip} ({source_device}) -> "
                f"{target_device}:{port} ({protocol}) [session={session_id}]"
            ),
            severity=EventSeverity.NOTICE,
            data={
                "session_id": session_id,
                "source_ip": source_ip,
                "source_device": source_device,
                "target_device": target_device,
                "protocol": protocol,
                "port": port,
                "username": username,
            },
        )

        return session_id

    async def disconnect(self, session_id: str) -> bool:
        """
        Close a connection.

        Returns True if connection was found and closed.
        """
        conn = self._connections.pop(session_id, None)
        if conn is None:
            return False

        now = self.sim_time.now()
        duration = now - conn.connected_at

        # Add to history
        self._history.append({
            "session_id": conn.session_id,
            "source_ip": conn.source_ip,
            "source_device": conn.source_device,
            "target_device": conn.target_device,
            "protocol": conn.protocol,
            "port": conn.port,
            "connected_at": conn.connected_at,
            "disconnected_at": now,
            "duration": duration,
            "username": conn.username,
            "closed_by": "client",
        })

        # Trim history
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        await self.logger.log_security(
            message=(
                f"Connection closed: {conn.source_ip} ({conn.source_device}) -> "
                f"{conn.target_device}:{conn.port} [session={session_id}, "
                f"duration={duration:.1f}s]"
            ),
            severity=EventSeverity.INFO,
            data={
                "session_id": session_id,
                "duration": duration,
            },
        )

        return True

    async def kill_connection(self, session_id: str, reason: str = "") -> bool:
        """
        Force-close a connection (defender action).

        Returns True if connection was found and killed.
        """
        conn = self._connections.pop(session_id, None)
        if conn is None:
            return False

        now = self.sim_time.now()
        duration = now - conn.connected_at

        self._history.append({
            "session_id": conn.session_id,
            "source_ip": conn.source_ip,
            "source_device": conn.source_device,
            "target_device": conn.target_device,
            "protocol": conn.protocol,
            "port": conn.port,
            "connected_at": conn.connected_at,
            "disconnected_at": now,
            "duration": duration,
            "username": conn.username,
            "closed_by": "defender",
            "reason": reason,
        })

        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

        await self.logger.log_security(
            message=(
                f"Connection KILLED by defender: {conn.source_ip} ({conn.source_device}) -> "
                f"{conn.target_device}:{conn.port} [session={session_id}, reason={reason}]"
            ),
            severity=EventSeverity.WARNING,
            data={
                "session_id": session_id,
                "reason": reason,
                "duration": duration,
            },
        )

        return True

    async def get_active_connections(
        self,
        target_device: str | None = None,
        source_device: str | None = None,
        protocol: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get active connections, optionally filtered."""
        now = self.sim_time.now()
        results = []

        for conn in self._connections.values():
            if target_device and conn.target_device != target_device:
                continue
            if source_device and conn.source_device != source_device:
                continue
            if protocol and conn.protocol != protocol:
                continue

            results.append({
                "session_id": conn.session_id,
                "source_ip": conn.source_ip,
                "source_device": conn.source_device,
                "target_device": conn.target_device,
                "protocol": conn.protocol,
                "port": conn.port,
                "connected_at": conn.connected_at,
                "duration": now - conn.connected_at,
                "username": conn.username,
            })

        return results

    async def get_connection_history(
        self,
        limit: int = 50,
        target_device: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get closed connection history for forensics."""
        history = self._history
        if target_device:
            history = [h for h in history if h["target_device"] == target_device]
        return history[-limit:]

    def get_connection(self, session_id: str) -> Connection | None:
        """Get a specific active connection."""
        return self._connections.get(session_id)

    def is_connected(self, session_id: str) -> bool:
        """Check if a session is still active."""
        return session_id in self._connections

    async def reset(self) -> None:
        """Reset all connections (for testing)."""
        self._connections.clear()
        self._history.clear()

    @classmethod
    def reset_singleton(cls) -> None:
        """Reset the singleton instance (for testing only)."""
        cls._instance = None