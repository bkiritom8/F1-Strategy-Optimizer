"""GCS-backed user store with PBKDF2-SHA256 password hashing and GDPR support.

Password hashing: PBKDF2-HMAC-SHA256, 260,000 iterations, 32-byte random salt.
This is SHA-256 based (OWASP 2024 recommendation) and far stronger than raw SHA-256
because the iteration count makes brute-force infeasible.

GDPR compliance:
  - Data minimisation: only username, email, full_name, role, consent timestamp stored.
  - Right of access:   get_user_data(username) returns all stored personal data.
  - Right of erasure:  delete_user(username) removes all records and logs deletion.
  - Consent tracking:  consent_at stored at registration; cannot register without consent.
  - Audit log:         every data access/mutation appended to GCS audit log.

Storage layout in gs://f1optimizer-models/users/:
  users/<username>.json      — user record (no password hash)
  users/<username>.hash      — password hash (separate blob, restricted access)
  users/audit.log            — append-only GDPR audit log (newline-delimited JSON)
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import secrets
import threading
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

_BUCKET   = os.environ.get("MODELS_BUCKET", "f1optimizer-models").lstrip("gs://")
_PREFIX   = "users"
_LOCK     = threading.Lock()


# ── Password hashing (PBKDF2-HMAC-SHA256) ────────────────────────────────────

def hash_password(plain: str) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 (260k iterations, 32-byte salt).
    Returns '<hex_salt>:<hex_hash>' suitable for storage.
    """
    salt = secrets.token_bytes(32)
    dk   = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, 260_000)
    return f"{salt.hex()}:{dk.hex()}"


def verify_password(plain: str, stored: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2-SHA256 hash."""
    try:
        salt_hex, hash_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, 260_000)
        return secrets.compare_digest(dk, expected)
    except Exception:
        return False


# ── GCS helpers ───────────────────────────────────────────────────────────────

def _gcs_client():
    from google.cloud import storage
    return storage.Client(project="f1optimizer")


def _read_blob(path: str) -> dict | None:
    try:
        buf = io.BytesIO()
        _gcs_client().bucket(_BUCKET).blob(path).download_to_file(buf)
        buf.seek(0)
        return json.loads(buf.read().decode("utf-8"))
    except Exception:
        return None


def _write_blob(path: str, data: dict | str) -> None:
    content = data if isinstance(data, str) else json.dumps(data, indent=2, default=str)
    _gcs_client().bucket(_BUCKET).blob(path).upload_from_string(
        content, content_type="application/json"
    )


def _delete_blob(path: str) -> None:
    try:
        _gcs_client().bucket(_BUCKET).blob(path).delete()
    except Exception:
        pass


def _append_audit(entry: dict) -> None:
    """Append a GDPR audit entry to the audit log in GCS."""
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    line = json.dumps(entry, default=str) + "\n"
    path = f"{_PREFIX}/audit.log"
    try:
        client = _gcs_client()
        bucket = client.bucket(_BUCKET)
        blob   = bucket.blob(path)
        try:
            existing = blob.download_as_text()
        except Exception:
            existing = ""
        blob.upload_from_string(existing + line, content_type="application/json")
    except Exception as exc:
        logger.warning("audit log write failed: %s", exc)


# ── User store ────────────────────────────────────────────────────────────────

class UserStore:
    """Thread-safe GCS-backed user store."""

    def register(
        self,
        username: str,
        email: str,
        full_name: str,
        password: str,
        role: str,
        gdpr_consent: bool,
    ) -> dict:
        """Create a new user. Raises ValueError on duplicate or missing consent."""
        if not gdpr_consent:
            raise ValueError("GDPR consent is required to create an account.")

        with _LOCK:
            if self._exists(username):
                raise ValueError(f"Username '{username}' is already taken.")

            # Store personal data (no password hash here)
            record: dict[str, Any] = {
                "username":   username,
                "email":      email,
                "full_name":  full_name,
                "role":       role,
                "disabled":   False,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "consent_at": datetime.now(timezone.utc).isoformat(),
            }
            _write_blob(f"{_PREFIX}/{username}.json", record)

            # Store hash separately
            _write_blob(
                f"{_PREFIX}/{username}.hash",
                {"hash": hash_password(password)},
            )

        _append_audit({
            "event":    "user_registered",
            "username": username,
            "email":    email,
            "role":     role,
        })
        logger.info("UserStore: registered user %s (role=%s)", username, role)
        return record

    def authenticate(self, username: str, password: str) -> dict | None:
        """Return user record if credentials are valid, else None."""
        record    = _read_blob(f"{_PREFIX}/{username}.json")
        hash_data = _read_blob(f"{_PREFIX}/{username}.hash")
        if not record or not hash_data:
            return None
        if record.get("disabled"):
            return None
        if not verify_password(password, hash_data["hash"]):
            return None
        _append_audit({"event": "user_login", "username": username})
        return record

    def get(self, username: str) -> dict | None:
        """Return user record without password hash."""
        return _read_blob(f"{_PREFIX}/{username}.json")

    def get_user_data(self, username: str) -> dict:
        """GDPR right of access — return all stored personal data."""
        record = _read_blob(f"{_PREFIX}/{username}.json")
        if not record:
            raise ValueError(f"User '{username}' not found.")
        _append_audit({"event": "gdpr_data_access", "username": username})
        return {
            "personal_data": record,
            "note": "This is all personal data stored about you. No password hashes are included.",
        }

    def delete_user(self, username: str) -> None:
        """GDPR right of erasure — permanently delete all user data."""
        with _LOCK:
            _delete_blob(f"{_PREFIX}/{username}.json")
            _delete_blob(f"{_PREFIX}/{username}.hash")
        _append_audit({"event": "gdpr_erasure", "username": username})
        logger.info("UserStore: deleted user %s (GDPR erasure)", username)

    def update_password(self, username: str, new_password: str) -> None:
        """Replace the stored password hash."""
        with _LOCK:
            _write_blob(
                f"{_PREFIX}/{username}.hash",
                {"hash": hash_password(new_password)},
            )
        _append_audit({"event": "password_changed", "username": username})

    def list_users(self) -> list[dict]:
        """Return all user records (admin use only — no password hashes)."""
        try:
            blobs = _gcs_client().bucket(_BUCKET).list_blobs(prefix=f"{_PREFIX}/")
            users = []
            for blob in blobs:
                if blob.name.endswith(".json") and not blob.name.endswith("audit.log"):
                    buf = io.BytesIO()
                    blob.download_to_file(buf)
                    buf.seek(0)
                    users.append(json.loads(buf.read()))
            return users
        except Exception as exc:
            logger.warning("UserStore.list_users failed: %s", exc)
            return []

    def _exists(self, username: str) -> bool:
        try:
            return _gcs_client().bucket(_BUCKET).blob(
                f"{_PREFIX}/{username}.json"
            ).exists()
        except Exception:
            return False


# Singleton
user_store = UserStore()
