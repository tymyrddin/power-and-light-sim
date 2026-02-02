# protocols/modbus/modbus_rtu_protocol.py
"""
Modbus RTU protocol wrapper.

Exposes attacker-relevant capabilities.
"""

from components.protocols.base_protocol import BaseProtocol


class ModbusRTUProtocol(BaseProtocol):
    def __init__(self, adapter):
        super().__init__("modbus_rtu")
        self.adapter = adapter

    # ------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------
    async def connect(self) -> bool:
        self.connected = await self.adapter.connect()
        return self.connected

    async def disconnect(self) -> None:
        await self.adapter.disconnect()
        self.connected = False

    # ------------------------------------------------------------
    # Recon
    # ------------------------------------------------------------
    async def probe(self) -> dict[str, object]:
        """Probe device capabilities"""
        base_info: dict[str, object] = {
            "protocol": self.protocol_name,
            "connected": self.connected,
            "coils_readable": False,
            "discrete_inputs_readable": False,
            "holding_registers_readable": False,
            "input_registers_readable": False,
            "device_info_readable": False,
        }

        if not self.connected:
            return base_info

        # Test read capabilities
        try:
            result = await self.adapter.read_coils(0, 1)
            if not (hasattr(result, "isError") and result.isError()):
                base_info["coils_readable"] = True
        except Exception:
            pass

        try:
            result = await self.adapter.read_discrete_inputs(0, 1)
            if not (hasattr(result, "isError") and result.isError()):
                base_info["discrete_inputs_readable"] = True
        except Exception:
            pass

        try:
            result = await self.adapter.read_holding_registers(0, 1)
            if not (hasattr(result, "isError") and result.isError()):
                base_info["holding_registers_readable"] = True
        except Exception:
            pass

        try:
            result = await self.adapter.read_input_registers(0, 1)
            if not (hasattr(result, "isError") and result.isError()):
                base_info["input_registers_readable"] = True
        except Exception:
            pass

        try:
            device_info = await self.adapter.get_device_info()
            if device_info:
                base_info["device_info_readable"] = True
                base_info["device_info"] = device_info
        except Exception:
            pass

        return base_info

    # ------------------------------------------------------------------
    # Device sync - call these from device scan cycle
    # ------------------------------------------------------------------

    # sync_from_device
    async def sync_from_device(self, memory_map: dict[str, object]) -> None:
        """Push device memory_map to Modbus server via adapter."""
        for i in range(self.adapter.num_input_registers):
            key = f"input_registers[{i}]"
            if key in memory_map:
                value = memory_map[key]
                if isinstance(value, (int, float)):
                    await self.adapter.write_register(i, int(value))
        for i in range(self.adapter.num_discrete_inputs):
            key = f"discrete_inputs[{i}]"
            if key in memory_map:
                value = memory_map[key]
                await self.adapter.write_coil(i, bool(value))

    # sync_to_device
    async def sync_to_device(self, memory_map: dict[str, object]) -> None:
        """Pull external writes from Modbus server into memory_map."""
        result = await self.adapter.read_coils(0, self.adapter.num_coils)
        if hasattr(result, "bits"):
            for i, val in enumerate(result.bits):
                memory_map[f"coils[{i}]"] = bool(val)
        result = await self.adapter.read_holding_registers(0, self.adapter.num_holding_registers)
        if hasattr(result, "registers"):
            for i, val in enumerate(result.registers):
                memory_map[f"holding_registers[{i}]"] = int(val)

    # ------------------------------------------------------------
    # Attack primitives
    # ------------------------------------------------------------
    async def scan_memory(self, start: int = 0, count: int = 100) -> dict[str, object]:
        """Scan device memory for readable regions"""
        results: dict[str, object] = {
            "coils": [],
            "discrete_inputs": [],
            "holding_registers": [],
            "input_registers": [],
        }

        # Scan coils
        try:
            result = await self.adapter.read_coils(start, count)
            if hasattr(result, "bits"):
                results["coils"] = result.bits[:count]
        except Exception:
            pass

        # Scan discrete inputs
        try:
            result = await self.adapter.read_discrete_inputs(start, count)
            if hasattr(result, "bits"):
                results["discrete_inputs"] = result.bits[:count]
        except Exception:
            pass

        # Scan holding registers
        try:
            result = await self.adapter.read_holding_registers(start, count)
            if hasattr(result, "registers"):
                results["holding_registers"] = result.registers[:count]
        except Exception:
            pass

        # Scan input registers
        try:
            result = await self.adapter.read_input_registers(start, count)
            if hasattr(result, "registers"):
                results["input_registers"] = result.registers[:count]
        except Exception:
            pass

        return results

    async def test_write_access(self, address: int = 0) -> dict[str, object]:
        """Test if device allows writes"""
        results: dict[str, object] = {
            "coil_writable": False,
            "register_writable": False,
        }

        # Test coil write
        try:
            original = await self.adapter.read_coils(address, 1)
            if hasattr(original, "bits") and len(original.bits) > 0:
                test_value = not original.bits[0]
                result = await self.adapter.write_coil(address, test_value)
                if not (hasattr(result, "isError") and result.isError()):
                    # Restore original
                    await self.adapter.write_coil(address, original.bits[0])
                    results["coil_writable"] = True
        except Exception:
            pass

        # Test register write
        try:
            original = await self.adapter.read_holding_registers(address, 1)
            if hasattr(original, "registers") and len(original.registers) > 0:
                test_value = (original.registers[0] + 1) % 65536
                result = await self.adapter.write_register(address, test_value)
                if not (hasattr(result, "isError") and result.isError()):
                    # Restore original
                    await self.adapter.write_register(address, original.registers[0])
                    results["register_writable"] = True
        except Exception:
            pass

        return results
