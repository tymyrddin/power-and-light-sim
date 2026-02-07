#!/usr/bin/env python3
"""
IEC 60870-5-104 adapter using Fraunhofer c104.

- Uses c104.Server (real simulator)
- Runs blocking server in a background thread
- Exposes async lifecycle for the simulator manager
"""

import asyncio
import threading
import time

import c104
from components.security.logging_system import get_logger

logger = get_logger(__name__)


class IEC104C104Adapter:
    """Async-friendly IEC 60870-5-104 simulator adapter."""

    def __init__(
        self,
        bind_host="0.0.0.0",
        bind_port=2404,
        common_address=1,
        simulator_mode=True,
    ):
        self.bind_host = bind_host
        self.bind_port = bind_port
        self.common_address = common_address
        self.simulator_mode = simulator_mode

        self._server = None
        self._station = None
        self._thread = None
        self._running = False
        self._stop_event = threading.Event()

        # Internal state with thread-safety
        self._state = {}
        self._state_lock = threading.Lock()

    # ------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------

    async def connect(self) -> bool:
        """
        Start IEC104 simulator.
        """
        if self._running or not self.simulator_mode:
            return True

        def _run():
            try:
                self._server = c104.Server(
                    ip=self.bind_host,
                    port=self.bind_port,
                )

                self._station = self._server.add_station(
                    common_address=self.common_address
                )

                self._server.start()
                self._running = True
                print(
                    f"[DEBUG] IEC104 server started on {self.bind_host}:{self.bind_port}"
                )
                logger.info(
                    f"IEC104 simulator started on {self.bind_host}:{self.bind_port}"
                )

                # Keep thread alive by waiting on stop event
                while not self._stop_event.is_set():
                    time.sleep(0.1)

            except Exception as e:
                print(f"[DEBUG] IEC104 server start error: {e}")
                import traceback

                traceback.print_exc()
                logger.error(f"IEC104 server failed to start: {e}")
                self._running = False

        self._stop_event.clear()
        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

        # Give socket time to bind and thread to start
        await asyncio.sleep(0.3)

        if not self._running:
            print("[DEBUG] IEC104 not running after sleep")
            logger.error(
                f"IEC104 simulator did not start on {self.bind_host}:{self.bind_port}"
            )
        return self._running

    async def disconnect(self) -> None:
        """
        Stop simulator.
        """
        if not self._server:
            return

        def _stop():
            try:
                if self._server:
                    self._server.stop()
                self._stop_event.set()
            except Exception as e:
                logger.error(f"Error stopping IEC104 server: {e}")

        await asyncio.to_thread(_stop)

        # Wait for thread to finish
        if self._thread and self._thread.is_alive():
            await asyncio.to_thread(self._thread.join, timeout=1.0)

        self._server = None
        self._station = None
        self._running = False
        logger.info(f"IEC104 simulator stopped on {self.bind_host}:{self.bind_port}")

    # ------------------------------------------------------------
    # async-facing helpers
    # ------------------------------------------------------------

    async def probe(self):
        """
        Minimal recon output.
        """
        with self._state_lock:
            points_count = len(self._state)

        return {
            "protocol": "IEC60870-5-104",
            "implementation": "c104",
            "listening": self._running,
            "bind": f"{self.bind_host}:{self.bind_port}",
            "common_address": self.common_address,
            "points": points_count,
        }

    async def set_point(self, ioa, value):
        """
        Set / update a simulated information object.
        """
        with self._state_lock:
            self._state[ioa] = value

        if not self._server or not self._station:
            return

        def _send():
            try:
                # Check if point exists
                point = None
                for p in self._station.points:
                    if p.io_address == ioa:
                        point = p
                        break

                # Create point if it doesn't exist
                if not point:
                    point = self._station.add_point(
                        io_address=ioa,
                        type=c104.Type.M_ME_NC_1,  # Measured value, short floating point
                    )

                # Update value
                point.value = value
                point.report(cause=c104.Cot.SPONTANEOUS)

            except Exception as e:
                logger.debug(f"Error sending point {ioa}: {e}")

        await asyncio.to_thread(_send)

    async def get_state(self):
        """
        Return full simulator state.
        """
        with self._state_lock:
            return dict(self._state)
