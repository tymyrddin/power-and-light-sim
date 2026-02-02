#!/usr/bin/env python3
"""
Siemens S7 adapter using python-snap7 2.0.2.

- Wraps snap7.client.Client
- Runs blocking PLC calls via asyncio.to_thread
- Exposes async lifecycle and attacker-meaningful primitives
"""

import asyncio

import snap7
from snap7.util import get_bool, set_bool


class Snap7Adapter202:
    """Async-friendly Siemens S7 adapter."""

    def __init__(
        self,
        host="127.0.0.1",
        rack=0,
        slot=1,
        simulator_mode=True,
    ):
        self.host = host
        self.rack = rack
        self.slot = slot
        self.simulator_mode = simulator_mode

        self._client = snap7.client.Client()
        self._connected = False

    # ------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------

    async def connect(self):
        """
        Connect to PLC or simulator.
        """
        if self._connected:
            return True

        def _connect():
            self._client.connect(self.host, self.rack, self.slot)
            return self._client.get_connected()

        self._connected = await asyncio.to_thread(_connect)
        return self._connected

    async def disconnect(self):
        """
        Disconnect cleanly.
        """
        if not self._connected:
            return

        await asyncio.to_thread(self._client.disconnect)
        self._connected = False

    # ------------------------------------------------------------
    # recon
    # ------------------------------------------------------------

    async def probe(self):
        """
        Minimal recon output.
        """
        if not self._connected:
            return {
                "protocol": "s7",
                "connected": False,
            }

        def _info():
            return {
                "protocol": "s7",
                "connected": True,
                "plc_state": self._client.get_cpu_state(),
                "plc_info": self._client.get_cpu_info(),
            }

        return await asyncio.to_thread(_info)

    # ------------------------------------------------------------
    # exploitation primitives
    # ------------------------------------------------------------

    async def read_db(self, db_number, start, size):
        """
        Read bytes from a Data Block.
        """

        def _read():
            return self._client.db_read(db_number, start, size)

        return await asyncio.to_thread(_read)

    async def write_db(self, db_number, start, data):
        """
        Write bytes to a Data Block.
        """

        def _write():
            self._client.db_write(db_number, start, data)

        await asyncio.to_thread(_write)

    async def read_bool(self, db_number, byte_index, bit_index):
        """
        Read a single boolean from a DB.
        """
        data = await self.read_db(db_number, byte_index, 1)
        return get_bool(data, 0, bit_index)

    async def write_bool(self, db_number, byte_index, bit_index, value):
        """
        Write a single boolean to a DB.
        """
        data = bytearray(1)
        set_bool(data, 0, bit_index, value)
        await self.write_db(db_number, byte_index, data)

    async def stop_plc(self):
        """
        Stop PLC CPU.
        """
        await asyncio.to_thread(self._client.plc_stop)

    async def start_plc(self):
        """
        Start PLC CPU.
        """
        await asyncio.to_thread(self._client.plc_hot_start)
