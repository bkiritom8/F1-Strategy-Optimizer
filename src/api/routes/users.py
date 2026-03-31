"""User management routes.

Public:
  POST /users/register          — create account (SHA-256 / PBKDF2, GDPR consent required)
  POST /users/login             — authenticate, returns JWT
  GET  /users/me                — current user profile
  GET  /users/me/data           — GDPR: export all personal data
  DELETE /users/me              — GDPR: erase account and all personal data
  PUT  /users/me/password       — change password

Admin only (requires Role.ADMIN):
  GET  /admin/users             — list all registered users
  GET  /admin/dashboard         — system metrics, model status, training job status
  DELETE /admin/users/{username} — delete any user account
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field

from src.security.https_middleware import get_current_user
from src.security.iam_simulator import (
    IAMSimulator,
    Permission,
    Role,
    Token,
    User,
    iam_simulator,
)
from src.security.user_store import user_store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["users"])

# Valid roles a self-registered user can request
_ALLOWED_SELF_REGISTER_ROLES = {Role.API_USER, Role.DATA_VIEWER}


# ── Request / response models ─────────────────────────────────────────────────


class RegisterRequest(BaseModel):
    username: str = Field(
        ..., min_length=3, max_length=40, pattern=r"^[a-zA-Z0-9_\-]+$"
    )
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="roles/apiUser")
    gdpr_consent: bool = Field(..., description="Must be true to create an account")


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class UserProfile(BaseModel):
    username: str
    email: str
    full_name: str
    role: str
    created_at: str
    consent_at: str
    is_admin: bool


class AdminUserView(BaseModel):
    username: str
    email: str
    full_name: str
    role: str
    disabled: bool
    created_at: str


class AdminDashboard(BaseModel):
    total_users: int
    models_available: list[str]
    api_version: str
    gcp_project: str
    region: str
    model_metrics: dict[str, Any]
    training_bucket: str


# ── Helpers ───────────────────────────────────────────────────────────────────


def _require_admin(current_user: User) -> None:
    if not iam_simulator.check_permission(current_user, Permission.ADMIN_ALL):
        raise HTTPException(status_code=403, detail="Admin access required")


def _role_from_str(role_str: str) -> Role:
    try:
        return Role(role_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role '{role_str}'. Allowed: {[r.value for r in _ALLOWED_SELF_REGISTER_ROLES]}",
        )


def _to_profile(record: dict, is_admin: bool) -> UserProfile:
    return UserProfile(
        username=record["username"],
        email=record["email"],
        full_name=record["full_name"],
        role=record.get("role", Role.API_USER.value),
        created_at=str(record.get("created_at", "")),
        consent_at=str(record.get("consent_at", "")),
        is_admin=is_admin,
    )


# ── Public endpoints ──────────────────────────────────────────────────────────


@router.post("/users/register", status_code=201, response_model=UserProfile)
async def register(request: RegisterRequest) -> UserProfile:
    """
    Create a new user account.

    - Password is hashed with PBKDF2-HMAC-SHA256 (260k iterations, random salt).
    - `gdpr_consent` must be `true` — by checking this box the user acknowledges
      that their username, email, and full name will be stored on GCP infrastructure
      in the EU/US region, and that they may request erasure at any time via
      DELETE /users/me.
    - Self-registration is limited to roles: `roles/apiUser`, `roles/dataViewer`.
    """
    role = _role_from_str(request.role)
    if role not in _ALLOWED_SELF_REGISTER_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Self-registration only allows: {[r.value for r in _ALLOWED_SELF_REGISTER_ROLES]}",
        )

    try:
        record = user_store.register(
            username=request.username,
            email=str(request.email),
            full_name=request.full_name,
            password=request.password,
            role=role.value,
            gdpr_consent=request.gdpr_consent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    return _to_profile(record, is_admin=False)


@router.post("/users/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    """
    Authenticate with username + password. Returns a JWT bearer token.
    Falls back to built-in admin/service accounts if not found in user store.
    """
    # Check user store first
    record = user_store.authenticate(form_data.username, form_data.password)
    if record:
        role = _role_from_str(record.get("role", Role.API_USER.value))
        access_token = iam_simulator.create_access_token(
            data={"sub": record["username"], "roles": [role.value]},
            expires_delta=timedelta(minutes=60),
        )
        return Token(access_token=access_token, token_type="bearer")

    # Fall back to built-in service accounts (admin, ml_engineer, etc.)
    user = iam_simulator.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = iam_simulator.create_access_token(
        data={"sub": user.username, "roles": [r.value for r in user.roles]},
        expires_delta=timedelta(minutes=60),
    )
    return Token(access_token=access_token, token_type="bearer")


@router.get("/users/me", response_model=UserProfile)
async def get_me(current_user: User = Depends(get_current_user)) -> UserProfile:
    """Return current user profile including is_admin flag."""
    is_admin = iam_simulator.check_permission(current_user, Permission.ADMIN_ALL)

    # Try user store first, fall back to IAM simulator built-ins
    record = user_store.get(current_user.username)
    if record:
        return _to_profile(record, is_admin)

    # Built-in service account
    return UserProfile(
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.roles[0].value if current_user.roles else Role.API_USER.value,
        created_at=str(current_user.created_at),
        consent_at=str(current_user.created_at),
        is_admin=is_admin,
    )


@router.get("/users/me/data")
async def gdpr_export(current_user: User = Depends(get_current_user)) -> dict:
    """
    GDPR right of access — returns all personal data stored about you.
    Built-in service accounts return their in-memory profile only.
    """
    record = user_store.get(current_user.username)
    if record:
        return user_store.get_user_data(current_user.username)

    # Built-in account — return what's held in memory
    return {
        "personal_data": {
            "username": current_user.username,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "roles": [r.value for r in current_user.roles],
            "note": "Built-in service account — no persistent personal data stored.",
        }
    }


@router.delete("/users/me", status_code=204, response_class=Response)
async def gdpr_erase(current_user: User = Depends(get_current_user)) -> Response:
    """
    GDPR right of erasure — permanently deletes your account and all stored
    personal data (username, email, full name, consent record).
    Your JWT will continue to work until it expires naturally.
    Built-in service accounts cannot be erased via this endpoint.
    """
    record = user_store.get(current_user.username)
    if not record:
        raise HTTPException(
            status_code=400,
            detail="Built-in service accounts cannot be erased via this endpoint.",
        )
    user_store.delete_user(current_user.username)
    return Response(status_code=204)


@router.put("/users/me/password", status_code=204, response_class=Response)
async def change_password(
    request: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Change your password. Requires your current password for verification."""
    record = user_store.get(current_user.username)
    if not record:
        raise HTTPException(
            status_code=400, detail="Cannot change password for built-in accounts."
        )

    if not user_store.authenticate(current_user.username, request.current_password):
        raise HTTPException(status_code=403, detail="Current password is incorrect.")

    user_store.update_password(current_user.username, request.new_password)
    return Response(status_code=204)


# ── Admin endpoints ───────────────────────────────────────────────────────────


@router.get("/admin/users", response_model=list[AdminUserView])
async def admin_list_users(
    current_user: User = Depends(get_current_user),
) -> list[AdminUserView]:
    """Admin only — list all registered users."""
    _require_admin(current_user)
    records = user_store.list_users()
    return [
        AdminUserView(
            username=r["username"],
            email=r["email"],
            full_name=r["full_name"],
            role=r.get("role", Role.API_USER.value),
            disabled=r.get("disabled", False),
            created_at=str(r.get("created_at", "")),
        )
        for r in records
    ]


@router.delete("/admin/users/{username}", status_code=204, response_class=Response)
async def admin_delete_user(
    username: str,
    current_user: User = Depends(get_current_user),
) -> Response:
    """Admin only — delete any user account."""
    _require_admin(current_user)
    record = user_store.get(username)
    if not record:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")
    user_store.delete_user(username)
    logger.info("Admin %s deleted user %s", current_user.username, username)
    return Response(status_code=204)


@router.get("/admin/dashboard", response_model=AdminDashboard)
async def admin_dashboard(
    current_user: User = Depends(get_current_user),
) -> AdminDashboard:
    """
    Admin only — system-level view unavailable to regular users:
      - Total registered users
      - Available model artifacts in GCS
      - Model performance metrics from model cards
      - GCP project / region / bucket info
    """
    _require_admin(current_user)

    project = os.environ.get("PROJECT_ID", "f1optimizer")
    region = os.environ.get("REGION", "us-central1")

    # Count registered users
    total_users = len(user_store.list_users())

    # Check which model artifacts exist in GCS
    model_names = [
        "tire_degradation",
        "driving_style",
        "safety_car",
        "pit_window",
        "overtake_prob",
        "race_outcome",
    ]
    available_models: list[str] = []
    model_metrics: dict[str, Any] = {}

    try:
        from google.cloud import storage

        bucket = storage.Client(project=project).bucket("f1optimizer-models")

        for name in model_names:
            blob = bucket.blob(f"{name}/model.pkl")
            if blob.exists():
                available_models.append(name)

            # Load model card metrics if available
            card_blob = bucket.blob(f"{name}/model_card.json")
            if card_blob.exists():
                import json, io

                buf = io.BytesIO()
                card_blob.download_to_file(buf)
                buf.seek(0)
                card = json.loads(buf.read())
                model_metrics[name] = card.get("train_metrics", {})
    except Exception as exc:
        logger.warning("admin_dashboard: GCS check failed — %s", exc)

    return AdminDashboard(
        total_users=total_users,
        models_available=available_models,
        api_version="1.0.0",
        gcp_project=project,
        region=region,
        model_metrics=model_metrics,
        training_bucket="gs://f1optimizer-training",
    )
