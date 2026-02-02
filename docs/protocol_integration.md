# Protocol Integration Guide

How devices integrate with protocol servers to expose network attack surfaces.

## Architecture Overview

The current architecture uses **centralized protocol server management** where SimulatorManager creates network servers and syncs them with device memory maps.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         SimulatorManager                                │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                       Device Layer                              │    │
│  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐         │    │
│  │  │ TurbinePLC   │   │ ReactorPLC   │   │ SafetyPLC    │         │    │
│  │  │              │   │              │   │              │         │    │
│  │  │ memory_map{} │   │ memory_map{} │   │ memory_map{} │         │    │
│  │  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘         │    │
│  └─────────┼──────────────────┼──────────────────┼─────────────────┘    │
│            │                  │                  │                      │
│            └──────────────────┴──────────────────┘                      │
│                               │                                         │
│                    _sync_protocol_servers()                             │
│                      (bidirectional sync)                               │
│                               │                                         │
│            ┌──────────────────┴──────────────────┐                      │
│            │                  │                  │                      │
│  ┌─────────┼──────────────────┼──────────────────┼──────────────────┐   │
│  │         ▼                  ▼                  ▼   Network Servers│   │
│  │  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐          │   │
│  │  │ ModbusTCP    │   │ ModbusTCP    │   │ ModbusTCP    │          │   │
│  │  │ Server       │   │ Server       │   │ Server       │          │   │
│  │  │ port 10502   │   │ port 10503   │   │ port 10504   │          │   │
│  │  └──────┬───────┘   └──────┬───────┘   └──────┬───────┘          │   │
│  └─────────┼──────────────────┼──────────────────┼──────────────────┘   │
└────────────┼──────────────────┼──────────────────┼──────────────────────┘
             │                  │                  │
═════════════╧══════════════════╧══════════════════╧═══════════ (NETWORK)
             │                  │                  │
             ▼                  ▼                  ▼
    ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
    │  SCADA Client   │  │  mbtget Tool    │  │   Metasploit    │
    │  (HMI)          │  │  (attacker)     │  │   (pen-test)    │
    └─────────────────┘  └─────────────────┘  └─────────────────┘
```

## Current implementation

### Phase 1: Device configuration (devices.yml)

Devices declare protocols they support:

```yaml
# config/devices.yml
- name: hex_turbine_plc
  type: turbine_plc
  device_id: 1
  protocols:
    modbus:
      host: 0.0.0.0
      port: 10502
      unit_id: 1

- name: reactor_plc
  type: reactor_plc
  device_id: 10
  protocols:
    s7:                    # Multiple protocols!
      host: 0.0.0.0
      port: 102
      rack: 0
      slot: 2
    modbus:
      host: 0.0.0.0
      port: 10504
      unit_id: 10
```

### Phase 2: Simulator initialisation

SimulatorManager orchestrates device and protocol server creation:

```python
# tools/simulator_manager.py

async def initialise(self):
    # 1-4. Create physics engines, networks, devices
    await self._create_physics_engines(config)
    await self._create_networks(config)
    await self._create_devices(config)

    # 5-6. Configure SCADA/HMI
    await self._configure_scada_servers(config)
    await self._configure_hmi_workstations(config)

    # 7. Create protocol servers for devices (NEW!)
    await self._expose_services(config)
```

### Phase 3: Protocol server creation (_expose_services)

SimulatorManager creates network servers based on device protocol configs:

```python
# tools/simulator_manager.py

async def _expose_services(self, config: dict[str, Any]) -> None:
    """Start protocol servers for devices based on config."""
    from components.network.servers import ModbusTCPServer

    devices = config.get("devices", [])

    for device_cfg in devices:
        device_name = device_cfg.get("name")
        protocols_cfg = device_cfg.get("protocols", {})

        for proto_name, proto_cfg in protocols_cfg.items():
            if proto_name == "modbus":
                # Create Modbus TCP server
                server = ModbusTCPServer(
                    host=proto_cfg.get("host", "0.0.0.0"),
                    port=proto_cfg.get("port"),
                    unit_id=proto_cfg.get("unit_id", 1),
                    num_coils=64,
                    num_discrete_inputs=64,
                    num_holding_registers=256,
                    num_input_registers=256,
                )

                await server.start()  # Opens real TCP socket!

                # Store reference
                server_key = f"{device_name}:modbus"
                self.protocol_servers[server_key] = server

                logger.info(f"Started Modbus TCP server: {device_name}:{port}")
```

**Key points:**
- ✅ Protocol servers are **separate objects** not owned by devices
- ✅ One device can have **multiple protocol servers** (e.g., reactor_plc has both S7 and Modbus)
- ✅ Servers open **real network ports** immediately
- ✅ No "simulator mode" vs "real mode" - always real

### Phase 4: Memory map synchronisation (_sync_protocol_servers)

SimulatorManager syncs device memory maps with protocol servers every simulation cycle:

```python
# tools/simulator_manager.py

async def _sync_protocol_servers(self) -> None:
    """Sync device registers with protocol servers.

    Device → Server: Push telemetry (input_registers, discrete_inputs)
    Server → Device: Pull commands (coils, holding_registers)
    """
    for device_name, device in self.device_instances.items():
        # Find protocol server for this device
        server_key = f"{device_name}:modbus"
        server = self.protocol_servers.get(server_key)

        if not server:
            continue

        try:
            memory_map = device.memory_map

            # Extract telemetry registers from device
            input_registers = {}
            discrete_inputs = {}

            for key, value in memory_map.items():
                if key.startswith("input_registers["):
                    addr = int(key.split("[")[1].split("]")[0])
                    input_registers[addr] = value
                elif key.startswith("discrete_inputs["):
                    addr = int(key.split("[")[1].split("]")[0])
                    discrete_inputs[addr] = value

            # Device → Server (telemetry)
            if input_registers:
                await server.sync_from_device(input_registers, "input_registers")
            if discrete_inputs:
                await server.sync_from_device(discrete_inputs, "discrete_inputs")

            # Server → Device (commands)
            coil_addrs = [int(k.split("[")[1].split("]")[0])
                         for k in memory_map.keys()
                         if k.startswith("coils[")]

            if coil_addrs:
                min_addr = min(coil_addrs)
                max_addr = max(coil_addrs)
                coils_from_server = await server.sync_to_device(
                    min_addr,
                    max_addr - min_addr + 1,
                    "coils"
                )

                for addr, value in coils_from_server.items():
                    device.memory_map[f"coils[{addr}]"] = value

            # Same for holding_registers...

        except Exception as e:
            logger.error(f"Failed to sync {device_name}: {e}")
```

**Key points:**
- ✅ **Centralized sync** - SimulatorManager coordinates
- ✅ **Bidirectional** - Telemetry flows out, commands flow in
- ✅ **Every cycle** - Runs during simulation update loop
- ✅ **Device agnostic** - Same sync for PLCs, RTUs, safety controllers

## Device implementation requirements

### Minimal device requirements

Devices only need to maintain a memory_map - **no protocol code needed**:

```python
# components/devices/control_zone/plc/turbine_plc.py

class TurbinePLC(BasePLC):
    def __init__(self, device_name, device_id, data_store, ...):
        super().__init__(device_name, device_id, data_store, ...)
        # NO protocol adapter creation needed!

    async def _initialise_memory_map(self) -> None:
        """Just define the memory map structure."""
        self.memory_map = {
            # Telemetry (read-only to external)
            "discrete_inputs[0]": False,  # Running
            "discrete_inputs[1]": False,  # Governor online
            "input_registers[0]": 0,      # Speed RPM
            "input_registers[1]": 0,      # Power MW*10

            # Commands (writable by external)
            "coils[0]": False,            # Governor enable
            "coils[1]": False,            # Emergency trip
            "holding_registers[0]": 3600, # Speed setpoint
        }

    async def _scan_cycle(self) -> None:
        """PLC logic - protocol sync happens automatically."""
        # Read from physics
        turbine_telem = self.turbine_physics.get_telemetry()
        self.memory_map["input_registers[0]"] = turbine_telem["shaft_speed_rpm"]

        # Execute control logic
        if self.memory_map["coils[0]"]:  # Governor enabled
            # Control logic...
            pass

        if self.memory_map["coils[1]"]:  # Emergency trip
            self.turbine_physics.trigger_emergency_trip()

        # NO protocol sync code needed - SimulatorManager handles it!
```

### Optional: DEFAULT_SETUP for documentation

Devices can optionally define DEFAULT_SETUP for reference (not functionally required):

```python
class TurbinePLC(BasePLC):
    # Reference only - shows initial memory map structure
    DEFAULT_SETUP = {
        "coils": {
            0: False,  # Governor enable
            1: False,  # Emergency trip
        },
        "discrete_inputs": {
            0: False,  # Running
            1: False,  # Governor online
        },
        "input_registers": {
            0: 0,      # Speed RPM
            1: 0,      # Power MW*10
        },
        "holding_registers": {
            0: 3600,   # Speed setpoint
        },
    }
```

## Protocol-specific implementation

### Modbus TCP (most devices)

**Location:** `components/network/servers/modbus_tcp_server.py`

**Features:**
- Opens real TCP socket on specified port
- Implements Modbus function codes (1, 2, 3, 4, 5, 6, 15, 16)
- Sync methods: `sync_from_device()`, `sync_to_device()`
- Based on pymodbus 3.11.4 simulator

**Supported Devices:**
- PLCs (turbine, reactor, HVAC)
- Safety controllers
- RTUs (with Modbus gateway)
- SCADA servers

### S7 Protocol (Siemens PLCs)

**Location:** `components/protocols/s7/server.py`

**Status:** Partial implementation - server exists but not yet wired

**Future:** Will follow same pattern as Modbus in `_expose_services()`

### DNP3 (Utility RTUs)

**Location:** `components/protocols/dnp3/`

**Status:** In progress

## External Attack Tool Integration

Protocol servers expose **real network attack surfaces**:

### Terminal 1: Run Simulation
```bash
$ python tools/simulator_manager.py

Protocol servers running: 7
  - hex_turbine_plc:modbus (port 10502)
  - hex_turbine_safety_plc:modbus (port 10503)
  - reactor_plc:modbus (port 10504)
```

### Terminal 2: Attack with Real Tools

**Reconnaissance:**
```bash
$ nmap -p 10500-10600 localhost
$ mbtget -r -a 0 -n 10 localhost:10502
```

**Malicious write:**
```bash
$ mbtget -w -a 1 -v 1 localhost:10502  # Trigger emergency trip
```

**Python attack script:**
```python
from pymodbus.client import AsyncModbusTcpClient

client = AsyncModbusTcpClient("localhost", port=10502)
await client.connect()

# Read telemetry
speed = await client.read_input_registers(0, 1)

# Malicious write
await client.write_coil(1, True)  # Emergency trip
```

## Adding new protocol support

### Step 1: Implement Protocol Server

Create server in `components/network/servers/`:

```python
# components/network/servers/dnp3_server.py

class DNP3Server:
    def __init__(self, host, port, outstation_address, ...):
        self.host = host
        self.port = port
        # ...

    async def start(self):
        # Open network socket
        pass

    async def sync_from_device(self, data, data_type):
        # Device → Server
        pass

    async def sync_to_device(self, address, count, data_type):
        # Server → Device
        return {}
```

### Step 2: Add to _expose_services()

```python
# tools/simulator_manager.py

async def _expose_services(self, config):
    # ...
    for proto_name, proto_cfg in protocols_cfg.items():
        if proto_name == "dnp3":
            from components.network.servers import DNP3Server

            server = DNP3Server(
                host=proto_cfg.get("host"),
                port=proto_cfg.get("port"),
                outstation_address=proto_cfg.get("outstation_address"),
            )

            await server.start()
            self.protocol_servers[f"{device_name}:dnp3"] = server
```

### Step 3: Add Sync Logic to _sync_protocol_servers()

```python
# tools/simulator_manager.py

async def _sync_protocol_servers(self):
    for device_name, device in self.device_instances.items():
        # Handle DNP3 servers
        dnp3_key = f"{device_name}:dnp3"
        dnp3_server = self.protocol_servers.get(dnp3_key)

        if dnp3_server:
            # Device → DNP3 sync
            await dnp3_server.sync_from_device(...)

            # DNP3 → Device sync
            commands = await dnp3_server.sync_to_device(...)
```

## Architecture Benefits

**✅ Separation of concerns:**
- Devices: Control logic and physics interaction
- Protocol servers: Network exposure and protocol encoding
- SimulatorManager: Orchestration and sync

**✅ Multiple protocols per device:**
- Reactor PLC can speak both S7 and Modbus
- No inheritance complexity

**✅ Realistic attack surface:**
- Real network ports for external tools
- Industry-standard protocols
- Observable impact on simulation

**✅ Testability:**
- Devices can be tested without protocols
- Protocols can be tested without devices
- Integration testing validates sync

## Related Documentation

- [SCADA Wiring Guide](scada_wiring.md) - SCADA tag database configuration
- [README.md](../README.md) - External attack examples
- [Network Architecture](../README.md#network-attack-surface) - Attack surface overview
