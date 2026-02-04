# config/config_loader.py
"""
Config loader module for modular YAML configuration.
"""

from pathlib import Path

import yaml


class ConfigLoader:
    """Loads and merges modular configuration files."""

    def __init__(self, config_dir="config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def load_all(self):
        """Load all configuration files and merge them."""
        config = {}

        # Load devices config
        devices_path = self.config_dir / "devices.yml"
        if devices_path.exists():
            with open(devices_path) as f:
                devices_data = yaml.safe_load(f)
                config["devices"] = devices_data.get("devices", [])
        else:
            config["devices"] = self._create_default_devices()
            self._save_devices(config["devices"])

        # Load network config
        network_path = self.config_dir / "network.yml"
        if network_path.exists():
            with open(network_path) as f:
                network_data = yaml.safe_load(f)
                config["zones"] = network_data.get("zones", [])
                config["networks"] = network_data.get("networks", [])
                config["connections"] = network_data.get("connections", {})
                config["inter_zone_routing"] = network_data.get(
                    "inter_zone_routing", []
                )
                config["physical_topology"] = network_data.get("physical_topology", {})
        else:
            config["zones"] = []
            config["networks"] = []
            config["connections"] = {}

        # Load protocols config
        protocols_path = self.config_dir / "protocols.yml"
        if protocols_path.exists():
            with open(protocols_path) as f:
                protocols_data = yaml.safe_load(f)
                config["protocol_settings"] = protocols_data.get("protocols", {})
                config["adapter_info"] = protocols_data.get("adapters", {})
        else:
            config["protocol_settings"] = {}
            config["adapter_info"] = {}

        # Load simulation config
        simulation_path = self.config_dir / "simulation.yml"
        if simulation_path.exists():
            with open(simulation_path) as f:
                simulation_data = yaml.safe_load(f)
                config["simulation"] = simulation_data.get("simulation", {})
        else:
            config["simulation"] = {}

        # Load SCADA tags config
        scada_tags_path = self.config_dir / "scada_tags.yml"
        if scada_tags_path.exists():
            with open(scada_tags_path) as f:
                scada_data = yaml.safe_load(f)
                config["scada_servers"] = scada_data.get("scada_servers", {})
        else:
            config["scada_servers"] = {}

        # Load HMI screens config
        hmi_screens_path = self.config_dir / "hmi_screens.yml"
        if hmi_screens_path.exists():
            with open(hmi_screens_path) as f:
                hmi_data = yaml.safe_load(f)
                config["hmi_workstations"] = hmi_data.get("hmi_workstations", {})
        else:
            config["hmi_workstations"] = {}

        # Load device identity config
        device_identity_path = self.config_dir / "device_identity.yml"
        if device_identity_path.exists():
            with open(device_identity_path) as f:
                identity_data = yaml.safe_load(f)
                config["device_identities"] = identity_data.get("device_identities", {})
        else:
            config["device_identities"] = {}

        return config

    def _create_default_devices(self):
        """Create default device configuration."""
        return [
            {
                "name": "turbine_plc_1",
                "type": "turbine_plc",
                "device_id": 1,
                "description": "Main steam turbine PLC",
                "protocols": {
                    "modbus": {
                        "adapter": "pymodbus_3114",
                        "host": "localhost",
                        "port": 15020,
                        "device_id": 1,
                        "simulator": True,
                    }
                },
            },
            {
                "name": "substation_plc_1",
                "type": "substation_plc",
                "device_id": 2,
                "description": "Main substation PLC",
                "protocols": {
                    "modbus": {
                        "adapter": "pymodbus_3114",
                        "host": "localhost",
                        "port": 15021,
                        "device_id": 2,
                        "simulator": True,
                    }
                },
            },
            {
                "name": "scada_server_1",
                "type": "scada_server",
                "device_id": 3,
                "description": "SCADA master station",
                "protocols": {
                    "modbus": {
                        "adapter": "pymodbus_3114",
                        "host": "localhost",
                        "port": 15022,
                        "device_id": 3,
                        "simulator": True,
                    }
                },
            },
        ]

    def _save_devices(self, devices):
        """Save devices configuration to file."""
        devices_path = self.config_dir / "devices.yml"
        with open(devices_path, "w") as f:
            yaml.dump({"devices": devices}, f, default_flow_style=False)
        print(f"[INFO] Created default devices config at {devices_path}")
