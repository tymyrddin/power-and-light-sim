# components/security/opcua_user_manager.py
"""
OPC UA User Manager - bridges asyncua authentication to the simulator's AuthenticationManager.

Implements asyncua's UserManager interface to validate OPC UA client credentials
against the RBAC user database (Challenge 1: Password Protect the SCADA).

The asyncua UserManager.get_user() method is synchronous, so this module uses
the sync/async bridge pattern (same as Modbus Filter in Challenge 5):
- Sync decision: check auth_mgr.users dict directly (no await needed)
- Async logging: asyncio.create_task() for audit trail (fire-and-forget)
"""

import asyncio

from asyncua.server.user_managers import UserManager

from components.security.logging_system import EventSeverity, get_logger

logger = get_logger(__name__)


class OPCUAUserManager(UserManager):
    """
    Custom OPC UA user manager that validates credentials against AuthenticationManager.

    Maps simulator roles to asyncua UserRole values for OPC UA access control.
    """

    def __init__(self, auth_manager):
        """
        Initialise with a reference to the simulator's AuthenticationManager.

        Args:
            auth_manager: AuthenticationManager instance with .users dict
        """
        self.auth_manager = auth_manager
        self._stats = {
            "total_attempts": 0,
            "successful": 0,
            "failed": 0,
            "rejected_anonymous": 0,
        }

    def get_user(self, iserver, username=None, password=None, certificate=None):
        """
        Validate OPC UA client credentials.

        Called by asyncua when a client connects. This method is synchronous
        (asyncua requirement), so we check auth_mgr.users directly and use
        create_task() for async audit logging.

        Args:
            iserver: asyncua internal server instance
            username: Client-provided username (None for anonymous)
            password: Client-provided password (not validated in simulation)
            certificate: Client certificate (not used for password auth)

        Returns:
            asyncua User with mapped role on success, None to reject
        """
        from asyncua.server.user_managers import User as OPCUAUser, UserRole as OPCUAUserRole

        self._stats["total_attempts"] += 1

        # Reject anonymous connections
        if username is None:
            self._stats["rejected_anonymous"] += 1
            self._schedule_audit_log(
                username="<anonymous>",
                success=False,
                reason="Anonymous access denied (authentication required)",
            )
            return None

        # Look up user in RBAC database
        user = self.auth_manager.users.get(username)

        if user is None:
            self._stats["failed"] += 1
            self._schedule_audit_log(
                username=username,
                success=False,
                reason="Unknown user",
            )
            return None

        if not user.active:
            self._stats["failed"] += 1
            self._schedule_audit_log(
                username=username,
                success=False,
                reason="Account locked",
            )
            return None

        # Map simulator role to asyncua role
        opcua_role = self._map_role(user.role)

        self._stats["successful"] += 1
        self._schedule_audit_log(
            username=username,
            success=True,
            reason=f"Authenticated as {user.role.name} (OPC UA role: {opcua_role.name})",
        )

        return OPCUAUser(role=opcua_role, name=username)

    def _map_role(self, sim_role):
        """
        Map simulator UserRole to asyncua UserRole.

        asyncua has limited roles (Admin, Anonymous, User), so we map:
        - ADMIN, SUPERVISOR -> Admin (full OPC UA access)
        - ENGINEER, OPERATOR, VIEWER -> User (standard access)
        """
        from asyncua.server.user_managers import UserRole as OPCUAUserRole

        # Import here to avoid circular imports at module level
        from components.security.authentication import UserRole

        if sim_role in (UserRole.ADMIN, UserRole.SUPERVISOR):
            return OPCUAUserRole.Admin
        return OPCUAUserRole.User

    def _schedule_audit_log(self, username, success, reason=""):
        """
        Schedule async audit log entry (fire-and-forget).

        Uses asyncio.create_task() to log without blocking the sync get_user() method.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._log_auth_attempt(username, success, reason))
        except RuntimeError:
            # No event loop running (e.g. in tests) - log synchronously instead
            level = "INFO" if success else "WARNING"
            result = "SUCCESS" if success else "DENIED"
            logger.log(level, f"OPC UA auth {result}: {username} - {reason}")

    async def _log_auth_attempt(self, username, success, reason):
        """Log authentication attempt via ICSLogger."""
        severity = EventSeverity.NOTICE if success else EventSeverity.WARNING
        result = "SUCCESS" if success else "DENIED"

        logger.log_security(
            message=f"OPC UA authentication {result}: {username} - {reason}",
            severity=severity,
            data={
                "username": username,
                "result": result,
                "reason": reason,
                "protocol": "opcua",
            },
        )

    def get_statistics(self):
        """Return authentication statistics."""
        return dict(self._stats)
