"""
ergast_ingestion.py — Fetch F1 historical data from the Jolpica API.

API base: https://api.jolpi.ca/ergast/f1
Rate limit: 500 calls/hr, 200 per 4 seconds
All endpoints require a trailing slash.

Data is saved as raw JSON to data/raw/jolpica/<endpoint>/<params>.json

Usage:
    ingestion = ErgastIngestion(output_dir="data/raw/jolpica")
    ingestion.fetch_seasons()
    ingestion.fetch_race_results(2024, 1)
    ingestion.fetch_circuits()

    # Bulk ingest a full season
    ingestion.ingest_season(2024)
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.jolpi.ca/ergast/f1"

# Rate limiting: 500 calls/hr → ~1.38 req/s; we stay conservative at 1 req/s
_MIN_REQUEST_INTERVAL = 1.0  # seconds between requests
_last_request_time: float = 0.0


def _rate_limited_get(url: str, timeout: int = 30) -> requests.Response:
    """HTTP GET with rate limiting (1 req/s). Does NOT call raise_for_status."""
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
def _fetch_json(url: str) -> Dict[str, Any]:
    """Fetch a Jolpica URL and return parsed JSON.

    - Retries automatically on connection errors and timeouts (up to 5 attempts).
    - On HTTP 429 (rate limited), sleeps 60 s and retries once.
    - Non-retriable HTTP errors (404, other 4xx) are raised immediately.
    - 5xx errors raise immediately; callers should retry at a higher level.
    """
    logger.debug("GET %s", url)
    resp = _rate_limited_get(url)
    if resp.status_code == 429:
        logger.warning("Rate limited (429) — sleeping 60s before retry")
        time.sleep(60)
        resp = _rate_limited_get(url)
    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


def _paginate(base_url: str, limit: int = 1000) -> List[Dict[str, Any]]:
    """Fetch all pages from a Jolpica endpoint."""
    results: List[Dict[str, Any]] = []
    offset = 0
    while True:
        url = f"{base_url}?limit={limit}&offset={offset}"
        data = _fetch_json(url)
        mr = data.get("MRData", {})
        total = int(mr.get("total", 0))
        # Flatten — pick whichever table key exists
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
        offset += limit
        if offset >= total:
            break
    logger.info("Fetched %d records from %s", len(results), base_url)
    return results


class ErgastIngestion:
    """
    Fetches F1 historical data from the Jolpica API and saves raw JSON.

    Parameters
    ----------
    output_dir : str
        Root directory for raw JSON output (default: data/raw/jolpica)
    """

    def __init__(self, output_dir: str = "data/raw/jolpica") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("ErgastIngestion initialized — output: %s", self.output_dir)

    def _save(self, data: Any, rel_path: str) -> Path:
        """Save data as JSON to output_dir/rel_path."""
        out = self.output_dir / rel_path
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            json.dump(data, f)
        logger.info("Saved %s (%d bytes)", out, out.stat().st_size)
        return out

    def fetch_seasons(self) -> List[Dict[str, Any]]:
        """
        Fetch list of all F1 seasons (1950–present).

        Returns
        -------
        list of season dicts: [{"season": "2024", "url": "..."}, ...]
        """
        url = f"{BASE_URL}/seasons/"
        seasons = _paginate(url)
        self._save(seasons, "seasons.json")
        return seasons

    def fetch_circuits(self) -> List[Dict[str, Any]]:
        """
        Fetch all F1 circuits.

        Returns
        -------
        list of circuit dicts with circuitId, circuitName, Location, etc.
        """
        url = f"{BASE_URL}/circuits/"
        circuits = _paginate(url)
        self._save(circuits, "circuits.json")
        return circuits

    def fetch_drivers(self, year: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Fetch F1 driver list, optionally filtered by season.

        Parameters
        ----------
        year : int, optional
            Season year. If None, fetches all-time driver list.
        """
        if year is not None:
            url = f"{BASE_URL}/{year}/drivers/"
            out_path = f"drivers/{year}.json"
        else:
            url = f"{BASE_URL}/drivers/"
            out_path = "drivers/all.json"
        drivers = _paginate(url)
        self._save(drivers, out_path)
        return drivers

    def fetch_race_results(self, year: int, round_num: int) -> Dict[str, Any]:
        """
        Fetch race results for a specific round.

        Parameters
        ----------
        year : int
            Season year (e.g. 2024)
        round_num : int
            Round number within the season (1-indexed)

        Returns
        -------
        Race result dict with Results list
        """
        url = f"{BASE_URL}/{year}/{round_num}/results/"
        data = _fetch_json(url)
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        result = races[0] if races else {}
        self._save(result, f"results/{year}/{round_num}.json")
        return result

    def fetch_lap_times(self, year: int, round_num: int) -> List[Dict[str, Any]]:
        """
        Fetch all lap times for a race.

        Parameters
        ----------
        year : int
        round_num : int

        Returns
        -------
        List of per-lap dicts, each with a Timings list per driver.
        """
        url = f"{BASE_URL}/{year}/{round_num}/laps/"
        laps = _paginate(url, limit=1000)
        self._save(laps, f"laps/{year}/{round_num}.json")
        return laps

    def fetch_pit_stops(self, year: int, round_num: int) -> List[Dict[str, Any]]:
        """
        Fetch pit stop data for a race.

        Parameters
        ----------
        year : int
        round_num : int

        Returns
        -------
        List of pit stop dicts: driverId, lap, stop, time, duration
        """
        url = f"{BASE_URL}/{year}/{round_num}/pitstops/"
        pit_stops = _paginate(url)
        self._save(pit_stops, f"pit_stops/{year}/{round_num}.json")
        return pit_stops

    def fetch_qualifying(self, year: int, round_num: int) -> Dict[str, Any]:
        """
        Fetch qualifying results for a round.

        Parameters
        ----------
        year : int
        round_num : int
        """
        url = f"{BASE_URL}/{year}/{round_num}/qualifying/"
        data = _fetch_json(url)
        races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
        result = races[0] if races else {}
        self._save(result, f"qualifying/{year}/{round_num}.json")
        return result

    def ingest_season(self, year: int, max_rounds: int = 25) -> Dict[str, int]:
        """
        Ingest all data for a full season: results, lap times, pit stops.

        Parameters
        ----------
        year : int
            Season to ingest
        max_rounds : int
            Maximum number of rounds to fetch (default 25)

        Returns
        -------
        Dict mapping data type to number of records fetched
        """
        logger.info("Starting full season ingest: %d", year)
        counts: Dict[str, int] = {}

        # Race results — one request per round, stop when 404 or empty
        results_count = 0
        for rnd in range(1, max_rounds + 1):
            try:
                result = self.fetch_race_results(year, rnd)
                if not result:
                    logger.info("No results for %d round %d — stopping", year, rnd)
                    break
                results_count += len(result.get("Results", []))
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    logger.info("Round %d not found — end of season", rnd)
                    break
                raise
            except Exception:
                logger.exception("Failed to fetch results for %d round %d", year, rnd)
                break
        counts["results"] = results_count

        # Lap times
        laps_count = 0
        for rnd in range(1, max_rounds + 1):
            try:
                laps = self.fetch_lap_times(year, rnd)
                if not laps:
                    break
                laps_count += len(laps)
            except Exception:
                logger.warning(
                    "Failed to fetch laps for %d round %d, skipping", year, rnd
                )
        counts["laps"] = laps_count

        # Pit stops
        pit_count = 0
        for rnd in range(1, max_rounds + 1):
            try:
                pits = self.fetch_pit_stops(year, rnd)
                if not pits:
                    break
                pit_count += len(pits)
            except Exception:
                logger.warning(
                    "Failed to fetch pit stops for %d round %d, skipping", year, rnd
                )
        counts["pit_stops"] = pit_count

        logger.info("Season %d ingest complete: %s", year, counts)
        return counts


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    ingestion = ErgastIngestion()
    # Fetch reference data
    ingestion.fetch_seasons()
    ingestion.fetch_circuits()
    ingestion.fetch_drivers()
    # Ingest recent seasons
    for season_year in range(2022, 2026):
        ingestion.ingest_season(season_year)
