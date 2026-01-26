import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from config.config_loader import ConfigLoader

# Configure logging
logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# Time modes
# ----------------------------------------------------------------
class TimeMode(Enum):
    """Simulation time operation modes."""

    REALTIME = "realtime"
    ACCELERATED = "accelerated"
    STEPPED = "stepped"
    PAUSED = "paused"


@dataclass
class TimeState:
    """State container for simulation time tracking."""

    simulation_time: float = 0.0
    wall_time_start: float = 0.0
    wall_time_elapsed: float = 0.0
    mode: TimeMode = TimeMode.REALTIME
    speed_multiplier: float = 1.0
    paused: bool = False
    update_interval: float = 0.01  # default, overridden by YAML
    total_pause_duration: float = 0.0
    pause_start: Optional[float] = None


# ----------------------------------------------------------------
# Singleton simulation time manager
# ----------------------------------------------------------------
class SimulationTime:
    """Singleton simulation time manager.

    Provides centralised time authority for the entire simulation,
    supporting multiple operation modes (realtime, accelerated, stepped, paused).

    Example:
        `>>> sim_time = SimulationTime()`
        `>>> await sim_time.start()`
        `>>> current = sim_time.now()`
        `>>> await sim_time.set_speed(10.0)  # 10x acceleration`
    """

    _instance: Optional["SimulationTime"] = None
    _MAX_SPEED_MULTIPLIER = 1000.0  # Safety limit

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True

            # Declare instance attributes for static analysers
            self.state: TimeState
            self._lock: asyncio.Lock
            self._running: bool = False
            self._update_task: Optional[asyncio.Task] = None

            self._setup()

    def _setup(self):
        """Initialize singleton instance."""
        self.state = TimeState()
        self._lock = asyncio.Lock()
        self._running = False
        self._update_task: Optional[asyncio.Task] = None

        # Load from YAML
        self._load_config()

    def _load_config(self):
        """Load configuration from YAML."""
        config = ConfigLoader().load_all()
        runtime_cfg = config.get("simulation", {}).get("runtime", {})

        # Set update interval
        update_interval = runtime_cfg.get("update_interval", 0.01)
        if update_interval <= 0:
            logger.warning(
                f"Invalid update_interval {update_interval}, using default 0.01"
            )
            update_interval = 0.01
        self.state.update_interval = update_interval

        # Set initial mode
        if runtime_cfg.get("realtime", True):
            self.state.mode = TimeMode.REALTIME
        else:
            self.state.mode = TimeMode.ACCELERATED

        # Set speed multiplier with validation
        speed = runtime_cfg.get("time_acceleration", 1.0)
        if speed <= 0:
            logger.warning(f"Invalid time_acceleration {speed}, using default 1.0")
            speed = 1.0
        elif speed > self._MAX_SPEED_MULTIPLIER:
            logger.warning(
                f"time_acceleration {speed} exceeds maximum {self._MAX_SPEED_MULTIPLIER}, capping"
            )
            speed = self._MAX_SPEED_MULTIPLIER
        self.state.speed_multiplier = speed

        logger.info(
            f"SimulationTime configured: mode={self.state.mode.value}, "
            f"speed={self.state.speed_multiplier}x, "
            f"update_interval={self.state.update_interval}s"
        )

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------
    async def start(self):
        """Start the simulation time system.

        Initialises wall-clock tracking and starts the time loop
        for REALTIME and ACCELERATED modes.
        """
        if self._running:
            logger.warning("SimulationTime already running")
            return

        async with self._lock:
            self.state.wall_time_start = time.time()
            self.state.simulation_time = 0.0
            self.state.wall_time_elapsed = 0.0
            self.state.total_pause_duration = 0.0
            self.state.pause_start = None
            self.state.paused = self.state.mode == TimeMode.PAUSED

        self._running = True

        if self.state.mode in [TimeMode.REALTIME, TimeMode.ACCELERATED]:
            self._update_task = asyncio.create_task(self._time_loop())

        logger.info(f"SimulationTime started in {self.state.mode.value} mode")

    async def stop(self):
        """Stop the simulation time system.

        Cancels the time loop and cleans up resources.
        """
        if not self._running:
            return

        self._running = False
        if self._update_task:
            self._update_task.cancel()
            try:
                await self._update_task
            except asyncio.CancelledError:
                pass
            self._update_task = None

        logger.info("SimulationTime stopped")

    async def reset(self):
        """Reset simulation time to zero.

        Preserves mode and speed settings but resets time counters.
        """
        async with self._lock:
            self.state.simulation_time = 0.0
            self.state.wall_time_start = time.time()
            self.state.wall_time_elapsed = 0.0
            self.state.total_pause_duration = 0.0
            self.state.pause_start = None

        logger.info("SimulationTime reset to zero")

    # ----------------------------------------------------------------
    # Time queries
    # ----------------------------------------------------------------
    def now(self) -> float:
        """Get current simulation time in seconds.

        Returns:
            Current simulation time as a float.
        """
        return self.state.simulation_time

    def delta(self, last_time: float) -> float:
        """Calculate time elapsed since a previous time.

        Args:
            last_time: Previous simulation time to compare against

        Returns:
            Time delta in simulation seconds
        """
        return self.state.simulation_time - last_time

    def elapsed(self) -> float:
        """Get total elapsed simulation time.

        Returns:
            Total simulation time since start/reset
        """
        return self.state.simulation_time

    def wall_elapsed(self) -> float:
        """Get total elapsed wall-clock time.

        Returns:
            Total wall-clock time since start/reset
        """
        return self.state.wall_time_elapsed

    def speed(self) -> float:
        """Get current speed multiplier.

        Returns:
            Current speed multiplier (1.0 = realtime)
        """
        return self.state.speed_multiplier

    def is_paused(self) -> bool:
        """Check if simulation is currently paused.

        Returns:
            True if paused, False otherwise
        """
        return self.state.paused

    # ----------------------------------------------------------------
    # Time control
    # ----------------------------------------------------------------
    async def pause(self):
        """Pause simulation time progression.

        Time stops advancing but the simulation remains in a ready state.
        Can be resumed with resume().
        """
        async with self._lock:
            if self.state.paused:
                logger.warning("SimulationTime already paused")
                return

            self.state.paused = True
            self.state.pause_start = time.time()

        logger.info("SimulationTime paused")

    async def resume(self):
        """Resume simulation time progression after pause.

        Adjusts internal timing to account for pause duration.
        """
        async with self._lock:
            if not self.state.paused:
                logger.warning("SimulationTime not paused")
                return

            self.state.paused = False

            # Track total pause duration
            if self.state.pause_start is not None:
                pause_duration = time.time() - self.state.pause_start
                self.state.total_pause_duration += pause_duration
                self.state.pause_start = None

            # Adjust wall time start to account for pause
            self.state.wall_time_start = time.time() - (
                self.state.simulation_time / self.state.speed_multiplier
            )

        logger.info("SimulationTime resumed")

    async def set_speed(self, multiplier: float):
        """Set simulation speed multiplier.

        Args:
            multiplier: Speed multiplier (1.0 = realtime, 2.0 = 2x faster)

        Raises:
            ValueError: If multiplier is <= 0 or exceeds maximum
        """
        if multiplier <= 0:
            raise ValueError(
                f"Speed multiplier must be > 0, got {multiplier}"
            )

        if multiplier > self._MAX_SPEED_MULTIPLIER:
            raise ValueError(
                f"Speed multiplier {multiplier} exceeds maximum {self._MAX_SPEED_MULTIPLIER}"
            )

        async with self._lock:
            old_speed = self.state.speed_multiplier
            current_sim_time = self.state.simulation_time
            self.state.speed_multiplier = multiplier

            # Adjust wall time start to maintain continuity
            self.state.wall_time_start = time.time() - (
                current_sim_time / multiplier
            )

        logger.info(f"SimulationTime speed changed: {old_speed}x -> {multiplier}x")

    async def step(self, delta_seconds: float):
        """Manually advance simulation time (STEPPED mode).

        Args:
            delta_seconds: Amount of time to advance in seconds

        Raises:
            ValueError: If delta_seconds is negative
            RuntimeError: If not in STEPPED or PAUSED mode
        """
        if delta_seconds < 0:
            raise ValueError(
                f"Cannot step negative time: {delta_seconds}"
            )

        async with self._lock:
            if self.state.mode not in [TimeMode.STEPPED, TimeMode.PAUSED]:
                raise RuntimeError(
                    f"step() only valid in STEPPED or PAUSED mode, "
                    f"current mode is {self.state.mode.value}"
                )

            self.state.simulation_time += delta_seconds
            self.state.wall_time_elapsed = time.time() - self.state.wall_time_start

        logger.debug(f"SimulationTime stepped by {delta_seconds}s to {self.state.simulation_time}s")

    # ----------------------------------------------------------------
    # Internal time loop
    # ----------------------------------------------------------------
    async def _time_loop(self):
        """Internal time progression loop for REALTIME and ACCELERATED modes."""
        last_update = time.time()
        interval = self.state.update_interval

        logger.debug(
            f"Time loop started with {interval}s interval at {self.state.speed_multiplier}x speed"
        )

        while self._running:
            await asyncio.sleep(interval)
            current_time = time.time()

            async with self._lock:
                if self.state.paused:
                    last_update = current_time
                    continue

                wall_delta = current_time - last_update
                last_update = current_time
                sim_delta = wall_delta * self.state.speed_multiplier
                self.state.simulation_time += sim_delta
                self.state.wall_time_elapsed = (
                    current_time - self.state.wall_time_start - self.state.total_pause_duration
                )

    # ----------------------------------------------------------------
    # Status
    # ----------------------------------------------------------------
    async def get_status(self) -> dict:
        """Get comprehensive time system status.

        Returns:
            Dictionary containing current time state and metrics
        """
        async with self._lock:
            return {
                "simulation_time": self.state.simulation_time,
                "wall_time_elapsed": self.state.wall_time_elapsed,
                "mode": self.state.mode.value,
                "speed_multiplier": self.state.speed_multiplier,
                "paused": self.state.paused,
                "total_pause_duration": self.state.total_pause_duration,
                "ratio": (
                    self.state.simulation_time / self.state.wall_time_elapsed
                    if self.state.wall_time_elapsed > 0
                    else 0.0
                ),
            }


# ----------------------------------------------------------------
# Convenience functions
# ----------------------------------------------------------------
async def wait_simulation_time(seconds: float):
    """Wait for a specified duration in simulation time.

    This function is time-mode aware and will wait for the correct
    amount of simulation time regardless of acceleration or pauses.

    Args:
        seconds: Duration to wait in simulation seconds

    Raises:
        ValueError: If seconds is negative

    Example:
        `>>> await wait_simulation_time(10.0)  # Wait 10 sim seconds`
    """
    if seconds < 0:
        raise ValueError(f"Cannot wait negative time: {seconds}")

    if seconds == 0:
        return

    sim_time = SimulationTime()
    target_time = sim_time.now() + seconds

    while sim_time.now() < target_time:
        if sim_time.is_paused():
            # Wait for resume, checking periodically
            while sim_time.is_paused():
                await asyncio.sleep(0.1)
        else:
            # Sleep for update interval or remaining time, whichever is less
            remaining = target_time - sim_time.now()
            speed = sim_time.speed()

            # Calculate appropriate sleep time
            if speed > 0:
                sleep_time = min(
                    sim_time.state.update_interval,
                    remaining / speed
                )
            else:
                sleep_time = sim_time.state.update_interval

            # Ensure minimum sleep to prevent busy-waiting
            await asyncio.sleep(max(0.001, sleep_time))


def get_simulation_delta(last_time: float) -> float:
    """Get time delta since a previous simulation time.

    Args:
        last_time: Previous simulation time to compare against

    Returns:
        Time delta in simulation seconds

    Example:
        >>> start = sim_time.now()
        >>> # ... do work ...
        >>> elapsed = get_simulation_delta(start)
    """
    sim_time = SimulationTime()
    return sim_time.delta(last_time)
