#!/usr/bin/env python3
# tools/simulator_manager.py
"""
ICS Simulator Manager - Main Orchestrator

Coordinates simulation components based on what's currently implemented:
- Device registration and state management (SystemState, DataStore)
- Network topology (NetworkSimulator)
- Physics engines (TurbinePhysics, GridPhysics, PowerFlow)
- Simulation time (SimulationTime)

Future: Will orchestrate protocol adapters when implemented.

Integrates:
- SimulationTime for temporal coordination
- SystemState/DataStore for device state
- ConfigLoader for configuration
- NetworkSimulator for topology
- Physics engines for realistic behaviour
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Any

from components.network.network_simulator import NetworkSimulator
from components.physics.grid_physics import GridParameters, GridPhysics
from components.physics.power_flow import PowerFlow
from components.physics.turbine_physics import TurbineParameters, TurbinePhysics
from components.state.data_store import DataStore
from components.state.system_state import SystemState
from components.time.simulation_time import SimulationTime, wait_simulation_time
from config.config_loader import ConfigLoader

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("logs/simulation.log")],
)
logger = logging.getLogger(__name__)


class SimulatorManager:
    """
    Main orchestrator for ICS simulation.

    Manages simulation lifecycle from initialisation through execution to shutdown.
    Currently orchestrates state management, network topology, and physics engines.

    Future expansion: Protocol listeners when adapters are implemented.

    Example:
        >>> manager = SimulatorManager()
        >>> await manager.initialise()
        >>> await manager.start()
        >>> # Simulation runs...
        >>> await manager.stop()
    """

    def __init__(self, config_dir: str = "config"):
        """Initialise simulator manager.

        Args:
            config_dir: Directory containing configuration files
        """
        self.config_dir = Path(config_dir)

        # Ensure required directories exist
        Path("logs").mkdir(exist_ok=True)
        self.config_dir.mkdir(exist_ok=True)

        # Core infrastructure
        self.config_loader = ConfigLoader(config_dir=str(self.config_dir))
        self.sim_time = SimulationTime()
        self.system_state = SystemState()
        self.data_store = DataStore(self.system_state)

        # Network components
        self.network_sim = NetworkSimulator(self.config_loader, self.system_state)

        # Physics engines
        self.turbine_physics: dict[str, TurbinePhysics] = {}
        self.grid_physics: GridPhysics | None = None
        self.power_flow: PowerFlow | None = None

        # Simulation state
        self._running = False
        self._paused = False
        self._simulation_task: asyncio.Task | None = None
        self._initialised = False

        # Statistics
        self._update_count = 0
        self._start_time: float = 0.0

        # Signal handling
        self._shutdown_event = asyncio.Event()

        logger.info("SimulatorManager created")

    # ----------------------------------------------------------------
    # Initialisation
    # ----------------------------------------------------------------

    async def initialise(self) -> None:
        """Initialise all simulation components.

        Performs setup in dependency order:
        1. Load configuration
        2. Register devices in state
        3. Load network topology
        4. Create physics engines
        5. Initialise all components

        Raises:
            RuntimeError: If initialisation fails
        """
        if self._initialised:
            logger.warning("Simulator already initialised")
            return

        try:
            logger.info("=== Starting Simulator Initialisation ===")

            # 1. Load configuration
            logger.info("Loading configuration...")
            config = self.config_loader.load_all()

            # 2. Register devices
            logger.info("Registering devices...")
            await self._register_devices(config)

            # 3. Load network topology
            logger.info("Loading network topology...")
            await self.network_sim.load()

            # 4. Create physics engines
            logger.info("Creating physics engines...")
            await self._create_physics_engines(config)

            # 5. Expose services in network
            logger.info("Exposing network services...")
            await self._expose_services(config)

            self._initialised = True

            logger.info("=== Initialisation Complete ===")
            await self._log_summary()

        except Exception as e:
            logger.error(f"Initialisation failed: {e}", exc_info=True)
            raise RuntimeError(f"Failed to initialise simulator: {e}") from e

    async def _register_devices(self, config: dict[str, Any]) -> None:
        """Register all devices from configuration.

        Args:
            config: Loaded configuration dictionary
        """
        devices = config.get("devices", [])

        if not devices:
            logger.warning("No devices found in configuration")
            return

        for device_cfg in devices:
            device_name = device_cfg.get("name")
            device_type = device_cfg.get("type")
            device_id = device_cfg.get("device_id", 1)
            protocols = list(device_cfg.get("protocols", {}).keys())
            metadata = {
                "description": device_cfg.get("description", ""),
                "location": device_cfg.get("location", ""),
            }

            if not device_name or not device_type:
                logger.warning(f"Skipping invalid device config: {device_cfg}")
                continue

            # Register device in state
            await self.data_store.register_device(
                device_name=device_name,
                device_type=device_type,
                device_id=device_id,
                protocols=protocols,
                metadata=metadata,
            )

            # Set device online (in real implementation, protocols would do this)
            await self.data_store.set_device_online(device_name, True)

            logger.info(
                f"Registered device: {device_name} (type={device_type}, protocols={protocols})"
            )

    async def _create_physics_engines(self, config: dict[str, Any]) -> None:
        """Create physics engines for devices.

        Args:
            config: Loaded configuration dictionary
        """
        # Create turbine physics for each turbine PLC
        turbines = await self.data_store.get_devices_by_type("turbine_plc")

        for turbine_device in turbines:
            device_name = turbine_device.device_name

            # Get turbine-specific parameters from metadata if available
            # For now, use defaults
            params = TurbineParameters(
                rated_speed_rpm=3600, rated_power_mw=50.0, max_safe_speed_rpm=3960
            )

            # Create physics engine
            turbine = TurbinePhysics(device_name, self.data_store, params)
            await turbine.initialise()

            self.turbine_physics[device_name] = turbine

            logger.info(f"Created turbine physics: {device_name}")

        # Create grid physics if we have turbines
        if self.turbine_physics:
            grid_params = GridParameters(
                nominal_frequency_hz=50.0,
                inertia_constant=5000.0,
                min_frequency_hz=49.0,
                max_frequency_hz=51.0,
            )
            self.grid_physics = GridPhysics(self.data_store, grid_params)
            await self.grid_physics.initialise()
            logger.info("Created grid physics")

            # Create power flow
            self.power_flow = PowerFlow(self.data_store, self.config_loader)
            await self.power_flow.initialise()
            logger.info("Created power flow engine")

    async def _expose_services(self, config: dict[str, Any]) -> None:
        """Expose services in network simulator.

        Args:
            config: Loaded configuration dictionary
        """
        devices = config.get("devices", [])

        for device_cfg in devices:
            device_name = device_cfg.get("name")
            protocols_cfg = device_cfg.get("protocols", {})

            for proto_name, proto_cfg in protocols_cfg.items():
                port = proto_cfg.get("port")

                if not port:
                    continue

                # Expose service in network simulator
                await self.network_sim.expose_service(device_name, proto_name, port)

                logger.info(f"Exposed {proto_name} service: {device_name}:{port}")

    async def _log_summary(self) -> None:
        """Log initialisation summary."""
        summary = await self.data_store.get_simulation_state()
        net_summary = await self.network_sim.get_summary()

        logger.info("--- Simulation Summary ---")
        logger.info(f"Devices: {summary['devices']['total']}")
        logger.info(f"Device types: {summary['device_types']}")
        logger.info(f"Networks: {net_summary['networks']['count']}")
        logger.info(f"Services exposed: {net_summary['services']['count']}")
        logger.info(f"Turbine physics engines: {len(self.turbine_physics)}")
        logger.info(f"Grid physics: {'enabled' if self.grid_physics else 'disabled'}")
        logger.info(f"Power flow: {'enabled' if self.power_flow else 'disabled'}")
        logger.info("-------------------------")

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    async def start(self) -> None:
        """Start the simulation.

        Starts time system and begins main simulation loop.

        Raises:
            RuntimeError: If not initialised or already running
        """
        if not self._initialised:
            raise RuntimeError("Cannot start: simulator not initialised")

        if self._running:
            logger.warning("Simulator already running")
            return

        logger.info("=== Starting Simulation ===")

        # Start simulation time
        await self.sim_time.start()

        # Mark system as running
        await self.data_store.mark_simulation_running(True)

        self._running = True
        self._start_time = self.sim_time.now()

        # Start main simulation loop
        self._simulation_task = asyncio.create_task(self._simulation_loop())

        logger.info("Simulation started - physics engines active")
        logger.info(
            "NOTE: Protocol listeners not implemented yet - devices accessible via state only"
        )

    async def stop(self) -> None:
        """Stop the simulation gracefully.

        Stops all components and cleans up resources.
        """
        if not self._running:
            logger.warning("Simulator not running")
            return

        logger.info("=== Stopping Simulation ===")

        self._running = False

        # Stop simulation loop
        if self._simulation_task:
            self._simulation_task.cancel()
            try:
                await self._simulation_task
            except asyncio.CancelledError:
                pass

        # Stop simulation time
        await self.sim_time.stop()

        # Mark system as stopped
        await self.data_store.mark_simulation_running(False)

        # Log final statistics
        await self._log_final_statistics()

        logger.info("Simulation stopped")

    async def pause(self) -> None:
        """Pause the simulation.

        Freezes simulation time.
        """
        if not self._running:
            raise RuntimeError("Cannot pause: simulation not running")

        if self._paused:
            logger.warning("Simulation already paused")
            return

        await self.sim_time.pause()
        self._paused = True

        logger.info("Simulation paused")

    async def resume(self) -> None:
        """Resume paused simulation."""
        if not self._paused:
            logger.warning("Simulation not paused")
            return

        await self.sim_time.resume()
        self._paused = False

        logger.info("Simulation resumed")

    async def reset(self) -> None:
        """Reset simulation to initial state.

        Stops simulation if running and resets all state.
        """
        logger.info("=== Resetting Simulation ===")

        if self._running:
            await self.stop()

        # Reset simulation time
        await self.sim_time.reset()

        # Reset system state
        await self.system_state.reset()

        # Reset physics engines
        for turbine in self.turbine_physics.values():
            await turbine.initialise()

        if self.grid_physics:
            await self.grid_physics.initialise()

        if self.power_flow:
            await self.power_flow.initialise()

        self._update_count = 0
        self._initialised = False

        logger.info("Simulation reset complete")

    # ----------------------------------------------------------------
    # Main simulation loop
    # ----------------------------------------------------------------

    async def _simulation_loop(self) -> None:
        """Main simulation update loop.

        Runs at configured update interval, coordinating physics updates.
        """
        config = self.config_loader.load_all()
        runtime_cfg = config.get("simulation", {}).get("runtime", {})
        update_interval = runtime_cfg.get("update_interval", 0.1)

        logger.info(f"Simulation loop started (interval={update_interval}s)")

        last_time = self.sim_time.now()

        try:
            while self._running:
                # Get simulation time delta
                current_time = self.sim_time.now()
                dt = current_time - last_time
                last_time = current_time

                # Skip update if paused or dt is zero
                if self._paused or dt <= 0:
                    await wait_simulation_time(update_interval)
                    continue

                # Perform simulation update
                await self._update_simulation(dt)

                # Increment cycle counter
                self._update_count += 1

                # Periodic status logging
                if self._update_count % 100 == 0:
                    await self._log_status()

                # Wait for next cycle
                await wait_simulation_time(update_interval)

        except asyncio.CancelledError:
            logger.info("Simulation loop cancelled")
        except Exception as e:
            logger.error(f"Error in simulation loop: {e}", exc_info=True)
            self._running = False

    async def _update_simulation(self, dt: float) -> None:
        """Perform one simulation update cycle.

        Updates physics engines and writes telemetry to device state.

        Args:
            dt: Time delta in simulation seconds
        """
        # 1. Update device aggregations for grid/power flow
        if self.grid_physics:
            await self.grid_physics.update_from_devices()

        if self.power_flow:
            await self.power_flow.update_from_devices()

        # 2. Update all physics engines (synchronous, deterministic order)
        for turbine in self.turbine_physics.values():
            turbine.update(dt)

        if self.grid_physics:
            self.grid_physics.update(dt)

        if self.power_flow:
            self.power_flow.update(dt)

        # 3. Write telemetry back to device memory maps
        for turbine in self.turbine_physics.values():
            await turbine.write_telemetry()

        # 4. Increment system update counter
        await self.data_store.increment_update_cycle()

    # ----------------------------------------------------------------
    # Status and monitoring
    # ----------------------------------------------------------------

    async def get_status(self) -> dict[str, Any]:
        """Get comprehensive simulation status.

        Returns:
            Dictionary with simulation status and statistics
        """
        sim_time_status = await self.sim_time.get_status()
        system_summary = await self.data_store.get_simulation_state()
        net_summary = await self.network_sim.get_summary()

        # Get physics status
        physics_status = {}
        if self.grid_physics:
            physics_status["grid"] = self.grid_physics.get_telemetry()

        turbine_status = {}
        for name, turbine in self.turbine_physics.items():
            turbine_status[name] = turbine.get_telemetry()

        return {
            "running": self._running,
            "paused": self._paused,
            "initialised": self._initialised,
            "update_count": self._update_count,
            "simulation_time": sim_time_status,
            "system_state": system_summary,
            "network": net_summary,
            "physics": {
                "grid": physics_status.get("grid"),
                "turbines": turbine_status,
                "power_flow": self.power_flow is not None,
            },
        }

    async def _log_status(self) -> None:
        """Log periodic status update."""
        status = await self.get_status()

        # Log basic status
        logger.info(
            f"Cycle {self._update_count}: "
            f"SimTime {status['simulation_time']['simulation_time']:.1f}s, "
            f"Devices {status['system_state']['devices']['online']}/"
            f"{status['system_state']['devices']['total']} online"
        )

        # Log grid status if available
        if status["physics"]["grid"]:
            grid = status["physics"]["grid"]
            logger.debug(
                f"Grid: {grid['frequency_hz']:.3f}Hz, "
                f"Gen={grid['total_generation_mw']:.1f}MW, "
                f"Load={grid['total_load_mw']:.1f}MW"
            )

    async def _log_final_statistics(self) -> None:
        """Log final simulation statistics."""
        elapsed_sim = self.sim_time.now() - self._start_time
        elapsed_wall = self.sim_time.wall_elapsed()

        if elapsed_wall > 0:
            ratio = elapsed_sim / elapsed_wall
        else:
            ratio = 0

        logger.info("--- Final Statistics ---")
        logger.info(f"Total update cycles: {self._update_count}")
        logger.info(f"Simulation time elapsed: {elapsed_sim:.1f}s")
        logger.info(f"Wall-clock time elapsed: {elapsed_wall:.1f}s")
        logger.info(f"Time ratio: {ratio:.2f}x")
        logger.info("------------------------")

    # ----------------------------------------------------------------
    # Signal handling
    # ----------------------------------------------------------------

    def setup_signal_handlers(self) -> None:
        """Set up signal handlers for graceful shutdown."""

        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}")
            self._shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        logger.info("Signal handlers configured")

    async def wait_for_shutdown(self) -> None:
        """Wait for shutdown signal."""
        await self._shutdown_event.wait()

    # ----------------------------------------------------------------
    # Main run method
    # ----------------------------------------------------------------

    async def run(self) -> None:
        """Run complete simulation lifecycle.

        Initialises, starts, and runs until interrupted.
        """
        try:
            # Set up signal handlers
            self.setup_signal_handlers()

            # Initialise
            await self.initialise()

            # Start simulation
            await self.start()

            # Wait for shutdown signal
            logger.info("Simulation running. Press Ctrl+C to stop.")
            logger.info("")
            logger.info("Current capabilities:")
            logger.info("  ✓ Physics simulation (turbines, grid, power flow)")
            logger.info("  ✓ Device state management")
            logger.info("  ✓ Network topology simulation")
            logger.info("  ✗ Protocol listeners (not yet implemented)")
            logger.info("")
            await self.wait_for_shutdown()

        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
        finally:
            # Clean shutdown
            if self._running:
                await self.stop()


# ----------------------------------------------------------------
# Command-line interface
# ----------------------------------------------------------------


async def main():
    """Main entry point."""
    logger.info("=== UU Power & Light ICS Simulator ===")
    logger.info("")

    # Create and run simulator
    manager = SimulatorManager()
    await manager.run()


if __name__ == "__main__":
    asyncio.run(main())
