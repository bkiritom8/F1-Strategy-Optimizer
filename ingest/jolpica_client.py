"""jolpica_client.py — Jolpica/Ergast API pagination and JSON fetch."""

from __future__ import annotations

import logging
from typing import Any, Optional

from .http_utils import backoff_wait, is_rate_limit, rate_limited_get

log = logging.getLogger(__name__)


def fetch_json(url: str) -> Optional[dict[str, Any]]:
    """Fetch with infinite retry. Returns None on 404."""
    attempt = 0
    while True:
        try:
            resp = rate_limited_get(url)
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                log.warning("rate limited 429  url=%s", url)
                backoff_wait(attempt)
                attempt += 1
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            if is_rate_limit(exc):
                log.warning("rate limit  url=%s: %s", url, exc)
            else:
                log.error(
                    "fetch error  url=%s attempt=%d: %s: %s",
                    url,
                    attempt,
                    type(exc).__name__,
                    exc,
                )
            backoff_wait(attempt)
            attempt += 1


def paginate(base_url: str, limit: int = 100) -> list[dict[str, Any]]:
    """Page through a Jolpica endpoint, returning all records."""
    results: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = fetch_json(f"{base_url}?limit={limit}&offset={offset}")
        if data is None:
            break
        mr = data.get("MRData", {})
        total = int(mr.get("total", 0))
        table = (
            mr.get("RaceTable")
            or mr.get("StandingsTable")
            or mr.get("SeasonTable")
            or {}
        )
        rows: list[dict[str, Any]] = []
        for val in table.values():
            if isinstance(val, list):
                rows = val
                break
        results.extend(rows)
        actual_limit = int(mr.get("limit", limit))
        offset += actual_limit
        if offset >= total or not rows:
            break
    return results
