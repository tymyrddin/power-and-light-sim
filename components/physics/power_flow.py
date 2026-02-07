# components/physics/power_flow.py
"""
Electrical power flow simulation.

Models:
- Node voltages and phase angles
- Line currents and power flows
- Reactive power and losses
- Line overload detection

Integrates with:
- SimulationTime for temporal accuracy
- DataStore to read bus injections from devices
- ConfigLoader for network topology
"""

from dataclasses import dataclass, field
from typing import Any

from components.security.logging_system import get_logger
from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime
from config.config_loader import ConfigLoader

# Configure logging
logger = get_logger(__name__)


@dataclass
class BusState:
    """State of a grid bus/node.

    Attributes:
        voltage_pu: Per-unit voltage magnitude
        angle_deg: Voltage phase angle in degrees
        load_mw: Active power load
        load_mvar: Reactive power load
        gen_mw: Active power generation
        gen_mvar: Reactive power generation
    """

    voltage_pu: float = 1.0
    angle_deg: float = 0.0
    load_mw: float = 0.0
    load_mvar: float = 0.0
    gen_mw: float = 0.0
    gen_mvar: float = 0.0


@dataclass
class LineState:
    """State of a transmission line.

    Attributes:
        from_bus: Source bus name
        to_bus: Destination bus name
        current_a: Line current in amperes
        mw_flow: Active power flow
        mvar_flow: Reactive power flow
        overload: True if line is overloaded
    """

    from_bus: str = ""
    to_bus: str = ""
    current_a: float = 0.0
    mw_flow: float = 0.0
    mvar_flow: float = 0.0
    overload: bool = False


@dataclass
class PowerFlowParameters:
    """Electrical network parameters.

    Attributes:
        base_mva: Base power in MVA for per-unit system
        line_max_mva: Default line rating in MVA
        buses: Dictionary of bus states
        lines: Dictionary of line states
    """

    base_mva: float = 100.0
    line_max_mva: float = 150.0
    buses: dict[str, BusState] = field(default_factory=dict)
    lines: dict[str, LineState] = field(default_factory=dict)


class PowerFlow:
    """
    Simulates steady-state electrical power flow.

    Uses simplified DC power flow approximation for computational efficiency.
    Suitable for real-time simulation and security analysis.

    Example:
        >>> power_flow = PowerFlow(data_store, config_loader)
        >>> await power_flow.initialise()
        >>> await power_flow.update_from_devices()
        >>> power_flow.update(delta_time)
    """

    def __init__(
        self,
        data_store: DataStore,
        config_loader: ConfigLoader | None = None,
        params: PowerFlowParameters | None = None,
    ):
        """Initialise power flow engine.

        Args:
            data_store: DataStore instance for device access
            config_loader: ConfigLoader for grid topology (optional)
            params: Power flow parameters (optional, overrides config)
        """
        self.data_store = data_store
        self.config_loader = config_loader or ConfigLoader()
        self.params = params or PowerFlowParameters()
        self.sim_time = SimulationTime()

        self._initialised = False

        logger.info("Power flow engine created")

    # ----------------------------------------------------------------
    # Initialisation
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialise power flow engine.

        Loads grid topology from configuration if not provided via params.
        """
        # Load grid configuration if buses/lines not already set
        if not self.params.buses or not self.params.lines:
            await self._load_grid_config()

        # Initialise all buses to nominal voltage
        for bus in self.params.buses.values():
            bus.voltage_pu = 1.0
            bus.angle_deg = 0.0

        self._initialised = True

        logger.info(
            f"Power flow initialised: {len(self.params.buses)} buses, "
            f"{len(self.params.lines)} lines"
        )

    async def _load_grid_config(self) -> None:
        """Load grid topology from configuration.

        Expected config/grid.yml format:
        grid:
          base_mva: 100.0
          buses:
            - name: bus_gen_1
              type: generator
            - name: bus_load_1
              type: load
          lines:
            - name: line_1_2
              from_bus: bus_gen_1
              to_bus: bus_load_1
              reactance_pu: 0.05
              rating_mva: 150.0
        """
        try:
            config = self.config_loader.load_all()
            grid_config = config.get("grid", {})

            # Load base parameters
            self.params.base_mva = grid_config.get("base_mva", 100.0)
            self.params.line_max_mva = grid_config.get("line_max_mva", 150.0)

            # Load buses
            buses_config = grid_config.get("buses", [])
            for bus_cfg in buses_config:
                bus_name = bus_cfg["name"]
                self.params.buses[bus_name] = BusState()
                logger.debug(f"Loaded bus: {bus_name}")

            # Load lines
            lines_config = grid_config.get("lines", [])
            for line_cfg in lines_config:
                line_name = line_cfg["name"]
                self.params.lines[line_name] = LineState(
                    from_bus=line_cfg["from_bus"], to_bus=line_cfg["to_bus"]
                )
                logger.debug(
                    f"Loaded line: {line_name} "
                    f"({line_cfg['from_bus']} -> {line_cfg['to_bus']})"
                )

            if not self.params.buses:
                logger.warning("No buses defined in grid configuration")
                self._create_default_grid()

        except Exception as e:
            logger.warning(f"Could not load grid configuration: {e}")
            logger.warning("Using default power flow configuration")
            # Create minimal default configuration
            self._create_default_grid()

    def _create_default_grid(self) -> None:
        """Create minimal default grid for testing."""
        # Create two-bus system
        self.params.buses = {
            "bus_gen": BusState(),
            "bus_load": BusState(),
        }

        self.params.lines = {
            "line_gen_load": LineState(from_bus="bus_gen", to_bus="bus_load")
        }

        logger.info("Created default 2-bus power system")

    # ----------------------------------------------------------------
    # Device aggregation
    # ----------------------------------------------------------------

    async def update_from_devices(self) -> None:
        """Update bus injections from device states.
        Reads generation from turbines and loads from substations.
        Should be called before update() each simulation cycle.
        """
        # Reset all bus injections
        for bus in self.params.buses.values():
            bus.gen_mw = 0.0
            bus.gen_mvar = 0.0
            bus.load_mw = 0.0
            bus.load_mvar = 0.0

        # Aggregate generation from turbines
        turbines = await self.data_store.get_devices_by_type("turbine_plc")

        for turbine in turbines:
            # Get power output from holding register 5
            power_mw = turbine.memory_map.get("holding_registers[5]", 0)

            # Map turbine to bus (simplified - assumes one turbine per gen bus)
            # In full implementation, would use device metadata or config
            bus_name = f"bus_{turbine.device_name}"
            if bus_name in self.params.buses:
                self.params.buses[bus_name].gen_mw += power_mw
                # Assume power factor of 0.9 for reactive power
                self.params.buses[bus_name].gen_mvar += (
                    power_mw * 0.484
                )  # tan(acos(0.9))

        # For now, use fixed load distribution
        # In full implementation, would read from substation controllers
        if "bus_load" in self.params.buses:
            self.params.buses["bus_load"].load_mw = 80.0
            self.params.buses["bus_load"].load_mvar = 40.0  # Inductive load

    # ----------------------------------------------------------------
    # Physics simulation
    # ----------------------------------------------------------------

    def update(self, dt: float) -> None:
        """Update power flow solution.
        Uses simplified DC power flow for computational efficiency.
        Real implementation would use Newton-Raphson or fast-decoupled methods.
        Args:
            dt: Time delta in simulation seconds
        Raises:
            RuntimeError: If not initialised
        """
        if not self._initialised:
            raise RuntimeError("Power flow not initialised. Call initialise() first.")

        if dt <= 0:
            logger.warning(f"Invalid time delta {dt}, skipping update")
            return

        # Simplified DC power flow
        self._update_dc_power_flow()

        # Check line loading
        self._check_line_overloads()

    def _update_dc_power_flow(self) -> None:
        """Update line flows using simplified DC approximation.
        DC power flow assumptions:
        - Voltage magnitudes are 1.0 pu
        - Only phase angles vary
        - Active power flow proportional to angle difference
        - Reactive power ignored
        """
        for line_id, line in self.params.lines.items():
            from_bus = self.params.buses.get(line.from_bus)
            to_bus = self.params.buses.get(line.to_bus)

            if not from_bus or not to_bus:
                logger.warning(
                    f"Line {line_id} references unknown bus: "
                    f"{line.from_bus} or {line.to_bus}"
                )
                continue

            # Simplified: power flow proportional to voltage/angle difference
            # Real implementation would use line reactance
            voltage_diff = from_bus.voltage_pu - to_bus.voltage_pu
            angle_diff = from_bus.angle_deg - to_bus.angle_deg

            # Power flow (simplified linear approximation)
            # P = (V1*V2/X) * sin(θ1 - θ2) ≈ (V1*V2/X) * (θ1 - θ2) for small angles
            # Using arbitrary gain factor for demonstration
            line.mw_flow = voltage_diff * 100.0 + angle_diff * 10.0

            # Reactive flow (placeholder)
            line.mvar_flow = voltage_diff * 50.0

            # Current (simplified: I = S/V)
            apparent_mva = (line.mw_flow**2 + line.mvar_flow**2) ** 0.5
            line.current_a = (apparent_mva / from_bus.voltage_pu) * 1000.0  # kA to A

    def _check_line_overloads(self) -> None:
        """Check for line thermal overloads."""
        for line_id, line in self.params.lines.items():
            # Calculate apparent power
            apparent_mva = (line.mw_flow**2 + line.mvar_flow**2) ** 0.5

            # Check against rating
            old_overload = line.overload
            line.overload = apparent_mva > self.params.line_max_mva

            # Log new overload events
            if line.overload and not old_overload:
                logger.error(
                    f"LINE OVERLOAD: {line_id} "
                    f"({line.from_bus} -> {line.to_bus}): "
                    f"{apparent_mva:.1f}MVA (limit: {self.params.line_max_mva}MVA)"
                )

    # ----------------------------------------------------------------
    # State access
    # ----------------------------------------------------------------

    def get_bus_states(self) -> dict[str, BusState]:
        """Get all bus states.
        Returns:
            Dictionary mapping bus names to states
        """
        return self.params.buses

    def get_line_states(self) -> dict[str, LineState]:
        """Get all line states.
        Returns:
            Dictionary mapping line names to states
        """
        return self.params.lines

    def get_telemetry(self) -> dict[str, Any]:
        """Get telemetry data in dictionary format.
        Returns:
            Dictionary with power flow telemetry
        """
        return {
            "buses": {
                bus_name: {
                    "voltage_pu": round(bus.voltage_pu, 3),
                    "angle_deg": round(bus.angle_deg, 1),
                    "load_mw": round(bus.load_mw, 1),
                    "gen_mw": round(bus.gen_mw, 1),
                    "net_injection_mw": round(bus.gen_mw - bus.load_mw, 1),
                }
                for bus_name, bus in self.params.buses.items()
            },
            "lines": {
                line_name: {
                    "from_bus": line.from_bus,
                    "to_bus": line.to_bus,
                    "mw_flow": round(line.mw_flow, 1),
                    "mvar_flow": round(line.mvar_flow, 1),
                    "current_a": round(line.current_a, 0),
                    "overload": line.overload,
                }
                for line_name, line in self.params.lines.items()
            },
        }
