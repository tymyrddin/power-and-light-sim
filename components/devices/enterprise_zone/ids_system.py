# components/devices/enterprise_zone/ids_system.py
"""Industrial IDS/IPS system."""

from components.devices.core.base_device import BaseDevice


class IDSSystem(BaseDevice):
    """Industrial Intrusion Detection System (passive monitoring)."""

    protocol_name = "passive"  # Observation only

    DEFAULT_SETUP = {
        # Protocol decoders (passive)
        "monitored_protocols": ["modbus", "iec104", "iec61850", "dnp3"],
        # Detection rules
        "alert_rules": [],
        # Traffic logs
        "traffic_log": [],
    }

    def __init__(self, device_id: int, description: str = "IDS System", protocols=None):
        super().__init__(
            device_id=device_id, description=description, protocols=protocols
        )
