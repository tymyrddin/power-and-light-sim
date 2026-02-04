# UU Power & Light ICS Simulator

![Version](https://img.shields.io/badge/status-active%20development-orange)
![Python](https://img.shields.io/badge/python-3.12+-blue)
[![codecov](https://codecov.io/github/ninabarzh/power-and-light-sim/graph/badge.svg?token=O4L0ABOK5W)](https://codecov.io/github/ninabarzh/power-and-light-sim)

*"Ankh-Morpork's quietly indispensable utility, operating from repurposed university basements and one building that 
insists it was never meant to be a building at all."*

Welcome to the [Unseen University Power & Light Co.](https://red.tymyrddin.dev/docs/power/territory/company) simulator.

This is a causally correct, layered, and testable simulation of an industrial control system (ICS) environment,
designed for developing convincing security proofs-of-concept *without risking production systems*.

## Why this exists

Real ICS/SCADA environments are:
- **Fragile**: a misplaced packet can cause physical consequences
- **Legacy-ridden**: decades-old systems with no security considerations
- **High-stakes**: blackouts, floods, or worse

This simulator lets you explore attack paths, test detection mechanisms, and develop PoCs against a realistic
OT environment that won't leave a city in the dark.

## What we're simulating

The [UU P&L infrastructure](https://red.tymyrddin.dev/docs/power/territory/components) includes:

| System                     | Description                                                         | Control Hardware                          |
|----------------------------|---------------------------------------------------------------------|-------------------------------------------|
| **Hex Steam Turbine**      | Main power generation with hardwired logic and polling loops        | Allen-Bradley ControlLogix (1998)         |
| **Alchemical Reactor**     | Volatile energy conversion with chemical and metaphysical variables | Siemens S7-400 (2003)                     |
| **Library Environmental**  | Temperature, humidity, and magical stability control                | Schneider Modicon (1987) + Modbus gateway |
| **City-Wide Distribution** | SCADA managing substations across Ankh-Morpork                      | RTUs via DNP3, Wonderware HMI             |

Plus the supporting cast: historians storing 10+ years of operational data, safety PLCs with redundant sensors,
protective relays, PMUs, and yes, a Windows 98 machine that's been collecting turbine data for 25 years.

## Capabilities

This simulator provides:

- **Physics-aware devices**: PLCs, RTUs, and safety controllers with realistic scan cycles (25-100ms)
- **Time-synchronised behaviour**: deterministic stepping for reproducible scenarios
- **Real network attack surfaces**: Protocol servers on actual TCP/IP ports for external tool access
- **OT protocols**: Modbus TCP/RTU, DNP3, IEC 60870-5-104, IEC 61850, OPC UA, S7comm
- **Network segmentation**: control zones, DMZs, and firewall simulation
- **Security layers**: authentication, logging, and anomaly detection
- **External attack tools**: Use mbtget, nmap, Metasploit against running simulation
- **Scenario framework**: both white-box internal tests and black-box external PoCs

## Project structure

```
.
├── components/
│   ├── devices/       # PLCs, RTUs, HMIs, historians, safety controllers
│   ├── network/       # Network simulation, attack surfaces (protocol servers)
│   ├── physics/       # Turbine dynamics, power flow, thermal models
│   ├── protocols/     # Modbus, DNP3, IEC-104, S7, OPC UA semantics
│   ├── security/      # Logging, authentication, anomaly detection
│   ├── state/         # Shared state fabric and data store
│   └── time/          # Deterministic time orchestration
├── config/            # YAML device configs, network topologies, SCADA tag databases
├── scripts/
│   ├── assessment/    # Internal white-box scenario scripts
│   └── recon/         # External black-box PoC tools
├── tests/
│   ├── unit/          # Component-level tests
│   ├── integration/   # Cross-component tests
│   └── scenario/      # End-to-end scenario validation
├── tools/             # Simulator manager, test clients
└── docs/              # Architecture documentation, wiring guides
```

Think of this as an engineer's workbench where:

- **Devices** behave according to real industrial logic and timing
- **Physics** models drive actual state changes (not just data)
- **Protocols** translate interactions into proper network semantics
- **Security** observes and constrains without hiding underlying behaviour

## Architecture

The simulator follows a strict **causal layering**: higher layers consume, never define, lower layers:

```
┌─────────────────────────────────────────────────────────────────┐
│  8. Scenarios & PoCs                                            │
│     Internal scripts (white-box) │ External tools (black-box)   │
├─────────────────────────────────────────────────────────────────┤
│  7. Adapters & IO                                               │
│     Real network stacks, protocol libraries, external boundary  │
├─────────────────────────────────────────────────────────────────┤
│  6. Security & Policy                                           │
│     Authentication, encryption, logging, anomaly detection      │
├─────────────────────────────────────────────────────────────────┤
│  5. Protocol Semantics                                          │
│     What Modbus/DNP3/S7 messages mean, not just their bytes     │
├─────────────────────────────────────────────────────────────────┤
│  4. Device Layer                                                │
│     PLCs, RTUs, HMIs, historians, safety controllers            │
├─────────────────────────────────────────────────────────────────┤
│  3. Physics Engines                                             │
│     Turbine dynamics, power flow, thermal models                │
├─────────────────────────────────────────────────────────────────┤
│  2. State Fabric                                                │
│     Consistent shared state that all components read/write      │
├─────────────────────────────────────────────────────────────────┤
│  1. Time & Orchestration                                        │
│     Single time source, deterministic stepping                  │
└─────────────────────────────────────────────────────────────────┘
```

This maps roughly to the Purdue Model levels you'd find in real ICS environments: from Level 0 field devices
up through control, operations, and enterprise zones.

### Network Attack Surface

The simulator exposes **real network services** on TCP/IP ports that external tools can target:

```
┌────────────────────────────────────────────────────────┐
│  External Attack Tools (Terminal 2)                    │
│  - nmap: Port scanning                                 │
│  - mbtget: Modbus client                               │
│  - Metasploit: SCADA exploits                          │
│  - Custom scripts: pymodbus, python-snap7              │
└───────────────────┬────────────────────────────────────┘
                    │ Real TCP/IP connections
                    ↓
┌────────────────────────────────────────────────────────┐
│  Network Protocol Servers (components/network/servers) │
│  - ModbusTCPServer: ports 10502-10506                  │
│  - S7Server: port 102                                  │
│  - DNP3Server: ports 20000-20002                       │
└───────────────────┬────────────────────────────────────┘
                    │ Memory map sync
                    ↓
┌────────────────────────────────────────────────────────┐
│  Device Logic (components/devices)                     │
│  - TurbinePLC, ReactorPLC, SafetyPLCs                  │
│  - SCADA servers, HMI workstations                     │
│  - Historians, engineering workstations                │
└───────────────────┬────────────────────────────────────┘
                    │ Physics interaction
                    ↓
┌────────────────────────────────────────────────────────┐
│  Physics Engines (components/physics)                  │
│  - TurbinePhysics, ReactorPhysics, GridPhysics         │
└────────────────────────────────────────────────────────┘
```

This architecture allows **realistic attack demonstrations** where:
1. Simulation runs in Terminal 1 with exposed services
2. Attacker tools run in Terminal 2 using standard ICS tooling
3. Attacks have observable impact on simulated physical processes

For detailed testing strategy, see [tests/README.md](tests/README.md).
For SCADA wiring documentation, see [docs/SCADA_WIRING.md](docs/scada_wiring.md).

## Getting started

```bash
# Clone and install
git clone https://github.com/tymyrddin/power-and-light-sim.git
cd power-and-light-sim
pip install -r requirements.txt

# Run the simulator
python tools/simulator_manager.py

# The simulation opens real network ports:
# - Modbus TCP: ports 10502-10506 (PLCs, safety controllers)
# - S7: port 102 (reactor PLC)
# - DNP3: ports 20000-20002 (RTUs)

# Run tests (in another terminal)
pytest tests/unit                    # Component tests
pytest tests/unit -m "not slow"      # Skip slower tests
pytest tests/integration             # Cross-component tests
```

Configuration files in `config/` define:
- Device definitions and control zones (`devices.yml`)
- Network topology and segmentation (`network.yml`)
- Protocol bindings and behavior (`protocols.yml`)
- SCADA tag databases (`scada_tags.yml`)
- HMI screen configurations (`hmi_screens.yml`)
- Simulation parameters (`simulation.yml`)

## Example use cases

### External Attack Simulation (Two Terminal Approach)

**Terminal 1: Run the simulation**
```bash
$ python tools/simulator_manager.py

# Output shows exposed attack surfaces:
Protocol servers running: 7
  - hex_turbine_plc:modbus (port 10502)
  - hex_turbine_safety_plc:modbus (port 10503)
  - reactor_plc:modbus (port 10504)
  - library_hvac_plc:modbus (port 10505)
  ...
```

**Terminal 2: Reconnaissance with real ICS tools**
```bash
# Scan for exposed services
$ nmap -p 10500-10600 localhost

# Enumerate Modbus devices
$ mbtget -r -a 0 -n 10 localhost:10502  # Read turbine PLC registers

# Fingerprint device
$ nmap -sV -p 10502 localhost
```

**Terminal 2: Malicious write attack**
```bash
# Trigger emergency trip on turbine
$ mbtget -w -a 1 -v 1 localhost:10502  # Write to coil[1] = Emergency trip

# Watch Terminal 1 for impact:
# [SIM: 5.23s] [WARNING] TurbinePLC: Emergency trip commanded!
# [SIM: 5.23s] [CRITICAL] TurbineSafetyPLC: FORCING SAFE STATE
```

**Terminal 2: Python-based attack script**
```python
# Custom attack using pymodbus
from pymodbus.client import AsyncModbusTcpClient

client = AsyncModbusTcpClient("localhost", port=10502)
await client.connect()

# Read current turbine speed
speed = await client.read_input_registers(0, 1)
print(f"Turbine speed: {speed.registers[0]} RPM")

# Malicious setpoint change
await client.write_register(0, 5000)  # Dangerous overspeed setpoint
```

### Internal Assessment Scripts

**Detection testing**: Validate that anomaly detection catches unauthorized writes:
```bash
pytest tests/scenario/test_unauthorized_write_detection.py
```

**Protocol exploitation**: Test Modbus function code abuse:
```bash
python scripts/assessment/modbus_fc_test.py --device hex_turbine_plc
```

## Status

This project is under active development. Current implementation status:

| Component                          | Status         | External Access          |
|------------------------------------|----------------|--------------------------|
| Core devices (PLC, RTU, HMI)       | ✅ Functional   | Via Modbus TCP           |
| Safety controllers (SIL2/SIL3)     | ✅ Functional   | Via Modbus TCP           |
| SCADA servers (tag database)       | ✅ Functional   | Via Modbus TCP           |
| Historian (10-year data retention) | ✅ Functional   | Via OPC UA               |
| Network attack surfaces            | ✅ Functional   | Real TCP ports           |
| Modbus TCP/RTU protocol            | ✅ Functional   | mbtget, pymodbus         |
| S7 protocol                        | 🔄 Partial     | Not exposed yet          |
| DNP3 protocol                      | 🔄 In progress | Not exposed yet          |
| Physics engines (turbine, reactor) | ✅ Functional   | Via device PLCs          |
| Security logging                   | ✅ Functional   | ICS log format           |
| External tool testing              | ✅ Ready        | nmap, mbtget, Metasploit |

**Legend:** ✅ = Complete, 🔄 = In Progress, ❌ = Not Started

## Contributing

Contributions welcome:

- New device types (IEDs, PMUs, relays)
- Protocol implementations
- Physics models (thermal, hydraulic, electrical)
- Security rules and detection logic
- Scenario libraries

Before adding tests, read [tests/README.md](tests/README.md) for dependency ordering.
Respect the layering: *fix the architecture, not the test*.

## Disclaimer

This simulator is for *authorised security research, education, and testing only*.
Use it to develop and validate PoCs in a safe environment before engaging with real systems
under proper authorisation.

The authors take no responsibility for misuse. If you're testing real ICS/SCADA systems,
make sure you have explicit written permission and understand the physical consequences.

## License and usage

This project is licensed under the [Polyform Noncommercial License](LICENSE).

### What this means in practice

You are welcome to use this software for:

- Learning and experimentation
- Academic or independent research
- Defensive security research
- Developing and validating proof-of-concepts
- Incident response exercises
- Non-commercial red/blue team simulations

You may **not** use this software for:

- Paid workshops or training
- Consultancy or advisory services
- Internal corporate training
- Commercial product development

If you want to use this project in a paid or commercial context, a commercial license is required.  
See [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md) for details.

### Why this license exists

This project is actively developed and maintained to support realistic security research and training.  
The license ensures that:

- Security research remains accessible
- Defensive knowledge can spread
- Commercial exploitation is fair and sustainable

If you are unsure whether your use case is commercial, ask. [Ambiguity is solvable](https://tymyrddin.dev/contact/); silence is not.

## References

- [UU P&L Company Overview](https://red.tymyrddin.dev/docs/power/territory/company)
- [ICS Components Guide](https://red.tymyrddin.dev/docs/power/territory/components)
- [Testing Strategy](tests/README.md)

---

*"The thing about electricity is, once it's out of the bottle, you can't put it back."*
— Archchancellor Ridcully (probably)
