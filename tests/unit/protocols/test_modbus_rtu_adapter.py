# tests/unit/protocols/test_modbus_rtu_adapter.py
"""
Unit tests for ModbusRTUAdapter.

Tests the Modbus RTU serial adapter using pymodbus 3.11.4.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from components.protocols.modbus.modbus_rtu_adapter import ModbusRTUAdapter


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
def adapter():
    """Create ModbusRTUAdapter instance with typical parameters."""
    return ModbusRTUAdapter(
        port="/dev/ttyUSB0",
        device_id=1,
        baudrate=9600,
        bytesize=8,
        parity="N",
        stopbits=1,
    )


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestModbusRTUAdapterInitialization:
    """Test ModbusRTUAdapter initialization."""

    def test_init_with_all_parameters(self):
        """Test initialization with all parameters."""
        adapter = ModbusRTUAdapter(
            port="/dev/ttyS1",
            device_id=5,
            baudrate=19200,
            bytesize=7,
            parity="E",
            stopbits=2,
        )

        assert adapter.port == "/dev/ttyS1"
        assert adapter.device_id == 5
        assert adapter.baudrate == 19200
        assert adapter.bytesize == 7
        assert adapter.parity == "E"
        assert adapter.stopbits == 2
        assert adapter.client is None
        assert adapter.connected is False

    def test_init_with_defaults(self):
        """Test initialization with default serial parameters."""
        adapter = ModbusRTUAdapter(
            port="/dev/ttyUSB0",
            device_id=1,
        )

        # Check defaults
        assert adapter.baudrate == 9600
        assert adapter.bytesize == 8
        assert adapter.parity == "N"
        assert adapter.stopbits == 1


# ================================================================
# CONNECTION LIFECYCLE TESTS
# ================================================================
class TestModbusRTUAdapterLifecycle:
    """Test ModbusRTUAdapter connection lifecycle."""

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
    async def test_connect_creates_serial_client(self, mock_client_class, adapter):
        """Test connect creates serial client with correct parameters."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client_class.return_value = mock_client

        result = await adapter.connect()

        assert result is True
        assert adapter.connected is True
        mock_client_class.assert_called_once_with(
            port="/dev/ttyUSB0",
            baudrate=9600,
            bytesize=8,
            parity="N",
            stopbits=1,
        )
        assert mock_client.unit_id == 1
        mock_client.connect.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
    async def test_connect_reuses_existing_client(self, mock_client_class, adapter):
        """Test connect reuses existing client."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client_class.return_value = mock_client

        # First connect
        await adapter.connect()
        first_client = adapter.client

        # Second connect
        mock_client_class.reset_mock()
        await adapter.connect()

        assert adapter.client == first_client
        mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
    async def test_connect_failure(self, mock_client_class, adapter):
        """Test connect handles connection failure."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=False)
        mock_client_class.return_value = mock_client

        result = await adapter.connect()

        assert result is False
        assert adapter.connected is False

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
    async def test_disconnect(self, mock_client_class, adapter):
        """Test disconnect closes serial client."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = Mock()
        mock_client_class.return_value = mock_client

        await adapter.connect()
        await adapter.disconnect()

        assert adapter.connected is False
        assert adapter.client is None
        mock_client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, adapter):
        """Test disconnect when not connected."""
        await adapter.disconnect()

        assert adapter.connected is False
        assert adapter.client is None


# ================================================================
# READ OPERATIONS TESTS
# ================================================================
class TestModbusRTUAdapterReadOperations:
    """Test ModbusRTUAdapter read operations."""

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
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
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
    async def test_read_discrete_inputs(self, mock_client_class, adapter):
        """Test reading discrete inputs."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.read_discrete_inputs = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        result = await adapter.read_discrete_inputs(20, count=8)

        assert result == mock_response
        mock_client.read_discrete_inputs.assert_awaited_once_with(20, count=8)

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
    async def test_read_holding_registers(self, mock_client_class, adapter):
        """Test reading holding registers."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.read_holding_registers = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        result = await adapter.read_holding_registers(100, count=4)

        assert result == mock_response
        mock_client.read_holding_registers.assert_awaited_once_with(100, count=4)

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
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
class TestModbusRTUAdapterWriteOperations:
    """Test ModbusRTUAdapter write operations."""

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
    async def test_write_coil(self, mock_client_class, adapter):
        """Test writing a single coil."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.write_coil = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        result = await adapter.write_coil(15, False)

        assert result == mock_response
        mock_client.write_coil.assert_awaited_once_with(15, False)

    @pytest.mark.asyncio
    async def test_write_coil_without_connection_raises(self, adapter):
        """Test writing coil without connection raises error."""
        with pytest.raises(RuntimeError, match="Client not connected"):
            await adapter.write_coil(0, True)

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
    async def test_write_register(self, mock_client_class, adapter):
        """Test writing a single register."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.write_register = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        result = await adapter.write_register(200, 999)

        assert result == mock_response
        mock_client.write_register.assert_awaited_once_with(200, 999)

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
    async def test_write_multiple_coils(self, mock_client_class, adapter):
        """Test writing multiple coils."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.write_coils = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        values = [True, True, False, True]
        result = await adapter.write_multiple_coils(10, values)

        assert result == mock_response
        mock_client.write_coils.assert_awaited_once_with(10, values)

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
    async def test_write_multiple_registers(self, mock_client_class, adapter):
        """Test writing multiple registers."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_response = Mock()
        mock_client.write_registers = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        values = [10, 20, 30]
        result = await adapter.write_multiple_registers(50, values)

        assert result == mock_response
        mock_client.write_registers.assert_awaited_once_with(50, values)


# ================================================================
# PROBE TESTS
# ================================================================
class TestModbusRTUAdapterProbe:
    """Test ModbusRTUAdapter probe functionality."""

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
    async def test_probe_returns_transport_info(self, mock_client_class, adapter):
        """Test probe returns serial port and connection info."""
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client_class.return_value = mock_client

        await adapter.connect()
        result = await adapter.probe()

        assert result["transport"] == "modbus-rtu"
        assert result["port"] == "/dev/ttyUSB0"
        assert result["device_id"] == 1
        assert result["baudrate"] == 9600
        assert result["connected"] is True

    @pytest.mark.asyncio
    async def test_probe_when_not_connected(self, adapter):
        """Test probe shows not connected status."""
        result = await adapter.probe()

        assert result["connected"] is False


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestModbusRTUAdapterIntegration:
    """Test ModbusRTUAdapter end-to-end scenarios."""

    @pytest.mark.asyncio
    @patch("components.protocols.modbus.modbus_rtu_adapter.AsyncModbusSerialClient")
    async def test_typical_rtu_workflow(self, mock_client_class, adapter):
        """Test typical RTU workflow: connect, read, write, disconnect."""
        # Setup mock
        mock_client = Mock()
        mock_client.connect = AsyncMock(return_value=True)
        mock_client.close = Mock()
        mock_client.read_holding_registers = AsyncMock(return_value=Mock())
        mock_client.write_register = AsyncMock(return_value=Mock())
        mock_client_class.return_value = mock_client

        # 1. Connect via serial
        connected = await adapter.connect()
        assert connected is True

        # 2. Read registers
        await adapter.read_holding_registers(0, count=10)
        mock_client.read_holding_registers.assert_awaited_once()

        # 3. Write register
        await adapter.write_register(5, 42)
        mock_client.write_register.assert_awaited_once()

        # 4. Disconnect
        await adapter.disconnect()
        assert adapter.connected is False
