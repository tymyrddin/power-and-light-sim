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

    # ------------------------------------------------------------------
    # Device sync - call these from device scan cycle
    # ------------------------------------------------------------------

    async def sync_from_device(self, memory_map: dict[str, object]) -> None:
        """Push device memory_map to Modbus TCP server via adapter."""
        for i in range(self.adapter.num_input_registers):
            key = f"input_registers[{i}]"
            if key in memory_map:
                value = memory_map[key]
                if isinstance(value, (int, float)):
                    await self.adapter.write_register(i, int(value))
        for i in range(self.adapter.num_discrete_inputs):
            key = f"discrete_inputs[{i}]"
            if key in memory_map:
                await self.adapter.write_coil(i, bool(memory_map[key]))

    async def sync_to_device(self, memory_map: dict[str, object]) -> None:
        """Pull external writes from Modbus TCP server into memory_map."""
        result = await self.adapter.read_coils(0, self.adapter.num_coils)
        if hasattr(result, "bits"):
            for i, val in enumerate(result.bits):
                memory_map[f"coils[{i}]"] = bool(val)
        result = await self.adapter.read_holding_registers(0, self.adapter.num_holding_registers)
        if hasattr(result, "registers"):
            for i, val in enumerate(result.registers):
                memory_map[f"holding_registers[{i}]"] = int(val)

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
