# components/devices/control_zone/plc/generic/base_plc.py
"""
Protocol-agnostic base class for all PLC devices.

Extends BaseDevice with PLC-specific functionality:
- Standard PLC scan cycle (read inputs → execute logic → write outputs)
- Control logic orchestration

This class does NOT define any specific memory structure (Modbus registers, S7 DBs, AB tags).
Subclasses define their own memory structures appropriate to their protocol.
"""

from abc import abstractmethod

from components.devices.core.base_device import BaseDevice
from components.state.data_store import DataStore


class BasePLC(BaseDevice):
    """
    Protocol-agnostic base class for all PLCs.

    PLCs are field controllers that:
    1. Read inputs from physical processes
    2. Execute control logic
    3. Write outputs to physical processes

    This base class provides the PLC scan cycle pattern without assuming
    any specific protocol memory structure. Subclasses implement their
    memory layout for Modbus, S7, Allen-Bradley, etc.

    Subclasses must implement:
    - _initialise_memory_map(): Define protocol-specific memory structure
    - _read_inputs(): Read from physics engines/sensors
    - _execute_logic(): Run control algorithms
    - _write_outputs(): Write to physics engines/actuators
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        description: str = "",
        scan_interval: float = 0.1,  # 100ms typical PLC scan rate
    ):
        """
        Initialise PLC device.

        Args:
            device_name: Unique PLC identifier
            device_id: Protocol-specific ID (Modbus unit, S7 slot, CIP instance, etc.)
            data_store: Reference to DataStore
            description: PLC description
            scan_interval: Scan cycle time in seconds
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
        )

        # Note: BaseDevice already tracks scan_count, error_count, last_scan_time
        # in metadata dictionary. No need to duplicate here.

        self.logger.info(f"BasePLC '{device_name}' initialised")

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return 'plc' as base type (override for specific types like 'turbine_plc')."""
        return "plc"

    async def _scan_cycle(self) -> None:
        """
        Execute standard PLC scan cycle.

        Order of operations (standard across all PLC types):
        1. Read inputs from process/physics
        2. Execute control logic
        3. Write outputs to process/physics

        Note: BaseDevice._scan_loop() already handles:
        - Incrementing scan_count
        - Updating last_scan_time
        - Incrementing error_count on exceptions
        - Writing memory_map to DataStore
        """
        # Standard PLC scan cycle
        await self._read_inputs()
        await self._execute_logic()
        await self._write_outputs()

        # BaseDevice handles all diagnostic updates automatically
        # No need to update counters here

    # ----------------------------------------------------------------
    # Abstract methods for PLC scan cycle - must be implemented
    # ----------------------------------------------------------------

    @abstractmethod
    async def _read_inputs(self) -> None:
        """
        Read inputs from process.

        Typically:
        - Read telemetry from physics engines via DataStore
        - Update input memory areas (discrete inputs, input registers, etc.)
        """
        pass

    @abstractmethod
    async def _execute_logic(self) -> None:
        """
        Execute PLC control logic.

        Typically:
        - Read from input memory
        - Apply control algorithms (PID, ladder logic, etc.)
        - Update output memory (coils, holding registers, etc.)
        """
        pass

    @abstractmethod
    async def _write_outputs(self) -> None:
        """
        Write outputs to process.

        Typically:
        - Read from output memory areas
        - Write control commands to physics engines via DataStore
        """
        pass
