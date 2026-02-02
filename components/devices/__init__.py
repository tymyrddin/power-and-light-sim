# components/devices/__init__.py
"""Device implementations for ICS simulation."""

from components.devices.control_zone.plc.vendor_specific.turbine_plc import TurbinePLC
from components.devices.control_zone.rtu import BaseRTU, SubstationRTU
from components.devices.control_zone.safety.sis_controller import SISController
from components.devices.core.base_device import BaseDevice
from components.devices.enterprise_zone.historian import Historian
from components.devices.enterprise_zone.ids_system import IDSSystem
from components.devices.enterprise_zone.ied import IED
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
    "SCADAServer",
    "Historian",
    "EngineeringWorkstation",
    "HMIWorkstation",
    "IDSSystem",
    "SIEMSystem",
    "TurbinePLC",
    "DEVICE_REGISTRY",
]

# ================================================================
# Device Registry - Maps device type (from config) to class
# ================================================================
DEVICE_REGISTRY = {
    # Control Zone - PLCs
    "turbine_plc": TurbinePLC,
    # "reactor_plc": ReactorPLC,  # TODO: Add when implemented
    # "hvac_plc": HVACPLC,  # TODO: Add when implemented

    # Control Zone - RTUs
    "substation_rtu": SubstationRTU,

    # Control Zone - Safety
    "safety_plc": SISController,

    # Operations Zone
    "scada_server": SCADAServer,
    "hmi_workstation": HMIWorkstation,
    "engineering_workstation": EngineeringWorkstation,

    # Enterprise Zone
    "historian": Historian,
    "ids_system": IDSSystem,
    "siem_system": SIEMSystem,
}
