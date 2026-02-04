# components/devices/__init__.py
"""Device implementations for ICS simulation."""

from components.devices.control_zone.plc.vendor_specific.hvac_plc import HVACPLC
from components.devices.control_zone.plc.vendor_specific.reactor_plc import ReactorPLC
from components.devices.control_zone.plc.vendor_specific.turbine_plc import TurbinePLC
from components.devices.control_zone.rtu import BaseRTU, SubstationRTU
from components.devices.control_zone.safety.reactor_safety_plc import ReactorSafetyPLC
from components.devices.control_zone.safety.sis_controller import SISController
from components.devices.control_zone.safety.turbine_safety_plc import TurbineSafetyPLC
from components.devices.control_zone.specialty.lspace_monitor import LSpaceMonitor
from components.devices.core.base_device import BaseDevice
from components.devices.enterprise_zone.enterprise_workstation import (
    EnterpriseWorkstation,
)
from components.devices.enterprise_zone.historian import Historian
from components.devices.enterprise_zone.ids_system import IDSSystem
from components.devices.enterprise_zone.ied import IED
from components.devices.enterprise_zone.legacy_workstation import LegacyWorkstation
from components.devices.enterprise_zone.siem_system import SIEMSystem
from components.devices.enterprise_zone.substation_controller import (
    SubstationController,
)
from components.devices.operations_zone.engineering_workstation import (
    EngineeringWorkstation,
)
from components.devices.operations_zone.hmi_workstation import HMIWorkstation
from components.devices.operations_zone.scada_server import SCADAServer

__all__ = [
    "BaseDevice",
    "BaseRTU",
    "SubstationRTU",
    "IED",
    "SubstationController",
    "SISController",
    "TurbineSafetyPLC",
    "ReactorSafetyPLC",
    "SCADAServer",
    "Historian",
    "EngineeringWorkstation",
    "HMIWorkstation",
    "IDSSystem",
    "SIEMSystem",
    "TurbinePLC",
    "HVACPLC",
    "ReactorPLC",
    "LSpaceMonitor",
    "LegacyWorkstation",
    "EnterpriseWorkstation",
    "DEVICE_REGISTRY",
]

# ================================================================
# Device Registry - Maps device type (from config) to class
# ================================================================
DEVICE_REGISTRY = {
    # Control Zone - PLCs
    "turbine_plc": TurbinePLC,
    "hvac_plc": HVACPLC,
    "reactor_plc": ReactorPLC,
    # Control Zone - RTUs
    "substation_rtu": SubstationRTU,
    # Control Zone - Safety
    "safety_plc": SISController,  # Generic configurable SIS
    "turbine_safety_plc": TurbineSafetyPLC,  # Dedicated turbine safety
    "reactor_safety_plc": ReactorSafetyPLC,  # Dedicated reactor safety
    # Control Zone - Specialty
    "specialty_controller": LSpaceMonitor,  # L-Space dimensional stability monitor
    # Control Zone - Legacy
    "legacy_system": LegacyWorkstation,  # Windows 98 data collector
    "legacy_workstation": LegacyWorkstation,  # Alias
    # Operations Zone
    "scada_server": SCADAServer,
    "hmi_workstation": HMIWorkstation,
    "engineering_workstation": EngineeringWorkstation,
    "historian": Historian,
    # Enterprise Zone
    "enterprise_workstation": EnterpriseWorkstation,
    "ids_system": IDSSystem,
    "siem_system": SIEMSystem,
}
