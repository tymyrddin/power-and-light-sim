# components/devices/substation_controller.py
"""Substation automation controller."""

from components.devices.core.base_device import BaseDevice


class SubstationController(BaseDevice):
    """Substation controller with IEC 61850, IEC-104, and Modbus support."""

    protocol_name = "iec61850"  # Primary protocol

    DEFAULT_SETUP = {
        # IEC 61850
        "logical_nodes": {},
        "goose_data": [],
        # IEC-104
        "single_points": [False] * 64,
        "measured_values": [0.0] * 64,
        # Modbus
        "coils": [False] * 64,
        "holding_registers": [0] * 64,
    }

    def __init__(
        self, device_id: int, description: str = "Substation Controller", protocols=None
    ):
        super().__init__(
            device_id=device_id, description=description, protocols=protocols
        )
