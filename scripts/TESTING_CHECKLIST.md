# ICS PoC scripts - Testing checklist

Track validation status of all PoC scripts against the simulator.

## 📊 SUMMARY

**Total Scripts: 46** (38 original + 8 vulnerability assessment)
- ✅ Fully tested & working: **22** (48%)
- ✅ Updated following confirmed pattern: **22** (48%)
- ✅ All protocols supported: Modbus, S7, OPC UA, EtherNet/IP
- ⚠️ S7 scripts require sudo (privileged port 102)

**By Category:**
- Recon: 5 working, 2 now unblocked (7 total)
- Discovery: 4 tested + 14 updated (18 total)
- Exploitation: 2 tested + 9 updated (11 total)
- Analysis: 3 tested offline tools (3 total)
- **Vulnerability Assessment: 8 tested (8 total) ← NEW**

## TESTED & WORKING (22/46)

### Recon

(5/7 working)

- [x] turbine_recon.py - Modbus telemetry ✓
- [x] modbus_identity_probe.py - Device ID ✓ (⚠️ pymodbus bug)
- [x] raw-tcp-probing.py - Basic connectivity ✓
- [x] connect-remote-substation.py - OPC UA ✓
- [x] query-substation-controller.py - TCP probe ✓ (needs sudo)

### Discovery

(4 tested, 14 updated)

Tested & Working:

- [x] scan_unit_ids.py - Unit ID enumeration ✓ (⚠️ all IDs respond)
- [x] modbus_memory_census.py - Memory map ✓
- [x] check_input_registers.py - Input register discovery ✓
- [x] test_write_permissions.py - Write testing ✓

Updated for pymodbus 3.x (same pattern):

- [~] check_discrete_points.py - Updated (device_id → slave_id)
- [~] compare_mirror_values.py - Updated
- [~] compare_unit_id_memory.py - Updated
- [~] correlate_analogue_discrete.py - Updated
- [~] decode_register_0_type.py - Updated
- [~] monitor_discrete_pattern.py - Updated
- [~] multi_id_snapshot.py - Updated
- [~] poll_register_0.py - Updated
- [~] sparse_input_register_scan.py - Updated
- [~] sparse_modbus_scan.py - Updated
- [~] track_counter_groups.py - Updated
- [~] verify_memory_access.py - Updated
- [~] discover_pymodbus_api.py - (needs review)
- [~] minimal-modbus-request-frame.py - (needs review)

### Exploitation

(2 tested, others follow same pattern)

Tested & Working:

- [x] turbine_overspeed_attack.py - Gradual overspeed attack ✓
- [x] turbine_emergency_stop.py - Emergency stop attack ✓

Same pymodbus pattern (not individually tested):

- [~] modbus_shutdown_attack_demo.py
- [~] historian_exfiltration.py
- [~] covert_exfiltration.py
- [~] plc_logic_extraction.py (uses pycomm3 for Allen-Bradley)
- [~] modbus_turbine_simulator.py
- [~] protocol_camouflage.py
- [~] anomaly_bypass_test.py
- [~] logging_gap_test.py

Already has reports directory:

- [x] ids_detection_test.py - Updated earlier
- [x] siem_correlation_test.py - Updated earlier
- [x] ladder-logic-analysis.py - Demonstrates config analysis findings ✓

### Analysis

(3 offline analysis tools)

All working (offline tools, don't connect to simulator):
- [x] id-rogues-by-mac-address.py - Wireless survey analysis ✓ (requires CSV input)
- [x] safety_plc_analysis.py - PLC config security analysis ✓ (creates demo, saves reports/)
- [x] ladder-logic-analysis.py - Demonstrates ladder logic findings ✓

### Vulnerability Assessment

(8 scripts - protocol-specific vulnerability testing)

**Modbus Vulnerability Assessment:**
- [x] modbus_coil_register_snapshot.py - Read-only memory snapshot ✓ (port 10502)

**OPC UA Vulnerability Assessment:**
- [x] opcua_readonly_probe.py - Anonymous browse & reconnaissance ✓ (port 4840)

**S7 Vulnerability Assessment (requires sudo for port 102):**
- [x] testing-turbine-control-plcs.py - Connection test & CPU info ✓ (needs sudo)
- [x] s7_plc_status_dump.py - Status & configuration dump ✓ (needs sudo)
- [x] s7_read_memory.py - Memory area reconnaissance ✓ (needs sudo)
- [x] s7_readonly_block_dump.py - Program block upload ✓ (needs sudo)

**EtherNet/IP Vulnerability Assessment:**
- [x] ab_logix_tag_inventory.py - Tag enumeration ✓ (port 44818, simplified CIP)

**Educational/Simulated Tools:**
- [x] plc_password_bruteforce.py - S7 password brute force demo ✓ (simulated)

## NOTES

### Protocol Requirements

**S7 Protocol (Port 102):**
- Requires root/sudo access (privileged port)
- Run with: `sudo .venv/bin/python scripts/vulns/<script>.py`
- Affects: All S7 vulnerability assessment scripts

**EtherNet/IP (Port 44818):**
- ✅ Now implemented with simplified CIP protocol
- Full pycomm3 compatibility for tag enumeration
- Sufficient for vulnerability assessment demonstrations

### Previously Blocked (Now Resolved)

- ✅ enumerate-device.py - **UNBLOCKED** (EtherNet/IP server now implemented)
- ✅ query-plc.py - **UNBLOCKED** (S7 server works, just needs sudo)

## Common issues to fix

1. Pymodbus API → Update from 2.x to 3.x
   - Remove `slave=` parameter
   - Use `client.slave_id = X` instead
   - Handle async properly if needed

2. Register addresses -> Use correct ranges
   - Input registers: 0-9 (not 100-109 or 2000-2009)
   - Holding registers: 0-1 (not 200-201 or 1000-1050)
   - Coils: 0-2
   - Discrete inputs: 0-7

3. Output format -> Standardise
   - JSON output for machine parsing
   - Clear impact descriptions
   - Timestamp and metadata

## Testing procedure

For each script:
1. Read the code, understand its purpose
2. Update for pymodbus 3.x + correct addresses
3. Run against live simulator
4. Document what it reveals/demonstrates
5. Mark when working
6. Note any missing simulator features

## Priority order

- Recon: Start with non-invasive reconnaissance to validate basics.
- Discovery: Deep enumeration to map the attack surface.
- Exploitation: Attack demonstrations.
- Analysis: Reporting and documentation.
