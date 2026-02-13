# tests/unit/network/test_protocol_simulator.py
"""Comprehensive tests for ProtocolSimulator (NetworkGateway) component.

Level 2 dependency - uses REAL NetworkSimulator.

Test Coverage:
- Gateway registration
- Lifecycle management (start/stop)
- Summary reporting
- Input validation
- Concurrent operations
- Internal port offset computation
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from components.network.connection_registry import ConnectionRegistry
from components.network.network_simulator import NetworkSimulator
from components.network.protocol_simulator import (
    INTERNAL_PORT_OFFSET,
    ProtocolSimulator,
)
from config.config_loader import ConfigLoader


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture(autouse=True)
def reset_registry():
    """Reset ConnectionRegistry singleton between tests."""
    ConnectionRegistry.reset_singleton()
    yield
    ConnectionRegistry.reset_singleton()


@pytest.fixture
def simple_network_config(temp_config_dir):
    """Create simple network configuration."""
    config = {
        "networks": [{"name": "control_network", "vlan": 100}],
        "connections": {"control_network": ["plc_1", "plc_2"]},
    }

    (temp_config_dir / "network.yml").write_text(yaml.dump(config))
    (temp_config_dir / "devices.yml").write_text(yaml.dump({"devices": []}))

    return ConfigLoader(config_dir=str(temp_config_dir))


@pytest.fixture
def segmented_network_config(temp_config_dir):
    """Create segmented network configuration."""
    config = {
        "networks": [
            {"name": "control_network", "vlan": 100},
            {"name": "corporate_network", "vlan": 200},
        ],
        "connections": {
            "control_network": ["plc_1", "scada_1"],
            "corporate_network": ["workstation_1"],
        },
    }

    (temp_config_dir / "network.yml").write_text(yaml.dump(config))
    (temp_config_dir / "devices.yml").write_text(yaml.dump({"devices": []}))

    return ConfigLoader(config_dir=str(temp_config_dir))


@pytest.fixture
async def network_sim(simple_network_config):
    """Create loaded NetworkSimulator."""
    net_sim = NetworkSimulator(config_loader=simple_network_config)
    await net_sim.load()
    return net_sim


@pytest.fixture
async def segmented_network_sim(segmented_network_config):
    """Create loaded segmented NetworkSimulator."""
    net_sim = NetworkSimulator(config_loader=segmented_network_config)
    await net_sim.load()
    return net_sim


# ================================================================
# REGISTRATION TESTS
# ================================================================
class TestProtocolSimulatorRegistration:
    """Test gateway registration."""

    @pytest.mark.asyncio
    async def test_register_listener(self, network_sim):
        """Test registering a gateway."""
        proto_sim = ProtocolSimulator(network_sim)

        await proto_sim.register(
            node="plc_1",
            network="control_network",
            port=502,
            protocol="modbus",
        )

        assert len(proto_sim.listeners) == 1
        assert proto_sim.listeners[0].node == "plc_1"
        assert proto_sim.listeners[0].port == 502
        assert proto_sim.listeners[0].internal_port == 502 + INTERNAL_PORT_OFFSET

    @pytest.mark.asyncio
    async def test_register_multiple_listeners(self, network_sim):
        """Test registering multiple gateways."""
        proto_sim = ProtocolSimulator(network_sim)

        await proto_sim.register(
            node="plc_1",
            network="control_network",
            port=502,
            protocol="modbus",
        )
        await proto_sim.register(
            node="plc_1",
            network="control_network",
            port=4840,
            protocol="opcua",
        )

        assert len(proto_sim.listeners) == 2

    @pytest.mark.asyncio
    async def test_register_exposes_service_in_network(self, network_sim):
        """Test registration exposes service in network simulator."""
        proto_sim = ProtocolSimulator(network_sim)

        await proto_sim.register(
            node="plc_1",
            network="control_network",
            port=502,
            protocol="modbus",
        )

        services = await network_sim.get_all_services()
        assert ("plc_1", 502) in services
        assert services[("plc_1", 502)] == "modbus"

    @pytest.mark.asyncio
    async def test_register_validates_empty_node(self, network_sim):
        """Test node validation."""
        proto_sim = ProtocolSimulator(network_sim)

        with pytest.raises(ValueError, match="node cannot be empty"):
            await proto_sim.register(
                node="",
                network="control_network",
                port=502,
                protocol="modbus",
            )

    @pytest.mark.asyncio
    async def test_register_validates_empty_network(self, network_sim):
        """Test network validation."""
        proto_sim = ProtocolSimulator(network_sim)

        with pytest.raises(ValueError, match="network cannot be empty"):
            await proto_sim.register(
                node="plc_1",
                network="",
                port=502,
                protocol="modbus",
            )

    @pytest.mark.asyncio
    async def test_register_validates_empty_protocol(self, network_sim):
        """Test protocol validation."""
        proto_sim = ProtocolSimulator(network_sim)

        with pytest.raises(ValueError, match="protocol cannot be empty"):
            await proto_sim.register(
                node="plc_1",
                network="control_network",
                port=502,
                protocol="",
            )

    @pytest.mark.asyncio
    async def test_register_validates_port_range(self, network_sim):
        """Test port validation."""
        proto_sim = ProtocolSimulator(network_sim)

        with pytest.raises(ValueError, match="port must be 1-65535"):
            await proto_sim.register(
                node="plc_1",
                network="control_network",
                port=0,
                protocol="modbus",
            )

        with pytest.raises(ValueError, match="port must be 1-65535"):
            await proto_sim.register(
                node="plc_1",
                network="control_network",
                port=65536,
                protocol="modbus",
            )


# ================================================================
# LIFECYCLE TESTS
# ================================================================
class TestProtocolSimulatorLifecycle:
    """Test lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_with_no_listeners_warns(self, network_sim):
        """Test starting with no listeners logs warning."""
        proto_sim = ProtocolSimulator(network_sim)

        await proto_sim.start()

        assert len(proto_sim.listeners) == 0

    @pytest.mark.asyncio
    async def test_start_creates_servers(self, network_sim):
        """Test starting creates TCP servers (gateways)."""
        proto_sim = ProtocolSimulator(network_sim)

        await proto_sim.register(
            node="plc_1",
            network="control_network",
            port=15502,
            protocol="modbus",
        )

        await proto_sim.start()

        try:
            assert proto_sim.listeners[0].server is not None
            assert proto_sim.listeners[0].server.is_serving()
        finally:
            await proto_sim.stop()

    @pytest.mark.asyncio
    async def test_stop_closes_servers(self, network_sim):
        """Test stopping closes TCP servers."""
        proto_sim = ProtocolSimulator(network_sim)

        await proto_sim.register(
            node="plc_1",
            network="control_network",
            port=15503,
            protocol="modbus",
        )

        await proto_sim.start()
        await proto_sim.stop()

        assert not proto_sim.listeners[0].server.is_serving()

    @pytest.mark.asyncio
    async def test_stop_with_no_listeners(self, network_sim):
        """Test stopping with no listeners is safe."""
        proto_sim = ProtocolSimulator(network_sim)

        await proto_sim.stop()


# ================================================================
# SUMMARY TESTS
# ================================================================
class TestProtocolSimulatorSummary:
    """Test summary reporting."""

    @pytest.mark.asyncio
    async def test_get_summary_structure(self, network_sim):
        """Test summary structure."""
        proto_sim = ProtocolSimulator(network_sim)
        summary = proto_sim.get_summary()

        assert "listeners" in summary
        assert "count" in summary["listeners"]
        assert "details" in summary["listeners"]

    @pytest.mark.asyncio
    async def test_get_summary_counts(self, network_sim):
        """Test summary reflects registered gateways."""
        proto_sim = ProtocolSimulator(network_sim)

        await proto_sim.register(
            node="plc_1",
            network="control_network",
            port=502,
            protocol="modbus",
        )

        summary = proto_sim.get_summary()

        assert summary["listeners"]["count"] == 1
        assert len(summary["listeners"]["details"]) == 1
        detail = summary["listeners"]["details"][0]
        assert detail["node"] == "plc_1"
        assert detail["port"] == 502
        assert detail["internal_port"] == 502 + INTERNAL_PORT_OFFSET
        assert detail["protocol"] == "modbus"

    @pytest.mark.asyncio
    async def test_get_summary_connection_stats(self, network_sim):
        """Test summary includes connection statistics."""
        proto_sim = ProtocolSimulator(network_sim)

        await proto_sim.register(
            node="plc_1",
            network="control_network",
            port=502,
            protocol="modbus",
        )

        summary = proto_sim.get_summary()
        detail = summary["listeners"]["details"][0]

        assert "active_connections" in detail
        assert "total_connections" in detail
        assert "denied_connections" in detail


# ================================================================
# GATEWAY CONNECTION TESTS
# ================================================================
class TestGatewayConnectionHandling:
    """Test gateway connection handling."""

    @pytest.mark.asyncio
    async def test_gateway_tracks_connection_counts(self, network_sim):
        """Test gateway tracks connection statistics."""
        proto_sim = ProtocolSimulator(network_sim)

        await proto_sim.register(
            node="plc_1",
            network="control_network",
            port=15504,
            protocol="modbus",
        )

        await proto_sim.start()

        try:
            listener = proto_sim.listeners[0]

            assert listener.total_connections == 0
            assert listener.active_connections == 0
            assert listener.denied_connections == 0

            # Connect - will fail to pipe to backend (no protocol server on loopback)
            # but total_connections should still increment
            reader, writer = await asyncio.open_connection("127.0.0.1", 15504)
            await asyncio.sleep(0.1)

            assert listener.total_connections == 1

            writer.close()
            await writer.wait_closed()

        finally:
            await proto_sim.stop()

    @pytest.mark.asyncio
    async def test_connection_allowed_same_network(self, network_sim):
        """Test same-network reachability check passes."""
        proto_sim = ProtocolSimulator(network_sim)

        await proto_sim.register(
            node="plc_1",
            network="control_network",
            port=15505,
            protocol="modbus",
        )

        await proto_sim.start()

        try:
            can_reach = await network_sim.can_reach(
                "control_network", "plc_1", "modbus", 15505
            )
            assert can_reach is True

        finally:
            await proto_sim.stop()


# ================================================================
# CONCURRENT REGISTRATION TESTS
# ================================================================
class TestProtocolSimulatorConcurrency:
    """Test concurrent operations."""

    @pytest.mark.asyncio
    async def test_concurrent_registration(self, network_sim):
        """Test concurrent registrations are safe."""
        proto_sim = ProtocolSimulator(network_sim)

        async def register_listeners(start_port: int):
            for i in range(5):
                await proto_sim.register(
                    node=f"plc_{start_port + i}",
                    network="control_network",
                    port=start_port + i,
                    protocol="modbus",
                )

        await asyncio.gather(
            register_listeners(10000),
            register_listeners(10100),
            register_listeners(10200),
        )

        assert len(proto_sim.listeners) == 15


# ================================================================
# ERROR HANDLING TESTS
# ================================================================
class TestProtocolSimulatorErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_start_failure_partial(self, network_sim):
        """Test partial start failure is handled."""
        proto_sim = ProtocolSimulator(network_sim)

        # Register on same port twice - second should fail
        await proto_sim.register(
            node="plc_1",
            network="control_network",
            port=15508,
            protocol="modbus",
        )
        await proto_sim.register(
            node="plc_2",
            network="control_network",
            port=15508,  # Same port - will fail
            protocol="modbus",
        )

        # Should not raise, but will log error
        await proto_sim.start()

        await proto_sim.stop()
