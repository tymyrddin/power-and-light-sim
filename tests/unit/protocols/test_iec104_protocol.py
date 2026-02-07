# tests/unit/protocols/test_iec104_protocol.py
"""
Unit tests for IEC104Protocol.

Tests the high-level IEC 60870-5-104 protocol wrapper that provides
attacker-relevant capabilities via an adapter pattern.
"""

from unittest.mock import AsyncMock, Mock

import pytest

from components.protocols.iec104.iec104_protocol import IEC104Protocol


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
def mock_adapter():
    """Create a mock IEC104 adapter."""
    adapter = Mock()
    adapter.connect = AsyncMock(return_value=True)
    adapter.disconnect = AsyncMock()
    adapter.set_point = AsyncMock(return_value=True)
    adapter.get_state = AsyncMock(return_value={})
    adapter.probe = AsyncMock(return_value={"connected": False})
    return adapter


@pytest.fixture
def iec104_protocol(mock_adapter):
    """Create IEC104Protocol instance with mock adapter."""
    return IEC104Protocol(mock_adapter)


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestIEC104ProtocolInitialization:
    """Test IEC104Protocol initialization."""

    def test_init_with_adapter(self, mock_adapter):
        """Test initialization with adapter."""
        protocol = IEC104Protocol(mock_adapter)

        assert protocol.protocol_name == "iec104"
        assert protocol.adapter == mock_adapter
        assert protocol.connected is False
        assert protocol.data_transfer_started is False

    def test_inherits_from_base_protocol(self, iec104_protocol):
        """Test that IEC104Protocol inherits from BaseProtocol."""
        from components.protocols.base_protocol import BaseProtocol

        assert isinstance(iec104_protocol, BaseProtocol)


# ================================================================
# LIFECYCLE TESTS
# ================================================================
class TestIEC104ProtocolLifecycle:
    """Test IEC104Protocol connection lifecycle."""

    @pytest.mark.asyncio
    async def test_connect_success(self, iec104_protocol, mock_adapter):
        """Test successful connection."""
        mock_adapter.connect.return_value = True

        result = await iec104_protocol.connect()

        assert result is True
        assert iec104_protocol.connected is True
        mock_adapter.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_failure(self, iec104_protocol, mock_adapter):
        """Test failed connection."""
        mock_adapter.connect.return_value = False

        result = await iec104_protocol.connect()

        assert result is False
        assert iec104_protocol.connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self, iec104_protocol, mock_adapter):
        """Test disconnection."""
        await iec104_protocol.connect()
        await iec104_protocol.disconnect()

        assert iec104_protocol.connected is False
        assert iec104_protocol.data_transfer_started is False
        mock_adapter.disconnect.assert_awaited_once()


# ================================================================
# DATA TRANSFER TESTS
# ================================================================
class TestIEC104ProtocolDataTransfer:
    """Test IEC104Protocol data transfer lifecycle."""

    @pytest.mark.asyncio
    async def test_start_data_transfer(self, iec104_protocol, mock_adapter):
        """Test starting data transfer."""
        mock_adapter.connect.return_value = True
        await iec104_protocol.connect()

        result = await iec104_protocol.start_data_transfer()

        assert result is True
        assert iec104_protocol.data_transfer_started is True

    @pytest.mark.asyncio
    async def test_start_data_transfer_already_started(
        self, iec104_protocol, mock_adapter
    ):
        """Test starting data transfer when already started."""
        mock_adapter.connect.return_value = True
        await iec104_protocol.connect()

        await iec104_protocol.start_data_transfer()
        result = await iec104_protocol.start_data_transfer()

        assert result is True
        assert iec104_protocol.data_transfer_started is True

    @pytest.mark.asyncio
    async def test_stop_data_transfer(self, iec104_protocol, mock_adapter):
        """Test stopping data transfer."""
        mock_adapter.connect.return_value = True
        await iec104_protocol.connect()
        await iec104_protocol.start_data_transfer()

        await iec104_protocol.stop_data_transfer()

        assert iec104_protocol.data_transfer_started is False

    @pytest.mark.asyncio
    async def test_stop_data_transfer_when_not_started(self, iec104_protocol):
        """Test stopping data transfer when not started."""
        await iec104_protocol.stop_data_transfer()

        assert iec104_protocol.data_transfer_started is False


# ================================================================
# INTERROGATION TESTS
# ================================================================
class TestIEC104ProtocolInterrogation:
    """Test IEC104Protocol interrogation functionality."""

    @pytest.mark.asyncio
    async def test_interrogation_returns_state(self, iec104_protocol, mock_adapter):
        """Test interrogation returns adapter state."""
        mock_adapter.connect.return_value = True
        mock_state = {100: 42.5, 200: 99.9}
        mock_adapter.get_state.return_value = mock_state

        await iec104_protocol.connect()
        await iec104_protocol.start_data_transfer()
        result = await iec104_protocol.interrogation()

        assert result == mock_state
        mock_adapter.get_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_interrogation_empty_state(self, iec104_protocol, mock_adapter):
        """Test interrogation with empty state."""
        mock_adapter.connect.return_value = True
        mock_adapter.get_state.return_value = {}

        await iec104_protocol.connect()
        await iec104_protocol.start_data_transfer()
        result = await iec104_protocol.interrogation()

        assert result == {}


# ================================================================
# PROBE TESTS
# ================================================================
class TestIEC104ProtocolProbe:
    """Test IEC104Protocol probe functionality."""

    @pytest.mark.asyncio
    async def test_probe_when_connected(self, iec104_protocol, mock_adapter):
        """Test probe when already connected."""
        mock_adapter.connect.return_value = True
        mock_adapter.get_state.return_value = {100: 42.5}
        await iec104_protocol.connect()

        result = await iec104_protocol.probe()

        assert result["connected"] is True
        assert result["startdt"] is True
        assert result["interrogation"] is True

    @pytest.mark.asyncio
    async def test_probe_auto_connect(self, iec104_protocol, mock_adapter):
        """Test probe auto-connects if not connected."""
        mock_adapter.connect.return_value = True
        mock_adapter.get_state.return_value = {}

        await iec104_protocol.probe()

        # Should connect during probe, then disconnect after
        mock_adapter.connect.assert_awaited_once()
        mock_adapter.disconnect.assert_awaited_once()
        assert iec104_protocol.connected is False

    @pytest.mark.asyncio
    async def test_probe_auto_disconnect_after_probe(
        self, iec104_protocol, mock_adapter
    ):
        """Test probe auto-disconnects after probing if it connected."""
        mock_adapter.connect.return_value = True
        mock_adapter.probe.return_value = {"protocol": "iec104"}

        await iec104_protocol.probe()

        # Should disconnect after probe
        mock_adapter.disconnect.assert_awaited_once()
        assert iec104_protocol.connected is False

    @pytest.mark.asyncio
    async def test_probe_keeps_connection_if_already_connected(
        self, iec104_protocol, mock_adapter
    ):
        """Test probe doesn't disconnect if already connected."""
        await iec104_protocol.connect()
        mock_adapter.disconnect.reset_mock()
        mock_adapter.probe.return_value = {"protocol": "iec104"}

        await iec104_protocol.probe()

        # Should NOT disconnect if we were already connected
        mock_adapter.disconnect.assert_not_awaited()
        assert iec104_protocol.connected is True


# ================================================================
# SET POINT TESTS
# ================================================================
class TestIEC104ProtocolSetPoint:
    """Test IEC104Protocol set_point functionality."""

    @pytest.mark.asyncio
    async def test_set_point_success(self, iec104_protocol, mock_adapter):
        """Test setting a point successfully."""
        mock_adapter.connect.return_value = True
        mock_adapter.set_point.return_value = None

        await iec104_protocol.connect()
        await iec104_protocol.start_data_transfer()
        await iec104_protocol.set_point(100, 42.5)

        mock_adapter.set_point.assert_awaited_once_with(100, 42.5)

    @pytest.mark.asyncio
    async def test_set_point_failure(self, iec104_protocol, mock_adapter):
        """Test set_point raises error if data transfer not started."""
        mock_adapter.connect.return_value = True
        await iec104_protocol.connect()

        with pytest.raises(RuntimeError, match="Data transfer not started"):
            await iec104_protocol.set_point(100, 42.5)

    @pytest.mark.asyncio
    async def test_set_point_different_addresses(self, iec104_protocol, mock_adapter):
        """Test setting points at different IOAs."""
        mock_adapter.connect.return_value = True
        await iec104_protocol.connect()
        await iec104_protocol.start_data_transfer()

        await iec104_protocol.set_point(10, 10.0)
        await iec104_protocol.set_point(20, 20.0)
        await iec104_protocol.set_point(30, 30.0)

        assert mock_adapter.set_point.call_count == 3


# ================================================================
# OVERWRITE STATE TESTS
# ================================================================
class TestIEC104ProtocolOverwriteState:
    """Test IEC104Protocol overwrite_state functionality."""

    @pytest.mark.asyncio
    async def test_overwrite_state_with_multiple_points(
        self, iec104_protocol, mock_adapter
    ):
        """Test overwriting multiple state points."""
        mock_adapter.connect.return_value = True
        await iec104_protocol.connect()
        await iec104_protocol.start_data_transfer()

        new_state = {
            100: 42.5,
            200: 99.9,
            300: 123.4,
        }

        await iec104_protocol.overwrite_state(new_state)

        # Should call set_point for each entry
        assert mock_adapter.set_point.call_count == 3
        mock_adapter.set_point.assert_any_await(100, 42.5)
        mock_adapter.set_point.assert_any_await(200, 99.9)
        mock_adapter.set_point.assert_any_await(300, 123.4)

    @pytest.mark.asyncio
    async def test_overwrite_state_empty_dict(self, iec104_protocol, mock_adapter):
        """Test overwriting with empty state."""
        mock_adapter.connect.return_value = True
        await iec104_protocol.connect()
        await iec104_protocol.start_data_transfer()

        await iec104_protocol.overwrite_state({})

        mock_adapter.set_point.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_overwrite_state_handles_failure(self, iec104_protocol, mock_adapter):
        """Test overwrite_state raises error if data transfer not started."""
        mock_adapter.connect.return_value = True
        await iec104_protocol.connect()

        with pytest.raises(RuntimeError, match="Data transfer not started"):
            await iec104_protocol.overwrite_state({100: 42.5})


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestIEC104ProtocolIntegration:
    """Test IEC104Protocol end-to-end scenarios."""

    @pytest.mark.asyncio
    async def test_typical_workflow(self, iec104_protocol, mock_adapter):
        """Test typical workflow: connect, start data, interrogate, set point."""
        mock_adapter.connect.return_value = True
        mock_adapter.get_state.return_value = {100: 25.0}

        # 1. Connect
        connected = await iec104_protocol.connect()
        assert connected is True

        # 2. Start data transfer
        await iec104_protocol.start_data_transfer()
        assert iec104_protocol.data_transfer_started is True

        # 3. Interrogate (read all points)
        state = await iec104_protocol.interrogation()
        assert 100 in state

        # 4. Set a point
        await iec104_protocol.set_point(100, 50.0)
        mock_adapter.set_point.assert_awaited_once()

        # 5. Disconnect
        await iec104_protocol.disconnect()
        assert iec104_protocol.connected is False

    @pytest.mark.asyncio
    async def test_attacker_workflow(self, iec104_protocol, mock_adapter):
        """Test attacker workflow: probe, interrogate, overwrite critical values."""
        mock_adapter.connect.return_value = True
        mock_adapter.get_state.return_value = {
            100: 25.0,  # Temperature
            200: 50.0,  # Pressure
            300: 1.0,  # Safety valve (1 = open)
        }

        # 1. Probe (auto-connect and disconnect)
        probe_result = await iec104_protocol.probe()
        assert probe_result["protocol"] == "iec104"

        # 2. Reconnect for exploitation
        await iec104_protocol.connect()
        await iec104_protocol.start_data_transfer()

        # 3. Interrogate to understand system state
        state = await iec104_protocol.interrogation()
        assert len(state) == 3

        # 4. Overwrite critical points
        malicious_state = {
            100: 999.0,  # Dangerous temperature
            200: 0.0,  # Zero pressure
            300: 0.0,  # Close safety valve
        }
        await iec104_protocol.overwrite_state(malicious_state)

        # 5. Verify overwrites were attempted
        assert mock_adapter.set_point.call_count == 3

        # 6. Disconnect
        await iec104_protocol.disconnect()

    @pytest.mark.asyncio
    async def test_data_transfer_lifecycle(self, iec104_protocol, mock_adapter):
        """Test complete data transfer lifecycle."""
        mock_adapter.connect.return_value = True
        await iec104_protocol.connect()

        # Start
        result = await iec104_protocol.start_data_transfer()
        assert result is True
        assert iec104_protocol.data_transfer_started is True

        # Do work while data transfer active
        # (in real implementation, this would enable periodic updates)

        # Stop
        await iec104_protocol.stop_data_transfer()
        assert iec104_protocol.data_transfer_started is False
