# components/devices/control_zone/safety/base_safety_controller.py
"""
Base class for Safety Instrumented Systems (SIS) controllers.

Safety controllers are specialised devices for safety-critical functions:
- Safety Integrity Level (SIL) rated
- Redundant architectures (1oo2, 2oo3, etc.)
- Fail-safe operation
- Continuous diagnostics
- Independence from basic process control

Safety controllers differ from standard PLCs:
- Certified design and runtime
- Proven-in-use safety functions
- Diagnostic coverage requirements
- Forced logic evaluation
"""

import logging
from abc import abstractmethod
from enum import Enum
from typing import Any

from components.devices.core.base_device import BaseDevice

logger = logging.getLogger(__name__)


class SafetyIntegrityLevel(Enum):
    """Safety Integrity Levels per IEC 61508."""

    SIL1 = 1  # 10^-2 to 10^-1 probability of failure on demand
    SIL2 = 2  # 10^-3 to 10^-2
    SIL3 = 3  # 10^-4 to 10^-3
    SIL4 = 4  # 10^-5 to 10^-4


class VotingArchitecture(Enum):
    """Redundancy voting architectures."""

    ONE_OUT_OF_ONE = "1oo1"  # No redundancy
    ONE_OUT_OF_TWO = "1oo2"  # 1 of 2 must trip
    TWO_OUT_OF_TWO = "2oo2"  # Both must trip
    TWO_OUT_OF_THREE = "2oo3"  # 2 of 3 must trip
    TWO_OUT_OF_FOUR = "2oo4"  # 2 of 4 must trip


class BaseSafetyController(BaseDevice):
    """
    Base class for safety instrumented system controllers.

    Safety controllers implement Safety Instrumented Functions (SIFs) such as:
    - Emergency shutdown (ESD)
    - High integrity pressure protection (HIPPS)
    - Fire and gas detection
    - Burner management

    Key features:
    - Redundant processing
    - Continuous self-diagnostics
    - Fail-safe defaults
    - Proof test tracking
    - Safety state logic

    Subclasses must implement:
    - _initialise_memory_map(): Define safety I/O and logic
    - _read_safety_inputs(): Read from redundant sensors
    - _execute_safety_logic(): Evaluate safety conditions
    - _write_safety_outputs(): Drive final elements to safe state
    - _run_diagnostics(): Continuous system health checks
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: Any,
        sil_level: SafetyIntegrityLevel = SafetyIntegrityLevel.SIL2,
        voting: VotingArchitecture = VotingArchitecture.TWO_OUT_OF_THREE,
        description: str = "",
        scan_interval: float = 0.05,  # Safety controllers scan faster (50ms)
    ):
        """
        Initialise safety controller.

        Args:
            device_name: Unique safety controller identifier
            device_id: Controller address
            data_store: Reference to DataStore
            sil_level: Required Safety Integrity Level
            voting: Redundancy voting architecture
            description: Controller description
            scan_interval: Safety logic scan time in seconds
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
        )

        self.sil_level = sil_level
        self.voting = voting

        # Safety controller state
        self.safe_state_active = False  # System in safe state (tripped)
        self.diagnostic_fault = False  # Diagnostic failure detected
        self.bypass_active = (
            False  # Safety function bypassed (requires # authorisation)
        )

        # Diagnostics and testing
        self.diagnostic_count = 0
        self.fault_count = 0
        self.last_proof_test = 0.0
        self.proof_test_interval = 8760.0  # Hours (1 year default)

        # Safety logic metrics
        self.demand_count = 0  # Number of times safety function demanded
        self.spurious_trip_count = 0

        logger.info(
            f"BaseSafetyController '{device_name}' initialised "
            f"(SIL: {sil_level.name}, voting: {voting.value})"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return 'safety_controller' as base type."""
        return "safety_controller"

    def _supported_protocols(self) -> list[str]:
        """Safety controllers often use Modbus, Profibus, or proprietary protocols."""
        return ["modbus"]  # Override in subclass for specific protocols

    async def _scan_cycle(self) -> None:
        """
        Execute safety controller scan cycle.

        Order of operations (safety-critical):
        1. Run diagnostics FIRST (fail-safe if fault detected)
        2. Read safety inputs (with redundancy voting)
        3. Execute safety logic
        4. Write safety outputs (force safe state if needed)
        5. Update diagnostic status
        """
        try:
            # 1. Diagnostics first - fail-safe if fault
            await self._run_diagnostics()
            if self.diagnostic_fault:
                logger.warning(
                    f"Safety controller '{self.device_name}': Diagnostic fault - "
                    f"forcing safe state"
                )
                self.safe_state_active = True
                await self._force_safe_state()
                return

            # 2. Read safety inputs
            await self._read_safety_inputs()

            # 3. Execute safety logic
            safety_demand = await self._execute_safety_logic()

            # Track safety demands and activate safe state
            if safety_demand and not self.safe_state_active:
                self.demand_count += 1
                self.safe_state_active = True
                logger.warning(
                    f"Safety controller '{self.device_name}': Safety demand #{self.demand_count} - "
                    f"activating safe state"
                )

            # 4. Write safety outputs
            await self._write_safety_outputs()

            # 5. Update diagnostics
            self.diagnostic_count += 1
            self._update_diagnostics()

        except Exception as e:
            # ANY exception in safety logic forces safe state
            logger.critical(
                f"CRITICAL: Exception in safety controller '{self.device_name}': {e}",
                exc_info=True,
            )
            self.fault_count += 1
            self.safe_state_active = True
            await self._force_safe_state()

    # ----------------------------------------------------------------
    # Abstract methods for safety logic - must be implemented
    # ----------------------------------------------------------------

    @abstractmethod
    async def _read_safety_inputs(self) -> None:
        """
        Read safety-critical inputs.

        Must implement redundancy voting (1oo2, 2oo3, etc.)
        Should detect sensor faults and discrepancies
        """
        pass

    @abstractmethod
    async def _execute_safety_logic(self) -> bool:
        """
        Execute safety instrumented functions.

        Returns:
            True if safety action demanded, False otherwise
        """
        pass

    @abstractmethod
    async def _write_safety_outputs(self) -> None:
        """
        Write safety outputs to final elements.

        Must de-energise to safe state (fail-safe design)
        """
        pass

    @abstractmethod
    async def _run_diagnostics(self) -> None:
        """
        Run continuous self-diagnostics.

        Should check:
        - CPU health
        - Memory integrity
        - I/O module status
        - Communication health
        - Power supply status

        Sets self.diagnostic_fault if issues detected
        """
        pass

    @abstractmethod
    async def _force_safe_state(self) -> None:
        """
        Force system to safe state.

        Called on:
        - Diagnostic fault
        - Safety logic exception
        - Manual safety trip
        """
        pass

    # ----------------------------------------------------------------
    # Safety controller operations
    # ----------------------------------------------------------------

    async def reset_from_safe_state(self) -> bool:
        """
        Reset from safe state (requires conditions to be safe).

        Returns:
            True if reset successful, False if conditions not met
        """
        if self.diagnostic_fault:
            logger.error(f"Cannot reset '{self.device_name}': Diagnostic fault active")
            return False

        if self.bypass_active:
            logger.warning(
                f"Resetting '{self.device_name}' with bypass active - "
                f"safety function bypassed!"
            )

        self.safe_state_active = False
        logger.info(f"Safety controller '{self.device_name}' reset from safe state")
        return True

    async def activate_bypass(self, authorization: str) -> bool:
        """
        Activate safety function bypass (requires authorisation).

        Args:
            authorization: Session ID or username for authorisation

        Returns:
            True if bypass activated, False if unauthorised
        """
        # Verify authorisation through security system
        try:
            from components.security.authentication import (
                PermissionType,
                verify_authorization,
            )

            authorized = await verify_authorization(
                authorization,
                PermissionType.SAFETY_BYPASS,
                resource=self.device_name,
            )

            if not authorized:
                logger.error(
                    f"UNAUTHORIZED safety bypass attempt on '{self.device_name}' - "
                    f"Authorization denied"
                )
                return False

            self.bypass_active = True
            logger.warning(
                f"SAFETY BYPASS ACTIVATED on '{self.device_name}' - "
                f"Authorization: {authorization}"
            )
            return True

        except ImportError:
            # Fallback if authentication module not available
            logger.warning(
                f"Authentication module not available - "
                f"allowing bypass on '{self.device_name}' (INSECURE)"
            )
            self.bypass_active = True
            return True

    async def deactivate_bypass(self) -> None:
        """Deactivate safety function bypass."""
        self.bypass_active = False
        logger.info(f"Safety bypass deactivated on '{self.device_name}'")

    async def record_proof_test(self) -> None:
        """Record that proof test was performed."""
        self.last_proof_test = self.sim_time.now()
        logger.info(
            f"Proof test recorded for '{self.device_name}' at "
            f"sim time {self.last_proof_test}"
        )

    def is_proof_test_due(self) -> bool:
        """Check if proof test is due."""
        time_since_test = self.sim_time.now() - self.last_proof_test
        # Convert hours to seconds for comparison
        return time_since_test > (self.proof_test_interval * 3600)

    # ----------------------------------------------------------------
    # Safety diagnostics
    # ----------------------------------------------------------------

    def _update_diagnostics(self) -> None:
        """Update diagnostic values in memory map."""
        self.memory_map["_safe_state_active"] = self.safe_state_active
        self.memory_map["_diagnostic_fault"] = self.diagnostic_fault
        self.memory_map["_bypass_active"] = self.bypass_active
        self.memory_map["_diagnostic_count"] = self.diagnostic_count
        self.memory_map["_fault_count"] = self.fault_count
        self.memory_map["_demand_count"] = self.demand_count
        self.memory_map["_proof_test_due"] = self.is_proof_test_due()

    async def get_safety_status(self) -> dict[str, Any]:
        """Get safety controller status."""
        base_status = await self.get_status()
        safety_status = {
            **base_status,
            "sil_level": self.sil_level.name,
            "voting_architecture": self.voting.value,
            "safe_state_active": self.safe_state_active,
            "diagnostic_fault": self.diagnostic_fault,
            "bypass_active": self.bypass_active,
            "diagnostic_count": self.diagnostic_count,
            "fault_count": self.fault_count,
            "demand_count": self.demand_count,
            "spurious_trip_count": self.spurious_trip_count,
            "proof_test_due": self.is_proof_test_due(),
            "time_since_proof_test_hours": (
                (self.sim_time.now() - self.last_proof_test) / 3600
            ),
        }
        return safety_status
