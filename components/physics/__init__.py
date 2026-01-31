# components/physics/__init__.py
"""
Physics simulation engines for ICS environments.

This module provides physical process simulations for industrial equipment:
- Turbine dynamics (steam turbines, shaft speed, power output)
- Reactor physics (temperature, pressure, reaction kinetics)
- HVAC systems (temperature, humidity, air handling)
- Grid physics (frequency, load-generation balance)
- Power flow (transmission lines, bus voltages)
"""

from components.physics.grid_physics import GridParameters, GridPhysics, GridState
from components.physics.hvac_physics import HVACParameters, HVACPhysics, HVACState
from components.physics.power_flow import (
    BusState,
    LineState,
    PowerFlow,
    PowerFlowParameters,
)
from components.physics.reactor_physics import (
    ReactorParameters,
    ReactorPhysics,
    ReactorState,
)
from components.physics.turbine_physics import (
    TurbineParameters,
    TurbinePhysics,
    TurbineState,
)

__all__ = [
    # Turbine
    "TurbinePhysics",
    "TurbineState",
    "TurbineParameters",
    # Reactor
    "ReactorPhysics",
    "ReactorState",
    "ReactorParameters",
    # HVAC
    "HVACPhysics",
    "HVACState",
    "HVACParameters",
    # Grid
    "GridPhysics",
    "GridState",
    "GridParameters",
    # Power Flow
    "PowerFlow",
    "BusState",
    "LineState",
    "PowerFlowParameters",
]
