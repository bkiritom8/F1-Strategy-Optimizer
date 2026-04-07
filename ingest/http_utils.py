"""http_utils.py — Rate-limited HTTP helpers for ingest workers."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import requests

log = logging.getLogger(__name__)

_last_req: float = 0.0
BACKOFF_BASE = 60
BACKOFF_CAP = 120


def rate_limited_get(
    url: str, gap: float = 1.0, timeout: int = 30
) -> requests.Response:
    """HTTP GET with rate limiting. *gap* = min seconds between calls."""
    global _last_req
    elapsed = time.monotonic() - _last_req
    if elapsed < gap:
        time.sleep(gap - elapsed)
    resp = requests.get(url, timeout=timeout)
    _last_req = time.monotonic()
    return resp


def is_rate_limit(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    return "rate limit" in s or "429" in s or "ratelimit" in s


def backoff_wait(attempt: int) -> float:
    wait = min(BACKOFF_BASE * (2**attempt), BACKOFF_CAP)
    log.warning("backoff: sleeping %.0fs (attempt %d)", wait, attempt + 1)
    time.sleep(wait)
    return wait


def retry_forever(fn: Callable, label: str, retry_sleep: int = 3600) -> Any:
    """Call *fn()* in a loop; on any exception sleep *retry_sleep* s and retry."""
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            attempt += 1
            log.error(
                "error — will retry after %ds  label=%s attempt=%d: %s: %s",
                retry_sleep,
                label,
                attempt,
                type(exc).__name__,
                exc,
            )
            time.sleep(retry_sleep)
