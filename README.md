# UU Power & Light ICS Simulator

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

- **Physics-aware devices**: PLCs and RTUs with realistic scan cycles (10-100ms)
- **Time-synchronised behaviour**: deterministic stepping for reproducible scenarios
- **OT protocols**: Modbus, DNP3, IEC 60870-5-104, IEC 61850, OPC UA, S7comm
- **Network segmentation**: control zones, DMZs, and firewall simulation
- **Security layers**: authentication, logging, and anomaly detection
- **Scenario framework**: both white-box internal tests and black-box external PoCs

## Project structure

```
.
├── components/
│   ├── devices/       # PLCs, RTUs, HMIs, historians, safety controllers
│   ├── network/       # network simulation, TCP proxy, protocol simulation
│   ├── physics/       # turbine dynamics, power flow, thermal models
│   ├── protocols/     # Modbus, DNP3, IEC-104, S7, OPC UA semantics
│   ├── security/      # logging, authentication, anomaly detection
│   ├── state/         # shared state fabric and data store
│   └── time/          # deterministic time orchestration
├── config/            # YAML scenarios, network topologies, device definitions
├── scripts/
│   ├── assessment/    # internal white-box scenario scripts
│   └── recon/         # external black-box PoC tools
├── tests/
│   ├── unit/          # component-level tests
│   ├── integration/   # cross-component tests
│   └── scenario/      # end-to-end scenario validation
├── tools/             # simulator manager, test clients
└── docs/              # additional documentation
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

For detailed testing strategy, see `tests/README.md`.

## Getting started

```bash
# Clone and install
git clone https://github.com/tymyrddin/power-and-light-sim.git
cd power-and-light-sim
pip install -r requirements.txt

# Run tests
pytest tests/unit                    # Component tests
pytest tests/unit -m "not slow"      # Skip slower tests
pytest tests/integration             # Cross-component tests

# Run a scenario
python scripts/assessment/example_scenario.py
```

Configuration files in `config/` define:
- Device definitions and control zones
- Network topology and segmentation
- Protocol bindings and behaviour
- Simulation parameters

## Example use cases

**Reconnaissance PoC**: Scan the simulated network, enumerate exposed services, fingerprint PLCs:
```bash
python scripts/recon/network_scan.py --target control_zone
```

**Protocol exploitation**: Test Modbus function code abuse against the turbine controller:
```bash
python scripts/assessment/modbus_fc_test.py --device hex_turbine_plc
```

**Detection testing**: Validate that anomaly detection catches unauthorised writes:
```bash
pytest tests/scenario/test_unauthorized_write_detection.py
```

## Status

This project is under active development. Some modules are more complete than others:

| Component | Status |
|-----------|--------|
| Core devices (PLC, RTU, HMI) | Functional |
| Network simulation | Functional |
| Modbus protocol | Functional |
| DNP3 protocol | In progress |
| Physics engines | In progress |
| Security logging | Functional |
| Scenario framework | Partial |

## Contributing

Contributions welcome:

- New device types (IEDs, PMUs, relays)
- Protocol implementations
- Physics models (thermal, hydraulic, electrical)
- Security rules and detection logic
- Scenario libraries

Before adding tests, read `tests/README.md` for dependency ordering.
Respect the layering: *fix the architecture, not the test*.

## Disclaimer

This simulator is for **authorised security research, education, and testing only**.
Use it to develop and validate PoCs in a safe environment before engaging with real systems
under proper authorisation.

The authors take no responsibility for misuse. If you're testing real ICS/SCADA systems,
ensure you have explicit written permission and understand the physical consequences.

## Licence

Public domain ([Unlicense](LICENSE)). Do what you will.

## References

- [UU P&L Company Overview](https://red.tymyrddin.dev/docs/power/territory/company)
- [ICS Components Guide](https://red.tymyrddin.dev/docs/power/territory/components)
- [Testing Strategy](tests/README.md)

---

*"The thing about electricity is, once it's out of the bottle, you can't put it back."*
— Archchancellor Ridcully (probably)
