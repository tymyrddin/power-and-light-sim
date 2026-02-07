# components/devices/enterprise_zone/substation_controller.py
"""
Substation Automation Controller - Multi-Protocol SCADA Gateway.

This device represents a modern substation automation controller (SAC) that
bridges multiple industrial protocols in electrical distribution networks.
It monitors and controls circuit breakers, transformers, and protective relays.

**Protocols Supported:**
- **IEC 61850**: Modern power utility automation protocol
  - GOOSE (Generic Object Oriented Substation Events): Fast peer-to-peer messaging
  - MMS (Manufacturing Message Specification): Client-server data access
- **IEC-104** (IEC 60870-5-104): Legacy SCADA protocol for remote monitoring
- **Modbus TCP**: Industrial protocol for RTU/PLC communication

**Attack Surface:**
- Multiple protocol implementations = multiple attack vectors
- GOOSE has no authentication (can be spoofed)
- Legacy IEC-104 implementations often lack encryption
- Modbus has no security features (plaintext, no auth)
- Dual-homed network configuration (IT/OT boundary)
- Web interface for configuration (default credentials)
- Firmware updates via FTP (no verification)

**Realistic Context:**
At UU Power & Light, this controller manages a 69kV substation with:
- 4x circuit breakers (transmission lines)
- 2x power transformers (69kV/13.8kV)
- 8x IEDs (protection relays) communicating via IEC 61850
- SCADA master in control center using IEC-104
- Local HMI using Modbus TCP
- Emergency backup access via serial console

**Security Vulnerabilities (Intentional for Red Team):**
- Default credentials on web interface (admin/admin)
- GOOSE messages have no authentication
- IEC-104 has no encryption (plaintext SCADA commands)
- Modbus function code 100 enables debug mode
- Firmware upload via FTP with known credentials
- Hardcoded SSH key for vendor support access
- SNMP community string "public" enabled
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from components.devices.core.base_device import BaseDevice
from components.security.logging_system import (
    AlarmPriority,
    AlarmState,
    EventSeverity,
)
from components.state.data_store import DataStore


@dataclass
class CircuitBreaker:
    """Circuit breaker state."""

    name: str
    closed: bool = False  # Open = False, Closed = True
    lockout: bool = False
    trip_count: int = 0
    last_operation_time: float = 0.0


@dataclass
class Transformer:
    """Power transformer state."""

    name: str
    primary_voltage_kv: float = 0.0
    secondary_voltage_kv: float = 0.0
    load_mva: float = 0.0
    temperature_c: float = 25.0
    tap_position: int = 0  # -16 to +16


@dataclass
class GOOSEMessage:
    """IEC 61850 GOOSE message."""

    source_ied: str
    dataset: str
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)


class SubstationController(BaseDevice):
    """
    Substation Automation Controller with multi-protocol support.

    Supports IEC 61850 (GOOSE, MMS), IEC-104, and Modbus TCP for
    substation automation and SCADA integration.

    Example:
        >>> controller = SubstationController(
        ...     device_name="substation_69kv_main",
        ...     device_id=1,
        ...     data_store=data_store,
        ...     substation_name="Main Substation",
        ...     voltage_level_kv=69.0,
        ... )
        >>> await controller.start()
        >>> await controller.close_breaker("CB_LINE_1", user="operator")
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        substation_name: str = "Substation",
        voltage_level_kv: float = 69.0,
        description: str = "Substation automation controller",
        scan_interval: float = 1.0,
        log_dir: Path | None = None,
    ):
        """
        Initialize substation controller.

        Args:
            device_name: Unique device identifier
            device_id: Numeric ID
            data_store: DataStore instance
            substation_name: Substation name
            voltage_level_kv: Primary voltage level
            description: Human-readable description
            scan_interval: Scan cycle interval
            log_dir: Directory for log files
        """
        super().__init__(
            device_name=device_name,
            device_id=device_id,
            data_store=data_store,
            description=description,
            scan_interval=scan_interval,
            log_dir=log_dir,
        )

        # Configuration
        self.substation_name = substation_name
        self.voltage_level_kv = voltage_level_kv

        # Circuit breakers
        self.breakers: dict[str, CircuitBreaker] = {
            "CB_LINE_1": CircuitBreaker("Line 1"),
            "CB_LINE_2": CircuitBreaker("Line 2"),
            "CB_LINE_3": CircuitBreaker("Line 3"),
            "CB_LINE_4": CircuitBreaker("Line 4"),
        }

        # Transformers
        self.transformers: dict[str, Transformer] = {
            "XFMR_1": Transformer(
                "Transformer 1", primary_voltage_kv=69.0, secondary_voltage_kv=13.8
            ),
            "XFMR_2": Transformer(
                "Transformer 2", primary_voltage_kv=69.0, secondary_voltage_kv=13.8
            ),
        }

        # IEC 61850 state
        self.goose_messages: list[GOOSEMessage] = []
        self.goose_subscriptions: list[str] = []  # IEDs we're subscribed to

        # IEC-104 state
        self.iec104_connected = False
        self.iec104_master_ip = "192.168.1.100"  # SCADA master

        # Security vulnerabilities (for attack scenarios)
        self.web_credentials = {"username": "admin", "password": "admin"}
        self.ftp_credentials = {"username": "firmware", "password": "update123"}
        self.vendor_ssh_key = "ssh-rsa AAAAB3NzaC1... vendor@support"
        self.snmp_community = "public"
        self.debug_mode_enabled = False

        # Alarm state tracking
        self.breaker_trip_alarm_raised = {}
        for breaker_name in self.breakers:
            self.breaker_trip_alarm_raised[breaker_name] = False

        self.transformer_overload_alarm_raised = {}
        for xfmr_name in self.transformers:
            self.transformer_overload_alarm_raised[xfmr_name] = False

        self.logger.info(
            f"SubstationController '{device_name}' initialized "
            f"({substation_name}, {voltage_level_kv}kV)"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return 'substation_controller' as device type."""
        return "substation_controller"

    def _supported_protocols(self) -> list[str]:
        """Protocols supported."""
        return ["iec61850_goose", "iec61850_mms", "iec104", "modbus"]

    async def _initialise_memory_map(self) -> None:
        """
        Initialize memory map.

        Maps data to different protocol address spaces:
        - IEC 61850: Logical nodes and data objects
        - IEC-104: Information objects (single points, measured values)
        - Modbus: Coils and holding registers
        """
        self.memory_map = {
            # IEC 61850 Logical Nodes (simplified)
            "ied_name": f"{self.substation_name}_SAC",
            "goose_enabled": True,
            # Circuit breaker states (mapped to all protocols)
            "CB_LINE_1_closed": False,
            "CB_LINE_2_closed": False,
            "CB_LINE_3_closed": False,
            "CB_LINE_4_closed": False,
            # Transformer states
            "XFMR_1_load_mva": 0.0,
            "XFMR_2_load_mva": 0.0,
            "XFMR_1_temp_c": 25.0,
            "XFMR_2_temp_c": 25.0,
            # IEC-104 connection status
            "iec104_connected": False,
            "iec104_master_ip": self.iec104_master_ip,
            # Protocol statistics
            "goose_messages_sent": 0,
            "goose_messages_received": 0,
            "iec104_commands_received": 0,
            "modbus_requests_received": 0,
        }

        self.logger.debug("Memory map initialized (substation controller)")

    async def _scan_cycle(self) -> None:
        """
        Execute scan cycle.

        Updates measurements, processes GOOSE messages, and checks alarm conditions.
        """
        try:
            # Simulate measurement updates (would come from IEDs in real system)
            await self._update_measurements()

            # Process any pending GOOSE messages
            await self._process_goose_messages()

            # Update memory map
            self.memory_map["CB_LINE_1_closed"] = self.breakers["CB_LINE_1"].closed
            self.memory_map["CB_LINE_2_closed"] = self.breakers["CB_LINE_2"].closed
            self.memory_map["CB_LINE_3_closed"] = self.breakers["CB_LINE_3"].closed
            self.memory_map["CB_LINE_4_closed"] = self.breakers["CB_LINE_4"].closed

            self.memory_map["XFMR_1_load_mva"] = self.transformers["XFMR_1"].load_mva
            self.memory_map["XFMR_2_load_mva"] = self.transformers["XFMR_2"].load_mva
            self.memory_map["XFMR_1_temp_c"] = self.transformers["XFMR_1"].temperature_c
            self.memory_map["XFMR_2_temp_c"] = self.transformers["XFMR_2"].temperature_c

            self.memory_map["iec104_connected"] = self.iec104_connected
            self.memory_map["goose_messages_sent"] = len(self.goose_messages)

            # Check alarm conditions
            await self._check_alarm_conditions()

        except Exception as e:
            self.logger.error(f"Error in scan cycle: {e}")

    async def _update_measurements(self) -> None:
        """Update measurements from connected IEDs (simulated)."""
        # In real implementation, would read from IEDs via GOOSE/MMS
        # For now, maintain current values
        pass

    async def _process_goose_messages(self) -> None:
        """Process received GOOSE messages from IEDs."""
        # Simulated - would receive actual GOOSE multicast messages
        pass

    # ----------------------------------------------------------------
    # Breaker control operations
    # ----------------------------------------------------------------

    async def close_breaker(self, breaker_name: str, user: str = "operator") -> bool:
        """
        Close a circuit breaker.

        Args:
            breaker_name: Breaker to close
            user: User issuing command

        Returns:
            True if successful
        """
        if breaker_name not in self.breakers:
            return False

        breaker = self.breakers[breaker_name]

        if breaker.lockout:
            await self.logger.log_security(
                message=f"Breaker close command rejected - lockout active: {breaker_name}",
                severity=EventSeverity.WARNING,
                data={
                    "breaker": breaker_name,
                    "user": user,
                    "reason": "lockout_active",
                },
            )
            return False

        # Execute close command
        breaker.closed = True
        breaker.last_operation_time = self.sim_time.now()

        await self.logger.log_audit(
            message=f"Circuit breaker closed: {breaker_name}",
            user=user,
            action="breaker_close",
            data={"breaker": breaker_name, "device": self.device_name},
        )

        # Publish GOOSE message
        await self._publish_goose_breaker_status(breaker_name)

        return True

    async def open_breaker(self, breaker_name: str, user: str = "operator") -> bool:
        """
        Open a circuit breaker.

        Args:
            breaker_name: Breaker to open
            user: User issuing command

        Returns:
            True if successful
        """
        if breaker_name not in self.breakers:
            return False

        breaker = self.breakers[breaker_name]

        # Execute open command
        breaker.closed = False
        breaker.trip_count += 1
        breaker.last_operation_time = self.sim_time.now()

        await self.logger.log_audit(
            message=f"Circuit breaker opened: {breaker_name}",
            user=user,
            action="breaker_open",
            data={"breaker": breaker_name, "device": self.device_name},
        )

        # Publish GOOSE message
        await self._publish_goose_breaker_status(breaker_name)

        return True

    async def _publish_goose_breaker_status(self, breaker_name: str) -> None:
        """Publish GOOSE message for breaker status change."""
        breaker = self.breakers[breaker_name]

        goose_msg = GOOSEMessage(
            source_ied=self.memory_map["ied_name"],
            dataset=f"{breaker_name}_Status",
            timestamp=self.sim_time.now(),
            data={
                "breaker": breaker_name,
                "closed": breaker.closed,
                "lockout": breaker.lockout,
            },
        )

        self.goose_messages.append(goose_msg)

        await self.logger.log_security(
            message=f"GOOSE message published: {breaker_name} status",
            severity=EventSeverity.INFO,
            data={
                "protocol": "iec61850_goose",
                "dataset": goose_msg.dataset,
                "breaker_closed": breaker.closed,
            },
        )

    # ----------------------------------------------------------------
    # Alarm conditions
    # ----------------------------------------------------------------

    async def _check_alarm_conditions(self) -> None:
        """Check and raise/clear alarms for fault conditions."""
        # Breaker trip alarms
        for breaker_name, breaker in self.breakers.items():
            if (
                breaker.trip_count > 3
                and not self.breaker_trip_alarm_raised[breaker_name]
            ):
                await self.logger.log_alarm(
                    message=f"Repeated breaker trips on '{self.device_name}': {breaker_name} ({breaker.trip_count} trips)",
                    priority=AlarmPriority.HIGH,
                    state=AlarmState.ACTIVE,
                    device=self.device_name,
                    data={
                        "breaker": breaker_name,
                        "trip_count": breaker.trip_count,
                    },
                )
                self.breaker_trip_alarm_raised[breaker_name] = True

        # Transformer overload alarms
        for xfmr_name, xfmr in self.transformers.items():
            # Assume 50 MVA rated transformers
            overload = xfmr.load_mva > 50.0

            if overload and not self.transformer_overload_alarm_raised[xfmr_name]:
                await self.logger.log_alarm(
                    message=f"Transformer overload on '{self.device_name}': {xfmr_name} ({xfmr.load_mva:.1f} MVA)",
                    priority=AlarmPriority.HIGH,
                    state=AlarmState.ACTIVE,
                    device=self.device_name,
                    data={
                        "transformer": xfmr_name,
                        "load_mva": xfmr.load_mva,
                        "rated_mva": 50.0,
                    },
                )
                self.transformer_overload_alarm_raised[xfmr_name] = True

            elif not overload and self.transformer_overload_alarm_raised[xfmr_name]:
                await self.logger.log_alarm(
                    message=f"Transformer overload cleared on '{self.device_name}': {xfmr_name}",
                    priority=AlarmPriority.HIGH,
                    state=AlarmState.CLEARED,
                    device=self.device_name,
                    data={"transformer": xfmr_name, "load_mva": xfmr.load_mva},
                )
                self.transformer_overload_alarm_raised[xfmr_name] = False

    # ----------------------------------------------------------------
    # Attack surface (for red team scenarios)
    # ----------------------------------------------------------------

    async def web_login(self, username: str, password: str) -> bool:
        """
        Web interface login.

        Simulates web interface authentication (default credentials).
        """
        success = (
            username == self.web_credentials["username"]
            and password == self.web_credentials["password"]
        )

        await self.logger.log_security(
            message=f"Web interface login attempt on '{self.device_name}': {username}",
            severity=EventSeverity.WARNING if success else EventSeverity.ERROR,
            data={
                "username": username,
                "success": success,
                "source": "web_interface",
            },
        )

        return success

    async def enable_debug_mode(self, user: str = "unknown") -> bool:
        """
        Enable debug mode (Modbus function code 100).

        VULNERABILITY: Undocumented debug mode accessible via Modbus.
        """
        self.debug_mode_enabled = True

        await self.logger.log_security(
            message=f"DEBUG MODE ENABLED on '{self.device_name}' by {user}",
            severity=EventSeverity.CRITICAL,
            data={
                "device": self.device_name,
                "user": user,
                "protocol": "modbus",
            },
        )

        return True

    def get_vulnerabilities(self) -> list[dict[str, Any]]:
        """
        Enumerate security vulnerabilities.

        Returns list of known security issues for attack scenario documentation.
        """
        return [
            {
                "id": "GOOSE-SPOOF",
                "name": "GOOSE Message Spoofing",
                "description": "GOOSE messages have no authentication",
                "severity": "critical",
                "protocol": "iec61850_goose",
                "exploitable": True,
            },
            {
                "id": "DEFAULT-CREDS",
                "name": "Default Web Credentials",
                "description": "Web interface uses default admin/admin",
                "severity": "high",
                "credentials": self.web_credentials,
                "exploitable": True,
            },
            {
                "id": "IEC104-PLAINTEXT",
                "name": "IEC-104 No Encryption",
                "description": "SCADA commands sent in plaintext",
                "severity": "high",
                "protocol": "iec104",
                "exploitable": True,
            },
            {
                "id": "MODBUS-DEBUG",
                "name": "Undocumented Debug Mode",
                "description": "Modbus function code 100 enables debug mode",
                "severity": "critical",
                "protocol": "modbus",
                "function_code": 100,
                "exploitable": True,
            },
            {
                "id": "FTP-FIRMWARE",
                "name": "Insecure Firmware Update",
                "description": "Firmware upload via FTP with known credentials",
                "severity": "critical",
                "credentials": self.ftp_credentials,
                "exploitable": True,
            },
            {
                "id": "VENDOR-BACKDOOR",
                "name": "Vendor SSH Backdoor",
                "description": "Hardcoded SSH key for vendor support",
                "severity": "critical",
                "ssh_key": self.vendor_ssh_key,
                "exploitable": True,
            },
        ]

    # ----------------------------------------------------------------
    # Status and telemetry
    # ----------------------------------------------------------------

    async def get_substation_status(self) -> dict[str, Any]:
        """Get substation controller status."""
        base_status = await self.get_status()
        substation_status = {
            **base_status,
            "substation_name": self.substation_name,
            "voltage_level_kv": self.voltage_level_kv,
            "breakers": {
                name: {
                    "closed": breaker.closed,
                    "lockout": breaker.lockout,
                    "trip_count": breaker.trip_count,
                }
                for name, breaker in self.breakers.items()
            },
            "transformers": {
                name: {
                    "load_mva": xfmr.load_mva,
                    "temperature_c": xfmr.temperature_c,
                }
                for name, xfmr in self.transformers.items()
            },
            "iec104_connected": self.iec104_connected,
            "goose_messages_sent": len(self.goose_messages),
        }
        return substation_status

    async def get_telemetry(self) -> dict[str, Any]:
        """Get substation controller telemetry."""
        return {
            "device_name": self.device_name,
            "device_type": "substation_controller",
            "substation": {
                "name": self.substation_name,
                "voltage_kv": self.voltage_level_kv,
            },
            "breakers": len(self.breakers),
            "transformers": len(self.transformers),
            "protocols": {
                "iec61850_goose": True,
                "iec61850_mms": True,
                "iec104": self.iec104_connected,
                "modbus": True,
            },
            "security": {
                "vulnerabilities": len(self.get_vulnerabilities()),
                "debug_mode": self.debug_mode_enabled,
                "default_credentials": True,
            },
        }
