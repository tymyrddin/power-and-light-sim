# components/devices/control_zone/plc/vendor_specific/s7_plc.py
"""Siemens S7 PLC device."""

from components.devices.control_zone.plc.generic.base_plc import BasePLC


class S7PLC(BasePLC):
    """Siemens S7 PLC with S7comm, Profinet, and Modbus support."""

    protocol_name = "s7"

    DEFAULT_SETUP = {
        "db_blocks": {
            1: bytearray(256),  # DB1: 256 bytes
            2: bytearray(256),  # DB2: 256 bytes
        },
        "inputs": bytearray(128),  # PI (Process Inputs)
        "outputs": bytearray(128),  # PQ (Process Outputs)
        "flags": bytearray(128),  # M (Merkers/Flags)
    }

    def __init__(
        self, device_id: int, description: str = "Siemens S7 PLC", protocols=None
    ):
        super().__init__(
            device_id=device_id, description=description, protocols=protocols
        )

    def read_db(self, db_number: int, start: int, size: int) -> bytearray:
        """Read data from a specific DB block."""
        if db_number in self.setup["db_blocks"]:
            db = self.setup["db_blocks"][db_number]
            return db[start : start + size]
        return bytearray()

    def write_db(self, db_number: int, start: int, data: bytearray) -> bool:
        """Write data to a specific DB block."""
        if db_number in self.setup["db_blocks"]:
            db = self.setup["db_blocks"][db_number]
            db[start : start + len(data)] = data
            return True
        return False
