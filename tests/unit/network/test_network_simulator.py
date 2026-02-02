# tests/unit/network/test_network_simulator.py
"""Comprehensive tests for NetworkSimulator component.

Level 1 dependency - uses REAL ConfigLoader and SystemState.

Test Coverage:
- Configuration loading
- Service exposure
- Network reachability/segmentation
- Network queries
- Lifecycle management
- Concurrent access
"""

import asyncio

import pytest
import yaml

from components.network.network_simulator import NetworkSimulator
from components.state.system_state import SystemState
from config.config_loader import ConfigLoader


# ================================================================
# FIXTURES
# ================================================================
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


# ================================================================
# CONFIGURATION TESTS
# ================================================================
class TestNetworkSimulatorConfiguration:
    """Test configuration loading."""

    @pytest.mark.asyncio
    async def test_load_simple_network(self, simple_network_config):
        """Test loading basic network.

        WHY: Must load topology from YAML.
        """
        net_sim = NetworkSimulator(config_loader=simple_network_config)
        await net_sim.load()

        assert len(net_sim.networks) == 1
        assert "control_network" in net_sim.networks
        assert len(net_sim.device_networks) == 2

    @pytest.mark.asyncio
    async def test_load_segmented_networks(self, segmented_network_config):
        """Test loading multiple networks.

        WHY: Network segmentation is core security.
        """
        net_sim = NetworkSimulator(config_loader=segmented_network_config)
        await net_sim.load()

        assert len(net_sim.networks) == 2
        assert "control_network" in net_sim.networks
        assert "corporate_network" in net_sim.networks

    @pytest.mark.asyncio
    async def test_load_validates_against_system_state(self, simple_network_config):
        """Test validation with SystemState.

        WHY: Should warn about unregistered devices.
        """
        system_state = SystemState()
        await system_state.register_device("plc_1", "turbine_plc", 1, ["modbus"])

        net_sim = NetworkSimulator(
            config_loader=simple_network_config, system_state=system_state
        )
        await net_sim.load()

        assert "plc_1" in net_sim.device_networks
        assert "plc_2" in net_sim.device_networks  # Still loads, warns


# ================================================================
# SERVICE EXPOSURE TESTS
# ================================================================
class TestNetworkSimulatorServiceExposure:
    """Test service exposure."""

    @pytest.mark.asyncio
    async def test_expose_service(self):
        """Test exposing a service.

        WHY: Services must be exposed to be reachable.
        """
        net_sim = NetworkSimulator()
        await net_sim.expose_service("plc_1", "modbus", 502)

        assert ("plc_1", 502) in net_sim.services
        assert net_sim.services[("plc_1", 502)] == "modbus"

    @pytest.mark.asyncio
    async def test_expose_multiple_services(self):
        """Test exposing multiple services.

        WHY: Devices run multiple protocols.
        """
        net_sim = NetworkSimulator()
        await net_sim.expose_service("plc_1", "modbus", 502)
        await net_sim.expose_service("plc_1", "opcua", 4840)

        assert len(net_sim.services) == 2

    @pytest.mark.asyncio
    async def test_expose_service_validates_node(self):
        """Test node validation.

        WHY: Input validation.
        """
        net_sim = NetworkSimulator()

        with pytest.raises(ValueError, match="node cannot be empty"):
            await net_sim.expose_service("", "modbus", 502)

    @pytest.mark.asyncio
    async def test_expose_service_validates_protocol(self):
        """Test protocol validation.

        WHY: Input validation.
        """
        net_sim = NetworkSimulator()

        with pytest.raises(ValueError, match="protocol cannot be empty"):
            await net_sim.expose_service("plc_1", "", 502)

    @pytest.mark.asyncio
    async def test_expose_service_validates_port(self):
        """Test port validation.

        WHY: Port must be 1-65535.
        """
        net_sim = NetworkSimulator()

        with pytest.raises(ValueError, match="port must be 1-65535"):
            await net_sim.expose_service("plc_1", "modbus", 0)

    @pytest.mark.asyncio
    async def test_unexpose_service(self):
        """Test removing service.

        WHY: Services can be stopped.
        """
        net_sim = NetworkSimulator()
        await net_sim.expose_service("plc_1", "modbus", 502)

        result = await net_sim.unexpose_service("plc_1", 502)

        assert result is True
        assert ("plc_1", 502) not in net_sim.services

    @pytest.mark.asyncio
    async def test_unexpose_nonexistent_returns_false(self):
        """Test unexposing non-existent service.

        WHY: Should indicate not found.
        """
        net_sim = NetworkSimulator()
        result = await net_sim.unexpose_service("plc_1", 502)

        assert result is False


# ================================================================
# REACHABILITY TESTS
# ================================================================
class TestNetworkSimulatorReachability:
    """Test network reachability."""

    @pytest.mark.asyncio
    async def test_can_reach_same_network(self, simple_network_config):
        """Test reachability within network.

        WHY: Same network devices should communicate.
        """
        net_sim = NetworkSimulator(config_loader=simple_network_config)
        await net_sim.load()
        await net_sim.expose_service("plc_1", "modbus", 502)

        can_reach = await net_sim.can_reach("control_network", "plc_1", "modbus", 502)

        assert can_reach is True

    @pytest.mark.asyncio
    async def test_cannot_reach_different_network(self, segmented_network_config):
        """Test reachability blocked across networks.

        WHY: Network segmentation prevents access.
        """
        net_sim = NetworkSimulator(config_loader=segmented_network_config)
        await net_sim.load()
        await net_sim.expose_service("plc_1", "modbus", 502)

        can_reach = await net_sim.can_reach("corporate_network", "plc_1", "modbus", 502)

        assert can_reach is False

    @pytest.mark.asyncio
    async def test_cannot_reach_service_not_exposed(self):
        """Test service must be exposed.

        WHY: Service must be listening.
        """
        net_sim = NetworkSimulator()
        can_reach = await net_sim.can_reach("control_network", "plc_1", "modbus", 502)

        assert can_reach is False

    @pytest.mark.asyncio
    async def test_cannot_reach_protocol_mismatch(self, simple_network_config):
        """Test protocol must match.

        WHY: Must use correct protocol.
        """
        net_sim = NetworkSimulator(config_loader=simple_network_config)
        await net_sim.load()
        await net_sim.expose_service("plc_1", "modbus", 502)

        can_reach = await net_sim.can_reach("control_network", "plc_1", "opcua", 502)

        assert can_reach is False

    @pytest.mark.asyncio
    async def test_can_reach_from_device_same_network(self, simple_network_config):
        """Test device-to-device reachability.

        WHY: Devices communicate directly.
        """
        net_sim = NetworkSimulator(config_loader=simple_network_config)
        await net_sim.load()
        await net_sim.expose_service("plc_1", "modbus", 502)

        can_reach = await net_sim.can_reach_from_device("plc_2", "plc_1", "modbus", 502)

        assert can_reach is True

    @pytest.mark.asyncio
    async def test_cannot_reach_from_device_different_network(
        self, segmented_network_config
    ):
        """Test device-to-device blocked across networks.

        WHY: Segmentation applies device-to-device.
        """
        net_sim = NetworkSimulator(config_loader=segmented_network_config)
        await net_sim.load()
        await net_sim.expose_service("plc_1", "modbus", 502)

        can_reach = await net_sim.can_reach_from_device(
            "workstation_1", "plc_1", "modbus", 502
        )

        assert can_reach is False

    @pytest.mark.asyncio
    async def test_cannot_reach_from_orphan_device(self):
        """Test orphan device cannot reach.

        WHY: Unmapped devices have no connectivity.
        """
        net_sim = NetworkSimulator()
        await net_sim.expose_service("plc_1", "modbus", 502)

        can_reach = await net_sim.can_reach_from_device(
            "orphan", "plc_1", "modbus", 502
        )

        assert can_reach is False


# ================================================================
# QUERY TESTS
# ================================================================
class TestNetworkSimulatorQueries:
    """Test network queries."""

    @pytest.mark.asyncio
    async def test_get_device_networks(self, simple_network_config):
        """Test querying device networks.

        WHY: Need device network membership.
        """
        net_sim = NetworkSimulator(config_loader=simple_network_config)
        await net_sim.load()

        networks = await net_sim.get_device_networks("plc_1")

        assert "control_network" in networks

    @pytest.mark.asyncio
    async def test_get_device_networks_unknown_returns_empty(self):
        """Test unknown device returns empty.

        WHY: Should indicate not found.
        """
        net_sim = NetworkSimulator()
        networks = await net_sim.get_device_networks("unknown")

        assert networks == set()

    @pytest.mark.asyncio
    async def test_get_network_devices(self, simple_network_config):
        """Test querying network devices.

        WHY: Need to enumerate members.
        """
        net_sim = NetworkSimulator(config_loader=simple_network_config)
        await net_sim.load()

        devices = await net_sim.get_network_devices("control_network")

        assert len(devices) == 2
        assert "plc_1" in devices
        assert "plc_2" in devices

    @pytest.mark.asyncio
    async def test_get_all_services(self):
        """Test getting all services.

        WHY: Need to enumerate services.
        """
        net_sim = NetworkSimulator()
        await net_sim.expose_service("plc_1", "modbus", 502)
        await net_sim.expose_service("plc_2", "opcua", 4840)

        services = await net_sim.get_all_services()

        assert len(services) == 2

    @pytest.mark.asyncio
    async def test_get_device_services(self):
        """Test getting device services.

        WHY: Need to know what device offers.
        """
        net_sim = NetworkSimulator()
        await net_sim.expose_service("plc_1", "modbus", 502)
        await net_sim.expose_service("plc_1", "opcua", 4840)

        services = await net_sim.get_device_services("plc_1")

        assert len(services) == 2
        assert services[502] == "modbus"


# ================================================================
# SUMMARY TESTS
# ================================================================
class TestNetworkSimulatorSummary:
    """Test summary reporting."""

    @pytest.mark.asyncio
    async def test_get_summary_structure(self):
        """Test summary structure.

        WHY: Used for monitoring.
        """
        net_sim = NetworkSimulator()
        summary = await net_sim.get_summary()

        assert "loaded" in summary
        assert "networks" in summary
        assert "devices" in summary
        assert "services" in summary

    @pytest.mark.asyncio
    async def test_get_summary_counts(self, simple_network_config):
        """Test summary counts.

        WHY: Must reflect topology.
        """
        net_sim = NetworkSimulator(config_loader=simple_network_config)
        await net_sim.load()
        await net_sim.expose_service("plc_1", "modbus", 502)

        summary = await net_sim.get_summary()

        assert summary["loaded"] is True
        assert summary["networks"]["count"] == 1
        assert summary["devices"]["count"] == 2
        assert summary["services"]["count"] == 1


# ================================================================
# LIFECYCLE TESTS
# ================================================================
class TestNetworkSimulatorLifecycle:
    """Test lifecycle."""

    @pytest.mark.asyncio
    async def test_reset_clears_all(self, simple_network_config):
        """Test reset clears everything.

        WHY: Reset returns to clean slate.
        """
        net_sim = NetworkSimulator(config_loader=simple_network_config)
        await net_sim.load()
        await net_sim.expose_service("plc_1", "modbus", 502)

        await net_sim.reset()

        assert len(net_sim.networks) == 0
        assert len(net_sim.device_networks) == 0
        assert len(net_sim.services) == 0
        assert net_sim._loaded is False


# ================================================================
# CONCURRENCY TESTS
# ================================================================
class TestNetworkSimulatorConcurrency:
    """Test concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_service_exposure(self):
        """Test concurrent exposures safe.

        WHY: Multiple coroutines expose services.
        """
        net_sim = NetworkSimulator()

        async def expose_services(start: int):
            for i in range(10):
                await net_sim.expose_service(f"plc_{start + i}", "modbus", 502 + i)

        await asyncio.gather(
            expose_services(0),
            expose_services(10),
            expose_services(20),
        )

        assert len(net_sim.services) == 30

    @pytest.mark.asyncio
    async def test_concurrent_reachability_checks(self, simple_network_config):
        """Test concurrent checks safe.

        WHY: Many simultaneous checks.
        """
        net_sim = NetworkSimulator(config_loader=simple_network_config)
        await net_sim.load()
        await net_sim.expose_service("plc_1", "modbus", 502)

        results = []

        async def check():
            for _ in range(50):
                result = await net_sim.can_reach(
                    "control_network", "plc_1", "modbus", 502
                )
                results.append(result)

        await asyncio.gather(*[check() for _ in range(5)])

        assert len(results) == 250
        assert all(results)


# ================================================================
# EDGE CASES
# ================================================================
class TestNetworkSimulatorEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_orphan_device(self):
        """Test device on no networks.

        WHY: Should handle gracefully.
        """
        net_sim = NetworkSimulator()
        networks = await net_sim.get_device_networks("orphan")

        assert networks == set()

    @pytest.mark.asyncio
    async def test_same_port_different_devices(self):
        """Test same port on multiple devices.

        WHY: Ports are per-device.
        """
        net_sim = NetworkSimulator()
        await net_sim.expose_service("plc_1", "modbus", 502)
        await net_sim.expose_service("plc_2", "modbus", 502)
        await net_sim.expose_service("plc_3", "modbus", 502)

        assert len(net_sim.services) == 3
