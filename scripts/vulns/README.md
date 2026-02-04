# Vulnerability Assessment scripts

**Phase:** Security testing and vulnerability enumeration
**Risk Level:** High (invasive reconnaissance, demonstrates exploitable weaknesses)
**Goal:** Identify security flaws and demonstrate attack vectors across industrial protocols

## Scripts

### Modbus TCP Vulnerabilities

#### modbus_coil_register_snapshot.py
**Status:** WORKING
**Purpose:** Read-only reconnaissance of coils and registers without authentication
**Target:** Modbus TCP devices on port 10502
**Output:** JSON report with complete memory snapshot

**What it demonstrates:**
- Unauthorised access to coils (control outputs) and registers (process data)
- No authentication required for Modbus TCP protocol
- Attackers can read operational state, setpoints, and control logic

### OPC UA Vulnerabilities

#### opcua_readonly_probe.py
**Status:** WORKING
**Purpose:** Anonymous browsing and reconnaissance of OPC UA server
**Target:** OPC UA server on port 63342
**Output:** JSON report with node tree and accessible values

**What it demonstrates:**
- Anonymous access to OPC UA server (if security policy allows)
- Complete tag enumeration and value reading
- Information disclosure vulnerability

### S7 (Siemens) Vulnerabilities

**Note:** All S7 scripts require sudo/root access (privileged port 102)
Run with: `sudo .venv/bin/python scripts/vulns/<script>.py`

#### testing-turbine-control-plcs.py
**Status:** WORKING (requires sudo)
**Purpose:** Connection test and CPU information extraction
**Target:** S7 PLCs on port 102 (rack 0, slot 2)
**Output:** Console output with CPU type and operational state

**What it demonstrates:**
- Unauthenticated connection to S7 PLCs
- CPU model and firmware information disclosure
- Foundation for deeper S7 reconnaissance

#### s7_plc_status_dump.py
**Status:** WORKING (requires sudo)
**Purpose:** Extract detailed PLC status and configuration
**Target:** S7 PLCs on port 102
**Output:** JSON report with CPU status, run/stop state, and diagnostics

**What it demonstrates:**
- Unauthorised access to PLC operational state
- System information disclosure
- Potential for reconnaissance before attack

#### s7_read_memory.py
**Status:** WORKING (requires sudo)
**Purpose:** Read memory areas (Process Image, Data Blocks)
**Target:** S7 PLCs on port 102
**Output:** Console output with memory area contents

**What it demonstrates:**
- Direct memory access without authentication
- Process variable and data block exfiltration
- Complete visibility into PLC runtime state

#### s7_readonly_block_dump.py
**Status:** WORKING (requires sudo)
**Purpose:** Upload program blocks (OB, FC, FB, DB) from PLC
**Target:** S7 PLCs on port 102
**Output:** Block files saved to reports/s7_blocks/

**What it demonstrates:**
- Programme logic extraction (intellectual property theft)
- Reverse engineering of control algorithms
- Foundation for crafting targeted attacks

### EtherNet/IP (Allen-Bradley) Vulnerabilities

#### ab_logix_tag_inventory.py
**Status:** WORKING
**Purpose:** Enumerate tags from ControlLogix/CompactLogix PLCs
**Target:** EtherNet/IP server on port 44818
**Output:** Console output with tag names, data types, and access rights
**Modes:** Simulator mode (simplified CIP) or real hardware mode (pycomm3)

**What it demonstrates:**
- Unauthenticated tag enumeration
- Identification of writable control points
- Complete mapping of PLC tag database

### Educational/Simulated Tools

#### plc_password_bruteforce.py
**Status:** WORKING (simulated)
**Purpose:** Demonstrate S7 password brute force methodology
**Target:** Simulated PLC authentication
**Output:** Console output with timing and success metrics

**What it demonstrates:**
- Weak password protection in legacy PLCs
- Feasibility of brute force attacks
- Educational tool for understanding authentication weaknesses

## Security Impact

These scripts demonstrate critical vulnerabilities in industrial control systems:

- **No Authentication:** Modbus TCP, S7comm, and EtherNet/IP allow unauthenticated access
- **Information Disclosure:** Attackers can enumerate devices, read configurations, and extract programme logic
- **Attack Surface Mapping:** Complete visibility into control points enables targeted attacks
- **Intellectual Property:** Programme blocks can be exfiltrated and reverse-engineered

## Protocol Requirements

**Modbus TCP (Port 10502):** No special requirements, runs as regular user

**OPC UA (Port 63342):** No special requirements, runs as regular user

**S7 (Port 102):** Requires root/sudo access for privileged port binding
- Use: `sudo .venv/bin/python scripts/vulns/<script>.py`
- Alternative: Use `setcap` or port forwarding for regular user access

**EtherNet/IP (Port 44818):** No special requirements, runs as regular user
- Simulator mode: Works with simplified CIP implementation
- Real hardware mode: Requires pycomm3 and actual Allen-Bradley PLCs

## Status

All 8 vulnerability assessment scripts are working and tested against the simulator.
Scripts produce JSON output to the `reports/` directory for integration with SIEM and analysis tools.
