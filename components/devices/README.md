# Device Classes

This directory contains device classes that bridge physics engines with protocol interfaces. These devices expose physics simulation state as protocol memory maps (Modbus registers, IEC 104 information objects, etc.) and implement realistic PLC/RTU scan cycle logic.

## Overview

In an ICS simulator, there are three critical layers:

1. **Physics layer** - Models physical processes (turbines spinning, grid frequency, power flow)
2. **Device layer** - PLCs, RTUs, SCADA servers that interface with physics
3. **Protocol layer** - Modbus, IEC 104, DNP3, OPC UA communication

The **device classes** in this directory form the middle layer, reading telemetry from physics engines via DataStore and exposing it through protocol memory maps.

```
┌─────────────────────────────────────────────────────────────┐
│                   Protocol Layer                            │
│  (Modbus, IEC 104, DNP3 - network-accessible interfaces)   │
└──────────────────────┬──────────────────────────────────────┘
                       │ read/write
                       │ memory maps
┌──────────────────────▼──────────────────────────────────────┐
│                   Device Layer                              │
│  TurbinePLC, SubstationPLC, RTU, SCADA                     │
│  - Scan cycle logic                                         │
│  - Memory map exposure (registers, coils, I/O)             │
│  - Control application to physics                           │
└──────────────────────┬──────────────────────────────────────┘
                       │ read/write
                       │ via DataStore
┌──────────────────────▼──────────────────────────────────────┐
│                   Physics Layer                             │
│  TurbinePhysics, GridPhysics, PowerFlow                    │
│  - Physical process simulation                              │
│  - Realistic dynamics and time constants                    │
└─────────────────────────────────────────────────────────────┘
```

## Device Classes

### `turbine_plc.py` - Turbine PLC

Complete implementation of a turbine control PLC that bridges TurbinePhysics with Modbus protocol interfaces.

**Features:**
- Integrates with `TurbinePhysics` engine
- Modbus memory map (holding registers, coils)
- Configurable scan rate (default 10 Hz)
- Realistic PLC scan cycle logic
- Alarm generation (overspeed, high vibration, high temperature, damage)
- Control inputs (speed setpoint, governor enable, emergency trip)

**Memory Map:**

*Holding Registers (telemetry - read-only):*
- `0` - Shaft speed (RPM)
- `1` - Steam temperature (°F)
- `2` - Steam pressure (PSI)
- `3` - Bearing temperature (°F)
- `4` - Vibration (mils × 10)
- `5` - Power output (MW)
- `6` - Cumulative overspeed time (seconds)
- `7` - Damage level (%)

*Holding Registers (control - read-write):*
- `10` - Speed setpoint (RPM)

*Coils (status - read-only):*
- `0` - Running status
- `1` - Overspeed alarm
- `2` - High vibration alarm
- `3` - High bearing temperature alarm
- `4` - Severe damage alarm

*Coils (control - read-write):*
- `10` - Governor enabled
- `11` - Emergency trip

**Example Usage:**
```python
from devices.turbine_plc import TurbinePLC, TurbineParameters

# Create turbine PLC
turbine_plc = TurbinePLC(
    device_name="turbine_plc_1",
    data_store=data_store,
    turbine_params=TurbineParameters(
        rated_speed_rpm=3600,
        rated_power_mw=100.0,
        max_safe_speed_rpm=3960
    ),
    scan_rate_hz=10.0
)

# Initialise and start
await turbine_plc.initialise()
await turbine_plc.start()

# Read telemetry
speed = turbine_plc.get_holding_register(0)  # Shaft speed
running = turbine_plc.get_coil(0)  # Running status

# Write controls (simulating SCADA or attacker)
turbine_plc.set_holding_register(10, 3600)  # Set speed setpoint
turbine_plc.set_coil(10, True)  # Enable governor

# Get comprehensive telemetry
telemetry = await turbine_plc.get_telemetry()
```

**Attack Scenarios:**

*Overspeed Attack:*
```python
# Attacker writes excessive speed setpoint
turbine_plc.set_holding_register(10, 4500)  # 125% rated speed
turbine_plc.set_coil(10, True)  # Enable governor

# Physics will:
# - Accelerate turbine to 4500 RPM
# - Trigger overspeed alarm at 3960 RPM
# - Accumulate damage at 1.5%/second
# - Show increasing vibration
# - Risk catastrophic failure at 50% damage
```

*Emergency Trip Bypass:*
```python
# Attacker prevents safety shutdown
turbine_plc.set_coil(11, False)  # Ensure trip is NOT active

# Even if overspeed detected, turbine won't trip
# Damage continues accumulating
```

### `substation_plc.py` - Substation PLC

Substation controller supporting both Modbus and IEC 104 protocols.

**Features:**
- Dual protocol support (Modbus TCP + IEC 104)
- Breaker control and status
- Voltage and current measurements
- Relay protection simulation
- IEC 104 information objects

**Memory Map (Modbus):**

*Holding Registers:*
- `0-2` - Phase voltages (V)
- `3-5` - Phase currents (A)
- `6` - Frequency (Hz × 100)
- `7` - Active power (kW)
- `8` - Reactive power (kVAR)

*Coils:*
- `0` - Breaker status (0=open, 1=closed)
- `1` - Breaker command (write to operate)
- `10-14` - Protection relay trip flags

**IEC 104 Information Objects:**

- **Single-point information** (M_SP_NA_1, IOA 100-199):
  - Breaker positions
  - Protection relay statuses
  - Alarm states

- **Measured value, normalised** (M_ME_NA_1, IOA 200-299):
  - Voltages
  - Currents
  - Power flows

- **Single command** (C_SC_NA_1, IOA 1000-1099):
  - Breaker control
  - Relay resets

**Example Usage:**
```python
from devices.substation_plc import SubstationPLC

substation = SubstationPLC(
    device_name="substation_plc_1",
    data_store=data_store,
    common_address=1,  # IEC 104 ASDU address
    scan_rate_hz=10.0
)

await substation.initialise()
await substation.start()

# Read measurements via Modbus
voltage_a = substation.get_holding_register(0)
current_a = substation.get_holding_register(3)

# Control breaker via IEC 104
await substation.send_command(1001, True)  # Close breaker
```

### `rtu_modbus.py` - Modbus RTU

Generic Modbus RTU (Remote Terminal Unit) for field device simulation.

**Features:**
- Flexible memory map configuration
- Custom update callbacks
- Serial and TCP modes
- Protocol timing simulation

**Example Usage:**
```python
from devices.rtu_modbus import RTUModbus, ModbusRegisterMap

# Create RTU with custom register map
rtu = RTUModbus(
    device_name="field_rtu_1",
    data_store=data_store,
    register_map=ModbusRegisterMap(
        holding_registers_count=50,
        coils_count=20
    )
)

# Define custom update logic
async def update_field_sensors(rtu, dt):
    # Simulate temperature sensor
    import random
    temp = 20 + random.gauss(0, 2)  # 20°C ± 2°C
    rtu.set_input_register(0, int(temp * 10))
    
    # Simulate flow sensor
    flow = 100 + random.gauss(0, 5)  # 100 L/min ± 5
    rtu.set_input_register(1, int(flow))

rtu.set_update_callback(update_field_sensors)

await rtu.initialise()
await rtu.start()
```

### `rtu_c104.py` - IEC 60870-5-104 RTU

Remote Terminal Unit with IEC 104 protocol support.

**Features:**
- IEC 104 information objects
- Time synchronisation
- Spontaneous and cyclic data transmission
- Quality descriptors

**Information Object Types:**
- M_SP_NA_1 - Single-point information
- M_DP_NA_1 - Double-point information
- M_ME_NA_1 - Measured value, normalised
- M_ME_NB_1 - Measured value, scaled
- C_SC_NA_1 - Single command
- C_DC_NA_1 - Double command

**Example Usage:**
```python
from devices.rtu_c104 import RTUC104

rtu = RTUC104(
    device_name="remote_station_1",
    data_store=data_store,
    common_address=10,
    scan_rate_hz=1.0  # 1 Hz for SCADA polling
)

# Configure information objects
rtu.add_single_point(100, "breaker_status")
rtu.add_measured_value(200, "line_current", scale=100.0)

await rtu.initialise()
await rtu.start()

# Update values (typically from physics)
rtu.update_single_point(100, True)  # Breaker closed
rtu.update_measured_value(200, 523.7)  # 523.7 A
```

### `scada_server.py` - SCADA Master

SCADA master station that polls field devices and aggregates data.

**Features:**
- Multi-protocol polling (Modbus, IEC 104, DNP3)
- Tag database
- Historical data logging
- Alarm management
- HMI data provision

**Example Usage:**
```python
from devices.scada_server import SCADAServer

scada = SCADAServer(
    device_name="scada_master_1",
    data_store=data_store
)

# Configure polled devices
scada.add_poll_target(
    device_name="turbine_plc_1",
    protocol="modbus",
    poll_rate_s=1.0,
    tags=[
        ("turbine_1_speed", "holding_register", 0),
        ("turbine_1_power", "holding_register", 5),
    ]
)

await scada.initialise()
await scada.start()

# Read aggregated data
speed = await scada.get_tag_value("turbine_1_speed")
power = await scada.get_tag_value("turbine_1_power")
```

### `ied.py` - Intelligent Electronic Device

Protection relay / IED with IEC 61850 support.

**Features:**
- IEC 61850 GOOSE messaging
- IEC 61850 MMS reporting
- Protection function simulation
- Trip logic

**Example Usage:**
```python
from devices.ied import IED

ied = IED(
    device_name="protection_relay_1",
    data_store=data_store,
    ied_name="BAY1_PROT",
    goose_enabled=True
)

# Configure protection functions
ied.add_overcurrent_protection(
    pickup_current=1200,  # 1200 A pickup
    time_delay=0.5  # 500ms time delay
)

await ied.initialise()
await ied.start()

# IED monitors current and trips if >1200A for >500ms
# Sends GOOSE message on trip
```

## Device Architecture

### Scan Cycle Pattern

All devices follow a consistent scan cycle pattern:

```python
async def _scan_cycle(self):
    """Main device scan cycle."""
    while self._running:
        current_time = self.sim_time.now()
        dt = current_time - self._last_scan_time
        
        try:
            # 1. Read control inputs from DataStore
            await self._read_control_inputs()
            
            # 2. Apply controls to physics (if applicable)
            self._apply_controls_to_physics()
            
            # 3. Read telemetry from physics
            self._read_telemetry_from_physics()
            
            # 4. Update alarms and status
            self._update_alarms()
            
            # 5. Write memory map to DataStore
            await self._sync_memory_to_datastore()
            
        except Exception as e:
            logger.error(f"Scan cycle error: {e}")
        
        self._last_scan_time = current_time
        await asyncio.sleep(self.scan_interval)
```

### Memory Map Pattern

Devices expose Modbus-style memory maps:

```python
# Memory map storage
self.holding_registers: dict[int, int] = {}  # 16-bit registers
self.coils: dict[int, bool] = {}  # Boolean outputs
self.input_registers: dict[int, int] = {}  # 16-bit inputs
self.discrete_inputs: dict[int, bool] = {}  # Boolean inputs

# Memory map definition (metadata)
self.memory_map_def = MemoryMapDefinition(
    holding_registers=[
        RegisterDefinition(
            address=0,
            name="shaft_speed_rpm",
            data_type="uint16",
            access="ro",
            description="Shaft speed",
            unit="RPM"
        ),
        # ...
    ]
)
```

### Integration with DataStore

Devices use DataStore for all state persistence:

```python
# Register device on initialisation
await self.data_store.register_device(
    device_name=self.device_name,
    device_type="turbine_plc",
    device_id=1,
    protocols=["modbus"],
    metadata={...}
)

# Read control inputs (written by protocol adapters)
speed_setpoint = await self.data_store.read_memory(
    self.device_name, "speed_setpoint_rpm"
)

# Write telemetry (read by protocol adapters)
await self.data_store.write_memory(
    self.device_name, "shaft_speed_rpm", 3600
)

# Bulk write entire memory map
await self.data_store.bulk_write_memory(
    self.device_name, memory_map
)
```

### Integration with Physics

Devices that control physics create their own physics engine instances:

```python
# TurbinePLC owns TurbinePhysics
self.physics = TurbinePhysics(params=self.turbine_params)
await self.physics.start()

# Each scan cycle:
# 1. Read controls from memory map
speed_setpoint = self.holding_registers.get(10, 0)

# 2. Apply to physics
self.physics.set_speed_setpoint(float(speed_setpoint))

# 3. Read physics telemetry
telemetry = self.physics.get_telemetry()

# 4. Update memory map
self.holding_registers[0] = int(telemetry["shaft_speed_rpm"])
```

## Creating Custom Devices

To create a custom device:

1. **Inherit from base class** (or create standalone):
```python
class CustomPLC:
    def __init__(self, device_name, data_store, ...):
        self.device_name = device_name
        self.data_store = data_store
        self.sim_time = SimulationTime()
        # ...
```

2. **Define memory map**:
```python
self.memory_map_def = MemoryMapDefinition(
    holding_registers=[...],
    coils=[...]
)
```

3. **Implement scan cycle**:
```python
async def _scan_cycle(self):
    while self._running:
        # Custom logic here
        await asyncio.sleep(self.scan_interval)
```

4. **Integrate with physics** (if needed):
```python
self.physics = CustomPhysics(...)
# In scan cycle:
telemetry = self.physics.get_telemetry()
self.holding_registers[0] = telemetry["value"]
```

## Protocol Integration

Devices expose memory maps that protocol adapters access via DataStore:

```python
# Protocol adapter reads device memory
# (e.g., Modbus adapter handling read holding registers request)
device_memory = await data_store.bulk_read_memory("turbine_plc_1")
shaft_speed = device_memory["shaft_speed_rpm"]

# Protocol adapter writes device memory
# (e.g., Modbus adapter handling write register request)
await data_store.write_memory("turbine_plc_1", "speed_setpoint_rpm", 3600)
```

The device scan cycle picks up these writes and applies them to physics.

## Testing Devices

### Unit Testing

Test device logic in isolation:

```python
async def test_turbine_plc_scan_cycle():
    # Create mocks
    mock_data_store = MockDataStore()
    
    # Create device
    turbine_plc = TurbinePLC("test_turbine", mock_data_store)
    await turbine_plc.initialise()
    await turbine_plc.start()
    
    # Set control input
    turbine_plc.set_holding_register(10, 3600)
    turbine_plc.set_coil(10, True)
    
    # Wait for scan cycles
    await asyncio.sleep(0.5)
    
    # Verify physics responded
    speed = turbine_plc.get_holding_register(0)
    assert speed > 0  # Turbine accelerating
    
    await turbine_plc.stop()
```

### Integration Testing

Test device with protocol adapters:

```python
async def test_turbine_plc_modbus_integration():
    # Create real infrastructure
    system_state = SystemState()
    data_store = DataStore(system_state)
    
    # Create device
    turbine_plc = TurbinePLC("turbine_plc_1", data_store)
    await turbine_plc.initialise()
    await turbine_plc.start()
    
    # Create Modbus adapter
    modbus_adapter = ModbusAdapter("turbine_plc_1", data_store)
    await modbus_adapter.start()
    
    # Send Modbus command
    response = await modbus_adapter.write_holding_register(10, 3600)
    
    # Verify device responded
    await asyncio.sleep(0.5)
    speed = await modbus_adapter.read_holding_register(0)
    assert speed > 0
```

## Performance Considerations

### Scan Rate Selection

Choose scan rates based on process dynamics:

- **Fast processes** (turbine control): 10-50 Hz
- **Medium processes** (substation monitoring): 1-10 Hz  
- **Slow processes** (SCADA polling): 0.1-1 Hz

```python
# Fast turbine control
turbine_plc = TurbinePLC(..., scan_rate_hz=10.0)

# Slow SCADA polling
scada = SCADAServer(..., scan_rate_hz=0.5)
```

### Memory Map Size

Keep memory maps reasonably sized:

- Holding registers: 100-1000 typically sufficient
- Coils: 100-500 for most applications
- Larger maps possible but consider protocol limitations

### DataStore access patterns

Minimise DataStore round-trips:

```python
# Bad: Multiple individual writes
for i, value in enumerate(values):
    await data_store.write_memory(device_name, f"reg_{i}", value)

# Good: Single bulk write
memory_map = {f"reg_{i}": value for i, value in enumerate(values)}
await data_store.bulk_write_memory(device_name, memory_map)
```

## Common Patterns

### Alarm generation

```python
def _update_alarms(self):
    """Calculate alarms from telemetry."""
    shaft_speed = self.holding_registers.get(0, 0)
    overspeed_limit = self.params.max_safe_speed_rpm
    
    # Overspeed alarm
    self.coils[1] = shaft_speed > overspeed_limit
    
    # High vibration
    vibration = self.holding_registers.get(4, 0) / 10.0
    self.coils[2] = vibration > self.params.vibration_critical_mils
```

### Control application

```python
def _apply_controls_to_physics(self):
    """Apply memory map controls to physics engine."""
    # Read from memory map (written by protocols)
    speed_setpoint = self.holding_registers.get(10, 0)
    governor_enabled = self.coils.get(10, False)
    
    # Apply to physics
    self.physics.set_speed_setpoint(float(speed_setpoint))
    self.physics.set_governor_enabled(governor_enabled)
```

### Telemetry mapping

```python
def _read_telemetry_from_physics(self):
    """Map physics telemetry to memory map."""
    telemetry = self.physics.get_telemetry()
    
    # Map to registers with appropriate scaling
    self.holding_registers[0] = int(telemetry["shaft_speed_rpm"])
    self.holding_registers[4] = int(telemetry["vibration_mils"] * 10)
```

## Troubleshooting

### Issue: Device not updating

**Symptom:** Memory map values stay at zero/false

**Solution:**
```python
# Verify device started
await device.start()

# Check scan cycle is running
assert device._running
assert device._scan_task is not None

# Verify physics engine started (if applicable)
assert device.physics._running
```

### Issue: Protocol can't read device

**Symptom:** Protocol adapter gets None when reading device memory

**Solution:**
```python
# Verify device registered with DataStore
device_state = await data_store.get_device_state("device_name")
assert device_state is not None

# Verify device writing to DataStore
memory_map = await data_store.bulk_read_memory("device_name")
assert memory_map is not None
```

### Issue: Controls not affecting physics

**Symptom:** Writing control registers has no effect on telemetry

**Solution:**
```python
# Verify control registers are writable
reg_def = device.memory_map_def.holding_registers[10]
assert reg_def.access == "rw"

# Verify _apply_controls_to_physics() is called in scan cycle
# Check logs for errors in scan cycle
```

## Future Enhancements

Potential improvements:

- Base device class for common patterns
- Protocol-agnostic memory map abstraction
- Built-in historian integration
- Automatic alarm logging
- OPC UA integration
- DNP3 support
- IEC 61850 GOOSE/MMS
- Device templates for common equipment types

## References

- IEC 60870-5-104: Telecontrol equipment and systems
- Modbus Application Protocol Specification V1.1b3
- IEC 61850: Power system communication
- DNP3 specification
- PLC scan cycle theory
- SCADA system architecture

---

*"The PLCs don't debate philosophy. They read sensors, run logic, write outputs. Every scan cycle, like clockwork. Miss a scan and you might miss the turbine overspeeding. The physics don't wait for your code to catch up."*