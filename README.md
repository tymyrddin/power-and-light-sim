# UU Power & Light ICS Simulator under construction

Welcome to the *Unseen University Power & Light Co.* simulator — a deliberately engineered modelling and testing 
framework for industrial control systems (ICS) and operational technology (OT) environments of the kind described in 
our territory guides.

This simulator is not a toy. It is a *causally correct, layered, testable, and extendible environment* for exploring:

- physics‑aware devices like PLCs and RTUs
- time‑synchronised network behaviour
- common OT protocols (Modbus, DNP3, IEC‑104, IEC‑61850, OPC UA, S7, etc.)
- security and policy enforcement mechanisms  
- realistic internal scenarios and external adversarial proofs‑of‑concept

If you are familiar with OT documentation, from control room hierarchy to PLC risk characteristics, this engine is 
architected to reflect those realities in code and test strategy.

## Project overview

```
.
├── components/        # core simulation logic (devices, protocols, state, network, physics, security, time)
├── config/            # declarative YAML for simulation scenarios, protocols, networks, and devices
├── scripts/           # scenario scripts and PoC tooling (internal and external)
├── tests/             # unit, integration, and scenario tests
├── tools/             # support utilities (simulator manager, test clients)
├── pyproject.toml     # build, metadata, tooling dependencies
├── requirements.txt   # explicit runtime dependencies
├── LICENSE            # project licensing
└── README.md          # this document
````

This project is *actively under construction*. Its parts are designed to be useful early, but the whole is not yet 
complete. Expect some modules to feel more finished than others.

It helps to think of this simulator as *an engineer’s tinker bench*, where:

- devices (PLCs, HMIs, RTUs, IEDs) behave according to documented industrial logic
- physics modules model turbines and grid behaviour with real state and time
- protocols translate interactions into real‑world network semantics
- security layers observe and constrain without hiding the underlying behaviour

This mirrors the *key OT components* you might see in the field. From unattended substations to operator workstations, 
each with unique responsibilities and risks.

## Architecture and grounding

The simulator is designed around a strict **causal layering**:

1. **Time and orchestration**:   
   Everything depends on a single source of time with deterministic stepping.

2. **State fabric and data store**:   
   A consistent, shared state that all components read and write.

3. **Physics engines**:   
   Real physics modules (turbine dynamics, power flow, etc.) drive behaviour.

4. **Device layer**: 
   Abstract base devices and concrete implementations (PLCs, RTUs, safety controllers, HMIs, historians).

5. **Protocol semantics**:   
   High‑level protocol logic that defines what messages *mean*.

6. **Security and policy**:   
   Gateways that enforce authentication, encryption, logging, and anomaly detection.

7. **Adapters and IO**:   
   Real network stacks and protocol libraries form the external boundary.

8. **Scenarios and PoCs**: 
   - **Internal scripts:** panic‑tested, deterministic, white‑box validation
   - **External tools:** real network interaction, asynchronous, black‑box proofs‑of‑concept

This layered approach ensures clarity: *higher layers consume, not define, lower layers*. If a test imports something 
above its layer, the architecture needs reconsideration.

For a detailed testing strategy, see `tests/README.md`.

## Getting started

Install dependencies:

```bash
pip install -r requirements.txt
```

Set up your configuration (`config/`) to describe:

* target devices and zones
* network topology
* simulation parameters
* protocols and behaviour

Run unit and integration tests:

```bash
pytest tests/unit
pytest tests/integration
```

Run an internal scenario:

```bash
python scripts/assessment/example_scenario.py
```

Run an external PoC (from another terminal or machine):

```bash
python scripts/recon/your_poc.py
```

## Contributing

Do not hesitate. Everything is designed for community development:

* new devices
* protocol enhancements
* security rules
* physics models
* scenario libraries

*Before adding tests*, familiarise yourself with the dependency ordering in `tests/README.md`.

Please respect the layering: *fix the architecture, not the test*.


