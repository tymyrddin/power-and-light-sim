# tests/conftest.py
import pytest
from unittest.mock import patch

from components.time.simulation_time import SimulationTime


@pytest.fixture(autouse=True)
def reset_simulation_time_singleton():
    """
    SimulationTime is a singleton. Reset between tests or enjoy chaos.
    """
    SimulationTime._instance = None
    yield
    SimulationTime._instance = None


@pytest.fixture
def mock_config_realtime():
    with patch("components.time.simulation_time.ConfigLoader") as mock_loader:
        mock_loader.return_value.load_all.return_value = {
            "simulation": {
                "runtime": {
                    "update_interval": 0.01,
                    "realtime": True,
                    "time_acceleration": 1.0,
                }
            }
        }
        yield


@pytest.fixture
def mock_config_accelerated():
    with patch("components.time.simulation_time.ConfigLoader") as mock_loader:
        mock_loader.return_value.load_all.return_value = {
            "simulation": {
                "runtime": {
                    "update_interval": 0.01,
                    "realtime": False,
                    "time_acceleration": 10.0,
                }
            }
        }
        yield
