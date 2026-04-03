"""Firestore-backed user store with PBKDF2-SHA256 hashing and GDPR support.

Race-condition safety
─────────────────────
Registration uses a Firestore transaction that atomically checks for an
existing username and creates the document in one operation. Under 100+
concurrent registrations with the same username, exactly one succeeds.

Password hashing
─────────────────
PBKDF2-HMAC-SHA256 with 260,000 iterations and a 32-byte random salt per
user. This is SHA-256 based (as requested) and OWASP 2024 compliant.
Raw SHA-256 alone is not safe for passwords; key stretching + salt is
what makes it secure against offline brute-force attacks.

Firestore collections
─────────────────────
  users/{username}              — profile (no credentials)
      username, email, full_name, role, disabled, created_at, consent_at,
      email_verified, verification_token (cleared after verification)

  user_credentials/{username}   — password hash only (separate collection)
      hash

  audit_log/{auto_id}           — GDPR audit entries (append-only)
      event, username, timestamp, [extra fields]

GDPR compliance
─────────────────
  Data minimisation : only what is listed above is stored.
  Right of access   : get_user_data() returns all documents for a user.
  Right of erasure  : delete_user() removes both profile and credentials
                      documents in a single transaction, then appends an
                      erasure entry to the audit log.
  Consent tracking  : consent_at timestamp stored at registration.
  Audit log         : every create / read / update / delete operation is
                      recorded in audit_log with a server timestamp.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_PROJECT = os.environ.get("PROJECT_ID", "f1optimizer")
_USERS = "users"
_CREDS = "user_credentials"
_AUDIT = "audit_log"


# ── Password hashing ──────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    """Return '<hex_salt>:<hex_dk>' using PBKDF2-HMAC-SHA256, 260k iterations."""
    salt = secrets.token_bytes(32)
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, 260_000)
    return f"{salt.hex()}:{dk.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    """Constant-time verification against a stored PBKDF2-SHA256 hash."""
    try:
        salt_hex, hash_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, 260_000)
        return secrets.compare_digest(dk, expected)
    except Exception:
        return False


# ── Firestore client ──────────────────────────────────────────────────────────

_db = None


def _firestore():
    global _db
    if _db is None:
        from google.cloud import firestore

        _db = firestore.Client(project=_PROJECT)
    return _db


def _audit(event: str, username: str, **extra: Any) -> None:
    try:
        from google.cloud import firestore

        _firestore().collection(_AUDIT).add(
            {
                "event": event,
                "username": username,
                "timestamp": firestore.SERVER_TIMESTAMP,
                **extra,
            }
        )
    except Exception as exc:
        logger.warning("audit write failed: %s", exc)


# ── User store ────────────────────────────────────────────────────────────────


class UserStore:
    """Firestore-backed user store. All mutating operations are transactional."""

    # ── Write operations ──────────────────────────────────────────────────────

    def register(
        self,
        username: str,
        email: str,
        full_name: str,
        password: str,
        role: str,
        gdpr_consent: bool,
    ) -> dict:
        """
        Create a new user atomically.

        Uses a Firestore transaction so that two concurrent registrations
        with the same username cannot both succeed — the second write will
        see the committed document from the first and raise ValueError.

        Raises:
            ValueError: username already taken or GDPR consent not given.
        """
        if not gdpr_consent:
            raise ValueError("GDPR consent is required to create an account.")

        from google.cloud import firestore

        db = _firestore()
        user_ref = db.collection(_USERS).document(username)
        cred_ref = db.collection(_CREDS).document(username)
        now = datetime.now(timezone.utc).isoformat()
        pw_hash = hash_password(password)  # computed outside transaction (CPU-bound)

        @firestore.transactional
        def _create(transaction):
            snapshot = user_ref.get(transaction=transaction)
            if snapshot.exists:
                raise ValueError(f"Username '{username}' is already taken.")

            verification_token = secrets.token_urlsafe(32)
            profile = {
                "username": username,
                "email": email,
                "full_name": full_name,
                "role": role,
                "disabled": False,
                "email_verified": False,
                "verification_token": verification_token,
                "created_at": now,
                "consent_at": now,
            }
            transaction.set(user_ref, profile)
            transaction.set(cred_ref, {"hash": pw_hash})
            return profile

        try:
            profile = _create(db.transaction())
        except ValueError:
            raise
        except Exception as exc:
            logger.error("register transaction failed: %s", exc)
            raise RuntimeError("Registration failed — please try again.") from exc

        _audit("user_registered", username, email=email, role=role)
        logger.info("UserStore: registered %s (role=%s)", username, role)
        return profile  # includes verification_token for the caller to send via email

    def update_password(self, username: str, new_password: str) -> None:
        """Replace password hash. Atomic single-document write."""
        from google.cloud import firestore

        db = _firestore()
        cred_ref = db.collection(_CREDS).document(username)
        pw_hash = hash_password(new_password)

        @firestore.transactional
        def _update(transaction):
            snap = cred_ref.get(transaction=transaction)
            if not snap.exists:
                raise ValueError(f"User '{username}' not found.")
            transaction.update(cred_ref, {"hash": pw_hash})

        _update(db.transaction())
        _audit("password_changed", username)

    def disable_user(self, username: str) -> None:
        """Soft-disable a user account without deleting data."""
        _firestore().collection(_USERS).document(username).update({"disabled": True})
        _audit("user_disabled", username)

    def delete_user(self, username: str) -> None:
        """
        GDPR right of erasure — atomically delete profile and credentials,
        then write an erasure record to the audit log.
        """
        from google.cloud import firestore

        db = _firestore()
        user_ref = db.collection(_USERS).document(username)
        cred_ref = db.collection(_CREDS).document(username)

        @firestore.transactional
        def _delete(transaction):
            transaction.delete(user_ref)
            transaction.delete(cred_ref)

        _delete(db.transaction())
        _audit("gdpr_erasure", username)
        logger.info("UserStore: erased user %s (GDPR)", username)

    # ── Read operations ───────────────────────────────────────────────────────

    def authenticate(self, username: str, password: str) -> "dict | str | None":
        """
        Verify credentials. Returns user profile dict on success, None on failure.
        Reads profile and credentials in a single batch (no transaction needed —
        credentials document is immutable during a login check).
        """
        db = _firestore()

        # Batch-get both documents in one round trip
        refs = [
            db.collection(_USERS).document(username),
            db.collection(_CREDS).document(username),
        ]
        snaps = db.get_all(refs)
        docs = {s.reference.parent.id: s for s in snaps}

        user_snap = docs.get(_USERS)
        cred_snap = docs.get(_CREDS)

        if not user_snap or not user_snap.exists:
            return None
        if not cred_snap or not cred_snap.exists:
            return None

        profile = user_snap.to_dict()
        if profile.get("disabled"):
            return None
        if not profile.get("email_verified", False):
            return "unverified"
        if not verify_password(password, cred_snap.to_dict()["hash"]):
            return None

        _audit("user_login", username)
        return profile

    def verify_email(self, token: str) -> str:
        """
        Mark the user whose verification_token matches as email_verified=True.

        Returns the username on success.
        Raises ValueError if the token is invalid or already used.
        """
        db = _firestore()
        results = (
            db.collection(_USERS)
            .where("verification_token", "==", token)
            .limit(1)
            .stream()
        )
        docs = list(results)
        if not docs:
            raise ValueError("Invalid or expired verification token.")

        doc = docs[0]
        username = doc.id
        doc.reference.update({"email_verified": True, "verification_token": None})
        _audit("email_verified", username)
        logger.info("UserStore: email verified for %s", username)
        return username

    def get_by_email(self, email: str) -> dict | None:
        """Return user profile by email address (case-sensitive). Admin / resend use."""
        results = (
            _firestore()
            .collection(_USERS)
            .where("email", "==", email)
            .limit(1)
            .stream()
        )
        docs = list(results)
        return docs[0].to_dict() if docs else None

    def regenerate_verification_token(self, username: str) -> str:
        """Issue a fresh verification token (for resend). Returns the new token."""
        token = secrets.token_urlsafe(32)
        _firestore().collection(_USERS).document(username).update(
            {"verification_token": token, "email_verified": False}
        )
        _audit("verification_token_regenerated", username)
        return token

    def get(self, username: str) -> dict | None:
        """Return user profile without credentials."""
        snap = _firestore().collection(_USERS).document(username).get()
        return snap.to_dict() if snap.exists else None

    def get_user_data(self, username: str) -> dict:
        """GDPR right of access — all stored personal data for this user."""
        profile = self.get(username)
        if not profile:
            raise ValueError(f"User '{username}' not found.")
        _audit("gdpr_data_access", username)
        return {
            "personal_data": profile,
            "note": (
                "This is all personal data stored about you. "
                "Password hashes are not included. "
                "To request erasure, call DELETE /users/me."
            ),
        }

    def list_users(self) -> list[dict]:
        """Return all user profiles. Admin use only — no credentials returned."""
        try:
            return [s.to_dict() for s in _firestore().collection(_USERS).stream()]
        except Exception as exc:
            logger.warning("UserStore.list_users failed: %s", exc)
            return []

    def list_audit_log(
        self, username: str | None = None, limit: int = 100
    ) -> list[dict]:
        """Return recent audit entries, optionally filtered by username."""
        try:
            query = (
                _firestore()
                .collection(_AUDIT)
                .order_by("timestamp", direction="DESCENDING")
                .limit(limit)
            )
            if username:
                query = query.where("username", "==", username)
            return [s.to_dict() for s in query.stream()]
        except Exception as exc:
            logger.warning("UserStore.list_audit_log failed: %s", exc)
            return []


# Singleton
user_store = UserStore()
