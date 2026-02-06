# protocols/modbus/modbus_protocol.py
"""
Modbus protocol abstraction.

Library-agnostic attacker behaviour.
"""

from components.protocols.base_protocol import BaseProtocol


class ModbusProtocol(BaseProtocol):
    def __init__(self, adapter):
        super().__init__("modbus")
        self.adapter = adapter

    # ------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------

    async def connect(self) -> bool:
        self.connected = await self.adapter.connect()
        return self.connected

    async def disconnect(self) -> None:
        await self.adapter.disconnect()
        self.connected = False

    # ------------------------------------------------------------
    # recon
    # ------------------------------------------------------------

    async def probe(self) -> dict[str, object]:
        result = {
            "protocol": self.protocol_name,
            "connected": self.connected,
            "coils_readable": False,
            "holding_registers_readable": False,
        }

        if not self.connected:
            return result

        try:
            for offset in range(4):
                resp = await self.adapter.read_coils(offset)
                if not resp or resp.isError():
                    raise RuntimeError
            result["coils_readable"] = True
        except Exception:
            pass

        try:
            for offset in range(4):
                resp = await self.adapter.read_holding_registers(offset)
                if not resp or resp.isError():
                    raise RuntimeError
            result["holding_registers_readable"] = True
        except Exception:
            pass

        return result

    # ------------------------------------------------------------
    # exploitation primitives
    # ------------------------------------------------------------

    async def read_coils(self, address: int, count: int = 1):
        results = []
        for offset in range(count):
            results.append(await self.adapter.read_coils(address + offset))
        return results

    async def read_holding_registers(self, address: int, count: int = 1):
        results = []
        for offset in range(count):
            results.append(await self.adapter.read_holding_registers(address + offset))
        return results

    async def write_coil(self, address: int, value: bool):
        return await self.adapter.write_coil(address, value)

    async def write_register(self, address: int, value: int):
        return await self.adapter.write_register(address, value)
