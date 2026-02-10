# components/devices/enterprise_zone/modbus_filter.py
"""
Modbus Function Code Filter - Protocol-Level Security

Filters Modbus requests based on function codes (FCs).
Implements whitelist/blacklist policies to block dangerous operations:
- Write Multiple (FC 15/16) - Batch writes, malware
- Diagnostics (FC 08) - Device control/firmware
- MEI/Firmware (FC 43) - Firmware extraction/upload

Defense in depth: Protocol filtering + RBAC + Firewall
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from components.security.logging_system import EventSeverity, get_logger

if TYPE_CHECKING:
    from components.state.data_store import DataStore

logger = get_logger(__name__)


class PolicyMode(Enum):
    """Filter policy mode."""

    WHITELIST = "whitelist"  # Allow only listed function codes
    BLACKLIST = "blacklist"  # Block only listed function codes


@dataclass
class ModbusPolicy:
    """Modbus function code policy."""

    mode: PolicyMode
    allowed_function_codes: set[int]
    blocked_function_codes: set[int]


# Modbus function code names for logging
FUNCTION_CODE_NAMES = {
    1: "Read Coils",
    2: "Read Discrete Inputs",
    3: "Read Holding Registers",
    4: "Read Input Registers",
    5: "Write Single Coil",
    6: "Write Single Register",
    7: "Read Exception Status",
    8: "Diagnostics",
    11: "Get Comm Event Counter",
    12: "Get Comm Event Log",
    15: "Write Multiple Coils",
    16: "Write Multiple Registers",
    17: "Report Slave ID",
    20: "Read File Record",
    21: "Write File Record",
    22: "Mask Write Register",
    23: "Read/Write Multiple Registers",
    24: "Read FIFO Queue",
    43: "Read Device Identification / MEI",
}


class ModbusFilter:
    """
    Modbus function code filter for protocol-level security.

    Enforces whitelist/blacklist policies on Modbus function codes.
    Blocks dangerous operations like batch writes (FC 15/16), diagnostics (FC 08),
    and firmware access (FC 43).
    """

    def __init__(
        self,
        device_name: str = "modbus_filter",
        device_id: int = 600,
        data_store: DataStore | None = None,
        description: str = "Modbus Function Code Filter",
    ):
        """Initialize Modbus filter."""
        self.device_name = device_name
        self.device_id = device_id
        self.data_store = data_store
        self.description = description

        # Enforcement state
        self.enforcement_enabled = False

        # Global policy
        self.global_policy = ModbusPolicy(
            mode=PolicyMode.WHITELIST,
            allowed_function_codes={1, 2, 3, 4, 5, 6},
            blocked_function_codes=set(),
        )

        # Per-device policies (override global)
        self.device_policies: dict[str, ModbusPolicy] = {}

        # Logging configuration
        self.log_blocked_requests = True
        self.log_allowed_requests = False

        # Block mode: "reject" (send exception) or "drop" (silent)
        self.block_mode = "reject"

        # Statistics
        self.total_requests_checked = 0
        self.total_requests_blocked = 0
        self.blocked_by_function_code: dict[int, int] = {}  # FC -> count

        logger.info(
            f"Modbus filter '{self.device_name}' initialized (enforcement: {self.enforcement_enabled})"
        )

    async def load_config(self, config: dict[str, Any]) -> None:
        """Load configuration from config dict."""
        self.enforcement_enabled = config.get("enforcement_enabled", False)

        # Load global policy
        global_policy_config = config.get("global_policy", {})
        mode = global_policy_config.get("mode", "whitelist")
        allowed = set(
            global_policy_config.get("allowed_function_codes", [1, 2, 3, 4, 5, 6])
        )
        blocked = set(global_policy_config.get("blocked_function_codes", []))

        self.global_policy = ModbusPolicy(
            mode=PolicyMode(mode),
            allowed_function_codes=allowed,
            blocked_function_codes=blocked,
        )

        # Load device-specific policies
        device_policies_config = config.get("device_policies") or []
        for policy_config in device_policies_config:
            device_name = policy_config.get("device_name")
            if not device_name:
                continue

            mode = policy_config.get("mode", "whitelist")
            allowed = set(policy_config.get("allowed_function_codes", []))
            blocked = set(policy_config.get("blocked_function_codes", []))

            self.device_policies[device_name] = ModbusPolicy(
                mode=PolicyMode(mode),
                allowed_function_codes=allowed,
                blocked_function_codes=blocked,
            )

        # Load logging config
        self.log_blocked_requests = config.get("log_blocked_requests", True)
        self.log_allowed_requests = config.get("log_allowed_requests", False)
        self.block_mode = config.get("block_mode", "reject")

        logger.info(
            f"Modbus filter '{self.device_name}' loaded config: "
            f"enforcement={'ENABLED' if self.enforcement_enabled else 'DISABLED'}, "
            f"global_mode={self.global_policy.mode.value}, "
            f"device_policies={len(self.device_policies)}"
        )

    async def check_function_code(
        self,
        function_code: int,
        device_name: str = "unknown",
        source_ip: str = "unknown",
    ) -> tuple[bool, str]:
        """
        Check if function code is allowed.

        Args:
            function_code: Modbus function code (1-255)
            device_name: Target device name
            source_ip: Source IP address

        Returns:
            (allowed: bool, reason: str)
        """
        self.total_requests_checked += 1

        # If enforcement disabled, allow all
        if not self.enforcement_enabled:
            return True, "Enforcement disabled"

        # Get applicable policy (device-specific or global)
        policy = self.device_policies.get(device_name, self.global_policy)

        # Check policy
        allowed = self._check_policy(function_code, policy)

        # Log result
        fc_name = FUNCTION_CODE_NAMES.get(
            function_code, f"Unknown (0x{function_code:02X})"
        )

        if not allowed:
            self.total_requests_blocked += 1
            self.blocked_by_function_code[function_code] = (
                self.blocked_by_function_code.get(function_code, 0) + 1
            )

            reason = (
                f"FC {function_code} ({fc_name}) blocked by {policy.mode.value} policy"
            )

            if self.log_blocked_requests:
                await logger.log_security(
                    message=f"MODBUS BLOCKED: FC {function_code} ({fc_name}) from {source_ip} to {device_name}",
                    severity=EventSeverity.WARNING,
                    source_ip=source_ip,
                    data={
                        "function_code": function_code,
                        "function_name": fc_name,
                        "device": device_name,
                        "policy_mode": policy.mode.value,
                        "result": "BLOCKED",
                    },
                )

            return False, reason

        else:
            reason = (
                f"FC {function_code} ({fc_name}) allowed by {policy.mode.value} policy"
            )

            if self.log_allowed_requests:
                await logger.log_security(
                    message=f"MODBUS ALLOWED: FC {function_code} ({fc_name}) from {source_ip} to {device_name}",
                    severity=EventSeverity.INFO,
                    source_ip=source_ip,
                    data={
                        "function_code": function_code,
                        "function_name": fc_name,
                        "device": device_name,
                        "policy_mode": policy.mode.value,
                        "result": "ALLOWED",
                    },
                )

            return True, reason

    def _check_policy(self, function_code: int, policy: ModbusPolicy) -> bool:
        """Check if function code passes policy."""
        if policy.mode == PolicyMode.WHITELIST:
            # Whitelist: allow only if in allowed list
            return function_code in policy.allowed_function_codes
        else:
            # Blacklist: block only if in blocked list
            return function_code not in policy.blocked_function_codes

    def check_function_code_sync(
        self,
        function_code: int,
        device_name: str = "unknown",
    ) -> tuple[bool, str]:
        """
        Synchronous function code check (no async logging).

        Used by ModbusTCP server trace_pdu callback (synchronous context).
        Updates statistics but does not perform async logging.
        Use check_function_code() for full async logging.

        Args:
            function_code: Modbus function code (1-255)
            device_name: Target device name

        Returns:
            (allowed: bool, reason: str)
        """
        self.total_requests_checked += 1

        # If enforcement disabled, allow all
        if not self.enforcement_enabled:
            return True, "Enforcement disabled"

        # Get applicable policy (device-specific or global)
        policy = self.device_policies.get(device_name, self.global_policy)

        # Check policy
        allowed = self._check_policy(function_code, policy)

        # Get function code name
        fc_name = FUNCTION_CODE_NAMES.get(
            function_code, f"Unknown (0x{function_code:02X})"
        )

        # Update statistics
        if not allowed:
            self.total_requests_blocked += 1
            self.blocked_by_function_code[function_code] = (
                self.blocked_by_function_code.get(function_code, 0) + 1
            )
            reason = (
                f"FC {function_code} ({fc_name}) blocked by {policy.mode.value} policy"
            )
        else:
            reason = (
                f"FC {function_code} ({fc_name}) allowed by {policy.mode.value} policy"
            )

        return allowed, reason

    async def set_enforcement(self, enabled: bool, user: str = "system") -> None:
        """Enable/disable function code filtering (runtime)."""
        old_state = self.enforcement_enabled
        self.enforcement_enabled = enabled

        await logger.log_security(
            message=f"Modbus filter enforcement {'ENABLED' if enabled else 'DISABLED'} by {user}",
            severity=EventSeverity.WARNING if not enabled else EventSeverity.NOTICE,
            user=user,
            data={
                "old_state": old_state,
                "new_state": enabled,
                "device": self.device_name,
            },
        )

    async def set_device_policy(
        self,
        device_name: str,
        mode: PolicyMode,
        allowed_codes: set[int] | None = None,
        blocked_codes: set[int] | None = None,
        user: str = "system",
    ) -> None:
        """Set device-specific policy (runtime)."""
        policy = ModbusPolicy(
            mode=mode,
            allowed_function_codes=allowed_codes or set(),
            blocked_function_codes=blocked_codes or set(),
        )

        self.device_policies[device_name] = policy

        await logger.log_security(
            message=f"Modbus policy updated for '{device_name}' by {user}: {mode.value} mode",
            severity=EventSeverity.NOTICE,
            user=user,
            data={
                "device": device_name,
                "mode": mode.value,
                "allowed_codes": list(allowed_codes or []),
                "blocked_codes": list(blocked_codes or []),
            },
        )

    def get_statistics(self) -> dict[str, Any]:
        """Get filter statistics."""
        return {
            "enforcement_enabled": self.enforcement_enabled,
            "global_policy": {
                "mode": self.global_policy.mode.value,
                "allowed_codes": list(self.global_policy.allowed_function_codes),
                "blocked_codes": list(self.global_policy.blocked_function_codes),
            },
            "device_policies": len(self.device_policies),
            "total_requests_checked": self.total_requests_checked,
            "total_requests_blocked": self.total_requests_blocked,
            "block_rate": (
                self.total_requests_blocked / self.total_requests_checked
                if self.total_requests_checked > 0
                else 0
            ),
            "blocked_by_function_code": dict(self.blocked_by_function_code),
            "log_blocked": self.log_blocked_requests,
            "log_allowed": self.log_allowed_requests,
            "block_mode": self.block_mode,
        }
