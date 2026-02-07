# components/network/network_simulator.py
"""
Async network reachability simulator.

Simulates network topology and connectivity based on configuration.
Enforces network segmentation rules for security testing.

Source of truth:
- config/network.yml (network definitions and device membership)
- SystemState (device registry validation)
"""

import asyncio
from collections import Counter
from typing import Any

from components.security.logging_system import (
    EventSeverity,
    ICSLogger,
    get_logger,
)
from components.state.system_state import SystemState
from config.config_loader import ConfigLoader

__all__ = ["NetworkSimulator"]


class NetworkSimulator:
    """
    Network topology and reachability simulator.

    Enforces network segmentation rules based on configuration.
    Validates device membership and service exposure.

    Example:
        >>> net_sim = NetworkSimulator(config_loader, system_state)
        >>> await net_sim.load()
        >>> await net_sim.expose_service("turbine_plc_1", "modbus", 502)
        >>> can_reach = await net_sim.can_reach(
        ...     "corporate_network", "turbine_plc_1", "modbus", 502
        ... )
    """

    def __init__(
        self,
        config_loader: ConfigLoader | None = None,
        system_state: SystemState | None = None,
    ):
        """Initialise network simulator.

        Args:
            config_loader: Configuration loader instance (creates new if None)
            system_state: System state instance for device validation (optional)
        """
        self.config_loader = config_loader or ConfigLoader()
        self.system_state = system_state

        self.networks: dict[str, dict[str, Any]] = {}
        self.device_networks: dict[str, set[str]] = {}
        self.services: dict[tuple[str, int], str] = {}

        # Zone-based security policies
        self.inter_zone_policies: list[dict[str, Any]] = []
        self.network_to_zone: dict[str, str] = {}  # network_name -> zone_name

        self._lock = asyncio.Lock()
        self._loaded = False
        self.logger: ICSLogger = get_logger(__name__, device="network_simulator")

    # ----------------------------------------------------------------
    # Configuration loading
    # ----------------------------------------------------------------

    async def load(self) -> None:
        """Load network configuration from config/network.yml.

        Validates network topology and device membership.

        Raises:
            FileNotFoundError: If network.yml doesn't exist
            ValueError: If configuration is invalid
        """
        async with self._lock:
            try:
                config = self.config_loader.load_all()

                # Load network definitions from zones hierarchy
                # Support both flat "networks" list and hierarchical "zones" structure
                zones = config.get("zones", [])
                flat_networks = config.get("networks", [])

                all_networks = []

                # Extract networks from zones (Purdue model hierarchy)
                for zone in zones:
                    zone_networks = zone.get("networks", [])
                    for net in zone_networks:
                        # Add zone metadata to network
                        net["zone"] = zone.get("name")
                        net["zone_description"] = zone.get("description")
                        net["security_level"] = zone.get("security_level")
                        all_networks.append(net)

                # Add flat networks if present (backwards compatibility)
                all_networks.extend(flat_networks)

                if not all_networks:
                    self.logger.warning("No networks defined in network.yml")

                self.networks = {net["name"]: net for net in all_networks}
                self.logger.info(
                    f"Loaded {len(self.networks)} network(s): {list(self.networks.keys())}"
                )

                # Load device-to-network mappings
                self.device_networks.clear()
                connections = config.get("connections", {})

                for network_name, devices in connections.items():
                    if network_name not in self.networks:
                        self.logger.warning(
                            f"Connection references unknown network: {network_name}"
                        )
                        continue

                    if not isinstance(devices, list):
                        self.logger.warning(
                            f"Invalid device list for network {network_name}"
                        )
                        continue

                    for device_entry in devices:
                        # Extract device name from connection entry
                        # Supports both string format and dict format with "device" key
                        if isinstance(device_entry, str):
                            device_name = device_entry
                            device_ip = None
                        elif isinstance(device_entry, dict):
                            device_name = device_entry.get("device")
                            device_ip = device_entry.get("ip")
                            if not device_name:
                                self.logger.warning(
                                    f"Connection entry missing 'device' field in {network_name}"
                                )
                                continue
                        else:
                            self.logger.warning(
                                f"Invalid connection entry format in {network_name}: {device_entry}"
                            )
                            continue

                        # Validate device exists in system state if available
                        if self.system_state:
                            device_state = await self.system_state.get_device(
                                device_name
                            )
                            if not device_state:
                                self.logger.warning(
                                    f"Network config references unregistered device: {device_name}"
                                )

                        self.device_networks.setdefault(device_name, set()).add(
                            network_name
                        )

                        if device_ip:
                            self.logger.debug(
                                f"Device {device_name} ({device_ip}) connected to network {network_name}"
                            )
                        else:
                            self.logger.debug(
                                f"Device {device_name} connected to network {network_name}"
                            )

                device_count = len(self.device_networks)
                self.logger.info(f"Mapped {device_count} device(s) to networks")

                # Build network-to-zone mapping
                self.network_to_zone.clear()
                for network_name, network_info in self.networks.items():
                    zone = network_info.get("zone")
                    if zone:
                        self.network_to_zone[network_name] = zone

                # Load inter-zone security policies
                self.inter_zone_policies.clear()
                inter_zone_routing = config.get("inter_zone_routing", [])
                for policy in inter_zone_routing:
                    self.inter_zone_policies.append(policy)

                if self.inter_zone_policies:
                    self.logger.info(
                        f"Loaded {len(self.inter_zone_policies)} inter-zone security policy(ies)"
                    )
                else:
                    self.logger.warning("No inter-zone security policies defined")

                self._loaded = True

            except FileNotFoundError as e:
                self.logger.error(f"Network configuration file not found: {e}")
                raise
            except Exception as e:
                self.logger.error(f"Failed to load network configuration: {e}")
                raise ValueError(f"Invalid network configuration: {e}") from e

    # ----------------------------------------------------------------
    # Service exposure
    # ----------------------------------------------------------------

    async def expose_service(self, node: str, protocol: str, port: int) -> None:
        """Expose a service on a node.

        Registers that a node is listening on a specific port with a protocol.

        Args:
            node: Device name providing the service
            protocol: Protocol name (modbus, opcua, iec104, etc.)
            port: TCP port number

        Raises:
            ValueError: If parameters are invalid
        """
        if not node:
            raise ValueError("node cannot be empty")
        if not protocol:
            raise ValueError("protocol cannot be empty")
        if not (0 < port < 65536):
            raise ValueError(f"port must be 1-65535, got {port}")

        async with self._lock:
            # Validate device exists in system state
            if self.system_state:
                device_state = await self.system_state.get_device(node)
                if not device_state:
                    self.logger.warning(
                        f"Exposing service on unregistered device: {node}"
                    )

            # Check if device is on any network
            if node not in self.device_networks:
                self.logger.warning(
                    f"Device {node} not connected to any network, "
                    f"service {protocol}:{port} may be unreachable"
                )

            self.services[(node, port)] = protocol
            networks = self.device_networks.get(node, set())
            self.logger.info(
                f"Exposed service: {node}:{port} ({protocol}) "
                f"on networks {networks or 'none'}"
            )

    async def unexpose_service(self, node: str, port: int) -> bool:
        """Remove an exposed service.

        Args:
            node: Device name
            port: TCP port number

        Returns:
            True if service was removed, False if it didn't exist
        """
        async with self._lock:
            key = (node, port)
            if key in self.services:
                protocol = self.services[key]
                del self.services[key]
                self.logger.info(f"Unexposed service: {node}:{port} ({protocol})")
                return True
            return False

    # ----------------------------------------------------------------
    # Zone policy helpers
    # ----------------------------------------------------------------

    def _get_zone_for_network(self, network_name: str) -> str | None:
        """Get zone name for a network.

        Args:
            network_name: Network name

        Returns:
            Zone name, or None if network not found or not in a zone
        """
        return self.network_to_zone.get(network_name)

    def _check_zone_policy(
        self,
        src_zone: str,
        dst_zone: str,
        protocol: str,
        port: int,
    ) -> tuple[bool, str]:
        """Check if zone-to-zone connection is allowed by policy.

        Args:
            src_zone: Source zone name
            dst_zone: Destination zone name
            protocol: Protocol being used
            port: Port being accessed

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        # Same zone always allowed
        if src_zone == dst_zone:
            return True, "same_zone"

        # Check inter-zone policies
        for policy in self.inter_zone_policies:
            from_zone = policy.get("from_zone")
            to_zone = policy.get("to_zone")

            # Check if policy matches this zone pair
            if from_zone == src_zone and to_zone == dst_zone:
                # Found matching policy - check protocol
                allowed_protocols = policy.get("allowed_protocols", [])

                # Normalize protocol names for comparison (modbus_tcp -> modbus, opcua stays opcua)
                def normalize_protocol(p: str) -> str:
                    return p.replace("_tcp", "").replace("_rtu", "")

                normalized_protocol = normalize_protocol(protocol)
                normalized_allowed = [normalize_protocol(p) for p in allowed_protocols]

                if normalized_protocol not in normalized_allowed:
                    return False, f"protocol_{protocol}_not_allowed"

                # Check firewall rules for port
                firewall_rules = policy.get("firewall_rules", [])
                if firewall_rules:
                    port_allowed = False
                    for rule in firewall_rules:
                        rule_protocol = rule.get("allow", "")
                        rule_ports = rule.get("ports", [])

                        # Normalize rule protocol for comparison
                        if (
                            normalize_protocol(rule_protocol) == normalized_protocol
                            and port in rule_ports
                        ):
                            port_allowed = True
                            break

                    if not port_allowed:
                        return False, f"port_{port}_not_in_firewall_rules"

                # Check direction
                direction = policy.get("direction", "bidirectional")
                if direction == "outbound_only":
                    # Only allowed from source to destination, not reverse
                    return True, "outbound_policy_allows"
                else:
                    # Bidirectional allowed
                    return True, "bidirectional_policy_allows"

            # Check reverse direction if bidirectional
            elif from_zone == dst_zone and to_zone == src_zone:
                direction = policy.get("direction", "bidirectional")
                if direction == "bidirectional":
                    # Same checks as above
                    allowed_protocols = policy.get("allowed_protocols", [])

                    # Normalize protocol names for comparison
                    def normalize_protocol(p: str) -> str:
                        return p.replace("_tcp", "").replace("_rtu", "")

                    normalized_protocol = normalize_protocol(protocol)
                    normalized_allowed = [
                        normalize_protocol(p) for p in allowed_protocols
                    ]

                    if normalized_protocol not in normalized_allowed:
                        return False, f"protocol_{protocol}_not_allowed"

                    firewall_rules = policy.get("firewall_rules", [])
                    if firewall_rules:
                        port_allowed = False
                        for rule in firewall_rules:
                            rule_protocol = rule.get("allow", "")
                            rule_ports = rule.get("ports", [])

                            if (
                                normalize_protocol(rule_protocol) == normalized_protocol
                                and port in rule_ports
                            ):
                                port_allowed = True
                                break

                        if not port_allowed:
                            return False, f"port_{port}_not_in_firewall_rules"

                    return True, "bidirectional_policy_allows_reverse"

        # No policy found - default deny
        return False, "no_inter_zone_policy"

    # ----------------------------------------------------------------
    # Reachability checks
    # ----------------------------------------------------------------

    async def can_reach(
        self,
        src_network: str,
        dst_node: str,
        protocol: str,
        port: int,
    ) -> bool:
        """Check if a source network can reach a destination service.

        Enforces network segmentation and zone-based security policies.
        A connection is allowed if:
        1. The destination service exists
        2. The protocol matches
        3. Either:
           a) Source and destination are on the same network, OR
           b) Inter-zone security policy allows the connection

        Zone policy checks:
        - Protocol must be in allowed_protocols list
        - Port must be in firewall_rules (if specified)
        - Direction must permit the connection (bidirectional vs outbound_only)
        - Default deny if no policy exists

        Args:
            src_network: Source network name
            dst_node: Destination device name
            protocol: Protocol to use
            port: Destination port

        Returns:
            True if connection is allowed, False otherwise
        """
        async with self._lock:
            # Service must exist
            service_key = (dst_node, port)
            if service_key not in self.services:
                self.logger.debug(
                    f"Reachability denied: {src_network} -> {dst_node}:{port} "
                    f"(service not exposed)"
                )
                return False

            # Protocol must match
            if self.services[service_key] != protocol:
                self.logger.debug(
                    f"Reachability denied: {src_network} -> {dst_node}:{port} "
                    f"(protocol mismatch: requested {protocol}, "
                    f"service is {self.services[service_key]})"
                )
                return False

            # Get destination networks
            dst_networks = self.device_networks.get(dst_node, set())

            if not dst_networks:
                await self.logger.log_security(
                    message=f"Access denied: destination device {dst_node} not on any network",
                    severity=EventSeverity.WARNING,
                    source_ip="",
                    data={
                        "source_network": src_network,
                        "destination_node": dst_node,
                        "port": port,
                        "protocol": protocol,
                        "reason": "device_not_on_network",
                    },
                )
                return False

            # Check 1: Same network = always allowed (no zone check needed)
            if src_network in dst_networks:
                self.logger.debug(
                    f"Reachability allowed: {src_network} -> {dst_node}:{port} "
                    f"({protocol}) [same network]"
                )
                return True

            # Check 2: Different networks - check zone-based policies
            src_zone = self._get_zone_for_network(src_network)
            dst_zone = None

            # Find which destination network to use for zone checking
            # (device might be on multiple networks)
            for dst_net in dst_networks:
                zone = self._get_zone_for_network(dst_net)
                if zone:
                    dst_zone = zone
                    break

            # If either zone is unknown, deny (can't evaluate policy)
            if not src_zone or not dst_zone:
                await self.logger.log_security(
                    f"Zone policy check failed: {src_network} -> {dst_node}:{port}",
                    severity=EventSeverity.WARNING,
                    data={
                        "source_network": src_network,
                        "source_zone": src_zone or "unknown",
                        "destination_node": dst_node,
                        "destination_zone": dst_zone or "unknown",
                        "port": port,
                        "protocol": protocol,
                        "reason": "zone_not_defined",
                    },
                )
                return False

            # Check zone-based policy
            allowed, reason = self._check_zone_policy(
                src_zone, dst_zone, protocol, port
            )

            if allowed:
                self.logger.debug(
                    f"Reachability allowed: {src_network} ({src_zone}) -> "
                    f"{dst_node}:{port} ({dst_zone}) [{protocol}] - {reason}"
                )
            else:
                await self.logger.log_security(
                    f"Zone policy denied: {src_network} ({src_zone}) -> "
                    f"{dst_node}:{port} ({dst_zone})",
                    severity=EventSeverity.WARNING,
                    data={
                        "source_network": src_network,
                        "source_zone": src_zone,
                        "destination_node": dst_node,
                        "destination_zone": dst_zone,
                        "port": port,
                        "protocol": protocol,
                        "reason": reason,
                    },
                )

            return allowed

    async def can_reach_from_device(
        self,
        src_node: str,
        dst_node: str,
        protocol: str,
        port: int,
    ) -> bool:
        """Check if a source device can reach a destination service.

        Checks all networks the source device is on to see if any can reach
        the destination.

        Args:
            src_node: Source device name
            dst_node: Destination device name
            protocol: Protocol to use
            port: Destination port

        Returns:
            True if connection is allowed from any source network, False otherwise
        """
        # Get a copy of source networks while holding the lock
        async with self._lock:
            src_networks = self.device_networks.get(src_node, set()).copy()

        if not src_networks:
            self.logger.debug(
                f"Source device {src_node} not on any network, cannot reach {dst_node}"
            )
            return False

        # Check if any source network can reach destination
        for src_network in src_networks:
            if await self.can_reach(src_network, dst_node, protocol, port):
                return True

        return False

    # ----------------------------------------------------------------
    # Network queries
    # ----------------------------------------------------------------

    async def get_device_networks(self, device: str) -> set[str]:
        """Get all networks a device is connected to.

        Args:
            device: Device name

        Returns:
            Set of network names, empty if device not found
        """
        async with self._lock:
            return self.device_networks.get(device, set()).copy()

    async def get_network_devices(self, network: str) -> set[str]:
        """Get all devices on a specific network.

        Args:
            network: Network name

        Returns:
            Set of device names on the network
        """
        async with self._lock:
            devices = set()
            for device, networks in self.device_networks.items():
                if network in networks:
                    devices.add(device)
            return devices

    async def get_all_services(self) -> dict[tuple[str, int], str]:
        """Get all exposed services.

        Returns:
            Dictionary mapping (node, port) to protocol
        """
        async with self._lock:
            return self.services.copy()

    async def get_device_services(self, device: str) -> dict[int, str]:
        """Get all services exposed by a specific device.

        Args:
            device: Device name

        Returns:
            Dictionary mapping port to protocol
        """
        async with self._lock:
            return {
                port: protocol
                for (node, port), protocol in self.services.items()
                if node == device
            }

    # ----------------------------------------------------------------
    # Status
    # ----------------------------------------------------------------

    async def get_summary(self) -> dict[str, Any]:
        """Get network topology summary.

        Returns:
            Dictionary with network statistics
        """
        async with self._lock:
            return {
                "loaded": self._loaded,
                "networks": {
                    "count": len(self.networks),
                    "names": list(self.networks.keys()),
                },
                "devices": {
                    "count": len(self.device_networks),
                },
                "services": {
                    "count": len(self.services),
                    "by_protocol": self._count_services_by_protocol(),
                },
            }

    def _count_services_by_protocol(self) -> dict[str, int]:
        """Count services by protocol.

        Note: Should only be called while holding self._lock
        """
        return dict(Counter(self.services.values()))

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def reset(self) -> None:
        """Reset network simulator state.

        Clears all networks, devices, and services. Requires reload() to use again.
        """
        async with self._lock:
            self.networks.clear()
            self.device_networks.clear()
            self.services.clear()
            self._loaded = False
            self.logger.info("Network simulator reset")
