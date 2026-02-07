# tests/unit/protocols/test_modbus_protocol.py
"""
Unit tests for ModbusProtocol.

Tests the high-level Modbus protocol wrapper that provides
attacker-relevant capabilities via an adapter pattern.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from components.protocols.modbus.modbus_protocol import ModbusProtocol


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
def mock_adapter():
    """Create a mock Modbus adapter."""
    adapter = Mock()
    adapter.connect = AsyncMock(return_value=True)
    adapter.disconnect = AsyncMock()
    adapter.read_coils = AsyncMock()
    adapter.read_holding_registers = AsyncMock()
    adapter.write_coil = AsyncMock()
    adapter.write_register = AsyncMock()
    return adapter


@pytest.fixture
def modbus_protocol(mock_adapter):
    """Create ModbusProtocol instance with mock adapter."""
    return ModbusProtocol(mock_adapter)


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestModbusProtocolInitialization:
    """Test ModbusProtocol initialization."""

    def test_init_with_adapter(self, mock_adapter):
        """Test initialization with adapter."""
        protocol = ModbusProtocol(mock_adapter)

        assert protocol.protocol_name == "modbus"
        assert protocol.adapter == mock_adapter
        assert protocol.connected is False

    def test_inherits_from_base_protocol(self, modbus_protocol):
        """Test that ModbusProtocol inherits from BaseProtocol."""
        from components.protocols.base_protocol import BaseProtocol

        assert isinstance(modbus_protocol, BaseProtocol)


# ================================================================
# LIFECYCLE TESTS
# ================================================================
class TestModbusProtocolLifecycle:
    """Test ModbusProtocol connection lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_success(self, modbus_protocol, mock_adapter):
        """Test successful connection."""
        mock_adapter.connect.return_value = True

        result = await modbus_protocol.connect()

        assert result is True
        assert modbus_protocol.connected is True
        mock_adapter.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, modbus_protocol, mock_adapter):
        """Test failed connection."""
        mock_adapter.connect.return_value = False

        result = await modbus_protocol.connect()

        assert result is False
        assert modbus_protocol.connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self, modbus_protocol, mock_adapter):
        """Test disconnection."""
        # Connect first
        await modbus_protocol.connect()
        assert modbus_protocol.connected is True

        # Disconnect
        await modbus_protocol.disconnect()

        assert modbus_protocol.connected is False
        mock_adapter.disconnect.assert_awaited_once()


# ================================================================
# PROBE TESTS
# ================================================================
class TestModbusProtocolProbe:
    """Test ModbusProtocol probe functionality."""

    @pytest.mark.asyncio
    async def test_probe_when_not_connected(self, modbus_protocol):
        """Test probe returns basic info when not connected."""
        result = await modbus_protocol.probe()

        assert result["protocol"] == "modbus"
        assert result["connected"] is False
        assert result["coils_readable"] is False
        assert result["holding_registers_readable"] is False

    @pytest.mark.asyncio
    async def test_probe_coils_readable(self, modbus_protocol, mock_adapter):
        """Test probe detects readable coils."""
        # Setup: connect and mock successful coil reads
        await modbus_protocol.connect()
        mock_response = Mock()
        mock_response.isError.return_value = False
        mock_adapter.read_coils.return_value = mock_response

        result = await modbus_protocol.probe()

        assert result["connected"] is True
        assert result["coils_readable"] is True
        assert mock_adapter.read_coils.call_count == 4  # Tests 4 offsets

    @pytest.mark.asyncio
    async def test_probe_holding_registers_readable(
        self, modbus_protocol, mock_adapter
    ):
        """Test probe detects readable holding registers."""
        await modbus_protocol.connect()

        # Coils fail, holding registers succeed
        coil_response = Mock()
        coil_response.isError.return_value = True
        mock_adapter.read_coils.return_value = coil_response

        reg_response = Mock()
        reg_response.isError.return_value = False
        mock_adapter.read_holding_registers.return_value = reg_response

        result = await modbus_protocol.probe()

        assert result["coils_readable"] is False
        assert result["holding_registers_readable"] is True

    @pytest.mark.asyncio
    async def test_probe_handles_errors_gracefully(self, modbus_protocol, mock_adapter):
        """Test probe handles adapter errors without crashing."""
        await modbus_protocol.connect()
        mock_adapter.read_coils.side_effect = RuntimeError("Connection error")
        mock_adapter.read_holding_registers.side_effect = RuntimeError(
            "Connection error"
        )

        result = await modbus_protocol.probe()

        assert result["connected"] is True
        assert result["coils_readable"] is False
        assert result["holding_registers_readable"] is False


# ================================================================
# READ OPERATIONS TESTS
# ================================================================
class TestModbusProtocolReadOperations:
    """Test ModbusProtocol read operations."""

    @pytest.mark.asyncio
    async def test_read_single_coil(self, modbus_protocol, mock_adapter):
        """Test reading a single coil."""
        mock_response = Mock()
        mock_adapter.read_coils.return_value = mock_response

        results = await modbus_protocol.read_coils(10, count=1)

        assert len(results) == 1
        assert results[0] == mock_response
        mock_adapter.read_coils.assert_awaited_once_with(10)

    @pytest.mark.asyncio
    async def test_read_multiple_coils(self, modbus_protocol, mock_adapter):
        """Test reading multiple coils sequentially."""
        mock_adapter.read_coils.return_value = Mock()

        results = await modbus_protocol.read_coils(100, count=3)

        assert len(results) == 3
        assert mock_adapter.read_coils.call_count == 3
        # Verify addresses incremented
        mock_adapter.read_coils.assert_any_await(100)
        mock_adapter.read_coils.assert_any_await(101)
        mock_adapter.read_coils.assert_any_await(102)

    @pytest.mark.asyncio
    async def test_read_single_holding_register(self, modbus_protocol, mock_adapter):
        """Test reading a single holding register."""
        mock_response = Mock()
        mock_adapter.read_holding_registers.return_value = mock_response

        results = await modbus_protocol.read_holding_registers(50, count=1)

        assert len(results) == 1
        assert results[0] == mock_response
        mock_adapter.read_holding_registers.assert_awaited_once_with(50)

    @pytest.mark.asyncio
    async def test_read_multiple_holding_registers(self, modbus_protocol, mock_adapter):
        """Test reading multiple holding registers."""
        mock_adapter.read_holding_registers.return_value = Mock()

        results = await modbus_protocol.read_holding_registers(0, count=5)

        assert len(results) == 5
        assert mock_adapter.read_holding_registers.call_count == 5


# ================================================================
# WRITE OPERATIONS TESTS
# ================================================================
class TestModbusProtocolWriteOperations:
    """Test ModbusProtocol write operations."""

    @pytest.mark.asyncio
    async def test_write_coil(self, modbus_protocol, mock_adapter):
        """Test writing a coil."""
        mock_response = Mock()
        mock_adapter.write_coil.return_value = mock_response

        result = await modbus_protocol.write_coil(10, True)

        assert result == mock_response
        mock_adapter.write_coil.assert_awaited_once_with(10, True)

    @pytest.mark.asyncio
    async def test_write_register(self, modbus_protocol, mock_adapter):
        """Test writing a holding register."""
        mock_response = Mock()
        mock_adapter.write_register.return_value = mock_response

        result = await modbus_protocol.write_register(50, 1234)

        assert result == mock_response
        mock_adapter.write_register.assert_awaited_once_with(50, 1234)


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestModbusProtocolIntegration:
    """Test ModbusProtocol end-to-end scenarios."""

    @pytest.mark.asyncio
    async def test_typical_attacker_workflow(self, modbus_protocol, mock_adapter):
        """Test a typical attacker workflow: connect, probe, read, write."""
        # Setup mocks
        mock_adapter.connect.return_value = True
        coil_response = Mock()
        coil_response.isError.return_value = False
        mock_adapter.read_coils.return_value = coil_response

        # 1. Connect
        connected = await modbus_protocol.connect()
        assert connected is True

        # 2. Probe capabilities
        probe_result = await modbus_protocol.probe()
        assert probe_result["connected"] is True
        assert probe_result["coils_readable"] is True

        # 3. Read some coils
        coils = await modbus_protocol.read_coils(0, count=2)
        assert len(coils) == 2

        # 4. Write a coil
        await modbus_protocol.write_coil(5, True)
        mock_adapter.write_coil.assert_awaited_once()

        # 5. Disconnect
        await modbus_protocol.disconnect()
        assert modbus_protocol.connected is False
