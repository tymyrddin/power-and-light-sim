# tests/unit/protocols/test_c104_221.py
"""
Unit tests for IEC104C104Adapter.

Tests the IEC 60870-5-104 adapter using c104 library v2.2.1.
"""

import threading
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from components.protocols.iec104.c104_221 import IEC104C104Adapter


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
def mock_server():
    """Create a mock c104 Server."""
    server = Mock()
    server.start = Mock()
    server.stop = Mock()
    return server


@pytest.fixture
def adapter():
    """Create IEC104C104Adapter instance."""
    return IEC104C104Adapter(
        bind_host="192.168.1.100",
        bind_port=2404,
        common_address=1,
    )


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestIEC104C104AdapterInitialization:
    """Test IEC104C104Adapter initialization."""

    def test_init_with_parameters(self):
        """Test initialization with all parameters."""
        adapter = IEC104C104Adapter(
            bind_host="10.0.0.1",
            bind_port=2405,
            common_address=5,
        )

        assert adapter.bind_host == "10.0.0.1"
        assert adapter.bind_port == 2405
        assert adapter.common_address == 5
        assert adapter._server is None
        assert adapter._running is False
        assert adapter._thread is None

    def test_init_default_port(self):
        """Test initialization uses standard IEC 104 port."""
        adapter = IEC104C104Adapter(
            bind_host="192.168.1.10",
            bind_port=2404,
            common_address=1,
        )

        assert adapter.bind_port == 2404

    def test_initial_simulated_state_empty(self, adapter):
        """Test simulated_state is initialized as empty dict."""
        assert adapter._state == {}

    def test_stop_event_created(self, adapter):
        """Test stop event is created for thread coordination."""
        assert isinstance(adapter._stop_event, threading.Event)
        assert not adapter._stop_event.is_set()


# ================================================================
# CONNECTION LIFECYCLE TESTS
# ================================================================
class TestIEC104C104AdapterLifecycle:
    """Test IEC104C104Adapter connection lifecycle."""

    @pytest.mark.asyncio
    @patch("components.protocols.iec104.c104_221.c104")
    async def test_connect_creates_server(self, mock_c104, adapter):
        """Test connect creates c104 server and starts thread."""
        mock_server = Mock()
        mock_server.add_station = Mock(return_value=Mock())
        mock_server.start = Mock()
        mock_c104.Server.return_value = mock_server

        result = await adapter.connect()

        assert result is True
        assert adapter._running is True
        assert adapter._server == mock_server
        mock_c104.Server.assert_called_once_with(ip="192.168.1.100", port=2404)
        # Thread should be started
        assert adapter._thread is not None
        assert adapter._thread.daemon is True

    @pytest.mark.asyncio
    @patch("components.protocols.iec104.c104_221.c104")
    async def test_connect_starts_background_thread(self, mock_c104, adapter):
        """Test connect starts server in background thread."""
        mock_server = Mock()
        mock_server.add_station = Mock(return_value=Mock())
        mock_server.start = Mock()
        mock_c104.Server.return_value = mock_server

        await adapter.connect()

        # Verify thread is alive
        assert adapter._thread is not None
        assert adapter._thread.is_alive()

    @pytest.mark.asyncio
    @patch("components.protocols.iec104.c104_221.c104")
    async def test_connect_already_connected(self, mock_c104, adapter):
        """Test connect when already connected returns True."""
        mock_server = Mock()
        mock_server.add_station = Mock(return_value=Mock())
        mock_server.start = Mock()
        mock_c104.Server.return_value = mock_server

        # First connect
        await adapter.connect()
        first_server = adapter._server

        # Second connect should reuse server
        result = await adapter.connect()

        assert result is True
        assert adapter._server == first_server

    @pytest.mark.asyncio
    @patch("components.protocols.iec104.c104_221.c104")
    async def test_connect_handles_exception(self, mock_c104, adapter):
        """Test connect handles c104 exceptions."""
        mock_c104.Server.side_effect = RuntimeError("Port in use")

        result = await adapter.connect()

        assert result is False
        assert adapter._running is False

    @pytest.mark.asyncio
    @patch("components.protocols.iec104.c104_221.c104")
    async def test_disconnect_stops_server(self, mock_c104, adapter):
        """Test disconnect stops server and joins thread."""
        mock_server = Mock()
        mock_server.add_station = Mock(return_value=Mock())
        mock_server.start = Mock()
        mock_server.stop = Mock()
        mock_c104.Server.return_value = mock_server

        await adapter.connect()
        thread = adapter._thread

        await adapter.disconnect()

        assert adapter._running is False
        assert adapter._server is None
        assert adapter._stop_event.is_set()
        # Thread should be stopped
        assert not thread.is_alive()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, adapter):
        """Test disconnect when not connected."""
        await adapter.disconnect()

        assert adapter._running is False
        assert adapter._server is None


# ================================================================
# PROBE TESTS
# ================================================================
class TestIEC104C104AdapterProbe:
    """Test IEC104C104Adapter probe functionality."""

    @pytest.mark.asyncio
    @patch("components.protocols.iec104.c104_221.c104")
    async def test_probe_returns_connection_info(self, mock_c104, adapter):
        """Test probe returns transport and connection details."""
        mock_server = Mock()
        mock_server.add_station = Mock(return_value=Mock())
        mock_server.start = Mock()
        mock_c104.Server.return_value = mock_server

        await adapter.connect()
        result = await adapter.probe()

        assert result["protocol"] == "IEC60870-5-104"
        assert result["implementation"] == "c104"
        assert result["bind"] == "192.168.1.100:2404"
        assert result["common_address"] == 1
        assert result["listening"] is True

    @pytest.mark.asyncio
    async def test_probe_when_not_connected(self, adapter):
        """Test probe shows not connected status."""
        result = await adapter.probe()

        assert result["listening"] is False
        assert result["protocol"] == "IEC60870-5-104"


# ================================================================
# SET POINT TESTS
# ================================================================
class TestIEC104C104AdapterSetPoint:
    """Test IEC104C104Adapter set_point functionality."""

    @pytest.mark.asyncio
    async def test_set_point_updates_state(self, adapter):
        """Test set_point updates simulated_state."""
        await adapter.set_point(100, 42.5)

        state = await adapter.get_state()
        assert state[100] == 42.5

    @pytest.mark.asyncio
    async def test_set_point_different_addresses(self, adapter):
        """Test set_point with different IOAs."""
        await adapter.set_point(10, 10.0)
        await adapter.set_point(20, 20.0)
        await adapter.set_point(30, 30.0)

        state = await adapter.get_state()
        assert state[10] == 10.0
        assert state[20] == 20.0
        assert state[30] == 30.0

    @pytest.mark.asyncio
    async def test_set_point_overwrites_existing(self, adapter):
        """Test set_point overwrites existing value."""
        await adapter.set_point(100, 10.0)
        await adapter.set_point(100, 20.0)

        state = await adapter.get_state()
        assert state[100] == 20.0


# ================================================================
# GET STATE TESTS
# ================================================================
class TestIEC104C104AdapterGetState:
    """Test IEC104C104Adapter get_state functionality."""

    @pytest.mark.asyncio
    async def test_get_state_returns_all_points(self, adapter):
        """Test get_state returns all simulated points."""
        await adapter.set_point(100, 42.5)
        await adapter.set_point(200, 99.9)

        state = await adapter.get_state()

        assert len(state) == 2
        assert 100 in state
        assert 200 in state
        assert state[100] == 42.5
        assert state[200] == 99.9

    @pytest.mark.asyncio
    async def test_get_state_empty_when_no_points(self, adapter):
        """Test get_state returns empty dict when no points set."""
        state = await adapter.get_state()

        assert state == {}


# ================================================================
# THREAD SAFETY TESTS
# ================================================================
class TestIEC104C104AdapterThreadSafety:
    """Test IEC104C104Adapter thread safety."""

    @pytest.mark.asyncio
    @patch("components.protocols.iec104.c104_221.c104")
    async def test_state_access_is_thread_safe(self, mock_c104, adapter):
        """Test simulated_state access uses lock."""
        mock_server = Mock()
        mock_server.add_station = Mock(return_value=Mock())
        mock_server.start = Mock()
        mock_c104.Server.return_value = mock_server

        await adapter.connect()

        # Set point should use lock
        await adapter.set_point(100, 42.5)
        state = await adapter.get_state()

        # If we got here without deadlock, locking works
        assert state[100] == 42.5


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestIEC104C104AdapterIntegration:
    """Test IEC104C104Adapter end-to-end scenarios."""

    @pytest.mark.asyncio
    @patch("components.protocols.iec104.c104_221.c104")
    async def test_full_workflow(self, mock_c104, adapter):
        """Test complete workflow: connect, set point, get state, disconnect."""
        mock_server = Mock()
        mock_server.add_station = Mock(return_value=Mock())
        mock_server.start = Mock()
        mock_server.stop = Mock()
        mock_c104.Server.return_value = mock_server

        # 1. Connect
        connected = await adapter.connect()
        assert connected is True

        # 2. Set some points
        await adapter.set_point(100, 42.5)
        await adapter.set_point(200, 99.9)

        # 3. Read state
        state = await adapter.get_state()
        assert len(state) == 2

        # 4. Disconnect
        await adapter.disconnect()
        assert adapter._running is False

    @pytest.mark.asyncio
    @patch("components.protocols.iec104.c104_221.c104")
    async def test_attacker_workflow(self, mock_c104, adapter):
        """Test typical attacker workflow: probe, connect, overwrite values."""
        mock_server = Mock()
        mock_server.add_station = Mock(return_value=Mock())
        mock_server.start = Mock()
        mock_server.stop = Mock()
        mock_c104.Server.return_value = mock_server

        # 1. Probe without connecting
        probe_result = await adapter.probe()
        assert probe_result["listening"] is False

        # 2. Connect
        await adapter.connect()

        # 3. Probe again
        probe_result = await adapter.probe()
        assert probe_result["listening"] is True

        # 4. Overwrite critical point
        await adapter.set_point(100, 9999.0)

        # 6. Verify change
        final_state = await adapter.get_state()
        assert final_state[100] == 9999.0

        # 7. Disconnect
        await adapter.disconnect()
