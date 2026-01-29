# components/security/authentication.py
"""
Authentication and authorisation for ICS simulator.

Provides:
- User authentication (simulated)
- Role-based access control (RBAC)
- Action authorisation
- Dual authorisation for critical operations
- Audit logging integration

Integrations:
- SimulationTime: Use simulation time for sessions/audit logs
- DataStore: Store audit logs and session data
- ConfigLoader: Load security settings from YAML

This is a SIMULATION of ICS security - simplified for PoC purposes.
Real ICS security would integrate with:
- LDAP/Active Directory
- Hardware tokens
- Physical access controls
- Certificate-based authentication
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from enum import Enum

from components.state.data_store import DataStore
from components.time.simulation_time import SimulationTime
from config.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------
# User roles and permissions
# ----------------------------------------------------------------

class UserRole(Enum):
    """ICS user roles with increasing privilege levels."""
    VIEWER = 1  # Read-only access
    OPERATOR = 2  # Normal operations, no configuration
    ENGINEER = 3  # Configuration, programming
    SUPERVISOR = 4  # Bypass, override, elevated operations
    ADMIN = 5  # Full system access


class PermissionType(Enum):
    """Types of actions requiring authorisation."""
    # Read operations
    VIEW_DATA = "view_data"
    VIEW_ALARMS = "view_alarms"

    # Control operations
    CONTROL_SETPOINT = "control_setpoint"
    CONTROL_START_STOP = "control_start_stop"
    CONTROL_MODE_CHANGE = "control_mode_change"

    # Configuration operations
    CONFIG_PARAMETER = "config_parameter"
    CONFIG_PROGRAM = "config_program"
    CONFIG_NETWORK = "config_network"

    # Safety-critical operations
    SAFETY_BYPASS = "safety_bypass"
    SAFETY_RESET = "safety_reset"
    SAFETY_FORCE = "safety_force"
    EMERGENCY_SHUTDOWN = "emergency_shutdown"

    # Administrative operations
    ADMIN_USER_MANAGEMENT = "admin_user_management"
    ADMIN_SYSTEM_CONFIG = "admin_system_config"


# Role-Permission mapping
ROLE_PERMISSIONS = {
    UserRole.VIEWER: {
        PermissionType.VIEW_DATA,
        PermissionType.VIEW_ALARMS,
    },
    UserRole.OPERATOR: {
        PermissionType.VIEW_DATA,
        PermissionType.VIEW_ALARMS,
        PermissionType.CONTROL_SETPOINT,
        PermissionType.CONTROL_START_STOP,
        PermissionType.CONTROL_MODE_CHANGE,
    },
    UserRole.ENGINEER: {
        PermissionType.VIEW_DATA,
        PermissionType.VIEW_ALARMS,
        PermissionType.CONTROL_SETPOINT,
        PermissionType.CONTROL_START_STOP,
        PermissionType.CONTROL_MODE_CHANGE,
        PermissionType.CONFIG_PARAMETER,
        PermissionType.CONFIG_PROGRAM,
        PermissionType.CONFIG_NETWORK,
        PermissionType.SAFETY_RESET,
    },
    UserRole.SUPERVISOR: {
        PermissionType.VIEW_DATA,
        PermissionType.VIEW_ALARMS,
        PermissionType.CONTROL_SETPOINT,
        PermissionType.CONTROL_START_STOP,
        PermissionType.CONTROL_MODE_CHANGE,
        PermissionType.CONFIG_PARAMETER,
        PermissionType.CONFIG_PROGRAM,
        PermissionType.SAFETY_BYPASS,
        PermissionType.SAFETY_RESET,
        PermissionType.SAFETY_FORCE,
        PermissionType.EMERGENCY_SHUTDOWN,
    },
    UserRole.ADMIN: set(PermissionType),  # All permissions
}


# ----------------------------------------------------------------
# User and session management
# ----------------------------------------------------------------

@dataclass
class User:
    """ICS user account."""
    username: str
    role: UserRole
    full_name: str = ""
    email: str = ""
    active: bool = True
    created_at: float = 0.0  # Simulation time
    last_login: float | None = None  # Simulation time


@dataclass
class AuthSession:
    """Active authentication session."""
    session_id: str
    user: User
    created_at: float  # Simulation time
    expires_at: float | None = None  # Simulation time
    source_ip: str = "127.0.0.1"

    def is_expired(self, current_time: float) -> bool:
        """Check if session has expired."""
        if self.expires_at is None:
            return False
        return current_time > self.expires_at


@dataclass
class AuditLogEntry:
    """Audit log entry for security events."""
    timestamp: float  # Simulation time
    user: str
    action: str
    resource: str
    result: str  # "ALLOWED" or "DENIED"
    reason: str = ""
    source_ip: str = "127.0.0.1"


# ----------------------------------------------------------------
# Authentication Manager (Singleton)
# ----------------------------------------------------------------

class AuthenticationManager:
    """
    Centralised authentication and authorisation manager.

    Singleton pattern - one instance for entire simulation.
    """

    _instance: "AuthenticationManager | None" = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self._initialized = True

            # Core integrations
            self.sim_time = SimulationTime()
            self.data_store: DataStore | None = None
            self.config = ConfigLoader().load_all()

            # User database (simulated)
            self.users: dict[str, User] = {}

            # Active sessions
            self.sessions: dict[str, AuthSession] = {}

            # Audit log
            self.audit_log: list[AuditLogEntry] = []

            # Lock for thread safety
            self._lock = asyncio.Lock()

            # Load configuration
            self._load_config()

            # Initialise default users
            self._create_default_users()

            logger.info("AuthenticationManager initialised")

    def _load_config(self) -> None:
        """Load authentication settings from YAML."""
        auth_cfg = self.config.get("simulation", {}).get("authentication", {})

        # Session timeout in simulation hours (None = no timeout)
        self.session_timeout_hours = auth_cfg.get("session_timeout_hours", None)

        # Max audit log entries
        self.max_audit_entries = auth_cfg.get("max_audit_entries", 10000)

    def _create_default_users(self) -> None:
        """Create default simulation users."""
        current_time = self.sim_time.now()

        default_users = [
            User("operator1", UserRole.OPERATOR, "John Operator", "operator1@example.com", created_at=current_time),
            User("engineer1", UserRole.ENGINEER, "Jane Engineer", "engineer1@example.com", created_at=current_time),
            User("supervisor1", UserRole.SUPERVISOR, "Bob Supervisor", "supervisor1@example.com",
                 created_at=current_time),
            User("admin", UserRole.ADMIN, "Admin User", "admin@example.com", created_at=current_time),
            User("viewer1", UserRole.VIEWER, "View Only", "viewer1@example.com", created_at=current_time),
        ]

        for user in default_users:
            self.users[user.username] = user

        logger.info(f"Created {len(default_users)} default users")

    # ----------------------------------------------------------------
    # User management
    # ----------------------------------------------------------------

    async def create_user(
            self,
            username: str,
            role: UserRole,
            full_name: str = "",
            email: str = "",
    ) -> User:
        """Create a new user account."""
        async with self._lock:
            if username in self.users:
                raise ValueError(f"User '{username}' already exists")

            user = User(
                username=username,
                role=role,
                full_name=full_name,
                email=email,
                created_at=self.sim_time.now(),
            )
            self.users[username] = user

            logger.info(f"Created user '{username}' with role {role.name}")
            return user

    async def get_user(self, username: str) -> User | None:
        """Get user by username."""
        async with self._lock:
            return self.users.get(username)

    async def update_user_role(self, username: str, new_role: UserRole) -> bool:
        """Update user's role."""
        async with self._lock:
            user = self.users.get(username)
            if not user:
                return False

            old_role = user.role
            user.role = new_role

            logger.info(
                f"Updated user '{username}' role: {old_role.name} → {new_role.name}"
            )
            return True

    # ----------------------------------------------------------------
    # Authentication
    # ----------------------------------------------------------------

    async def authenticate(
            self,
            username: str,
            password: str = "",  # Not validated in simulation
            source_ip: str = "127.0.0.1",
    ) -> str | None:
        """
        Authenticate user and create session.

        Note: In simulation mode, passwords are NOT validated.

        Args:
            username: Username
            password: Password (ignored in simulation)
            source_ip: Source IP address

        Returns:
            Session ID if successful, None if authentication failed
        """
        async with self._lock:
            user = self.users.get(username)

            if not user or not user.active:
                logger.warning(f"Authentication failed for '{username}' from {source_ip}")
                self._audit_log("AUTHENTICATION", username, "DENIED", "User not found or inactive")
                return None

            # NOTE: Password validation intentionally skipped in simulation
            _ = password  # Explicitly mark as intentionally unused

            # Create session
            import uuid
            session_id = str(uuid.uuid4())

            current_time = self.sim_time.now()

            # Calculate expiration
            expires_at = None
            if self.session_timeout_hours:
                expires_at = current_time + (self.session_timeout_hours * 3600)

            session = AuthSession(
                session_id=session_id,
                user=user,
                created_at=current_time,
                expires_at=expires_at,
                source_ip=source_ip,
            )

            self.sessions[session_id] = session
            user.last_login = current_time

            logger.info(
                f"User '{username}' authenticated from {source_ip} (session: {session_id[:8]}...)"
            )
            self._audit_log("AUTHENTICATION", username, "ALLOWED", f"From {source_ip}")

            return session_id

    async def logout(self, session_id: str) -> bool:
        """Logout and invalidate session."""
        async with self._lock:
            session = self.sessions.pop(session_id, None)
            if session:
                logger.info(f"User '{session.user.username}' logged out")
                return True
            return False

    async def get_session(self, session_id: str) -> AuthSession | None:
        """Get active session."""
        async with self._lock:
            session = self.sessions.get(session_id)
            if session and session.is_expired(self.sim_time.now()):
                self.sessions.pop(session_id)
                return None
            return session

    # ----------------------------------------------------------------
    # Authorisation
    # ----------------------------------------------------------------

    async def authorize(
            self,
            session_id: str,
            action: PermissionType | str,
            resource: str = "",
            reason: str = "",
    ) -> bool:
        """
        Check if user is authorised for an action.

        Args:
            session_id: Session ID
            action: Permission being requested
            resource: Resource being accessed
            reason: Reason for the action

        Returns:
            True if authorised, False otherwise
        """
        # Convert string to PermissionType if needed
        if isinstance(action, str):
            try:
                action = PermissionType(action)
            except ValueError:
                logger.warning(f"Unknown permission type: {action}")
                return False

        session = await self.get_session(session_id)
        if not session:
            logger.warning("Authorisation failed: Invalid or expired session")
            return False

        user = session.user

        # Check if user's role has this permission
        user_permissions = ROLE_PERMISSIONS.get(user.role, set())
        authorized = action in user_permissions

        result = "ALLOWED" if authorized else "DENIED"
        self._audit_log(
            action.value,
            user.username,
            result,
            f"Resource: {resource}, Reason: {reason}",
        )

        if authorized:
            logger.info(
                f"AUTHORISED: User '{user.username}' ({user.role.name}) - "
                f"{action.value} on {resource}"
            )
        else:
            logger.warning(
                f"DENIED: User '{user.username}' ({user.role.name}) - "
                f"{action.value} on {resource} (insufficient permissions)"
            )

        return authorized

    async def authorize_with_dual_auth(
            self,
            session_id_1: str,
            session_id_2: str,
            action: PermissionType,
            resource: str = "",
            reason: str = "",
    ) -> bool:
        """
        Dual authorisation (two-person rule) for critical operations.

        Both users must have permission for the action.

        Args:
            session_id_1: First user's session
            session_id_2: Second user's session
            action: Permission being requested
            resource: Resource being accessed
            reason: Reason for the action

        Returns:
            True if both users authorised
        """
        # Check both sessions
        auth1 = await self.authorize(session_id_1, action, resource, reason)
        auth2 = await self.authorize(session_id_2, action, resource, reason)

        session1 = await self.get_session(session_id_1)
        session2 = await self.get_session(session_id_2)

        if not (session1 and session2):
            return False

        # Both must be authorised and be different users
        if auth1 and auth2 and session1.user.username != session2.user.username:
            logger.warning(
                f"DUAL AUTHORISATION GRANTED: "
                f"{session1.user.username} + {session2.user.username} - "
                f"{action.value} on {resource}"
            )
            return True

        logger.warning(
            f"DUAL AUTHORISATION DENIED: "
            f"{session1.user.username} + {session2.user.username} - "
            f"{action.value} on {resource}"
        )
        return False

    # ----------------------------------------------------------------
    # DataStore integration
    # ----------------------------------------------------------------

    async def set_data_store(self, data_store: DataStore) -> None:
        """Set DataStore for persistent audit logging."""
        self.data_store = data_store

    async def store_audit_logs(self) -> None:
        """Store audit logs in DataStore."""
        if not self.data_store:
            return

        # Convert audit logs to JSON
        logs_json = json.dumps([
            {
                "timestamp": entry.timestamp,
                "user": entry.user,
                "action": entry.action,
                "resource": entry.resource,
                "result": entry.result,
                "reason": entry.reason,
                "source_ip": entry.source_ip,
            }
            for entry in self.audit_log[-1000:]  # Last 1000 entries
        ])

        await self.data_store.update_metadata(
            "authentication_manager",
            {"audit_logs": logs_json}
        )

    # ----------------------------------------------------------------
    # Audit log management
    # ----------------------------------------------------------------

    def _audit_log(
            self,
            action: str,
            user: str,
            result: str,
            reason: str = "",
    ) -> None:
        """Add entry to audit log."""
        entry = AuditLogEntry(
            timestamp=self.sim_time.now(),
            user=user,
            action=action,
            resource="",
            result=result,
            reason=reason,
        )
        self.audit_log.append(entry)

        # Keep last N entries
        if len(self.audit_log) > self.max_audit_entries:
            self.audit_log = self.audit_log[-self.max_audit_entries:]

    async def get_audit_log(
            self,
            limit: int = 100,
            user: str | None = None,
    ) -> list[AuditLogEntry]:
        """Get audit log entries."""
        async with self._lock:
            logs = self.audit_log[-limit:]
            if user:
                logs = [log for log in logs if log.user == user]
            return logs


# ----------------------------------------------------------------
# Convenience functions for device use
# ----------------------------------------------------------------

async def verify_authorization(
        authorization: str,
        action: str | PermissionType,
        resource: str = "",
) -> bool:
    """
    Verify authorisation for an action.

    This is a simplified interface for devices to use.
    In simulation, 'authorisation' can be:
    - A session ID
    - A username (auto-authenticates in simulation)
    - Format "username:action" for quick auth

    Args:
        authorization: Session ID, username, or "username:action"
        action: Permission type or string
        resource: Resource being accessed

    Returns:
        True if authorised
    """
    auth_mgr = AuthenticationManager()

    # Try as session ID first
    session = await auth_mgr.get_session(authorization)
    if session:
        return await auth_mgr.authorize(authorization, action, resource)

    # Try as username (auto-authenticate in simulation)
    if ":" in authorization:
        username, _ = authorization.split(":", 1)
    else:
        username = authorization

    user = await auth_mgr.get_user(username)
    if user:
        # Auto-create session for simulation convenience
        session_id = await auth_mgr.authenticate(username)
        if session_id:
            return await auth_mgr.authorize(session_id, action, resource)

    logger.warning(f"Invalid authorization token: {authorization}")
    return False


async def quick_auth(username: str) -> str | None:
    """Quick authentication for simulation (returns session ID)."""
    auth_mgr = AuthenticationManager()
    return await auth_mgr.authenticate(username)
