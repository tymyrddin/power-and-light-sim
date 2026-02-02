# components/devices/control_zone/specialty/lspace_monitor.py
"""
L-Space Dimensional Stability Monitor

Monitors magical dimensional stability in the Library's Special Collections.
L-space (Library-space) is where all libraries are connected through magical dimensions.

Based on Schneider Modicon with custom thaumic field sensors (circa 1987).
"""

import random

from components.devices.control_zone.plc.generic.base_plc import BasePLC
from components.state.data_store import DataStore


class LSpaceMonitor(BasePLC):
    """
    L-Space dimensional stability monitoring controller.

    Monitors thaumic field strength, dimensional stability, and narrative causality
    to prevent uncontrolled L-space incursions in the Library.

    This prevents books from spontaneously appearing/disappearing and stops
    librarians from accidentally traversing into other dimensions.

    Memory Map (Modbus):
        Input Registers:
            0: Thaumic field strength (0-100%)
            1: Dimensional stability (0-100%)
            2: L-space penetration depth (meters)
            3: Octarine radiation (millithaumics)
            4: Narrative causality index (0-100)

        Discrete Inputs:
            0: L-space link active
            1: Dimensional boundary stable
            2: Thaumic field nominal
            3: Octarine alarm
            4: Narrative cascade warning

        Holding Registers:
            0: Thaumic damping setpoint (0-100%)
            1: Stability threshold (0-100%)

        Coils:
            0: Enable thaumic damping
            1: Emergency dimensional seal
    """

    DEFAULT_SETUP = {
        "input_registers": {
            0: 45,   # Thaumic field strength
            1: 95,   # Dimensional stability
            2: 5,    # L-space penetration
            3: 12,   # Octarine radiation
            4: 50,   # Narrative causality
        },
        "discrete_inputs": {
            0: True,   # L-space link active
            1: True,   # Boundary stable
            2: True,   # Field nominal
            3: False,  # Octarine alarm
            4: False,  # Narrative cascade
        },
        "holding_registers": {
            0: 60,   # Damping setpoint
            1: 80,   # Stability threshold
        },
        "coils": {
            0: True,   # Damping enabled
            1: False,  # Emergency seal
        },
    }

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        description: str = "L-Space Dimensional Stability Monitor",
        scan_interval: float = 2.0,
    ):
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
        )

        self.logger.info(
            f"LSpaceMonitor '{device_name}' initialised (monitoring dimensional stability)"
        )

    def _device_type(self) -> str:
        return "specialty_controller"

    def _supported_protocols(self) -> list[str]:
        return ["modbus"]

    async def _initialise_memory_map(self) -> None:
        """Initialise L-space monitoring memory map."""
        # Input registers (telemetry)
        self.memory_map["input_registers[0]"] = 45   # Thaumic field
        self.memory_map["input_registers[1]"] = 95   # Stability
        self.memory_map["input_registers[2]"] = 5    # Penetration
        self.memory_map["input_registers[3]"] = 12   # Octarine radiation
        self.memory_map["input_registers[4]"] = 50   # Narrative causality

        # Discrete inputs (status)
        self.memory_map["discrete_inputs[0]"] = True   # Link active
        self.memory_map["discrete_inputs[1]"] = True   # Boundary stable
        self.memory_map["discrete_inputs[2]"] = True   # Field nominal
        self.memory_map["discrete_inputs[3]"] = False  # Octarine alarm
        self.memory_map["discrete_inputs[4]"] = False  # Narrative cascade

        # Holding registers (parameters)
        self.memory_map["holding_registers[0]"] = 60  # Damping setpoint
        self.memory_map["holding_registers[1]"] = 80  # Stability threshold

        # Coils (commands)
        self.memory_map["coils[0]"] = True   # Damping enabled
        self.memory_map["coils[1]"] = False  # Emergency seal

        self.logger.debug(f"LSpaceMonitor '{self.device_name}' memory map initialised")

    async def _read_inputs(self) -> None:
        """
        Read thaumic field sensor inputs.

        Simulates sensor readings with natural variations.
        """
        # Simulate thaumic field variations (slow drift)
        current_field = self.memory_map.get("input_registers[0]", 45)
        field_drift = random.uniform(-2, 2)
        new_field = max(0, min(100, current_field + field_drift))
        self.memory_map["input_registers[0]"] = int(new_field)

        # L-space penetration depth (correlated with field strength)
        penetration = max(0, min(20, 10 - int(new_field / 10)))
        self.memory_map["input_registers[2]"] = penetration

        # Octarine radiation readings
        octarine = self.memory_map.get("input_registers[3]", 12)
        octarine_drift = random.uniform(-1, 1)
        self.memory_map["input_registers[3]"] = max(0, min(50, int(octarine + octarine_drift)))

        # Narrative causality index (mostly stable)
        narrative = self.memory_map.get("input_registers[4]", 50)
        self.memory_map["input_registers[4]"] = max(0, min(100, int(narrative + random.uniform(-0.5, 0.5))))

        # Update status inputs
        self.memory_map["discrete_inputs[2]"] = 30 <= new_field <= 70  # Field nominal

    async def _execute_logic(self) -> None:
        """
        Execute L-space stability control logic.

        Implements thaumic damping control and dimensional stability monitoring.
        """
        # Read control parameters
        damping_enabled = self.memory_map.get("coils[0]", True)
        emergency_seal = self.memory_map.get("coils[1]", False)
        stability_threshold = self.memory_map.get("holding_registers[1]", 80)

        # Dimensional stability calculation (affected by damping)
        current_stability = self.memory_map.get("input_registers[1]", 95)
        if damping_enabled:
            stability_change = random.uniform(-1, 2)  # Damping helps
        else:
            stability_change = random.uniform(-3, 1)  # Less stable

        new_stability = max(0, min(100, current_stability + stability_change))
        self.memory_map["input_registers[1]"] = int(new_stability)

        # Update status based on stability
        self.memory_map["discrete_inputs[1]"] = new_stability >= stability_threshold  # Boundary stable

        # Emergency seal overrides
        if emergency_seal:
            self.memory_map["input_registers[1]"] = 100  # Force stability
            self.memory_map["discrete_inputs[1]"] = True
            self.memory_map["discrete_inputs[3]"] = False  # Clear octarine alarm
            self.memory_map["discrete_inputs[4]"] = False  # Clear narrative cascade

        # Alarm conditions
        field_strength = self.memory_map.get("input_registers[0]", 45)
        octarine = self.memory_map.get("input_registers[3]", 12)
        self.memory_map["discrete_inputs[3]"] = octarine > 30  # Octarine alarm
        self.memory_map["discrete_inputs[4]"] = new_stability < 50  # Narrative cascade warning

        # Rare temporal anomalies (1% chance)
        if random.random() < 0.01:
            self.logger.warning(
                f"LSpaceMonitor '{self.device_name}': Temporal anomaly detected!"
            )

    async def _write_outputs(self) -> None:
        """
        Write control outputs.

        L-space monitor is primarily a monitoring device with no physical outputs,
        but emergency seal can trigger library-wide alarms via DataStore.
        """
        emergency_seal = self.memory_map.get("coils[1]", False)

        if emergency_seal:
            # In a full implementation, this would write to DataStore to trigger
            # library-wide dimensional lockdown procedures
            self.logger.info(
                f"LSpaceMonitor '{self.device_name}': Emergency dimensional seal activated!"
            )
