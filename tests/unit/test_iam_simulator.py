"""
Unit tests for IAM/RBAC simulator
"""

import pytest
from datetime import timedelta

import sys

sys.path.insert(0, "/home/user/test")

from src.common.security.iam_simulator import IAMSimulator, Role, Permission, User


class TestIAMSimulator:
    """Test IAM simulator functionality"""

    @pytest.fixture
    def iam(self):
        """Create IAM simulator instance"""
        return IAMSimulator()

    def test_authenticate_valid_user(self, iam):
        """Test authentication with valid credentials"""
        user = iam.authenticate_user("admin", "admin")

        assert user is not None
        assert user.username == "admin"
        assert Role.ADMIN in user.roles

    def test_authenticate_invalid_password(self, iam):
        """Test authentication with invalid password"""
        user = iam.authenticate_user("admin", "wrong_password")

        assert user is None

    def test_authenticate_nonexistent_user(self, iam):
        """Test authentication with nonexistent user"""
        user = iam.authenticate_user("nonexistent", "password")

        assert user is None

    def test_create_access_token(self, iam):
        """Test JWT token creation"""
        token = iam.create_access_token(
            data={"sub": "test_user", "roles": [Role.DATA_VIEWER.value]}
        )

        assert isinstance(token, str)
        assert len(token) > 0

    def test_verify_valid_token(self, iam):
        """Test token verification"""
        token = iam.create_access_token(
            data={"sub": "test_user", "roles": [Role.DATA_VIEWER.value]}
        )

        token_data = iam.verify_token(token)

        assert token_data is not None
        assert token_data.username == "test_user"
        assert Role.DATA_VIEWER.value in token_data.roles

    def test_verify_expired_token(self, iam):
        """Test verification of expired token"""
        token = iam.create_access_token(
            data={"sub": "test_user", "roles": []},
            expires_delta=timedelta(seconds=-1),  # Already expired
        )

        token_data = iam.verify_token(token)

        # Expired token should fail verification
        assert token_data is None

    def test_verify_invalid_token(self, iam):
        """Test verification of invalid token"""
        token_data = iam.verify_token("invalid_token")

        assert token_data is None

    def test_get_user_permissions_admin(self, iam):
        """Test admin permissions"""
        user = User(
            username="admin",
            email="admin@test.com",
            full_name="Admin User",
            roles=[Role.ADMIN],
        )

        permissions = iam.get_user_permissions(user)

        # Admin should have all permissions
        assert Permission.ADMIN_ALL in permissions

    def test_get_user_permissions_data_engineer(self, iam):
        """Test data engineer permissions"""
        user = User(
            username="de",
            email="de@test.com",
            full_name="Data Engineer",
            roles=[Role.DATA_ENGINEER],
        )

        permissions = iam.get_user_permissions(user)

        assert Permission.DATA_READ in permissions
        assert Permission.DATA_WRITE in permissions
        assert Permission.CLOUDSQL_QUERY in permissions
        assert Permission.ML_MODEL_DEPLOY not in permissions  # Should not have this

    def test_check_permission_granted(self, iam):
        """Test permission check - granted"""
        user = User(
            username="de",
            email="de@test.com",
            full_name="Data Engineer",
            roles=[Role.DATA_ENGINEER],
        )

        has_permission = iam.check_permission(user, Permission.CLOUDSQL_QUERY)

        assert has_permission is True

    def test_check_permission_denied(self, iam):
        """Test permission check - denied"""
        user = User(
            username="viewer",
            email="viewer@test.com",
            full_name="Viewer",
            roles=[Role.DATA_VIEWER],
        )

        has_permission = iam.check_permission(user, Permission.DATA_WRITE)

        assert has_permission is False

    def test_add_user(self, iam):
        """Test adding new user"""
        user = iam.add_user(
            username="new_user",
            email="new@test.com",
            full_name="New User",
            password="password123",
            roles=[Role.API_USER],
        )

        assert user.username == "new_user"
        assert Role.API_USER in user.roles

        # Should be able to authenticate
        auth_user = iam.authenticate_user("new_user", "password123")
        assert auth_user is not None

    def test_add_duplicate_user(self, iam):
        """Test adding duplicate user raises error"""
        with pytest.raises(ValueError):
            iam.add_user(
                username="admin",  # Already exists
                email="admin2@test.com",
                full_name="Admin 2",
                password="password",
                roles=[Role.ADMIN],
            )

    def test_grant_role(self, iam):
        """Test granting role to user"""
        # Add user with minimal permissions
        iam.add_user(
            username="test_user",
            email="test@test.com",
            full_name="Test User",
            password="password",
            roles=[Role.DATA_VIEWER],
        )

        # Grant additional role
        success = iam.grant_role("test_user", Role.DATA_ENGINEER)

        assert success is True
        assert Role.DATA_ENGINEER in iam.users["test_user"]["roles"]

    def test_revoke_role(self, iam):
        """Test revoking role from user"""
        success = iam.revoke_role("data_engineer", Role.DATA_ENGINEER)

        assert success is True
        assert Role.DATA_ENGINEER not in iam.users["data_engineer"]["roles"]

    def test_multiple_roles(self, iam):
        """Test user with multiple roles"""
        user = User(
            username="multi",
            email="multi@test.com",
            full_name="Multi Role User",
            roles=[Role.DATA_ENGINEER, Role.ML_ENGINEER],
        )

        permissions = iam.get_user_permissions(user)

        # Should have permissions from both roles
        assert Permission.CLOUDSQL_QUERY in permissions
        assert Permission.ML_MODEL_WRITE in permissions


class TestRolePermissions:
    """Test role-permission mappings"""

    def test_admin_has_all_permissions(self):
        """Test admin role has wildcard permission"""
        from src.common.security.iam_simulator import ROLE_PERMISSIONS

        admin_perms = ROLE_PERMISSIONS[Role.ADMIN]

        assert Permission.ADMIN_ALL in admin_perms

    def test_data_viewer_read_only(self):
        """Test data viewer has only read permissions"""
        from src.common.security.iam_simulator import ROLE_PERMISSIONS

        viewer_perms = ROLE_PERMISSIONS[Role.DATA_VIEWER]

        assert Permission.DATA_READ in viewer_perms
        assert Permission.DATA_WRITE not in viewer_perms
        assert Permission.DATA_DELETE not in viewer_perms

    def test_ml_engineer_permissions(self):
        """Test ML engineer has model permissions"""
        from src.common.security.iam_simulator import ROLE_PERMISSIONS

        ml_perms = ROLE_PERMISSIONS[Role.ML_ENGINEER]

        assert Permission.ML_MODEL_READ in ml_perms
        assert Permission.ML_MODEL_WRITE in ml_perms
        assert Permission.ML_MODEL_DEPLOY in ml_perms


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
