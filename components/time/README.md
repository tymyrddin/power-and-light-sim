# Simulation time management

This directory contains the time management system for the ICS simulator. Industrial control systems operate 
on precise timing. PLCs scan at millisecond intervals, turbines spin at exact RPMs, and safety systems must respond 
within defined time windows—the simulator needs robust time control.

## Overview

The `simulation_time.py` module provides a singleton time manager that can run in multiple modes, allowing for:

- **Testing in real-time** - Match real-world timing for realistic behaviour
- **Accelerating testing** - Run scenarios faster than real-time (e.g., 10x speed)
- **Stepping through time** - Manually advance time for deterministic testing
- **Pausing and resuming** - Freeze the simulation without losing state

## Architecture

### Core components

**`SimulationTime` (Singleton)**
- Central time authority for the entire simulation
- Manages simulation time independently of wall-clock time
- Thread-safe with asyncio locks
- Configured from `config/simulation.yml`

**`TimeMode` (Enum)**
- `REALTIME` - Simulation time matches wall-clock time (1:1)
- `ACCELERATED` - Simulation time runs faster than wall-clock (configurable multiplier)
- `STEPPED` - Manual time advancement, no automatic progression
- `PAUSED` - Simulation frozen, time does not advance

**`TimeState` (Dataclass)**
- Holds current time state
- Tracks simulation time vs. wall-clock time
- Stores mode, speed multiplier, pause state

## Usage

### Basic time queries

```python
from components.time.simulation_time import SimulationTime

sim_time = SimulationTime()

# Get current simulation time
current = sim_time.now()

# Calculate time delta since last check
last_check = sim_time.now()
# ... do work ...
delta = sim_time.delta(last_check)

# Get total elapsed simulation time
elapsed = sim_time.elapsed()

# Get wall-clock elapsed time
wall_elapsed = sim_time.wall_elapsed()
```

### Running the time system

```python
import asyncio
from components.time.simulation_time import SimulationTime

async def main():
    sim_time = SimulationTime()
    
    # Start time progression
    await sim_time.start()
    
    # Simulation runs...
    
    # Stop when done
    await sim_time.stop()

asyncio.run(main())
```

### Time control

```python
# Pause the simulation
await sim_time.pause()

# Resume from pause
await sim_time.resume()

# Change speed (2x faster)
await sim_time.set_speed(2.0)

# Reset to time zero
await sim_time.reset()
```

### Stepped mode

For deterministic testing where you need complete control:

```python
# Set mode to STEPPED in simulation.yml or:
sim_time.state.mode = TimeMode.STEPPED

await sim_time.start()

# Manually advance time
await sim_time.step(0.1)  # Advance 100ms
await sim_time.step(1.0)  # Advance 1 second
```

### Waiting for simulation time

Use the convenience function to wait for simulation time (not wall-clock time):

```python
from components.time.simulation_time import wait_simulation_time

# Wait for 10 simulation seconds
# (Could be 1 wall-clock second at 10x speed)
await wait_simulation_time(10.0)
```

## Configuration

Time settings are loaded from `config/simulation.yml`:

```yaml
simulation:
  runtime:
    update_interval: 1.0      # Time loop update frequency (seconds)
    realtime: true            # True = REALTIME mode, False = ACCELERATED
    time_acceleration: 1.0    # Speed multiplier (2.0 = 2x faster)
```

**Configuration Parameters:**

- **`update_interval`** - How often the time loop updates (default: 0.01s = 10ms)
  - Smaller = more precise time tracking, higher CPU usage
  - Larger = less CPU usage, coarser time granularity
  - For PLCs with 10-100ms scan cycles, 0.01s is appropriate
  
- **`realtime`** - Initial time mode
  - `true` = Start in REALTIME mode
  - `false` = Start in ACCELERATED mode
  
- **`time_acceleration`** - Speed multiplier for ACCELERATED mode
  - `1.0` = Real-time speed
  - `2.0` = 2x faster (2 sim seconds per 1 wall second)
  - `10.0` = 10x faster (useful for long-duration tests)
  - `0.5` = Half speed (useful for debugging)

## Time modes explained

### REALTIME mode

Simulation time progresses at the same rate as wall-clock time.

**Use when:**
- Testing realistic timing behavior
- Verifying protocol timeouts work correctly
- Demonstrating the simulation to others
- Running long-term stability tests

**Example:**
```python
# PLC scan cycle running at real-world speed
async def plc_scan_loop():
    while True:
        start = sim_time.now()
        
        # Execute control logic
        await execute_ladder_logic()
        
        # Wait for remainder of 100ms scan cycle
        elapsed = sim_time.delta(start)
        await wait_simulation_time(0.1 - elapsed)
```

### ACCELERATED mode

Simulation time runs faster than wall-clock time.

**Use when:**
- Testing scenarios that take hours in real life
- Running turbine startup sequences (normally 30+ minutes)
- Simulating daily operational cycles
- Stress testing with rapid state changes

**Example:**
```python
# Test 24-hour operational cycle in 2.4 hours
await sim_time.set_speed(10.0)
await sim_time.start()

# Run daily cycle
await wait_simulation_time(86400)  # 24 hours simulation time
```

**Caution:** External protocols don't speed up. If running at 10x speed and a real Modbus client connects, it will experience the accelerated behavior.

### STEPPED mode

Time only advances when explicitly commanded.

**Use when:**
- Debugging complex timing issues
- Unit testing with deterministic time
- Analyzing state transitions step-by-step
- Reproducing race conditions

**Example:**
```python
# Deterministic test
sim_time.state.mode = TimeMode.STEPPED
await sim_time.start()

# Step through startup sequence
await turbine.start()
await sim_time.step(1.0)   # Advance 1 second
assert turbine.rpm == expected_rpm_at_1s

await sim_time.step(5.0)   # Advance 5 more seconds
assert turbine.rpm == expected_rpm_at_6s
```

### PAUSED mode

Time is frozen but simulation maintains state.

**Use when:**
- Inspecting state during operation
- Taking a break without stopping everything
- Waiting for operator input
- Debugging live issues

## Implementation details

### Singleton pattern

`SimulationTime` uses a singleton to ensure there's only one time authority:

```python
class SimulationTime:
    _instance: Optional["SimulationTime"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

This means:
```python
time1 = SimulationTime()
time2 = SimulationTime()
# time1 and time2 are the same object
assert time1 is time2
```

### Thread safety

All state modifications use an asyncio lock:

```python
async def set_speed(self, multiplier: float):
    async with self._lock:
        # Thread-safe state modification
        self.state.speed_multiplier = multiplier
```

This ensures multiple coroutines can safely query and modify time.

### Time loop

In REALTIME and ACCELERATED modes, an internal loop updates time:

```python
async def _time_loop(self):
    while self._running:
        await asyncio.sleep(self.state.update_interval)
        
        # Calculate wall-clock delta
        wall_delta = current_time - last_update
        
        # Apply speed multiplier
        sim_delta = wall_delta * self.state.speed_multiplier
        
        # Update simulation time
        self.state.simulation_time += sim_delta
```

### Pause handling

When paused, the loop continues running but doesn't advance time:

```python
if self.state.paused:
    last_update = current_time
    continue  # Don't advance simulation_time
```

When resumed, the wall-clock start time is adjusted to account for the pause.

## Practical examples

### PLC scan cycle

```python
class TurbinePLC:
    def __init__(self):
        self.sim_time = SimulationTime()
        self.scan_interval = 0.1  # 100ms scan cycle
    
    async def run(self):
        last_scan = self.sim_time.now()
        
        while True:
            # Read inputs
            pressure = await self.read_pressure_sensor()
            temperature = await self.read_temperature_sensor()
            
            # Execute logic
            if pressure > self.max_pressure:
                await self.open_relief_valve()
            
            if temperature > self.max_temperature:
                await self.activate_cooling()
            
            # Update outputs
            await self.write_outputs()
            
            # Wait for next scan
            await wait_simulation_time(self.scan_interval)
```

### Protocol timeout testing

```python
async def test_modbus_timeout():
    sim_time = SimulationTime()
    await sim_time.start()
    
    # Configure 3-second timeout
    client = ModbusClient(timeout=3.0)
    
    start = sim_time.now()
    
    try:
        # This should timeout after 3 simulation seconds
        await client.read_registers(address=100)
    except TimeoutError:
        elapsed = sim_time.delta(start)
        assert 2.9 < elapsed < 3.1  # Verify timeout timing
```

### Long-duration scenario

```python
async def test_daily_operations():
    sim_time = SimulationTime()
    
    # Run at 100x speed (24 hours in 14.4 minutes)
    await sim_time.set_speed(100.0)
    await sim_time.start()
    
    # Simulate morning startup (6 AM)
    await wait_simulation_time(6 * 3600)
    await plant.startup()
    
    # Run production (6 AM to 10 PM)
    await wait_simulation_time(16 * 3600)
    
    # Evening shutdown
    await plant.shutdown()
```

### Deterministic testing

```python
async def test_state_machine():
    sim_time = SimulationTime()
    sim_time.state.mode = TimeMode.STEPPED
    await sim_time.start()
    
    turbine = TurbinePLC()
    
    # Initial state
    assert turbine.state == TurbineState.STOPPED
    
    # Start command
    await turbine.start_command()
    await sim_time.step(0.1)
    assert turbine.state == TurbineState.STARTING
    
    # Wait for speed ramp
    await sim_time.step(10.0)
    assert turbine.state == TurbineState.RUNNING
    assert 3590 < turbine.rpm < 3610  # 3600 RPM target
```

## Status monitoring

Get comprehensive time status:

```python
status = await sim_time.get_status()
print(status)
# {
#     'simulation_time': 125.7,
#     'wall_time_elapsed': 12.57,
#     'mode': 'accelerated',
#     'speed_multiplier': 10.0,
#     'paused': False,
#     'ratio': 10.0  # Actual sim/wall ratio
# }
```

The `ratio` field shows the actual simulation-to-wall-clock ratio, useful for verifying acceleration is working correctly.

## Integration with other components

### Physics engines

```python
class TurbinePhysics:
    def update(self, delta_time: float):
        # Use simulation time delta, not wall-clock
        self.rpm += self.acceleration * delta_time
        self.temperature += self.heat_rate * delta_time
```

### Network protocols

```python
class ModbusServer:
    async def handle_request(self):
        start_time = self.sim_time.now()
        
        # Process request...
        
        # Check if we've exceeded protocol timeout
        if self.sim_time.delta(start_time) > self.timeout:
            raise TimeoutError("Request processing timeout")
```

### Event scheduling

```python
class EventScheduler:
    async def schedule_at(self, sim_time_target: float, callback):
        while self.sim_time.now() < sim_time_target:
            await asyncio.sleep(0.01)
        await callback()
```

## TL;DR

1. **Always use simulation time** - Never use `time.time()` or `asyncio.sleep()` directly in simulation code
2. **Use `wait_simulation_time()`** - For waiting periods in simulation code
3. **Check pause state** - Long-running operations should check `is_paused()`
4. **Test in multiple modes** - Verify behavior in REALTIME, ACCELERATED, and STEPPED
5. **Monitor time ratio** - Use `get_status()` to verify acceleration is working
6. **Handle mode transitions** - Be prepared for speed changes during operation

## Common pitfalls

### Mixing time systems

❌ **Wrong:**
```python
import time
await asyncio.sleep(1.0)  # Wall-clock sleep, not simulation time
```

✅ **Correct:**
```python
await wait_simulation_time(1.0)  # Simulation time aware
```

### External protocol timing

When real external clients connect, they experience accelerated time:

```python
# At 10x speed, a Modbus client connecting will see:
# - Faster responses
# - More frequent data updates
# - Timeouts may trigger unexpectedly

# Consider running at 1x speed when external clients connect
if external_clients_connected:
    await sim_time.set_speed(1.0)
```

### Update interval too large

If `update_interval` is too large, time advancement becomes choppy:

```python
# Bad: 1-second updates with 100ms scan cycles
update_interval: 1.0

# Good: 10ms updates for 100ms scan cycles  
update_interval: 0.01
```

## Troubleshooting

**Time not advancing:**
- Check if paused: `sim_time.is_paused()`
- Verify mode is not STEPPED: `sim_time.state.mode`
- Ensure `start()` was called

**Acceleration not working:**
- Check `time_acceleration` in config
- Verify mode is ACCELERATED
- Monitor `ratio` in status

**Time progressing too fast/slow:**
- Adjust `time_acceleration` multiplier
- Check for pause/resume timing bugs
- Verify `update_interval` is appropriate

## Testing

The time system itself should be tested:

```python
async def test_time_acceleration():
    sim_time = SimulationTime()
    await sim_time.set_speed(10.0)
    await sim_time.start()
    
    wall_start = time.time()
    sim_start = sim_time.now()
    
    await asyncio.sleep(1.0)  # 1 wall-clock second
    
    wall_elapsed = time.time() - wall_start
    sim_elapsed = sim_time.delta(sim_start)
    
    # Should be approximately 10 sim seconds in 1 wall second
    assert 9.5 < sim_elapsed < 10.5
```

## Future enhancements

Potential improvements to consider:

- **Event-based time jumps** - Jump to next scheduled event
- **Time synchronization** - Sync with external time sources
- **Playback mode** - Replay recorded timelines
- **Time travel** - Checkpoint and restore time states
- **Variable speed** - Dynamically adjust speed based on activity

## References

- ICS timing requirements: PLCs typically scan at 10-100ms
- DNP3 protocol timeout: Default 5-30 seconds
- Modbus timeout: Typically 1-5 seconds
- IEC 104 timing: T1=15s, T2=10s, T3=20s

---

*"Time is an illusion. Lunchtime doubly so. But PLC scan cycles are very real."*  
— Adapted from Douglas Adams, with apologies to automation engineers