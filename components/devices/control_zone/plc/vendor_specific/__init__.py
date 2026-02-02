# components/devices/control_zone/plc/vendor_specific/__init__.py
"""
Vendor-specific PLC implementations for UU Power & Light Co.

Base Classes:
- S7PLC: Siemens S7-300/400/1200/1500 style PLC
- ABLogixPLC: Allen-Bradley ControlLogix/CompactLogix style PLC

Application PLCs:
- TurbinePLC: Allen-Bradley ControlLogix for Hex Steam Turbine
- ReactorPLC: Siemens S7-400 for Alchemical Reactor
- HVACPLC: Schneider Modicon for Library Environmental
"""

from components.devices.control_zone.plc.vendor_specific.ab_logix_plc import (
    ABLogixPLC,
    LogixDataType,
    LogixProgram,
    LogixTag,
)
from components.devices.control_zone.plc.vendor_specific.hvac_plc import HVACPLC
from components.devices.control_zone.plc.vendor_specific.reactor_plc import ReactorPLC
from components.devices.control_zone.plc.vendor_specific.s7_plc import S7PLC
from components.devices.control_zone.plc.vendor_specific.turbine_plc import TurbinePLC

__all__ = [
    # Vendor base classes
    "S7PLC",
    "ABLogixPLC",
    "LogixDataType",
    "LogixTag",
    "LogixProgram",
    # Application PLCs
    "TurbinePLC",
    "ReactorPLC",
    "HVACPLC",
]
