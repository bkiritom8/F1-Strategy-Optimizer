"""
ConstructorPaceStore — loads constructor_pace.json and resolves
constructor_id + season → car offset in milliseconds.

Source resolution order:
  1. Explicit `source` argument
  2. CONSTRUCTOR_PACE_PATH env var
  3. frontend/public/data/constructor_pace.json (local dev fallback)
  4. Empty store (returns 0.0 for all queries)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_LOCAL = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "frontend",
    "public",
    "data",
    "constructor_pace.json",
)


class ConstructorPaceStore:
    """
    Thread-safe read-only store for constructor car pace deltas.

    Loaded once at construction time from a JSON file.
    All methods return safe defaults on missing data.
    """

    def __init__(self, source: str | None = None) -> None:
        resolved = self._resolve_source(source)
        self._data: dict[str, Any] = self._load(resolved)

    # ── Source resolution ─────────────────────────────────────────────────────

    @staticmethod
    def _resolve_source(source: str | None) -> str | None:
        if source is not None:
            return source
        env = os.environ.get("CONSTRUCTOR_PACE_PATH")
        if env:
            return env
        local = os.path.normpath(_DEFAULT_LOCAL)
        if os.path.isfile(local):
            return local
        return None

    # ── Loading ───────────────────────────────────────────────────────────────

    @staticmethod
    def _load(source: str | None) -> dict[str, Any]:
        if source is None:
            logger.info("ConstructorPaceStore: no source — empty store")
            return {}

        try:
            if source.startswith("gs://"):
                return ConstructorPaceStore._load_gcs(source)
            with open(source, "r") as f:
                raw = json.load(f)
            logger.info("ConstructorPaceStore: loaded from %s", source)
            return raw.get("constructors", {})
        except FileNotFoundError:
            logger.info("ConstructorPaceStore: %s not found — empty store", source)
            return {}
        except Exception as exc:  # noqa: BLE001
            logger.warning("ConstructorPaceStore: load error (%s) — empty store", exc)
            return {}

    @staticmethod
    def _load_gcs(uri: str) -> dict[str, Any]:
        from google.cloud import storage  # lazy import

        # gs://bucket/path
        path = uri[5:]
        bucket_name, _, blob_name = path.partition("/")
        client = storage.Client()
        blob = client.bucket(bucket_name).blob(blob_name)
        raw = json.loads(blob.download_as_text())
        logger.info("ConstructorPaceStore: loaded from %s", uri)
        return raw.get("constructors", {})

    # ── Public API ────────────────────────────────────────────────────────────

    def get_offset_ms(self, constructor_id: str, season: int) -> float:
        """
        Return car pace delta in milliseconds vs field median.
        Negative = faster than average. Returns 0.0 if unknown.
        """
        entry = (
            self._data.get(constructor_id, {})
            .get("seasons", {})
            .get(str(season))
        )
        if entry is None:
            return 0.0
        delta_s = entry.get("pace_delta_s")
        if delta_s is None:
            return 0.0
        return float(delta_s) * 1000.0

    def is_limited_data(self, constructor_id: str, season: int) -> bool:
        """Return True if this constructor-season is flagged as limited_data."""
        entry = (
            self._data.get(constructor_id, {})
            .get("seasons", {})
            .get(str(season))
        )
        if entry is None:
            return False
        return bool(entry.get("limited_data", False))

    def __len__(self) -> int:
        return len(self._data)
