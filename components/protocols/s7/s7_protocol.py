# protocols/s7_protocol.py
"""
Siemens S7 protocol abstraction.

Library-agnostic attacker behaviour for S7.
Concrete S7 adapters are injected (duck-typed).
"""

from components.protocols.base_protocol import BaseProtocol


class S7Protocol(BaseProtocol):
    """
    S7 protocol wrapper exposing attacker-meaningful actions.

    Expected adapter interface (duck-typed):
      - connect() -> bool
      - disconnect() -> None
      - probe() -> dict
      - read_db(db, start, size)
      - write_db(db, start, data)
      - read_bool(db, byte, bit)
      - write_bool(db, byte, bit, value)
      - stop_plc()
      - start_plc()
    """

    def __init__(self, adapter):
        super().__init__("s7")
        self.adapter = adapter

    # ------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------

    async def connect(self):
        self.connected = await self.adapter.connect()
        return self.connected

    async def disconnect(self):
        if self.connected:
            await self.adapter.disconnect()
        self.connected = False

    # ------------------------------------------------------------
    # recon
    # ------------------------------------------------------------

    async def probe(self):
        result = {
            "protocol": self.protocol_name,
            "connected": self.connected,
            "db_readable": False,
            "db_writable": False,
        }

        if not self.connected:
            return result

        try:
            await self.adapter.read_db(1, 0, 1)
            result["db_readable"] = True
        except Exception:
            pass

        try:
            await self.adapter.write_db(1, 0, bytes([0x00]))
            result["db_writable"] = True
        except Exception:
            pass

        return result

    # ------------------------------------------------------------
    # exploitation primitives
    # ------------------------------------------------------------

    async def read_db(self, db, start, size):
        return await self.adapter.read_db(db, start, size)

    async def write_db(self, db, start, data):
        return await self.adapter.write_db(db, start, data)

    async def read_bool(self, db, byte, bit):
        return await self.adapter.read_bool(db, byte, bit)

    async def write_bool(self, db, byte, bit, value):
        return await self.adapter.write_bool(db, byte, bit, value)

    async def stop_plc(self):
        return await self.adapter.stop_plc()

    async def start_plc(self):
        return await self.adapter.start_plc()
