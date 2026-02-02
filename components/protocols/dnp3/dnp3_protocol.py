"""
DNP3 protocol wrapper.

Exposes attacker-relevant capabilities.
"""

from __future__ import annotations

from components.protocols.base_protocol import BaseProtocol


class DNP3Protocol(BaseProtocol):
    def __init__(self, adapter):
        super().__init__("dnp3")
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
        """Probe DNP3 device capabilities"""
        base_info: dict[str, object] = {
            "protocol": self.protocol_name,
            "mode": self.adapter.mode,
            "connected": self.connected,
            "supports_integrity_scan": False,
            "supports_event_scan": False,
            "binary_inputs_count": 0,
            "analog_inputs_count": 0,
            "counters_count": 0,
        }

        if not self.connected:
            return base_info

        # For master mode, test scanning capabilities
        if self.adapter.mode == "master":
            try:
                await self.adapter.integrity_scan()
                base_info["supports_integrity_scan"] = True
            except Exception:
                pass

            try:
                await self.adapter.event_scan()
                base_info["supports_event_scan"] = True
            except Exception:
                pass

        # For outstation mode, report point counts
        else:
            base_info["binary_inputs_count"] = len(
                self.adapter.setup.get("binary_inputs", {})
            )
            base_info["analog_inputs_count"] = len(
                self.adapter.setup.get("analog_inputs", {})
            )
            base_info["counters_count"] = len(self.adapter.setup.get("counters", {}))

        return base_info

    # ------------------------------------------------------------
    # Attack primitives
    # ------------------------------------------------------------
    async def enumerate_points(self) -> dict[str, object]:
        """Enumerate all DNP3 data points (master mode)"""
        if self.adapter.mode != "master":
            raise RuntimeError("Point enumeration only available in master mode")

        results: dict[str, object] = {
            "binary_inputs": [],
            "analog_inputs": [],
        }

        # Perform integrity scan to get all points
        await self.adapter.integrity_scan()

        # Try to read ranges
        try:
            binary_data = await self.adapter.read_binary_inputs(0, 100)
            results["binary_inputs"] = binary_data
        except Exception:
            pass

        try:
            analog_data = await self.adapter.read_analog_inputs(0, 100)
            results["analog_inputs"] = analog_data
        except Exception:
            pass

        return results

    async def test_write_capabilities(self) -> dict[str, object]:
        """Test control capabilities (master mode)"""
        if self.adapter.mode != "master":
            raise RuntimeError("Write testing only available in master mode")

        tested_indices: list[tuple[str, int]] = []
        results: dict[str, object] = {
            "binary_output_successful": False,
            "analog_output_successful": False,
            "tested_indices": tested_indices,
        }

        # Test binary output on index 0
        try:
            success = await self.adapter.write_binary_output(0, True)
            results["binary_output_successful"] = success
            tested_indices.append(("binary", 0))
        except Exception:
            pass

        # Test analogue output on index 0
        try:
            success = await self.adapter.write_analog_output(0, 100.0)
            results["analog_output_successful"] = success
            tested_indices.append(("analog", 0))
        except Exception:
            pass

        return results

    async def send_unsolicited_response(self) -> bool:
        """Trigger unsolicited response (outstation mode)"""
        if self.adapter.mode != "outstation":
            raise RuntimeError("Unsolicited only available in outstation mode")

        if not self.adapter.connected:
            raise RuntimeError("Outstation not connected")

        # Update a value to trigger unsolicited response
        try:
            await self.adapter.update_binary_input(0, True)
            return True
        except Exception:
            return False

    async def flood_events(self, count: int = 100) -> dict[str, object]:
        """Generate flood of events (outstation mode)"""
        if self.adapter.mode != "outstation":
            raise RuntimeError("Event generation only available in outstation mode")

        if not self.adapter.connected:
            raise RuntimeError("Outstation not connected")

        results: dict[str, object] = {
            "events_generated": 0,
            "success": False,
        }

        try:
            # Get available binary input indices from the database
            if not self.adapter.database or not hasattr(
                self.adapter.database, "binary_inputs"
            ):
                results["success"] = True
                return results

            available_indices = list(self.adapter.database.binary_inputs.keys())

            if not available_indices:
                # No points to update, but not an error
                results["success"] = True
                return results

            for i in range(count):
                # Cycle through available points
                point_index = available_indices[i % len(available_indices)]
                # Alternate binary input values
                await self.adapter.update_binary_input(point_index, i % 2 == 0)
                results["events_generated"] = i + 1

            results["success"] = True
        except Exception as e:
            results["error"] = str(e)

        return results
