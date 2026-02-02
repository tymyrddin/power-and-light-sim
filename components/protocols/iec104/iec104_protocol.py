"""
IEC 60870-5-104 protocol abstraction.

Library-agnostic IEC-104 behaviour.
Concrete IEC-104 client implementations are injected.
"""

from components.protocols.base_protocol import BaseProtocol


class IEC104Protocol(BaseProtocol):
    def __init__(self, adapter):
        super().__init__("iec104")
        self.adapter = adapter
        self.data_transfer_started = False

    # ------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------

    async def connect(self) -> bool:
        self.connected = await self.adapter.connect()
        return self.connected

    async def disconnect(self) -> None:
        if self.connected:
            await self.adapter.disconnect()
        self.connected = False
        self.data_transfer_started = False

    # ------------------------------------------------------------
    # IEC-104 primitives
    # ------------------------------------------------------------

    async def start_data_transfer(self) -> bool:
        if not self.connected:
            return False

        # Simulator always accepts DT
        self.data_transfer_started = True
        return True

    async def stop_data_transfer(self) -> None:
        self.data_transfer_started = False

    async def interrogation(self):
        if not self.data_transfer_started:
            raise RuntimeError("Data transfer not started")

        # Simulator: interrogation == state dump
        return await self.adapter.get_state()

    # ------------------------------------------------------------
    # recon
    # ------------------------------------------------------------

    async def probe(self) -> dict[str, object]:
        """
        Probe IEC-104 capabilities.

        If already connected, tests capabilities without disconnecting.
        If not connected, attempts to connect, test, and disconnect.
        """
        result = {
            "protocol": self.protocol_name,
            "connected": False,
            "startdt": False,
            "interrogation": False,
        }

        # Track if we connected during this probe
        probe_connected = False

        # If not already connected, try to connect for the probe
        if not self.connected:
            if not await self.connect():
                # Failed to connect, return early
                return result
            probe_connected = True

        result["connected"] = True

        # Test data transfer
        dt_was_active = self.data_transfer_started
        if not dt_was_active:
            if await self.start_data_transfer():
                result["startdt"] = True
                try:
                    state = await self.interrogation()
                    result["interrogation"] = bool(state is not None)
                except Exception:
                    pass
                finally:
                    await self.stop_data_transfer()
        else:
            # Data transfer already active
            result["startdt"] = True
            try:
                state = await self.interrogation()
                result["interrogation"] = bool(state is not None)
            except Exception:
                pass

        # Only disconnect if we connected during this probe
        if probe_connected:
            await self.disconnect()

        return result

    # ------------------------------------------------------------
    # exploitation primitives
    # ------------------------------------------------------------

    async def set_point(self, ioa: int, value):
        """
        Force a process value.
        """
        if not self.data_transfer_started:
            raise RuntimeError("Data transfer not started")

        return await self.adapter.set_point(ioa, value)

    async def overwrite_state(self, mapping: dict[int, object]):
        """
        Bulk overwrite process image.
        """
        if not self.data_transfer_started:
            raise RuntimeError("Data transfer not started")

        for ioa, value in mapping.items():
            await self.adapter.set_point(ioa, value)
