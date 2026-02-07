# components/devices/enterprise_zone/enterprise_workstation.py
"""
Enterprise IT Workstation - The Phishing Target.

ATTACK NARRATIVE:
================
This workstation represents the classic entry point for targeted attacks on
industrial infrastructure. It's a corporate IT system with no direct access
to operational technology, but it's the starting point for a multi-stage
attack campaign:

ATTACK CHAIN SCENARIO:
1. **Initial Compromise (Phishing)**: Employee opens malicious Excel macro
   from "urgent invoice" email. Establishes C2 beacon on this workstation.

2. **Lateral Movement**: Attacker discovers VPN credentials in browser cache,
   saved passwords, or config files. VPN provides access from corporate
   network into DMZ.

3. **DMZ Breach**: From DMZ, attacker discovers jump servers, data historians,
   or poorly segmented networks. Harvests operational data, understands
   the industrial processes.

4. **Operations Zone Access**: Through misconfigured firewall rules or
   compromised jump server, attacker pivots into operations zone (SCADA/HMI).

5. **Control Zone Penetration**: From operations zone, attacker maps out
   PLCs, RTUs, and safety systems. Identifies attack targets (turbines,
   reactors, safety interlocks).

6. **Impact**: Attacker can now:
   - Exfiltrate process data (IP theft, competitive intelligence)
   - Manipulate setpoints (cause equipment damage)
   - Disable safety systems (create dangerous conditions)
   - Deploy ransomware across both IT and OT networks

REALISTIC CONTEXT:
==================
At UU Power & Light, this workstation is used by finance/accounting staff
to pull operational reports from the historian for billing, regulatory
reporting, and management dashboards. It has:

- Read-only access to historian data (via scheduled exports or OPC UA)
- VPN client installed (for remote work)
- Standard corporate IT security (antivirus, patching... in theory)
- User credentials that work across multiple systems
- Browser full of saved passwords
- Email client (primary attack vector)

VULNERABILITIES (Realistic):
=============================
- Users click on phishing emails (social engineering)
- Saved VPN credentials in plain text config files
- Browser password manager with weak master password
- Antivirus signatures outdated
- Users have local admin rights (legacy requirement)
- No application whitelisting
- Office macros enabled (because "business requires it")
- Personal USB drives allowed
- Remote desktop enabled

SECURITY VALUE:
===============
This device demonstrates why IT/OT network segmentation is critical.
Even though this workstation never talks directly to PLCs, it's a
stepping stone that attackers use to bridge the air gap between
corporate IT and industrial control systems.

Defense strategies this enables testing:
- Network segmentation effectiveness
- VPN security (MFA, certificate-based auth)
- Jump server hardening
- Data flow restrictions (one-way data diodes)
- Credential hygiene (no shared passwords across IT/OT)
- User behavior monitoring (detect lateral movement)
"""

from pathlib import Path
from typing import Any

from components.devices.core.base_device import BaseDevice
from components.security.logging_system import (
    AlarmPriority,
    AlarmState,
    EventSeverity,
)
from components.state.data_store import DataStore


class EnterpriseWorkstation(BaseDevice):
    """
    Enterprise IT workstation - the phishing target entry point.

    This device sits in the enterprise zone and has read-only access to
    historian data exports. It never directly communicates with PLCs,
    but serves as a realistic initial compromise point for attack scenarios.

    Security characteristics (realistic corporate IT):
    - User has local admin rights (legacy requirement)
    - VPN client installed (for remote work)
    - Saved passwords in browser/config files
    - Antivirus present but outdated
    - Office macros enabled (business requirement)
    - Email client (primary phishing vector)
    - Remote desktop enabled

    Network access:
    - Historian data exports (OPC UA client, scheduled reports)
    - Corporate email/file shares
    - VPN to DMZ (for "authorized remote access")
    - Internet access (browsing, email)

    Example:
        >>> workstation = EnterpriseWorkstation(
        ...     device_name="finance_workstation",
        ...     device_id=400,
        ...     data_store=data_store,
        ...     historian_source="historian_primary",
        ... )
        >>> await workstation.start()
    """

    def __init__(
        self,
        device_name: str,
        device_id: int,
        data_store: DataStore,
        historian_source: str = "historian_primary",
        description: str = "Enterprise workstation with historian access",
        scan_interval: float = 60.0,  # Check for historian data every minute
        log_dir: Path | None = None,
    ):
        """
        Initialize enterprise workstation.

        Args:
            device_name: Unique device identifier
            device_id: Numeric ID
            data_store: DataStore instance
            historian_source: Historian device to read data from
            description: Human-readable description
            scan_interval: Data collection interval in seconds
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
        self.historian_source = historian_source

        # Workstation details (for realism)
        self.computer_name = device_name.upper().replace("_", "-")
        self.username = "accounting"  # Generic user account
        self.domain = "UUPL-CORP"
        self.os_version = "Windows 10 Enterprise"
        self.os_build = "19045.3803"

        # Installed software (corporate standard image)
        self.installed_software = {
            "Microsoft Office 365": {
                "version": "16.0.16827",
                "macros_enabled": True,  # Required for "business process"
            },
            "Google Chrome": {
                "version": "120.0.6099.129",
                "passwords_saved": 47,  # Browser password manager
            },
            "Cisco AnyConnect VPN": {
                "version": "4.10.07061",
                "saved_profiles": ["DMZ-Access", "Remote-Work"],
            },
            "McAfee Endpoint Security": {
                "version": "10.7.0",
                "last_update": "2024-11-15",  # Outdated
                "status": "enabled",
            },
            "OSIsoft PI DataLink": {
                "version": "2021",
                "purpose": "Excel integration with historian",
            },
        }

        # Network access
        self.vpn_connected = False
        self.last_historian_sync = 0.0
        self.collected_reports = []

        # Alarm state tracking
        self.historian_failure_alarm_raised = False
        self.historian_failure_count = 0

        # Security vulnerabilities (for attack scenarios)
        self.saved_vpn_credentials = {
            "dmz_access": {
                "username": "accounting",
                "password": "Winter2023!",  # Weak but follows policy
                "profile": "DMZ-Access",
                "server": "vpn.uupl.com",
            }
        }

        self.browser_saved_passwords = {
            "historian.uupl.local": {
                "username": "reporting",
                "password": "Report123",
            },
            "email.uupl.com": {
                "username": "accounting@uupl.com",
                "password": "Winter2023!",  # Same as VPN!
            },
        }

        self.logger.info(
            f"EnterpriseWorkstation '{device_name}' initialized "
            f"(historian={historian_source}, scan={scan_interval}s)"
        )

    # ----------------------------------------------------------------
    # BaseDevice implementation
    # ----------------------------------------------------------------

    def _device_type(self) -> str:
        """Return 'enterprise_workstation' as device type."""
        return "enterprise_workstation"

    def _supported_protocols(self) -> list[str]:
        """Protocols supported (IT protocols, not OT)."""
        return ["http", "https", "smb", "rdp", "vpn"]

    async def _initialise_memory_map(self) -> None:
        """
        Initialize memory map.

        Simulates data visible on the workstation.
        """
        self.memory_map = {
            # System info
            "computer_name": self.computer_name,
            "username": self.username,
            "domain": self.domain,
            "os_version": self.os_version,
            # Network status
            "vpn_connected": False,
            "historian_connected": False,
            # Data collection
            "reports_collected": 0,
            "last_sync": 0.0,
        }

        self.logger.debug("Memory map initialized (enterprise workstation)")

    async def _scan_cycle(self) -> None:
        """
        Execute scan cycle.

        Periodically reads historian data exports (via OPC UA client or
        scheduled reports). Never directly accesses PLCs.
        """
        try:
            # Simulate reading historian data exports
            historian_status = await self.data_store.get_device_state(
                self.historian_source
            )

            if historian_status and historian_status.online:
                # Read historian data (simulated)
                self.last_historian_sync = self.sim_time.now()
                self.collected_reports.append(
                    {
                        "timestamp": self.last_historian_sync,
                        "source": self.historian_source,
                        "type": "operational_summary",
                    }
                )

                # Keep only last 100 reports
                if len(self.collected_reports) > 100:
                    self.collected_reports = self.collected_reports[-100:]

                # Update memory map
                self.memory_map["historian_connected"] = True
                self.memory_map["reports_collected"] = len(self.collected_reports)
                self.memory_map["last_sync"] = self.last_historian_sync

                # Reset failure count on success
                if self.historian_failure_count > 0:
                    self.historian_failure_count = 0

        except Exception as e:
            self.logger.error(f"Error reading historian data: {e}")
            self.memory_map["historian_connected"] = False
            self.historian_failure_count += 1

        # Check alarm conditions
        await self._check_alarm_conditions()

    # ----------------------------------------------------------------
    # Alarm conditions
    # ----------------------------------------------------------------

    async def _check_alarm_conditions(self) -> None:
        """Check and raise/clear alarms for critical conditions."""
        # Historian connection failure alarm (>3 consecutive failures)
        if self.historian_failure_count > 3 and not self.historian_failure_alarm_raised:
            await self.logger.log_alarm(
                message=f"Enterprise workstation '{self.device_name}': Historian connection failed ({self.historian_failure_count} failures)",
                priority=AlarmPriority.MEDIUM,
                state=AlarmState.ACTIVE,
                device=self.device_name,
                data={
                    "historian_source": self.historian_source,
                    "failure_count": self.historian_failure_count,
                },
            )
            self.historian_failure_alarm_raised = True
        elif self.historian_failure_count == 0 and self.historian_failure_alarm_raised:
            await self.logger.log_alarm(
                message=f"Enterprise workstation '{self.device_name}': Historian connection restored",
                priority=AlarmPriority.MEDIUM,
                state=AlarmState.CLEARED,
                device=self.device_name,
                data={"historian_source": self.historian_source},
            )
            self.historian_failure_alarm_raised = False

    # ----------------------------------------------------------------
    # Attack surface methods (for red team scenarios)
    # ----------------------------------------------------------------

    async def get_saved_credentials(self, user: str = "unknown") -> dict[str, Any]:
        """
        Get saved credentials from browser and VPN client.

        Simulates credential harvesting from compromised workstation.
        """
        await self.logger.log_security(
            message=f"Credential extraction from enterprise workstation '{self.device_name}'",
            severity=EventSeverity.CRITICAL,
            data={
                "device": self.device_name,
                "user": user,
                "vpn_credentials_exposed": len(self.saved_vpn_credentials),
                "browser_passwords_exposed": len(self.browser_saved_passwords),
            },
        )
        return {
            "vpn": self.saved_vpn_credentials,
            "browser": self.browser_saved_passwords,
        }

    async def connect_vpn(
        self, profile: str = "DMZ-Access", user: str = "unknown"
    ) -> bool:
        """
        Connect to VPN.

        Logs VPN connection as audit event.
        """
        if profile in self.installed_software["Cisco AnyConnect VPN"]["saved_profiles"]:
            self.vpn_connected = True
            self.memory_map["vpn_connected"] = True

            await self.logger.log_audit(
                message=f"VPN connection established from '{self.device_name}' to {profile}",
                user=user,
                action="vpn_connect",
                data={
                    "device": self.device_name,
                    "vpn_profile": profile,
                },
            )
            return True
        return False

    async def disconnect_vpn(self, user: str = "unknown") -> None:
        """Disconnect from VPN."""
        if self.vpn_connected:
            self.vpn_connected = False
            self.memory_map["vpn_connected"] = False

            await self.logger.log_audit(
                message=f"VPN connection closed from '{self.device_name}'",
                user=user,
                action="vpn_disconnect",
                data={"device": self.device_name},
            )

    def enumerate_network_access(self) -> dict[str, Any]:
        """
        Enumerate network access points.

        Shows what networks attacker can pivot to from this workstation.
        """
        return {
            "local_network": "enterprise_zone",
            "vpn_access": [
                {
                    "name": "DMZ-Access",
                    "destination": "dmz",
                    "credentials_available": True,
                },
            ],
            "accessible_services": [
                {"service": "historian", "protocol": "opcua", "access": "read-only"},
                {"service": "email", "protocol": "https", "access": "full"},
                {"service": "file_shares", "protocol": "smb", "access": "read-write"},
            ],
        }

    async def simulate_phishing_compromise(
        self, user: str = "accounting"
    ) -> dict[str, Any]:
        """
        Simulate successful phishing attack on this workstation.

        Returns information available to attacker after initial compromise.
        """
        await self.logger.log_security(
            message=f"Phishing attack simulation: User on '{self.device_name}' opened malicious attachment",
            severity=EventSeverity.CRITICAL,
            data={
                "device": self.device_name,
                "user": user,
                "attack_type": "phishing",
                "local_admin_access": True,
            },
        )

        return {
            "compromised": True,
            "access_level": "user",
            "local_admin": True,  # User has admin rights
            "credentials": await self.get_saved_credentials(user),
            "network_access": self.enumerate_network_access(),
            "installed_software": list(self.installed_software.keys()),
            "attack_paths": [
                "VPN to DMZ → Historian → Operations Zone → Control Zone",
                "File shares → Steal more credentials → Lateral movement",
                "Email → Phish other users → Expand access",
            ],
        }

    # ----------------------------------------------------------------
    # Status and telemetry
    # ----------------------------------------------------------------

    async def get_enterprise_status(self) -> dict[str, Any]:
        """Get enterprise workstation status."""
        base_status = await self.get_status()
        enterprise_status = {
            **base_status,
            "computer_name": self.computer_name,
            "username": self.username,
            "historian_source": self.historian_source,
            "vpn_connected": self.vpn_connected,
            "reports_collected": len(self.collected_reports),
        }
        return enterprise_status

    async def get_telemetry(self) -> dict[str, Any]:
        """Get enterprise workstation telemetry."""
        return {
            "device_name": self.device_name,
            "device_type": "enterprise_workstation",
            "system": {
                "computer_name": self.computer_name,
                "user": self.username,
                "domain": self.domain,
                "os": self.os_version,
            },
            "data_access": {
                "historian": self.historian_source,
                "reports_collected": len(self.collected_reports),
                "last_sync": self.last_historian_sync,
            },
            "network": {
                "zone": "enterprise",
                "vpn_available": True,
                "vpn_connected": self.vpn_connected,
            },
            "security": {
                "antivirus": "McAfee (outdated)",
                "macros_enabled": True,
                "local_admin": True,
                "saved_credentials": len(self.saved_vpn_credentials)
                + len(self.browser_saved_passwords),
                "attack_surface": "high",
            },
        }
