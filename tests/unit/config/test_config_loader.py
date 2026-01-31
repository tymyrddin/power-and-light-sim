# tests/unit/config/test_config_loader.py
import yaml

from config.config_loader import ConfigLoader


def test_create_default_devices(tmp_path):
    loader = ConfigLoader(config_dir=tmp_path)
    defaults = loader._create_default_devices()
    assert isinstance(defaults, list)
    assert len(defaults) >= 3
    names = [d["name"] for d in defaults]
    assert "turbine_plc_1" in names
    assert "substation_plc_1" in names
    assert "scada_server_1" in names


def test_save_and_load_devices(tmp_path):
    loader = ConfigLoader(config_dir=tmp_path)
    devices = loader._create_default_devices()
    loader._save_devices(devices)

    devices_path = tmp_path / "devices.yml"
    assert devices_path.exists()

    with open(devices_path) as f:
        data = yaml.safe_load(f)
    assert "devices" in data
    assert len(data["devices"]) == len(devices)
