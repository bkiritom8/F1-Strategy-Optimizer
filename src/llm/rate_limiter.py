"""Per-user token-bucket rate limiter for the LLM endpoint.

Each authenticated user (identified by JWT sub claim) gets an independent
token bucket. Buckets are lazy-created and evicted after 5 minutes of
inactivity to keep memory bounded.

Default policy: 10 LLM requests per 60-second sliding window per user.
Adjust via LLM_RATE_LIMIT_RPM env var.
"""

from __future__ import annotations

import asyncio
import os
import time
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_RPM = int(os.environ.get("LLM_RATE_LIMIT_RPM", "10"))
_EVICT_AFTER_S = 300.0  # evict idle bucket after 5 minutes


@dataclass
class _Bucket:
    tokens: float
    last_refill: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)

    def refill(self, capacity: int, refill_rate: float) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(capacity, self.tokens + elapsed * refill_rate)
        self.last_refill = now

    def consume(self) -> bool:
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            self.last_used = time.monotonic()
            return True
        return False


class UserRateLimiter:
    """Token-bucket rate limiter keyed on user identity.

    Concurrency-safe via a per-instance asyncio.Lock (one lock for the whole
    dict, not per-user, which keeps the overhead minimal for typical user counts).
    """

    def __init__(self, rpm: int = _RPM) -> None:
        self._rpm = rpm
        self._refill_rate = rpm / 60.0  # tokens per second
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def is_allowed(self, user_id: str) -> bool:
        """Return True and consume a token if the user is within their limit."""
        async with self._lock:
            self._evict_stale()
            bucket = self._buckets.get(user_id)
            if bucket is None:
                # New user: start full so they're not penalised on first request
                bucket = _Bucket(tokens=float(self._rpm))
                self._buckets[user_id] = bucket

            bucket.refill(self._rpm, self._refill_rate)
            allowed = bucket.consume()
            if not allowed:
                logger.warning("LLM rate limit hit for user %s", user_id)
            return allowed

    def _evict_stale(self) -> None:
        now = time.monotonic()
        stale = [
            uid
            for uid, b in self._buckets.items()
            if now - b.last_used > _EVICT_AFTER_S
        ]
        for uid in stale:
            del self._buckets[uid]


# Module-level singleton
_limiter: UserRateLimiter | None = None


def get_rate_limiter() -> UserRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = UserRateLimiter()
    return _limiter
