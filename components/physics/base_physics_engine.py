# components/physics/base_physics_engine.py
"""
Base classes for physics simulation engines.

Provides common infrastructure for:
- Initialization and lifecycle management
- SimulationTime integration
- DataStore integration
- Control input/output patterns
- State access interface

All physics engines should inherit from either BasePhysicsEngine (system-wide)
or BaseDevicePhysicsEngine (device-specific).
"""

from abc import ABC, abstractmethod
from typing import Any

from components.security.logging_system import ICSLogger, get_logger
from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime

__all__ = ["BasePhysicsEngine", "BaseDevicePhysicsEngine"]


class BasePhysicsEngine(ABC):
    """
    Abstract base class for all physics simulation engines.

    Provides common infrastructure for system-wide physics engines
    (e.g., GridPhysics, PowerFlow).

    Subclasses must implement:
    - initialise(): Set up initial state
    - update(dt): Update physics for one timestep
    - get_state(): Return current state object
    - get_telemetry(): Return telemetry dictionary
    """

    def __init__(
        self,
        data_store: DataStore,
        params: Any | None = None,
    ):
        """Initialise base physics engine.

        Args:
            data_store: DataStore for reading/writing simulation state
            params: Engine-specific parameters (typed in subclass)
        """
        self.data_store = data_store
        self.params = params
        self.sim_time = SimulationTime()

        # Lifecycle tracking
        self._initialised = False
        self._last_update_time = 0.0

        # Logger (subclass can override device name)
        self.logger: ICSLogger = get_logger(self.__class__.__name__)

    # ----------------------------------------------------------------
    # Lifecycle (abstract)
    # ----------------------------------------------------------------

    @abstractmethod
    async def initialise(self) -> None:
        """Initialize physics engine and set initial state.

        Must set self._initialised = True when complete.
        Should set self._last_update_time = self.sim_time.now()

        Raises:
            RuntimeError: If initialization fails
        """
        pass

    # ----------------------------------------------------------------
    # Physics update (abstract)
    # ----------------------------------------------------------------

    def _validate_update(self, dt: float) -> bool:
        """Validate update parameters before running physics.

        Args:
            dt: Time delta in seconds

        Returns:
            True if update should proceed, False if should skip

        Raises:
            RuntimeError: If engine not initialized
        """
        if not self._initialised:
            raise RuntimeError(
                f"{self.__class__.__name__} not initialised. Call initialise() first."
            )

        if dt <= 0:
            self.logger.warning(
                f"Invalid time delta {dt} for {self.__class__.__name__}, skipping update"
            )
            return False

        return True

    @abstractmethod
    def update(self, dt: float) -> None:
        """Update physics state for one simulation timestep.

        Subclasses must call self._validate_update(dt) first and return early if False.

        Args:
            dt: Time delta in seconds

        Raises:
            RuntimeError: If engine not initialized
        """
        # Subclass implements actual physics
        pass

    # ----------------------------------------------------------------
    # State access (abstract)
    # ----------------------------------------------------------------

    @abstractmethod
    def get_state(self) -> Any:
        """Get current physics state object.

        Returns:
            Engine-specific state object (typed in subclass)
        """
        pass

    @abstractmethod
    def get_telemetry(self) -> dict[str, Any]:
        """Get current telemetry in dictionary format.

        Returns:
            Dictionary of telemetry values for monitoring/logging
        """
        pass

    # ----------------------------------------------------------------
    # Status
    # ----------------------------------------------------------------

    def is_initialised(self) -> bool:
        """Check if engine has been initialised.

        Returns:
            True if initialise() has been called successfully
        """
        return self._initialised


class BaseDevicePhysicsEngine(BasePhysicsEngine):
    """
    Base class for device-specific physics engines.

    Extends BasePhysicsEngine with device-specific patterns:
    - Device name tracking
    - Control input caching
    - Memory map read/write

    Used for engines that simulate individual devices
    (e.g., TurbinePhysics, ReactorPhysics, HVACPhysics).
    """

    def __init__(
        self,
        device_name: str,
        data_store: DataStore,
        params: Any | None = None,
    ):
        """Initialise device-specific physics engine.

        Args:
            device_name: Name of device being simulated
            data_store: DataStore for reading/writing device state
            params: Engine-specific parameters (typed in subclass)
        """
        super().__init__(data_store, params)
        self.device_name = device_name

        # Control input cache (populated by read_control_inputs)
        self._control_cache: dict[str, Any] = {}

        # Override logger with device name
        self.logger = get_logger(self.__class__.__name__, device=device_name)

    # ----------------------------------------------------------------
    # Device lifecycle (with common patterns)
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialize device physics engine.

        Validates device exists in DataStore, writes initial telemetry,
        and sets initialisation flag.

        Subclasses should:
        1. Call super().initialise()
        2. Initialize engine-specific state
        3. Optionally call write_telemetry()

        Raises:
            RuntimeError: If device not found in DataStore
        """
        # Validate device exists
        device = await self.data_store.get_device_state(self.device_name)
        if not device:
            raise RuntimeError(
                f"Cannot initialise {self.__class__.__name__}: "
                f"device '{self.device_name}' not found in DataStore"
            )

        self._last_update_time = self.sim_time.now()
        self._initialised = True

        self.logger.info(
            f"{self.__class__.__name__} initialised for device '{self.device_name}'"
        )

    # ----------------------------------------------------------------
    # Control input/output (abstract, with helpers)
    # ----------------------------------------------------------------

    async def read_control_inputs(self) -> None:
        """Read control inputs from device memory map.

        Caches values in self._control_cache for use during update().
        This allows async I/O to happen before synchronous physics update.

        Subclasses should implement this to read device-specific inputs.
        Use _cache_control_input() helper to read and cache values.
        """
        pass

    async def write_telemetry(self) -> None:
        """Write current physics state to device memory map.

        Subclasses should implement this to write device-specific telemetry.
        """
        pass

    # ----------------------------------------------------------------
    # Control cache helpers
    # ----------------------------------------------------------------

    async def _cache_control_input(
        self,
        address: str,
        default: Any,
    ) -> None:
        """Read control input from DataStore and cache it.

        Args:
            address: Memory map address to read
            default: Default value if read fails
        """
        try:
            value = await self.data_store.read_memory(self.device_name, address)
            if value is not None:
                self._control_cache[address] = value
            else:
                self._control_cache[address] = default
        except Exception as e:
            self.logger.warning(
                f"Failed to read control input '{address}': {e}, using default"
            )
            self._control_cache[address] = default

    def _read_control_input(self, address: str, default: Any) -> Any:
        """Get cached control input value.

        Args:
            address: Memory map address
            default: Default value if not cached

        Returns:
            Cached value or default
        """
        return self._control_cache.get(address, default)
