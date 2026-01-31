# Network simulation

This directory contains the network topology and connectivity simulation components. These modules create realistic 
industrial network infrastructure that external security testers can interact with using standard tools and techniques.

## Overview

Industrial control systems use network segmentation to isolate critical infrastructure. The Purdue Model defines 
layers from field devices (Level 0-1) through control systems (Level 2-3) to enterprise networks (Level 4-5). 
This simulation implements that architecture, creating real TCP listeners that external attackers can discover and 
attempt to exploit.

The network components provide:
- **Realistic topology** - Multi-segment networks matching real industrial environments
- **Real TCP services** - Actual network listeners that respond to standard tools
- **Segmentation enforcement** - Blocks or allows connections based on network rules
- **Attack surface** - Dual-homed hosts, exposed services, misconfigurations to discover

## Components

### `network_simulator.py` - Network topology manager

Manages the simulated network topology and enforces segmentation rules.

**Purpose:**
- Define multiple network segments (plant, SCADA, corporate)
- Track which devices belong to which networks
- Maintain service registry (what's listening where)
- Enforce reachability rules (can source reach destination?)
- Validate configuration against registered devices

**Key Concepts:**

**Networks** - Isolated segments with VLAN tags and subnets:
```yaml
networks:
  - name: plant_network
    subnet: 192.168.1.0/24
    vlan: 10
    description: Field devices and PLCs
```

**Device Membership** - Which devices are on which networks:
```yaml
connections:
  plant_network:
    - turbine_plc_1
    - substation_plc_1
```

**Service Exposure** - What protocols/ports are listening:
```python
await net_sim.expose_service("turbine_plc_1", "modbus", 502)
```

**Reachability Rules** - Can source network reach destination?
```python
allowed = await net_sim.can_reach(
    src_network="corporate_network",
    dst_node="turbine_plc_1",
    protocol="modbus",
    port=502
)
```

**Integration:**
```python
from components.network.network_simulator import NetworkSimulator
from components.state.system_state import SystemState
from config.config_loader import ConfigLoader

system_state = SystemState()
config_loader = ConfigLoader()

# Create and load network topology
net_sim = NetworkSimulator(config_loader, system_state)
await net_sim.load()  # Loads config/network.yml

# Expose services as devices start
await net_sim.expose_service("turbine_plc_1", "modbus", 502)
await net_sim.expose_service("scada_server_1", "opcua", 4840)

# Query topology
networks = await net_sim.get_device_networks("turbine_plc_1")
services = await net_sim.get_device_services("turbine_plc_1")
```

### `protocol_simulator.py` - Protocol listener manager

Manages real TCP listeners for protocol servers with network segmentation enforcement.

**Purpose:**
- Create actual TCP listeners on specified ports
- Accept incoming connections from external clients
- Enforce network segmentation at connection time
- Route allowed connections to protocol handlers
- Track connection statistics

**How It Works:**

1. Register listeners for each protocol server
2. Start TCP sockets listening on real ports
3. When connection arrives, determine source network
4. Check if source can reach destination (via NetworkSimulator)
5. If allowed, pass connection to protocol handler
6. If denied, close connection and log denial

**Integration:**
```python
from components.network.protocol_simulator import ProtocolSimulator
from components.protocols.modbus_protocol import ModbusServerHandler

protocol_sim = ProtocolSimulator(net_sim)

# Register Modbus listener on turbine PLC
await protocol_sim.register(
    node="turbine_plc_1",
    network="plant_network",
    port=502,
    protocol="modbus",
    handler_factory=lambda: ModbusServerHandler(data_store, "turbine_plc_1")
)

# Register OPC UA listener on SCADA server
await protocol_sim.register(
    node="scada_server_1",
    network="scada_network",
    port=4840,
    protocol="opcua",
    handler_factory=lambda: OPCUAServerHandler(data_store, "scada_server_1")
)

# Start all listeners
await protocol_sim.start()

# External attackers can now:
# - Port scan to discover services
# - Connect using standard tools
# - Attempt exploitation
```

**Protocol Handler Requirements:**

Handlers must implement the `ProtocolHandler` interface:
```python
class ModbusServerHandler:
    async def serve(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle Modbus client connection."""
        while True:
            # Read Modbus request
            request = await reader.read(260)
            if not request:
                break
            
            # Process request, generate response
            response = self.process_modbus_request(request)
            
            # Send response
            writer.write(response)
            await writer.drain()
```

The handler receives an established connection and implements protocol-specific logic.

### `tcp_proxy.py` - Transparent TCP proxy

Provides transparent TCP proxying for testing and demonstration scenarios.

**Purpose:**
- Forward traffic from one port to another
- Useful for setting up test environments
- Demonstrates pivot/tunnel techniques
- No protocol awareness - pure TCP forwarding

**Use Cases:**

**1. Testing Protocol Implementations:**
```python
# Forward local port to simulator for testing
proxy = TCPProxy(
    listen_host="127.0.0.1",
    listen_port=5502,
    target_host="localhost",
    target_port=502
)
await proxy.start()

# Now test your Modbus client against localhost:5502
```

**2. Simulating Compromised Jump Host:**
```python
# Set up on simulated engineering workstation
# This demonstrates what attacker would achieve with socat/SSH tunnel
proxy = TCPProxy(
    listen_host="0.0.0.0",
    listen_port=8502,
    target_host="192.168.1.100",  # turbine_plc_1 on isolated network
    target_port=502
)
await proxy.start()

# External attacker can now reach turbine via workstation:8502
# Demonstrates lateral movement through dual-homed host
```

**3. Traffic Analysis:**
```python
# Add logging to proxy for traffic inspection
class LoggingProxy(TCPProxy):
    async def _pipe(self, reader, writer, direction):
        while True:
            data = await reader.read(self.buffer_size)
            if not data:
                break
            logger.info(f"{direction}: {data.hex()}")  # Log traffic
            writer.write(data)
            await writer.drain()
```

## Setting up network topology

### 1. Define networks in configuration

Edit `config/network.yml`:

```yaml
networks:
  - name: plant_network
    subnet: 192.168.1.0/24
    vlan: 10
    description: Purdue Level 1-2 - Field devices

  - name: scada_network
    subnet: 192.168.2.0/24
    vlan: 20
    description: Purdue Level 3 - Supervisory control

  - name: corporate_network
    subnet: 10.0.0.0/16
    vlan: 100
    description: Purdue Level 4-5 - Enterprise

connections:
  plant_network:
    - turbine_plc_1
    - turbine_plc_2
    - substation_plc_1
  
  scada_network:
    - scada_server_1
    - historian_1
    - engineering_workstation_1  # Dual-homed
    - substation_plc_1           # Dual-homed
  
  corporate_network:
    - engineering_workstation_1  # Dual-homed - pivot point!
```

### 2. Register devices in SystemState

```python
# Register devices before loading network config
await system_state.register_device(
    "turbine_plc_1", "turbine_plc", 1, ["modbus"]
)
await system_state.register_device(
    "engineering_workstation_1", "engineering_ws", 10, ["rdp", "ssh"]
)

# Load network topology (validates devices exist)
await net_sim.load()
```

### 3. Start protocol listeners

```python
# Expose services and register listeners
await net_sim.expose_service("turbine_plc_1", "modbus", 502)
await protocol_sim.register(
    node="turbine_plc_1",
    network="plant_network",
    port=502,
    protocol="modbus",
    handler_factory=ModbusHandler
)

await protocol_sim.start()  # All listeners now active
```

### 4. Verify setup

```python
# Check what external attacker will see
summary = await protocol_sim.get_summary()
print(f"Active listeners: {summary['listeners']['count']}")

for listener in summary['listeners']['details']:
    print(f"  {listener['node']}:{listener['port']} ({listener['protocol']})")
```

## What external attackers see

Once the simulation is running, external attackers interact with real network services:

### Discovery phase

```bash
# Port scanning (from attacker machine)
nmap -p- 192.168.2.100  # SCADA server
nmap -p 502 192.168.1.0/24  # Scan for Modbus

# Service enumeration
nmap -sV -p 502 192.168.1.100  # Identify Modbus
nmap -p 4840 --script opcua-info 192.168.2.100  # OPC UA details
```

### Exploitation phase

```bash
# Use standard tools (no simulator imports!)
msfconsole
use auxiliary/scanner/scada/modbusdetect
set RHOSTS 192.168.1.100
run

# Custom exploits
python modbus_exploit.py --target 192.168.1.100:502
python iec104_fuzzer.py --target 192.168.1.101:2404
```

### Lateral movement

```bash
# After compromising engineering workstation
ssh engineer@192.168.2.50

# Set up tunnel to isolated network (attacker uses socat, not TCPProxy!)
socat TCP-LISTEN:8502,fork TCP:192.168.1.100:502

# Now access plant network from corporate network
python modbus_client.py --target 192.168.2.50:8502
```

## Network segmentation scenarios

### Scenario A: Properly segmented

```yaml
# Plant network isolated from corporate
connections:
  plant_network:
    - turbine_plc_1
  corporate_network:
    - workstation_1
```

**Result:** Direct attacks from corporate to plant fail:
```bash
# From attacker machine on corporate network
telnet 192.168.1.100 502  # Connection refused or timeout
```

Logs show:
```
WARNING: Connection denied: 10.0.1.50:49152 (corporate_network) -> turbine_plc_1:502 (network segmentation)
```

### Scenario B: Dual-homed device (Misconfiguration)

```yaml
connections:
  plant_network:
    - turbine_plc_1
  scada_network:
    - engineering_workstation_1
  corporate_network:
    - engineering_workstation_1  # Bridges networks!
```

**Result:** Workstation is pivot point for lateral movement:
```bash
# Compromise workstation via phishing/RDP
ssh engineer@workstation  # Now on device with plant access

# Access plant network
telnet 192.168.1.100 502  # SUCCESS - workstation can reach plant
```

### Scenario C: Exposed historian

```yaml
connections:
  scada_network:
    - historian_1
  corporate_network:
    - historian_1  # Allowed for business reporting - security risk!
```

**Result:** Historian accessible from corporate for data exfiltration:
```bash
# From corporate network
curl http://historian:8080/api/tags  # Get list of all sensors
curl http://historian:8080/api/data?tag=turbine_rpm  # Exfiltrate operational data
```

## Monitoring and debugging

### Check network topology

```python
# Verify networks loaded
summary = await net_sim.get_summary()
print(f"Networks: {summary['networks']['names']}")
print(f"Devices: {summary['devices']['count']}")
print(f"Services: {summary['services']['count']}")

# Find dual-homed devices (pivot points)
for device in await system_state.get_all_devices():
    networks = await net_sim.get_device_networks(device)
    if len(networks) > 1:
        print(f"PIVOT POINT: {device} on {networks}")
```

### Monitor connections

```python
# Protocol simulator tracks all connections
stats = await protocol_sim.get_summary()

for listener in stats['listeners']['details']:
    print(f"{listener['node']}:{listener['port']}")
    print(f"  Active: {listener['active_connections']}")
    print(f"  Total: {listener['total_connections']}")
    print(f"  Denied: {listener['denied_connections']}")
```

### Review logs

```
INFO: Loaded 3 network(s): ['plant_network', 'scada_network', 'corporate_network']
INFO: Mapped 12 device(s) to networks
INFO: Exposed service: turbine_plc_1:502 (modbus) on networks {'plant_network'}
INFO: Listener started: turbine_plc_1:502 (modbus)
INFO: Connection accepted: 192.168.2.10:54321 (scada_network) -> turbine_plc_1:502
WARNING: Connection denied: 10.0.1.50:49152 (corporate_network) -> turbine_plc_1:502
DEBUG: Reachability allowed: plant_network -> turbine_plc_1:502 (modbus)
```

## Testing different configurations

### Test 1: Complete isolation

```yaml
# No device on multiple networks
connections:
  plant_network:
    - turbine_plc_1
  scada_network:
    - scada_server_1
  corporate_network:
    - workstation_1
```

**Expected:** No lateral movement possible, all cross-network attacks blocked.

### Test 2: Firewall bypass (SCADA bridging)

```yaml
# SCADA server bridges plant and corporate
connections:
  plant_network:
    - turbine_plc_1
  scada_network:
    - scada_server_1
  corporate_network:
    - scada_server_1  # Bridge point
```

**Expected:** Compromising SCADA server allows plant access.

### Test 3: Real-world complexity

```yaml
# Multiple bridge points (realistic but insecure)
connections:
  plant_network:
    - turbine_plc_1
    - substation_plc_1
  scada_network:
    - scada_server_1
    - historian_1
    - engineering_workstation_1
    - substation_plc_1  # Bridge 1
  corporate_network:
    - engineering_workstation_1  # Bridge 2
    - historian_1                # Bridge 3
```

**Expected:** Multiple attack paths available.

## Integration with simulation lifecycle

```python
async def start_simulation():
    # 1. Initialise state management
    system_state = SystemState()
    data_store = DataStore(system_state)
    
    # 2. Register devices
    await register_all_devices(system_state)
    
    # 3. Set up network
    config_loader = ConfigLoader()
    net_sim = NetworkSimulator(config_loader, system_state)
    await net_sim.load()
    
    # 4. Create protocol simulator
    protocol_sim = ProtocolSimulator(net_sim)
    
    # 5. Register all protocol listeners
    await register_protocol_listeners(protocol_sim, data_store)
    
    # 6. Start network services
    await protocol_sim.start()
    
    # 7. Start physics engines, time simulation, etc.
    # ...
    
    logger.info("Simulation ready for external testing")
    
async def stop_simulation():
    # Graceful shutdown
    await protocol_sim.stop()
    logger.info("All network services stopped")
```

## Performance considerations

### Connection limits

Each protocol listener can handle many concurrent connections:
- Asyncio efficiently manages thousands of connections
- Connection overhead is minimal (dict lookups)
- Consider OS file descriptor limits for very large tests

### Port conflicts

Ensure no port conflicts:
```python
# Check before registering
services = await net_sim.get_all_services()
if ("turbine_plc_1", 502) in services:
    logger.warning("Port 502 already in use on turbine_plc_1")
```

### Network I/O

All network components use real TCP sockets:
- Traffic happens at network speed (not simulation time)
- Large data transfers don't block simulation
- Protocol timeouts use wall-clock time

## Common issues

### Service not reachable

**Problem:** External client can't connect

**Check:**
1. Service exposed? `await net_sim.get_device_services("device")`
2. Listener started? `await protocol_sim.get_summary()`
3. Network segmentation? Check device membership
4. Firewall on host? `netstat -tulpn | grep 502`

### Wrong source network

**Problem:** Connections allowed/denied incorrectly

The simulator assumes external connections come from `corporate_network`. For accurate testing:
- Run attack tools from actual separate machine
- Configure network interfaces to match topology
- Or modify `_determine_source_network()` in protocol_simulator.py

### Dual-homed device not working

**Problem:** Device on multiple networks but can't reach both

**Check:** Device must be listed in multiple network connections:
```yaml
connections:
  network_a:
    - device_1
  network_b:
    - device_1  # Same device on both
```

## TL;DR

1. **Load topology before exposing services** - `net_sim.load()` first
2. **Validate devices exist** - Pass SystemState to NetworkSimulator
3. **Match config to reality** - Use realistic IP ranges and VLANs
4. **Test from external machines** - Don't import simulator in attack scripts
5. **Monitor denied connections** - Review logs for unexpected blocks
6. **Document pivot points** - Clearly mark dual-homed devices
7. **Clean shutdown** - Always `await protocol_sim.stop()`

## References

- Purdue Enterprise Reference Architecture (PERA)
- IEC 62443 Network Segmentation Guidelines
- NIST SP 800-82 Guide to ICS Security
- Industrial network topology best practices

---

*"The network is properly segmented. Unless you're the engineering workstation. Or the SCADA historian. Or that 
Windows XP box nobody remembers installing."*  
— UU P&L Network Architecture Review, 2024