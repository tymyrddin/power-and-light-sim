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
                config["segmentation"] = network_data.get("segmentation", {})
                config["zones"] = network_data.get("zones", [])
                config["networks"] = network_data.get("networks", [])
                config["connections"] = network_data.get("connections", {})
                config["inter_zone_routing"] = network_data.get(
                    "inter_zone_routing", []
                )
                config["physical_topology"] = network_data.get("physical_topology", {})
        else:
            config["segmentation"] = {}
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

        # Load firewall config
        firewall_path = self.config_dir / "firewall.yml"
        if firewall_path.exists():
            with open(firewall_path) as f:
                firewall_data = yaml.safe_load(f)
                config["firewall"] = {
                    "default_action": firewall_data.get("default_action", "allow"),
                    "baseline_rules": firewall_data.get("baseline_rules", []),
                }
        else:
            config["firewall"] = {
                "default_action": "allow",
                "baseline_rules": [],
            }

        # Load IDS/IPS config
        ids_ips_path = self.config_dir / "ids_ips.yml"
        if ids_ips_path.exists():
            with open(ids_ips_path) as f:
                ids_data = yaml.safe_load(f)
                config["ids_ips"] = {
                    "prevention_mode": ids_data.get("prevention_mode", False),
                    "auto_block_on_critical": ids_data.get(
                        "auto_block_on_critical", True
                    ),
                    "permanent_blocked_ips": ids_data.get("permanent_blocked_ips", []),
                    "detection_thresholds": ids_data.get("detection_thresholds", {}),
                }
        else:
            config["ids_ips"] = {
                "prevention_mode": False,
                "auto_block_on_critical": True,
                "permanent_blocked_ips": [],
                "detection_thresholds": {},
            }
        # Load RBAC config
        rbac_path = self.config_dir / "rbac.yml"
        if rbac_path.exists():
            with open(rbac_path) as f:
                rbac_data = yaml.safe_load(f)
                config["rbac"] = {
                    "enforcement_enabled": rbac_data.get("enforcement_enabled", False),
                    "log_denials": rbac_data.get("log_denials", True),
                    "require_session": rbac_data.get("require_session", True),
                    "address_permissions": rbac_data.get("address_permissions", {}),
                    "default_users": rbac_data.get("default_users", []),
                }
        else:
            config["rbac"] = {
                "enforcement_enabled": False,
                "log_denials": True,
                "require_session": True,
                "address_permissions": {},
                "default_users": [],
            }

        # Load Modbus filtering config
        modbus_filtering_path = self.config_dir / "modbus_filtering.yml"
        if modbus_filtering_path.exists():
            with open(modbus_filtering_path) as f:
                modbus_data = yaml.safe_load(f)
                config["modbus_filtering"] = {
                    "enforcement_enabled": modbus_data.get(
                        "enforcement_enabled", False
                    ),
                    "global_policy": modbus_data.get("global_policy", {}),
                    "device_policies": modbus_data.get("device_policies", []),
                    "log_blocked_requests": modbus_data.get(
                        "log_blocked_requests", True
                    ),
                    "log_allowed_requests": modbus_data.get(
                        "log_allowed_requests", False
                    ),
                    "block_mode": modbus_data.get("block_mode", "reject"),
                }
        else:
            config["modbus_filtering"] = {
                "enforcement_enabled": False,
                "global_policy": {
                    "mode": "whitelist",
                    "allowed_function_codes": [1, 2, 3, 4, 5, 6],
                    "blocked_function_codes": [],
                },
                "device_policies": [],
                "log_blocked_requests": True,
                "log_allowed_requests": False,
                "block_mode": "reject",
            }

        # Load anomaly detection config
        anomaly_detection_path = self.config_dir / "anomaly_detection.yml"
        if anomaly_detection_path.exists():
            with open(anomaly_detection_path) as f:
                anomaly_data = yaml.safe_load(f)
                config["anomaly_detection"] = {
                    "enabled": anomaly_data.get("enabled", False),
                    "sigma_threshold": anomaly_data.get("sigma_threshold", 3.0),
                    "learning_window": anomaly_data.get("learning_window", 1000),
                    "alarm_flood_threshold": anomaly_data.get(
                        "alarm_flood_threshold", 10
                    ),
                    "alarm_flood_window": anomaly_data.get("alarm_flood_window", 60.0),
                    "baselines": anomaly_data.get("baselines", []),
                    "range_limits": anomaly_data.get("range_limits", []),
                    "rate_limits": anomaly_data.get("rate_limits", []),
                    "severity_mapping": anomaly_data.get("severity_mapping", {}),
                    "integration": anomaly_data.get("integration", {}),
                }
        else:
            config["anomaly_detection"] = {
                "enabled": False,
                "sigma_threshold": 3.0,
                "learning_window": 1000,
                "alarm_flood_threshold": 10,
                "alarm_flood_window": 60.0,
                "baselines": [],
                "range_limits": [],
                "rate_limits": [],
                "severity_mapping": {},
                "integration": {},
            }

        # Load OPC UA security config
        opcua_security_path = self.config_dir / "opcua_security.yml"
        if opcua_security_path.exists():
            with open(opcua_security_path) as f:
                opcua_data = yaml.safe_load(f)
                config["opcua_security"] = {
                    "enforcement_enabled": opcua_data.get("enforcement_enabled", False),
                    "security_policy": opcua_data.get(
                        "security_policy", "Aes256_Sha256_RsaPss"
                    ),
                    "cert_dir": opcua_data.get("cert_dir", "certs"),
                    "validity_hours": opcua_data.get("validity_hours", 8760),
                    "key_size": opcua_data.get("key_size", 2048),
                    "allow_anonymous": opcua_data.get("allow_anonymous", False),
                    "require_authentication": opcua_data.get(
                        "require_authentication", False
                    ),
                    "server_overrides": opcua_data.get("server_overrides", {}),
                }
        else:
            config["opcua_security"] = {
                "enforcement_enabled": False,
                "security_policy": "Aes256_Sha256_RsaPss",
                "cert_dir": "certs",
                "validity_hours": 8760,
                "key_size": 2048,
                "allow_anonymous": False,
                "require_authentication": False,
                "server_overrides": {},
            }

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
