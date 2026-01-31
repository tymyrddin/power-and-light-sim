# components/devices/siem_system.py
"""Security Information and Event Management system."""

from components.devices.core.base_device import BaseDevice


class SIEMSystem(BaseDevice):
    """SIEM system for log aggregation and analysis (not ICS protocols)."""

    protocol_name = "syslog"

    DEFAULT_SETUP = {
        # Log sources
        "syslog_sources": [],
        "api_endpoints": [],
        # Event correlation
        "events": [],
        "alerts": [],
    }

    def __init__(
        self, device_id: int, description: str = "SIEM System", protocols=None
    ):
        super().__init__(
            device_id=device_id, description=description, protocols=protocols
        )
