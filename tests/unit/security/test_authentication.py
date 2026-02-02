# tests/unit/security/test_authentication.py
"""Comprehensive tests for authentication and authorisation system.

Test Coverage:
- UserRole and PermissionType enums
- Role-permission mappings
- User and AuthSession dataclasses
- AuthenticationManager singleton
- User management (create, get, update)
- Authentication (login, logout, sessions)
- Authorisation (single and dual)
- Audit logging integration
- Thread safety
"""

import asyncio
import threading

import pytest

from components.security.authentication import (
    ROLE_PERMISSIONS,
    AuthenticationManager,
    AuthSession,
    PermissionType,
    User,
    UserRole,
    quick_auth,
    verify_authorization,
)


# ================================================================
# ENUM TESTS
# ================================================================
class TestUserRole:
    """Test UserRole enum."""

    def test_role_privilege_ordering(self):
        """Test that roles have increasing privilege levels.

        WHY: RBAC requires clear privilege hierarchy.
        """
        assert UserRole.VIEWER.value < UserRole.OPERATOR.value
        assert UserRole.OPERATOR.value < UserRole.ENGINEER.value
        assert UserRole.ENGINEER.value < UserRole.SUPERVISOR.value
        assert UserRole.SUPERVISOR.value < UserRole.ADMIN.value

    def test_all_roles_have_unique_values(self):
        """Test all roles have unique values.

        WHY: Prevents role confusion.
        """
        values = [r.value for r in UserRole]
        assert len(values) == len(set(values))


class TestPermissionType:
    """Test PermissionType enum."""

    def test_view_permissions_exist(self):
        """Test that view permissions exist.

        WHY: Read operations need permission.
        """
        assert PermissionType.VIEW_DATA.value == "view_data"
        assert PermissionType.VIEW_ALARMS.value == "view_alarms"

    def test_control_permissions_exist(self):
        """Test that control permissions exist.

        WHY: Control operations need permission.
        """
        assert PermissionType.CONTROL_SETPOINT.value == "control_setpoint"
        assert PermissionType.CONTROL_START_STOP.value == "control_start_stop"

    def test_safety_permissions_exist(self):
        """Test that safety permissions exist.

        WHY: Safety-critical operations need special permissions.
        """
        assert PermissionType.SAFETY_BYPASS.value == "safety_bypass"
        assert PermissionType.EMERGENCY_SHUTDOWN.value == "emergency_shutdown"


# ================================================================
# ROLE PERMISSION MAPPING TESTS
# ================================================================
class TestRolePermissions:
    """Test role-permission mappings."""

    def test_viewer_has_view_only(self):
        """Test that viewer role only has view permissions.

        WHY: Viewers should not modify anything.
        """
        viewer_perms = ROLE_PERMISSIONS[UserRole.VIEWER]

        assert PermissionType.VIEW_DATA in viewer_perms
        assert PermissionType.VIEW_ALARMS in viewer_perms
        assert PermissionType.CONTROL_SETPOINT not in viewer_perms
        assert PermissionType.CONFIG_PARAMETER not in viewer_perms

    def test_operator_has_control(self):
        """Test that operator role has control permissions.

        WHY: Operators need to control the process.
        """
        operator_perms = ROLE_PERMISSIONS[UserRole.OPERATOR]

        assert PermissionType.CONTROL_SETPOINT in operator_perms
        assert PermissionType.CONTROL_START_STOP in operator_perms
        assert PermissionType.CONFIG_PARAMETER not in operator_perms

    def test_engineer_has_config(self):
        """Test that engineer role has configuration permissions.

        WHY: Engineers need to configure systems.
        """
        engineer_perms = ROLE_PERMISSIONS[UserRole.ENGINEER]

        assert PermissionType.CONFIG_PARAMETER in engineer_perms
        assert PermissionType.CONFIG_PROGRAM in engineer_perms
        assert PermissionType.SAFETY_BYPASS not in engineer_perms

    def test_supervisor_has_safety(self):
        """Test that supervisor role has safety override permissions.

        WHY: Supervisors can bypass safety in emergencies.
        """
        supervisor_perms = ROLE_PERMISSIONS[UserRole.SUPERVISOR]

        assert PermissionType.SAFETY_BYPASS in supervisor_perms
        assert PermissionType.EMERGENCY_SHUTDOWN in supervisor_perms

    def test_admin_has_all_permissions(self):
        """Test that admin role has all permissions.

        WHY: Admins need full access.
        """
        admin_perms = ROLE_PERMISSIONS[UserRole.ADMIN]

        for perm in PermissionType:
            assert perm in admin_perms


# ================================================================
# USER DATACLASS TESTS
# ================================================================
class TestUser:
    """Test User dataclass."""

    def test_create_user(self):
        """Test creating a user.

        WHY: Core functionality.
        """
        user = User(
            username="operator1",
            role=UserRole.OPERATOR,
            full_name="John Operator",
            email="operator1@example.com",
        )

        assert user.username == "operator1"
        assert user.role == UserRole.OPERATOR
        assert user.active is True

    def test_user_defaults(self):
        """Test user default values.

        WHY: Defaults should be sensible.
        """
        user = User(username="test", role=UserRole.VIEWER)

        assert user.full_name == ""
        assert user.email == ""
        assert user.active is True
        assert user.created_at == 0.0
        assert user.last_login is None


# ================================================================
# AUTH SESSION TESTS
# ================================================================
class TestAuthSession:
    """Test AuthSession dataclass."""

    def test_create_session(self):
        """Test creating a session.

        WHY: Core functionality.
        """
        user = User(username="test", role=UserRole.OPERATOR)
        session = AuthSession(
            session_id="sess_123",
            user=user,
            created_at=100.0,
        )

        assert session.session_id == "sess_123"
        assert session.user.username == "test"

    def test_session_not_expired_when_no_expiry(self):
        """Test that session without expiry doesn't expire.

        WHY: Some sessions are permanent.
        """
        user = User(username="test", role=UserRole.OPERATOR)
        session = AuthSession(
            session_id="sess_123",
            user=user,
            created_at=100.0,
            expires_at=None,
        )

        assert session.is_expired(1000000.0) is False

    def test_session_expired_after_expiry_time(self):
        """Test that session expires after expiry time.

        WHY: Sessions should timeout.
        """
        user = User(username="test", role=UserRole.OPERATOR)
        session = AuthSession(
            session_id="sess_123",
            user=user,
            created_at=100.0,
            expires_at=200.0,
        )

        assert session.is_expired(150.0) is False
        assert session.is_expired(250.0) is True


# ================================================================
# AUTHENTICATION MANAGER TESTS
# ================================================================
class TestAuthenticationManager:
    """Test AuthenticationManager class."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test.

        WHY: Tests need isolated state.
        """
        AuthenticationManager._instance = None
        yield
        AuthenticationManager._instance = None

    def test_singleton_pattern(self):
        """Test that AuthenticationManager is a singleton.

        WHY: One auth manager per simulation.
        """
        mgr1 = AuthenticationManager()
        mgr2 = AuthenticationManager()

        assert mgr1 is mgr2

    def test_default_users_created(self):
        """Test that default users are created on init.

        WHY: Simulation needs pre-configured users.
        """
        mgr = AuthenticationManager()

        assert "operator1" in mgr.users
        assert "engineer1" in mgr.users
        assert "supervisor1" in mgr.users
        assert "admin" in mgr.users
        assert "viewer1" in mgr.users

    @pytest.mark.asyncio
    async def test_create_user(self):
        """Test creating a new user.

        WHY: Need to add users dynamically.
        """
        mgr = AuthenticationManager()

        user = await mgr.create_user(
            username="new_operator",
            role=UserRole.OPERATOR,
            full_name="New Operator",
        )

        assert user.username == "new_operator"
        assert user.role == UserRole.OPERATOR
        assert "new_operator" in mgr.users

    @pytest.mark.asyncio
    async def test_create_duplicate_user_raises(self):
        """Test that creating duplicate user raises error.

        WHY: Usernames must be unique.
        """
        mgr = AuthenticationManager()

        await mgr.create_user("unique_user", UserRole.OPERATOR)

        with pytest.raises(ValueError, match="already exists"):
            await mgr.create_user("unique_user", UserRole.OPERATOR)

    @pytest.mark.asyncio
    async def test_get_user(self):
        """Test getting a user by username.

        WHY: Need to look up users.
        """
        mgr = AuthenticationManager()

        user = await mgr.get_user("operator1")

        assert user is not None
        assert user.username == "operator1"
        assert user.role == UserRole.OPERATOR

    @pytest.mark.asyncio
    async def test_get_nonexistent_user_returns_none(self):
        """Test that getting nonexistent user returns None.

        WHY: Should indicate absence.
        """
        mgr = AuthenticationManager()

        user = await mgr.get_user("nonexistent")

        assert user is None

    @pytest.mark.asyncio
    async def test_update_user_role(self):
        """Test updating a user's role.

        WHY: Roles can change.
        """
        mgr = AuthenticationManager()

        result = await mgr.update_user_role("operator1", UserRole.ENGINEER)

        assert result is True
        user = await mgr.get_user("operator1")
        assert user.role == UserRole.ENGINEER


# ================================================================
# AUTHENTICATION TESTS
# ================================================================
class TestAuthentication:
    """Test authentication functionality."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        AuthenticationManager._instance = None
        yield
        AuthenticationManager._instance = None

    @pytest.mark.asyncio
    async def test_authenticate_valid_user(self):
        """Test authenticating a valid user.

        WHY: Core authentication functionality.
        """
        mgr = AuthenticationManager()

        session_id = await mgr.authenticate("operator1")

        assert session_id is not None
        assert len(session_id) > 0

    @pytest.mark.asyncio
    async def test_authenticate_invalid_user_returns_none(self):
        """Test that authenticating invalid user returns None.

        WHY: Invalid users should be rejected.
        """
        mgr = AuthenticationManager()

        session_id = await mgr.authenticate("nonexistent")

        assert session_id is None

    @pytest.mark.asyncio
    async def test_authenticate_inactive_user_returns_none(self):
        """Test that authenticating inactive user returns None.

        WHY: Disabled accounts should be rejected.
        """
        mgr = AuthenticationManager()
        mgr.users["operator1"].active = False

        session_id = await mgr.authenticate("operator1")

        assert session_id is None

    @pytest.mark.asyncio
    async def test_authenticate_creates_session(self):
        """Test that authenticate creates a session.

        WHY: Sessions track authenticated users.
        """
        mgr = AuthenticationManager()

        session_id = await mgr.authenticate("operator1")
        session = await mgr.get_session(session_id)

        assert session is not None
        assert session.user.username == "operator1"

    @pytest.mark.asyncio
    async def test_logout_invalidates_session(self):
        """Test that logout invalidates the session.

        WHY: Logged out users should lose access.
        """
        mgr = AuthenticationManager()

        session_id = await mgr.authenticate("operator1")
        result = await mgr.logout(session_id)

        assert result is True
        session = await mgr.get_session(session_id)
        assert session is None

    @pytest.mark.asyncio
    async def test_get_expired_session_returns_none(self):
        """Test that getting expired session returns None.

        WHY: Expired sessions should be invalid.
        """
        mgr = AuthenticationManager()

        session_id = await mgr.authenticate("operator1")

        # Directly set session to be expired
        session = mgr.sessions[session_id]
        session.expires_at = mgr.sim_time.now() - 1.0  # Already expired

        session = await mgr.get_session(session_id)
        assert session is None


# ================================================================
# AUTHORISATION TESTS
# ================================================================
class TestAuthorisation:
    """Test authorisation functionality."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        AuthenticationManager._instance = None
        yield
        AuthenticationManager._instance = None

    @pytest.mark.asyncio
    async def test_authorize_allowed_action(self):
        """Test authorising an allowed action.

        WHY: Users with permission should be allowed.
        """
        mgr = AuthenticationManager()
        session_id = await mgr.authenticate("operator1")

        result = await mgr.authorize(
            session_id, PermissionType.CONTROL_SETPOINT, "turbine_1"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_authorize_denied_action(self):
        """Test authorising a denied action.

        WHY: Users without permission should be denied.
        """
        mgr = AuthenticationManager()
        session_id = await mgr.authenticate("viewer1")

        result = await mgr.authorize(
            session_id, PermissionType.CONTROL_SETPOINT, "turbine_1"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_authorize_invalid_session_denied(self):
        """Test that invalid session is denied.

        WHY: Only authenticated users can be authorised.
        """
        mgr = AuthenticationManager()

        result = await mgr.authorize(
            "invalid_session", PermissionType.VIEW_DATA, "turbine_1"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_authorize_with_string_action(self):
        """Test authorising with string action type.

        WHY: Devices may pass action as string.
        """
        mgr = AuthenticationManager()
        session_id = await mgr.authenticate("operator1")

        result = await mgr.authorize(session_id, "control_setpoint", "turbine_1")

        assert result is True

    @pytest.mark.asyncio
    async def test_authorize_with_invalid_string_action(self):
        """Test that invalid string action is denied.

        WHY: Unknown actions should be rejected.
        """
        mgr = AuthenticationManager()
        session_id = await mgr.authenticate("admin")

        result = await mgr.authorize(session_id, "invalid_action", "turbine_1")

        assert result is False


# ================================================================
# DUAL AUTHORISATION TESTS
# ================================================================
class TestDualAuthorisation:
    """Test dual authorisation functionality."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        AuthenticationManager._instance = None
        yield
        AuthenticationManager._instance = None

    @pytest.mark.asyncio
    async def test_dual_auth_both_authorised(self):
        """Test dual auth when both users are authorised.

        WHY: Two-person rule for critical operations.
        """
        mgr = AuthenticationManager()
        session1 = await mgr.authenticate("supervisor1")
        session2 = await mgr.authenticate("admin")

        result = await mgr.authorize_with_dual_auth(
            session1, session2, PermissionType.SAFETY_BYPASS, "reactor_1"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_dual_auth_one_not_authorised(self):
        """Test dual auth when one user lacks permission.

        WHY: Both must have permission.
        """
        mgr = AuthenticationManager()
        session1 = await mgr.authenticate("supervisor1")
        session2 = await mgr.authenticate("operator1")

        result = await mgr.authorize_with_dual_auth(
            session1, session2, PermissionType.SAFETY_BYPASS, "reactor_1"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_dual_auth_same_user_denied(self):
        """Test that same user can't dual-auth themselves.

        WHY: Two different people required.
        """
        mgr = AuthenticationManager()
        session1 = await mgr.authenticate("admin")
        session2 = await mgr.authenticate("admin")

        result = await mgr.authorize_with_dual_auth(
            session1, session2, PermissionType.SAFETY_BYPASS, "reactor_1"
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_dual_auth_invalid_session_denied(self):
        """Test dual auth with invalid session is denied.

        WHY: Both sessions must be valid.
        """
        mgr = AuthenticationManager()
        session1 = await mgr.authenticate("supervisor1")

        result = await mgr.authorize_with_dual_auth(
            session1, "invalid", PermissionType.SAFETY_BYPASS, "reactor_1"
        )

        assert result is False


# ================================================================
# CONVENIENCE FUNCTION TESTS
# ================================================================
class TestConvenienceFunctions:
    """Test convenience functions."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        AuthenticationManager._instance = None
        yield
        AuthenticationManager._instance = None

    @pytest.mark.asyncio
    async def test_quick_auth(self):
        """Test quick_auth function.

        WHY: Convenient for simulation setup.
        """
        session_id = await quick_auth("operator1")

        assert session_id is not None

    @pytest.mark.asyncio
    async def test_verify_authorization_with_session(self):
        """Test verify_authorization with session ID.

        WHY: Devices use this for auth checks.
        """
        session_id = await quick_auth("operator1")

        result = await verify_authorization(
            session_id, PermissionType.CONTROL_SETPOINT, "turbine_1"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_authorization_with_username(self):
        """Test verify_authorization with username (auto-auth).

        WHY: Convenience for simulation.
        """
        result = await verify_authorization(
            "operator1", PermissionType.CONTROL_SETPOINT, "turbine_1"
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_verify_authorization_invalid_returns_false(self):
        """Test verify_authorization with invalid auth returns False.

        WHY: Invalid credentials should be rejected.
        """
        result = await verify_authorization(
            "nonexistent_user", PermissionType.VIEW_DATA, "turbine_1"
        )

        assert result is False


# ================================================================
# THREAD SAFETY TESTS
# ================================================================
class TestAuthThreadSafety:
    """Test thread safety of AuthenticationManager."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        AuthenticationManager._instance = None
        yield
        AuthenticationManager._instance = None

    def test_singleton_thread_safe(self):
        """Test that singleton creation is thread-safe.

        WHY: Multiple threads may access auth manager.
        """
        instances = []
        errors = []

        def get_instance():
            try:
                mgr = AuthenticationManager()
                instances.append(mgr)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=get_instance) for _ in range(10)]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # All instances should be the same object
        assert all(i is instances[0] for i in instances)


# ================================================================
# AUDIT LOG TESTS
# ================================================================
class TestAuditLogging:
    """Test audit logging integration."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton before each test."""
        AuthenticationManager._instance = None
        yield
        AuthenticationManager._instance = None

    @pytest.mark.asyncio
    async def test_authentication_logged(self):
        """Test that authentication is logged.

        WHY: Auth events must be auditable.
        """
        mgr = AuthenticationManager()

        await mgr.authenticate("operator1")

        # Check that logger was used (audit trail in ICSLogger)
        trail = await mgr.logger.get_audit_trail()
        assert len(trail) > 0

    @pytest.mark.asyncio
    async def test_failed_authentication_logged(self):
        """Test that failed authentication is logged.

        WHY: Failed attempts must be tracked.
        """
        mgr = AuthenticationManager()

        await mgr.authenticate("nonexistent")

        # Check that logger was used
        trail = await mgr.logger.get_audit_trail()
        assert len(trail) > 0
