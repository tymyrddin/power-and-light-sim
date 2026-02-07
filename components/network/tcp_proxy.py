# components/network/tcp_proxy.py
"""
Async TCP proxy with connection tracking.

Provides transparent TCP proxying between client and target server.
Useful for testing protocol interactions and network segmentation bypass.
"""

import asyncio
from typing import Any

from components.security.logging_system import (
    AlarmPriority,
    AlarmState,
    ICSLogger,
    get_logger,
)

__all__ = ["TCPProxy"]


class TCPProxy:
    """
    Transparent TCP proxy.

    Proxies TCP connections between a listen address and target address.
    Tracks active connections and data transfer statistics.

    Example:
        >>> proxy = TCPProxy(
        ...     listen_host="0.0.0.0",
        ...     listen_port=5502,
        ...     target_host="localhost",
        ...     target_port=502
        ... )
        >>> await proxy.start()
    """

    def __init__(
        self,
        *,
        listen_host: str,
        listen_port: int,
        target_host: str,
        target_port: int,
        buffer_size: int = 8192,
        timeout: float = 30.0,
    ):
        """Initialise TCP proxy.

        Args:
            listen_host: Host address to listen on
            listen_port: Port to listen on
            target_host: Target server host
            target_port: Target server port
            buffer_size: Buffer size for data transfer (default 8192)
            timeout: Connection timeout in seconds (default 30.0)

        Raises:
            ValueError: If parameters are invalid
        """
        if not listen_host:
            raise ValueError("listen_host cannot be empty")
        if not (0 < listen_port < 65536):
            raise ValueError(f"listen_port must be 1-65535, got {listen_port}")
        if not target_host:
            raise ValueError("target_host cannot be empty")
        if not (0 < target_port < 65536):
            raise ValueError(f"target_port must be 1-65535, got {target_port}")
        if buffer_size <= 0:
            raise ValueError(f"buffer_size must be > 0, got {buffer_size}")
        if timeout <= 0:
            raise ValueError(f"timeout must be > 0, got {timeout}")

        self.listen_host = listen_host
        self.listen_port = listen_port
        self.target_host = target_host
        self.target_port = target_port
        self.buffer_size = buffer_size
        self.timeout = timeout

        self.server: asyncio.AbstractServer | None = None
        self.active_connections = 0
        self.total_connections = 0
        self.bytes_proxied = 0
        self._connection_tasks: set[asyncio.Task[None]] = set()
        self.logger: ICSLogger = get_logger(
            __name__, device=f"proxy_{listen_port}_{target_port}"
        )

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def start(self) -> None:
        """Start TCP proxy listener.

        Raises:
            OSError: If unable to bind to listen address
        """
        try:
            self.server = await asyncio.start_server(
                self._handle_client,
                self.listen_host,
                self.listen_port,
            )

            self.logger.info(
                f"TCP Proxy started: {self.listen_host}:{self.listen_port} -> "
                f"{self.target_host}:{self.target_port}"
            )

        except OSError as e:
            await self.logger.log_alarm(
                message=f"Failed to start TCP proxy on {self.listen_host}:{self.listen_port}: {e}",
                priority=AlarmPriority.HIGH,
                state=AlarmState.ACTIVE,
                device=f"tcp_proxy_{self.listen_port}",
                data={
                    "listen_host": self.listen_host,
                    "listen_port": self.listen_port,
                    "target_host": self.target_host,
                    "target_port": self.target_port,
                    "error": str(e),
                },
            )
            raise

    async def stop(self) -> None:
        """Stop TCP proxy and close all active connections.

        Waits for active connections to complete gracefully.
        """
        if not self.server:
            return

        self.logger.info(
            f"Stopping TCP proxy {self.listen_host}:{self.listen_port} "
            f"({self.active_connections} active connections)"
        )

        # Stop accepting new connections
        self.server.close()

        # Cancel active connection tasks BEFORE wait_closed()
        # (wait_closed waits for handlers to finish, which won't happen
        # if they're blocked waiting for data)
        if self._connection_tasks:
            tasks = list(self._connection_tasks)
            self.logger.debug(f"Cancelling {len(tasks)} active connection tasks")
            for task in tasks:
                task.cancel()
            # Wait briefly for cancellation to propagate
            await asyncio.gather(*tasks, return_exceptions=True)
            self._connection_tasks.clear()

        await self.server.wait_closed()

        self.logger.info(
            f"TCP Proxy stopped: proxied {self.total_connections} connections, "
            f"{self.bytes_proxied} bytes total"
        )

    # ----------------------------------------------------------------
    # Connection handling
    # ----------------------------------------------------------------

    async def _handle_client(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming client connection.

        Creates a connection to the target and proxies data bidirectionally.

        Args:
            client_reader: Client stream reader
            client_writer: Client stream writer
        """
        self.total_connections += 1
        self.active_connections += 1

        # Get client address
        peername = client_writer.get_extra_info("peername")
        client_addr = f"{peername[0]}:{peername[1]}" if peername else "unknown"

        # Log proxy usage for security audit
        await self.logger.log_audit(
            f"Proxy connection initiated: {client_addr} -> "
            f"{self.target_host}:{self.target_port}",
            action="proxy_connect",
            result="INITIATED",
            data={
                "client_address": client_addr,
                "target": f"{self.target_host}:{self.target_port}",
            },
        )

        self.logger.info(
            f"Proxy connection: {client_addr} -> "
            f"{self.target_host}:{self.target_port}"
        )

        target_writer: asyncio.StreamWriter | None = None
        client_to_target: asyncio.Task[None] | None = None
        target_to_client: asyncio.Task[None] | None = None

        try:
            # Connect to target with timeout
            target_reader, target_writer = await asyncio.wait_for(
                asyncio.open_connection(self.target_host, self.target_port),
                timeout=self.timeout,
            )

            # Verify both connections established
            if target_reader is None or target_writer is None:
                raise ConnectionError("Failed to establish target connection")

            self.logger.debug(
                f"Proxy established: {client_addr} <-> {self.target_host}:{self.target_port}"
            )

            # Create bidirectional proxy tasks
            client_to_target = asyncio.create_task(
                self._pipe(client_reader, target_writer, f"{client_addr} -> target")
            )
            target_to_client = asyncio.create_task(
                self._pipe(target_reader, client_writer, f"target -> {client_addr}")
            )

            # Track tasks for graceful shutdown
            self._connection_tasks.add(client_to_target)
            self._connection_tasks.add(target_to_client)

            # Wait for either direction to complete (EOF), then cancel the other
            done, pending = await asyncio.wait(
                [client_to_target, target_to_client],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel pending tasks (the other direction)
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        except TimeoutError:
            self.logger.warning(
                f"Proxy timeout: {client_addr} -> {self.target_host}:{self.target_port}"
            )
        except ConnectionRefusedError:
            await self.logger.log_alarm(
                message=f"TCP proxy target connection refused: {self.target_host}:{self.target_port}",
                priority=AlarmPriority.MEDIUM,
                state=AlarmState.ACTIVE,
                device=f"tcp_proxy_{self.listen_port}",
                data={
                    "client_addr": str(client_addr),
                    "target_host": self.target_host,
                    "target_port": self.target_port,
                    "error": "connection_refused",
                },
            )
        except Exception as e:
            self.logger.error(f"Proxy error for {client_addr}: {e}", exc_info=True)
        finally:
            # Remove completed tasks from tracking set
            if client_to_target is not None:
                self._connection_tasks.discard(client_to_target)
            if target_to_client is not None:
                self._connection_tasks.discard(target_to_client)

            # Clean up target connection if established
            if target_writer:
                try:
                    target_writer.close()
                    await target_writer.wait_closed()
                except Exception:
                    pass

            # Clean up client connection
            try:
                client_writer.close()
                await client_writer.wait_closed()
            except Exception:
                pass

            self.active_connections -= 1

            self.logger.debug(f"Proxy connection closed: {client_addr}")

    # ----------------------------------------------------------------
    # Data piping
    # ----------------------------------------------------------------

    async def _pipe(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        direction: str,
    ) -> None:
        """Pipe data from reader to writer.

        Note: Caller is responsible for closing the writer.

        Args:
            reader: Source stream reader
            writer: Destination stream writer
            direction: Description for logging
        """
        try:
            while True:
                data = await reader.read(self.buffer_size)

                if not data:
                    # EOF reached
                    self.logger.debug(f"EOF on {direction}")
                    break

                self.bytes_proxied += len(data)

                writer.write(data)
                await writer.drain()

                self.logger.debug(f"Proxied {len(data)} bytes: {direction}")

        except asyncio.CancelledError:
            self.logger.debug(f"Pipe cancelled: {direction}")
            raise
        except Exception as e:
            self.logger.error(f"Pipe error on {direction}: {e}")

    # ----------------------------------------------------------------
    # Status
    # ----------------------------------------------------------------

    def get_summary(self) -> dict[str, Any]:
        """Get proxy statistics.

        Returns:
            Dictionary with proxy statistics
        """
        return {
            "listen": f"{self.listen_host}:{self.listen_port}",
            "target": f"{self.target_host}:{self.target_port}",
            "active_connections": self.active_connections,
            "total_connections": self.total_connections,
            "bytes_proxied": self.bytes_proxied,
            "running": self.server is not None and self.server.is_serving(),
        }
