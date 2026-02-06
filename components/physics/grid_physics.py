# components/physics/grid_physics.py
"""
Grid dynamics simulation.

Models:
- System frequency based on load-generation balance
- Voltage stability
- Automatic frequency control
- Grid protection trips (over/under frequency and voltage)

Integrates with:
- SimulationTime for temporal accuracy
- DataStore to aggregate generation and load from devices
- ConfigLoader for grid parameters
"""

from dataclasses import dataclass
from typing import Any

from components.physics.base_physics_engine import BasePhysicsEngine
from components.state.data_store import DataStore


@dataclass
class GridState:
    """Overall grid state.

    Attributes:
        frequency_hz: System frequency in Hertz
        voltage_pu: System voltage in per-unit (1.0 = nominal)
        total_load_mw: Total system load in megawatts
        total_gen_mw: Total generation in megawatts
        under_frequency_trip: Under-frequency protection triggered
        over_frequency_trip: Over-frequency protection triggered
        undervoltage_trip: Undervoltage protection triggered
        overvoltage_trip: Overvoltage protection triggered
    """

    frequency_hz: float = 50.0
    voltage_pu: float = 1.0
    total_load_mw: float = 0.0
    total_gen_mw: float = 0.0
    under_frequency_trip: bool = False
    over_frequency_trip: bool = False
    undervoltage_trip: bool = False
    overvoltage_trip: bool = False


@dataclass
class GridParameters:
    """Grid-wide control parameters.

    Attributes:
        nominal_frequency_hz: Rated frequency (50 or 60 Hz)
        frequency_deadband_hz: Acceptable frequency deviation
        max_frequency_hz: Over-frequency trip point
        min_frequency_hz: Under-frequency trip point
        voltage_deadband_pu: Acceptable voltage deviation
        max_voltage_pu: Overvoltage trip point
        min_voltage_pu: Undervoltage trip point
        inertia_constant: System inertia in MW·s
        damping: Load damping in MW/Hz
    """

    nominal_frequency_hz: float = 50.0
    frequency_deadband_hz: float = 0.2
    max_frequency_hz: float = 51.0
    min_frequency_hz: float = 49.0
    voltage_deadband_pu: float = 0.05
    max_voltage_pu: float = 1.1
    min_voltage_pu: float = 0.9
    inertia_constant: float = 5000.0  # MW·s
    damping: float = 1.0  # MW/Hz


class GridPhysics(BasePhysicsEngine):
    """
    Simulates overall grid dynamics.

    Models system frequency response to load-generation imbalance
    using simplified swing equation. Aggregates power from all
    generators and loads in the simulation.

    Example:
        >>> grid = GridPhysics(data_store)
        >>> await grid.initialise()
        >>> await grid.update_from_devices()  # Aggregate gen/load
        >>> grid.update(delta_time)  # Update frequency
    """

    def __init__(
        self,
        data_store: DataStore,
        params: GridParameters | None = None,
    ):
        """Initialise grid physics engine.

        Args:
            data_store: DataStore instance for device access
            params: Grid parameters (uses defaults if None)
        """
        super().__init__(data_store, params or GridParameters())
        self.state = GridState(frequency_hz=self.params.nominal_frequency_hz)

        self.logger.info(
            f"Grid physics created: {self.params.nominal_frequency_hz}Hz nominal, "
            f"inertia={self.params.inertia_constant}MW·s"
        )

    # ----------------------------------------------------------------
    # Initialisation
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialise grid physics.

        Sets initial state to nominal conditions.
        """
        self.state.frequency_hz = self.params.nominal_frequency_hz
        self.state.voltage_pu = 1.0

        # Initial load/gen aggregation
        await self.update_from_devices()

        self._last_update_time = self.sim_time.now()
        self._initialised = True

        self.logger.info(
            f"Grid physics initialised: {self.state.total_gen_mw:.1f}MW gen, "
            f"{self.state.total_load_mw:.1f}MW load"
        )

    # ----------------------------------------------------------------
    # Device aggregation
    # ----------------------------------------------------------------

    async def update_from_devices(self) -> None:
        """Aggregate total generation and load from all devices.

        Reads power output from turbines and power consumption from loads.
        Should be called before update() each simulation cycle.
        """
        # Aggregate generation from all turbine PLCs
        turbines = await self.data_store.get_devices_by_type("turbine_plc")

        total_gen = 0.0
        for turbine in turbines:
            # Read power output from holding register 5
            power_mw = turbine.memory_map.get("holding_registers[5]", 0)
            total_gen += power_mw

        self.state.total_gen_mw = total_gen

        # Aggregate load from all load devices
        # For now, use a fixed load - in full implementation,
        # would read from load controllers or calculate from substations
        self.state.total_load_mw = 80.0  # Fixed 80MW load for now

        self.logger.debug(
            f"Grid: Gen={self.state.total_gen_mw:.1f}MW, "
            f"Load={self.state.total_load_mw:.1f}MW, "
            f"Imbalance={self.state.total_gen_mw - self.state.total_load_mw:.1f}MW"
        )

    # ----------------------------------------------------------------
    # Physics simulation
    # ----------------------------------------------------------------

    def update(self, dt: float) -> None:
        """Update grid frequency and voltage based on power balance.

        Uses simplified swing equation:
        df/dt = (P_gen - P_load - D*(f - f_nom)) / H

        where:
        - df/dt = rate of frequency change
        - P_gen = total generation
        - P_load = total load
        - D = damping coefficient
        - f = current frequency
        - f_nom = nominal frequency
        - H = inertia constant

        Args:
            dt: Time delta in simulation seconds

        Raises:
            RuntimeError: If not initialised
        """
        if not self._validate_update(dt):
            return

        # Power imbalance (MW)
        imbalance_mw = self.state.total_gen_mw - self.state.total_load_mw

        # Damping effect (load increases with frequency)
        frequency_deviation = self.state.frequency_hz - self.params.nominal_frequency_hz
        damping_mw = self.params.damping * frequency_deviation

        # Net power affecting frequency
        net_power_mw = imbalance_mw - damping_mw

        # Swing equation: df/dt = P_net / H
        df_dt = net_power_mw / self.params.inertia_constant

        # Update frequency
        self.state.frequency_hz += df_dt * dt

        # Voltage deviation proportional to power imbalance (very simplified)
        # In reality, voltage depends on reactive power, not active power
        # This is placeholder for more sophisticated model
        voltage_deviation = imbalance_mw / 10000.0  # Scale factor
        self.state.voltage_pu = 1.0 + voltage_deviation

        # Check protection trips
        self._update_protection()

        # Log significant deviations
        if abs(frequency_deviation) > self.params.frequency_deadband_hz:
            self.logger.warning(
                f"Grid frequency deviation: {self.state.frequency_hz:.3f}Hz "
                f"(imbalance: {imbalance_mw:.1f}MW)"
            )

    def _update_protection(self) -> None:
        """Update grid protection trip status.

        Checks if frequency or voltage exceed safe limits and sets trip flags.
        """
        # Frequency protection
        old_uf_trip = self.state.under_frequency_trip
        old_of_trip = self.state.over_frequency_trip

        self.state.under_frequency_trip = (
            self.state.frequency_hz < self.params.min_frequency_hz
        )
        self.state.over_frequency_trip = (
            self.state.frequency_hz > self.params.max_frequency_hz
        )

        # Log trip events
        if self.state.under_frequency_trip and not old_uf_trip:
            self.logger.error(
                f"UNDER-FREQUENCY TRIP: {self.state.frequency_hz:.3f}Hz "
                f"(limit: {self.params.min_frequency_hz}Hz)"
            )

        if self.state.over_frequency_trip and not old_of_trip:
            self.logger.error(
                f"OVER-FREQUENCY TRIP: {self.state.frequency_hz:.3f}Hz "
                f"(limit: {self.params.max_frequency_hz}Hz)"
            )

        # Voltage protection
        old_uv_trip = self.state.undervoltage_trip
        old_ov_trip = self.state.overvoltage_trip

        self.state.undervoltage_trip = (
            self.state.voltage_pu < self.params.min_voltage_pu
        )
        self.state.overvoltage_trip = self.state.voltage_pu > self.params.max_voltage_pu

        # Log trip events
        if self.state.undervoltage_trip and not old_uv_trip:
            self.logger.error(
                f"UNDERVOLTAGE TRIP: {self.state.voltage_pu:.3f}pu "
                f"(limit: {self.params.min_voltage_pu}pu)"
            )

        if self.state.overvoltage_trip and not old_ov_trip:
            self.logger.error(
                f"OVERVOLTAGE TRIP: {self.state.voltage_pu:.3f}pu "
                f"(limit: {self.params.max_voltage_pu}pu)"
            )

    # ----------------------------------------------------------------
    # State access
    # ----------------------------------------------------------------

    def get_state(self) -> GridState:
        """Get current grid state.

        Returns:
            Current GridState snapshot
        """
        return self.state

    def get_telemetry(self) -> dict[str, Any]:
        """Get telemetry data in dictionary format.

        Returns:
            Dictionary with current grid telemetry
        """
        return {
            "frequency_hz": round(self.state.frequency_hz, 3),
            "voltage_pu": round(self.state.voltage_pu, 3),
            "total_generation_mw": round(self.state.total_gen_mw, 1),
            "total_load_mw": round(self.state.total_load_mw, 1),
            "imbalance_mw": round(
                self.state.total_gen_mw - self.state.total_load_mw, 1
            ),
            "under_frequency_trip": self.state.under_frequency_trip,
            "over_frequency_trip": self.state.over_frequency_trip,
            "undervoltage_trip": self.state.undervoltage_trip,
            "overvoltage_trip": self.state.overvoltage_trip,
        }
