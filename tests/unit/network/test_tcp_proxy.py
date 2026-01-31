# tests/unit/network/test_tcp_proxy.py
"""Comprehensive tests for TCPProxy component.

Level 0 dependency - standalone component.

Test Coverage:
- Initialization and validation
- Lifecycle management (start/stop)
- Bidirectional data proxying
- Connection tracking
- Summary reporting
- Error handling
- Concurrent connections
"""

import asyncio

import pytest

from components.network.tcp_proxy import TCPProxy


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
async def echo_server():
    """Create a simple echo server for testing."""
    server = None
    connections = []

    async def handle_client(reader, writer):
        connections.append(writer)
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except asyncio.CancelledError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 15600)

    yield {"server": server, "port": 15600, "connections": connections}

    server.close()
    await server.wait_closed()


@pytest.fixture
async def delayed_echo_server():
    """Create an echo server with artificial delay."""

    async def handle_client(reader, writer):
        try:
            while True:
                data = await reader.read(1024)
                if not data:
                    break
                await asyncio.sleep(0.1)  # Add delay
                writer.write(data)
                await writer.drain()
        except asyncio.CancelledError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 15601)

    yield {"server": server, "port": 15601}

    server.close()
    await server.wait_closed()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestTCPProxyInitialization:
    """Test initialization and validation."""

    def test_init_basic(self):
        """Test basic initialization.

        WHY: Proxy must be configurable.
        """
        proxy = TCPProxy(
            listen_host="0.0.0.0",
            listen_port=5502,
            target_host="localhost",
            target_port=502,
        )

        assert proxy.listen_host == "0.0.0.0"
        assert proxy.listen_port == 5502
        assert proxy.target_host == "localhost"
        assert proxy.target_port == 502

    def test_init_with_options(self):
        """Test initialization with custom options.

        WHY: Buffer size and timeout should be configurable.
        """
        proxy = TCPProxy(
            listen_host="0.0.0.0",
            listen_port=5502,
            target_host="localhost",
            target_port=502,
            buffer_size=4096,
            timeout=60.0,
        )

        assert proxy.buffer_size == 4096
        assert proxy.timeout == 60.0

    def test_init_defaults(self):
        """Test default values.

        WHY: Sensible defaults should be provided.
        """
        proxy = TCPProxy(
            listen_host="0.0.0.0",
            listen_port=5502,
            target_host="localhost",
            target_port=502,
        )

        assert proxy.buffer_size == 8192
        assert proxy.timeout == 30.0

    def test_init_validates_empty_listen_host(self):
        """Test listen_host validation.

        WHY: Input validation.
        """
        with pytest.raises(ValueError, match="listen_host cannot be empty"):
            TCPProxy(
                listen_host="",
                listen_port=5502,
                target_host="localhost",
                target_port=502,
            )

    def test_init_validates_listen_port_range(self):
        """Test listen_port validation.

        WHY: Port must be 1-65535.
        """
        with pytest.raises(ValueError, match="listen_port must be 1-65535"):
            TCPProxy(
                listen_host="0.0.0.0",
                listen_port=0,
                target_host="localhost",
                target_port=502,
            )

        with pytest.raises(ValueError, match="listen_port must be 1-65535"):
            TCPProxy(
                listen_host="0.0.0.0",
                listen_port=65536,
                target_host="localhost",
                target_port=502,
            )

    def test_init_validates_empty_target_host(self):
        """Test target_host validation.

        WHY: Input validation.
        """
        with pytest.raises(ValueError, match="target_host cannot be empty"):
            TCPProxy(
                listen_host="0.0.0.0",
                listen_port=5502,
                target_host="",
                target_port=502,
            )

    def test_init_validates_target_port_range(self):
        """Test target_port validation.

        WHY: Port must be 1-65535.
        """
        with pytest.raises(ValueError, match="target_port must be 1-65535"):
            TCPProxy(
                listen_host="0.0.0.0",
                listen_port=5502,
                target_host="localhost",
                target_port=0,
            )

    def test_init_validates_buffer_size(self):
        """Test buffer_size validation.

        WHY: Buffer must be positive.
        """
        with pytest.raises(ValueError, match="buffer_size must be > 0"):
            TCPProxy(
                listen_host="0.0.0.0",
                listen_port=5502,
                target_host="localhost",
                target_port=502,
                buffer_size=0,
            )

    def test_init_validates_timeout(self):
        """Test timeout validation.

        WHY: Timeout must be positive.
        """
        with pytest.raises(ValueError, match="timeout must be > 0"):
            TCPProxy(
                listen_host="0.0.0.0",
                listen_port=5502,
                target_host="localhost",
                target_port=502,
                timeout=0,
            )


# ================================================================
# LIFECYCLE TESTS
# ================================================================
class TestTCPProxyLifecycle:
    """Test lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_creates_server(self, echo_server):
        """Test starting creates TCP server.

        WHY: Server must be running to accept connections.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15700,
            target_host="127.0.0.1",
            target_port=echo_server["port"],
        )

        await proxy.start()

        try:
            assert proxy.server is not None
            assert proxy.server.is_serving()
        finally:
            await proxy.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_server(self, echo_server):
        """Test stopping closes TCP server.

        WHY: Resources must be cleaned up.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15701,
            target_host="127.0.0.1",
            target_port=echo_server["port"],
        )

        await proxy.start()
        await proxy.stop()

        assert not proxy.server.is_serving()

    @pytest.mark.asyncio
    async def test_stop_without_start(self):
        """Test stopping without starting is safe.

        WHY: Should not raise.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15702,
            target_host="127.0.0.1",
            target_port=502,
        )

        # Should not raise
        await proxy.stop()

    @pytest.mark.asyncio
    async def test_start_port_in_use_raises(self, echo_server):
        """Test starting on used port raises OSError.

        WHY: Should report binding failure.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=echo_server["port"],  # Already in use
            target_host="127.0.0.1",
            target_port=502,
        )

        with pytest.raises(OSError):
            await proxy.start()


# ================================================================
# PROXYING TESTS
# ================================================================
class TestTCPProxyProxying:
    """Test data proxying."""

    @pytest.mark.asyncio
    async def test_proxy_data_to_target(self, echo_server):
        """Test data is proxied to target.

        WHY: Core proxy functionality.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15703,
            target_host="127.0.0.1",
            target_port=echo_server["port"],
        )

        await proxy.start()

        try:
            # Connect through proxy
            reader, writer = await asyncio.open_connection("127.0.0.1", 15703)

            # Send data
            writer.write(b"Hello, World!")
            await writer.drain()

            # Read echoed data
            data = await asyncio.wait_for(reader.read(1024), timeout=1.0)

            assert data == b"Hello, World!"

            writer.close()
            await writer.wait_closed()

        finally:
            await proxy.stop()

    @pytest.mark.asyncio
    async def test_proxy_multiple_messages(self, echo_server):
        """Test multiple messages are proxied.

        WHY: Proxy should handle message streams.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15704,
            target_host="127.0.0.1",
            target_port=echo_server["port"],
        )

        await proxy.start()

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", 15704)

            for i in range(5):
                msg = f"Message {i}".encode()
                writer.write(msg)
                await writer.drain()

                data = await asyncio.wait_for(reader.read(1024), timeout=1.0)
                assert data == msg

            writer.close()
            await writer.wait_closed()

        finally:
            await proxy.stop()

    @pytest.mark.asyncio
    async def test_proxy_large_data(self, echo_server):
        """Test large data is proxied correctly.

        WHY: Should handle data larger than buffer.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15705,
            target_host="127.0.0.1",
            target_port=echo_server["port"],
            buffer_size=1024,  # Small buffer
        )

        await proxy.start()

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", 15705)

            # Send data larger than buffer
            large_data = b"X" * 10000
            writer.write(large_data)
            await writer.drain()

            # Read all echoed data
            received = b""
            while len(received) < len(large_data):
                chunk = await asyncio.wait_for(reader.read(8192), timeout=1.0)
                if not chunk:
                    break
                received += chunk

            assert received == large_data

            writer.close()
            await writer.wait_closed()

        finally:
            await proxy.stop()

    @pytest.mark.asyncio
    async def test_proxy_tracks_bytes_proxied(self, echo_server):
        """Test bytes_proxied is tracked.

        WHY: Need metrics for monitoring.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15706,
            target_host="127.0.0.1",
            target_port=echo_server["port"],
        )

        await proxy.start()

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", 15706)

            writer.write(b"Hello")
            await writer.drain()

            await asyncio.wait_for(reader.read(1024), timeout=1.0)

            writer.close()
            await writer.wait_closed()

            # Wait for cleanup
            await asyncio.sleep(0.1)

            # Should have proxied data in both directions
            assert proxy.bytes_proxied >= 10  # "Hello" * 2

        finally:
            await proxy.stop()


# ================================================================
# CONNECTION TRACKING TESTS
# ================================================================
class TestTCPProxyConnectionTracking:
    """Test connection tracking."""

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_tracks_total_connections(self, echo_server):
        """Test total_connections is tracked.

        WHY: Need connection metrics.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15707,
            target_host="127.0.0.1",
            target_port=echo_server["port"],
        )

        await proxy.start()

        try:
            assert proxy.total_connections == 0

            # Make connections
            for _ in range(3):
                reader, writer = await asyncio.open_connection("127.0.0.1", 15707)
                await asyncio.sleep(0.05)
                writer.close()
                await writer.wait_closed()

            await asyncio.sleep(0.1)

            assert proxy.total_connections == 3

        finally:
            await proxy.stop()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_tracks_active_connections(self, delayed_echo_server):
        """Test active_connections is tracked.

        WHY: Need to know current load.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15708,
            target_host="127.0.0.1",
            target_port=delayed_echo_server["port"],
        )

        await proxy.start()

        try:
            assert proxy.active_connections == 0

            # Make multiple concurrent connections
            writers = []
            for _ in range(3):
                _, writer = await asyncio.open_connection("127.0.0.1", 15708)
                writers.append(writer)

            await asyncio.sleep(0.1)

            # All should be active
            assert proxy.active_connections == 3

            # Close connections
            for writer in writers:
                writer.close()
                await writer.wait_closed()

            await asyncio.sleep(0.2)

            # None should be active
            assert proxy.active_connections == 0

        finally:
            await proxy.stop()


# ================================================================
# SUMMARY TESTS
# ================================================================
class TestTCPProxySummary:
    """Test summary reporting."""

    def test_get_summary_structure(self):
        """Test summary structure.

        WHY: Used for monitoring.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15709,
            target_host="127.0.0.1",
            target_port=502,
        )

        summary = proxy.get_summary()

        assert "listen" in summary
        assert "target" in summary
        assert "active_connections" in summary
        assert "total_connections" in summary
        assert "bytes_proxied" in summary
        assert "running" in summary

    def test_get_summary_not_running(self):
        """Test summary when not running.

        WHY: Should indicate stopped state.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15710,
            target_host="127.0.0.1",
            target_port=502,
        )

        summary = proxy.get_summary()

        assert summary["running"] is False

    @pytest.mark.asyncio
    async def test_get_summary_running(self, echo_server):
        """Test summary when running.

        WHY: Should indicate running state.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15711,
            target_host="127.0.0.1",
            target_port=echo_server["port"],
        )

        await proxy.start()

        try:
            summary = proxy.get_summary()

            assert summary["running"] is True
            assert summary["listen"] == "127.0.0.1:15711"
            assert summary["target"] == f"127.0.0.1:{echo_server['port']}"

        finally:
            await proxy.stop()

    @pytest.mark.asyncio
    async def test_get_summary_after_stop(self, echo_server):
        """Test summary after stopping.

        WHY: Should indicate stopped state.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15712,
            target_host="127.0.0.1",
            target_port=echo_server["port"],
        )

        await proxy.start()
        await proxy.stop()

        summary = proxy.get_summary()

        assert summary["running"] is False


# ================================================================
# ERROR HANDLING TESTS
# ================================================================
class TestTCPProxyErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_target_connection_refused(self):
        """Test handling when target refuses connection.

        WHY: Should handle gracefully.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15713,
            target_host="127.0.0.1",
            target_port=59999,  # No server listening
        )

        await proxy.start()

        try:
            # Connect to proxy
            reader, writer = await asyncio.open_connection("127.0.0.1", 15713)

            # Give time for proxy to try connecting to target
            await asyncio.sleep(0.2)

            # Connection should be closed by proxy
            writer.close()
            await writer.wait_closed()

            # Proxy should still be running
            assert proxy.server.is_serving()

        finally:
            await proxy.stop()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_target_connection_timeout(self):
        """Test handling when target connection times out.

        WHY: Should handle gracefully.
        Note: This test takes ~0.7s due to timeout wait.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15714,
            target_host="10.255.255.1",  # Non-routable address
            target_port=502,
            timeout=0.5,  # Short timeout
        )

        await proxy.start()

        try:
            # Connect to proxy
            reader, writer = await asyncio.open_connection("127.0.0.1", 15714)

            # Wait for timeout
            await asyncio.sleep(0.7)

            writer.close()
            await writer.wait_closed()

            # Proxy should still be running
            assert proxy.server.is_serving()

        finally:
            await proxy.stop()

    @pytest.mark.asyncio
    async def test_client_disconnect_during_proxy(self, echo_server):
        """Test handling when client disconnects abruptly.

        WHY: Should handle gracefully.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15715,
            target_host="127.0.0.1",
            target_port=echo_server["port"],
        )

        await proxy.start()

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", 15715)

            # Send some data
            writer.write(b"Hello")
            await writer.drain()

            # Abrupt close
            writer.close()
            await writer.wait_closed()

            await asyncio.sleep(0.1)

            # Proxy should still be running
            assert proxy.server.is_serving()

        finally:
            await proxy.stop()


# ================================================================
# CONCURRENT CONNECTION TESTS
# ================================================================
class TestTCPProxyConcurrency:
    """Test concurrent connections."""

    @pytest.mark.asyncio
    async def test_multiple_concurrent_connections(self, echo_server):
        """Test handling multiple concurrent connections.

        WHY: Proxy should handle concurrent clients.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15716,
            target_host="127.0.0.1",
            target_port=echo_server["port"],
        )

        await proxy.start()

        try:

            async def client_task(client_id: int):
                reader, writer = await asyncio.open_connection("127.0.0.1", 15716)

                for i in range(5):
                    msg = f"Client {client_id} Message {i}".encode()
                    writer.write(msg)
                    await writer.drain()

                    data = await asyncio.wait_for(reader.read(1024), timeout=1.0)
                    assert data == msg

                writer.close()
                await writer.wait_closed()

            # Run multiple clients concurrently
            await asyncio.gather(*[client_task(i) for i in range(5)])

            await asyncio.sleep(0.1)

            assert proxy.total_connections == 5

        finally:
            await proxy.stop()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_stop_with_active_connections(self, delayed_echo_server):
        """Test stopping with active connections.

        WHY: Should close connections gracefully.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15717,
            target_host="127.0.0.1",
            target_port=delayed_echo_server["port"],
        )

        await proxy.start()

        # Open connections
        writers = []
        for _ in range(3):
            _, writer = await asyncio.open_connection("127.0.0.1", 15717)
            writers.append(writer)

        await asyncio.sleep(0.1)

        # Stop with active connections
        await proxy.stop()

        # Clean up writers
        for writer in writers:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        assert not proxy.server.is_serving()


# ================================================================
# TASK CLEANUP TESTS
# ================================================================
class TestTCPProxyTaskCleanup:
    """Test task cleanup."""

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_connection_tasks_cleaned_up(self, echo_server):
        """Test connection tasks are removed after completion.

        WHY: Prevent memory leaks from accumulated tasks.
        """
        proxy = TCPProxy(
            listen_host="127.0.0.1",
            listen_port=15718,
            target_host="127.0.0.1",
            target_port=echo_server["port"],
        )

        await proxy.start()

        try:
            # Make several connections
            for _ in range(5):
                reader, writer = await asyncio.open_connection("127.0.0.1", 15718)
                writer.write(b"test")
                await writer.drain()
                await reader.read(1024)
                writer.close()
                await writer.wait_closed()

            # Wait for cleanup
            await asyncio.sleep(0.2)

            # Task set should be empty
            assert len(proxy._connection_tasks) == 0

        finally:
            await proxy.stop()
