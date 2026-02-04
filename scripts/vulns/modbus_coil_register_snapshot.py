#!/usr/bin/env python3
"""
Modbus Coil and Register Snapshot
Read-only reconnaissance of Modbus device memory state.
Tests against UU P&L simulator on port 10502.
"""

from pymodbus.client import ModbusTcpClient
from datetime import datetime
from pathlib import Path
import json


def main():
    target_ip = "127.0.0.1"
    target_port = 10502

    print(f"[*] Modbus Read-Only Memory Snapshot")
    print(f"[*] Target: {target_ip}:{target_port}")
    print(f"[*] Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 50)

    # Create client
    client = ModbusTcpClient(host=target_ip, port=target_port)

    if not client.connect():
        print("[!] Connection failed")
        return

    # Set unit ID for simulator
    client.slave_id = 1

    results = {
        "timestamp": datetime.now().isoformat(),
        "target": f"{target_ip}:{target_port}",
        "coils": {},
        "discrete_inputs": {},
        "holding_registers": {},
        "input_registers": {}
    }

    # Read coils (FC01) – read-only
    print("\n[*] Reading Coils (FC 01)...")
    coils = client.read_coils(address=0, count=10)
    if not coils.isError():
        print(f"    Coil 0-9: {coils.bits[:10]}")
        results["coils"] = {i: bool(coils.bits[i]) for i in range(min(10, len(coils.bits)))}
    else:
        print(f"    Error: {coils}")

    # Read discrete inputs (FC02) – read-only
    print("[*] Reading Discrete Inputs (FC 02)...")
    discrete = client.read_discrete_inputs(address=0, count=10)
    if not discrete.isError():
        print(f"    Discrete Input 0-9: {discrete.bits[:10]}")
        results["discrete_inputs"] = {i: bool(discrete.bits[i]) for i in range(min(10, len(discrete.bits)))}
    else:
        print(f"    Error: {discrete}")

    # Read holding registers (FC03) – read-only
    print("[*] Reading Holding Registers (FC 03)...")
    registers = client.read_holding_registers(address=0, count=10)
    if not registers.isError():
        print(f"    Holding Registers 0-9: {registers.registers}")
        results["holding_registers"] = {i: registers.registers[i] for i in range(len(registers.registers))}
    else:
        print(f"    Error: {registers}")

    # Read input registers (FC04) – read-only
    print("[*] Reading Input Registers (FC 04)...")
    input_regs = client.read_input_registers(address=0, count=10)
    if not input_regs.isError():
        print(f"    Input Registers 0-9: {input_regs.registers}")
        results["input_registers"] = {i: input_regs.registers[i] for i in range(len(input_regs.registers))}
    else:
        print(f"    Error: {input_regs}")

    client.close()

    # Save snapshot to reports
    reports_dir = Path(__file__).parent.parent.parent / "reports"
    reports_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file = reports_dir / f"modbus_snapshot_{timestamp}.json"

    with open(report_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n[*] Snapshot saved to: {report_file}")
    print("[*] Read-only reconnaissance complete")


if __name__ == "__main__":
    main()
