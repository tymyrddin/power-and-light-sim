# tests/conftest.py
"""Shared pytest fixtures for ICS simulator tests.

This file provides common fixtures used across all test modules,
following the bottom-up testing strategy where foundation components
are tested with real dependencies wherever possible.
"""

import asyncio
import tempfile
from pathlib import Path
from typing import Generator

import pytest
import yaml


# ----------------------------------------------------------------
# Async event loop configuration
# ----------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop_policy():
    """Set event loop policy for the test session."""
    return asyncio.get_event_loop_policy()


@pytest.fixture
def event_loop(event_loop_policy):
    """Create an event loop for each test.

    This ensures each test gets a fresh event loop and proper cleanup.
    """
    loop = event_loop_policy.new_event_loop()
    yield loop
    # Cancel all pending tasks
    pending = asyncio.all_tasks(loop)
    for task in pending:
        task.cancel()
    # Run loop until all tasks are cancelled
    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    loop.close()


# ----------------------------------------------------------------
# Configuration fixtures
# ----------------------------------------------------------------
@pytest.fixture
def temp_config_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for test configuration files.

    Yields:
        Path to temporary configuration directory
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir)
        yield config_path


@pytest.fixture
def default_simulation_config() -> dict:
    """Provide default simulation configuration for testing.

    Returns:
        Dictionary with default simulation runtime configuration
    """
    return {
        "simulation": {
            "runtime": {
                "realtime": True,
                "time_acceleration": 1.0,
                "update_interval": 0.01,
                "max_iterations": 1000,
            }
        }
    }


@pytest.fixture
def accelerated_config() -> dict:
    """Provide accelerated simulation configuration for testing.

    Returns:
        Dictionary with 10x accelerated simulation config
    """
    return {
        "simulation": {
            "runtime": {
                "realtime": False,
                "time_acceleration": 10.0,
                "update_interval": 0.01,
                "max_iterations": 1000,
            }
        }
    }


@pytest.fixture
def write_config_file(temp_config_dir):
    """Factory fixture for writing YAML configuration files.

    Args:
        temp_config_dir: Temporary directory for config files

    Returns:
        Function that writes config dict to YAML file
    """

    def _write_config(config: dict, filename: str = "simulation.yml") -> Path:
        """Write configuration to YAML file.

        Args:
            config: Configuration dictionary
            filename: Name of the config file

        Returns:
            Path to written configuration file
        """
        config_file = temp_config_dir / filename
        with open(config_file, "w") as f:
            yaml.dump(config, f)
        return config_file

    return _write_config


# ----------------------------------------------------------------
# Time-related fixtures
# ----------------------------------------------------------------
@pytest.fixture
async def clean_simulation_time(setup_config_files):
    """Provide a clean SimulationTime instance for testing.

    This fixture ensures:
    1. Real YAML config files are set up
    2. SimulationTime singleton is stopped before test
    3. Test gets a fresh instance with real ConfigLoader
    4. SimulationTime is stopped and cleaned up after test

    Yields:
        Fresh SimulationTime instance using REAL ConfigLoader
    """
    from components.time.simulation_time import SimulationTime

    # Setup real config files first
    setup_config_files()

    # Get singleton instance
    sim_time = SimulationTime()

    # Ensure it's stopped before test
    await sim_time.stop()

    # Reset to clean state (will reload from REAL YAML)
    sim_time.reset_for_testing()

    yield sim_time

    # Cleanup after test
    await sim_time.stop()


@pytest.fixture
def clean_simulation_time_with_config(setup_config_files):
    """Factory fixture for SimulationTime with custom config.

    Use this when you need to test with a specific configuration.

    Returns:
        Async function that sets up SimulationTime with custom config
    """

    async def _create(config: dict = None):
        """Create clean SimulationTime with specified config.

        Args:
            config: Configuration dictionary (uses default if None)

        Returns:
            Clean SimulationTime instance
        """
        from components.time.simulation_time import SimulationTime

        # Setup config files
        setup_config_files(config)

        # Get singleton and reset
        sim_time = SimulationTime()
        await sim_time.stop()
        sim_time.reset_for_testing()

        return sim_time

    return _create


@pytest.fixture
def time_tolerance() -> float:
    """Provide standard time comparison tolerance for tests.

    Used for floating-point time comparisons to account for
    system timing variability and async scheduling delays.

    Returns:
        Tolerance value in seconds (0.05s = 50ms)
    """
    return 0.05


# ----------------------------------------------------------------
# Assertion helpers
# ----------------------------------------------------------------
@pytest.fixture
def assert_time_approximately():
    """Provide a helper for approximate time assertions.

    Returns:
        Function that asserts two time values are approximately equal
    """

    def _assert_approx(actual: float, expected: float, tolerance: float = 0.05):
        """Assert that actual time is within tolerance of expected.

        Args:
            actual: Actual time value
            expected: Expected time value
            tolerance: Maximum allowed difference (default 50ms)

        Raises:
            AssertionError: If values differ by more than tolerance
        """
        diff = abs(actual - expected)
        assert diff <= tolerance, (
            f"Time values not within tolerance: "
            f"actual={actual:.3f}s, expected={expected:.3f}s, "
            f"diff={diff:.3f}s, tolerance={tolerance:.3f}s"
        )

    return _assert_approx


# ----------------------------------------------------------------
# Real configuration setup (NO MOCKING)
# ----------------------------------------------------------------
@pytest.fixture
def setup_config_files(temp_config_dir, default_simulation_config, monkeypatch):
    """Setup real YAML configuration files for testing.

    This uses the REAL ConfigLoader with actual YAML files.
    NO MOCKING - we test with real components.

    Args:
        temp_config_dir: Temporary directory for config files
        default_simulation_config: Default config dictionary
        monkeypatch: To override config directory location

    Returns:
        Function that writes config and sets up ConfigLoader
    """

    def _setup(config: dict = None):
        """Write real YAML files and configure ConfigLoader to use them.

        Args:
            config: Configuration dictionary (uses default if None)
        """
        if config is None:
            config = default_simulation_config

        # Write simulation.yml
        simulation_file = temp_config_dir / "simulation.yml"
        with open(simulation_file, "w") as f:
            yaml.dump(config, f)

        # Create minimal devices.yml to prevent defaults
        devices_file = temp_config_dir / "devices.yml"
        with open(devices_file, "w") as f:
            yaml.dump({"devices": []}, f)

        # Monkeypatch ConfigLoader to use temp directory
        import components.time.simulation_time

        original_init = components.time.simulation_time.ConfigLoader.__init__

        def patched_init(self, config_dir=None):
            # Ignore any passed config_dir and always use temp_config_dir
            # This ensures tests use isolated config files
            _ = config_dir  # Explicitly ignore parameter
            original_init(self, config_dir=str(temp_config_dir))

        monkeypatch.setattr(
            components.time.simulation_time.ConfigLoader, "__init__", patched_init
        )

    return _setup


# ----------------------------------------------------------------
# Async utilities
# ----------------------------------------------------------------
@pytest.fixture
async def wait_for_condition():
    """Provide utility for waiting on async conditions.

    Returns:
        Async function that polls a condition until true or timeout
    """

    async def _wait(
        condition_fn,
        timeout: float = 1.0,
        poll_interval: float = 0.01,
        error_msg: str = "Condition not met within timeout",
    ):
        """Wait for a condition to become true.

        Args:
            condition_fn: Callable that returns bool
            timeout: Maximum time to wait in seconds
            poll_interval: Time between checks in seconds
            error_msg: Error message if timeout occurs

        Raises:
            AssertionError: If condition not met within timeout
        """
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            if condition_fn():
                return
            await asyncio.sleep(poll_interval)

        raise AssertionError(error_msg)

    return _wait
