from pathlib import Path

import pytest
import yaml

from config.config_loader import ConfigLoader


def test_save_devices_creates_file_and_logs(tmp_path, capsys):
    """
    Functional test: _save_devices() writes devices.yml
    and prints the creation message.
    """
    loader = ConfigLoader(config_dir=tmp_path)

    # Make some test devices
    devices = [
        {"name": "test_device", "type": "test_plc", "device_id": 99, "protocols": {}}
    ]

    # Call the protected _save_devices method
    loader._save_devices(devices)

    # File should exist
    devices_file = tmp_path / "devices.yml"
    assert devices_file.exists()

    # File contents should match what was saved
    with open(devices_file) as f:
        data = yaml.safe_load(f)
    assert "devices" in data
    assert data["devices"] == devices

    # Check stdout capture for creation message
    captured = capsys.readouterr()
    assert f"Created default devices config at {devices_file}" in captured.out


def test_load_all_creates_default_and_calls_save(tmp_path, capsys):
    """
    Functional test: load_all() triggers default creation if devices.yml is missing.
    """
    loader = ConfigLoader(config_dir=tmp_path)
    config = loader.load_all()

    devices_file = tmp_path / "devices.yml"
    # File should now exist
    assert devices_file.exists()

    # Capture printed message
    captured = capsys.readouterr()
    assert f"Created default devices config at {devices_file}" in captured.out

    # Devices in config should match file contents
    with open(devices_file) as f:
        file_data = yaml.safe_load(f)
    assert file_data["devices"] == config["devices"]
