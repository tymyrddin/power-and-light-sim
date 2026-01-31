# components/devices/control_zone/plc/generic/modbus_plc.py
"""Generic Modbus PLC device."""

from components.devices.control_zone.plc.generic.base_plc import BasePLC


class ModbusPLC(BasePLC):
    """Generic Modbus PLC with standard memory layout."""

    protocol_name = "modbus"

    DEFAULT_SETUP = {
        "coils": [False] * 64,
        "discrete_inputs": [False] * 64,
        "holding_registers": [0] * 64,
        "input_registers": [0] * 64,
    }

    def __init__(self, device_id: int, description: str = "Modbus PLC", protocols=None):
        super().__init__(
            device_id=device_id, description=description, protocols=protocols
        )
