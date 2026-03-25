"""http_client.py — Rate-limited HTTP client for src/ingestion."""

from __future__ import annotations

import logging
import time

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

_MIN_REQUEST_INTERVAL = 1.0
_last_request_time: float = 0.0


def rate_limited_get(url: str, timeout: int = 30) -> requests.Response:
    """HTTP GET with 1 req/s rate limiting."""
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    resp = requests.get(url, timeout=timeout)
    _last_request_time = time.monotonic()
    return resp


@retry(
    retry=retry_if_exception_type((requests.ConnectionError, requests.Timeout)),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
)
def fetch_json(url: str) -> dict:
    """Fetch URL, retry on connection errors, handle 429 with 60s backoff."""
    logger.debug("GET %s", url)
    resp = rate_limited_get(url)
    if resp.status_code == 429:
        logger.warning("Rate limited (429) — sleeping 60s before retry")
        time.sleep(60)
        resp = rate_limited_get(url)
    resp.raise_for_status()
    return resp.json()
