# ICS Simulator Configuration

This directory contains modular YAML configuration files for the Unseen University Power & Light Co. ICS simulator. The configuration is split into focused files to make the simulator easier to understand, maintain, and extend.

## Configuration Files

### `devices.yml` - Device Definitions

Defines all industrial control system devices in the simulation. Each device represents a component you might find at UU P&L's facility.

**Structure:**
```yaml
devices:
  - name: <unique_device_name>
    type: <device_type>
    device_id: <unique_id>
    description: <what this device does>
    location: <physical location>
    protocols:
      <protocol_name>:
        adapter: <adapter_to_use>
        <protocol_specific_settings>
```

**Supported Device Types:**

- **`turbine_plc`** - Steam turbine controller
  - Controls main steam turbines
  - Manages turbine speed, temperature, vibration monitoring
  - Example: Hex Steam Turbine Control System
  
- **`substation_plc`** - Electrical substation controller
  - Manages circuit breakers, transformers, protection relays
  - Monitors voltage, current, power quality
  - Often bridges multiple network segments
  
- **`scada_server`** - SCADA master station
  - Supervisory control and data acquisition
  - Aggregates data from field devices
  - Provides HMI interfaces for operators
  
- **`modbus_plc`** - Generic Modbus-capable PLC
  - Multipurpose industrial controller
  - Supports standard Modbus protocol
  
- **`rtu_modbus`** - Remote Terminal Unit with Modbus
  - Remote monitoring and control
  - Typically deployed in unmanned locations
  - Used for wide-area monitoring (substations, pump stations)
  
- **`rtu_c104`** - RTU with IEC 60870-5-104
  - Common in European electrical utilities
  - Supports IEC 104 protocol
  
- **`ied`** - Intelligent Electronic Device
  - Protective relays, power meters, PMUs
  - Used in electrical substations
  
- **`sis_controller`** - Safety Instrumented System
  - Independent safety system
  - Monitors for hazardous conditions
  - Takes automatic protective action
  - **Critical: Test with extreme caution**

**Example Device Definition:**
```yaml
- name: turbine_plc_1
  type: turbine_plc
  device_id: 1
  description: Main steam turbine PLC controlling Hex turbine in Hall A
  location: Turbine Hall A
  protocols:
    modbus:
      adapter: pymodbus_3114
      host: localhost
      port: 15020
      device_id: 1
      simulator: true
```

### `network.yml` - Network Topology

Defines the network architecture and how devices connect. Reflects the Purdue Model common in industrial environments.

**Structure:**
```yaml
networks:
  - name: <network_name>
    subnet: <CIDR_notation>
    vlan: <vlan_id>
    description: <network purpose>

connections:
  <network_name>:
    - <device_name>
    - <device_name>
```

**Typical Network Segments:**

- **Plant/Process Network** (Level 1-2)
  - Field devices, PLCs, RTUs
  - Direct process control
  - Example: `192.168.1.0/24`
  
- **SCADA/Supervisory Network** (Level 3)
  - SCADA servers, historians, HMIs
  - Supervisory control
  - Example: `192.168.2.0/24`
  
- **DMZ/Integration Network** (Level 3.5)
  - Firewall-protected zone
  - Data historians, jump hosts
  - Bridges OT and IT
  
- **Corporate Network** (Level 4-5)
  - Engineering workstations, business systems
  - Enterprise applications
  - Example: `10.0.0.0/16`

**Example Network Configuration:**
```yaml
networks:
  - name: plant_network
    subnet: 192.168.1.0/24
    vlan: 10
    description: Main plant control network - Purdue Level 1-2

  - name: scada_network
    subnet: 192.168.2.0/24
    vlan: 20
    description: SCADA supervisory network - Purdue Level 3

connections:
  plant_network:
    - turbine_plc_1
    - substation_plc_1
  
  scada_network:
    - scada_server_1
    - substation_plc_1  # Bridges networks
```

### `protocols.yml` - Protocol Settings

Defines protocol-specific global settings and adapter configurations. Each industrial protocol has its own characteristics and parameters.

**Structure:**
```yaml
protocols:
  <protocol_name>:
    <global_protocol_settings>

adapters:
  <adapter_name>:
    library: <python_library>
    version: <version>
    features:
      - <feature_list>
```

**Supported Protocols:**

- **Modbus TCP/RTU**
  - Most common industrial protocol
  - Simple, widely supported
  - No built-in security
  - Settings: timeout, retries, unit_id range
  
- **IEC 60870-5-104 (IEC 104)**
  - Common in power utilities
  - Used for SCADA communications
  - Settings: T1, T2, T3 timeouts, K and W parameters
  
- **S7 (Siemens)**
  - Proprietary Siemens PLC protocol
  - Settings: rack, slot, PDU size
  
- **OPC UA**
  - Modern, secure industrial protocol
  - Settings: security mode, security policy, session timeout
  
- **DNP3**
  - Common in North American utilities
  - Used for SCADA and RTU communications
  - Supports authentication extensions
  
- **IEC 61850 (MMS and GOOSE)**
  - Substation automation standard
  - GOOSE for fast peer-to-peer messaging
  - MMS for client-server communications

**Available Adapters:**

- `pymodbus_3114` - Modbus TCP/RTU (pymodbus library)
- `c104_221` - IEC 104 (c104 library)
- `snap7_202` - Siemens S7 (snap7 library)
- `opcua_asyncua_118` - OPC UA (asyncua library)
- `dnp3_adapter` - DNP3 protocol
- `iec61850_mms_adapter` - IEC 61850 MMS
- `iec61850_goose_adapter` - IEC 61850 GOOSE

**Example Protocol Configuration:**
```yaml
protocols:
  modbus:
    default_timeout: 3.0
    default_retries: 3
    unit_id_range: [1, 247]
  
  iec104:
    default_t1: 15  # Connection timeout
    default_t2: 10  # Acknowledgment timeout
    default_t3: 20  # Test frame timeout
    default_k: 12   # Max unacknowledged APDUs
    default_w: 8    # Acknowledgment window

adapters:
  pymodbus_3114:
    library: pymodbus
    version: 3.11.4
    features:
      - tcp_server
      - simulator
      - async_support
```

### `simulation.yml` - Runtime Parameters

Controls simulation behavior, logging, monitoring, and scenarios.

**Structure:**
```yaml
simulation:
  name: <simulation_name>
  description: <description>
  version: <version>
  
  runtime:
    update_interval: <seconds>
    realtime: <true/false>
    time_acceleration: <multiplier>
  
  logging:
    level: <DEBUG/INFO/WARNING/ERROR>
    file: <log_file_path>
    console: <true/false>
  
  monitoring:
    enabled: <true/false>
    metrics_port: <port>
    health_check_interval: <seconds>
  
  scenarios:
    - name: <scenario_name>
      description: <description>
      enabled: <true/false>
      trigger_time: <seconds>
```

**Example Simulation Configuration:**
```yaml
simulation:
  name: UU P&L ICS Simulation
  description: Industrial control system simulation for power generation facility
  version: 1.0.0
  
  runtime:
    update_interval: 1.0  # Physics and state updates per second
    realtime: true        # Run at real-world speed
    time_acceleration: 1.0
  
  logging:
    level: INFO
    file: logs/simulation.log
    console: true
  
  scenarios:
    - name: normal_operation
      description: Steady-state plant operation
      enabled: true
    
    - name: turbine_fault
      description: Simulated bearing failure
      enabled: false
      trigger_time: 300
```

## Configuration Workflow

### 1. Define Your Devices

Start by listing all the devices you want to simulate. Think about what exists at a real facility:

```yaml
# devices.yml
devices:
  # Control layer - the PLCs doing the work
  - name: turbine_plc_1
    type: turbine_plc
    # ... configuration
  
  # Supervisory layer - SCADA and monitoring
  - name: scada_server_1
    type: scada_server
    # ... configuration
  
  # Remote monitoring - RTUs in substations
  - name: substation_rtu_1
    type: rtu_c104
    # ... configuration
```

### 2. Design Your Network

Map out how devices connect. Consider network segmentation and the Purdue Model:

```yaml
# network.yml
networks:
  - name: field_network
    subnet: 192.168.1.0/24
    description: Level 1-2 process control
  
  - name: supervisory_network
    subnet: 192.168.2.0/24
    description: Level 3 SCADA

connections:
  field_network:
    - turbine_plc_1
  supervisory_network:
    - scada_server_1
```

### 3. Configure Protocols

Set global defaults and adapter preferences:

```yaml
# protocols.yml
protocols:
  modbus:
    default_timeout: 3.0
    default_retries: 3

adapters:
  pymodbus_3114:
    library: pymodbus
    version: 3.11.4
```

### 4. Set Runtime Parameters

Control how the simulation runs:

```yaml
# simulation.yml
simulation:
  runtime:
    update_interval: 1.0
    realtime: true
  
  logging:
    level: INFO
```

## Real-World Examples

The UU P&L facility demonstrates typical industrial control system architecture:

### Hex Steam Turbine Control System
- **Device Type:** `turbine_plc`
- **Key Protocols:** Modbus TCP
- **Security Characteristics:** 1990s-era Allen-Bradley ControlLogix, no authentication, programming port exposed
- **Testing Considerations:** Critical production system, test with extreme caution

### Bursar's Alchemical Reactor Controls
- **Device Type:** `sis_controller` with associated `substation_plc`
- **Key Protocols:** Modbus, possibly OPC UA
- **Security Characteristics:** Safety system - independent from BPCS
- **Testing Considerations:** **DO NOT ACTIVELY TEST** - observation and documentation review only

### Library Environmental Management System
- **Device Type:** `modbus_plc` with Modbus gateway
- **Key Protocols:** Modbus (retrofitted to 1987 system)
- **Security Characteristics:** Ancient system, no native network security
- **Testing Considerations:** System predates cybersecurity concepts, handle delicately

### City-Wide Distribution SCADA
- **Device Type:** `scada_server` with multiple `rtu_c104` units
- **Key Protocols:** IEC 104, DNP3, Modbus
- **Security Characteristics:** Cellular communications, weak authentication, city-level impact
- **Testing Considerations:** Test RTUs individually, verify communication security

## Security Testing Notes

When configuring devices for security testing scenarios:

1. **Identify critical systems** - Mark safety systems, mark devices controlling hazardous processes
2. **Document dependencies** - Note which devices depend on others
3. **Establish baselines** - Record normal operating parameters
4. **Plan segmentation** - Test network isolation and firewall rules
5. **Never test safety systems actively** - Observe, document, recommend, but don't break

## Adding New Devices

To add a new device to the simulation:

1. Add device definition to `devices.yml`
2. Assign it to appropriate network(s) in `network.yml`
3. Ensure required protocol adapters are defined in `protocols.yml`
4. Implement device class in `components/devices/` if it's a new type
5. Update this README with device type documentation

## Loading Configuration

The `ConfigLoader` class automatically loads and merges all YAML files:

```python
from config.config_loader import ConfigLoader

loader = ConfigLoader(config_dir="config")
config = loader.load_all()

# Access configuration
devices = config["devices"]
networks = config["networks"]
protocol_settings = config["protocol_settings"]
simulation = config["simulation"]
```

## Best Practices

- **One concern per file** - Don't mix device definitions with network topology
- **Use descriptive names** - `turbine_plc_1` not `device_1`
- **Document locations** - Physical location helps with security testing
- **Comment liberally** - Future you will thank present you
- **Version control everything** - Track configuration changes
- **Test configurations** - Validate YAML before deployment
- **Follow Purdue Model** - Proper network segmentation matters

## References

- [UU P&L Company Overview](https://red.tymyrddin.dev/docs/power/territory/company)
- [Key Components in OT Systems](https://red.tymyrddin.dev/docs/power/territory/components)
- [Common OT Protocols](https://red.tymyrddin.dev/docs/power/territory/protocols)
- [Purdue Model Reference](https://red.tymyrddin.dev/docs/power/territory/purdue)

---

*"Most days, UU P&L keeps Ankh-Morpork running. Most days."*
