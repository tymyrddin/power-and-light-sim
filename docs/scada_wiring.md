# SCADA Server Wiring Documentation

## Overview

The SCADA servers are now fully wired to poll PLCs and collect telemetry data through a configuration-driven approach.

## Architecture

```
┌─────────────────┐
│ scada_tags.yml  │  Configuration file defines:
│                 │  - Poll targets (which devices to poll)
└────────┬────────┘  - Tags (what data to collect)
         │           - Alarm limits (when to alert)
         │
         v
┌─────────────────┐
│  ConfigLoader   │  Loads YAML config into memory
└────────┬────────┘
         │
         v
┌─────────────────┐
│SimulatorManager │  Applies config to SCADA devices:
│                 │  - add_poll_target()
└────────┬────────┘  - add_tag()
         │
         v
┌─────────────────┐
│  SCADAServer    │  Polls devices and collects data:
│                 │  - Multi-rate polling
│  ┌───────────┐  │  - Tag database
│  │Tag:Value  │  │  - Alarm management
│  │Quality    │  │  - Quality tracking
│  │Timestamp  │  │
│  └───────────┘  │
└─────────────────┘
```

## Files

### 1. **config/scada_tags.yml** (NEW)
Comprehensive tag database configuration:
- **66 tags** defined across 3 systems
- **4 poll targets** configured
- Alarm limits set for critical parameters

### 2. **config/config_loader.py**
SCADA tags loading:
```python
# Load SCADA tags config
scada_tags_path = self.config_dir / "scada_tags.yml"
if scada_tags_path.exists():
    config["scada_servers"] = scada_data.get("scada_servers", {})
```

### 3. **tools/simulator_manager.py**
`_configure_scada_servers()` method:
- Reads config for each SCADA server
- Configures poll targets (devices to poll)
- Defines tags (data points to collect)
- Sets alarm limits

Wired into initialization sequence:
```python
# 5. Create device instances
await self._create_devices(config)

# 6. Configure SCADA servers (NEW)
await self._configure_scada_servers(config)

# 7. Expose services in network
await self._expose_services(config)
```

## Tag database

### Turbine tags (23 tags)
**Telemetry:**
- Speed, power, steam pressure/temp
- Bearing temp, vibration, damage
- Grid frequency

**Status:**
- Running, governor online, trip active, overspeed

**Control:**
- Speed setpoint, governor enable, emergency trip

### Reactor tags (24 tags)
**Telemetry:**
- Core/coolant temps, pressure, power
- Thaumic field strength, reaction rate
- Coolant flow, containment integrity

**Status:**
- Active, high temp/pressure warnings
- Thaumic/containment warnings, SCRAM active

**Control:**
- Power setpoint, coolant pump, control rods
- SCRAM command/reset, thaumic dampener

### HVAC tags (19 tags)
**Telemetry:**
- Zone temp, humidity, supply temp
- L-space stability
- Fan/valve/damper positions, energy

**Status:**
- Fan running, heating/cooling active
- Temperature/humidity alarms
- L-space warnings

**Control:**
- Temp/humidity setpoints, fan speed
- Operating mode, damper position
- System enable, L-space dampener

## Alarm configuration

Critical alarms configured:

**Safety-Critical:**
- `TURB1_SPEED` > 3960 RPM (overspeed)
- `RX1_CORE_TEMP` > 400°C (critical temp)
- `RX1_PRESSURE` > 150 bar (overpressure)
- `RX1_COOLANT_FLOW` < 20% (loss of cooling)

**Process Alarms:**
- `TURB1_BEARING_TEMP` > 180°F
- `TURB1_VIBRATION` > 8.0 mils
- `RX1_THAUMIC_FIELD` < 50% (instability)
- `LIB_LSPACE_STAB` < 50% (dimensional instability)

**Environmental:**
- `LIB_ZONE_TEMP` outside 18-22°C
- `LIB_HUMIDITY` outside 40-55%

## Data flow

1. **PLC Scan Cycle** (100ms - 1s)
   - PLCs read from physics engines
   - Update memory maps (input_registers, discrete_inputs)

2. **Protocol Sync** (each simulation update)
   - SimulatorManager._sync_protocol_servers()
   - Pushes PLC telemetry to Modbus servers

3. **SCADA Polling** (1-2s poll rates)
   - SCADA reads from PLC Modbus servers via DataStore
   - Updates tag values, timestamps, quality
   - Checks alarm conditions

4. **Tag Database**
   - Current values stored in memory_map
   - Available to HMI workstations
   - Alarms tracked and logged

## Usage examples

### Reading tag values
```python
# Get SCADA server instance
scada = simulator.device_instances.get("scada_server_primary")

# Read individual tag
speed = await scada.get_tag_value("TURB1_SPEED")
print(f"Turbine speed: {speed} RPM")

# Get all tags
all_tags = await scada.get_all_tags()
for tag_name, tag_data in all_tags.items():
    print(f"{tag_name}: {tag_data['value']} ({tag_data['quality']})")

# Get active alarms
alarms = await scada.get_active_alarms()
for alarm in alarms:
    print(f"ALARM: {alarm.message}")
```

### Writing control commands
Control commands should be written to PLC memory maps:
```python
# Get PLC instance
turbine_plc = simulator.device_instances.get("hex_turbine_plc")

# Set speed setpoint
await turbine_plc.set_speed_command(3600.0)

# Enable governor
await turbine_plc.enable_governor(True)
```

SCADA will poll the updated values and reflect them in the tag database.

## Testing

Run the simulation and verify SCADA wiring:
```bash
python tools/simulator_manager.py
```

Expected log output:
```
INFO - Configuring SCADA servers...
DEBUG - Added poll target to scada_server_primary: hex_turbine_plc (modbus) @ 1.0s
DEBUG - Added poll target to scada_server_primary: reactor_plc (modbus) @ 1.0s
DEBUG - Added poll target to scada_server_primary: library_hvac_plc (modbus) @ 2.0s
DEBUG - Added tag to scada_server_primary: TURB1_SPEED -> hex_turbine_plc:input_register[0]
...
INFO - Configured SCADA server 'scada_server_primary': 4 poll targets, 66 tags
```

Check SCADA telemetry:
```python
# Get comprehensive status
status = await scada.get_telemetry()
print(f"Total polls: {status['statistics']['total_polls']}")
print(f"Active alarms: {status['statistics']['active_alarms']}")
print(f"Tags: {len(status['tags'])}")
```

## Future Enhancements

1. **Tag Scaling**: Apply engineering unit conversions
2. **Derived Tags**: Calculate values from multiple sources
3. **Historian Integration**: Store tag history
4. **Change-of-State Alarms**: Track digital input transitions
5. **Alarm Hysteresis**: Prevent alarm chattering
6. **Tag Quality Codes**: Detailed quality indicators
7. **Backup Server Tags**: Configure independent tag set for redundancy

## HMI Workstation Integration

### Configuration File: `hmi_screens.yml`

HMI workstations connect to SCADA servers and display operator screens:

```yaml
hmi_workstations:
  hmi_operator_1:
    scada_server: scada_server_primary
    screens:
      - name: plant_overview
        tags: [TURB1_SPEED, RX1_CORE_TEMP, LIB_ZONE_TEMP]
        controls: [NAV_TO_TURBINE, NAV_TO_REACTOR]
```

### HMI → SCADA Connection Flow

```
HMI Workstation              SCADA Server              PLCs
┌──────────────┐            ┌──────────────┐         ┌─────────┐
│ hmi_operator │  poll @    │scada_server  │  poll @ │turbine  │
│      _1      │─ 500ms ───>│   _primary   │─  1s ──>│reactor  │
│              │            │              │         │hvac     │
│ Screens:     │            │ Tag DB:      │         └─────────┘
│ - Overview   │<───────────│ - TURB1_*    │
│ - Turbine    │  tag data  │ - RX1_*      │
│ - Reactor    │            │ - LIB_*      │
└──────────────┘            └──────────────┘
```

### Screen Definitions

**hmi_operator_1:**
- `plant_overview` - High-level system status
- `turbine_control` - Detailed turbine monitoring
- `reactor_control` - Reactor monitoring and control

**hmi_operator_2:**
- `library_hvac` - HVAC environmental control
- `alarm_summary` - Active alarms across all systems

**hmi_operator_3/4:**
- Connected to `scada_server_backup` for redundancy
- Basic monitoring screens

### HMI Configuration Process

1. **Load Config** - ConfigLoader reads `hmi_screens.yml`
2. **Configure HMIs** - SimulatorManager applies config:
   - Sets SCADA server connection
   - Clears default poll targets
   - Adds correct SCADA server as poll target
   - Defines screens with tags and controls
   - Navigates to initial screen
3. **Operation** - HMI polls SCADA at configured rate

### Fixed Issue

**Before:**
```
[WARNING] HMI 'hmi_operator_1': Lost connection to SCADA server
```
HMI was looking for default `"scada_master_1"` which doesn't exist.

**After:**
```
INFO - Configured HMI workstation 'hmi_operator_1': SCADA=scada_server_primary, 3 screens
```
HMI now connected to correct `"scada_server_primary"`.

## Troubleshooting

**No tag values updating:**
- Check poll targets are enabled
- Verify device names match config
- Ensure protocol servers are running

**Alarms not triggering:**
- Verify alarm limits are set in config
- Check tag quality is "good"
- Ensure _check_alarms() is being called

**High poll failure rate:**
- Reduce poll rates
- Check device availability
- Verify network connectivity in simulation

**HMI "Lost connection to SCADA server":**
- Verify `scada_server` name in hmi_screens.yml matches devices.yml
- Check SCADA server device is created and running
- Ensure HMI configuration was applied (check logs for "Configured HMI workstation")
