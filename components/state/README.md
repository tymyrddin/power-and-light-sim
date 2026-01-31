# State Management

This directory contains the centralised state management system for the UU Power & Light ICS simulator. Because keeping track of dozens of turbines, substations, alchemical reactors, and their interconnected states is exactly the kind of problem that led to the Bursar's current condition, we have a proper state management system.

## Overview

Industrial control systems maintain state across hundreds or thousands of data points: valve positions, temperature readings, pump speeds, alarm conditions, and at UU P&L, the occasional metaphysical anomaly. This state must be tracked accurately, updated atomically, and queried efficiently, especially when something is going wrong and you need to know *right now* whether the reactor containment field is holding.

The state management system provides:

- **Centralised state tracking** - Single source of truth for all device states
- **Atomic operations** - Thread-safe updates with asyncio locks
- **Efficient queries** - Find devices by type, protocol, or status
- **Memory maps** - Protocol-agnostic register/coil/tag storage
- **Metadata tracking** - Store arbitrary device information
- **Status reporting** - Real-time simulation health monitoring
- **Time integration** - Uses SimulationTime for accurate temporal tracking

## Architecture

### Core Components

**`SystemState`** - Central state manager
- Maintains registry of all devices in the simulation
- Tracks overall simulation state (running, uptime, cycles)
- Provides atomic state updates with async locks
- Generates summary statistics
- Integrates with SimulationTime for temporal tracking

**`DeviceState`** - Per-device state snapshot
- Device identification (name, type, ID)
- Protocol capabilities
- Online/offline status
- Memory map (register/coil values)
- Metadata (physical properties, configuration)
- Last update timestamp

**`DataStore`** - Async data access interface
- High-level API for reading/writing device data
- Memory map operations (single and bulk)
- Metadata management
- Device queries and filtering
- Input validation and logging

**`SimulationState`** - Overall simulation status
- Start time and uptime tracking
- Running state
- Total devices and online count
- Update cycle counter

## The State Hierarchy

```
SystemState (singleton authority)
├── SimulationState (global simulation status)
│   ├── Uses SimulationTime for temporal tracking
│   └── Tracks update cycles and device counts
├── DeviceState: turbine_plc_1
│   ├── device_type: "turbine_plc"
│   ├── protocols: ["modbus"]
│   ├── online: True
│   ├── memory_map:
│   │   ├── "holding_registers[0]": 3600  (RPM)
│   │   ├── "holding_registers[1]": 450   (Temperature °C)
│   │   └── "coils[0]": True              (Running status)
│   └── metadata:
│       ├── "location": "Turbine Hall A"
│       └── "turbine_capacity_mw": 50
├── DeviceState: substation_plc_1
│   └── ...
└── DeviceState: scada_server_1
    └── ...
```

## Usage

### Device Registration

When devices start up, they register with the state system:

```python
from components.state.system_state import SystemState
from components.state.data_store import DataStore

# Initialise state management
system_state = SystemState()
data_store = DataStore(system_state)

# Register the Hex Steam Turbine PLC
await data_store.register_device(
    device_name="turbine_plc_1",
    device_type="turbine_plc",
    device_id=1,
    protocols=["modbus"],
    metadata={
        "location": "Turbine Hall A",
        "manufacturer": "Allen-Bradley",
        "model": "ControlLogix",
        "install_date": "1998-03-15",
        "turbine_capacity_mw": 50,
        "scan_cycle_ms": 100
    }
)
```

### Memory Map Operations

Industrial protocols work with memory maps—registers, coils, tags. The state system provides protocol-agnostic storage:

```python
# Write turbine RPM to holding register 0
await data_store.write_memory(
    device_name="turbine_plc_1",
    address="holding_registers[0]",
    value=3600  # Target RPM
)

# Read current temperature from holding register 1
temp = await data_store.read_memory(
    device_name="turbine_plc_1",
    address="holding_registers[1]"
)

# Bulk update multiple registers
await data_store.bulk_write_memory(
    device_name="turbine_plc_1",
    values={
        "holding_registers[0]": 3600,  # RPM
        "holding_registers[1]": 450,   # Temperature
        "holding_registers[2]": 95,    # Pressure
        "coils[0]": True,              # Running
        "coils[1]": False,             # Fault condition
    }
)

# Read entire memory map
memory = await data_store.bulk_read_memory("turbine_plc_1")
```

### Device State Updates

Update device online status and metadata:

```python
# Mark device as online
await data_store.set_device_online("turbine_plc_1", True)

# Check if device is online
is_online = await data_store.is_device_online("turbine_plc_1")

# Update metadata (e.g., after maintenance)
await data_store.update_metadata(
    device_name="turbine_plc_1",
    metadata={
        "last_maintenance": "2025-01-15",
        "next_maintenance_due": "2025-04-15"
    }
)
```

### Querying Device State

Find devices by various criteria:

```python
# Get specific device state
turbine = await data_store.get_device_state("turbine_plc_1")
if turbine:
    print(f"Turbine online: {turbine.online}")
    print(f"Location: {turbine.metadata['location']}")

# Get all turbine PLCs
turbines = await data_store.get_devices_by_type("turbine_plc")
for turbine in turbines:
    rpm = turbine.memory_map.get("holding_registers[0]", 0)
    print(f"{turbine.device_name}: {rpm} RPM")

# Get all devices using Modbus
modbus_devices = await data_store.get_devices_by_protocol("modbus")
print(f"Found {len(modbus_devices)} Modbus devices")

# Get all device states
all_devices = await data_store.get_all_device_states()
for name, device in all_devices.items():
    status = "online" if device.online else "offline"
    print(f"{name}: {status}")
```

### Simulation Status

Monitor overall simulation health:

```python
# Get high-level summary
summary = await data_store.get_simulation_state()
print(summary)
# {
#     "simulation": {
#         "running": True,
#         "started_at": "2025-01-26T10:30:00",
#         "uptime_seconds": 3600,
#         "simulation_time": 3600.0,  # From SimulationTime
#         "update_cycles": 36000
#     },
#     "devices": {
#         "total": 12,
#         "online": 11,
#         "offline": 1
#     },
#     "device_types": {
#         "turbine_plc": 3,
#         "substation_plc": 4,
#         "scada_server": 2,
#         "rtu_c104": 3
#     },
#     "protocols": {
#         "modbus": 8,
#         "iec104": 5,
#         "opcua": 2
#     }
# }

# Check simulation state
sim_state = await system_state.get_simulation_state()
print(f"Running: {sim_state.running}")
print(f"Devices online: {sim_state.devices_online}/{sim_state.total_devices}")

# Increment update cycle counter (called by main simulation loop)
await data_store.increment_update_cycle()
```

## Real-World Examples

### Hex Steam Turbine Control System

The turbine PLCs maintain extensive state:

```python
# Turbine PLC memory map structure
turbine_memory = {
    # Holding registers (analogue values)
    "holding_registers[0]": 3600,    # Current RPM
    "holding_registers[1]": 450,     # Steam temperature (°C)
    "holding_registers[2]": 95,      # Steam pressure (bar)
    "holding_registers[3]": 75,      # Bearing temperature (°C)
    "holding_registers[4]": 0.5,     # Vibration (mm/s)
    "holding_registers[5]": 48500,   # Power output (kW)
    
    # Coils (digital values)
    "coils[0]": True,   # Running status
    "coils[1]": False,  # Emergency stop activated
    "coils[2]": False,  # Overspeed condition
    "coils[3]": True,   # Steam valve open
    "coils[4]": False,  # High vibration alarm
    "coils[5]": True,   # Cooling system active
}

await data_store.bulk_write_memory("turbine_plc_1", turbine_memory)

# Metadata tracks physical properties
turbine_metadata = {
    "location": "Turbine Hall A",
    "manufacturer": "Allen-Bradley",
    "model": "ControlLogix 5000",
    "firmware_version": "v16.0",
    "install_date": "1998-03-15",
    "turbine_capacity_mw": 50,
    "rated_rpm": 3600,
    "max_rpm": 3960,  # 110% overspeed trip
    "scan_cycle_ms": 100,
    "last_maintenance": "2025-01-10",
    "maintenance_interval_days": 90
}

await data_store.update_metadata("turbine_plc_1", turbine_metadata)
```

### City-Wide distribution SCADA

The SCADA server aggregates state from multiple RTUs:

```python
# SCADA tracks aggregated grid state
scada_state = {
    "holding_registers[0]": 11500,   # Total grid load (MW)
    "holding_registers[1]": 12000,   # Total generation (MW)
    "holding_registers[2]": 50,      # Grid frequency (Hz)
    "holding_registers[3]": 132000,  # Primary voltage (V)
    "holding_registers[4]": 97,      # Power factor (%)
}

await data_store.bulk_write_memory("scada_server_1", scada_state)

# Query all RTUs to check substation status
rtus = await data_store.get_devices_by_type("rtu_c104")
for rtu in rtus:
    breaker_status = rtu.memory_map.get("coils[0]", False)
    voltage = rtu.memory_map.get("holding_registers[0]", 0)
    location = rtu.metadata.get("location", "Unknown")
    
    status = "CLOSED" if breaker_status else "OPEN"
    print(f"{location}: Breaker {status}, Voltage {voltage}V")
```

### Bursar's Alchemical Reactor Controls

Safety-critical systems track both physical and metaphysical state:

```python
# Reactor state (handle with care)
reactor_state = {
    # Physical measurements
    "holding_registers[0]": 850,     # Core temperature (°C)
    "holding_registers[1]": 45,      # Pressure (bar)
    "holding_registers[2]": 0.2,     # Vibration (mm/s)
    
    # Magical measurements (non-standard but necessary)
    "holding_registers[10]": 7.5,    # Thaumic flux (milliThaums)
    "holding_registers[11]": 0.3,    # L-space proximity (normalised)
    "holding_registers[12]": 12,     # Bursar anxiety level (0-20 scale)
    
    # Safety system status
    "coils[0]": True,    # Containment field active
    "coils[1]": False,   # Emergency scram triggered
    "coils[2]": True,    # Cooling system operational
    "coils[3]": False,   # Dimensional instability detected
    "coils[4]": True,    # Librarian approval granted
}

await data_store.bulk_write_memory("reactor_sis_1", reactor_state)

# Metadata includes safety ratings
reactor_metadata = {
    "location": "Sub-basement 7",
    "safety_integrity_level": "SIL-3",
    "hazard_classification": "High (with metaphysical complications)",
    "emergency_contact": "The Librarian (ook)",
    "last_safety_test": "2025-01-20",
    "approved_by_bursar": True,  # On a good day
    "emergency_shutdown_procedure": "Run. Fast.",
}

await data_store.update_metadata("reactor_sis_1", reactor_metadata)
```

## State consistency

### Atomic updates

All state modifications are protected by async locks:

```python
# This is atomic - no partial updates
async with system_state._lock:
    device.memory_map = new_memory_map
    device.online = True
    device.last_update = datetime.now()
```

Multiple concurrent requests won't corrupt state.

### Memory map patterns

Memory maps use string keys following protocol conventions:

**Modbus pattern:**
```python
{
    "holding_registers[0]": value,
    "holding_registers[1]": value,
    "input_registers[0]": value,
    "coils[0]": True/False,
    "discrete_inputs[0]": True/False,
}
```

**OPC UA pattern:**
```python
{
    "ns=2;s=Temperature": 450.5,
    "ns=2;s=Pressure": 95.0,
    "ns=2;s=Running": True,
}
```

**IEC 104 pattern:**
```python
{
    "M_SP_NA_1:100": True,      # Single point (on/off)
    "M_ME_NC_1:200": 3600.0,    # Measured value (float)
}
```

The `DataStore` validates addresses against these patterns and logs warnings for non-standard formats.

## Integration with other components

### SimulationTime integration

`SystemState` integrates with the `SimulationTime` singleton for accurate temporal tracking:

```python
from components.time.simulation_time import SimulationTime

class SystemState:
    def __init__(self):
        self._sim_time = SimulationTime()
    
    async def get_summary(self):
        return {
            "simulation": {
                "simulation_time": self._sim_time.now(),  # Uses SimulationTime
                # ... other fields
            }
        }
```

This ensures simulation time (which can be accelerated, stepped, or paused) is accurately reflected in state summaries.

### Physics engines

Physics engines update state based on physical models:

```python
class TurbinePhysics:
    async def update(self, delta_time):
        # Calculate new RPM based on physics
        new_rpm = self.calculate_rpm(delta_time)
        
        # Update state
        await self.data_store.write_memory(
            self.device_name,
            "holding_registers[0]",
            new_rpm
        )
```

### Protocol adapters

Protocol servers read/write state when clients connect:

```python
class ModbusServer:
    async def read_holding_registers(self, address, count):
        # Read from state system
        memory = await self.data_store.bulk_read_memory(self.device_name)
        
        values = []
        for i in range(count):
            key = f"holding_registers[{address + i}]"
            values.append(memory.get(key, 0))
        
        return values
    
    async def write_holding_register(self, address, value):
        # Write to state system
        await self.data_store.write_memory(
            self.device_name,
            f"holding_registers[{address}]",
            value
        )
```

### Monitoring systems

IDS and SIEM systems query state for anomalies:

```python
class AnomalyDetector:
    async def check_for_anomalies(self):
        # Get all turbines
        turbines = await self.data_store.get_devices_by_type("turbine_plc")
        
        for turbine in turbines:
            rpm = turbine.memory_map.get("holding_registers[0]", 0)
            max_rpm = turbine.metadata.get("max_rpm", 3960)
            
            # Check for overspeed
            if rpm > max_rpm:
                await self.raise_alarm(
                    f"OVERSPEED: {turbine.device_name} at {rpm} RPM"
                )
```

## Error handling and validation

### Input validation

All `DataStore` methods validate inputs:

```python
# Raises ValueError for invalid inputs
await data_store.write_memory("", "address", value)  # Empty device_name
await data_store.write_memory("device", "", value)   # Empty address
await data_store.bulk_write_memory("device", {})     # Empty values dict
```

### Error logging

Operations log at appropriate levels:

```python
# INFO: Successful important operations
logger.info(f"Registered device: turbine_plc_1")
logger.info(f"Device turbine_plc_1 marked online")

# WARNING: Failed operations on non-existent devices
logger.warning(f"Cannot update non-existent device: missing_device")

# DEBUG: Routine operations
logger.debug(f"Read turbine_plc_1[holding_registers[0]] = 3600")
```

### Return values

Consistent return patterns:

- **Mutations** (write, update, register): Return `bool` for success/failure
- **Queries** (read, get): Return data or `None` if not found
- **Validation errors**: Raise `ValueError` with descriptive message

```python
# Returns bool
success = await data_store.write_memory(device, address, value)
if not success:
    logger.error("Write failed - device doesn't exist")

# Returns data or None
value = await data_store.read_memory(device, address)
if value is None:
    logger.warning("Device or address not found")

# Raises ValueError
try:
    await data_store.write_memory("", address, value)
except ValueError as e:
    logger.error(f"Invalid input: {e}")
```

## Performance considerations

### Lock contention

The system uses asyncio locks. High-frequency updates might cause contention:

```python
# Bad: Many small updates
for i in range(1000):
    await data_store.write_memory(device, f"holding_registers[{i}]", i)

# Good: Bulk update
updates = {f"holding_registers[{i}]": i for i in range(1000)}
await data_store.bulk_write_memory(device, updates)
```

### Memory map size

Memory maps are stored in-memory. Large memory maps (thousands of registers) increase memory usage and copy overhead.

For devices with huge memory maps, consider:
- Only storing active/changing registers
- Using sparse maps with default values
- Paginating memory map access

### Query optimisation

Filtering operations scan all devices. Cache results if querying frequently:

```python
# Cache device lists if stable
self._turbine_cache = await data_store.get_devices_by_type("turbine_plc")

# Refresh cache when topology changes
async def on_device_added(self, device):
    self._turbine_cache = None  # Invalidate cache
```

## Debugging and monitoring

### State inspection

Dump complete state for debugging:

```python
# Get all devices
devices = await data_store.get_all_device_states()

for name, device in devices.items():
    print(f"\n{name}:")
    print(f"  Type: {device.device_type}")
    print(f"  Online: {device.online}")
    print(f"  Last Update: {device.last_update}")
    print(f"  Memory Map: {device.memory_map}")
    print(f"  Metadata: {device.metadata}")
```

### Health checks

Monitor system health:

```python
async def health_check():
    summary = await data_store.get_simulation_state()
    
    # Check critical systems
    critical_devices = ["turbine_plc_1", "reactor_sis_1", "scada_server_1"]
    for device_name in critical_devices:
        device = await data_store.get_device_state(device_name)
        if not device or not device.online:
            raise RuntimeError(f"Critical device offline: {device_name}")
    
    # Check device online ratio
    total = summary["devices"]["total"]
    online = summary["devices"]["online"]
    if total > 0 and online / total < 0.8:  # Less than 80% online
        logger.warning(f"Low device availability: {online}/{total} online")
```

## TL;DR

1. **Register devices at startup** - All devices should register before simulation starts
2. **Use bulk operations** - Reduce lock contention with bulk reads/writes
3. **Follow protocol patterns** - Use consistent memory address formats
4. **Update atomically** - Group related changes into single operations
5. **Use metadata liberally** - Store context that helps with debugging and monitoring
6. **Handle None returns** - Always check if queries return None
7. **Cache stable queries** - Device type/protocol lists rarely change
8. **Monitor state health** - Track devices going offline unexpectedly
9. **Validate inputs** - Let DataStore raise ValueError for invalid inputs
10. **Use appropriate log levels** - INFO for important events, DEBUG for routine operations

## Common pitfalls

### Forgetting to registerdevices

❌ **Wrong:**
```python
# Try to update without registering
await data_store.write_memory("turbine_plc_1", "holding_registers[0]", 3600)
# Returns False - device doesn't exist
```

✅ **Correct:**
```python
# Register first
await data_store.register_device("turbine_plc_1", "turbine_plc", 1, ["modbus"])
# Then update
await data_store.write_memory("turbine_plc_1", "holding_registers[0]", 3600)
```

### Inconsistent key patterns

❌ **Wrong:**
```python
# Mixing patterns
await data_store.write_memory(device, "register_0", 100)
await data_store.write_memory(device, "holding_registers[1]", 200)
await data_store.write_memory(device, "HR2", 300)
```

✅ **Correct:**
```python
# Consistent pattern
await data_store.write_memory(device, "holding_registers[0]", 100)
await data_store.write_memory(device, "holding_registers[1]", 200)
await data_store.write_memory(device, "holding_registers[2]", 300)
```

### Not handling None returns

❌ **Wrong:**
```python
device = await data_store.get_device_state("missing_device")
print(device.online)  # AttributeError: 'NoneType' has no attribute 'online'
```

✅ **Correct:**
```python
device = await data_store.get_device_state("missing_device")
if device:
    print(device.online)
else:
    logger.warning("Device not found")
```

### Not catching ValueError

❌ **Wrong:**
```python
# Crashes with ValueError
await data_store.write_memory("", "address", value)
```

✅ **Correct:**
```python
try:
    await data_store.write_memory(device_name, address, value)
except ValueError as e:
    logger.error(f"Invalid parameters: {e}")
```

## Future enhancements

Potential improvements to consider:

- **Event subscriptions** - Notify listeners when device state changes
- **State persistence** - Save/load state to disk for simulator restart
- **State history** - Track state changes over time for analysis
- **State validation** - Enforce type/range constraints on memory values
- **Distributed state** - Support for multi-process simulations
- **State compression** - Optimise memory for large-scale simulations
- **ConfigLoader integration** - Load device definitions from YAML configuration

## References

- ICS register patterns: Modbus uses 16-bit registers, OPC UA uses node IDs
- State machine patterns for device lifecycle
- Observer pattern for state change notifications
- SCADA historian architectures
- SimulationTime module for temporal integration

---

*"The state of the system is a quantum superposition of 'working' and 'about to explode' until observed by the Bursar."*  
— UU P&L Operations Manual, Appendix M (Metaphysical)