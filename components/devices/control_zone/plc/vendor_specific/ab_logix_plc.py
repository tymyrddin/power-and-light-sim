# components/devices/control_zone/plc/vendor_specific/ab_logix_plc.py
"""Allen-Bradley (Rockwell) Logix PLC device."""

from components.devices.control_zone.plc.generic.base_plc import BasePLC


class ABLogixPLC(BasePLC):
    """Allen-Bradley ControlLogix/CompactLogix PLC using EtherNet/IP, CIP Safety, and Modbus."""

    protocol_name = "enip"  # EtherNet/IP

    DEFAULT_SETUP = {
        "tags": {
            # Boolean tags
            "Program:MainProgram.Relay1": False,
            "Program:MainProgram.Relay2": False,
            "Program:MainProgram.Emergency_Stop": False,
            # Integer tags (DINT)
            "Program:MainProgram.Counter1": 0,
            "Program:MainProgram.SetPoint": 0,
            "Program:MainProgram.Status": 0,
            # Real (floating point) tags
            "Program:MainProgram.Temperature": 0.0,
            "Program:MainProgram.Pressure": 0.0,
            "Program:MainProgram.Flow_Rate": 0.0,
        }
    }

    def __init__(
        self,
        device_id: int,
        description: str = "Allen-Bradley Logix PLC",
        protocols=None,
    ):
        super().__init__(
            device_id=device_id, description=description, protocols=protocols
        )

    def read_tag(self, tag_name: str):
        """Read a tag value by name."""
        return self.setup["tags"].get(tag_name)

    def write_tag(self, tag_name: str, value) -> bool:
        """Write a tag value by name."""
        if tag_name in self.setup["tags"]:
            self.setup["tags"][tag_name] = value
            return True
        return False
