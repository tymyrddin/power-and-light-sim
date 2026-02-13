# components/network/servers/base_server.py
"""
Base class for all TCP protocol servers.

Provides shared infrastructure that every protocol server needs:
- Host/port binding (127.0.0.1 for loopback, gateway handles external)
- Device identity (device_name for ConnectionRegistry, logging)
- ICSLogger integration (security event logging)
- Common status reporting

Protocol servers bind to 127.0.0.1. External access goes through the
NetworkGateway (_Listener on 0.0.0.0) which enforces segmentation,
firewall rules, and IDS/IPS.
"""

from abc import ABC, abstractmethod
from typing import Any

from components.security.logging_system import EventSeverity, ICSLogger, get_logger


class BaseProtocolServer(ABC):
    """Base class for all TCP protocol servers.

    All protocol servers bind to 127.0.0.1 (loopback only).
    The NetworkGateway opens the external port on 0.0.0.0 and
    pipes through after per-connection enforcement.

    Subclasses must implement: running, start(), stop().
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        device_name: str = "unknown",
    ):
        self.host = host
        self.port = port
        self.device_name = device_name
        self.logger: ICSLogger = get_logger(
            f"{self.__class__.__module__}.{device_name}",
            device=device_name,
        )

    @property
    @abstractmethod
    def running(self) -> bool: ...

    @abstractmethod
    async def start(self) -> Any: ...

    @abstractmethod
    async def stop(self) -> None: ...

    async def log_security(
        self,
        message: str,
        severity: EventSeverity = EventSeverity.INFO,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Log a security event via ICSLogger."""
        await self.logger.log_security(
            message=message,
            severity=severity,
            data=data or {},
        )

    def get_status(self) -> dict[str, Any]:
        """Get server status. Override to add protocol-specific fields."""
        return {
            "running": self.running,
            "host": self.host,
            "port": self.port,
            "device": self.device_name,
        }