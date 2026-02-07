# tests/unit/protocols/test_modbus_rtu_protocol.py
"""
Unit tests for ModbusRTUProtocol.

Tests the high-level Modbus RTU protocol wrapper that exposes
attacker-relevant capabilities like memory scanning and write access testing.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from components.protocols.modbus.modbus_rtu_protocol import ModbusRTUProtocol


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
def mock_adapter():
    """Create a mock Modbus RTU adapter."""
    adapter = Mock()
    adapter.connect = AsyncMock(return_value=True)
    adapter.disconnect = AsyncMock()
    adapter.read_coils = AsyncMock()
    adapter.read_discrete_inputs = AsyncMock()
    adapter.read_holding_registers = AsyncMock()
    adapter.read_input_registers = AsyncMock()
    adapter.write_coil = AsyncMock()
    adapter.write_register = AsyncMock()
    return adapter


@pytest.fixture
def rtu_protocol(mock_adapter):
    """Create ModbusRTUProtocol instance with mock adapter."""
    return ModbusRTUProtocol(mock_adapter)


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestModbusRTUProtocolInitialization:
    """Test ModbusRTUProtocol initialization."""

    def test_init_with_adapter(self, mock_adapter):
        """Test initialization with adapter."""
        protocol = ModbusRTUProtocol(mock_adapter)

        assert protocol.protocol_name == "modbus_rtu"
        assert protocol.adapter == mock_adapter
        assert protocol.connected is False

    def test_inherits_from_base_protocol(self, rtu_protocol):
        """Test that ModbusRTUProtocol inherits from BaseProtocol."""
        from components.protocols.base_protocol import BaseProtocol

        assert isinstance(rtu_protocol, BaseProtocol)


# ================================================================
# LIFECYCLE TESTS
# ================================================================
class TestModbusRTUProtocolLifecycle:
    """Test ModbusRTUProtocol connection lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_success(self, rtu_protocol, mock_adapter):
        """Test successful connection."""
        mock_adapter.connect.return_value = True

        result = await rtu_protocol.connect()

        assert result is True
        assert rtu_protocol.connected is True
        mock_adapter.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, rtu_protocol, mock_adapter):
        """Test failed connection."""
        mock_adapter.connect.return_value = False

        result = await rtu_protocol.connect()

        assert result is False
        assert rtu_protocol.connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self, rtu_protocol, mock_adapter):
        """Test disconnection."""
        await rtu_protocol.connect()
        await rtu_protocol.disconnect()

        assert rtu_protocol.connected is False
        mock_adapter.disconnect.assert_awaited_once()


# ================================================================
# PROBE TESTS
# ================================================================
class TestModbusRTUProtocolProbe:
    """Test ModbusRTUProtocol probe functionality."""

    @pytest.mark.asyncio
    async def test_probe_when_not_connected(self, rtu_protocol):
        """Test probe returns basic info when not connected."""
        result = await rtu_protocol.probe()

        assert result["protocol"] == "modbus_rtu"
        assert result["connected"] is False
        assert result["coils_readable"] is False
        assert result["discrete_inputs_readable"] is False
        assert result["holding_registers_readable"] is False
        assert result["input_registers_readable"] is False

    @pytest.mark.asyncio
    async def test_probe_all_readable(self, rtu_protocol, mock_adapter):
        """Test probe detects all readable memory types."""
        await rtu_protocol.connect()

        # Mock all reads as successful
        mock_response = Mock()
        mock_response.isError.return_value = False
        mock_adapter.read_coils.return_value = mock_response
        mock_adapter.read_discrete_inputs.return_value = mock_response
        mock_adapter.read_holding_registers.return_value = mock_response
        mock_adapter.read_input_registers.return_value = mock_response

        result = await rtu_protocol.probe()

        assert result["connected"] is True
        assert result["coils_readable"] is True
        assert result["discrete_inputs_readable"] is True
        assert result["holding_registers_readable"] is True
        assert result["input_registers_readable"] is True

    @pytest.mark.asyncio
    async def test_probe_partial_readable(self, rtu_protocol, mock_adapter):
        """Test probe detects partial readability."""
        await rtu_protocol.connect()

        # Only coils and holding registers are readable
        success_response = Mock()
        success_response.isError.return_value = False
        error_response = Mock()
        error_response.isError.return_value = True

        mock_adapter.read_coils.return_value = success_response
        mock_adapter.read_discrete_inputs.return_value = error_response
        mock_adapter.read_holding_registers.return_value = success_response
        mock_adapter.read_input_registers.return_value = error_response

        result = await rtu_protocol.probe()

        assert result["coils_readable"] is True
        assert result["discrete_inputs_readable"] is False
        assert result["holding_registers_readable"] is True
        assert result["input_registers_readable"] is False

    @pytest.mark.asyncio
    async def test_probe_handles_exceptions(self, rtu_protocol, mock_adapter):
        """Test probe handles adapter exceptions gracefully."""
        await rtu_protocol.connect()

        # All reads raise exceptions
        mock_adapter.read_coils.side_effect = RuntimeError("Connection lost")
        mock_adapter.read_discrete_inputs.side_effect = RuntimeError("Timeout")
        mock_adapter.read_holding_registers.side_effect = RuntimeError("Error")
        mock_adapter.read_input_registers.side_effect = RuntimeError("Failed")

        result = await rtu_protocol.probe()

        assert result["coils_readable"] is False
        assert result["discrete_inputs_readable"] is False
        assert result["holding_registers_readable"] is False
        assert result["input_registers_readable"] is False


# ================================================================
# MEMORY SCANNING TESTS
# ================================================================
class TestModbusRTUProtocolMemoryScanning:
    """Test ModbusRTUProtocol memory scanning functionality."""

    @pytest.mark.asyncio
    async def test_scan_memory_default_range(self, rtu_protocol, mock_adapter):
        """Test scanning memory with default range."""
        # Mock successful reads
        coil_response = Mock()
        coil_response.bits = [True, False, True] * 34  # 100+ bits
        mock_adapter.read_coils.return_value = coil_response

        reg_response = Mock()
        reg_response.registers = list(range(100))
        mock_adapter.read_holding_registers.return_value = reg_response

        discrete_response = Mock()
        discrete_response.bits = [False, True, False] * 34
        mock_adapter.read_discrete_inputs.return_value = discrete_response

        input_response = Mock()
        input_response.registers = list(range(200, 300))
        mock_adapter.read_input_registers.return_value = input_response

        result = await rtu_protocol.scan_memory()

        # Verify all memory types scanned
        assert len(result["coils"]) == 100
        assert len(result["holding_registers"]) == 100
        assert len(result["discrete_inputs"]) == 100
        assert len(result["input_registers"]) == 100

        # Verify correct addresses and counts
        mock_adapter.read_coils.assert_awaited_once_with(0, 100)
        mock_adapter.read_holding_registers.assert_awaited_once_with(0, 100)

    @pytest.mark.asyncio
    async def test_scan_memory_custom_range(self, rtu_protocol, mock_adapter):
        """Test scanning memory with custom start and count."""
        # Mock responses
        mock_response = Mock()
        mock_response.bits = [True] * 50
        mock_response.registers = [42] * 50
        mock_adapter.read_coils.return_value = mock_response
        mock_adapter.read_discrete_inputs.return_value = mock_response
        mock_adapter.read_holding_registers.return_value = mock_response
        mock_adapter.read_input_registers.return_value = mock_response

        result = await rtu_protocol.scan_memory(start=100, count=50)

        # Verify custom range used
        mock_adapter.read_coils.assert_awaited_once_with(100, 50)
        mock_adapter.read_holding_registers.assert_awaited_once_with(100, 50)
        assert len(result["coils"]) == 50
        assert len(result["holding_registers"]) == 50

    @pytest.mark.asyncio
    async def test_scan_memory_handles_failures(self, rtu_protocol, mock_adapter):
        """Test scan_memory handles read failures gracefully."""
        # Coils work, holding registers fail
        coil_response = Mock()
        coil_response.bits = [True] * 100
        mock_adapter.read_coils.return_value = coil_response
        mock_adapter.read_discrete_inputs.side_effect = RuntimeError("Failed")
        mock_adapter.read_holding_registers.side_effect = RuntimeError("Failed")
        mock_adapter.read_input_registers.side_effect = RuntimeError("Failed")

        result = await rtu_protocol.scan_memory()

        # Successful scan returns data, failed scans return empty lists
        assert len(result["coils"]) == 100
        assert result["discrete_inputs"] == []
        assert result["holding_registers"] == []
        assert result["input_registers"] == []


# ================================================================
# WRITE ACCESS TESTING
# ================================================================
class TestModbusRTUProtocolWriteAccessTesting:
    """Test ModbusRTUProtocol write access testing functionality."""

    @pytest.mark.asyncio
    async def test_write_access_both_writable(self, rtu_protocol, mock_adapter):
        """Test detecting writable coils and registers."""
        # Mock reading original values
        coil_response = Mock()
        coil_response.bits = [False]
        mock_adapter.read_coils.return_value = coil_response

        reg_response = Mock()
        reg_response.registers = [100]
        mock_adapter.read_holding_registers.return_value = reg_response

        # Mock successful writes
        write_response = Mock()
        write_response.isError.return_value = False
        mock_adapter.write_coil.return_value = write_response
        mock_adapter.write_register.return_value = write_response

        result = await rtu_protocol.test_write_access(address=0)

        assert result["coil_writable"] is True
        assert result["register_writable"] is True

        # Verify it tested by writing and restoring
        assert mock_adapter.write_coil.call_count == 2  # Test + restore
        assert mock_adapter.write_register.call_count == 2  # Test + restore

    @pytest.mark.asyncio
    async def test_write_access_not_writable(self, rtu_protocol, mock_adapter):
        """Test detecting non-writable memory."""
        # Mock reads
        coil_response = Mock()
        coil_response.bits = [True]
        mock_adapter.read_coils.return_value = coil_response

        reg_response = Mock()
        reg_response.registers = [200]
        mock_adapter.read_holding_registers.return_value = reg_response

        # Mock write errors
        error_response = Mock()
        error_response.isError.return_value = True
        mock_adapter.write_coil.return_value = error_response
        mock_adapter.write_register.return_value = error_response

        result = await rtu_protocol.test_write_access(address=10)

        assert result["coil_writable"] is False
        assert result["register_writable"] is False

    @pytest.mark.asyncio
    async def test_write_access_restores_original_values(
        self, rtu_protocol, mock_adapter
    ):
        """Test write access test restores original values."""
        # Mock original values
        coil_response = Mock()
        coil_response.bits = [True]
        mock_adapter.read_coils.return_value = coil_response

        reg_response = Mock()
        reg_response.registers = [42]
        mock_adapter.read_holding_registers.return_value = reg_response

        # Mock successful writes
        write_response = Mock()
        write_response.isError.return_value = False
        mock_adapter.write_coil.return_value = write_response
        mock_adapter.write_register.return_value = write_response

        await rtu_protocol.test_write_access(address=5)

        # Verify original values were restored
        # First call writes test value, second call restores
        coil_calls = mock_adapter.write_coil.await_args_list
        assert coil_calls[0][0] == (5, False)  # Test with opposite value
        assert coil_calls[1][0] == (5, True)  # Restore original

        reg_calls = mock_adapter.write_register.await_args_list
        assert reg_calls[0][0] == (5, 43)  # Test with +1
        assert reg_calls[1][0] == (5, 42)  # Restore original

    @pytest.mark.asyncio
    async def test_write_access_handles_exceptions(self, rtu_protocol, mock_adapter):
        """Test write access test handles exceptions gracefully."""
        # Mock reads that fail
        mock_adapter.read_coils.side_effect = RuntimeError("Read failed")
        mock_adapter.read_holding_registers.side_effect = RuntimeError("Read failed")

        result = await rtu_protocol.test_write_access()

        assert result["coil_writable"] is False
        assert result["register_writable"] is False


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestModbusRTUProtocolIntegration:
    """Test ModbusRTUProtocol end-to-end attack scenarios."""

    @pytest.mark.asyncio
    async def test_attacker_workflow(self, rtu_protocol, mock_adapter):
        """Test typical attacker workflow: probe, scan, test writes."""
        # Setup mocks
        mock_adapter.connect.return_value = True

        # Probe responses
        probe_response = Mock()
        probe_response.isError.return_value = False
        mock_adapter.read_coils.return_value = probe_response
        mock_adapter.read_holding_registers.return_value = probe_response
        mock_adapter.read_discrete_inputs.return_value = probe_response
        mock_adapter.read_input_registers.return_value = probe_response

        # Scan responses
        scan_response = Mock()
        scan_response.bits = [True, False] * 50
        scan_response.registers = list(range(100))
        mock_adapter.read_coils.return_value = scan_response
        mock_adapter.read_holding_registers.return_value = scan_response
        mock_adapter.read_discrete_inputs.return_value = scan_response
        mock_adapter.read_input_registers.return_value = scan_response

        # Write test responses
        write_response = Mock()
        write_response.isError.return_value = False
        mock_adapter.write_coil.return_value = write_response
        mock_adapter.write_register.return_value = write_response

        # 1. Connect
        connected = await rtu_protocol.connect()
        assert connected is True

        # 2. Probe capabilities
        probe_result = await rtu_protocol.probe()
        assert probe_result["connected"] is True

        # 3. Scan memory for data
        scan_result = await rtu_protocol.scan_memory(start=0, count=100)
        assert len(scan_result["coils"]) == 100

        # 4. Test write access
        write_result = await rtu_protocol.test_write_access()
        assert write_result["coil_writable"] is True

        # 5. Disconnect
        await rtu_protocol.disconnect()
        assert rtu_protocol.connected is False
