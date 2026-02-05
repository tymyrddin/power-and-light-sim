# Development roadmap

*Feature development and technical improvements*

## Current state

**Code:**
- 2,949 Python files
- Python 3.12, type-checked (mypy strict)
- 238 test files (60%+ coverage requirement)
- GitHub Actions CI/CD
- Black, isort, ruff for code quality

**Implemented and active:**
- Protocols: Modbus TCP, S7comm, OPC UA, EtherNet/IP
- Devices: Turbine PLCs, Reactor PLCs, SCADA servers, Safety PLCs
- Physics: Turbine, Reactor
- Security components: Authentication, encryption, logging, anomaly detection
- 49 attack scripts (recon, exploitation, analysis)
- Workshop materials: Pentesting challenges, remediation challenges

**Implemented but inactive:**
- Protocols: DNP3, IEC 60870-5-104, IEC 61850 (GOOSE and MMS), Modbus RTU
- Devices: 3 substation RTUs, IEDs, Historian, SIEM, IDS, HVAC PLC, L-space monitor
- Physics: Grid (frequency, voltage), Power flow, HVAC
- Few scripts for power grid scenarios

**Missing:**
- State persistence (save/restore)
- Web interface
- Protocol adapters not fully integrated
- Grid/substation workshop materials
- Some security features (IEC 61850 security, DNP3 SAv5)

## Development priorities

### High priority: Activate existing code

#### 1. Grid and substation scenario (2-3 weeks)

**What's already there:**
- DNP3 protocol fully implemented
- IEC 60870-5-104 protocol implemented
- IEC 61850 (GOOSE and MMS) implemented
- 3 substation RTUs configured (substation_rtu_1, 2, 3)
- IEDs with protection functions
- Grid physics (frequency, voltage, load-generation balance)
- Power flow calculations
- Scripts: **ZERO functional scripts** (2 basic recon scripts that don't use protocols)

**What needs to be built:**

**Integration and testing**
- Verify DNP3 works end-to-end (master-outstation communication)
- Verify IEC 104 works end-to-end
- Verify IEC 61850 GOOSE messaging works
- Test grid physics responds to substation changes
- Document protocol configurations

**Attack scripts (all need to be written from scratch)**
- DNP3 reconnaissance script (enumerate outstations, points)
- DNP3 breaker control script (open/close breakers remotely)
- DNP3 point manipulation script (analog/binary inputs)
- IEC 104 reconnaissance script (enumerate devices, IOAs)
- IEC 104 command injection script (control commands)
- IEC 61850 reconnaissance script (enumerate IEDs, GOOSE messages)
- IEC 61850 GOOSE injection script (inject false GOOSE messages)
- IEC 61850 MMS manipulation script (modify settings via MMS)
- Grid frequency manipulation script (via coordinated attacks)
- Cascading failure demonstration script (multi-substation attack)

**Estimated: 10-15 scripts, ~3-4 days of development**

**Workshop materials**
- Create power grid challenges document
- Update student guide with DNP3/IEC104/IEC61850 sections
- Create remediation challenges for grid (if applicable)
- Test with volunteer users

**Deliverables:**
- docs/grid-challenges.md (new)
- docs/grid-student-guide.md (new)
- 10-15 new scripts in scripts/grid/ (all from scratch)
- Updated overview.md mentioning grid scenario

**Realistic effort: 3-4 weeks, not 3 weeks**
- Week 1: Verify protocols work, write reconnaissance scripts
- Week 2: Write exploitation scripts
- Week 3: Write workshop materials
- Week 4: Test and refine

#### 2. HVAC and building automation scenario (1 week)

**What's already there:**
- HVAC PLC (library_hvac_plc) configured
- HVAC physics engine implemented
- L-space monitor (unique Discworld element)
- Scripts: **ZERO** (none exist)

**What needs to be built:**

**Integration**
- Verify HVAC PLC works with Modbus
- Verify HVAC physics responds to setpoint changes
- Test L-space stability responds to temperature/humidity

**Attack scripts (all need to be written from scratch)**
- HVAC reconnaissance script (enumerate zones, setpoints)
- Temperature manipulation script (change setpoints via Modbus)
- Humidity manipulation script
- L-space destabilisation script (cause instability via environmental changes)
- Library environmental attack script (coordinated temp/humidity/pressure)

**Estimated: 5 scripts, ~1-2 days of development**

**Workshop materials**
- Create building automation challenges
- Emphasise different risk profile (comfort vs safety)
- L-space angle (uniquely Discworld)

**Deliverables:**
- docs/building-automation-challenges.md (new)
- 5 new scripts in scripts/building/ (all from scratch)
- Integration with existing workshops

**Realistic effort: 1-2 weeks**
- Days 1-2: Verify HVAC PLC and physics work
- Days 3-4: Write scripts
- Days 5-7: Workshop materials and testing

#### 3. Historian and enterprise zone scenarios (1 week)

**What's already there:**
- Historian device implemented
- SIEM system implemented
- IDS system implemented
- Scripts: 3 exist (historian_exfiltration.py, siem_correlation_test.py, ids_detection_test.py)

**What these scripts actually do:**
- historian_exfiltration.py: Actually works, extracts historical data
- siem_correlation_test.py: Tests SIEM correlation rules
- ids_detection_test.py: Tests if IDS detects attacks

**Status: Partially implemented, needs expansion**

**What needs to be built:**

**Scripts (expand existing 3 scripts)**
- Historian data mining scripts (more sophisticated queries)
- Historian timeline reconstruction script
- SIEM evasion techniques (avoid correlation)
- SIEM alert flooding script
- IDS bypass methods (protocol camouflage, timing attacks)
- IDS signature analysis script
- Log tampering scripts (modify audit trails)
- Anti-forensics scripts

**Estimated: 5-8 new scripts, ~2-3 days of development**

**Workshop materials**
- Enterprise zone challenges
- Detection vs evasion focus
- Blue team perspective scenarios

**Deliverables:**
- docs/enterprise-challenges.md (new)
- 5-8 new scripts in scripts/enterprise/ (expanding from 3 existing)
- Detection-focused workshop materials

**Realistic effort: 1-2 weeks**
- Days 1-3: Enhance existing scripts, write new ones
- Days 4-5: Workshop materials
- Days 6-7: Testing and refinement

### Medium priority: Technical improvements

#### 4. State persistence (1 week)

**Currently:** State is in-memory, lost on restart

**Implement:**
```python
# components/state/persistence.py
class StatePersistence:
    async def export_state(self) -> dict:
        """Export SystemState to JSON-serializable dict."""

    async def import_state(self, state_dict: dict):
        """Restore SystemState from dict."""

    async def save_to_file(self, filepath: str):
        """Save state to JSON file."""

    async def load_from_file(self, filepath: str):
        """Load state from JSON file."""
```

**Add CLI:**
```bash
python tools/simulator_manager.py --save-state checkpoint1.json
python tools/simulator_manager.py --load-state checkpoint1.json
```

**Benefits:**
- Save progress between sessions
- "Start from this state" for workshops
- Testing with consistent conditions
- Snapshot interesting states

**Effort:** 1 week?

**Deliverables:**
- components/state/persistence.py
- CLI integration
- Tests
- Documentation

#### 5. Protocol adapter refactoring (2 weeks)

**Currently:** Protocol code is scattered, some adapters not fully integrated

**Goal:** Consistent adapter pattern for all protocols

**Pattern:**
```python
# components/protocols/base_adapter.py
class ProtocolAdapter:
    async def start(self):
        """Start protocol server."""

    async def stop(self):
        """Stop protocol server."""

    async def handle_request(self, request):
        """Process incoming request."""

    async def send_response(self, response):
        """Send response to client."""
```

**Apply to all protocols:**
- Modbus: Already good
- S7: Refactor to pattern
- OPC UA: Refactor to pattern
- DNP3: Integrate fully
- IEC 104: Integrate fully
- IEC 61850: Integrate fully

**Benefits:**
- Consistent codebase
- Easier to add new protocols
- Better error handling
- Simpler testing

**Effort:** 3 weeks?

**Deliverables:**
- Refactored adapters
- Updated tests
- Documentation

#### 6. Enhanced security components (1-2 weeks)

**Currently:** Basic auth, encryption, logging, anomaly detection exist

**Add:**

**DNP3 Secure Authentication v5:**
```python
# components/security/encryption.py already has DNP3Crypto class
# Integrate with DNP3 protocol adapter
# Add challenge-response authentication
# Test with scripts
```

**IEC 61850 security:**
```python
# Add GOOSE message authentication
# Add MMS encryption support
# Integrate with IED devices
```

**Protocol-level filtering:**
```python
# components/security/protocol_filter.py
class ProtocolFilter:
    def allow_modbus_function(self, function_code: int, source_ip: str) -> bool:
        """Check if Modbus function code allowed from source."""

    def allow_s7_operation(self, operation: str, source_ip: str) -> bool:
        """Check if S7 operation allowed from source."""
```

**Effort:** 1-2 weeks depending on depth

**Deliverables:**
- Enhanced security components
- Integration with protocols
- Remediation challenge updates
- Tests and documentation

#### 7. Better logging and observability (1 week)

**Currently:** Text logs only

**Add:**

**Structured logging:**
```python
# Use existing ICSLogger more consistently
# Add correlation IDs
# Add context (which attack script, which user)
# Machine-readable format (JSON)
```

**Metrics export:**
```python
# components/metrics/
# Prometheus metrics
# Track: requests/sec per protocol, attacks detected, state changes
```

**Simple dashboard:**
```python
# Flask app serving metrics
# Real-time protocol activity
# Attack detection feed
# System state visualization
```

**Effort:** 1 week

**Deliverables:**
- Structured logging throughout
- Metrics export
- Simple monitoring dashboard
- Documentation

### Lower priority: Nice to have

#### 8. More realistic HMI simulation (2 weeks)

**Currently:** No visual HMI, just scripts

**Add:**
```python
# components/hmi/
# Simple web-based SCADA screens
# Show turbine speed, reactor temp, grid frequency
# Buttons for operator actions
# Alarms and events display
```

**Benefits:**
- More realistic demonstration
- See operator perspective during attacks
- Workshop demos more visual

**Complexity:** Medium-high

**Effort:** 2 weeks

#### 9. Packet capture integration (3-4 days)

**Add:**
```python
# components/capture/
# Record all protocol traffic
# Export to PCAP format
# Wireshark-compatible
```

**Benefits:**
- Traffic analysis training
- Wireshark practice
- Forensics scenarios

**Effort:** 3-4 days

#### 10. Advanced physics (ongoing)

**Enhance existing:**
- More realistic turbine dynamics
- Reactor decay heat and cooling
- Grid inertia and frequency response
- Cascading failure propagation

**Add new:**
- Thermal stress and equipment damage
- Vibration monitoring
- Chemistry and corrosion (reactor)

**Complexity:** High (requires domain expertise)

**Priority:** Low (current physics sufficient for security training)

### Community and ecosystem

#### 11. Contribution guidelines (2-3 days)

**Create:**
- CONTRIBUTING.md
- CODE_OF_CONDUCT.md
- Issue templates
- PR templates
- Architecture documentation
- Development setup guide

**Effort:** 2-3 days

#### 12. Plugin architecture (1-2 weeks)

**Enable:**
```python
# components/plugins/
# Load custom devices
# Load custom protocols
# Load custom scenarios
```

**Benefits:**
- Community contributions easier
- Custom scenarios without forking
- Industry-specific extensions

**Complexity:** Medium

**Effort:** 1-2 weeks

#### 13. Docker development environment (1-2 days)

**Add:**
```dockerfile
# Dockerfile.dev
FROM python:3.12
# Dev tools: pytest, black, mypy, etc.
# VSCode remote development support
# Hot reload for development
```

**Benefits:**
- Consistent dev environment
- New contributors onboard faster
- Works on any OS

**Effort:** 1-2 days

## Recommended sequence

### Activate existing code
**Goal:** Use what's already built (but scripts need writing)

**Reality check:**
- Protocols: Implemented ✓
- Devices: Configured ✓
- Physics: Implemented ✓
- Scripts: **Nearly all need to be written from scratch**
- Workshop materials: **All need to be written from scratch**

1. **Grid and substation scenario (4 weeks)**
   - Most impactful (completely new attack surface)
   - Shows different risk profile
   - Protocols exist, zero functional scripts
   - 10-15 scripts to write
   - Full workshop materials to create

2. **HVAC/building automation scenario (1-2 weeks)**
   - Different risk profile
   - Unique L-space angle
   - 5 scripts to write
   - Workshop materials to create

3. **Historian and enterprise zone (1-2 weeks)**
   - Rounds out attack scenarios
   - Detection focus
   - 3 scripts exist, need 5-8 more
   - Workshop materials to create

4. **State persistence (1 week)**
   - Enables better workshop flow
   - Testing benefits
   - Implementation needed

**Realistic total: 7-9 weeks, not 6 weeks**

**Result:** Three major new scenarios, 20-30 new scripts, significant workshop expansion

### Technical quality
**Goal:** Solidify codebase

5. Protocol adapter refactoring
   - Cleaner codebase
   - Easier maintenance

6. Enhanced security components
   - DNP3 SAv5, IEC 61850 security
   - More remediation options

7. Logging and observability
   - Better debugging
   - Monitoring for public service

8. Documentation and contribution guidelines
   - Community readiness

9. Docker dev environment
   - Easier for contributors

**Result:** Production-quality codebase, contributor-friendly

### Polish and expand
**Goal:** Nice-to-haves and ecosystem

10. Realistic HMI
    - Better demos
    - More immersive

11. Packet capture
    - Forensics training

12. Plugin architecture
    - Community extensions

13. Advanced physics (if interest)
    - More realistic consequences

**Result:** Feature-complete, extensible platform

### Community and maintenance
**Goal:** Sustainable project

- Regular dependency updates
- Bug fixes
- User feedback integration
- Workshop material refinement
- Conference presentations
- Academic partnerships

## Technical debt to address

**High priority:**
1. Inconsistent protocol adapter patterns
2. Some protocols not fully integrated (DNP3, IEC104, IEC61850)
3. Limited test coverage in some areas
4. Documentation gaps

**Medium priority:**
5. Some code duplication in protocol handlers
6. Inconsistent error handling
7. Limited input validation in some protocols
8. Hard-coded configuration values

**Low priority:**
9. Performance optimisations (works fine now)
10. Code organisation (mostly good)

## Breaking changes to consider

**Version 0.2 considerations:**
- State format change (if adding persistence)
- Protocol adapter interface change (if refactoring)
- Configuration file format (if unifying)

**Approach:**
- Maintain backwards compatibility
- Deprecation warnings before removal
- Migration guides
- Semantic versioning

## Resource requirements

**Development time (realistic estimates):**
- Activate existing code: 7-9 weeks = 280-360 hours
- Technical quality improvements: 6-8 weeks = 240-320 hours
- Polish and expand: 6-8 weeks = 240-320 hours
- **Total: 760-1000 hours**
- Ongoing maintenance = 10-20 hours/month

**Skills needed:**
- Python (async, type hints)
- OT protocols (Modbus, DNP3, S7, OPC UA, etc.)
- Docker and containerisation
- Security (authentication, encryption)
- Physics simulation (basic)
- Technical writing

**Can be done by:**
- Solo developer (6-9 months full-time)
- Small team (3-4 months)
- Community contributions (1-2 years, organic growth)

Most features can be built incrementally. Don't need to do everything before launching. Ship grid scenario, then HVAC, then enterprise, etc.

## Getting started

**Immediate next steps:**
1. Verify DNP3 protocol works end-to-end (can master communicate with outstation?)
2. Write first DNP3 reconnaissance script (enumerate outstations and points)
3. Write first DNP3 exploitation script (control breaker remotely)
4. Create first grid challenge document
5. Test with 2-3 volunteer users
6. Iterate based on feedback
