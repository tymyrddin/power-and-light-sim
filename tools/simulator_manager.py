#!/usr/bin/env python3
# tools/simulator_manager.py
"""
ICS Simulator Manager - Main Orchestrator

Coordinates simulation components based on what's currently implemented:
- Device registration and state management (SystemState, DataStore)
- Network topology (NetworkSimulator)
- Physics engines (TurbinePhysics, GridPhysics, PowerFlow)
- Simulation time (SimulationTime)

Future: Will orchestrate protocol adapters when implemented.

Integrates:
- SimulationTime for temporal coordination
- SystemState/DataStore for device state
- ConfigLoader for configuration
- NetworkSimulator for topology
- Physics engines for realistic behaviour
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Any

from components.devices import DEVICE_REGISTRY
from components.network.network_simulator import NetworkSimulator
from components.physics.grid_physics import GridParameters, GridPhysics
from components.physics.hvac_physics import HVACParameters, HVACPhysics
from components.physics.power_flow import PowerFlow
from components.physics.reactor_physics import ReactorParameters, ReactorPhysics
from components.physics.turbine_physics import TurbineParameters, TurbinePhysics
from components.security.logging_system import configure_logging
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime, wait_simulation_time
from config.config_loader import ConfigLoader

# Configure logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(log_dir / "simulation.log")],
)
logger = logging.getLogger(__name__)


class SimulatorManager:
    """
    Main orchestrator for ICS simulation.

    Manages simulation lifecycle from initialisation through execution to shutdown.
    Currently orchestrates state management, network topology, and physics engines.

    Future expansion: Protocol listeners when adapters are implemented.

    Example:
        >>> manager = SimulatorManager()
        >>> await manager.initialise()
        >>> await manager.start()
        >>> # Simulation runs...
        >>> await manager.stop()
    """

    def __init__(self, config_dir: str = "config"):
        """Initialise simulator manager.

        Args:
            config_dir: Directory containing configuration files
        """
        self.config_dir = Path(config_dir)

        # Ensure required directories exist
        Path("logs").mkdir(exist_ok=True)
        self.config_dir.mkdir(exist_ok=True)

        # Core infrastructure
        self.config_loader = ConfigLoader(config_dir=str(self.config_dir))
        self.sim_time = SimulationTime()
        self.system_state = SystemState()
        self.data_store = DataStore(self.system_state)

        # Configure ICSLogger with DataStore integration
        configure_logging(log_dir=log_dir, data_store=self.data_store)

        # Suppress noisy asyncua address space messages
        logging.getLogger("asyncua.server.address_space").setLevel(logging.WARNING)

        # Network components
        self.network_sim = NetworkSimulator(self.config_loader, self.system_state)

        # Physics engines
        self.turbine_physics: dict[str, TurbinePhysics] = {}
        self.hvac_physics: dict[str, HVACPhysics] = {}
        self.reactor_physics: dict[str, ReactorPhysics] = {}
        self.grid_physics: GridPhysics | None = None
        self.power_flow: PowerFlow | None = None

        # Device instances (PLCs, RTUs, etc.)
        self.device_instances: dict[str, Any] = {}

        # Protocol servers
        self.protocol_servers: dict[str, Any] = {}

        # Simulation state
        self._running = False
        self._paused = False
        self._simulation_task: asyncio.Task | None = None
        self._initialised = False

        # Statistics
        self._update_count = 0
        self._start_time: float = 0.0

        # Signal handling
        self._shutdown_event = asyncio.Event()

        logger.info("SimulatorManager created")

    # ----------------------------------------------------------------
    # Initialisation
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialise all simulation components.

        Performs setup in dependency order:
        1. Load configuration
        2. Register devices in state
        3. Load network topology
        4. Create physics engines
        5. Initialise all components

        Raises:
            RuntimeError: If initialisation fails
        """
        if self._initialised:
            logger.warning("Simulator already initialised")
            return

        try:
            logger.info("=== Starting Simulator Initialisation ===")

            # 1. Load configuration
            logger.info("Loading configuration...")
            config = self.config_loader.load_all()

            # 2. Register devices
            logger.info("Registering devices...")
            await self._register_devices(config)

            # 3. Load network topology
            logger.info("Loading network topology...")
            await self.network_sim.load()

            # 4. Create physics engines
            logger.info("Creating physics engines...")
            await self._create_physics_engines(config)

            # 5. Create device instances (PLCs, RTUs, etc.)
            logger.info("Creating device instances...")
            await self._create_devices(config)

            # 6. Configure SCADA servers with poll targets and tags
            logger.info("Configuring SCADA servers...")
            await self._configure_scada_servers(config)

            # 7. Configure HMI workstations with SCADA connections and screens
            logger.info("Configuring HMI workstations...")
            await self._configure_hmi_workstations(config)

            # 8. Expose services in network (start protocol servers)
            logger.info("Starting protocol servers...")
            await self._expose_services(config)

            self._initialised = True

            logger.info("=== Initialisation Complete ===")
            await self._log_summary()

        except Exception as e:
            logger.error(f"Initialisation failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialise simulator: {e}") from e

    async def _register_devices(self, config: dict[str, Any]) -> None:
        """Register all devices from configuration.

        Args:
            config: Loaded configuration dictionary
        """
        devices = config.get("devices", [])

        if not devices:
            logger.warning("No devices found in configuration")
            return

        for device_cfg in devices:
            device_name = device_cfg.get("name")
            device_type = device_cfg.get("type")
            device_id = device_cfg.get("device_id", 1)
            protocols = list(device_cfg.get("protocols", {}).keys())
            metadata = {
                "description": device_cfg.get("description", ""),
                "location": device_cfg.get("location", ""),
            }

            if not device_name or not device_type:
                logger.warning(f"Skipping invalid device config: {device_cfg}")
                continue

            # Register device in state (even if no protocols for network topology)
            await self.data_store.register_device(
                device_name=device_name,
                device_type=device_type,
                device_id=device_id,
                protocols=protocols,  # Can be empty list
                metadata=metadata,
            )

            # Set device online (in real implementation, protocols would do this)
            await self.data_store.set_device_online(device_name, True)

            if protocols:
                logger.info(
                    f"Registered device: {device_name} (type={device_type}, protocols={protocols})"
                )
            else:
                logger.info(
                    f"Registered device: {device_name} (type={device_type}, no protocols)"
                )

    async def _create_physics_engines(self, config: dict[str, Any]) -> None:
        """Create physics engines for devices.

        Args:
            config: Loaded configuration dictionary
        """
        # Create turbine physics for each turbine PLC
        turbines = await self.data_store.get_devices_by_type("turbine_plc")

        for turbine_device in turbines:
            device_name = turbine_device.device_name

            # Get turbine-specific parameters from metadata if available
            # For now, use defaults
            params = TurbineParameters(
                rated_speed_rpm=3600, rated_power_mw=50.0, max_safe_speed_rpm=3960
            )

            # Create physics engine
            turbine = TurbinePhysics(device_name, self.data_store, params)
            await turbine.initialise()

            self.turbine_physics[device_name] = turbine

            logger.info(f"Created turbine physics: {device_name}")

        # Create HVAC physics for each HVAC PLC
        hvac_devices = await self.data_store.get_devices_by_type("hvac_plc")

        for hvac_device in hvac_devices:
            device_name = hvac_device.device_name

            # Get HVAC-specific parameters from metadata if available
            # For now, use defaults (Library environmental system)
            params = HVACParameters(
                zone_thermal_mass=500.0,
                zone_volume_m3=5000.0,
                rated_heating_kw=50.0,
                rated_cooling_kw=75.0,
            )

            # Create physics engine
            hvac = HVACPhysics(device_name, self.data_store, params)
            await hvac.initialise()

            self.hvac_physics[device_name] = hvac

            logger.info(f"Created HVAC physics: {device_name}")

        # Create reactor physics for each reactor PLC
        reactor_devices = await self.data_store.get_devices_by_type("reactor_plc")

        for reactor_device in reactor_devices:
            device_name = reactor_device.device_name

            # Get reactor-specific parameters from metadata if available
            # For now, use defaults (Alchemical reactor)
            params = ReactorParameters(
                rated_power_mw=25.0,
                rated_temperature_c=350.0,
                max_safe_temperature_c=400.0,
                critical_temperature_c=450.0,
            )

            # Create physics engine
            reactor = ReactorPhysics(device_name, self.data_store, params)
            await reactor.initialise()

            self.reactor_physics[device_name] = reactor

            logger.info(f"Created reactor physics: {device_name}")

        # Create grid physics if we have turbines
        if self.turbine_physics:
            grid_params = GridParameters(
                nominal_frequency_hz=50.0,
                inertia_constant=5000.0,
                min_frequency_hz=49.0,
                max_frequency_hz=51.0,
            )
            self.grid_physics = GridPhysics(self.data_store, grid_params)
            await self.grid_physics.initialise()
            logger.info("Created grid physics")

            # Create power flow
            self.power_flow = PowerFlow(self.data_store, self.config_loader)
            await self.power_flow.initialise()
            logger.info("Created power flow engine")

    async def _create_devices(self, config: dict[str, Any]) -> None:
        """Create device instances (PLCs, RTUs, etc.) using config-driven registry.

        Args:
            config: Loaded configuration dictionary
        """
        devices = config.get("devices", [])

        for device_cfg in devices:
            device_name = device_cfg.get("name")
            device_type = device_cfg.get("type")
            device_id = device_cfg.get("device_id", 1)
            scan_interval = device_cfg.get("scan_interval", 0.1)
            physics_engine_name = device_cfg.get("physics_engine")

            # Look up device class from registry
            device_class = DEVICE_REGISTRY.get(device_type)
            if not device_class:
                logger.warning(
                    f"Unknown device type '{device_type}' for {device_name}, skipping"
                )
                continue

            # Get physics engine if specified in config
            physics_engine = (
                self._get_physics_engine(physics_engine_name)
                if physics_engine_name
                else None
            )

            try:
                # Create device instance
                # TurbinePLC needs turbine_physics and grid_physics
                if device_type == "turbine_plc":
                    if not physics_engine:
                        logger.warning(f"No physics engine for {device_name}, skipping")
                        continue

                    device = device_class(
                        device_name=device_name,
                        device_id=device_id,
                        data_store=self.data_store,
                        turbine_physics=physics_engine,
                        grid_physics=self.grid_physics,
                        scan_interval=scan_interval,
                    )
                elif device_type == "hvac_plc":
                    if not physics_engine:
                        logger.warning(f"No physics engine for {device_name}, skipping")
                        continue

                    device = device_class(
                        device_name=device_name,
                        device_id=device_id,
                        data_store=self.data_store,
                        hvac_physics=physics_engine,
                        scan_interval=scan_interval,
                    )
                elif device_type == "reactor_plc":
                    if not physics_engine:
                        logger.warning(f"No physics engine for {device_name}, skipping")
                        continue

                    device = device_class(
                        device_name=device_name,
                        device_id=device_id,
                        data_store=self.data_store,
                        reactor_physics=physics_engine,
                        scan_interval=scan_interval,
                    )
                elif device_type == "historian":
                    # Historian with SCADA server connection
                    device = device_class(
                        device_name=device_name,
                        device_id=device_id,
                        data_store=self.data_store,
                        scada_server=device_cfg.get(
                            "scada_server", "scada_server_primary"
                        ),
                        retention_days=device_cfg.get("retention_days", 3650),
                        description=device_cfg.get("description", ""),
                        scan_interval=scan_interval,
                    )
                elif device_type == "turbine_safety_plc":
                    # Turbine safety PLC with physics engine
                    if not physics_engine:
                        logger.warning(f"No physics engine for {device_name}, skipping")
                        continue

                    device = device_class(
                        device_name=device_name,
                        device_id=device_id,
                        data_store=self.data_store,
                        turbine_physics=physics_engine,
                        description=device_cfg.get("description", ""),
                        scan_interval=scan_interval,
                    )
                elif device_type == "reactor_safety_plc":
                    # Reactor safety PLC with physics engine
                    if not physics_engine:
                        logger.warning(f"No physics engine for {device_name}, skipping")
                        continue

                    device = device_class(
                        device_name=device_name,
                        device_id=device_id,
                        data_store=self.data_store,
                        reactor_physics=physics_engine,
                        description=device_cfg.get("description", ""),
                        scan_interval=scan_interval,
                    )
                elif device_type in ["legacy_system", "legacy_workstation"]:
                    # Legacy workstation (Windows 98 data collector)
                    # Optionally connect to turbine physics if specified
                    device = device_class(
                        device_name=device_name,
                        device_id=device_id,
                        data_store=self.data_store,
                        turbine_physics=physics_engine,  # May be None
                        description=device_cfg.get("description", ""),
                        scan_interval=scan_interval,
                    )
                else:
                    # Generic device creation (adjust as needed for other device types)
                    device = device_class(
                        device_name=device_name,
                        device_id=device_id,
                        data_store=self.data_store,
                        description=device_cfg.get("description", ""),
                    )

                # Start device
                await device.start()

                # Store reference
                self.device_instances[device_name] = device
                logger.info(
                    f"Created and started device: {device_name} ({device_type})"
                )

            except Exception as e:
                logger.error(
                    f"Failed to create device {device_name} ({device_type}): {e}",
                    exc_info=True,
                )

    async def _configure_scada_servers(self, config: dict[str, Any]) -> None:
        """Configure SCADA servers with poll targets and tags from config.

        Args:
            config: Loaded configuration dictionary
        """
        scada_servers_config = config.get("scada_servers", {})

        if not scada_servers_config:
            logger.info("No SCADA server configuration found, skipping")
            return

        for scada_name, scada_config in scada_servers_config.items():
            # Get SCADA server device instance
            scada_device = self.device_instances.get(scada_name)
            if not scada_device:
                logger.warning(
                    f"SCADA server '{scada_name}' not found in device instances, skipping"
                )
                continue

            # Configure poll targets
            poll_targets = scada_config.get("poll_targets", [])
            for target_cfg in poll_targets:
                device_name = target_cfg.get("device")
                protocol = target_cfg.get("protocol")
                poll_rate = target_cfg.get("poll_rate", 1.0)
                enabled = target_cfg.get("enabled", True)

                if not device_name or not protocol:
                    logger.warning(f"Invalid poll target config: {target_cfg}")
                    continue

                scada_device.add_poll_target(
                    device_name=device_name,
                    protocol=protocol,
                    poll_rate_s=poll_rate,
                    enabled=enabled,
                )
                logger.debug(
                    f"Added poll target to {scada_name}: {device_name} ({protocol}) @ {poll_rate}s"
                )

            # Configure tags
            tags = scada_config.get("tags", [])
            for tag_cfg in tags:
                tag_name = tag_cfg.get("name")
                device_name = tag_cfg.get("device")
                address_type = tag_cfg.get("address_type")
                address = tag_cfg.get("address")

                if not all([tag_name, device_name, address_type, address is not None]):
                    logger.warning(f"Invalid tag config: {tag_cfg}")
                    continue

                scada_device.add_tag(
                    tag_name=tag_name,
                    device_name=device_name,
                    address_type=address_type,
                    address=address,
                    data_type=tag_cfg.get("data_type", "int"),
                    description=tag_cfg.get("description", ""),
                    unit=tag_cfg.get("unit", ""),
                    alarm_high=tag_cfg.get("alarm_high"),
                    alarm_low=tag_cfg.get("alarm_low"),
                )
                logger.debug(
                    f"Added tag to {scada_name}: {tag_name} -> {device_name}:{address_type}[{address}]"
                )

            logger.info(
                f"Configured SCADA server '{scada_name}': "
                f"{len(poll_targets)} poll targets, {len(tags)} tags"
            )

    async def _configure_hmi_workstations(self, config: dict[str, Any]) -> None:
        """Configure HMI workstations with SCADA connections and screens from config.

        Args:
            config: Loaded configuration dictionary
        """
        hmi_workstations_config = config.get("hmi_workstations", {})

        if not hmi_workstations_config:
            logger.info("No HMI workstation configuration found, skipping")
            return

        for hmi_name, hmi_config in hmi_workstations_config.items():
            # Get HMI workstation device instance
            hmi_device = self.device_instances.get(hmi_name)
            if not hmi_device:
                logger.warning(
                    f"HMI workstation '{hmi_name}' not found in device instances, skipping"
                )
                continue

            # Update SCADA server connection
            scada_server = hmi_config.get("scada_server")
            if scada_server:
                hmi_device.scada_server = scada_server

                # Update poll target with correct SCADA server
                # Remove old poll targets first
                hmi_device.poll_targets.clear()

                # Add correct SCADA server as poll target
                scan_interval = hmi_config.get("scan_interval", 0.5)
                hmi_device.add_poll_target(
                    device_name=scada_server,
                    protocol="internal",
                    poll_rate_s=scan_interval,
                )
                logger.debug(
                    f"HMI '{hmi_name}' connected to SCADA server '{scada_server}'"
                )

            # Update OS and software info if provided
            if "os_version" in hmi_config:
                hmi_device.os_version = hmi_config["os_version"]
            if "hmi_software" in hmi_config:
                hmi_device.hmi_software = hmi_config["hmi_software"]

            # Configure screens
            screens = hmi_config.get("screens", [])
            for screen_cfg in screens:
                screen_name = screen_cfg.get("name")
                tags = screen_cfg.get("tags", [])
                controls = screen_cfg.get("controls", [])

                if not screen_name:
                    logger.warning(
                        f"Invalid screen config for {hmi_name}: {screen_cfg}"
                    )
                    continue

                hmi_device.add_screen(
                    screen_name=screen_name,
                    tags=tags,
                    controls=controls,
                )
                logger.debug(
                    f"Added screen to {hmi_name}: {screen_name} "
                    f"({len(tags)} tags, {len(controls)} controls)"
                )

            # Set initial screen if available
            if screens:
                first_screen = screens[0].get("name")
                hmi_device.navigate_to_screen(first_screen)

            logger.info(
                f"Configured HMI workstation '{hmi_name}': "
                f"SCADA={scada_server}, {len(screens)} screens"
            )

    def _get_physics_engine(self, engine_name: str | None) -> Any:
        """Get physics engine by name from config.

        Args:
            engine_name: Name of physics engine (e.g., "turbine_physics")

        Returns:
            Physics engine instance or None
        """
        if not engine_name:
            return None

        # Map engine names to actual instances
        # For named engines, look up by device name in config
        if engine_name in self.turbine_physics:
            return self.turbine_physics[engine_name]
        if engine_name in self.hvac_physics:
            return self.hvac_physics[engine_name]
        if engine_name in self.reactor_physics:
            return self.reactor_physics[engine_name]

        # Fallback to type-based lookup
        engine_map = {
            "turbine_physics": lambda: (
                next(iter(self.turbine_physics.values()))
                if self.turbine_physics
                else None
            ),
            "hvac_physics": lambda: (
                next(iter(self.hvac_physics.values())) if self.hvac_physics else None
            ),
            "reactor_physics": lambda: (
                next(iter(self.reactor_physics.values()))
                if self.reactor_physics
                else None
            ),
            "grid_physics": lambda: self.grid_physics,
        }

        engine_getter = engine_map.get(engine_name)
        if callable(engine_getter):
            return engine_getter()
        return engine_getter

    async def _expose_services(self, config: dict[str, Any]) -> None:
        """Start protocol servers for devices based on config.

        Creates network-accessible attack surfaces for external tools.
        Protocol servers open real TCP/IP ports that can be targeted
        from another terminal using tools like mbtget, nmap, Metasploit.

        Servers are started in PARALLEL for fast initialization.

        Args:
            config: Loaded configuration dictionary
        """
        from components.network.servers import (
            DNP3TCPServer,
            IEC104TCPServer,
            ModbusTCPServer,
            OPCUAServer,
            S7TCPServer,
        )

        devices = config.get("devices", [])

        # Separate Modbus servers (sequential) from others (parallel)
        # Modbus uses pymodbus ModbusDeviceIdentification which has shared class attributes
        modbus_servers = []  # List of (device_name, proto_name, server_obj, port)
        other_server_tasks = []  # Tasks for parallel execution
        other_server_metadata = []  # Metadata for other servers

        for device_cfg in devices:
            device_name = device_cfg.get("name")
            device_id = device_cfg.get("device_id", 1)
            protocols_cfg = device_cfg.get("protocols", {})

            for proto_name, proto_cfg in protocols_cfg.items():
                # Skip non-network protocols (serial, etc.)
                if proto_name not in [
                    "modbus",
                    "s7",
                    "dnp3",
                    "opcua",
                    "iec61850",
                    "ethernet_ip",
                    "iec104",
                ]:
                    continue

                port = proto_cfg.get("port")

                if not port:
                    continue

                # Convert port to int if needed (skip if not numeric)
                try:
                    port = int(port) if isinstance(port, str) else port
                except ValueError:
                    logger.warning(
                        f"Invalid port '{port}' for {device_name}:{proto_name}, skipping"
                    )
                    continue

                # Expose service in network simulator (topology)
                await self.network_sim.expose_service(device_name, proto_name, port)

                # Create protocol server (will be started in parallel later)
                if proto_name == "modbus":
                    try:
                        host = proto_cfg.get("host", "0.0.0.0")
                        unit_id = proto_cfg.get("unit_id", 1)

                        # Get device identity from config for realistic fingerprinting
                        device_type = device_cfg.get("type", "")
                        device_identities = config.get("device_identities", {})
                        device_identity = device_identities.get(
                            device_type, device_identities.get("default", {})
                        )

                        # Create Modbus TCP server with pymodbus simulator
                        server = ModbusTCPServer(
                            host=host,
                            port=port,
                            unit_id=unit_id,
                            num_coils=64,
                            num_discrete_inputs=64,
                            num_holding_registers=256,
                            num_input_registers=256,
                            device_identity=device_identity,
                        )

                        # Collect Modbus servers for sequential start (not parallel)
                        modbus_servers.append((device_name, proto_name, server, port))

                    except Exception as e:
                        logger.error(
                            f"Failed to create {proto_name} server for {device_name}: {e}"
                        )

                elif proto_name == "s7":
                    try:
                        host = proto_cfg.get("host", "0.0.0.0")
                        rack = proto_cfg.get("rack", 0)
                        slot = proto_cfg.get("slot", 2)

                        # Create S7 TCP server with snap7
                        server = S7TCPServer(
                            host=host,
                            port=port,
                            rack=rack,
                            slot=slot,
                            db1_size=256,  # Input registers
                            db2_size=256,  # Holding registers
                            db3_size=64,  # Discrete inputs
                            db4_size=64,  # Coils
                        )

                        # Collect for parallel start
                        other_server_tasks.append(server.start())
                        other_server_metadata.append(
                            (device_name, proto_name, server, port)
                        )

                    except Exception as e:
                        logger.error(
                            f"Failed to create {proto_name} server for {device_name}: {e}"
                        )

                elif proto_name == "dnp3":
                    try:
                        host = proto_cfg.get("host", "0.0.0.0")
                        master_address = proto_cfg.get("master_address", 1)
                        outstation_address = proto_cfg.get(
                            "outstation_address", device_id
                        )

                        # Create DNP3 TCP server (outstation)
                        server = DNP3TCPServer(
                            host=host,
                            port=port,
                            master_address=master_address,
                            outstation_address=outstation_address,
                            num_binary_inputs=64,
                            num_analog_inputs=32,
                            num_counters=16,
                        )

                        # Collect for parallel start
                        other_server_tasks.append(server.start())
                        other_server_metadata.append(
                            (device_name, proto_name, server, port)
                        )

                    except Exception as e:
                        logger.error(
                            f"Failed to create {proto_name} server for {device_name}: {e}"
                        )

                elif proto_name == "iec104":
                    try:
                        host = proto_cfg.get("host", "0.0.0.0")
                        common_address = proto_cfg.get("common_address", 1)

                        # Create IEC 104 TCP server
                        server = IEC104TCPServer(
                            host=host,
                            port=port,
                            common_address=common_address,
                        )

                        # Collect for parallel start
                        other_server_tasks.append(server.start())
                        other_server_metadata.append(
                            (device_name, proto_name, server, port)
                        )

                    except Exception as e:
                        logger.error(
                            f"Failed to create {proto_name} server for {device_name}: {e}"
                        )

                elif proto_name == "opcua":
                    try:
                        endpoint_url = proto_cfg.get(
                            "endpoint",
                            f"opc.tcp://{proto_cfg.get('host', '0.0.0.0')}:{port}/",
                        )

                        # Security configuration (optional)
                        security_policy = proto_cfg.get("security_policy", "None")
                        certificate_path = proto_cfg.get("certificate")
                        private_key_path = proto_cfg.get("private_key")
                        allow_anonymous = proto_cfg.get("allow_anonymous", True)

                        # Apply global OPC UA security config
                        opcua_sec = self.config.get("opcua_security", {})

                        # Authentication enforcement (Challenge 1)
                        opcua_auth_manager = None
                        if opcua_sec.get("require_authentication", False):
                            from components.security.authentication import (
                                AuthenticationManager,
                            )

                            opcua_auth_manager = AuthenticationManager()
                            allow_anonymous = False
                            logger.info(
                                f"OPC UA authentication enforcement: {device_name} "
                                f"(users: {len(opcua_auth_manager.users)})"
                            )

                        # Encryption enforcement (Challenge 7)
                        if opcua_sec.get("enforcement_enabled", False):
                            # Check for per-server overrides first
                            overrides = opcua_sec.get("server_overrides", {})
                            server_override = overrides.get(device_name, {})

                            security_policy = server_override.get(
                                "security_policy",
                                opcua_sec.get(
                                    "security_policy", "Aes256_Sha256_RsaPss"
                                ),
                            )
                            allow_anonymous = server_override.get(
                                "allow_anonymous",
                                opcua_sec.get("allow_anonymous", False),
                            )

                            # Use cert paths from device config or generate from cert_dir
                            cert_dir = opcua_sec.get("cert_dir", "certs")
                            if not certificate_path:
                                certificate_path = f"{cert_dir}/{device_name}.crt"
                            if not private_key_path:
                                private_key_path = f"{cert_dir}/{device_name}.key"

                            logger.info(
                                f"OPC UA security enforcement: {device_name} "
                                f"policy={security_policy}, anonymous={allow_anonymous}"
                            )

                        # Create OPC UA server with optional security
                        server = OPCUAServer(
                            endpoint=endpoint_url,
                            security_policy=security_policy,
                            certificate_path=certificate_path,
                            private_key_path=private_key_path,
                            allow_anonymous=allow_anonymous,
                            auth_manager=opcua_auth_manager,
                        )

                        # Collect for parallel start
                        other_server_tasks.append(server.start())
                        other_server_metadata.append(
                            (device_name, proto_name, server, port)
                        )

                    except Exception as e:
                        logger.error(
                            f"Failed to create {proto_name} server for {device_name}: {e}"
                        )

                else:
                    # Protocol not yet implemented
                    logger.info(
                        f"Exposed {proto_name} service (server not implemented): {device_name}:{port}"
                    )

        # Start Modbus servers SEQUENTIALLY (pymodbus class attribute workaround)
        if modbus_servers:
            logger.info(
                f"Starting {len(modbus_servers)} Modbus servers sequentially..."
            )
            for device_name, proto_name, server, port in modbus_servers:
                try:
                    result = await server.start()
                    if result:
                        server_key = f"{device_name}:{proto_name}"
                        self.protocol_servers[server_key] = server
                        logger.info(
                            f"Started {proto_name} server: {device_name}:{port}"
                        )
                    else:
                        logger.warning(
                            f"{proto_name} server for {device_name}:{port} failed to start"
                        )
                except Exception as e:
                    logger.error(
                        f"Failed to start {proto_name} server for {device_name}:{port}: {e}"
                    )

        # Start other servers in PARALLEL for fast initialization
        if other_server_tasks:
            logger.info(
                f"Starting {len(other_server_tasks)} other protocol servers in parallel..."
            )

            # Run all server.start() calls concurrently
            results = await asyncio.gather(*other_server_tasks, return_exceptions=True)

            # Process results and store successful servers
            for i, (device_name, proto_name, server, port) in enumerate(
                other_server_metadata
            ):
                result = results[i]

                if isinstance(result, Exception):
                    logger.error(
                        f"Failed to start {proto_name} server for {device_name}:{port}: {result}"
                    )
                elif result:  # Server started successfully
                    server_key = f"{device_name}:{proto_name}"
                    self.protocol_servers[server_key] = server
                    logger.info(f"Started {proto_name} server: {device_name}:{port}")
                else:
                    logger.warning(
                        f"{proto_name} server for {device_name}:{port} failed to start - "
                        "library may not be installed or port unavailable"
                    )

    async def _log_summary(self) -> None:
        """Log initialisation summary."""
        summary = await self.data_store.get_simulation_state()
        net_summary = await self.network_sim.get_summary()

        logger.info("--- Simulation Summary ---")
        logger.info(f"Devices: {summary['devices']['total']}")
        logger.info(f"Device instances: {len(self.device_instances)}")
        logger.info(f"Device types: {summary['device_types']}")
        logger.info(f"Networks: {net_summary['networks']['count']}")
        logger.info(f"Services exposed: {net_summary['services']['count']}")
        logger.info(f"Protocol servers: {len(self.protocol_servers)}")
        logger.info(f"Turbine physics engines: {len(self.turbine_physics)}")
        logger.info(f"HVAC physics engines: {len(self.hvac_physics)}")
        logger.info(f"Reactor physics engines: {len(self.reactor_physics)}")
        logger.info(f"Grid physics: {'enabled' if self.grid_physics else 'disabled'}")
        logger.info(f"Power flow: {'enabled' if self.power_flow else 'disabled'}")
        logger.info("-------------------------")

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def start(self) -> None:
        """Start the simulation.

        Starts time system and begins main simulation loop.

        Raises:
            RuntimeError: If not initialised or already running
        """
        if not self._initialised:
            raise RuntimeError("Cannot start: simulator not initialised")

        if self._running:
            logger.warning("Simulator already running")
            return

        logger.info("=== Starting Simulation ===")

        # Start simulation time
        await self.sim_time.start()

        # Mark system as running
        await self.data_store.mark_simulation_running(True)

        self._running = True
        self._start_time = self.sim_time.now()

        # Start main simulation loop
        self._simulation_task = asyncio.create_task(self._simulation_loop())

        logger.info("Simulation started - physics engines and protocol servers active")
        if self.protocol_servers:
            logger.info(f"Protocol servers running: {len(self.protocol_servers)}")
            for server_key in self.protocol_servers.keys():
                logger.info(f"  - {server_key}")
        else:
            logger.info("No protocol servers configured")

    async def stop(self) -> None:
        """Stop the simulation gracefully.

        Stops all components and cleans up resources.
        """
        if not self._running:
            logger.warning("Simulator not running")
            return

        logger.info("=== Stopping Simulation ===")

        self._running = False

        # Stop simulation loop
        if self._simulation_task:
            self._simulation_task.cancel()
            try:
                await self._simulation_task
            except asyncio.CancelledError:
                pass

        # Stop all protocol servers
        for server_key, server in self.protocol_servers.items():
            try:
                await server.stop()
                logger.info(f"Stopped protocol server: {server_key}")
            except Exception as e:
                logger.error(f"Error stopping {server_key}: {e}")

        # Stop all device instances
        for device_name, device in self.device_instances.items():
            try:
                if hasattr(device, "stop"):
                    await device.stop()
                    logger.info(f"Stopped device: {device_name}")
            except Exception as e:
                logger.error(f"Error stopping device {device_name}: {e}")

        # Stop simulation time
        await self.sim_time.stop()

        # Mark system as stopped
        await self.data_store.mark_simulation_running(False)

        # Log final statistics
        await self._log_final_statistics()

        logger.info("Simulation stopped")

    async def pause(self) -> None:
        """Pause the simulation.

        Freezes simulation time.
        """
        if not self._running:
            raise RuntimeError("Cannot pause: simulation not running")

        if self._paused:
            logger.warning("Simulation already paused")
            return

        await self.sim_time.pause()
        self._paused = True

        logger.info("Simulation paused")

    async def resume(self) -> None:
        """Resume paused simulation."""
        if not self._paused:
            logger.warning("Simulation not paused")
            return

        await self.sim_time.resume()
        self._paused = False

        logger.info("Simulation resumed")

    async def reset(self) -> None:
        """Reset simulation to initial state.

        Stops simulation if running and resets all state.
        """
        logger.info("=== Resetting Simulation ===")

        if self._running:
            await self.stop()

        # Reset simulation time
        await self.sim_time.reset()

        # Reset system state
        await self.system_state.reset()

        # Reset physics engines
        for turbine in self.turbine_physics.values():
            await turbine.initialise()

        for hvac in self.hvac_physics.values():
            await hvac.initialise()

        for reactor in self.reactor_physics.values():
            await reactor.initialise()

        if self.grid_physics:
            await self.grid_physics.initialise()

        if self.power_flow:
            await self.power_flow.initialise()

        self._update_count = 0
        self._initialised = False

        logger.info("Simulation reset complete")

    # ----------------------------------------------------------------
    # Main simulation loop
    # ----------------------------------------------------------------

    async def _simulation_loop(self) -> None:
        """Main simulation update loop.

        Runs at configured update interval, coordinating physics updates.
        """
        config = self.config_loader.load_all()
        runtime_cfg = config.get("simulation", {}).get("runtime", {})
        update_interval = runtime_cfg.get("update_interval", 0.1)

        logger.info(f"Simulation loop started (interval={update_interval}s)")

        last_time = self.sim_time.now()

        try:
            while self._running:
                # Get simulation time delta
                current_time = self.sim_time.now()
                dt = current_time - last_time
                last_time = current_time

                # Skip update if paused or dt is zero
                if self._paused or dt <= 0:
                    await wait_simulation_time(update_interval)
                    continue

                # Perform simulation update
                await self._update_simulation(dt)

                # Increment cycle counter
                self._update_count += 1

                # Periodic status logging
                if self._update_count % 100 == 0:
                    await self._log_status()

                # Wait for next cycle
                await wait_simulation_time(update_interval)

        except asyncio.CancelledError:
            logger.info("Simulation loop cancelled")
        except Exception as e:
            logger.error(f"Error in simulation loop: {e}", exc_info=True)
            self._running = False

    async def _update_simulation(self, dt: float) -> None:
        """Perform one simulation update cycle.

        Updates physics engines and writes telemetry to device state.

        Args:
            dt: Time delta in simulation seconds
        """
        # 1. Update device aggregations for grid/power flow
        if self.grid_physics:
            await self.grid_physics.update_from_devices()

        if self.power_flow:
            await self.power_flow.update_from_devices()

        # 2. Update all physics engines (synchronous, deterministic order)
        for turbine in self.turbine_physics.values():
            turbine.update(dt)

        for hvac in self.hvac_physics.values():
            hvac.update(dt)

        for reactor in self.reactor_physics.values():
            reactor.update(dt)

        if self.grid_physics:
            self.grid_physics.update(dt)

        if self.power_flow:
            self.power_flow.update(dt)

        # 3. Write telemetry back to device memory maps
        for turbine in self.turbine_physics.values():
            await turbine.write_telemetry()

        for hvac in self.hvac_physics.values():
            await hvac.write_telemetry()

        for reactor in self.reactor_physics.values():
            await reactor.write_telemetry()

        # 4. Sync protocol servers with device registers
        await self._sync_protocol_servers()

        # 5. Increment system update counter
        await self.data_store.increment_update_cycle()

    async def _sync_protocol_servers(self) -> None:
        """Sync device registers with protocol servers (Option C: manual sync).

        Device → Server: Push telemetry (input_registers, discrete_inputs)
        Server → Device: Pull commands (coils, holding_registers)

        Handles Modbus, S7, and DNP3 protocol servers.
        """
        for device_name, device in self.device_instances.items():
            # Check for Modbus server
            modbus_key = f"{device_name}:modbus"
            modbus_server = self.protocol_servers.get(modbus_key)

            # Check for S7 server
            s7_key = f"{device_name}:s7"
            s7_server = self.protocol_servers.get(s7_key)

            # Check for DNP3 server
            dnp3_key = f"{device_name}:dnp3"
            dnp3_server = self.protocol_servers.get(dnp3_key)

            # Sync with Modbus/S7 servers (same data model)
            for server in [modbus_server, s7_server]:
                if not server:
                    continue

                try:
                    # Extract registers from device memory_map
                    memory_map = device.memory_map

                    # Device → Server (telemetry)
                    input_registers = {}
                    discrete_inputs = {}
                    for key, value in memory_map.items():
                        if key.startswith("input_registers["):
                            # Extract address from "input_registers[100]"
                            addr = int(key.split("[")[1].split("]")[0])
                            input_registers[addr] = value
                        elif key.startswith("discrete_inputs["):
                            addr = int(key.split("[")[1].split("]")[0])
                            discrete_inputs[addr] = value

                    if input_registers:
                        await server.sync_from_device(
                            input_registers, "input_registers"
                        )
                    if discrete_inputs:
                        await server.sync_from_device(
                            discrete_inputs, "discrete_inputs"
                        )

                    # Server → Device (commands)
                    # Find coils range
                    coil_addrs = [
                        int(k.split("[")[1].split("]")[0])
                        for k in memory_map.keys()
                        if k.startswith("coils[")
                    ]
                    if coil_addrs:
                        min_addr = min(coil_addrs)
                        max_addr = max(coil_addrs)
                        coils_from_server = await server.sync_to_device(
                            min_addr, max_addr - min_addr + 1, "coils"
                        )
                        for addr, value in coils_from_server.items():
                            device.memory_map[f"coils[{addr}]"] = value

                    # Find holding registers range
                    hr_addrs = [
                        int(k.split("[")[1].split("]")[0])
                        for k in memory_map.keys()
                        if k.startswith("holding_registers[")
                    ]
                    if hr_addrs:
                        min_addr = min(hr_addrs)
                        max_addr = max(hr_addrs)
                        regs_from_server = await server.sync_to_device(
                            min_addr, max_addr - min_addr + 1, "holding_registers"
                        )
                        for addr, value in regs_from_server.items():
                            key = f"holding_registers[{addr}]"
                            if key in device.memory_map:
                                device.memory_map[key] = value

                except Exception as e:
                    logger.error(
                        f"Failed to sync {device_name} with protocol server: {e}"
                    )

            # Sync with DNP3 server (different data model)
            if dnp3_server:
                try:
                    # Extract data from device memory_map
                    memory_map = device.memory_map

                    # Device → Server (telemetry)
                    # Map Modbus-style registers to DNP3 data model
                    analog_inputs = {}  # DNP3 analog inputs
                    binary_inputs = {}  # DNP3 binary inputs

                    for key, value in memory_map.items():
                        if key.startswith("input_registers["):
                            # Map input_registers → analog_inputs
                            addr = int(key.split("[")[1].split("]")[0])
                            analog_inputs[addr] = value
                        elif key.startswith("discrete_inputs["):
                            # Map discrete_inputs → binary_inputs
                            addr = int(key.split("[")[1].split("]")[0])
                            binary_inputs[addr] = value

                    # Sync to DNP3 server
                    if analog_inputs:
                        await dnp3_server.sync_from_device(
                            analog_inputs, "analog_inputs"
                        )
                    if binary_inputs:
                        await dnp3_server.sync_from_device(
                            binary_inputs, "binary_inputs"
                        )

                    # Server → Device (commands)
                    # DNP3 commands (Binary/Analog Outputs) would be synced here
                    # Currently not fully implemented in DNP3 adapter
                    # TODO: Add DNP3 command handling when adapter supports it

                except Exception as e:
                    logger.error(f"Failed to sync {device_name} with DNP3 server: {e}")

    # ----------------------------------------------------------------
    # Status and monitoring
    # ----------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        """Get comprehensive simulation status.

        Returns:
            Dictionary with simulation status and statistics
        """
        sim_time_status = await self.sim_time.get_status()
        system_summary = await self.data_store.get_simulation_state()
        net_summary = await self.network_sim.get_summary()

        # Get physics status
        physics_status = {}
        if self.grid_physics:
            physics_status["grid"] = self.grid_physics.get_telemetry()

        turbine_status = {}
        for name, turbine in self.turbine_physics.items():
            turbine_status[name] = turbine.get_telemetry()

        hvac_status = {}
        for name, hvac in self.hvac_physics.items():
            hvac_status[name] = hvac.get_telemetry()

        reactor_status = {}
        for name, reactor in self.reactor_physics.items():
            reactor_status[name] = reactor.get_telemetry()

        return {
            "running": self._running,
            "paused": self._paused,
            "initialised": self._initialised,
            "update_count": self._update_count,
            "simulation_time": sim_time_status,
            "system_state": system_summary,
            "network": net_summary,
            "physics": {
                "grid": physics_status.get("grid"),
                "turbines": turbine_status,
                "hvac": hvac_status,
                "reactors": reactor_status,
                "power_flow": self.power_flow is not None,
            },
        }

    async def _log_status(self) -> None:
        """Log periodic status update."""
        status = await self.get_status()

        # Log basic status
        logger.info(
            f"Cycle {self._update_count}: "
            f"SimTime {status['simulation_time']['simulation_time']:.1f}s, "
            f"Devices {status['system_state']['devices']['online']}/"
            f"{status['system_state']['devices']['total']} online"
        )

        # Log grid status if available
        if status["physics"]["grid"]:
            grid = status["physics"]["grid"]
            logger.debug(
                f"Grid: {grid['frequency_hz']:.3f}Hz, "
                f"Gen={grid['total_generation_mw']:.1f}MW, "
                f"Load={grid['total_load_mw']:.1f}MW"
            )

    async def _log_final_statistics(self) -> None:
        """Log final simulation statistics."""
        elapsed_sim = self.sim_time.now() - self._start_time
        elapsed_wall = self.sim_time.wall_elapsed()

        if elapsed_wall > 0:
            ratio = elapsed_sim / elapsed_wall
        else:
            ratio = 0

        logger.info("--- Final Statistics ---")
        logger.info(f"Total update cycles: {self._update_count}")
        logger.info(f"Simulation time elapsed: {elapsed_sim:.1f}s")
        logger.info(f"Wall-clock time elapsed: {elapsed_wall:.1f}s")
        logger.info(f"Time ratio: {ratio:.2f}x")
        logger.info("------------------------")

    # ----------------------------------------------------------------
    # Signal handling
    # ----------------------------------------------------------------

    def setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}")
            self._shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("Signal handlers configured")

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()

    # ----------------------------------------------------------------
    # Main run method
    # ----------------------------------------------------------------

    async def run(self) -> None:
        """Run complete simulation lifecycle.

        Initialises, starts, and runs until interrupted.
        """
        try:
            # Set up signal handlers
            self.setup_signal_handlers()

            # Initialise
            await self.initialise()

            # Start simulation
            await self.start()

            # Wait for shutdown signal
            logger.info("Simulation running. Press Ctrl+C to stop.")
            logger.info("")
            logger.info("Current capabilities:")
            logger.info("  ✓ Physics simulation (turbines, grid, power flow)")
            logger.info("  ✓ Device state management")
            logger.info("  ✓ Network topology simulation")
            logger.info("  ✓ Protocol servers (Modbus TCP)")
            logger.info("  ✓ Device ↔ Server synchronization")
            logger.info("")
            await self.wait_for_shutdown()

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            # Clean shutdown
            if self._running:
                await self.stop()


# ----------------------------------------------------------------
# Command-line interface
# ----------------------------------------------------------------


async def main():
    """Main entry point."""
    logger.info("=== UU Power & Light ICS Simulator ===")
    logger.info("")

    # Create and run simulator
    manager = SimulatorManager()
    await manager.run()


if __name__ == "__main__":
    asyncio.run(main())
