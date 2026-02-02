# components/devices/control_zone/safety/sis_controller.py
"""
Configurable Safety Instrumented System (SIS) Controller.

A flexible SIS controller that can be configured with multiple Safety
Instrumented Functions (SIFs) at runtime. Extends BaseSafetyController
to provide a generic safety system for UU Power & Light Co.

Unlike the dedicated TurbineSafetyPLC and ReactorSafetyPLC, this controller
can monitor multiple process variables from different sources and execute
configurable safety actions.

Use cases at UU P&L:
- Plant-wide emergency shutdown coordination
- Fire and gas detection system
- Area isolation systems
- Supplementary safety monitoring

CRITICAL: SIS must be independent from BPCS (Basic Process Control System).
Per IEC 61511, safety systems should be:
- Independent from control systems
- On separate network segments
- Separate engineering workstation
- Cannot be bypassed remotely without authorisation

Reality at UU P&L: Often shares engineering workstation with BPCS
(the Bursar refused to fund a separate one).

Memory Map (Modbus):
-----------------------------------------------------------------
Discrete Inputs (Read-only booleans):
  0-15: SIF trip status (up to 16 SIFs)
  16: Any SIF tripped
  17: System healthy
  18: Safe state active
  19: Bypass active
  20: Proof test due
  21-23: Reserved

Input Registers (Read-only 16-bit):
  0: Active SIF count
  1: Tripped SIF count
  2: Total demand count
  3: Total fault count
  4: Diagnostic status code
  5-9: Reserved

Coils (Read/write booleans):
  0: Manual trip command (all SIFs)
  1: Trip reset command
  2: Bypass enable (REQUIRES AUTHORISATION)

Holding Registers (Read/write 16-bit):
  0-15: SIF enable flags (bit-packed)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from components.devices.control_zone.safety.base_safety_controller import (
    BaseSafetyController,
    SafetyIntegrityLevel,
    VotingArchitecture,
)
from components.state.data_store import DataStore


class TripAction(Enum):
    """Actions to take when a SIF trips."""

    LOG_ONLY = "log_only"  # Log the event but don't trigger safe state
    ALARM = "alarm"  # Raise alarm but don't trip
    TRIP = "trip"  # Trigger safe state
    SCRAM = "scram"  # Emergency shutdown (highest priority)


@dataclass
class SafetyInstrumentedFunction:
    """
    Configuration for a single Safety Instrumented Function (SIF).

    A SIF monitors a specific process condition and takes action
    when the condition exceeds safe limits.
    """

    name: str
    description: str
    sil_level: SafetyIntegrityLevel
    trip_action: TripAction = TripAction.TRIP

    # Trip condition (evaluated each scan)
    # Returns True if trip condition is met
    condition_func: Callable[[], bool] | None = None

    # Optional: Direct value monitoring
    data_source: str | None = None  # DataStore path for value
    trip_high: float | None = None  # Trip if value > trip_high
    trip_low: float | None = None  # Trip if value < trip_low

    # Runtime state
    enabled: bool = True
    tripped: bool = False
    trip_count: int = 0
    last_trip_time: float = 0.0
    last_value: float = 0.0

    # Optional callback when SIF trips
    on_trip_callback: Callable[[], None] | None = field(default=None, repr=False)


class SISController(BaseSafetyController):
    """
    Configurable Safety Instrumented System controller.

    A flexible SIS that supports multiple configurable Safety Instrumented
    Functions (SIFs). Can monitor values from DataStore or use custom
    condition functions.

    Example:
        >>> sis = SISController(
        ...     device_name="plant_sis",
        ...     device_id=50,
        ...     data_store=data_store,
        ...     sil_level=SafetyIntegrityLevel.SIL2,
        ... )
        ...
        >>> # Add SIF with direct value monitoring
        >>> sis.add_sif(
        ...     name="high_temp",
        ...     description="Reactor high temperature protection",
        ...     sil_level=SafetyIntegrityLevel.SIL2,
        ...     data_source="reactor_plc/input_registers[0]",
        ...     trip_high=450.0,
        ... )
        ...
        >>> # Add SIF with custom condition
        >>> sis.add_sif(
        ...     name="pressure_rate",
        ...     description="Rapid pressure rise protection",
        ...     sil_level=SafetyIntegrityLevel.SIL3,
        ...     condition_func=lambda: pressure_rate > 10.0,
        ... )
        ...
        >>> await sis.start()
    """

    MAX_SIFS = 16  # Maximum number of SIFs supported

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        sil_level: SafetyIntegrityLevel = SafetyIntegrityLevel.SIL2,
        voting: VotingArchitecture = VotingArchitecture.ONE_OUT_OF_ONE,
        description: str = "Safety Instrumented System Controller",
        scan_interval: float = 0.05,  # 50ms default for safety
        independent_from: list[str] | None = None,
    ):
        """
        Initialise SIS controller.

        Args:
            device_name: Unique SIS identifier
            device_id: Controller address
            data_store: Reference to DataStore
            sil_level: Overall SIL level for this SIS
            voting: Voting architecture (typically 1oo1 for software SIS)
            description: Controller description
            scan_interval: Safety logic scan time in seconds
            independent_from: List of devices this SIS is independent from
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            sil_level=sil_level,
            voting=voting,
            description=description,
            scan_interval=scan_interval,
        )

        # Safety Instrumented Functions
        self._sifs: dict[str, SafetyInstrumentedFunction] = {}

        # Independence declaration (for documentation/auditing)
        self.independent_from = independent_from or []

        # Architectural properties (realistic weaknesses)
        self.shared_engineering_workstation = True  # Common at UU P&L
        self.shared_network = False  # Should be separate
        self.uses_same_historian = True  # Bursar's cost-cutting

        # Cached values for diagnostics
        self._last_diagnostic_status = 0

        self.logger.info(
            f"SISController '{device_name}' created "
            f"(SIL: {sil_level.name}, independent from: {self.independent_from})"
        )

    @property
    def sifs(self) -> dict[str, SafetyInstrumentedFunction]:
        """Read-only access to configured SIFs."""
        return self._sifs

    # ----------------------------------------------------------------
    # SIF Management
    # ----------------------------------------------------------------

    def add_sif(
        self,
        name: str,
        description: str,
        sil_level: SafetyIntegrityLevel,
        trip_action: TripAction = TripAction.TRIP,
        condition_func: Callable[[], bool] | None = None,
        data_source: str | None = None,
        trip_high: float | None = None,
        trip_low: float | None = None,
        on_trip_callback: Callable[[], None] | None = None,
        enabled: bool = True,
    ) -> bool:
        """
        Add a Safety Instrumented Function to this SIS.

        Args:
            name: Unique SIF identifier
            description: Human-readable description
            sil_level: SIL level for this specific SIF
            trip_action: Action to take when tripped
            condition_func: Custom function returning True if trip condition met
            data_source: DataStore path for value monitoring
            trip_high: Trip if monitored value exceeds this
            trip_low: Trip if monitored value falls below this
            on_trip_callback: Optional callback when SIF trips
            enabled: Whether SIF is initially enabled

        Returns:
            True if SIF added successfully, False if limit reached or name exists
        """
        if len(self._sifs) >= self.MAX_SIFS:
            self.logger.error(
                f"Cannot add SIF '{name}': Maximum {self.MAX_SIFS} SIFs reached"
            )
            return False

        if name in self._sifs:
            self.logger.error(f"Cannot add SIF '{name}': Name already exists")
            return False

        # Validate: must have either condition_func or data_source with limits
        if condition_func is None and data_source is None:
            self.logger.error(
                f"Cannot add SIF '{name}': Must specify condition_func or data_source"
            )
            return False

        if data_source is not None and trip_high is None and trip_low is None:
            self.logger.error(
                f"Cannot add SIF '{name}': data_source requires trip_high or trip_low"
            )
            return False

        sif = SafetyInstrumentedFunction(
            name=name,
            description=description,
            sil_level=sil_level,
            trip_action=trip_action,
            condition_func=condition_func,
            data_source=data_source,
            trip_high=trip_high,
            trip_low=trip_low,
            on_trip_callback=on_trip_callback,
            enabled=enabled,
        )

        self._sifs[name] = sif
        self.logger.info(
            f"SIF '{name}' added to '{self.device_name}' "
            f"(SIL: {sil_level.name}, action: {trip_action.value})"
        )
        return True

    def remove_sif(self, name: str) -> bool:
        """Remove a SIF by name."""
        if name in self._sifs:
            del self._sifs[name]
            self.logger.info(f"SIF '{name}' removed from '{self.device_name}'")
            return True
        return False

    def enable_sif(self, name: str, enabled: bool = True) -> bool:
        """Enable or disable a specific SIF."""
        if name in self._sifs:
            self._sifs[name].enabled = enabled
            self.logger.info(f"SIF '{name}' {'enabled' if enabled else 'disabled'}")
            return True
        return False

    def get_sif(self, name: str) -> SafetyInstrumentedFunction | None:
        """Get a SIF by name."""
        return self._sifs.get(name)

    def get_all_sifs(self) -> dict[str, SafetyInstrumentedFunction]:
        """Get all configured SIFs."""
        return self._sifs.copy()

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return device type."""
        return "sis_controller"

    def _supported_protocols(self) -> list[str]:
        """Supported protocols."""
        return ["modbus", "profisafe"]

    async def _initialise_memory_map(self) -> None:
        """Initialise Modbus memory map."""
        # Discrete inputs (SIF trip status)
        for i in range(self.MAX_SIFS):
            self.memory_map[f"discrete_inputs[{i}]"] = False

        self.memory_map["discrete_inputs[16]"] = False  # Any SIF tripped
        self.memory_map["discrete_inputs[17]"] = True  # System healthy
        self.memory_map["discrete_inputs[18]"] = False  # Safe state active
        self.memory_map["discrete_inputs[19]"] = False  # Bypass active
        self.memory_map["discrete_inputs[20]"] = False  # Proof test due

        # Input registers
        self.memory_map["input_registers[0]"] = 0  # Active SIF count
        self.memory_map["input_registers[1]"] = 0  # Tripped SIF count
        self.memory_map["input_registers[2]"] = 0  # Total demand count
        self.memory_map["input_registers[3]"] = 0  # Total fault count
        self.memory_map["input_registers[4]"] = 0  # Diagnostic status

        # Coils
        self.memory_map["coils[0]"] = False  # Manual trip
        self.memory_map["coils[1]"] = False  # Trip reset
        self.memory_map["coils[2]"] = False  # Bypass enable

        # Holding registers (SIF enable flags, bit-packed)
        self.memory_map["holding_registers[0]"] = 0xFFFF  # All enabled by default

        self.logger.debug(f"SISController '{self.device_name}' memory map initialised")

    # ----------------------------------------------------------------
    # BaseSafetyController implementation
    # ----------------------------------------------------------------

    async def _read_safety_inputs(self) -> None:
        """
        Read safety inputs for all configured SIFs.

        For SIFs with data_source, reads the value from DataStore.
        """
        for sif in self._sifs.values():
            if not sif.enabled:
                continue

            if sif.data_source:
                try:
                    # Parse data source path (device/address format)
                    if "/" in sif.data_source:
                        device, address = sif.data_source.split("/", 1)
                        value = await self.data_store.read_memory(device, address)
                        if value is not None:
                            sif.last_value = float(value)
                except Exception as e:
                    self.logger.warning(
                        f"Failed to read data source for SIF '{sif.name}': {e}"
                    )

    async def _execute_safety_logic(self) -> bool:
        """
        Execute all Safety Instrumented Functions.

        Returns:
            True if any SIF demands a trip action
        """
        safety_demand = False
        tripped_count = 0
        active_count = 0

        # Check SIF enable flags from holding registers
        enable_flags = self.memory_map.get("holding_registers[0]", 0xFFFF)

        for i, (name, sif) in enumerate(self._sifs.items()):
            # Check if enabled via register
            sif_enabled_by_register = bool(enable_flags & (1 << i))
            sif.enabled = sif.enabled and sif_enabled_by_register

            if not sif.enabled:
                continue

            active_count += 1
            trip_condition = False

            # Evaluate trip condition
            if sif.condition_func is not None:
                try:
                    trip_condition = sif.condition_func()
                except Exception as e:
                    self.logger.error(f"Error evaluating SIF '{name}' condition: {e}")

            elif sif.data_source is not None:
                # Check against high/low limits
                if sif.trip_high is not None and sif.last_value > sif.trip_high:
                    trip_condition = True
                if sif.trip_low is not None and sif.last_value < sif.trip_low:
                    trip_condition = True

            # Handle trip condition
            if trip_condition and not sif.tripped:
                sif.tripped = True
                sif.trip_count += 1
                sif.last_trip_time = self.sim_time.now()
                tripped_count += 1

                self.logger.warning(
                    f"SIS '{self.device_name}': SIF '{name}' TRIPPED "
                    f"(action: {sif.trip_action.value}, count: {sif.trip_count})"
                )

                # Execute callback if defined
                if sif.on_trip_callback:
                    try:
                        sif.on_trip_callback()
                    except Exception as e:
                        self.logger.error(f"SIF '{name}' callback error: {e}")

                # Determine if this demands a safety action
                if sif.trip_action in (TripAction.TRIP, TripAction.SCRAM):
                    safety_demand = True

            elif sif.tripped:
                tripped_count += 1

            # Update discrete input for this SIF
            if i < self.MAX_SIFS:
                self.memory_map[f"discrete_inputs[{i}]"] = sif.tripped

        # Update summary registers
        self.memory_map["input_registers[0]"] = active_count
        self.memory_map["input_registers[1]"] = tripped_count
        self.memory_map["discrete_inputs[16]"] = tripped_count > 0

        # Check manual trip command
        manual_trip = self.memory_map.get("coils[0]", False)
        if manual_trip:
            self.logger.warning(f"SIS '{self.device_name}': Manual trip commanded")
            safety_demand = True

        # Check bypass
        if self.bypass_active and safety_demand:
            self.logger.critical(
                f"SIS '{self.device_name}': BYPASS ACTIVE - Trip ignored!"
            )
            safety_demand = False

        return safety_demand

    async def _write_safety_outputs(self) -> None:
        """Update status outputs and handle reset."""
        # Update status registers
        self.memory_map["discrete_inputs[17]"] = not self.diagnostic_fault
        self.memory_map["discrete_inputs[18]"] = self.safe_state_active
        self.memory_map["discrete_inputs[19]"] = self.bypass_active
        self.memory_map["discrete_inputs[20]"] = self.is_proof_test_due()
        self.memory_map["input_registers[2]"] = self.demand_count
        self.memory_map["input_registers[3]"] = self.fault_count
        self.memory_map["input_registers[4]"] = self._last_diagnostic_status

        # Handle trip reset command
        trip_reset = self.memory_map.get("coils[1]", False)
        if trip_reset and self.safe_state_active:
            if await self.reset_from_safe_state():
                # Reset all SIF trip states
                for sif in self._sifs.values():
                    sif.tripped = False
                self.memory_map["coils[0]"] = False
                self.memory_map["coils[1]"] = False
                self.logger.info(f"SIS '{self.device_name}': All SIFs reset")

    async def _run_diagnostics(self) -> None:
        """Run self-diagnostics."""
        # Check for configuration issues
        if len(self._sifs) == 0:
            self.logger.warning(f"SIS '{self.device_name}': No SIFs configured")
            self._last_diagnostic_status = 1
            # Don't fault - just warn
            return

        # Check for enabled SIFs with no valid condition
        for name, sif in self._sifs.items():
            if sif.enabled and sif.condition_func is None and sif.data_source is None:
                self.logger.error(f"SIF '{name}' has no valid condition source")
                self._last_diagnostic_status = 2
                self.diagnostic_fault = True
                return

        # All OK
        self._last_diagnostic_status = 0
        self.diagnostic_fault = False

    async def _force_safe_state(self) -> None:
        """Force all systems to safe state."""
        self.safe_state_active = True

        # Mark all SIFs as tripped
        for sif in self._sifs.values():
            if not sif.tripped:
                sif.tripped = True
                sif.trip_count += 1
                sif.last_trip_time = self.sim_time.now()

                # Execute callbacks
                if sif.on_trip_callback:
                    try:
                        sif.on_trip_callback()
                    except Exception as e:
                        self.logger.error(f"SIF '{sif.name}' callback error: {e}")

        self.logger.critical(
            f"SIS '{self.device_name}': FORCING SAFE STATE - All SIFs tripped"
        )

    # ----------------------------------------------------------------
    # Status and telemetry
    # ----------------------------------------------------------------

    async def get_safety_status(self) -> dict[str, Any]:
        """Get comprehensive SIS status."""
        base_status = await super().get_safety_status()

        sif_status = {}
        for name, sif in self._sifs.items():
            sif_status[name] = {
                "description": sif.description,
                "sil_level": sif.sil_level.name,
                "trip_action": sif.trip_action.value,
                "enabled": sif.enabled,
                "tripped": sif.tripped,
                "trip_count": sif.trip_count,
                "last_trip_time": sif.last_trip_time,
                "last_value": sif.last_value if sif.data_source else None,
            }

        return {
            **base_status,
            "sif_count": len(self._sifs),
            "sifs": sif_status,
            "architecture": {
                "independent_from": self.independent_from,
                "shared_engineering_workstation": self.shared_engineering_workstation,
                "shared_network": self.shared_network,
                "uses_same_historian": self.uses_same_historian,
            },
        }

    async def get_telemetry(self) -> dict[str, Any]:
        """Get telemetry data for SCADA/HMI."""
        return {
            "device_name": self.device_name,
            "device_type": "sis_controller",
            "sil_level": self.sil_level.name,
            "safe_state_active": self.safe_state_active,
            "bypass_active": self.bypass_active,
            "diagnostic_fault": self.diagnostic_fault,
            "sif_count": len(self._sifs),
            "tripped_count": sum(1 for s in self._sifs.values() if s.tripped),
            "demand_count": self.demand_count,
        }
