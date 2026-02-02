# components/devices/control_zone/__init__.py
"""
Control Zone devices for UU Power & Light Co.

Purdue Level 0-2 devices including:
- PLCs: TurbinePLC, ReactorPLC, HVACPLC
- RTUs: BaseRTU (substation RTUs)
- Safety Controllers: TurbineSafetyPLC, ReactorSafetyPLC
- Legacy: The forgotten Windows 98 box in the corner
"""

from components.devices.control_zone.legacy_workstation import (
    CSVLogEntry,
    DiscoveredArtifact,
    LegacyWorkstation,
)
from components.devices.control_zone.plc import (
    HVACPLC,
    BasePLC,
    ReactorPLC,
    TurbinePLC,
)
from components.devices.control_zone.rtu import (
    BaseRTU,
    BreakerState,
    RelayType,
    SubstationRTU,
)
from components.devices.control_zone.safety import (
    BaseSafetyController,
    ReactorSafetyPLC,
    SafetyIntegrityLevel,
    TurbineSafetyPLC,
    VotingArchitecture,
)

__all__ = [
    # PLCs
    "BasePLC",
    "TurbinePLC",
    "ReactorPLC",
    "HVACPLC",
    # RTUs
    "BaseRTU",
    "SubstationRTU",
    "BreakerState",
    "RelayType",
    # Safety Controllers
    "BaseSafetyController",
    "SafetyIntegrityLevel",
    "VotingArchitecture",
    "TurbineSafetyPLC",
    "ReactorSafetyPLC",
    # Legacy
    "LegacyWorkstation",
    "CSVLogEntry",
    "DiscoveredArtifact",
]
