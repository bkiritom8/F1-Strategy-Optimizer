"""
progress.py — GCS-backed progress tracker with optimistic locking.

Uses GCS generation-match conditions for atomic reads + writes so multiple
Cloud Run tasks can safely share a single progress.json without race conditions.
"""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Optional

from google.api_core import exceptions as gcp_exc
from google.cloud import storage

log = logging.getLogger(__name__)

PROGRESS_BLOB = "status/progress.json"
_LOCK_RETRY_BASE = 0.2   # seconds — jittered backoff on write conflicts


class Progress:
    """
    Thread/process-safe progress tracker stored in GCS.

    Every mutation reads the blob (capturing its generation number), modifies
    the dict locally, then writes back with if_generation_match.  On a 412
    Precondition Failed (concurrent writer), it retries from scratch.
    """

    def __init__(self, bucket: storage.Bucket) -> None:
        self._bucket = bucket
        self._blob = bucket.blob(PROGRESS_BLOB)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_done(self, key: str) -> bool:
        """Return True if *key* is already marked done in GCS."""
        data, _ = self._read()
        return data.get(key) == "done"

    def mark_done(self, key: str) -> None:
        """Mark *key* as done, retrying indefinitely on write conflicts."""
        attempt = 0
        while True:
            data, generation = self._read()
            if data.get(key) == "done":
                return  # already done, idempotent
            data[key] = "done"
            if self._write(data, generation):
                log.info("progress: marked done — %s", key)
                return
            wait = _LOCK_RETRY_BASE * (2 ** min(attempt, 6)) + random.uniform(0, 0.5)
            log.debug("progress: write conflict on %s, retry in %.2fs", key, wait)
            time.sleep(wait)
            attempt += 1

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _read(self) -> tuple[dict, int]:
        """Download progress.json and return (data_dict, generation)."""
        try:
            self._blob.reload()
            generation = self._blob.generation
            data = json.loads(self._blob.download_as_text())
            return data, generation
        except gcp_exc.NotFound:
            return {}, 0

    def _write(self, data: dict, generation: int) -> bool:
        """
        Write data back with if_generation_match=generation.
        Returns True on success, False on 412 (conflict).
        """
        try:
            self._blob.upload_from_string(
                json.dumps(data, indent=2),
                content_type="application/json",
                if_generation_match=generation,
            )
            return True
        except gcp_exc.PreconditionFailed:
            return False
