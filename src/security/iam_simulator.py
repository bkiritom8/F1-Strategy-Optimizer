"""
IAM/RBAC simulator for local development.
Simulates Google Cloud IAM roles and permissions.
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set

import bcrypt
from pydantic import BaseModel
from jose import JWTError, jwt

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# JWT configuration
SECRET_KEY = "f1-strategy-optimizer-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


class Role(str, Enum):
    """IAM roles"""

    ADMIN = "roles/admin"
    DATA_ENGINEER = "roles/dataEngineer"
    ML_ENGINEER = "roles/mlEngineer"
    DATA_VIEWER = "roles/dataViewer"
    API_USER = "roles/apiUser"


class Permission(str, Enum):
    """Granular permissions"""

    # Data permissions
    DATA_READ = "data.read"
    DATA_WRITE = "data.write"
    DATA_DELETE = "data.delete"

    # Cloud SQL permissions
    CLOUDSQL_QUERY = "cloudsql.query"
    CLOUDSQL_TABLE_CREATE = "cloudsql.table.create"
    CLOUDSQL_TABLE_UPDATE = "cloudsql.table.update"

    # Pub/Sub permissions
    PUBSUB_PUBLISH = "pubsub.publish"
    PUBSUB_SUBSCRIBE = "pubsub.subscribe"

    # Dataflow permissions
    DATAFLOW_JOB_CREATE = "dataflow.job.create"
    DATAFLOW_JOB_CANCEL = "dataflow.job.cancel"

    # ML permissions
    ML_MODEL_READ = "ml.model.read"
    ML_MODEL_WRITE = "ml.model.write"
    ML_MODEL_DEPLOY = "ml.model.deploy"

    # Admin permissions
    ADMIN_ALL = "admin.*"


# Role to permissions mapping
ROLE_PERMISSIONS: Dict[Role, Set[Permission]] = {
    Role.ADMIN: {Permission.ADMIN_ALL},  # All permissions
    Role.DATA_ENGINEER: {
        Permission.DATA_READ,
        Permission.DATA_WRITE,
        Permission.CLOUDSQL_QUERY,
        Permission.CLOUDSQL_TABLE_CREATE,
        Permission.CLOUDSQL_TABLE_UPDATE,
        Permission.PUBSUB_PUBLISH,
        Permission.PUBSUB_SUBSCRIBE,
        Permission.DATAFLOW_JOB_CREATE,
    },
    Role.ML_ENGINEER: {
        Permission.DATA_READ,
        Permission.CLOUDSQL_QUERY,
        Permission.ML_MODEL_READ,
        Permission.ML_MODEL_WRITE,
        Permission.ML_MODEL_DEPLOY,
    },
    Role.DATA_VIEWER: {
        Permission.DATA_READ,
        Permission.CLOUDSQL_QUERY,
    },
    Role.API_USER: {
        Permission.DATA_READ,
        Permission.ML_MODEL_READ,
    },
}


class User(BaseModel):
    """User model"""

    username: str
    email: str
    full_name: str
    roles: List[Role]
    disabled: bool = False
    created_at: datetime = datetime.utcnow()


class Token(BaseModel):
    """JWT token model"""

    access_token: str
    token_type: str


class TokenData(BaseModel):
    """Token payload data"""

    username: Optional[str] = None
    roles: List[str] = []


class IAMSimulator:
    """Simulate IAM/RBAC for local development"""

    def __init__(self):
        # In-memory user database
        self.users: Dict[str, Dict] = {
            "admin": {
                "username": "admin",
                "email": "admin@f1optimizer.local",
                "full_name": "Admin User",
                "hashed_password": self._hash_password("admin"),
                "roles": [Role.ADMIN],
                "disabled": False,
            },
            "data_engineer": {
                "username": "data_engineer",
                "email": "de@f1optimizer.local",
                "full_name": "Data Engineer",
                "hashed_password": self._hash_password("password"),
                "roles": [Role.DATA_ENGINEER],
                "disabled": False,
            },
            "ml_engineer": {
                "username": "ml_engineer",
                "email": "ml@f1optimizer.local",
                "full_name": "ML Engineer",
                "hashed_password": self._hash_password("password"),
                "roles": [Role.ML_ENGINEER],
                "disabled": False,
            },
            "viewer": {
                "username": "viewer",
                "email": "viewer@f1optimizer.local",
                "full_name": "Data Viewer",
                "hashed_password": self._hash_password("password"),
                "roles": [Role.DATA_VIEWER],
                "disabled": False,
            },
        }

        logger.info("IAM Simulator initialized with sample users")

    def _hash_password(self, password: str) -> str:
        """Hash password"""
        return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode(
            "utf-8"
        )

    def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password"""
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8")
        )

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password"""
        user_data = self.users.get(username)
        if not user_data:
            return None

        if not self._verify_password(password, user_data["hashed_password"]):
            return None

        return User.model_validate(
            {k: v for k, v in user_data.items() if k != "hashed_password"}
        )

    def create_access_token(
        self, data: Dict, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Create JWT access token"""
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

        return encoded_jwt

    def verify_token(self, token: str) -> Optional[TokenData]:
        """Verify and decode JWT token"""
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username: str = payload.get("sub")
            roles: List[str] = payload.get("roles", [])

            if username is None:
                return None

            return TokenData(username=username, roles=roles)

        except JWTError:
            return None

    def get_user_permissions(self, user: User) -> Set[Permission]:
        """Get all permissions for a user based on their roles"""
        permissions = set()

        for role in user.roles:
            role_perms = ROLE_PERMISSIONS.get(role, set())
            permissions.update(role_perms)

        # If user has ADMIN_ALL, grant all permissions
        if Permission.ADMIN_ALL in permissions:
            permissions = set(Permission)

        return permissions

    def check_permission(self, user: User, required_permission: Permission) -> bool:
        """Check if user has required permission"""
        user_permissions = self.get_user_permissions(user)

        # Check for exact match or admin wildcard
        if (
            required_permission in user_permissions
            or Permission.ADMIN_ALL in user_permissions
        ):
            logger.info(
                f"Permission granted: {user.username} has {required_permission.value}"
            )
            return True

        logger.warning(
            f"Permission denied: {user.username} lacks {required_permission.value}"
        )
        return False

    def add_user(
        self,
        username: str,
        email: str,
        full_name: str,
        password: str,
        roles: List[Role],
    ) -> User:
        """Add new user"""
        if username in self.users:
            raise ValueError(f"User {username} already exists")

        user_data = {
            "username": username,
            "email": email,
            "full_name": full_name,
            "hashed_password": self._hash_password(password),
            "roles": roles,
            "disabled": False,
        }

        self.users[username] = user_data

        logger.info(f"User {username} created with roles: {[r.value for r in roles]}")

        return User.model_validate(
            {k: v for k, v in user_data.items() if k != "hashed_password"}
        )

    def grant_role(self, username: str, role: Role) -> bool:
        """Grant role to user"""
        if username not in self.users:
            return False

        if role not in self.users[username]["roles"]:
            self.users[username]["roles"].append(role)
            logger.info(f"Granted role {role.value} to {username}")

        return True

    def revoke_role(self, username: str, role: Role) -> bool:
        """Revoke role from user"""
        if username not in self.users:
            return False

        if role in self.users[username]["roles"]:
            self.users[username]["roles"].remove(role)
            logger.info(f"Revoked role {role.value} from {username}")

        return True


# Global IAM simulator instance
iam_simulator = IAMSimulator()


if __name__ == "__main__":
    # Example usage
    sim = IAMSimulator()

    # Authenticate user
    user = sim.authenticate_user("data_engineer", "password")
    if user:
        print(f"Authenticated: {user.username}")

        # Check permissions
        can_query = sim.check_permission(user, Permission.CLOUDSQL_QUERY)
        print(f"Can query Cloud SQL: {can_query}")

        can_deploy = sim.check_permission(user, Permission.ML_MODEL_DEPLOY)
        print(f"Can deploy models: {can_deploy}")

        # Create token
        token = sim.create_access_token(
            data={"sub": user.username, "roles": [r.value for r in user.roles]}
        )
        print(f"Token: {token[:50]}...")

        # Verify token
        token_data = sim.verify_token(token)
        print(f"Token verified: {token_data}")
