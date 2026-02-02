# components/devices/control_zone/safety/__init__.py
"""
Safety Instrumented System (SIS) controllers for UU Power & Light Co.

Provides safety-critical control systems independent from basic process
control (BPCS). All safety controllers extend BaseSafetyController and
implement IEC 61511 compliant safety logic.

Classes:
- BaseSafetyController: Abstract base for all safety controllers
- TurbineSafetyPLC: Dedicated safety PLC for Hex Steam Turbine
- ReactorSafetyPLC: Dedicated safety PLC for Alchemical Reactor
- SISController: Configurable multi-function SIS controller

Enums:
- SafetyIntegrityLevel: SIL1-SIL4 per IEC 61508
- VotingArchitecture: Redundancy voting (1oo1, 1oo2, 2oo3, etc.)
- TripAction: Actions when SIF trips (log, alarm, trip, scram)

Dataclasses:
- SafetyInstrumentedFunction: Configuration for a single SIF
"""

from components.devices.control_zone.safety.base_safety_controller import (
    BaseSafetyController,
    SafetyIntegrityLevel,
    VotingArchitecture,
)
from components.devices.control_zone.safety.reactor_safety_plc import ReactorSafetyPLC
from components.devices.control_zone.safety.sis_controller import (
    SafetyInstrumentedFunction,
    SISController,
    TripAction,
)
from components.devices.control_zone.safety.turbine_safety_plc import TurbineSafetyPLC

__all__ = [
    # Base class
    "BaseSafetyController",
    # Enums
    "SafetyIntegrityLevel",
    "VotingArchitecture",
    "TripAction",
    # Dataclasses
    "SafetyInstrumentedFunction",
    # Dedicated safety PLCs
    "TurbineSafetyPLC",
    "ReactorSafetyPLC",
    # Configurable SIS
    "SISController",
]
