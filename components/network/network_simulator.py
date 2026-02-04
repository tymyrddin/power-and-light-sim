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

        Enforces network segmentation rules. A connection is allowed if:
        1. The destination service exists
        2. The protocol matches
        3. The source network overlaps with destination device's networks

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

            # Source network must overlap destination networks
            dst_networks = self.device_networks.get(dst_node, set())

            if not dst_networks:
                self.logger.warning(
                    f"Destination device {dst_node} not on any network, denying access"
                )
                return False

            allowed = src_network in dst_networks

            if allowed:
                self.logger.debug(
                    f"Reachability allowed: {src_network} -> {dst_node}:{port} ({protocol})"
                )
            else:
                await self.logger.log_security(
                    f"Network segmentation denied: {src_network} -> {dst_node}:{port}",
                    severity=EventSeverity.NOTICE,
                    data={
                        "source_network": src_network,
                        "destination_node": dst_node,
                        "destination_networks": list(dst_networks),
                        "port": port,
                        "protocol": protocol,
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
