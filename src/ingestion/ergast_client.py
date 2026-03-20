"""ergast_client.py — Jolpica/Ergast endpoint pagination."""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from .http_client import fetch_json

logger = logging.getLogger(__name__)

BASE_URL = "https://api.jolpi.ca/ergast/f1"


def paginate(base_url: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """Fetch all pages from a Jolpica endpoint."""
    results: List[Dict[str, Any]] = []
    offset = 0
    while True:
        url = f"{base_url}?limit={limit}&offset={offset}"
        data = fetch_json(url)
        mr = data.get("MRData", {})
        total = int(mr.get("total", 0))
        table = (
            mr.get("RaceTable")
            or mr.get("SeasonTable")
            or mr.get("DriverTable")
            or mr.get("CircuitTable")
            or {}
        )
        rows: List[Dict[str, Any]] = []
        for val in table.values():
            if isinstance(val, list):
                rows = val
                break
        results.extend(rows)
        actual_limit = int(mr.get("limit", limit))
        offset += actual_limit
        if offset >= total or not rows:
            break
    logger.info("Fetched %d records from %s", len(results), base_url)
    return results
