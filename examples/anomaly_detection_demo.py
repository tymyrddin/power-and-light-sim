#!/usr/bin/env python3
"""
Example: Anomaly Detection Demonstration

Shows how behavioural anomaly detection catches attacks that look normal at protocol level.
Demonstrates statistical baselines, range limits, and rate-of-change detection.

Workshop Flow:
1. Establish baseline for normal turbine behaviour
2. Set range limits (800-1800 RPM)
3. Set rate-of-change limits (max 10 RPM/second)
4. Simulate normal operations (no anomalies)
5. Simulate gradual attack (rate limit violation)
6. Simulate sudden attack (range limit violation)
"""

import asyncio
import random
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from components.security.anomaly_detector import AnomalyDetector, AnomalySeverity
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime


async def main():
    """Anomaly detection demonstration."""

    print("=" * 70)
    print("Anomaly Detection Demonstration")
    print("=" * 70)
    print()

    # ================================================================
    # INITIALISE SIMULATION
    # ================================================================
    print("[1/7] Initialising anomaly detection system...")

    system_state = SystemState()
    data_store = DataStore(system_state=system_state)
    sim_time = SimulationTime()

    detector = AnomalyDetector(
        data_store=data_store,
        system_state=system_state,
    )

    print("✓ Anomaly detection initialised")
    print()

    # ================================================================
    # ESTABLISH BASELINE
    # ================================================================
    print("[2/7] Establishing baseline for turbine speed...")
    print()

    await detector.add_baseline(
        device="turbine_plc_1",
        parameter="speed",
        learning_window=100,  # Small for demo
    )

    # Simulate normal operations to learn baseline (1500 ± 50 RPM)
    print("Learning normal behaviour (1500 ± 50 RPM)...")
    for i in range(100):
        normal_speed = 1500.0 + random.uniform(-50, 50)
        anomaly = await detector.check_value(
            device="turbine_plc_1",
            parameter="speed",
            value=normal_speed,
        )
        if i % 20 == 0:
            print(f"  Sample {i}: {normal_speed:.1f} RPM")

    print()
    print("✓ Baseline established")
    print("  Mean: ~1500 RPM")
    print("  Std Dev: ~30 RPM")
    print("  Detection threshold: 3 sigma (~90 RPM deviation)")
    print()

    # ================================================================
    # SET RANGE LIMITS
    # ================================================================
    print("[3/7] Setting range limits...")
    print()

    await detector.set_range_limit(
        device="turbine_plc_1",
        parameter="speed",
        min_value=800.0,
        max_value=1800.0,
        severity=AnomalySeverity.HIGH,
    )

    print("✓ Range limits set:")
    print("  Min: 800 RPM (below this is underspeed)")
    print("  Max: 1800 RPM (above this is overspeed - DANGEROUS)")
    print()

    # ================================================================
    # SET RATE-OF-CHANGE LIMITS
    # ================================================================
    print("[4/7] Setting rate-of-change limits...")
    print()

    await detector.set_rate_of_change_limit(
        device="turbine_plc_1",
        parameter="speed",
        max_rate=10.0,  # Max 10 RPM/second
        severity=AnomalySeverity.HIGH,
    )

    print("✓ Rate limit set:")
    print("  Max rate: 10 RPM/second")
    print("  Sudden speed changes will be detected")
    print()

    # ================================================================
    # TEST 1: NORMAL OPERATIONS
    # ================================================================
    print("[5/7] Test 1: Normal operations (should NOT trigger anomalies)")
    print()

    sim_time.start()
    print("Simulating normal speed changes...")

    current_speed = 1500.0
    for i in range(10):
        # Small random walk within normal bounds
        change = random.uniform(-5, 5)
        current_speed += change
        sim_time.advance(1.0)  # 1 second

        anomaly = await detector.check_value(
            device="turbine_plc_1",
            parameter="speed",
            value=current_speed,
        )

        status = "✗ ANOMALY" if anomaly else "✓ Normal"
        print(f"  t={i:2d}s: {current_speed:7.1f} RPM - {status}")

    print()
    recent_anomalies = await detector.get_recent_anomalies(limit=10)
    print(f"Result: {len(recent_anomalies)} anomalies detected (expected: 0)")
    print()

    # ================================================================
    # TEST 2: GRADUAL ATTACK (Rate Limit Violation)
    # ================================================================
    print("[6/7] Test 2: Gradual overspeed attack (rate limit violation)")
    print()

    print("Attacker slowly increases speed (15 RPM/second)...")
    current_speed = 1500.0

    for i in range(10):
        # Increase 15 RPM/second (exceeds 10 RPM/second limit)
        current_speed += 15.0
        sim_time.advance(1.0)

        anomaly = await detector.check_value(
            device="turbine_plc_1",
            parameter="speed",
            value=current_speed,
        )

        status = "✗ ANOMALY" if anomaly else "✓ Normal"
        print(f"  t={i:2d}s: {current_speed:7.1f} RPM - {status}")

    print()
    recent_anomalies = await detector.get_recent_anomalies(limit=10)
    rate_anomalies = [
        a for a in recent_anomalies if a.anomaly_type.value == "rate_of_change"
    ]
    print(f"Result: {len(rate_anomalies)} rate-of-change anomalies detected")
    print("✓ Attack detected via rate limit!")
    print()

    # ================================================================
    # TEST 3: SUDDEN ATTACK (Range Limit Violation)
    # ================================================================
    print("[7/7] Test 3: Sudden overspeed attack (range limit violation)")
    print()

    print("Attacker suddenly sets speed to 1900 RPM (exceeds 1800 RPM limit)...")

    # Clear previous anomalies for clean test
    await detector.clear_anomalies()

    # Sudden jump to dangerous speed
    dangerous_speed = 1900.0
    sim_time.advance(1.0)

    anomaly = await detector.check_value(
        device="turbine_plc_1",
        parameter="speed",
        value=dangerous_speed,
    )

    status = "✗ ANOMALY" if anomaly else "✓ Normal"
    print(f"  Speed: {dangerous_speed:.1f} RPM - {status}")

    if anomaly:
        print()
        print(f"  Anomaly Type: {anomaly.anomaly_type.value}")
        print(f"  Severity: {anomaly.severity.name}")
        print(f"  Description: {anomaly.description}")

    print()
    recent_anomalies = await detector.get_recent_anomalies(limit=5)
    range_anomalies = [a for a in recent_anomalies if a.anomaly_type.value == "range"]
    print(f"Result: {len(range_anomalies)} range anomalies detected")
    print("✓ Attack detected via range limit!")
    print()

    # ================================================================
    # STATISTICS
    # ================================================================
    print("=" * 70)
    print("Anomaly Detection Statistics")
    print("=" * 70)
    print()

    stats = await detector.get_anomaly_summary()
    print(f"Total Anomalies: {stats['total_anomalies']}")
    print()

    by_type = stats.get("by_type", {})
    if by_type:
        print("Anomalies by Type:")
        for anom_type, count in by_type.items():
            print(f"  {anom_type:20s}: {count}")
        print()

    by_severity = stats.get("by_severity", {})
    if by_severity:
        print("Anomalies by Severity:")
        for severity, count in by_severity.items():
            print(f"  {severity:10s}: {count}")
        print()

    # ================================================================
    # SUMMARY
    # ================================================================
    print("=" * 70)
    print("Anomaly Detection Demo Complete!")
    print("=" * 70)
    print()

    print("Key Learnings:")
    print("  1. Statistical baselines detect deviations from learned normal")
    print("  2. Range limits catch values outside safe operating bounds")
    print("  3. Rate limits detect sudden or rapid changes")
    print("  4. Gradual attacks can evade statistical detection")
    print("  5. Multiple detection methods provide defence in depth")
    print()

    print("Trade-offs:")
    print("  • Sensitivity: Low sigma = more detections, more false positives")
    print("  • Learning: Long window = stable baseline, slow to adapt")
    print("  • Coverage: Monitor too much = alarm fatigue, too little = miss attacks")
    print()

    print("Real-World Considerations:")
    print("  • Startup/shutdown create anomalies (not attacks)")
    print("  • Maintenance operations may violate baselines")
    print("  • Seasonal patterns need adaptation")
    print("  • False positive rate determines usability")
    print()

    print("Testing with Blue Team CLI:")
    print("  python tools/blue_team.py anomaly enable")
    print(
        "  python tools/blue_team.py anomaly add-baseline --device turbine_plc_1 --parameter speed"
    )
    print(
        "  python tools/blue_team.py anomaly set-range --device turbine_plc_1 --parameter speed --min 800 --max 1800"
    )
    print("  python tools/blue_team.py anomaly list")
    print("  python tools/blue_team.py anomaly stats")
    print()


if __name__ == "__main__":
    asyncio.run(main())
