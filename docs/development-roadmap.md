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
- Some recon scripts exist

**What needs to be built:**

**Integration and testing**
- Verify DNP3 works end-to-end (master-outstation communication)
- Verify IEC 104 works end-to-end
- Verify IEC 61850 GOOSE messaging works
- Test grid physics responds to substation changes
- Document protocol configurations

**Attack scripts**
- DNP3 reconnaissance script
- DNP3 breaker control script
- IEC 104 command injection script
- IEC 61850 GOOSE injection script
- Grid frequency manipulation script
- Cascading failure demonstration script

**Workshop materials**
- Create power grid challenges document
- Update student guide with DNP3/IEC104/IEC61850 sections
- Create remediation challenges for grid (if applicable)
- Test with volunteer users

**Deliverables:**
- doc grid-challenges.md
- doc grid-student-guide.md
- 8-10 new scripts in scripts/grid/
- Updated overview.md mentioning grid scenario

#### 2. HVAC and building automation scenario (1 week)

**What's already there:**
- HVAC PLC (library_hvac_plc) configured
- HVAC physics engine implemented
- L-space monitor (unique Discworld element)

**What needs to be built:**

**Integration**
- Verify HVAC PLC works with Modbus
- Verify HVAC physics responds to setpoint changes
- Test L-space stability responds to temperature/humidity

**Attack scripts**
- HVAC reconnaissance script
- Temperature manipulation script
- L-space destabilisation script

**Workshop materials**
- Create building automation challenges
- Emphasise different risk profile (comfort vs safety)
- L-space angle (uniquely Discworld)

**Deliverables:**
- doc building-automation-challenges.md
- 3-5 new scripts in scripts/building/
- Integration with existing workshops

#### 3. Historian and enterprise zone scenarios (1 week)

**What's already there:**
- Historian device implemented
- SIEM system implemented
- IDS system implemented
- One historian exfiltration script exists
- SIEM and IDS test scripts exist

**What needs to be built:**

**Scripts**
- Historian data mining scripts
- SIEM evasion techniques
- IDS bypass methods
- Log tampering scripts

**Workshop materials**
- Enterprise zone challenges
- Detection vs evasion focus
- Blue team perspective scenarios

**Deliverables:**
- doc enterprise-challenges.md
- 5-8 new scripts in scripts/enterprise/
- Detection-focused workshop materials

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
**Goal:** Use what's already built

1. Grid and substation scenario
   - Most impactful (completely new attack surface)
   - Shows different risk profile
   - Code mostly exists

2. HVAC/building automation scenario
   - Quick win
   - Different risk profile
   - Unique L-space angle

3. Historian and enterprise zone
   - Rounds out attack scenarios
   - Detection focus

4. State persistence
   - Enables better workshop flow
   - Testing benefits

**Result:** Three major new scenarios, better workshop experience

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

**Development time:**
- 720 hours?
- Quarter 4: Ongoing maintenance = 10-20 hours/month

**Skills needed:**
- Python (async, type hints)
- OT protocols (Modbus, DNP3, S7, OPC UA, etc.)
- Docker and containerisation
- Security (authentication, encryption)
- Physics simulation (basic)
- Technical writing

**Can be done by:**
- Solo developer (1 year timeline)
- Small team (6 months timeline)
- Community contributions (organic growth)
