# tests/unit/protocols/test_pymodbus_3114.py
"""
Unit tests for PyModbus3114Adapter.

Tests the Modbus TCP adapter using pymodbus 3.11.4.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from components.protocols.modbus.pymodbus_3114 import PyModbus3114Adapter


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
def adapter():
    """Create PyModbus3114Adapter instance."""
    return PyModbus3114Adapter(
        host="192.168.1.100",
        port=502,
        device_id=1,
    )


@pytest.fixture
def mock_client():
    """Create a mock pymodbus TCP client."""
    client = Mock()
    client.connect = AsyncMock(return_value=True)
    client.close = Mock()
    client.read_coils = AsyncMock()
    client.read_discrete_inputs = AsyncMock()
    client.read_holding_registers = AsyncMock()
    client.read_input_registers = AsyncMock()
    client.write_coil = AsyncMock()
    client.write_register = AsyncMock()
    client.write_coils = AsyncMock()
    client.write_registers = AsyncMock()
    return client


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestPyModbus3114Initialization:
    """Test PyModbus3114Adapter initialization."""

    def test_init_with_parameters(self):
        """Test initialization with all parameters."""
        adapter = PyModbus3114Adapter(
            host="10.0.0.1",
            port=5020,
            device_id=5,
        )

        assert adapter.host == "10.0.0.1"
        assert adapter.port == 5020
        assert adapter.device_id == 5
        assert adapter.client is None
        assert adapter.connected is False

    def test_init_default_port(self):
        """Test initialization uses standard Modbus port."""
        adapter = PyModbus3114Adapter(
            host="192.168.1.10",
            port=502,
            device_id=1,
        )

        assert adapter.port == 502


# ================================================================
# CONNECTION LIFECYCLE TESTS
# ================================================================
class TestPyModbus3114Lifecycle:
    """Test PyModbus3114Adapter connection lifecycle."""

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_connect_creates_client(self, mock_client_class, adapter):
        """Test connect creates and connects client."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client_class.return_value = mock_client

        result = await adapter.connect()

        assert result is True
        assert adapter.connected is True
        assert adapter.client == mock_client
        mock_client_class.assert_called_once_with(host="192.168.1.100", port=502)
        assert mock_client.unit_id == 1
        mock_client.connect.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_connect_reuses_existing_client(self, mock_client_class, adapter):
        """Test connect reuses existing client if already created."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client_class.return_value = mock_client

        # First connect
        await adapter.connect()
        first_client = adapter.client

        # Second connect should reuse client
        mock_client_class.reset_mock()
        await adapter.connect()

        assert adapter.client == first_client
        mock_client_class.assert_not_called()  # Should not create new client

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_connect_failure(self, mock_client_class, adapter):
        """Test connect handles connection failure."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = await adapter.connect()

        assert result is False
        assert adapter.connected is False

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_disconnect(self, mock_client_class, adapter):
        """Test disconnect closes client."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = Mock()
        mock_client_class.return_value = mock_client

        # Connect then disconnect
        await adapter.connect()
        await adapter.disconnect()

        assert adapter.connected is False
        assert adapter.client is None
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, adapter):
        """Test disconnect handles case when not connected."""
        # Should not raise
        await adapter.disconnect()

        assert adapter.connected is False
        assert adapter.client is None


# ================================================================
# READ OPERATIONS TESTS
# ================================================================
class TestPyModbus3114ReadOperations:
    """Test PyModbus3114Adapter read operations."""

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_read_coils(self, mock_client_class, adapter):
        """Test reading coils."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.read_coils = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        result = await adapter.read_coils(10, count=5)

        assert result == mock_response
        mock_client.read_coils.assert_awaited_once_with(10, count=5)

    @pytest.mark.asyncio
    async def test_read_coils_without_connection_raises(self, adapter):
        """Test reading coils without connection raises error."""
        with pytest.raises(RuntimeError, match="Client not connected"):
            await adapter.read_coils(0)

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_read_discrete_inputs(self, mock_client_class, adapter):
        """Test reading discrete inputs."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.read_discrete_inputs = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        result = await adapter.read_discrete_inputs(20, count=3)

        assert result == mock_response
        mock_client.read_discrete_inputs.assert_awaited_once_with(20, count=3)

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_read_holding_registers(self, mock_client_class, adapter):
        """Test reading holding registers."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.read_holding_registers = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        result = await adapter.read_holding_registers(100, count=10)

        assert result == mock_response
        mock_client.read_holding_registers.assert_awaited_once_with(100, count=10)

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_read_input_registers(self, mock_client_class, adapter):
        """Test reading input registers."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.read_input_registers = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        result = await adapter.read_input_registers(50, count=2)

        assert result == mock_response
        mock_client.read_input_registers.assert_awaited_once_with(50, count=2)


# ================================================================
# WRITE OPERATIONS TESTS
# ================================================================
class TestPyModbus3114WriteOperations:
    """Test PyModbus3114Adapter write operations."""

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_write_coil(self, mock_client_class, adapter):
        """Test writing a single coil."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.write_coil = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        result = await adapter.write_coil(15, True)

        assert result == mock_response
        mock_client.write_coil.assert_awaited_once_with(15, True)

    @pytest.mark.asyncio
    async def test_write_coil_without_connection_raises(self, adapter):
        """Test writing coil without connection raises error."""
        with pytest.raises(RuntimeError, match="Client not connected"):
            await adapter.write_coil(0, False)

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_write_register(self, mock_client_class, adapter):
        """Test writing a single register."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.write_register = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        result = await adapter.write_register(200, 42)

        assert result == mock_response
        mock_client.write_register.assert_awaited_once_with(200, 42)

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_write_multiple_coils(self, mock_client_class, adapter):
        """Test writing multiple coils."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.write_coils = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        values = [True, False, True, True]
        result = await adapter.write_multiple_coils(10, values)

        assert result == mock_response
        mock_client.write_coils.assert_awaited_once_with(10, values)

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_write_multiple_registers(self, mock_client_class, adapter):
        """Test writing multiple registers."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.write_registers = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        values = [100, 200, 300, 400]
        result = await adapter.write_multiple_registers(50, values)

        assert result == mock_response
        mock_client.write_registers.assert_awaited_once_with(50, values)


# ================================================================
# PROBE TESTS
# ================================================================
class TestPyModbus3114Probe:
    """Test PyModbus3114Adapter probe functionality."""

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_probe_returns_connection_info(self, mock_client_class, adapter):
        """Test probe returns transport and connection details."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        result = await adapter.probe()

        assert result["transport"] == "modbus-tcp"
        assert result["host"] == "192.168.1.100"
        assert result["port"] == 502
        assert result["device_id"] == 1
        assert result["connected"] is True

    @pytest.mark.asyncio
    async def test_probe_when_not_connected(self, adapter):
        """Test probe shows not connected status."""
        result = await adapter.probe()

        assert result["connected"] is False


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestPyModbus3114Integration:
    """Test PyModbus3114Adapter end-to-end scenarios."""

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.pymodbus_3114.AsyncModbusTcpClient")
    async def test_full_workflow(self, mock_client_class, adapter):
        """Test complete workflow: connect, read, write, disconnect."""
        # Setup mock client
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = Mock()
        mock_client.read_coils = AsyncMock(return_value=Mock())
        mock_client.write_coil = AsyncMock(return_value=Mock())
        mock_client_class.return_value = mock_client

        # 1. Connect
        connected = await adapter.connect()
        assert connected is True

        # 2. Read coils
        await adapter.read_coils(0, count=10)
        mock_client.read_coils.assert_awaited_once()

        # 3. Write coil
        await adapter.write_coil(5, True)
        mock_client.write_coil.assert_awaited_once()

        # 4. Disconnect
        await adapter.disconnect()
        assert adapter.connected is False
        mock_client.close.assert_called_once()
