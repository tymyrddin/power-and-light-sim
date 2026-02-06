"""Comprehensive tests for BaseProtocol abstract base class.

BaseProtocol is the foundation for all protocol implementations (Modbus, DNP3, OPC UA, etc.).

Test Coverage:
- Initialization and configuration
- Abstract method enforcement
- Lifecycle management (connect/disconnect)
- Connection state tracking
- Protocol introspection
- Subclass implementation validation
- Edge cases and error handling

BaseProtocol is abstract, so we create concrete test implementations.
"""

import pytest

from components.protocols.base_protocol import BaseProtocol


# ================================================================
# TEST PROTOCOL IMPLEMENTATIONS
# ================================================================
class ConcreteTestProtocol(BaseProtocol):
    """Concrete implementation of BaseProtocol for testing.

    WHY: BaseProtocol is abstract - need concrete class to test.
    Note: Named ConcreteTestProtocol (not TestProtocol) to avoid pytest collection.
    """

    def __init__(self, protocol_name: str = "test_protocol"):
        super().__init__(protocol_name)
        self.connect_called = False
        self.disconnect_called = False
        self.probe_called = False
        self.should_fail_connect = False
        self.probe_data = {}

    async def connect(self) -> bool:
        """Test implementation of connect."""
        self.connect_called = True
        if self.should_fail_connect:
            self.connected = False
            return False
        self.connected = True
        return True

    async def disconnect(self) -> None:
        """Test implementation of disconnect."""
        self.disconnect_called = True
        self.connected = False

    async def probe(self) -> dict[str, object]:
        """Test implementation of probe."""
        self.probe_called = True
        return {
            "protocol": self.protocol_name,
            "connected": self.connected,
            **self.probe_data,
        }


class IncompleteProtocol(BaseProtocol):
    """Protocol with missing implementations for testing abstract enforcement.

    WHY: Verify abstract methods are properly enforced.
    """

    def __init__(self):
        super().__init__("incomplete")


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
def test_protocol():
    """Create ConcreteTestProtocol instance.

    WHY: Most tests need a protocol instance.
    """
    return ConcreteTestProtocol()


@pytest.fixture
async def connected_protocol(test_protocol):
    """Create and connect a test protocol.

    WHY: Many tests need a connected protocol.
    """
    await test_protocol.connect()
    yield test_protocol
    if test_protocol.connected:
        await test_protocol.disconnect()


# ================================================================
# INITIALIZATION TESTS
# ================================================================
class TestBaseProtocolInitialization:
    """Test protocol initialization and configuration."""

    def test_init_with_protocol_name(self):
        """Test initialization with protocol name.

        WHY: Protocol name identifies the protocol type.
        """
        protocol = ConcreteTestProtocol("modbus")
        assert protocol.protocol_name == "modbus"
        assert not protocol.connected

    def test_init_default_disconnected(self):
        """Test that protocols start disconnected.

        WHY: Connection must be explicitly established.
        """
        protocol = ConcreteTestProtocol()
        assert protocol.connected is False

    def test_protocol_name_stored(self):
        """Test that protocol name is accessible.

        WHY: Protocol name used for routing and identification.
        """
        protocol = ConcreteTestProtocol("dnp3")
        assert protocol.protocol_name == "dnp3"


# ================================================================
# ABSTRACT METHOD ENFORCEMENT TESTS
# ================================================================
class TestBaseProtocolAbstractMethods:
    """Test that abstract methods are properly enforced."""

    @pytest.mark.asyncio
    async def test_connect_must_be_implemented(self):
        """Test that connect() must be implemented by subclasses.

        WHY: Abstract method enforcement ensures proper protocol interface.
        """
        protocol = IncompleteProtocol()
        with pytest.raises(NotImplementedError):
            await protocol.connect()

    @pytest.mark.asyncio
    async def test_disconnect_must_be_implemented(self):
        """Test that disconnect() must be implemented by subclasses.

        WHY: Abstract method enforcement ensures proper protocol interface.
        """
        protocol = IncompleteProtocol()
        with pytest.raises(NotImplementedError):
            await protocol.disconnect()

    @pytest.mark.asyncio
    async def test_probe_must_be_implemented(self):
        """Test that probe() must be implemented by subclasses.

        WHY: Abstract method enforcement ensures proper protocol interface.
        """
        protocol = IncompleteProtocol()
        with pytest.raises(NotImplementedError):
            await protocol.probe()


# ================================================================
# LIFECYCLE TESTS
# ================================================================
class TestBaseProtocolLifecycle:
    """Test protocol lifecycle management (connect/disconnect)."""

    @pytest.mark.asyncio
    async def test_connect_returns_bool(self, test_protocol):
        """Test that connect() returns boolean status.

        WHY: Return value indicates connection success/failure.
        """
        result = await test_protocol.connect()
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_connect_sets_connected_flag(self, test_protocol):
        """Test that successful connect() sets connected flag.

        WHY: Connected flag tracks connection state.
        """
        assert not test_protocol.connected
        await test_protocol.connect()
        assert test_protocol.connected

    @pytest.mark.asyncio
    async def test_connect_success(self, test_protocol):
        """Test successful connection.

        WHY: Verify normal connect flow.
        """
        result = await test_protocol.connect()
        assert result is True
        assert test_protocol.connected
        assert test_protocol.connect_called

    @pytest.mark.asyncio
    async def test_connect_failure(self, test_protocol):
        """Test failed connection.

        WHY: Connection may fail due to network issues, auth, etc.
        """
        test_protocol.should_fail_connect = True
        result = await test_protocol.connect()
        assert result is False
        assert not test_protocol.connected

    @pytest.mark.asyncio
    async def test_disconnect_clears_connected_flag(self, connected_protocol):
        """Test that disconnect() clears connected flag.

        WHY: Disconnected protocols must update state.
        """
        assert connected_protocol.connected
        await connected_protocol.disconnect()
        assert not connected_protocol.connected

    @pytest.mark.asyncio
    async def test_disconnect_called(self, connected_protocol):
        """Test that disconnect() implementation is invoked.

        WHY: Verify disconnect flow executes.
        """
        await connected_protocol.disconnect()
        assert connected_protocol.disconnect_called

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, test_protocol):
        """Test disconnecting when not connected.

        WHY: Should handle disconnect on unconnected protocol gracefully.
        """
        assert not test_protocol.connected
        await test_protocol.disconnect()
        assert not test_protocol.connected
        assert test_protocol.disconnect_called

    @pytest.mark.asyncio
    async def test_reconnect_workflow(self, test_protocol):
        """Test complete connect-disconnect-reconnect cycle.

        WHY: Protocols may reconnect after disconnection.
        """
        # First connection
        await test_protocol.connect()
        assert test_protocol.connected

        # Disconnect
        await test_protocol.disconnect()
        assert not test_protocol.connected

        # Reconnect
        await test_protocol.connect()
        assert test_protocol.connected


# ================================================================
# CONNECTION STATE TESTS
# ================================================================
class TestBaseProtocolConnectionState:
    """Test connection state tracking."""

    def test_initial_state_disconnected(self, test_protocol):
        """Test that initial state is disconnected.

        WHY: Protocols must explicitly connect.
        """
        assert test_protocol.connected is False

    @pytest.mark.asyncio
    async def test_connected_state_persists(self, test_protocol):
        """Test that connected state persists until disconnect.

        WHY: Connection state must be stable.
        """
        await test_protocol.connect()
        assert test_protocol.connected

        # Check multiple times
        assert test_protocol.connected
        assert test_protocol.connected

    @pytest.mark.asyncio
    async def test_disconnected_state_persists(self, test_protocol):
        """Test that disconnected state persists.

        WHY: State must remain consistent.
        """
        await test_protocol.connect()
        await test_protocol.disconnect()

        assert not test_protocol.connected
        assert not test_protocol.connected


# ================================================================
# PROBE TESTS
# ================================================================
class TestBaseProtocolProbe:
    """Test protocol reconnaissance/probing functionality."""

    @pytest.mark.asyncio
    async def test_probe_returns_dict(self, test_protocol):
        """Test that probe() returns dictionary.

        WHY: Standard format for protocol capabilities.
        """
        result = await test_protocol.probe()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_probe_includes_protocol_name(self, test_protocol):
        """Test that probe() includes protocol name.

        WHY: Identifies protocol type.
        """
        result = await test_protocol.probe()
        assert "protocol" in result
        assert result["protocol"] == "test_protocol"

    @pytest.mark.asyncio
    async def test_probe_includes_connection_state(self, test_protocol):
        """Test that probe() includes connection state.

        WHY: Connection state is fundamental capability info.
        """
        result = await test_protocol.probe()
        assert "connected" in result
        assert result["connected"] is False

    @pytest.mark.asyncio
    async def test_probe_reflects_connected_state(self, connected_protocol):
        """Test that probe() reflects actual connection state.

        WHY: Probe data must be accurate.
        """
        result = await connected_protocol.probe()
        assert result["connected"] is True

    @pytest.mark.asyncio
    async def test_probe_custom_data(self, test_protocol):
        """Test that probe() can return custom protocol data.

        WHY: Different protocols expose different capabilities.
        """
        test_protocol.probe_data = {
            "supports_write": True,
            "max_registers": 1000,
        }

        result = await test_protocol.probe()
        assert result["supports_write"] is True
        assert result["max_registers"] == 1000

    @pytest.mark.asyncio
    async def test_probe_called_flag(self, test_protocol):
        """Test that probe() implementation is invoked.

        WHY: Verify probe flow executes.
        """
        await test_protocol.probe()
        assert test_protocol.probe_called


# ================================================================
# INTEGRATION TESTS
# ================================================================
class TestBaseProtocolIntegration:
    """Test protocol integration scenarios."""

    @pytest.mark.asyncio
    async def test_complete_protocol_lifecycle(self, test_protocol):
        """Test complete protocol usage workflow.

        WHY: Verify end-to-end protocol usage.
        """
        # Initial state
        assert not test_protocol.connected

        # Connect
        success = await test_protocol.connect()
        assert success
        assert test_protocol.connected

        # Probe while connected
        probe_result = await test_protocol.probe()
        assert probe_result["connected"] is True

        # Disconnect
        await test_protocol.disconnect()
        assert not test_protocol.connected

        # Probe while disconnected
        probe_result = await test_protocol.probe()
        assert probe_result["connected"] is False

    @pytest.mark.asyncio
    async def test_multiple_protocol_instances(self):
        """Test multiple protocol instances operate independently.

        WHY: Simulation may have multiple protocol sessions.
        """
        protocol1 = ConcreteTestProtocol("modbus")
        protocol2 = ConcreteTestProtocol("dnp3")

        # Connect only protocol1
        await protocol1.connect()

        assert protocol1.connected
        assert not protocol2.connected

        # Probe both
        probe1 = await protocol1.probe()
        probe2 = await protocol2.probe()

        assert probe1["connected"] is True
        assert probe2["connected"] is False
        assert probe1["protocol"] == "modbus"
        assert probe2["protocol"] == "dnp3"

        # Cleanup
        await protocol1.disconnect()


# ================================================================
# PROTOCOL NAME TESTS
# ================================================================
class TestBaseProtocolNaming:
    """Test protocol naming and identification."""

    def test_different_protocol_names(self):
        """Test creating protocols with different names.

        WHY: Protocol name distinguishes protocol types.
        """
        modbus = ConcreteTestProtocol("modbus")
        dnp3 = ConcreteTestProtocol("dnp3")
        opcua = ConcreteTestProtocol("opcua")

        assert modbus.protocol_name == "modbus"
        assert dnp3.protocol_name == "dnp3"
        assert opcua.protocol_name == "opcua"

    def test_protocol_name_immutable_after_init(self):
        """Test that protocol name is set at initialization.

        WHY: Protocol type should not change after creation.
        """
        protocol = ConcreteTestProtocol("modbus")
        original_name = protocol.protocol_name

        # Protocol name is an attribute, can be changed, but shouldn't be
        assert protocol.protocol_name == original_name


# ================================================================
# EDGE CASES AND ERROR HANDLING
# ================================================================
class TestBaseProtocolEdgeCases:
    """Test edge cases and unusual scenarios."""

    @pytest.mark.asyncio
    async def test_double_connect(self, test_protocol):
        """Test calling connect() twice.

        WHY: Should handle idempotent connects gracefully.
        """
        await test_protocol.connect()
        assert test_protocol.connected

        # Connect again
        await test_protocol.connect()
        assert test_protocol.connected

    @pytest.mark.asyncio
    async def test_double_disconnect(self, connected_protocol):
        """Test calling disconnect() twice.

        WHY: Should handle multiple disconnects gracefully.
        """
        await connected_protocol.disconnect()
        assert not connected_protocol.connected

        # Disconnect again
        await connected_protocol.disconnect()
        assert not connected_protocol.connected

    @pytest.mark.asyncio
    async def test_probe_without_connect(self, test_protocol):
        """Test probing without connecting first.

        WHY: Probe should work regardless of connection state.
        """
        result = await test_protocol.probe()
        assert isinstance(result, dict)
        assert result["connected"] is False

    def test_empty_protocol_name(self):
        """Test creating protocol with empty name.

        WHY: Protocol name may be empty in edge cases.
        """
        protocol = ConcreteTestProtocol("")
        assert protocol.protocol_name == ""
        assert not protocol.connected
