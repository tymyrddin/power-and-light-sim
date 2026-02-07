# tests/integration/test_zone_policy_enforcement.py
"""Integration tests for zone-based security policy enforcement.

Tests the NetworkSimulator's implementation of the Purdue Model security zones
and inter-zone policy enforcement. Verifies that:
- Intra-zone traffic is always allowed
- Inter-zone traffic respects policy rules
- Firewall rules are properly enforced
- Protocol restrictions are applied
- Default-deny policy works for unauthorized paths
"""

import pytest

from components.network.network_simulator import NetworkSimulator
from config.config_loader import ConfigLoader

# ================================================================
# FIXTURES
# ================================================================


@pytest.fixture
async def network_simulator():
    """Create and load NetworkSimulator with full configuration.

    WHY: Integration test needs real configuration with zones and policies.
    """
    config_loader = ConfigLoader()
    net_sim = NetworkSimulator(config_loader)
    await net_sim.load()
    return net_sim


@pytest.fixture
async def network_with_exposed_services(network_simulator):
    """NetworkSimulator with test services exposed.

    WHY: Multiple tests need the same service exposure setup.
    """
    net_sim = network_simulator

    # Expose test services on control zone device
    await net_sim.expose_service("hex_turbine_plc", "modbus", 10502)  # Allowed port
    await net_sim.expose_service(
        "hex_turbine_plc", "modbus", 502
    )  # Standard port (not in firewall)
    await net_sim.expose_service("hex_turbine_plc", "http", 80)  # Different protocol
    await net_sim.expose_service("hex_turbine_plc", "modbus", 9999)  # Custom port

    return net_sim


# ================================================================
# CONFIGURATION VALIDATION
# ================================================================


class TestZonePolicyConfiguration:
    """Verify zone policy configuration is loaded correctly."""

    @pytest.mark.asyncio
    async def test_networks_loaded(self, network_simulator):
        """Test that networks are loaded from configuration.

        WHY: Need networks for zone mapping to work.
        """
        assert len(network_simulator.networks) > 0, "Should load at least one network"

    @pytest.mark.asyncio
    async def test_inter_zone_policies_loaded(self, network_simulator):
        """Test that inter-zone policies are loaded.

        WHY: Policies define allowed inter-zone communication.
        """
        assert (
            len(network_simulator.inter_zone_policies) > 0
        ), "Should load at least one inter-zone policy"

    @pytest.mark.asyncio
    async def test_network_to_zone_mappings_loaded(self, network_simulator):
        """Test that network-to-zone mappings are created.

        WHY: Need to map networks to security zones for policy lookup.
        """
        assert (
            len(network_simulator.network_to_zone) > 0
        ), "Should have network-to-zone mappings"


# ================================================================
# INTRA-ZONE TRAFFIC
# ================================================================


class TestIntraZoneTraffic:
    """Test traffic within the same security zone."""

    @pytest.mark.asyncio
    async def test_same_network_always_allowed(self, network_with_exposed_services):
        """Test that traffic within the same network is always allowed.

        WHY: Devices on same network are in same zone - no restrictions.
        """
        net_sim = network_with_exposed_services

        # Same network = always allowed, regardless of port or protocol
        result = await net_sim.can_reach(
            "turbine_network", "hex_turbine_plc", "modbus", 10502
        )

        assert result is True, "Traffic within same network should always be allowed"


# ================================================================
# INTER-ZONE TRAFFIC WITH POLICY
# ================================================================


class TestInterZoneTrafficWithPolicy:
    """Test traffic between zones with explicit policies."""

    @pytest.mark.asyncio
    async def test_operations_to_control_allowed_port(
        self, network_with_exposed_services
    ):
        """Test operations zone can reach control zone on allowed port.

        WHY: Operations zone (SCADA) needs controlled access to control zone PLCs.
        """
        net_sim = network_with_exposed_services

        # Operations can reach control on port in firewall_rules
        result = await net_sim.can_reach(
            "scada_network", "hex_turbine_plc", "modbus", 10502
        )

        assert (
            result is True
        ), "Operations -> Control on allowed port should be permitted"

    @pytest.mark.asyncio
    async def test_operations_to_control_blocked_port(
        self, network_with_exposed_services
    ):
        """Test operations zone cannot reach control zone on blocked port.

        WHY: Even with policy, specific firewall rules must be enforced.
        """
        net_sim = network_with_exposed_services

        # Port 502 not in firewall_rules, should be denied
        result = await net_sim.can_reach(
            "scada_network", "hex_turbine_plc", "modbus", 502
        )

        assert result is False, "Port not in firewall_rules should be denied"

    @pytest.mark.asyncio
    async def test_operations_to_control_blocked_protocol(
        self, network_with_exposed_services
    ):
        """Test operations zone cannot use disallowed protocol.

        WHY: Policies specify allowed protocols (e.g., Modbus but not HTTP).
        """
        net_sim = network_with_exposed_services

        # HTTP not in allowed_protocols for operations -> control
        result = await net_sim.can_reach("scada_network", "hex_turbine_plc", "http", 80)

        assert result is False, "Protocol not in allowed_protocols should be denied"

    @pytest.mark.asyncio
    async def test_operations_to_control_custom_port_blocked(
        self, network_with_exposed_services
    ):
        """Test custom ports are blocked unless explicitly allowed.

        WHY: Firewall rules must be explicit - no implicit port ranges.
        """
        net_sim = network_with_exposed_services

        # Custom port 9999 not in firewall_rules
        result = await net_sim.can_reach(
            "scada_network", "hex_turbine_plc", "modbus", 9999
        )

        assert result is False, "Custom port not in firewall_rules should be denied"


# ================================================================
# INTER-ZONE TRAFFIC WITHOUT POLICY (DEFAULT DENY)
# ================================================================


class TestInterZoneTrafficWithoutPolicy:
    """Test default-deny behavior when no policy exists."""

    @pytest.mark.asyncio
    async def test_enterprise_to_control_denied(self, network_with_exposed_services):
        """Test enterprise zone cannot reach control zone without policy.

        WHY: Default deny - enterprise shouldn't directly access control zone.
        """
        net_sim = network_with_exposed_services

        # Enterprise should NOT directly reach control (no policy exists)
        result = await net_sim.can_reach(
            "historian_network", "hex_turbine_plc", "modbus", 10502
        )

        assert (
            result is False
        ), "Enterprise -> Control should be denied (no policy, default deny)"


# ================================================================
# POLICY INSPECTION
# ================================================================


class TestPolicyInspection:
    """Test ability to inspect loaded policies."""

    @pytest.mark.asyncio
    async def test_policies_have_required_fields(self, network_simulator):
        """Test that policies have all required fields.

        WHY: Policy structure must be validated for enforcement to work.
        """
        net_sim = network_simulator

        for policy in net_sim.inter_zone_policies:
            assert "from_zone" in policy, "Policy must have from_zone"
            assert "to_zone" in policy, "Policy must have to_zone"
            assert "allowed_protocols" in policy, "Policy must have allowed_protocols"
            assert "firewall_rules" in policy, "Policy must have firewall_rules"

    @pytest.mark.asyncio
    async def test_policies_are_directional(self, network_simulator):
        """Test that policies define direction (from_zone -> to_zone).

        WHY: Zone policies are directional - A->B doesn't imply B->A.
        """
        net_sim = network_simulator

        for policy in net_sim.inter_zone_policies:
            from_zone = policy.get("from_zone")
            to_zone = policy.get("to_zone")

            assert (
                from_zone != to_zone
            ), "Policy should be between different zones (intra-zone doesn't need policy)"
