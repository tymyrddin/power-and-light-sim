"""Comprehensive tests for DNP3Protocol.

DNP3Protocol is a wrapper around DNP3Adapter that exposes attacker-relevant
capabilities and inherits from BaseProtocol.

Test Coverage:
- Initialization and configuration
- Lifecycle management (connect/disconnect)
- Connection state tracking
- Probe functionality (recon)
- Attack primitives:
  - enumerate_points
  - test_write_capabilities
  - send_unsolicited_response
  - flood_events
- Error handling and resilience
- Integration with DNP3Adapter
- Mode-specific operations (master vs outstation)

Tests use mocking for DNP3Adapter to isolate protocol logic.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from components.protocols.dnp3.dnp3_protocol import DNP3Protocol


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
def mock_adapter():
    """Mock DNP3Adapter.

    WHY: Isolate protocol logic from adapter implementation.
    """
    adapter = Mock()
    adapter.mode = "outstation"
    adapter.connected = False
    adapter.setup = {
        "binary_inputs": {},
        "analog_inputs": {},
        "counters": {},
    }
    adapter.database = None
    adapter.connect = AsyncMock(return_value=True)
    adapter.disconnect = AsyncMock()
    adapter.integrity_scan = AsyncMock(return_value=False)
    adapter.event_scan = AsyncMock(return_value=False)
    adapter.read_binary_inputs = AsyncMock(return_value=[])
    adapter.read_analog_inputs = AsyncMock(return_value=[])
    adapter.write_binary_output = AsyncMock(return_value=False)
    adapter.write_analog_output = AsyncMock(return_value=False)
    adapter.update_binary_input = AsyncMock()
    return adapter


@pytest.fixture
def outstation_protocol(mock_adapter):
    """Create DNP3Protocol in outstation mode.

    WHY: Many tests need outstation protocol.
    """
    mock_adapter.mode = "outstation"
    return DNP3Protocol(mock_adapter)


@pytest.fixture
def master_protocol(mock_adapter):
    """Create DNP3Protocol in master mode.

    WHY: Some tests need master protocol.
    """
    mock_adapter.mode = "master"
    return DNP3Protocol(mock_adapter)


@pytest.fixture
async def connected_outstation(outstation_protocol, mock_adapter):
    """Create connected outstation protocol.

    WHY: Many tests need connected protocol.
    """
    mock_adapter.connected = True
    await outstation_protocol.connect()
    yield outstation_protocol


@pytest.fixture
async def connected_master(master_protocol, mock_adapter):
    """Create connected master protocol.

    WHY: Some tests need connected master.
    """
    mock_adapter.connected = True
    await master_protocol.connect()
    yield master_protocol


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestDNP3ProtocolInitialization:
    """Test protocol initialization and configuration."""

    def test_init_with_adapter(self, mock_adapter):
        """Test initialization with adapter.

        WHY: Protocol wraps adapter.
        """
        protocol = DNP3Protocol(mock_adapter)
        assert protocol.adapter is mock_adapter
        assert protocol.protocol_name == "dnp3"
        assert not protocol.connected

    def test_inherits_from_base_protocol(self, outstation_protocol):
        """Test that DNP3Protocol inherits from BaseProtocol.

        WHY: Ensures standard protocol interface.
        """
        from components.protocols.base_protocol import BaseProtocol

        assert isinstance(outstation_protocol, BaseProtocol)

    def test_protocol_name_is_dnp3(self, outstation_protocol):
        """Test that protocol name is set to 'dnp3'.

        WHY: Identifies protocol type.
        """
        assert outstation_protocol.protocol_name == "dnp3"


# ================================================================
# LIFECYCLE TESTS
# ================================================================
class TestDNP3ProtocolLifecycle:
    """Test protocol lifecycle management."""

    @pytest.mark.asyncio
    async def test_connect_calls_adapter_connect(
        self, outstation_protocol, mock_adapter
    ):
        """Test that connect() calls adapter.connect().

        WHY: Protocol delegates connection to adapter.
        """
        mock_adapter.connect.return_value = True
        result = await outstation_protocol.connect()

        mock_adapter.connect.assert_called_once()
        assert result is True

    @pytest.mark.asyncio
    async def test_connect_updates_connected_flag(
        self, outstation_protocol, mock_adapter
    ):
        """Test that successful connect() updates connected flag.

        WHY: Protocol tracks connection state.
        """
        mock_adapter.connect.return_value = True
        await outstation_protocol.connect()

        assert outstation_protocol.connected is True

    @pytest.mark.asyncio
    async def test_connect_failure(self, outstation_protocol, mock_adapter):
        """Test connection failure.

        WHY: Connection may fail.
        """
        mock_adapter.connect.return_value = False
        result = await outstation_protocol.connect()

        assert result is False
        assert outstation_protocol.connected is False

    @pytest.mark.asyncio
    async def test_disconnect_calls_adapter_disconnect(
        self, connected_outstation, mock_adapter
    ):
        """Test that disconnect() calls adapter.disconnect().

        WHY: Protocol delegates disconnection to adapter.
        """
        await connected_outstation.disconnect()

        mock_adapter.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_clears_connected_flag(
        self, connected_outstation, mock_adapter
    ):
        """Test that disconnect() clears connected flag.

        WHY: Protocol must update state on disconnect.
        """
        await connected_outstation.disconnect()

        assert connected_outstation.connected is False


# ================================================================
# PROBE TESTS
# ================================================================
class TestDNP3ProtocolProbe:
    """Test probe/reconnaissance functionality."""

    @pytest.mark.asyncio
    async def test_probe_returns_dict(self, outstation_protocol):
        """Test that probe() returns dictionary.

        WHY: Standard format for recon data.
        """
        result = await outstation_protocol.probe()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_probe_includes_protocol_name(self, outstation_protocol):
        """Test that probe() includes protocol name.

        WHY: Identifies protocol type.
        """
        result = await outstation_protocol.probe()
        assert result["protocol"] == "dnp3"

    @pytest.mark.asyncio
    async def test_probe_includes_mode(self, outstation_protocol, mock_adapter):
        """Test that probe() includes adapter mode.

        WHY: Mode indicates capabilities.
        """
        mock_adapter.mode = "outstation"
        result = await outstation_protocol.probe()
        assert result["mode"] == "outstation"

    @pytest.mark.asyncio
    async def test_probe_includes_connection_state(self, outstation_protocol):
        """Test that probe() includes connection state.

        WHY: Connection state indicates availability.
        """
        result = await outstation_protocol.probe()
        assert "connected" in result
        assert result["connected"] is False

    @pytest.mark.asyncio
    async def test_probe_disconnected_returns_base_info(self, outstation_protocol):
        """Test probe() when disconnected returns only base info.

        WHY: Cannot probe capabilities without connection.
        """
        result = await outstation_protocol.probe()

        assert result["protocol"] == "dnp3"
        assert result["connected"] is False
        assert result["supports_integrity_scan"] is False
        assert result["supports_event_scan"] is False
        assert result["binary_inputs_count"] == 0
        assert result["analog_inputs_count"] == 0
        assert result["counters_count"] == 0

    @pytest.mark.asyncio
    async def test_probe_master_tests_scan_capabilities(
        self, connected_master, mock_adapter
    ):
        """Test probe() in master mode tests scanning capabilities.

        WHY: Master mode exposes scan operations.
        """
        # Configure adapter to support scans
        mock_adapter.integrity_scan = AsyncMock(return_value=True)
        mock_adapter.event_scan = AsyncMock(return_value=True)

        await connected_master.probe()

        # Scans should have been attempted
        mock_adapter.integrity_scan.assert_called_once()
        mock_adapter.event_scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_probe_master_handles_scan_errors(
        self, connected_master, mock_adapter
    ):
        """Test probe() in master mode handles scan errors gracefully.

        WHY: Scans may fail due to communication issues.
        """
        # Configure adapter scans to raise exceptions
        mock_adapter.integrity_scan = AsyncMock(side_effect=RuntimeError("Scan failed"))
        mock_adapter.event_scan = AsyncMock(side_effect=RuntimeError("Scan failed"))

        result = await connected_master.probe()

        # Should return False for unsupported scans
        assert result["supports_integrity_scan"] is False
        assert result["supports_event_scan"] is False

    @pytest.mark.asyncio
    async def test_probe_outstation_reports_point_counts(
        self, connected_outstation, mock_adapter
    ):
        """Test probe() in outstation mode reports point counts.

        WHY: Outstation exposes available points.
        """
        mock_adapter.setup = {
            "binary_inputs": {0: True, 1: False, 2: True},
            "analog_inputs": {0: 123.45, 1: 456.78},
            "counters": {0: 100},
        }

        result = await connected_outstation.probe()

        assert result["binary_inputs_count"] == 3
        assert result["analog_inputs_count"] == 2
        assert result["counters_count"] == 1


# ================================================================
# ENUMERATE POINTS TESTS
# ================================================================
class TestDNP3ProtocolEnumeratePoints:
    """Test enumerate_points attack primitive (master mode)."""

    @pytest.mark.asyncio
    async def test_enumerate_points_master_mode_only(self, outstation_protocol):
        """Test enumerate_points raises error in outstation mode.

        WHY: Point enumeration only available in master mode.
        """
        with pytest.raises(RuntimeError, match="master mode"):
            await outstation_protocol.enumerate_points()

    @pytest.mark.asyncio
    async def test_enumerate_points_performs_integrity_scan(
        self, connected_master, mock_adapter
    ):
        """Test enumerate_points performs integrity scan.

        WHY: Integrity scan retrieves all points.
        """
        await connected_master.enumerate_points()

        mock_adapter.integrity_scan.assert_called_once()

    @pytest.mark.asyncio
    async def test_enumerate_points_reads_binary_inputs(
        self, connected_master, mock_adapter
    ):
        """Test enumerate_points attempts to read binary inputs.

        WHY: Enumerates all point types.
        """
        mock_adapter.read_binary_inputs.return_value = [True, False, True]

        result = await connected_master.enumerate_points()

        mock_adapter.read_binary_inputs.assert_called_once_with(0, 100)
        assert result["binary_inputs"] == [True, False, True]

    @pytest.mark.asyncio
    async def test_enumerate_points_reads_analog_inputs(
        self, connected_master, mock_adapter
    ):
        """Test enumerate_points attempts to read analog inputs.

        WHY: Enumerates all point types.
        """
        mock_adapter.read_analog_inputs.return_value = [123.45, 456.78]

        result = await connected_master.enumerate_points()

        mock_adapter.read_analog_inputs.assert_called_once_with(0, 100)
        assert result["analog_inputs"] == [123.45, 456.78]

    @pytest.mark.asyncio
    async def test_enumerate_points_handles_read_errors(
        self, connected_master, mock_adapter
    ):
        """Test enumerate_points handles read errors gracefully.

        WHY: Reads may fail due to communication issues.
        """
        mock_adapter.read_binary_inputs.side_effect = RuntimeError("Read failed")
        mock_adapter.read_analog_inputs.side_effect = RuntimeError("Read failed")

        result = await connected_master.enumerate_points()

        # Should return empty lists on error
        assert result["binary_inputs"] == []
        assert result["analog_inputs"] == []

    @pytest.mark.asyncio
    async def test_enumerate_points_returns_expected_structure(
        self, connected_master, mock_adapter
    ):
        """Test enumerate_points returns expected data structure.

        WHY: Standard format for enumeration results.
        """
        result = await connected_master.enumerate_points()

        assert isinstance(result, dict)
        assert "binary_inputs" in result
        assert "analog_inputs" in result


# ================================================================
# TEST WRITE CAPABILITIES TESTS
# ================================================================
class TestDNP3ProtocolTestWriteCapabilities:
    """Test test_write_capabilities attack primitive (master mode)."""

    @pytest.mark.asyncio
    async def test_write_capabilities_master_mode_only(self, outstation_protocol):
        """Test test_write_capabilities raises error in outstation mode.

        WHY: Write testing only available in master mode.
        """
        with pytest.raises(RuntimeError, match="master mode"):
            await outstation_protocol.test_write_capabilities()

    @pytest.mark.asyncio
    async def test_write_capabilities_tests_binary_output(
        self, connected_master, mock_adapter
    ):
        """Test test_write_capabilities attempts binary output write.

        WHY: Tests control capabilities.
        """
        mock_adapter.write_binary_output.return_value = True

        result = await connected_master.test_write_capabilities()

        mock_adapter.write_binary_output.assert_called_once_with(0, True)
        assert result["binary_output_successful"] is True

    @pytest.mark.asyncio
    async def test_write_capabilities_tests_analog_output(
        self, connected_master, mock_adapter
    ):
        """Test test_write_capabilities attempts analog output write.

        WHY: Tests control capabilities.
        """
        mock_adapter.write_analog_output.return_value = True

        result = await connected_master.test_write_capabilities()

        mock_adapter.write_analog_output.assert_called_once_with(0, 100.0)
        assert result["analog_output_successful"] is True

    @pytest.mark.asyncio
    async def test_write_capabilities_handles_errors(
        self, connected_master, mock_adapter
    ):
        """Test test_write_capabilities handles write errors gracefully.

        WHY: Writes may fail due to permissions or communication issues.
        """
        mock_adapter.write_binary_output.side_effect = RuntimeError("Write failed")
        mock_adapter.write_analog_output.side_effect = RuntimeError("Write failed")

        result = await connected_master.test_write_capabilities()

        # Should return False on error
        assert result["binary_output_successful"] is False
        assert result["analog_output_successful"] is False

    @pytest.mark.asyncio
    async def test_write_capabilities_tracks_tested_indices(
        self, connected_master, mock_adapter
    ):
        """Test test_write_capabilities tracks which indices were tested.

        WHY: Documents what was attempted.
        """
        mock_adapter.write_binary_output.return_value = True
        mock_adapter.write_analog_output.return_value = True

        result = await connected_master.test_write_capabilities()

        assert ("binary", 0) in result["tested_indices"]
        assert ("analog", 0) in result["tested_indices"]

    @pytest.mark.asyncio
    async def test_write_capabilities_returns_expected_structure(
        self, connected_master, mock_adapter
    ):
        """Test test_write_capabilities returns expected data structure.

        WHY: Standard format for test results.
        """
        result = await connected_master.test_write_capabilities()

        assert isinstance(result, dict)
        assert "binary_output_successful" in result
        assert "analog_output_successful" in result
        assert "tested_indices" in result


# ================================================================
# SEND UNSOLICITED RESPONSE TESTS
# ================================================================
class TestDNP3ProtocolSendUnsolicitedResponse:
    """Test send_unsolicited_response attack primitive (outstation mode)."""

    @pytest.mark.asyncio
    async def test_unsolicited_outstation_mode_only(self, master_protocol):
        """Test send_unsolicited_response raises error in master mode.

        WHY: Unsolicited responses only available in outstation mode.
        """
        with pytest.raises(RuntimeError, match="outstation mode"):
            await master_protocol.send_unsolicited_response()

    @pytest.mark.asyncio
    async def test_unsolicited_requires_connection(self, outstation_protocol):
        """Test send_unsolicited_response requires connection.

        WHY: Cannot send without connection.
        """
        with pytest.raises(RuntimeError, match="not connected"):
            await outstation_protocol.send_unsolicited_response()

    @pytest.mark.asyncio
    async def test_unsolicited_updates_binary_input(
        self, connected_outstation, mock_adapter
    ):
        """Test send_unsolicited_response triggers binary input update.

        WHY: Update triggers unsolicited response.
        """
        result = await connected_outstation.send_unsolicited_response()

        mock_adapter.update_binary_input.assert_called_once_with(0, True)
        assert result is True

    @pytest.mark.asyncio
    async def test_unsolicited_handles_errors(self, connected_outstation, mock_adapter):
        """Test send_unsolicited_response handles errors gracefully.

        WHY: Update may fail.
        """
        mock_adapter.update_binary_input.side_effect = RuntimeError("Update failed")

        result = await connected_outstation.send_unsolicited_response()

        assert result is False


# ================================================================
# FLOOD EVENTS TESTS
# ================================================================
class TestDNP3ProtocolFloodEvents:
    """Test flood_events attack primitive (outstation mode)."""

    @pytest.mark.asyncio
    async def test_flood_outstation_mode_only(self, master_protocol):
        """Test flood_events raises error in master mode.

        WHY: Event generation only available in outstation mode.
        """
        with pytest.raises(RuntimeError, match="outstation mode"):
            await master_protocol.flood_events()

    @pytest.mark.asyncio
    async def test_flood_requires_connection(self, outstation_protocol):
        """Test flood_events requires connection.

        WHY: Cannot generate events without connection.
        """
        with pytest.raises(RuntimeError, match="not connected"):
            await outstation_protocol.flood_events()

    @pytest.mark.asyncio
    async def test_flood_no_database(self, connected_outstation, mock_adapter):
        """Test flood_events handles missing database gracefully.

        WHY: Database may not be initialized.
        """
        mock_adapter.database = None

        result = await connected_outstation.flood_events()

        assert result["success"] is True
        assert result["events_generated"] == 0

    @pytest.mark.asyncio
    async def test_flood_no_binary_inputs_attribute(
        self, connected_outstation, mock_adapter
    ):
        """Test flood_events handles missing binary_inputs attribute.

        WHY: Database may not have binary_inputs.
        """
        mock_adapter.database = Mock(spec=[])  # Spec with no attributes

        result = await connected_outstation.flood_events()

        assert result["success"] is True
        assert result["events_generated"] == 0

    @pytest.mark.asyncio
    async def test_flood_empty_database(self, connected_outstation, mock_adapter):
        """Test flood_events with empty database.

        WHY: Database may have no points configured.
        """
        mock_adapter.database = Mock()
        mock_adapter.database.binary_inputs = {}

        result = await connected_outstation.flood_events(count=10)

        assert result["success"] is True
        assert result["events_generated"] == 0

    @pytest.mark.asyncio
    async def test_flood_generates_events(self, connected_outstation, mock_adapter):
        """Test flood_events generates specified count of events.

        WHY: Core flood functionality.
        """
        mock_adapter.database = Mock()
        mock_adapter.database.binary_inputs = {0: True, 1: False}

        result = await connected_outstation.flood_events(count=10)

        assert result["success"] is True
        assert result["events_generated"] == 10
        assert mock_adapter.update_binary_input.call_count == 10

    @pytest.mark.asyncio
    async def test_flood_alternates_values(self, connected_outstation, mock_adapter):
        """Test flood_events alternates binary input values.

        WHY: Creates event changes.
        """
        mock_adapter.database = Mock()
        mock_adapter.database.binary_inputs = {0: True}

        await connected_outstation.flood_events(count=4)

        # Check alternating True/False pattern
        calls = mock_adapter.update_binary_input.call_args_list
        assert calls[0][0] == (0, True)  # i=0: i%2==0 -> True
        assert calls[1][0] == (0, False)  # i=1: i%2==1 -> False
        assert calls[2][0] == (0, True)  # i=2: i%2==0 -> True
        assert calls[3][0] == (0, False)  # i=3: i%2==1 -> False

    @pytest.mark.asyncio
    async def test_flood_cycles_through_points(
        self, connected_outstation, mock_adapter
    ):
        """Test flood_events cycles through available points.

        WHY: Distributes events across points.
        """
        mock_adapter.database = Mock()
        mock_adapter.database.binary_inputs = {5: True, 10: False, 15: True}

        await connected_outstation.flood_events(count=6)

        # Should cycle through indices 5, 10, 15, 5, 10, 15
        calls = mock_adapter.update_binary_input.call_args_list
        assert calls[0][0][0] == 5  # First call to point 5
        assert calls[1][0][0] == 10  # Second call to point 10
        assert calls[2][0][0] == 15  # Third call to point 15
        assert calls[3][0][0] == 5  # Fourth call back to point 5

    @pytest.mark.asyncio
    async def test_flood_default_count(self, connected_outstation, mock_adapter):
        """Test flood_events uses default count of 100.

        WHY: Reasonable default for stress testing.
        """
        mock_adapter.database = Mock()
        mock_adapter.database.binary_inputs = {0: True}

        result = await connected_outstation.flood_events()

        assert result["events_generated"] == 100

    @pytest.mark.asyncio
    async def test_flood_handles_errors(self, connected_outstation, mock_adapter):
        """Test flood_events handles errors gracefully.

        WHY: Updates may fail.
        """
        mock_adapter.database = Mock()
        mock_adapter.database.binary_inputs = {0: True}
        mock_adapter.update_binary_input.side_effect = RuntimeError("Update failed")

        result = await connected_outstation.flood_events(count=10)

        assert "error" in result
        assert "Update failed" in result["error"]

    @pytest.mark.asyncio
    async def test_flood_returns_expected_structure(
        self, connected_outstation, mock_adapter
    ):
        """Test flood_events returns expected data structure.

        WHY: Standard format for flood results.
        """
        mock_adapter.database = Mock()
        mock_adapter.database.binary_inputs = {0: True}

        result = await connected_outstation.flood_events(count=5)

        assert isinstance(result, dict)
        assert "events_generated" in result
        assert "success" in result


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestDNP3ProtocolIntegration:
    """Test protocol integration scenarios."""

    @pytest.mark.asyncio
    async def test_complete_outstation_workflow(
        self, outstation_protocol, mock_adapter
    ):
        """Test complete outstation attack workflow.

        WHY: Verify end-to-end outstation usage.
        """
        mock_adapter.connected = True
        mock_adapter.database = Mock()
        mock_adapter.database.binary_inputs = {0: True}

        # Connect
        await outstation_protocol.connect()
        assert outstation_protocol.connected

        # Probe
        probe_result = await outstation_protocol.probe()
        assert probe_result["connected"] is True

        # Send unsolicited
        unsol_result = await outstation_protocol.send_unsolicited_response()
        assert unsol_result is True

        # Flood events
        flood_result = await outstation_protocol.flood_events(count=5)
        assert flood_result["success"] is True

        # Disconnect
        await outstation_protocol.disconnect()
        assert not outstation_protocol.connected

    @pytest.mark.asyncio
    async def test_complete_master_workflow(self, master_protocol, mock_adapter):
        """Test complete master attack workflow.

        WHY: Verify end-to-end master usage.
        """
        mock_adapter.connected = True
        mock_adapter.read_binary_inputs.return_value = [True, False]
        mock_adapter.write_binary_output.return_value = True

        # Connect
        await master_protocol.connect()
        assert master_protocol.connected

        # Probe
        probe_result = await master_protocol.probe()
        assert probe_result["connected"] is True

        # Enumerate points
        enum_result = await master_protocol.enumerate_points()
        assert "binary_inputs" in enum_result

        # Test write capabilities
        write_result = await master_protocol.test_write_capabilities()
        assert "binary_output_successful" in write_result

        # Disconnect
        await master_protocol.disconnect()
        assert not master_protocol.connected
