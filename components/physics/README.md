# Physics simulation

This directory contains the physical process simulation engines for the ICS simulator. These modules model the actual 
behaviour of industrial equipment - turbines spinning, grids balancing load and generation, power flowing through 
transmission lines. The physics engines make the simulation realistic and enable meaningful security testing.

## Overview

Industrial control systems control physical processes. A Modbus write to register 10 might set a turbine speed 
setpoint, but what actually happens? The turbine doesn't instantly jump to that speed - it accelerates based on steam 
flow, limited by rotational inertia and steam valve response time. If an attacker commands 120% overspeed, the turbine 
will physically damage itself over time.

The physics engines simulate these real-world consequences, making attack demonstrations convincing and teaching proper 
caution when testing real systems.

## Components

| Module | System | Description |
|--------|--------|-------------|
| `turbine_physics.py` | Hex Steam Turbine | Shaft dynamics, thermal behaviour, power output, damage |
| `reactor_physics.py` | Alchemical Reactor | Temperature, pressure, reaction kinetics, thaumic stability |
| `hvac_physics.py` | Library Environmental | Zone temperature, humidity, L-space stability |
| `grid_physics.py` | City-Wide Distribution | System frequency, load-generation balance |
| `power_flow.py` | Transmission Network | Bus voltages, line flows, overload protection |

### `turbine_physics.py` - Steam turbine dynamics

Models the physical behaviour of a steam turbine generator, from shaft rotation to power output to mechanical damage.

**Physical processes modelled:**
- **Shaft dynamics** - Acceleration/deceleration based on steam flow and load
- **Thermal behaviour** - Bearing and steam temperatures with realistic time constants
- **Vibration** - Increases with speed deviation and mechanical damage
- **Power generation** - Electrical output based on rotational speed
- **Cumulative damage** - Overspeed operation causes permanent damage
- **Emergency protection** - Trip response and shutdown dynamics

**Integration points:**
- **Reads from DataStore**: Control inputs from PLC (speed setpoint, governor enable, trip)
- **Writes to DataStore**: Telemetry (RPM, temperature, vibration, power)
- **Uses SimulationTime**: Physics updates respect simulation time acceleration
- **Configurable**: Parameters can be loaded from configuration or set directly

**Example Usage:**
```python
from components.physics.turbine_physics import TurbinePhysics, TurbineParameters

# Create turbine with custom parameters
params = TurbineParameters(
    rated_speed_rpm=3600,
    rated_power_mw=50.0,
    max_safe_speed_rpm=3960  # 110% overspeed trip
)

turbine = TurbinePhysics("turbine_plc_1", data_store, params)
await turbine.initialise()

# Main simulation loop
while running:
    dt = sim_time.delta(last_time)
    
    # Update physics
    turbine.update(dt)
    
    # Write telemetry to device memory map
    await turbine.write_telemetry()
    
    # Get human-readable state
    telemetry = turbine.get_telemetry()
    print(f"Turbine: {telemetry['shaft_speed_rpm']} RPM, {telemetry['power_output_mw']} MW")
```

**Memory Map Interface:**

The turbine reads control inputs and writes telemetry to the device memory map using Modbus-style addresses:

**Control Inputs (written by PLC/attacker):**
- `speed_setpoint_rpm` - Target shaft speed
- `governor_enabled` (coil) - Enable automatic speed control
- `emergency_trip` (coil) - Trigger emergency shutdown

**Telemetry Outputs (read by SCADA/attacker):**
- `holding_registers[0]` - Shaft speed (RPM)
- `holding_registers[1]` - Steam temperature (°F)
- `holding_registers[2]` - Steam pressure (PSI)
- `holding_registers[3]` - Bearing temperature (°F)
- `holding_registers[4]` - Vibration (mils × 10)
- `holding_registers[5]` - Power output (MW)
- `holding_registers[6]` - Cumulative overspeed time (seconds)
- `holding_registers[7]` - Damage level (percentage)
- `coils[0]` - Running status
- `coils[1]` - Overspeed alarm
- `coils[2]` - High vibration alarm
- `coils[3]` - High bearing temperature alarm
- `coils[4]` - Severe damage alarm

**Physical Behaviour Examples:**

**Normal Operation:**
```python
# Set speed to rated
await data_store.write_memory("turbine_plc_1", "speed_setpoint_rpm", 3600)
await data_store.write_memory("turbine_plc_1", "governor_enabled", True)

# Turbine accelerates to 3600 RPM over ~36 seconds (100 RPM/s acceleration)
# Power output ramps to rated (100 MW)
# Bearing temperature stabilises at ~150°F
# Vibration stays at normal level (2 mils)
```

**Attack Scenario - Overspeed:**
```python
# Attacker commands 120% overspeed
await data_store.write_memory("turbine_plc_1", "speed_setpoint_rpm", 4320)

# Turbine accelerates beyond safe limits
# After ~10 seconds above 110% rated:
# - Damage accumulates (1% per second at 120%)
# - Vibration increases significantly
# - Overspeed alarm activates
# After damage reaches 50%, turbine may fail catastrophically
```

**Attack Scenario - Emergency Trip Bypass:**
```python
# Attacker disables safety trip
await data_store.write_memory("turbine_plc_1", "emergency_trip", False)

# Without trip, turbine continues accelerating
# Physical damage accumulates
# No automatic protection
```

### `grid_physics.py` - System frequency and voltage

Models grid-wide electrical dynamics, particularly frequency response to load-generation imbalance.

**Physical Processes Modelled:**
- **Swing equation** - Frequency change based on power imbalance and system inertia
- **Load damping** - Frequency-dependent load behaviour
- **Voltage dynamics** - Simplified voltage response (placeholder for more sophisticated model)
- **Protection trips** - Under/over frequency and voltage protection

**Integration Points:**
- **Reads from DataStore**: Aggregates power output from all turbines
- **Writes to DataStore**: Could write grid frequency to SCADA devices
- **Uses SimulationTime**: Grid dynamics respect simulation time
- **Configurable**: Grid parameters (inertia, damping, limits)

**Example Usage:**
```python
from components.physics.grid_physics import GridPhysics, GridParameters

# Create grid with 50 Hz nominal frequency
params = GridParameters(
    nominal_frequency_hz=50.0,
    inertia_constant=5000.0,  # MW·s
    damping=1.0,  # MW/Hz
    min_frequency_hz=49.0,
    max_frequency_hz=51.0
)

grid = GridPhysics(data_store, params)
await grid.initialise()

# Main simulation loop
while running:
    dt = sim_time.delta(last_time)
    
    # Aggregate generation and load from all devices
    await grid.update_from_devices()
    
    # Update grid dynamics
    grid.update(dt)
    
    # Check status
    telemetry = grid.get_telemetry()
    print(f"Grid: {telemetry['frequency_hz']} Hz, "
          f"Gen={telemetry['total_generation_mw']} MW, "
          f"Load={telemetry['total_load_mw']} MW")
```

**Physical Behaviour Examples:**

**Load-Generation Balance:**
```python
# Turbines producing 100 MW, load consuming 100 MW
# Grid frequency stable at 50.000 Hz
```

**Generation Loss (Attack Impact):**
```python
# Attacker trips turbine producing 50 MW
# Total generation drops from 100 MW to 50 MW
# Load still 100 MW - 50 MW deficit
# Grid frequency drops: df/dt = -50 / 5000 = -0.01 Hz/s
# After 10 seconds: frequency = 49.9 Hz
# After 100 seconds: frequency = 49.0 Hz → UNDER-FREQUENCY TRIP
```

**Generation Excess (Overspeed Attack):**
```python
# Attacker overspeeds turbines, increasing generation
# Total generation 120 MW, load 100 MW
# 20 MW excess
# Grid frequency rises: df/dt = 20 / 5000 = 0.004 Hz/s
# Frequency gradually increases to 51.0 Hz → OVER-FREQUENCY TRIP
```

**Cascading Failure:**
```python
# Initial trip causes frequency drop
# Other turbines hit under-frequency protection
# They trip, causing further frequency drop
# Entire grid collapses - realistic simulation of blackout
```

### `power_flow.py` - Transmission network

Models power flowing through transmission lines between generation and load centres.

**Physical Processes Modelled:**
- **Bus voltages and angles** - Electrical state at each connection point
- **Line power flows** - Active and reactive power through transmission lines
- **Line currents** - Thermal loading of conductors
- **Overload protection** - Line thermal limits

**Integration Points:**
- **Reads from DataStore**: Bus injections from generators and loads
- **Writes to DataStore**: Could write line flows to SCADA
- **Uses SimulationTime**: Updates respect simulation time
- **Uses ConfigLoader**: Loads grid topology from `config/grid.yml`

**Configuration:**

Create `config/grid.yml`:
```yaml
grid:
  base_mva: 100.0
  line_max_mva: 150.0
  
  buses:
    - name: bus_turbine_1
      type: generator
      base_voltage_kv: 132
    
    - name: bus_substation_1
      type: load
      base_voltage_kv: 11
    
    - name: bus_tie
      type: interconnection
      base_voltage_kv: 132
  
  lines:
    - name: line_gen_tie
      from_bus: bus_turbine_1
      to_bus: bus_tie
      reactance_pu: 0.05
      rating_mva: 150.0
    
    - name: line_tie_load
      from_bus: bus_tie
      to_bus: bus_substation_1
      reactance_pu: 0.08
      rating_mva: 100.0
```

**Example Usage:**
```python
from components.physics.power_flow import PowerFlow

# Create power flow engine
power_flow = PowerFlow(data_store, config_loader)
await power_flow.initialise()  # Loads grid topology

# Main simulation loop
while running:
    dt = sim_time.delta(last_time)
    
    # Update bus injections from devices
    await power_flow.update_from_devices()
    
    # Solve power flow
    power_flow.update(dt)
    
    # Check for overloads
    telemetry = power_flow.get_telemetry()
    for line_name, line_data in telemetry['lines'].items():
        if line_data['overload']:
            print(f"LINE OVERLOAD: {line_name}")
```

**Physical Behaviour Examples:**

**Normal Operation:**
```python
# Power flows from generators to loads through transmission lines
# Line flows within thermal limits
# Voltages remain close to 1.0 pu
# No overloads
```

**Line Overload (Attack or Contingency):**
```python
# One transmission line out of service (N-1 contingency)
# Remaining lines carry additional load
# Power redistribution causes overload
# Line protection may trip, cascading to other lines
```

**Voltage Collapse:**
```python
# Heavy reactive power demand
# Insufficient reactive support
# Bus voltages drop below acceptable limits
# Undervoltage protection trips loads and generators
# Cascading outage possible
```

## Physics integration architecture

The physics engines are designed to integrate cleanly with the simulation infrastructure:

```
┌──────────────────────────────────────────────────────────┐
│ Main Simulation Loop                                     │
│                                                          │
│  while running:                                          │
│    dt = sim_time.delta(last_time)                        │
│    ↓                                                     │
│    ┌────────────────────────────────────────┐            │
│    │ Update device aggregations (async)     │            │
│    │  await grid.update_from_devices()      │            │
│    │  await power_flow.update_from_devices()│            │
│    └────────────────────────────────────────┘            │
│    ↓                                                     │
│    ┌────────────────────────────────────────┐            │
│    │ Update physics (synchronous)           │            │
│    │  turbine.update(dt)                    │            │
│    │  grid.update(dt)                       │            │
│    │  power_flow.update(dt)                 │            │
│    └────────────────────────────────────────┘            │
│    ↓                                                     │
│    ┌────────────────────────────────────────┐            │
│    │ Write telemetry (async)                │            │
│    │  await turbine.write_telemetry()       │            │
│    └────────────────────────────────────────┘            │
│    ↓                                                     │
│    await wait_simulation_time(interval)                  │
└──────────────────────────────────────────────────────────┘
```

**Key Design Principles:**

1. **Physics is synchronous** - `update(dt)` methods are not async, ensuring deterministic calculation order
2. **I/O is asynchronous** - Reading from and writing to DataStore is async
3. **Time-driven updates** - Physics receives time delta, not wall-clock time
4. **Single update per cycle** - Each physics engine updated once per simulation cycle
5. **Clear data flow** - Read inputs → Calculate physics → Write outputs

## Realistic physical behaviour

The physics engines implement realistic time constants and dynamics:

### Turbine dynamics

**Acceleration:** ~36 seconds from standstill to rated speed (100 RPM/s)
**Deceleration:** ~72 seconds from rated to stop (50 RPM/s)
**Thermal lag:** Bearing temperature changes over ~10 seconds
**Overspeed damage:** 1% per second at 120% rated speed

These match real steam turbine behaviour, making attack demonstrations credible.

### Grid dynamics

**Frequency response:** With 5000 MW·s inertia, 50 MW imbalance causes:
- Initial rate: 0.01 Hz/s
- Reaches protection limit (~1 Hz) in ~100 seconds

**Load damping:** 1% load increase per 1% frequency increase (simplified)

### Power flow

**Voltage drop:** Resistive and reactive components
**Line loading:** Thermal limits based on MVA rating
**Transient stability:** Simplified model (full transient stability requires differential equations)

## Security testing scenarios

### Scenario 1: Turbine overspeed attack

**Attacker Action:**
```python
# Modbus write to speed setpoint register
await attacker_write_register("192.168.1.100", 502, address=10, value=4500)
```

**Physics Response:**
1. Turbine accelerates to 4500 RPM (125% rated)
2. Overspeed alarm activates at 3960 RPM (110%)
3. Damage accumulates: 1.5% per second
4. After 30 seconds: 45% damage
5. Vibration increases significantly
6. Bearing temperature rises
7. At 50% damage, catastrophic failure possible

**Observable Effects:**
- SCADA shows increasing RPM
- Alarms trigger
- Physical plant damage (simulated)
- Potential grid frequency increase

### Scenario 2: Coordinated generator trip

**Attacker Action:**
```python
# Trip multiple turbines simultaneously
for turbine in ["192.168.1.100", "192.168.1.101", "192.168.1.102"]:
    await attacker_write_coil(turbine, 502, address=11, value=True)
```

**Physics Response:**
1. Three turbines producing 150 MW total trip
2. Grid loses 150 MW generation instantly
3. Grid frequency drops: df/dt = -150/5000 = -0.03 Hz/s
4. After 33 seconds: frequency hits 49.0 Hz
5. Under-frequency protection trips additional generators
6. Cascading failure leads to blackout

**Observable Effects:**
- SCADA shows turbines offline
- Grid frequency dropping
- Undervoltage on buses
- System-wide blackout (if protection acts)

### Scenario 3: Transmission line overload

**Attacker Action:**
```python
# Trip one transmission line (N-1 contingency)
# Then overload turbines on remaining lines
```

**Physics Response:**
1. One line trips
2. Power redistributes to remaining lines
3. Lines exceed thermal rating (150 MVA)
4. Line overload protection trips
5. Further redistribution causes cascading trips
6. Grid islands or collapses

## Performance considerations

### Computational efficiency

Physics updates are fast:
- **Turbine**: ~10 floating-point operations per update
- **Grid**: ~20 operations (scales with number of generators)
- **Power flow**: ~N² operations (N = number of buses)

For typical simulation (10 turbines, 20 buses):
- Total physics time: <0.1 ms per update
- Update rate: 10 Hz (0.1s intervals) is sufficient
- Can run much faster in accelerated simulation

### Memory usage

Physics state is minimal:
- **Turbine**: ~200 bytes per instance
- **Grid**: ~500 bytes
- **Power flow**: ~100 bytes per bus + 50 bytes per line

For large simulation (100 devices, 100 buses, 200 lines):
- Total physics memory: ~50 KB
- Negligible compared to network buffers

### Simulation time acceleration

Physics scales with simulation time:
```python
# 1x realtime: 1 second simulation = 1 second wall-clock
# Turbine spins up in 36 seconds realtime

# 10x acceleration: 1 second simulation = 0.1 second wall-clock  
# Turbine spins up in 3.6 seconds realtime
# Attack effects observable 10x faster
```

## Testing physics behaviour

### Unit testing

Test physics in isolation:
```python
async def test_turbine_acceleration():
    turbine = TurbinePhysics("test_turbine", mock_data_store)
    await turbine.initialise()
    
    # Command 3600 RPM
    turbine.update(dt=1.0)  # Simulate 1 second
    
    # Should accelerate at 100 RPM/s
    assert 90 < turbine.state.shaft_speed_rpm < 110
```

### Integration testing

Test with full simulation:
```python
async def test_grid_response_to_trip():
    # Set up simulation with 100 MW generation, 100 MW load
    # Trip 50 MW turbine
    # Measure frequency drop
    # Verify under-frequency protection at 49.0 Hz
```

### Validation against reality

Compare simulation to real system behaviour:
- Literature values for turbine dynamics
- Grid frequency response data from real events
- Transmission line thermal models from standards

## Common issues and solutions

### Issue: Physics not updating

**Symptom:** Turbine RPM stuck at zero, grid frequency constant

**Cause:** Physics `update()` not being called from main loop

**Solution:**
```python
# Ensure main loop calls physics update
turbine.update(dt)
grid.update(dt)
```

### Issue: Unrealistic behaviour

**Symptom:** Turbine accelerates instantly, frequency changes too fast

**Cause:** Time delta too large or parameters incorrect

**Solution:**
```python
# Check simulation update interval
# Should be 0.1s or less for realistic turbine dynamics
update_interval = 0.1

# Verify parameters match real equipment
params = TurbineParameters(
    inertia=5000.0,  # Realistic for large turbine
    acceleration_rate=100.0  # ~36s to rated speed
)
```

### Issue: Physics out of sync

**Symptom:** Grid frequency based on old turbine power output

**Cause:** Not calling `update_from_devices()` before physics update

**Solution:**
```python
# Always update device aggregations first
await grid.update_from_devices()
await power_flow.update_from_devices()

# Then update physics
grid.update(dt)
power_flow.update(dt)
```

### `reactor_physics.py` - Alchemical reactor dynamics

Models the physical behaviour of the Bursar's Automated Alchemical Reactor, which converts thaumic input into usable
thermal energy while accounting for both chemical and metaphysical variables.

**Physical Processes Modelled:**
- **Temperature dynamics** - Core and coolant temperatures with realistic thermal mass
- **Pressure dynamics** - Vessel pressure response to temperature
- **Reaction kinetics** - Reaction rate response to control rod position
- **Thaumic field stability** - The magical component that can destabilise under stress
- **Safety systems** - SCRAM (emergency shutdown), containment integrity
- **Cumulative damage** - Overtemperature operation causes permanent damage

**Integration Points:**
- **Reads from DataStore**: Control inputs from PLC (power setpoint, control rods, coolant pump)
- **Writes to DataStore**: Telemetry (temperatures, pressure, thaumic field, alarms)
- **Uses SimulationTime**: Physics updates respect simulation time acceleration
- **Configurable**: Parameters for thermal mass, cooling capacity, thaumic behaviour

**Example Usage:**
```python
from components.physics.reactor_physics import ReactorPhysics, ReactorParameters

# Create reactor with custom parameters
params = ReactorParameters(
    rated_power_mw=25.0,
    rated_temperature_c=350.0,
    max_safe_temperature_c=400.0,
    critical_temperature_c=450.0
)

reactor = ReactorPhysics("reactor_plc_1", data_store, params)
await reactor.initialise()

# Main simulation loop
while running:
    dt = sim_time.delta(last_time)
    await reactor.read_control_inputs()
    reactor.update(dt)
    await reactor.write_telemetry()

    telemetry = reactor.get_telemetry()
    print(f"Reactor: {telemetry['core_temperature_c']}°C, "
          f"Thaumic={telemetry['thaumic_field_strength']}")
```

**Attack Scenario - Overtemperature:**
```python
# Attacker commands 150% power with reduced cooling
await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 150)  # Power
await data_store.write_memory("reactor_plc_1", "holding_registers[11]", 20)   # Coolant

# Reactor temperature rises above safe limits
# Thaumic field becomes unstable
# Damage accumulates
# Eventually triggers auto-SCRAM or containment breach
```

### `hvac_physics.py` - Library environmental control

Models the Library Environmental Management System, which maintains temperature, humidity, and magical stability within
the University Library. The Library exists partially in L-space (a dimension where all libraries are connected).

**Physical Processes Modelled:**
- **Zone temperature** - Heating/cooling dynamics with thermal mass of stone building
- **Humidity control** - Humidification, dehumidification, outside air mixing
- **Air handling** - Fan speed, duct pressure, damper positions (fan laws)
- **L-space stability** - Dimensional stability affected by environmental stress
- **Energy consumption** - Power usage calculation for all components

**Integration Points:**
- **Reads from DataStore**: Control inputs (setpoints, mode, fan speed, damper)
- **Writes to DataStore**: Telemetry (temperatures, humidity, L-space stability, alarms)
- **Uses SimulationTime**: Physics updates respect simulation time
- **Configurable**: Zone thermal mass, equipment capacities, L-space thresholds

**Example Usage:**
```python
from components.physics.hvac_physics import HVACPhysics, HVACParameters

# Create HVAC for the Library
params = HVACParameters(
    zone_thermal_mass=500.0,      # Large stone library
    zone_volume_m3=5000.0,
    rated_heating_kw=50.0,
    rated_cooling_kw=75.0,
    lspace_threshold_temp_c=25.0  # L-space gets unstable above this
)

hvac = HVACPhysics("library_hvac_1", data_store, params)
await hvac.initialise()

# Main simulation loop
while running:
    dt = sim_time.delta(last_time)
    await hvac.read_control_inputs()
    hvac.update(dt)
    await hvac.write_telemetry()

    telemetry = hvac.get_telemetry()
    print(f"Library: {telemetry['zone_temperature_c']}°C, "
          f"RH={telemetry['zone_humidity_percent']}%, "
          f"L-space={telemetry['lspace_stability']}")
```

**Attack Scenario - L-space Destabilisation:**
```python
# Attacker disables L-space dampener and overheats the library
await data_store.write_memory("library_hvac_1", "coils[11]", False)  # Dampener off
await data_store.write_memory("library_hvac_1", "holding_registers[10]", 30)  # High temp

# Library temperature rises
# L-space stability decreases
# Books may begin migrating between dimensions
# The Librarian becomes very unhappy (Ook!)
```

## Future enhancements

Potential improvements:

- **Governor models** - More sophisticated speed control algorithms
- **Boiler dynamics** - Steam generation and pressure control
- **Transient stability** - Differential equation-based models
- **Harmonics** - Power quality simulation
- **Protection coordination** - Detailed relay models
- **HVDC links** - DC transmission modelling
- **Renewable integration** - Solar/wind variability
- **Substation physics** - Transformer dynamics, tap changers, breakers

## References

- Power system dynamics and stability (Kundur)
- Steam turbine operation and control
- Grid frequency response standards (NERC, ENTSO-E)
- IEC 61850 power system information exchange
- Swing equation and small-signal stability

---

*"The physics doesn't care about your penetration test scope. Overspeed the turbine, and it will destroy itself - 
simulated or not, the principle remains."*