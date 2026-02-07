"""Comprehensive tests for DNP3Adapter.

DNP3Adapter provides async interface to dnp3py library for both outstation (server)
and master (client) modes.

Test Coverage:
- Initialization and configuration
- Outstation mode lifecycle
- Master mode lifecycle
- Database operations (binary inputs, analog inputs, counters)
- Connection state management
- Simulator mode vs real mode
- Memory map updates
- Read/write operations
- Error handling and resilience
- Probe functionality

Tests use mocking for dnp3py components to avoid real network connections.
"""

import asyncio
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from components.protocols.dnp3.dnp3_adapter import DNP3Adapter


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
def mock_database():
    """Mock dnp3py Database.

    WHY: Avoid real database initialization.
    """
    database = Mock()
    database.binary_inputs = {}
    database.analog_inputs = {}
    database.counters = {}
    database.add_binary_input = Mock()
    database.add_analog_input = Mock()
    database.add_counter = Mock()
    database.update_binary_input = Mock()
    database.update_analog_input = Mock()
    database.update_counter = Mock()
    return database


@pytest.fixture
def mock_outstation():
    """Mock dnp3py Outstation.

    WHY: Avoid real outstation initialization.
    """
    return Mock()


@pytest.fixture
def mock_tcp_server():
    """Mock dnp3py TcpServer.

    WHY: Avoid real TCP server.
    """
    server = Mock()
    server.start = AsyncMock()
    server.stop = AsyncMock()
    return server


@pytest.fixture
def mock_master():
    """Mock dnp3py Master.

    WHY: Avoid real master initialization.
    """
    return Mock()


@pytest.fixture
def mock_tcp_client():
    """Mock dnp3py TcpClientChannel.

    WHY: Avoid real TCP client connections.
    """
    client = Mock()
    client.open = AsyncMock()
    client.close = AsyncMock()
    return client


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestDNP3AdapterInitialization:
    """Test adapter initialization and configuration."""

    def test_init_default_outstation_mode(self):
        """Test initialization with default outstation mode.

        WHY: Default mode should be outstation (server).
        """
        adapter = DNP3Adapter()
        assert adapter.mode == "outstation"
        assert adapter.host == "0.0.0.0"
        assert adapter.port == 20000
        assert adapter.simulator_mode is True
        assert not adapter.connected

    def test_init_master_mode(self):
        """Test initialization in master mode.

        WHY: Support both outstation and master modes.
        """
        adapter = DNP3Adapter(mode="master")
        assert adapter.mode == "master"

    def test_init_custom_host_port(self):
        """Test initialization with custom host and port.

        WHY: Support flexible network configuration.
        """
        adapter = DNP3Adapter(host="192.168.1.100", port=20001)
        assert adapter.host == "192.168.1.100"
        assert adapter.port == 20001

    def test_init_non_simulator_mode(self):
        """Test initialization in non-simulator mode.

        WHY: Support real network operations.
        """
        adapter = DNP3Adapter(simulator_mode=False)
        assert adapter.simulator_mode is False

    def test_init_with_setup_data(self):
        """Test initialization with initial setup data.

        WHY: Pre-configure database points.
        """
        setup = {
            "binary_inputs": {0: True, 1: False},
            "analog_inputs": {0: 123.45},
            "counters": {0: 100},
        }
        adapter = DNP3Adapter(setup=setup)
        assert adapter.setup == setup
        assert adapter.setup["binary_inputs"][0] is True
        assert adapter.setup["analog_inputs"][0] == 123.45
        assert adapter.setup["counters"][0] == 100

    def test_init_default_setup(self):
        """Test initialization creates empty setup structure.

        WHY: Default to empty database.
        """
        adapter = DNP3Adapter()
        assert "binary_inputs" in adapter.setup
        assert "analog_inputs" in adapter.setup
        assert "counters" in adapter.setup
        assert adapter.setup["binary_inputs"] == {}
        assert adapter.setup["analog_inputs"] == {}
        assert adapter.setup["counters"] == {}

    def test_init_state_defaults(self):
        """Test initial state values.

        WHY: Adapter starts in clean state.
        """
        adapter = DNP3Adapter()
        assert not adapter.connected
        assert isinstance(adapter.received_data, defaultdict)
        assert adapter.database is None
        assert adapter.outstation is None
        assert adapter.server is None
        assert adapter.master is None
        assert adapter.client_channel is None


# ================================================================
# OUTSTATION MODE TESTS
# ================================================================
class TestDNP3AdapterOutstationMode:
    """Test outstation (server) mode functionality."""

    @pytest.mark.asyncio
    @patch("components.protocols.dnp3.dnp3_adapter.Database")
    @patch("components.protocols.dnp3.dnp3_adapter.Outstation")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpServer")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpServerConfig")
    @patch("asyncio.to_thread")
    async def test_start_outstation_creates_database(
        self,
        mock_to_thread,
        mock_server_config,
        mock_tcp_server_class,
        mock_outstation_class,
        mock_database_class,
    ):
        """Test that start_outstation creates and initializes database.

        WHY: Database stores DNP3 points.
        """
        mock_to_thread.return_value = None
        mock_database = Mock()
        mock_database_class.return_value = mock_database
        mock_server = Mock()
        mock_server.start = AsyncMock()
        mock_tcp_server_class.return_value = mock_server

        setup = {
            "binary_inputs": {0: True},
            "analog_inputs": {0: 123.45},
            "counters": {0: 100},
        }
        adapter = DNP3Adapter(setup=setup)

        await adapter.start_outstation()

        # Database created
        assert adapter.database is not None
        mock_database_class.assert_called_once()

        # Points added to database
        mock_database.add_binary_input.assert_called()
        mock_database.add_analog_input.assert_called()
        mock_database.add_counter.assert_called()

    @pytest.mark.asyncio
    @patch("components.protocols.dnp3.dnp3_adapter.Database")
    @patch("components.protocols.dnp3.dnp3_adapter.Outstation")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpServer")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpServerConfig")
    @patch("asyncio.to_thread")
    async def test_start_outstation_starts_server(
        self,
        mock_to_thread,
        mock_server_config,
        mock_tcp_server_class,
        mock_outstation_class,
        mock_database_class,
    ):
        """Test that start_outstation starts TCP server.

        WHY: Server listens for master connections.
        """
        mock_to_thread.return_value = None
        mock_database = Mock()
        mock_database_class.return_value = mock_database
        mock_server = Mock()
        mock_server.start = AsyncMock()
        mock_tcp_server_class.return_value = mock_server

        adapter = DNP3Adapter(host="127.0.0.1", port=20000)
        await adapter.start_outstation()

        # Server started
        mock_server.start.assert_called_once()
        assert adapter.connected is True

    @pytest.mark.asyncio
    @patch("components.protocols.dnp3.dnp3_adapter.Database")
    @patch("components.protocols.dnp3.dnp3_adapter.Outstation")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpServer")
    @patch("asyncio.to_thread")
    async def test_start_outstation_idempotent(
        self,
        mock_to_thread,
        mock_tcp_server_class,
        mock_outstation_class,
        mock_database_class,
    ):
        """Test that calling start_outstation twice is safe.

        WHY: Prevent double-start errors.
        """
        mock_to_thread.return_value = None
        mock_database = Mock()
        mock_database_class.return_value = mock_database
        mock_server = Mock()
        mock_server.start = AsyncMock()
        mock_tcp_server_class.return_value = mock_server

        adapter = DNP3Adapter()
        await adapter.start_outstation()
        outstation_ref = adapter.outstation

        # Start again
        await adapter.start_outstation()

        # Should still have same outstation (not recreated)
        assert adapter.outstation is outstation_ref

    @pytest.mark.asyncio
    async def test_stop_outstation_cleanup(self):
        """Test that stop_outstation cleans up resources.

        WHY: Proper cleanup prevents resource leaks.
        """
        adapter = DNP3Adapter()
        mock_server = Mock()
        mock_server.stop = AsyncMock()
        adapter.server = mock_server
        adapter.outstation = Mock()
        adapter.database = Mock()
        adapter.connected = True

        await adapter.stop_outstation()

        # Resources cleaned up
        mock_server.stop.assert_called_once()
        assert adapter.server is None
        assert adapter.outstation is None
        assert adapter.database is None
        assert not adapter.connected

    @pytest.mark.asyncio
    async def test_stop_outstation_when_not_started(self):
        """Test stopping outstation when not started.

        WHY: Should handle gracefully.
        """
        adapter = DNP3Adapter()
        await adapter.stop_outstation()  # Should not raise

        assert not adapter.connected


# ================================================================
# MASTER MODE TESTS
# ================================================================
class TestDNP3AdapterMasterMode:
    """Test master (client) mode functionality."""

    @pytest.mark.asyncio
    @patch("components.protocols.dnp3.dnp3_adapter.Master")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpClientChannel")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpConfig")
    @patch("components.protocols.dnp3.dnp3_adapter.DefaultSOEHandler")
    async def test_start_master_simulator_mode(
        self, mock_handler, mock_tcp_config, mock_client_class, mock_master_class
    ):
        """Test starting master in simulator mode.

        WHY: Simulator mode skips real network connection.
        """
        mock_master = Mock()
        mock_master_class.return_value = mock_master
        mock_client = Mock()
        mock_client.open = AsyncMock()
        mock_client_class.return_value = mock_client

        adapter = DNP3Adapter(mode="master", simulator_mode=True)
        await adapter.start_master()

        # Master created but no connection attempted
        assert adapter.master is not None
        assert adapter.client_channel is not None
        assert adapter.connected is True
        mock_client.open.assert_not_called()

    @pytest.mark.asyncio
    @patch("components.protocols.dnp3.dnp3_adapter.Master")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpClientChannel")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpConfig")
    @patch("components.protocols.dnp3.dnp3_adapter.DefaultSOEHandler")
    async def test_start_master_non_simulator_mode(
        self, mock_handler, mock_tcp_config, mock_client_class, mock_master_class
    ):
        """Test starting master in non-simulator mode.

        WHY: Non-simulator mode attempts real connection.
        """
        mock_master = Mock()
        mock_master_class.return_value = mock_master
        mock_client = Mock()
        mock_client.open = AsyncMock()
        mock_client_class.return_value = mock_client

        adapter = DNP3Adapter(mode="master", simulator_mode=False)
        await adapter.start_master()

        # Master created and connection attempted
        assert adapter.master is not None
        assert adapter.client_channel is not None
        assert adapter.connected is True
        mock_client.open.assert_called_once()

    @pytest.mark.asyncio
    @patch("components.protocols.dnp3.dnp3_adapter.Master")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpClientChannel")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpConfig")
    @patch("components.protocols.dnp3.dnp3_adapter.DefaultSOEHandler")
    async def test_start_master_idempotent(
        self, mock_handler, mock_tcp_config, mock_client_class, mock_master_class
    ):
        """Test that calling start_master twice is safe.

        WHY: Prevent double-start errors.
        """
        mock_master = Mock()
        mock_master_class.return_value = mock_master
        mock_client = Mock()
        mock_client.open = AsyncMock()
        mock_client_class.return_value = mock_client

        adapter = DNP3Adapter(mode="master", simulator_mode=True)
        await adapter.start_master()
        master_ref = adapter.master

        # Start again
        await adapter.start_master()

        # Should still have same master (not recreated)
        assert adapter.master is master_ref

    @pytest.mark.asyncio
    async def test_stop_master_cleanup(self):
        """Test that stop_master cleans up resources.

        WHY: Proper cleanup prevents resource leaks.
        """
        adapter = DNP3Adapter(mode="master")
        mock_client = Mock()
        mock_client.close = AsyncMock()
        adapter.client_channel = mock_client
        adapter.master = Mock()
        adapter.connected = True

        await adapter.stop_master()

        # Resources cleaned up
        mock_client.close.assert_called_once()
        assert adapter.master is None
        assert adapter.client_channel is None
        assert not adapter.connected


# ================================================================
# GENERIC CONNECT/DISCONNECT TESTS
# ================================================================
class TestDNP3AdapterConnectDisconnect:
    """Test generic connect/disconnect methods."""

    @pytest.mark.asyncio
    @patch("components.protocols.dnp3.dnp3_adapter.Database")
    @patch("components.protocols.dnp3.dnp3_adapter.Outstation")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpServer")
    @patch("asyncio.to_thread")
    async def test_connect_outstation_mode(
        self, mock_to_thread, mock_tcp_server, mock_outstation, mock_database
    ):
        """Test connect() in outstation mode.

        WHY: Generic connect routes to start_outstation.
        """
        mock_to_thread.return_value = None
        mock_db = Mock()
        mock_database.return_value = mock_db
        mock_server = Mock()
        mock_server.start = AsyncMock()
        mock_tcp_server.return_value = mock_server

        adapter = DNP3Adapter(mode="outstation")
        result = await adapter.connect()

        assert result is True
        assert adapter.connected

    @pytest.mark.asyncio
    @patch("components.protocols.dnp3.dnp3_adapter.Master")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpClientChannel")
    @patch("components.protocols.dnp3.dnp3_adapter.DefaultSOEHandler")
    async def test_connect_master_mode(self, mock_handler, mock_client, mock_master):
        """Test connect() in master mode.

        WHY: Generic connect routes to start_master.
        """
        mock_master.return_value = Mock()
        mock_client.return_value = Mock()

        adapter = DNP3Adapter(mode="master", simulator_mode=True)
        result = await adapter.connect()

        assert result is True
        assert adapter.connected

    @pytest.mark.asyncio
    async def test_disconnect_outstation_mode(self):
        """Test disconnect() in outstation mode.

        WHY: Generic disconnect routes to stop_outstation.
        """
        adapter = DNP3Adapter(mode="outstation")
        adapter.server = Mock()
        adapter.server.stop = AsyncMock()
        adapter.connected = True

        await adapter.disconnect()

        assert not adapter.connected

    @pytest.mark.asyncio
    async def test_disconnect_master_mode(self):
        """Test disconnect() in master mode.

        WHY: Generic disconnect routes to stop_master.
        """
        adapter = DNP3Adapter(mode="master")
        adapter.client_channel = Mock()
        adapter.client_channel.close = AsyncMock()
        adapter.connected = True

        await adapter.disconnect()

        assert not adapter.connected


# ================================================================
# DATABASE UPDATE TESTS
# ================================================================
class TestDNP3AdapterDatabaseUpdates:
    """Test database update operations (outstation mode)."""

    @pytest.mark.asyncio
    @patch("asyncio.to_thread")
    async def test_update_binary_input(self, mock_to_thread):
        """Test updating binary input value.

        WHY: Binary inputs represent digital points.
        """
        mock_to_thread.return_value = None
        adapter = DNP3Adapter()
        adapter.database = Mock()
        adapter.database.update_binary_input = Mock()

        await adapter.update_binary_input(5, True)

        # Database updated
        assert adapter.setup["binary_inputs"][5] is True

    @pytest.mark.asyncio
    async def test_update_binary_input_without_database(self):
        """Test updating binary input without database raises error.

        WHY: Database must be initialized first.
        """
        adapter = DNP3Adapter()
        adapter.database = None

        with pytest.raises(RuntimeError, match="Outstation not started"):
            await adapter.update_binary_input(0, True)

    @pytest.mark.asyncio
    @patch("asyncio.to_thread")
    async def test_update_analog_input(self, mock_to_thread):
        """Test updating analog input value.

        WHY: Analog inputs represent continuous values.
        """
        mock_to_thread.return_value = None
        adapter = DNP3Adapter()
        adapter.database = Mock()
        adapter.database.update_analog_input = Mock()

        await adapter.update_analog_input(3, 456.78)

        # Database updated
        assert adapter.setup["analog_inputs"][3] == 456.78

    @pytest.mark.asyncio
    async def test_update_analog_input_without_database(self):
        """Test updating analog input without database raises error.

        WHY: Database must be initialized first.
        """
        adapter = DNP3Adapter()
        adapter.database = None

        with pytest.raises(RuntimeError, match="Outstation not started"):
            await adapter.update_analog_input(0, 100.0)

    @pytest.mark.asyncio
    @patch("asyncio.to_thread")
    async def test_update_counter(self, mock_to_thread):
        """Test updating counter value.

        WHY: Counters track累积 values.
        """
        mock_to_thread.return_value = None
        adapter = DNP3Adapter()
        adapter.database = Mock()
        adapter.database.update_counter = Mock()

        await adapter.update_counter(2, 999)

        # Database updated
        assert adapter.setup["counters"][2] == 999

    @pytest.mark.asyncio
    async def test_update_counter_without_database(self):
        """Test updating counter without database raises error.

        WHY: Database must be initialized first.
        """
        adapter = DNP3Adapter()
        adapter.database = None

        with pytest.raises(RuntimeError, match="Outstation not started"):
            await adapter.update_counter(0, 100)


# ================================================================
# MASTER OPERATIONS TESTS
# ================================================================
class TestDNP3AdapterMasterOperations:
    """Test master mode read/write operations."""

    @pytest.mark.asyncio
    async def test_integrity_scan_without_master(self):
        """Test integrity scan without master raises error.

        WHY: Master must be connected first.
        """
        adapter = DNP3Adapter(mode="master")

        with pytest.raises(RuntimeError, match="Master not connected"):
            await adapter.integrity_scan()

    @pytest.mark.asyncio
    async def test_integrity_scan_returns_false(self):
        """Test integrity scan returns False (not implemented).

        WHY: TODO placeholder returns False.
        """
        adapter = DNP3Adapter(mode="master", simulator_mode=True)
        adapter.master = Mock()
        adapter.client_channel = Mock()

        result = await adapter.integrity_scan()
        assert result is False

    @pytest.mark.asyncio
    async def test_event_scan_without_master(self):
        """Test event scan without master raises error.

        WHY: Master must be connected first.
        """
        adapter = DNP3Adapter(mode="master")

        with pytest.raises(RuntimeError, match="Master not connected"):
            await adapter.event_scan()

    @pytest.mark.asyncio
    async def test_event_scan_returns_false(self):
        """Test event scan returns False (not implemented).

        WHY: TODO placeholder returns False.
        """
        adapter = DNP3Adapter(mode="master", simulator_mode=True)
        adapter.master = Mock()
        adapter.client_channel = Mock()

        result = await adapter.event_scan()
        assert result is False

    @pytest.mark.asyncio
    async def test_read_binary_inputs_without_master(self):
        """Test reading binary inputs without master raises error.

        WHY: Master must be connected first.
        """
        adapter = DNP3Adapter(mode="master")

        with pytest.raises(RuntimeError, match="Master not connected"):
            await adapter.read_binary_inputs(0, 10)

    @pytest.mark.asyncio
    async def test_read_binary_inputs_returns_empty(self):
        """Test reading binary inputs returns empty list (not implemented).

        WHY: TODO placeholder returns empty list.
        """
        adapter = DNP3Adapter(mode="master", simulator_mode=True)
        adapter.master = Mock()
        adapter.client_channel = Mock()

        result = await adapter.read_binary_inputs(0, 10)
        assert result == []

    @pytest.mark.asyncio
    async def test_read_analog_inputs_without_master(self):
        """Test reading analog inputs without master raises error.

        WHY: Master must be connected first.
        """
        adapter = DNP3Adapter(mode="master")

        with pytest.raises(RuntimeError, match="Master not connected"):
            await adapter.read_analog_inputs(0, 10)

    @pytest.mark.asyncio
    async def test_read_analog_inputs_returns_empty(self):
        """Test reading analog inputs returns empty list (not implemented).

        WHY: TODO placeholder returns empty list.
        """
        adapter = DNP3Adapter(mode="master", simulator_mode=True)
        adapter.master = Mock()
        adapter.client_channel = Mock()

        result = await adapter.read_analog_inputs(0, 10)
        assert result == []

    @pytest.mark.asyncio
    async def test_write_binary_output_without_master(self):
        """Test writing binary output without master raises error.

        WHY: Master must be connected first.
        """
        adapter = DNP3Adapter(mode="master")

        with pytest.raises(RuntimeError, match="Master not connected"):
            await adapter.write_binary_output(0, True)

    @pytest.mark.asyncio
    async def test_write_binary_output_returns_false(self):
        """Test writing binary output returns False (not implemented).

        WHY: TODO placeholder returns False.
        """
        adapter = DNP3Adapter(mode="master", simulator_mode=True)
        adapter.master = Mock()
        adapter.client_channel = Mock()

        result = await adapter.write_binary_output(5, True)
        assert result is False

    @pytest.mark.asyncio
    async def test_write_analog_output_without_master(self):
        """Test writing analog output without master raises error.

        WHY: Master must be connected first.
        """
        adapter = DNP3Adapter(mode="master")

        with pytest.raises(RuntimeError, match="Master not connected"):
            await adapter.write_analog_output(0, 100.0)

    @pytest.mark.asyncio
    async def test_write_analog_output_returns_false(self):
        """Test writing analog output returns False (not implemented).

        WHY: TODO placeholder returns False.
        """
        adapter = DNP3Adapter(mode="master", simulator_mode=True)
        adapter.master = Mock()
        adapter.client_channel = Mock()

        result = await adapter.write_analog_output(3, 567.89)
        assert result is False


# ================================================================
# PROBE TESTS
# ================================================================
class TestDNP3AdapterProbe:
    """Test probe/introspection functionality."""

    @pytest.mark.asyncio
    async def test_probe_returns_dict(self):
        """Test that probe() returns dictionary.

        WHY: Standard format for introspection.
        """
        adapter = DNP3Adapter()
        result = await adapter.probe()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_probe_includes_mode(self):
        """Test that probe() includes mode.

        WHY: Mode indicates outstation vs master.
        """
        adapter = DNP3Adapter(mode="master")
        result = await adapter.probe()
        assert result["mode"] == "master"

    @pytest.mark.asyncio
    async def test_probe_includes_network_info(self):
        """Test that probe() includes network configuration.

        WHY: Host and port identify endpoint.
        """
        adapter = DNP3Adapter(host="10.0.0.1", port=20001)
        result = await adapter.probe()
        assert result["host"] == "10.0.0.1"
        assert result["port"] == 20001

    @pytest.mark.asyncio
    async def test_probe_includes_simulator_flag(self):
        """Test that probe() includes simulator mode flag.

        WHY: Distinguishes real vs simulated operation.
        """
        adapter = DNP3Adapter(simulator_mode=False)
        result = await adapter.probe()
        assert result["simulator"] is False

    @pytest.mark.asyncio
    async def test_probe_includes_connection_state(self):
        """Test that probe() includes connection state.

        WHY: Indicates adapter availability.
        """
        adapter = DNP3Adapter()
        result = await adapter.probe()
        assert "connected" in result
        assert result["connected"] is False

    @pytest.mark.asyncio
    async def test_probe_includes_setup(self):
        """Test that probe() includes setup configuration.

        WHY: Exposes configured points.
        """
        setup = {
            "binary_inputs": {0: True, 1: False},
            "analog_inputs": {0: 123.45},
            "counters": {0: 100},
        }
        adapter = DNP3Adapter(setup=setup)
        result = await adapter.probe()
        assert result["setup"] == setup


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestDNP3AdapterIntegration:
    """Test integration scenarios."""

    @pytest.mark.asyncio
    @patch("components.protocols.dnp3.dnp3_adapter.Database")
    @patch("components.protocols.dnp3.dnp3_adapter.Outstation")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpServer")
    @patch("asyncio.to_thread")
    async def test_outstation_full_lifecycle(
        self, mock_to_thread, mock_tcp_server, mock_outstation, mock_database
    ):
        """Test complete outstation lifecycle.

        WHY: Verify end-to-end outstation workflow.
        """
        mock_to_thread.return_value = None
        mock_db = Mock()
        mock_database.return_value = mock_db
        mock_server = Mock()
        mock_server.start = AsyncMock()
        mock_server.stop = AsyncMock()
        mock_tcp_server.return_value = mock_server

        adapter = DNP3Adapter(mode="outstation")

        # Start
        success = await adapter.connect()
        assert success
        assert adapter.connected

        # Probe
        probe_result = await adapter.probe()
        assert probe_result["connected"] is True

        # Stop
        await adapter.disconnect()
        assert not adapter.connected

    @pytest.mark.asyncio
    @patch("components.protocols.dnp3.dnp3_adapter.Master")
    @patch("components.protocols.dnp3.dnp3_adapter.TcpClientChannel")
    @patch("components.protocols.dnp3.dnp3_adapter.DefaultSOEHandler")
    async def test_master_full_lifecycle(self, mock_handler, mock_client, mock_master):
        """Test complete master lifecycle.

        WHY: Verify end-to-end master workflow.
        """
        mock_master.return_value = Mock()
        mock_client_instance = Mock()
        mock_client_instance.close = AsyncMock()
        mock_client.return_value = mock_client_instance

        adapter = DNP3Adapter(mode="master", simulator_mode=True)

        # Start
        success = await adapter.connect()
        assert success
        assert adapter.connected

        # Probe
        probe_result = await adapter.probe()
        assert probe_result["connected"] is True
        assert probe_result["mode"] == "master"

        # Stop
        await adapter.disconnect()
        assert not adapter.connected
