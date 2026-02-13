# tests/unit/network/test_opcua_server.py
"""
Unit tests for OPCUAServer.

Tests the OPC UA protocol server that opens real network ports
for ICS attack demonstrations.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


# Mock asyncua before importing OPCUAServer
@pytest.fixture(autouse=True)
def mock_opcua_adapter():
    """Mock OPC UA adapter for all tests."""
    mock_adapter_class = MagicMock()
    mock_adapter_instance = Mock()
    mock_adapter_instance.connect = AsyncMock(return_value=True)
    mock_adapter_instance.disconnect = AsyncMock()
    mock_adapter_instance.set_variable = AsyncMock()
    mock_adapter_instance.read_node = AsyncMock()
    mock_adapter_instance._running = False
    mock_adapter_class.return_value = mock_adapter_instance

    with (
        patch("components.network.servers.opcua_server.OPCUA_AVAILABLE", True),
        patch(
            "components.network.servers.opcua_server.OPCUAAsyncua118Adapter",
            mock_adapter_class,
        ),
    ):
        yield mock_adapter_class, mock_adapter_instance


from components.network.servers.opcua_server import OPCUAServer  # noqa: E402


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestOPCUAServerInitialization:
    """Test OPCUAServer initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters.

        WHY: Server should have sensible defaults.
        """
        server = OPCUAServer()

        assert server.endpoint == "opc.tcp://127.0.0.1:4840/"
        assert server.host == "127.0.0.1"
        assert server.port == 4840
        assert server.namespace_uri == "urn:simulator:opcua"
        assert server.security_policy == "None"
        assert server.allow_anonymous is True
        assert server.running is False

    def test_init_with_custom_params(self):
        """Test initialization with custom parameters.

        WHY: Should support custom configuration.
        """
        server = OPCUAServer(
            endpoint="opc.tcp://127.0.0.1:4841/",
            namespace_uri="urn:custom:opcua",
            security_policy="Basic256Sha256",
            certificate_path="/path/to/cert.pem",
            private_key_path="/path/to/key.pem",
            allow_anonymous=False,
        )

        assert server.endpoint == "opc.tcp://127.0.0.1:4841/"
        assert server.host == "127.0.0.1"
        assert server.port == 4841
        assert server.namespace_uri == "urn:custom:opcua"
        assert server.security_policy == "Basic256Sha256"
        assert server.certificate_path == "/path/to/cert.pem"
        assert server.private_key_path == "/path/to/key.pem"
        assert server.allow_anonymous is False


# ================================================================
# LIFECYCLE TESTS
# ================================================================
class TestOPCUAServerLifecycle:
    """Test OPCUAServer start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_success(self, mock_opcua_adapter):
        """Test successful server start.

        WHY: Must start OPC UA server and bind to port.
        """
        _mock_class, mock_instance = mock_opcua_adapter
        mock_instance.connect.return_value = True

        server = OPCUAServer()
        result = await server.start()

        assert result is True
        assert server.running is True
        mock_instance.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_when_already_running(self, mock_opcua_adapter):
        """Test starting when already running.

        WHY: Should return True immediately without restart.
        """
        server = OPCUAServer()
        server._running = True

        result = await server.start()

        assert result is True

    @pytest.mark.asyncio
    async def test_start_creates_adapter(self, mock_opcua_adapter):
        """Test that start creates adapter with correct config.

        WHY: Adapter must be initialized with server configuration.
        """
        mock_class, mock_instance = mock_opcua_adapter
        mock_instance.connect.return_value = True

        server = OPCUAServer(
            endpoint="opc.tcp://127.0.0.1:4841/",
            namespace_uri="urn:test:opcua",
            security_policy="Basic256Sha256",
        )
        await server.start()

        # Verify adapter was created with correct parameters
        mock_class.assert_called_once()
        call_kwargs = mock_class.call_args.kwargs
        assert call_kwargs["endpoint"] == "opc.tcp://127.0.0.1:4841/"
        assert call_kwargs["namespace_uri"] == "urn:test:opcua"
        assert call_kwargs["security_policy"] == "Basic256Sha256"
        assert call_kwargs["simulator_mode"] is True

    @pytest.mark.asyncio
    async def test_start_retries_on_failure(self, mock_opcua_adapter):
        """Test start retries on temporary failures.

        WHY: Port might be temporarily unavailable.
        """
        _mock_class, mock_instance = mock_opcua_adapter
        # Fail twice, succeed on third attempt
        mock_instance.connect.side_effect = [False, False, True]

        server = OPCUAServer()
        result = await server.start()

        assert result is True
        assert mock_instance.connect.await_count == 3

    @pytest.mark.asyncio
    async def test_start_fails_after_max_retries(self, mock_opcua_adapter):
        """Test start fails after exhausting retries.

        WHY: Should give up if port permanently unavailable.
        """
        _mock_class, mock_instance = mock_opcua_adapter
        mock_instance.connect.return_value = False

        server = OPCUAServer()
        result = await server.start()

        assert result is False
        assert server.running is False
        assert mock_instance.connect.await_count == 3  # max_retries

    @pytest.mark.asyncio
    async def test_stop_when_running(self, mock_opcua_adapter):
        """Test stopping running server.

        WHY: Must cleanly shut down and release port.
        """
        _mock_class, mock_instance = mock_opcua_adapter
        mock_instance.connect.return_value = True

        server = OPCUAServer()
        await server.start()
        await server.stop()

        assert server.running is False
        assert server._adapter is None
        mock_instance.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self, mock_opcua_adapter):
        """Test stopping when not running.

        WHY: Should handle gracefully without errors.
        """
        server = OPCUAServer()
        await server.stop()  # Should not raise

        assert server.running is False


# ================================================================
# DEVICE SYNC TESTS
# ================================================================
class TestOPCUAServerDeviceSync:
    """Test device synchronization methods."""

    @pytest.mark.asyncio
    async def test_sync_from_device(self, mock_opcua_adapter):
        """Test syncing data from device to server.

        WHY: Process variables from device must appear in OPC UA.
        """
        _mock_class, mock_instance = mock_opcua_adapter
        mock_instance.connect.return_value = True

        server = OPCUAServer()
        await server.start()

        # Sync variables
        data = {"Temperature": 45.2, "Pressure": 1.013, "Level": 75.0}
        await server.sync_from_device(data, "variables")

        # Verify set_variable called for each variable
        assert mock_instance.set_variable.await_count == 3
        mock_instance.set_variable.assert_any_await("Temperature", 45.2)
        mock_instance.set_variable.assert_any_await("Pressure", 1.013)
        mock_instance.set_variable.assert_any_await("Level", 75.0)

    @pytest.mark.asyncio
    async def test_sync_from_device_when_not_running(self, mock_opcua_adapter):
        """Test sync when server not running.

        WHY: Should handle gracefully without errors.
        """
        server = OPCUAServer()

        # Should not raise
        await server.sync_from_device({"Temperature": 45.2}, "variables")

    @pytest.mark.asyncio
    async def test_sync_from_device_handles_errors(self, mock_opcua_adapter):
        """Test sync handles adapter errors gracefully.

        WHY: Adapter might fail to set variables.
        """
        _mock_class, mock_instance = mock_opcua_adapter
        mock_instance.connect.return_value = True
        mock_instance.set_variable.side_effect = Exception("Node not found")

        server = OPCUAServer()
        await server.start()

        # Should not raise
        await server.sync_from_device({"Temperature": 45.2}, "variables")

    @pytest.mark.asyncio
    async def test_sync_to_device(self, mock_opcua_adapter):
        """Test syncing data from server to device.

        WHY: Commands from attacker via OPC UA must reach device.
        """
        _mock_class, mock_instance = mock_opcua_adapter
        mock_instance.connect.return_value = True
        mock_instance.read_node.side_effect = [45.2, 1.013, 75.0]

        server = OPCUAServer()
        await server.start()

        # Read variables
        result = await server.sync_to_device(
            ["Temperature", "Pressure", "Level"], "variables"
        )

        assert len(result) == 3
        assert result["Temperature"] == 45.2
        assert result["Pressure"] == 1.013
        assert result["Level"] == 75.0

    @pytest.mark.asyncio
    async def test_sync_to_device_filters_none_values(self, mock_opcua_adapter):
        """Test sync filters out None values.

        WHY: None indicates node doesn't exist or can't be read.
        """
        _mock_class, mock_instance = mock_opcua_adapter
        mock_instance.connect.return_value = True
        mock_instance.read_node.side_effect = [45.2, None, 75.0]

        server = OPCUAServer()
        await server.start()

        result = await server.sync_to_device(
            ["Temperature", "Pressure", "Level"], "variables"
        )

        assert len(result) == 2
        assert "Temperature" in result
        assert "Pressure" not in result
        assert "Level" in result

    @pytest.mark.asyncio
    async def test_sync_to_device_when_not_running(self, mock_opcua_adapter):
        """Test sync when server not running.

        WHY: Should return empty dict gracefully.
        """
        server = OPCUAServer()

        result = await server.sync_to_device(["Temperature"], "variables")

        assert result == {}

    @pytest.mark.asyncio
    async def test_sync_to_device_handles_errors(self, mock_opcua_adapter):
        """Test sync handles adapter errors gracefully.

        WHY: Adapter might fail to read nodes.
        """
        _mock_class, mock_instance = mock_opcua_adapter
        mock_instance.connect.return_value = True
        mock_instance.read_node.side_effect = Exception("Connection lost")

        server = OPCUAServer()
        await server.start()

        result = await server.sync_to_device(["Temperature"], "variables")

        assert result == {}


# ================================================================
# STATUS TESTS
# ================================================================
class TestOPCUAServerStatus:
    """Test server status methods."""

    def test_get_status_when_not_running(self, mock_opcua_adapter):
        """Test getting status when server not running.

        WHY: Status should be available even when stopped.
        """
        server = OPCUAServer(
            endpoint="opc.tcp://127.0.0.1:4841/", namespace_uri="urn:test:opcua"
        )

        status = server.get_status()

        assert status["running"] is False
        assert status["endpoint"] == "opc.tcp://127.0.0.1:4841/"
        assert status["namespace_uri"] == "urn:test:opcua"

    @pytest.mark.asyncio
    async def test_get_status_when_running(self, mock_opcua_adapter):
        """Test getting status when server running.

        WHY: Status should include adapter state when running.
        """
        _mock_class, mock_instance = mock_opcua_adapter
        mock_instance.connect.return_value = True
        mock_instance._running = True

        server = OPCUAServer()
        await server.start()

        status = server.get_status()

        assert status["running"] is True
        assert status["adapter_running"] is True


# ================================================================
# LIBRARY UNAVAILABLE TESTS
# ================================================================
class TestOPCUAServerWithoutLibrary:
    """Test behavior when asyncua library is not available."""

    @pytest.mark.asyncio
    async def test_start_without_asyncua(self):
        """Test starting server when asyncua not available.

        WHY: Should fail gracefully with clear error message.
        """
        with patch("components.network.servers.opcua_server.OPCUA_AVAILABLE", False):
            server = OPCUAServer()
            result = await server.start()

            assert result is False
            assert server.running is False
