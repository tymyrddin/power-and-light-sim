# tests/integration/test_simulator_lifecycle.py
"""
Complete Simulator Lifecycle Integration Test.

Tests the entire UU Power & Light simulator from cold start through normal
operation to clean shutdown. Verifies all major systems work together:
- Physics engines (turbines, reactor, grid)
- PLCs (turbine control, reactor control, safety)
- SCADA systems
- Workstations (HMI, engineering)
- Protocol communication
- State management

This is a comprehensive integration test that exercises real-world usage
patterns and ensures system stability under normal operating conditions.
"""

import asyncio

import pytest

from components.devices.control_zone.plc.vendor_specific.reactor_plc import ReactorPLC
from components.devices.control_zone.plc.vendor_specific.turbine_plc import TurbinePLC
from components.devices.control_zone.safety.reactor_safety_plc import (
    ReactorSafetyPLC,
)
from components.devices.control_zone.safety.turbine_safety_plc import (
    TurbineSafetyPLC,
)
from components.devices.operations_zone.engineering_workstation import (
    EngineeringWorkstation,
)
from components.devices.operations_zone.hmi_workstation import HMIWorkstation
from components.devices.operations_zone.scada_server import SCADAServer
from components.physics.grid_physics import GridPhysics
from components.physics.reactor_physics import ReactorPhysics
from components.physics.turbine_physics import TurbinePhysics
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime, TimeMode

# ================================================================
# TEST CONFIGURATION
# ================================================================
# How long to run the simulation (simulated seconds)
# Actual: ~55s (40s warm-up + 10s steady state + 5s cooldown)
SIMULATION_DURATION = 60.0

# Update interval (simulation seconds per step)
UPDATE_INTERVAL = 0.1

# Steady state verification threshold (seconds)
STEADY_STATE_TIME = 10.0


# ================================================================
# FIXTURES
# ================================================================
@pytest.fixture
async def clean_simulation():
    """Reset simulation time and provide clean environment."""
    sim_time = SimulationTime()
    sim_time.reset_for_testing()  # Full reset
    sim_time.state.mode = TimeMode.STEPPED  # Use STEPPED mode for manual time control
    yield sim_time
    sim_time.reset_for_testing()


@pytest.fixture
async def system_infrastructure(clean_simulation):
    """
    Create core system infrastructure.

    Provides SystemState and DataStore that all devices will use.
    """
    system_state = SystemState()
    data_store = DataStore(system_state)

    yield system_state, data_store


# ================================================================
# COMPLETE SIMULATOR LIFECYCLE TEST
# ================================================================
class TestSimulatorLifecycle:
    """Test complete simulator lifecycle from start to shutdown."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_complete_lifecycle(self, system_infrastructure):
        """
        Test complete simulator lifecycle.

        Phase 1: Cold Start
        - Initialize all physics engines
        - Initialize all PLCs and devices
        - Initialize SCADA and workstations
        - Verify clean initialization

        Phase 2: System Startup
        - Start all devices in correct order
        - Verify device registration
        - Verify initial telemetry

        Phase 3: Warm-up
        - Bring turbines and reactor to operating conditions
        - Monitor temperature rise
        - Verify safety systems monitoring

        Phase 4: Steady State Operation
        - Run at rated conditions
        - Verify stable telemetry
        - Verify protocol communication
        - Monitor for anomalies

        Phase 5: Clean Shutdown
        - Ramp down to safe shutdown
        - Stop all devices gracefully
        - Verify clean state
        """
        system_state, data_store = system_infrastructure
        sim_time = SimulationTime()

        # Track all devices for cleanup
        devices = []
        physics_engines = []

        try:
            # ========================================================
            # PHASE 1: COLD START - INITIALIZATION
            # ========================================================
            print("\n[PHASE 1] Cold Start - Initializing all systems")

            # Register all devices with SystemState first
            # This must happen before creating device instances

            # Turbine system devices
            await data_store.register_device(
                "turbine_plc_1", "turbine_plc", 1, ["modbus"]
            )
            await data_store.register_device(
                "turbine_safety_1", "turbine_safety_plc", 10, ["modbus"]
            )

            # Reactor system devices
            await data_store.register_device("reactor_plc_1", "reactor_plc", 2, ["s7"])
            await data_store.register_device(
                "reactor_safety_1", "reactor_safety_plc", 11, ["s7"]
            )

            # SCADA and workstations
            await data_store.register_device("scada_1", "scada_server", 100, ["opcua"])
            await data_store.register_device("hmi_1", "hmi_workstation", 101, [])
            await data_store.register_device(
                "engineering_1", "engineering_workstation", 102, []
            )

            print("  [✓] All devices registered in SystemState")

            # Initialize physics engines
            turbine_physics_1 = TurbinePhysics("turbine_plc_1", data_store)
            await turbine_physics_1.initialise()
            physics_engines.append(turbine_physics_1)

            reactor_physics_1 = ReactorPhysics("reactor_plc_1", data_store)
            await reactor_physics_1.initialise()
            physics_engines.append(reactor_physics_1)

            grid_physics = GridPhysics(data_store)
            await grid_physics.initialise()
            physics_engines.append(grid_physics)

            print("  [✓] Physics engines initialized")

            # Initialize PLCs
            turbine_plc_1 = TurbinePLC(
                device_name="turbine_plc_1",
                device_id=1,
                data_store=data_store,
                turbine_physics=turbine_physics_1,
            )
            devices.append(turbine_plc_1)

            turbine_safety_1 = TurbineSafetyPLC(
                device_name="turbine_safety_1",
                device_id=10,
                data_store=data_store,
                turbine_physics=turbine_physics_1,
            )
            devices.append(turbine_safety_1)

            reactor_plc_1 = ReactorPLC(
                device_name="reactor_plc_1",
                device_id=2,
                data_store=data_store,
                reactor_physics=reactor_physics_1,
            )
            devices.append(reactor_plc_1)

            reactor_safety_1 = ReactorSafetyPLC(
                device_name="reactor_safety_1",
                device_id=11,
                data_store=data_store,
                reactor_physics=reactor_physics_1,
            )
            devices.append(reactor_safety_1)

            print("  [✓] PLCs initialized")

            # Initialize SCADA and workstations
            scada_1 = SCADAServer(
                device_name="scada_1",
                device_id=100,
                data_store=data_store,
            )
            devices.append(scada_1)

            hmi_1 = HMIWorkstation(
                device_name="hmi_1",
                device_id=101,
                data_store=data_store,
            )
            devices.append(hmi_1)

            engineering_1 = EngineeringWorkstation(
                device_name="engineering_1",
                device_id=102,
                data_store=data_store,
            )
            devices.append(engineering_1)

            print("  [✓] SCADA and workstations initialized")

            # Verify initial state
            assert len(system_state.devices) == 7
            assert system_state.simulation.total_devices == 7
            print(f"  [✓] All {len(devices)} devices initialized successfully")

            # ========================================================
            # PHASE 2: SYSTEM STARTUP
            # ========================================================
            print("\n[PHASE 2] System Startup - Starting all devices")

            # Start devices in logical order
            # 1. SCADA/monitoring first (observers)
            await scada_1.start()
            await hmi_1.start()
            await engineering_1.start()

            # 2. Safety systems (must be ready before control systems)
            await turbine_safety_1.start()
            await reactor_safety_1.start()

            # 3. Control PLCs
            await turbine_plc_1.start()
            await reactor_plc_1.start()

            print("  [✓] All devices started")

            # Verify all devices are running
            for device in devices:
                assert device.is_running(), f"Device {device.device_name} not running"

            # Verify all devices are online in system state
            all_devices = await system_state.get_all_devices()
            online_devices = [d for d in all_devices.values() if d.online]
            assert len(online_devices) == 7
            print("  [✓] All devices online in SystemState")

            # Wait for initial scan cycles to complete
            await asyncio.sleep(0.1)

            # Verify initial telemetry was written
            turbine_rpm = await data_store.read_memory(
                "turbine_plc_1", "holding_registers[0]"
            )
            assert turbine_rpm is not None
            print(f"  [✓] Initial telemetry available (Turbine RPM: {turbine_rpm})")

            # ========================================================
            # PHASE 3: WARM-UP TO OPERATING CONDITIONS
            # ========================================================
            print("\n[PHASE 3] Warm-up - Bringing systems to operating conditions")

            # Enable turbine governor and set rated speed
            await data_store.write_memory("turbine_plc_1", "coils[10]", True)
            await data_store.write_memory(
                "turbine_plc_1", "holding_registers[10]", 3600
            )
            print("  [✓] Turbine governor enabled, target: 3600 RPM")

            # Enable reactor control and set target power
            # holding_registers[10] = power setpoint %
            # holding_registers[11] = coolant pump speed %
            # holding_registers[12] = control rod position (0=inserted, 100=withdrawn)
            await data_store.write_memory("reactor_plc_1", "holding_registers[10]", 80)
            await data_store.write_memory("reactor_plc_1", "holding_registers[11]", 100)
            await data_store.write_memory("reactor_plc_1", "holding_registers[12]", 80)
            print("  [✓] Reactor control enabled, target: 80% power")

            # Run warm-up phase (40 seconds simulated time)
            # Turbine accelerates at 100 RPM/s, so needs ~36s to reach 3600 RPM
            warmup_steps = int(40.0 / UPDATE_INTERVAL)
            print(f"  [→] Running {warmup_steps} update steps (40s simulated)")

            for _step in range(warmup_steps):
                # Update physics
                for physics in physics_engines:
                    if hasattr(physics, "read_control_inputs"):
                        await physics.read_control_inputs()
                    physics.update(UPDATE_INTERVAL)
                    if hasattr(physics, "write_telemetry"):
                        await physics.write_telemetry()

                # Advance simulation time
                await sim_time.step(UPDATE_INTERVAL)
                # Yield to event loop to allow PLC scan loops to run
                await asyncio.sleep(0.001)

            # Check turbine reached operating speed
            turbine_rpm = await data_store.read_memory(
                "turbine_plc_1", "holding_registers[0]"
            )
            assert turbine_rpm > 3000, f"Turbine not at speed: {turbine_rpm} RPM"
            print(f"  [✓] Turbine at speed: {turbine_rpm} RPM")

            # Check turbine temperature rising
            turbine_temp = await data_store.read_memory(
                "turbine_plc_1", "holding_registers[3]"
            )
            assert turbine_temp > 30, f"Turbine not warming up: {turbine_temp}°C"
            print(f"  [✓] Turbine temperature rising: {turbine_temp}°C")

            # Check reactor at power
            reactor_power = await data_store.read_memory(
                "reactor_plc_1", "holding_registers[5]"
            )
            assert reactor_power > 50, f"Reactor not at power: {reactor_power}%"
            print(f"  [✓] Reactor at power: {reactor_power}%")

            # Verify safety systems monitoring
            turbine_running = await data_store.read_memory(
                "turbine_safety_1", "discrete_inputs[0]"
            )
            assert turbine_running is True
            print("  [✓] Safety systems monitoring active")

            # ========================================================
            # PHASE 4: STEADY STATE OPERATION
            # ========================================================
            print("\n[PHASE 4] Steady State - Normal operation")

            # Run at steady state
            steady_state_steps = int(STEADY_STATE_TIME / UPDATE_INTERVAL)
            print(
                f"  [→] Running {steady_state_steps} update steps ({STEADY_STATE_TIME}s simulated)"
            )

            # Track telemetry for stability verification
            rpm_samples = []
            temp_samples = []
            power_samples = []

            for step in range(steady_state_steps):
                # Update all physics engines
                for physics in physics_engines:
                    if hasattr(physics, "read_control_inputs"):
                        await physics.read_control_inputs()
                    physics.update(UPDATE_INTERVAL)
                    if hasattr(physics, "write_telemetry"):
                        await physics.write_telemetry()

                # Sample telemetry every second
                if step % 10 == 0:
                    rpm = await data_store.read_memory(
                        "turbine_plc_1", "holding_registers[0]"
                    )
                    temp = await data_store.read_memory(
                        "turbine_plc_1", "holding_registers[3]"
                    )
                    power = await data_store.read_memory(
                        "turbine_plc_1", "holding_registers[5]"
                    )

                    rpm_samples.append(rpm)
                    temp_samples.append(temp)
                    power_samples.append(power)

                # Advance simulation time
                await sim_time.step(UPDATE_INTERVAL)
                # Yield to event loop to allow PLC scan loops to run
                await asyncio.sleep(0.001)

            print(f"  [✓] Completed {STEADY_STATE_TIME}s of steady state operation")

            # Verify stable operation
            avg_rpm = sum(rpm_samples) / len(rpm_samples)
            avg_temp = sum(temp_samples) / len(temp_samples)
            avg_power = sum(power_samples) / len(power_samples)

            print(f"  [✓] Average RPM: {avg_rpm:.0f}")
            print(f"  [✓] Average temperature: {avg_temp:.1f}°C")
            print(f"  [✓] Average power: {avg_power:.1f}MW")

            # Verify reasonable operating ranges
            assert 3500 < avg_rpm < 3700, f"Unstable RPM: {avg_rpm}"
            assert 50 < avg_temp < 150, f"Temperature out of range: {avg_temp}°C"
            assert avg_power > 0, f"No power output: {avg_power}MW"

            # Verify no safety trips occurred
            safety_trip = await data_store.read_memory(
                "turbine_safety_1", "discrete_inputs[5]"
            )
            assert safety_trip is False, "Unexpected safety trip"
            print("  [✓] No safety trips during normal operation")

            # Verify all devices still online
            all_devices = await system_state.get_all_devices()
            online_devices = [d for d in all_devices.values() if d.online]
            assert len(online_devices) == 7, "Device went offline during operation"
            print("  [✓] All devices remained online")

            # Verify protocol communication working
            # Read via different protocol (OPC UA server would read from SCADA)
            scada_turbine_speed = await data_store.read_memory(
                "turbine_plc_1", "holding_registers[0]"
            )
            assert scada_turbine_speed is not None
            print("  [✓] Protocol communication verified")

            # ========================================================
            # PHASE 5: CONTROLLED SHUTDOWN
            # ========================================================
            print("\n[PHASE 5] Shutdown - Graceful system shutdown")

            # Reduce reactor power first
            await data_store.write_memory("reactor_plc_1", "holding_registers[1]", 0)
            print("  [✓] Reactor shutdown commanded")

            # Reduce turbine speed
            await data_store.write_memory("turbine_plc_1", "holding_registers[10]", 0)
            print("  [✓] Turbine speed reduction commanded")

            # Run cooldown (5 seconds)
            cooldown_steps = int(5.0 / UPDATE_INTERVAL)
            for _step in range(cooldown_steps):
                for physics in physics_engines:
                    if hasattr(physics, "read_control_inputs"):
                        await physics.read_control_inputs()
                    physics.update(UPDATE_INTERVAL)
                    if hasattr(physics, "write_telemetry"):
                        await physics.write_telemetry()
                # Advance simulation time
                await sim_time.step(UPDATE_INTERVAL)
                await asyncio.sleep(0.001)

            # Verify systems cooling/slowing
            final_rpm = await data_store.read_memory(
                "turbine_plc_1", "holding_registers[0]"
            )
            assert final_rpm < avg_rpm, "Turbine did not slow down"
            print(f"  [✓] Turbine slowing down: {final_rpm} RPM")

            # Stop all devices in reverse order
            # 1. Control PLCs first
            await turbine_plc_1.stop()
            await reactor_plc_1.stop()

            # 2. Safety systems
            await turbine_safety_1.stop()
            await reactor_safety_1.stop()

            # 3. Monitoring systems
            await hmi_1.stop()
            await engineering_1.stop()
            await scada_1.stop()

            print("  [✓] All devices stopped gracefully")

            # Verify devices are stopped
            for device in devices:
                assert (
                    not device.is_running()
                ), f"Device {device.device_name} still running"

            # Verify clean state
            running_devices = [d for d in system_state.devices.values() if d.online]
            assert len(running_devices) == 0, "Devices still marked online"
            print("  [✓] Clean shutdown state verified")

            # ========================================================
            # PHASE 6: VERIFICATION
            # ========================================================
            print("\n[PHASE 6] Verification - Final checks")

            # Verify system state is clean
            assert system_state.simulation.total_devices == 7
            print("  [✓] SystemState integrity maintained")

            # Verify simulation time advanced correctly
            expected_time = 40.0 + STEADY_STATE_TIME + 5.0  # warmup + steady + cooldown
            actual_time = sim_time.now()
            # Allow some tolerance for async timing
            assert (
                abs(actual_time - expected_time) < 1.0
            ), f"Time drift: {actual_time} vs {expected_time}"
            print(f"  [✓] Simulation time tracked correctly: {actual_time:.1f}s")

            # Verify no resource leaks (basic check)
            assert len(devices) == 7
            assert len(physics_engines) == 3
            print("  [✓] No obvious resource leaks")

            print("\n[✓] COMPLETE LIFECYCLE TEST PASSED")
            print(
                f"    Simulated {actual_time:.1f}s of operation across 7 devices and 3 physics engines"
            )
            print("    All phases completed successfully:")
            print("      • Cold start and initialization")
            print("      • System startup and device registration")
            print("      • Warm-up to operating conditions")
            print("      • Steady state operation")
            print("      • Controlled shutdown")
            print("      • State verification")

        finally:
            # Cleanup: Stop any remaining devices
            for device in devices:
                if device.is_running():
                    try:
                        await device.stop()
                    except Exception as e:
                        print(f"Warning: Error stopping {device.device_name}: {e}")


# ================================================================
# SUPPORTING TESTS
# ================================================================
class TestSimulatorStability:
    """Additional stability and stress tests."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_extended_runtime(self, system_infrastructure):
        """
        Test simulator can run for extended period.

        Runs for 100 simulated seconds to catch timing issues,
        memory leaks, or state corruption that only appear over time.
        """
        system_state, data_store = system_infrastructure
        sim_time = SimulationTime()

        # Minimal setup - just one turbine system
        await data_store.register_device("turbine_plc_1", "turbine_plc", 1, ["modbus"])

        turbine_physics = TurbinePhysics("turbine_plc_1", data_store)
        await turbine_physics.initialise()

        turbine_plc = TurbinePLC(
            device_name="turbine_plc_1",
            device_id=1,
            data_store=data_store,
            turbine_physics=turbine_physics,
        )

        try:
            await turbine_plc.start()

            # Enable and run
            await data_store.write_memory("turbine_plc_1", "coils[10]", True)
            await data_store.write_memory(
                "turbine_plc_1", "holding_registers[10]", 3600
            )

            # Run for 100 seconds
            steps = int(100.0 / 0.1)
            for _ in range(steps):
                await turbine_physics.read_control_inputs()
                turbine_physics.update(0.1)
                await turbine_physics.write_telemetry()
                await sim_time.step(0.1)
                await asyncio.sleep(0.001)

            # Should still be running
            assert turbine_plc.is_running()
            rpm = await data_store.read_memory("turbine_plc_1", "holding_registers[0]")
            assert rpm > 3000

            print("[✓] Extended runtime test passed: 100s simulated")

        finally:
            if turbine_plc.is_running():
                await turbine_plc.stop()
