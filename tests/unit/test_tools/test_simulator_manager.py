# tests/unit/tools/test_simulator_manager.py
"""
Unit tests for SimulatorManager - Main orchestrator.

Tests the simulation lifecycle, configuration loading, device creation,
and physics engine coordination.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from tools.simulator_manager import SimulatorManager

# ================================================================
# FIXTURES
# ================================================================


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    return config_dir


@pytest.fixture
def minimal_config():
    """Minimal valid configuration for testing."""
    return {
        "simulation": {"runtime": {"update_interval": 0.1, "realtime": True}},
        "devices": [
            {
                "name": "test_turbine_plc",
                "type": "turbine_plc",
                "device_id": 1,
                "protocols": {},
                "physics_engine": "test_turbine_plc",
            }
        ],
        "network": {"networks": [], "devices": []},
    }


@pytest.fixture
def manager(temp_config_dir):
    """Create SimulatorManager instance with temp config."""
    with patch("tools.simulator_manager.Path.mkdir"):
        manager = SimulatorManager(config_dir=str(temp_config_dir))
    return manager


# ================================================================
# INITIALIZATION TESTS
# ================================================================


class TestSimulatorManagerInit:
    """Test SimulatorManager initialization."""

    def test_init_creates_directories(self, tmp_path):
        """Test that __init__ creates required directories."""
        config_dir = tmp_path / "test_config"

        with patch("tools.simulator_manager.Path.mkdir") as mock_mkdir:
            manager = SimulatorManager(config_dir=str(config_dir))

            assert manager.config_dir == config_dir
            assert mock_mkdir.called

    def test_init_creates_core_components(self, manager):
        """Test that __init__ creates core infrastructure components."""
        assert manager.config_loader is not None
        assert manager.sim_time is not None
        assert manager.system_state is not None
        assert manager.data_store is not None
        assert manager.network_sim is not None

    def test_init_initializes_empty_collections(self, manager):
        """Test that collections are initialized empty."""
        assert manager.turbine_physics == {}
        assert manager.hvac_physics == {}
        assert manager.reactor_physics == {}
        assert manager.grid_physics is None
        assert manager.power_flow is None
        assert manager.device_instances == {}
        assert manager.protocol_servers == {}

    def test_init_sets_initial_state(self, manager):
        """Test that simulation state flags are initialized."""
        assert manager._running is False
        assert manager._paused is False
        assert manager._initialised is False
        assert manager._simulation_task is None
        assert manager._update_count == 0


# ================================================================
# DEVICE REGISTRATION TESTS
# ================================================================


class TestDeviceRegistration:
    """Test device registration functionality."""

    @pytest.mark.asyncio
    async def test_register_devices_success(self, manager, minimal_config):
        """Test successful device registration."""
        with (
            patch.object(manager.data_store, "register_device") as mock_register,
            patch.object(manager.data_store, "set_device_online") as mock_online,
        ):
            await manager._register_devices(minimal_config)

            mock_register.assert_called_once()
            mock_online.assert_called_once_with("test_turbine_plc", True)

    @pytest.mark.asyncio
    async def test_register_devices_with_protocols(self, manager):
        """Test device registration with protocols."""
        config = {
            "devices": [
                {
                    "name": "modbus_plc",
                    "type": "turbine_plc",
                    "device_id": 1,
                    "protocols": {"modbus": {"port": 502}},
                }
            ]
        }

        with (
            patch.object(manager.data_store, "register_device") as mock_register,
            patch.object(manager.data_store, "set_device_online"),
        ):
            await manager._register_devices(config)

            call_kwargs = mock_register.call_args.kwargs
            assert "modbus" in call_kwargs["protocols"]

    @pytest.mark.asyncio
    async def test_register_devices_skips_invalid(self, manager):
        """Test that invalid devices are skipped."""
        config = {
            "devices": [
                {"name": "missing_type"},  # No type
                {"type": "missing_name"},  # No name
            ]
        }

        with patch.object(manager.data_store, "register_device") as mock_register:
            await manager._register_devices(config)

            assert mock_register.call_count == 0

    @pytest.mark.asyncio
    async def test_register_devices_empty_config(self, manager):
        """Test handling of empty device configuration."""
        config = {"devices": []}

        with patch.object(manager.data_store, "register_device") as mock_register:
            await manager._register_devices(config)

            assert mock_register.call_count == 0


# ================================================================
# PHYSICS ENGINE TESTS
# ================================================================


class TestPhysicsEngineCreation:
    """Test physics engine creation."""

    @pytest.mark.asyncio
    async def test_create_turbine_physics(self, manager):
        """Test turbine physics engine creation."""
        mock_turbine_device = Mock(device_name="test_turbine")

        # Return different devices based on device type
        async def get_devices_side_effect(device_type):
            if device_type == "turbine_plc":
                return [mock_turbine_device]
            return []

        with (
            patch.object(
                manager.data_store,
                "get_devices_by_type",
                side_effect=get_devices_side_effect,
            ),
            patch("tools.simulator_manager.TurbinePhysics") as mock_turbine_class,
            patch("tools.simulator_manager.GridPhysics") as mock_grid_class,
            patch("tools.simulator_manager.PowerFlow") as mock_pf_class,
        ):
            mock_turbine = AsyncMock()
            mock_turbine_class.return_value = mock_turbine
            mock_grid = AsyncMock()
            mock_grid_class.return_value = mock_grid
            mock_pf = AsyncMock()
            mock_pf_class.return_value = mock_pf

            await manager._create_physics_engines({})

            assert "test_turbine" in manager.turbine_physics
            mock_turbine.initialise.assert_called_once()
            # Grid and power flow should also be created since turbine exists
            mock_grid.initialise.assert_called_once()
            mock_pf.initialise.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_reactor_physics(self, manager):
        """Test reactor physics engine creation."""
        mock_reactor_device = Mock(device_name="test_reactor")

        # Return different devices based on device type
        async def get_devices_side_effect(device_type):
            if device_type == "reactor_plc":
                return [mock_reactor_device]
            return []

        with (
            patch.object(
                manager.data_store,
                "get_devices_by_type",
                side_effect=get_devices_side_effect,
            ),
            patch("tools.simulator_manager.ReactorPhysics") as mock_reactor_class,
        ):
            mock_reactor = AsyncMock()
            mock_reactor_class.return_value = mock_reactor

            await manager._create_physics_engines({})

            assert "test_reactor" in manager.reactor_physics
            mock_reactor.initialise.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_grid_physics_when_turbines_exist(self, manager):
        """Test grid physics created when turbines exist."""
        mock_turbine_device = Mock(device_name="turbine1")

        # Return different devices based on device type
        async def get_devices_side_effect(device_type):
            if device_type == "turbine_plc":
                return [mock_turbine_device]
            return []

        with (
            patch.object(
                manager.data_store,
                "get_devices_by_type",
                side_effect=get_devices_side_effect,
            ),
            patch("tools.simulator_manager.GridPhysics") as mock_grid_class,
            patch("tools.simulator_manager.PowerFlow") as mock_pf_class,
            patch("tools.simulator_manager.TurbinePhysics") as mock_turbine_class,
        ):
            mock_grid = AsyncMock()
            mock_grid_class.return_value = mock_grid
            mock_pf = AsyncMock()
            mock_pf_class.return_value = mock_pf
            mock_turbine = AsyncMock()
            mock_turbine_class.return_value = mock_turbine

            await manager._create_physics_engines({})

            assert manager.grid_physics is not None
            assert manager.power_flow is not None
            mock_grid.initialise.assert_called_once()
            mock_pf.initialise.assert_called_once()


# ================================================================
# LIFECYCLE TESTS
# ================================================================


class TestSimulationLifecycle:
    """Test simulation lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_requires_initialization(self, manager):
        """Test that start() fails if not initialized."""
        manager._initialised = False

        with pytest.raises(RuntimeError, match="not initialised"):
            await manager.start()

    @pytest.mark.asyncio
    async def test_start_success(self, manager):
        """Test successful simulation start."""
        manager._initialised = True

        with (
            patch.object(manager.sim_time, "start") as mock_time_start,
            patch.object(manager.data_store, "mark_simulation_running") as mock_mark,
            patch("asyncio.create_task") as mock_create_task,
        ):
            await manager.start()

            assert manager._running is True
            mock_time_start.assert_called_once()
            mock_mark.assert_called_once_with(True)
            mock_create_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_idempotent(self, manager):
        """Test that start() is idempotent (doesn't fail if already running)."""
        manager._initialised = True
        manager._running = True

        with patch.object(manager.sim_time, "start") as mock_time_start:
            await manager.start()

            # Should not call start again
            mock_time_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_success(self, manager):
        """Test successful simulation stop."""
        manager._running = True

        # Create a proper async task that can be awaited
        async def dummy_task():
            await asyncio.sleep(0.1)

        manager._simulation_task = asyncio.create_task(dummy_task())

        with (
            patch.object(manager.sim_time, "stop") as mock_time_stop,
            patch.object(manager.data_store, "mark_simulation_running") as mock_mark,
        ):
            await manager.stop()

            assert manager._running is False
            mock_time_stop.assert_called_once()
            mock_mark.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_stop_stops_protocol_servers(self, manager):
        """Test that stop() stops all protocol servers."""
        manager._running = True
        mock_server1 = AsyncMock()
        mock_server2 = AsyncMock()
        manager.protocol_servers = {"server1": mock_server1, "server2": mock_server2}

        with (
            patch.object(manager.sim_time, "stop"),
            patch.object(manager.data_store, "mark_simulation_running"),
        ):
            await manager.stop()

            mock_server1.stop.assert_called_once()
            mock_server2.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_stops_devices(self, manager):
        """Test that stop() stops all device instances."""
        manager._running = True
        mock_device = AsyncMock()
        manager.device_instances = {"device1": mock_device}

        with (
            patch.object(manager.sim_time, "stop"),
            patch.object(manager.data_store, "mark_simulation_running"),
        ):
            await manager.stop()

            mock_device.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_requires_running(self, manager):
        """Test that pause() requires simulation to be running."""
        manager._running = False

        with pytest.raises(RuntimeError, match="not running"):
            await manager.pause()

    @pytest.mark.asyncio
    async def test_pause_success(self, manager):
        """Test successful simulation pause."""
        manager._running = True
        manager._paused = False

        with patch.object(manager.sim_time, "pause") as mock_pause:
            await manager.pause()

            assert manager._paused is True
            mock_pause.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_success(self, manager):
        """Test successful simulation resume."""
        manager._paused = True

        with patch.object(manager.sim_time, "resume") as mock_resume:
            await manager.resume()

            assert manager._paused is False
            mock_resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_reset_stops_if_running(self, manager):
        """Test that reset() stops simulation if running."""
        manager._running = True
        manager._initialised = True

        with (
            patch.object(manager, "stop") as mock_stop,
            patch.object(manager.sim_time, "reset"),
            patch.object(manager.system_state, "reset"),
        ):
            await manager.reset()

            mock_stop.assert_called_once()
            assert manager._initialised is False


# ================================================================
# STATUS AND MONITORING TESTS
# ================================================================


class TestStatusMonitoring:
    """Test status and monitoring functionality."""

    @pytest.mark.asyncio
    async def test_get_status_returns_comprehensive_info(self, manager):
        """Test that get_status() returns comprehensive information."""
        manager._running = True
        manager._paused = False
        manager._initialised = True
        manager._update_count = 42

        with (
            patch.object(
                manager.sim_time, "get_status", return_value={"simulation_time": 10.0}
            ),
            patch.object(
                manager.data_store,
                "get_simulation_state",
                return_value={"devices": {"total": 5, "online": 5}},
            ),
            patch.object(
                manager.network_sim,
                "get_summary",
                return_value={"networks": {"count": 2}},
            ),
        ):
            status = await manager.get_status()

            assert status["running"] is True
            assert status["paused"] is False
            assert status["initialised"] is True
            assert status["update_count"] == 42
            assert "simulation_time" in status
            assert "system_state" in status
            assert "network" in status
            assert "physics" in status


# ================================================================
# PHYSICS ENGINE LOOKUP TESTS
# ================================================================


class TestPhysicsEngineLookup:
    """Test physics engine lookup functionality."""

    def test_get_physics_engine_by_name(self, manager):
        """Test physics engine lookup by name."""
        mock_turbine = Mock()
        manager.turbine_physics["turbine1"] = mock_turbine

        result = manager._get_physics_engine("turbine1")

        assert result is mock_turbine

    def test_get_physics_engine_by_type(self, manager):
        """Test physics engine lookup by type."""
        mock_turbine = Mock()
        manager.turbine_physics["some_turbine"] = mock_turbine

        result = manager._get_physics_engine("turbine_physics")

        assert result is mock_turbine

    def test_get_physics_engine_returns_none_when_not_found(self, manager):
        """Test that None is returned when engine not found."""
        result = manager._get_physics_engine("nonexistent")

        assert result is None

    def test_get_physics_engine_returns_none_for_empty_name(self, manager):
        """Test that None is returned for empty engine name."""
        result = manager._get_physics_engine(None)

        assert result is None


# ================================================================
# SIGNAL HANDLING TESTS
# ================================================================


class TestSignalHandling:
    """Test signal handling functionality."""

    def test_setup_signal_handlers(self, manager):
        """Test signal handler setup."""
        with patch("tools.simulator_manager.signal.signal") as mock_signal:
            manager.setup_signal_handlers()

            # Should register SIGINT and SIGTERM
            assert mock_signal.call_count == 2

    @pytest.mark.asyncio
    async def test_wait_for_shutdown(self, manager):
        """Test waiting for shutdown signal."""
        # Set the event immediately to avoid hanging
        manager._shutdown_event.set()

        # This should return immediately since event is set
        await manager.wait_for_shutdown()

        assert manager._shutdown_event.is_set()


# ================================================================
# ERROR HANDLING TESTS
# ================================================================


class TestErrorHandling:
    """Test error handling in SimulatorManager."""

    @pytest.mark.asyncio
    async def test_initialise_handles_config_load_failure(self, manager):
        """Test that initialize handles configuration load failures."""
        with patch.object(
            manager.config_loader,
            "load_all",
            side_effect=Exception("Config load failed"),
        ):
            with pytest.raises(RuntimeError, match="Failed to initialise"):
                await manager.initialise()

    @pytest.mark.asyncio
    async def test_stop_handles_server_stop_failure(self, manager):
        """Test that stop() handles server stop failures gracefully."""
        manager._running = True
        mock_server = AsyncMock()
        mock_server.stop.side_effect = Exception("Stop failed")
        manager.protocol_servers = {"server1": mock_server}

        with (
            patch.object(manager.sim_time, "stop"),
            patch.object(manager.data_store, "mark_simulation_running"),
        ):
            # Should not raise - should handle exception gracefully
            await manager.stop()

            assert manager._running is False

    @pytest.mark.asyncio
    async def test_stop_handles_device_stop_failure(self, manager):
        """Test that stop() handles device stop failures gracefully."""
        manager._running = True
        mock_device = AsyncMock()
        mock_device.stop.side_effect = Exception("Device stop failed")
        manager.device_instances = {"device1": mock_device}

        with (
            patch.object(manager.sim_time, "stop"),
            patch.object(manager.data_store, "mark_simulation_running"),
        ):
            # Should not raise - should handle exception gracefully
            await manager.stop()

            assert manager._running is False


# ================================================================
# SCADA CONFIGURATION TESTS
# ================================================================


class TestSCADAConfiguration:
    """Test SCADA server configuration."""

    @pytest.mark.asyncio
    async def test_configure_scada_servers_success(self, manager):
        """Test successful SCADA server configuration."""
        mock_scada = Mock()
        mock_scada.add_poll_target = Mock()
        mock_scada.add_tag = Mock()
        manager.device_instances = {"scada1": mock_scada}

        config = {
            "scada_servers": {
                "scada1": {
                    "poll_targets": [
                        {
                            "device": "plc1",
                            "protocol": "modbus",
                            "poll_rate": 1.0,
                        }
                    ],
                    "tags": [
                        {
                            "name": "temp",
                            "device": "plc1",
                            "address_type": "holding_registers",
                            "address": 0,
                        }
                    ],
                }
            }
        }

        await manager._configure_scada_servers(config)

        mock_scada.add_poll_target.assert_called_once()
        mock_scada.add_tag.assert_called_once()

    @pytest.mark.asyncio
    async def test_configure_scada_servers_skips_missing_device(self, manager):
        """Test that missing SCADA device is skipped gracefully."""
        config = {
            "scada_servers": {
                "nonexistent_scada": {
                    "poll_targets": [],
                    "tags": [],
                }
            }
        }

        # Should not raise - should skip gracefully
        await manager._configure_scada_servers(config)

    @pytest.mark.asyncio
    async def test_configure_scada_empty_config(self, manager):
        """Test handling of empty SCADA configuration."""
        config = {}

        # Should not raise
        await manager._configure_scada_servers(config)


# ================================================================
# HMI CONFIGURATION TESTS
# ================================================================


class TestHMIConfiguration:
    """Test HMI workstation configuration."""

    @pytest.mark.asyncio
    async def test_configure_hmi_workstations_success(self, manager):
        """Test successful HMI workstation configuration."""
        mock_hmi = Mock()
        mock_hmi.poll_targets = MagicMock()
        mock_hmi.add_poll_target = Mock()
        mock_hmi.add_screen = Mock()
        mock_hmi.navigate_to_screen = Mock()
        manager.device_instances = {"hmi1": mock_hmi}

        config = {
            "hmi_workstations": {
                "hmi1": {
                    "scada_server": "scada1",
                    "scan_interval": 0.5,
                    "screens": [
                        {
                            "name": "overview",
                            "tags": ["temp", "pressure"],
                            "controls": ["start", "stop"],
                        }
                    ],
                }
            }
        }

        await manager._configure_hmi_workstations(config)

        assert mock_hmi.scada_server == "scada1"
        mock_hmi.add_screen.assert_called_once()
        mock_hmi.navigate_to_screen.assert_called_once_with("overview")

    @pytest.mark.asyncio
    async def test_configure_hmi_empty_config(self, manager):
        """Test handling of empty HMI configuration."""
        config = {}

        # Should not raise
        await manager._configure_hmi_workstations(config)
