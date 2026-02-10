# components/security/__init__.py
"""
Security components for ICS simulator.

Modules:
- authentication: User authentication and RBAC
- anomaly_detector: Behavioral anomaly detection
- encryption: Data encryption and key management
- logging_system: Structured ICS logging with audit trail
- opcua_user_manager: OPC UA authentication bridge
"""

from components.security.authentication import (
    AuthenticationManager,
    PermissionType,
    UserRole,
)
from components.security.encryption import (
    CertificateInfo,
    CertificateManager,
    OPCUASecurityPolicy,
    SecurityLevel,
)
from components.security.logging_system import (
    AlarmPriority,
    AlarmState,
    EventCategory,
    EventSeverity,
    ICSLogger,
    get_logger,
)
from components.security.opcua_user_manager import OPCUAUserManager

__all__ = [
    # Authentication
    "AuthenticationManager",
    "UserRole",
    "PermissionType",
    # OPC UA Authentication
    "OPCUAUserManager",
    # Encryption
    "CertificateManager",
    "CertificateInfo",
    "OPCUASecurityPolicy",
    "SecurityLevel",
    # Logging
    "ICSLogger",
    "get_logger",
    "EventSeverity",
    "EventCategory",
    "AlarmPriority",
    "AlarmState",
]
