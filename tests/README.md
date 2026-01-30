# Test strategy and dependency order

My testing follows a strict, dependency‑driven strategy: Tests are written and executed in an order that mirrors the 
*causal structure* of the simulator.

The goal is to avoid:
- circular dependencies
- implicit coupling
- hidden test assumptions
- “integration tests pretending to be unit tests”

Once a layer is validated, it can be treated as *stable ground* for all layers above it.

## Core principles

- Lower layers must never import or depend on higher layers.
- Time, state, and physics are tested *before* behaviour.
- Devices are transport‑agnostic.
- Security and policy observe and gate behaviour; they do not define it.
- External attack proofs‑of‑concept treat the simulator as a *black box*.

No placeholders are used, but not all subsystems are wired at all levels.

## Dependency levels

### Level 0 – Time
_No dependencies_

- `SimulationTime`

Time must be deterministic, controllable, and globally consistent.
Everything else assumes this works correctly.

### Level 1 – Global coordination substrate
_Depends on Level 0_

- `SystemState`
- `NetworkSimulator`
- `ProtocolSimulator`
- `TCPProxy`

These provide scheduling, coordination, and transport simulation.
They contain no domain behaviour and no device logic.

### Level 2 – Shared state and data fabric
_Depends on Level 1_

- `DataStore`

This is the single source of truth for system and device state.
All higher layers read from and write to this fabric.

### Level 3 – Physics engines
_Depends on Level 2_

- `TurbinePhysics`
- `GridPhysics`
- `PowerFlow`

Physics modules are tested with:
- real time
- real state
- real data storage

No devices, protocols, or security logic are involved.
Once validated, physics behaviour is considered axiomatic.

### Level 4 – Core device abstraction
_Depends on Level 3_

- `BaseDevice`

This is the first point where time, state, and physics converge.
The device contract is locked at this level.

### Level 5 – Concrete devices
_Depends on Level 4_

Includes devices across zones:

- Control zone (PLCs, RTUs, safety controllers)
- Operations zone (HMI, engineering workstation, SCADA)
- Enterprise zone (historian, IEDs, controllers)

At this level:
- behaviour is semantic
- commands are abstract
- no protocol or transport assumptions exist

### Level 6 – Protocol semantics
_Depends on Level 5 and Level 1_

- Modbus, DNP3, IEC‑104, IEC‑61850, OPC UA, S7, etc.

Protocols translate between wire‑level meaning and device semantics.
They depend on network timing but not on security enforcement.

### Level 7 – Security and policy
_Depends on Level 6_

- Authentication
- Encryption
- Logging
- Anomaly detection

Security gates and observes behaviour.
It does not alter device or physics semantics.

### Level 8 – Adapters (real IO boundary)
_Depends on Level 7_

- Protocol adapters using real libraries and sockets

This is the simulator’s external boundary.
Everything below is internal and deterministic.

## Scenario and attack testing

### Internal scenarios (white‑box)

- May import simulator internals
- Used for assessment, validation, and controlled demonstrations
- Deterministic and suitable for CI

These scripts validate *causal chains*, not adversarial realism.

### External adversarial PoCs (black‑box)

- Run asynchronously
- Do **not** import simulator code
- Interact only via network interfaces and protocols
- May run from another terminal or machine

These scripts treat the simulator as an unknown ICS network and are used to produce convincing, realistic proofs‑of‑concept.

## Test layout

- `unit/` – Levels 0–4 (pure logic and invariants)
- `integration/` – Levels 5–7 (cross‑component behaviour)
- `functional/` – End‑to‑end internal scenarios
- `scripts/` – External attacker tooling (out of band)

## Design rule

If a test requires importing a higher‑level module to make a lower‑level test pass, the architecture is wrong.
Fix the architecture, not the test.
