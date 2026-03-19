"""
historical_worker.py — Task 8: Ergast/Jolpica historical data 1950-2017.

Fetches for every season:
  race_results          gs://{bucket}/historical/{year}/race_results.parquet
  lap_times             gs://{bucket}/historical/{year}/lap_times.parquet
  pit_stops             gs://{bucket}/historical/{year}/pit_stops.parquet
  qualifying            gs://{bucket}/historical/{year}/qualifying.parquet
  driver_standings      gs://{bucket}/historical/{year}/driver_standings.parquet
  constructor_standings gs://{bucket}/historical/{year}/constructor_standings.parquet

Notes:
  - Lap times available from 1996 in Ergast; earlier seasons produce empty files.
  - Pit stop data available from 2012 in Ergast.
  - 404 responses → genuinely absent data; marked done, not retried.
  - All other errors → infinite exponential-backoff retry (60s, 120s, 240s, …).
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import pandas as pd
import requests
from google.cloud import storage

from .gcs_utils import upload_done_marker, upload_parquet
from .progress import Progress

log = logging.getLogger(__name__)

BASE_URL      = "https://api.jolpi.ca/ergast/f1"
YEARS         = range(1950, 2018)   # 1950 … 2017 inclusive
BACKOFF_BASE  = 60      # seconds
BACKOFF_CAP   = 3_600   # 1 hour max wait
MIN_REQ_GAP   = 1.0     # seconds between API calls
_last_req: float = 0.0


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str, timeout: int = 30) -> requests.Response:
    global _last_req
    elapsed = time.monotonic() - _last_req
    if elapsed < MIN_REQ_GAP:
        time.sleep(MIN_REQ_GAP - elapsed)
    resp = requests.get(url, timeout=timeout)
    _last_req = time.monotonic()
    return resp


def _is_rate_limit(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    return "rate limit" in s or "429" in s or "ratelimit" in s


def _backoff_wait(attempt: int) -> None:
    wait = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
    log.warning("backoff: sleeping %.0fs (attempt %d)", wait, attempt + 1)
    time.sleep(wait)


def _fetch_json_retry(url: str) -> Optional[dict[str, Any]]:
    """
    Fetch URL with infinite exponential-backoff retry.
    Returns None on 404 (data genuinely absent). Never returns on persistent errors.
    """
    attempt = 0
    while True:
        try:
            resp = _get(url)
            if resp.status_code == 404:
                log.info("404 — data absent: %s", url)
                return None
            if resp.status_code == 429:
                log.warning("rate limited (429): %s", url)
                _backoff_wait(attempt)
                attempt += 1
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            if _is_rate_limit(exc):
                log.warning("rate limit: %s — %s", url, exc)
            else:
                log.error("fetch error (attempt %d): %s — %s: %s",
                          attempt, url, type(exc).__name__, exc)
            _backoff_wait(attempt)
            attempt += 1


def _paginate(base_url: str, limit: int = 100) -> list[dict[str, Any]]:
    """Page through a Jolpica endpoint, returning all records."""
    results: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = _fetch_json_retry(f"{base_url}?limit={limit}&offset={offset}")
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


# ---------------------------------------------------------------------------
# Fetchers — one per data type
# ---------------------------------------------------------------------------

def _fetch_race_results(year: int) -> pd.DataFrame:
    races = _paginate(f"{BASE_URL}/{year}/results/")
    rows = []
    for race in races:
        base = {
            "season": year,
            "round": int(race.get("round", 0)),
            "raceName": race.get("raceName", ""),
            "circuitId": race.get("Circuit", {}).get("circuitId", ""),
        }
        for result in race.get("Results", []):
            rows.append({
                **base,
                "position":     result.get("position"),
                "positionText": result.get("positionText"),
                "points":       result.get("points"),
                "driverId":     result.get("Driver", {}).get("driverId"),
                "constructorId": result.get("Constructor", {}).get("constructorId"),
                "grid":         result.get("grid"),
                "laps":         result.get("laps"),
                "status":       result.get("status"),
            })
    return pd.DataFrame(rows)


def _fetch_lap_times(year: int, rounds: list[int]) -> pd.DataFrame:
    rows = []
    for rnd in rounds:
        laps = _paginate(f"{BASE_URL}/{year}/{rnd}/laps/")
        for lap in laps:
            lap_num = lap.get("number")
            for timing in lap.get("Timings", []):
                rows.append({
                    "season":   year,
                    "round":    rnd,
                    "lap":      lap_num,
                    "driverId": timing.get("driverId"),
                    "position": timing.get("position"),
                    "time":     timing.get("time"),
                })
    return pd.DataFrame(rows)


def _fetch_pit_stops(year: int, rounds: list[int]) -> pd.DataFrame:
    rows = []
    for rnd in rounds:
        pits = _paginate(f"{BASE_URL}/{year}/{rnd}/pitstops/")
        for pit in pits:
            rows.append({
                "season":   year,
                "round":    rnd,
                "driverId": pit.get("driverId"),
                "stop":     pit.get("stop"),
                "lap":      pit.get("lap"),
                "time":     pit.get("time"),
                "duration": pit.get("duration"),
            })
    return pd.DataFrame(rows)


def _fetch_qualifying(year: int, rounds: list[int]) -> pd.DataFrame:
    rows = []
    for rnd in rounds:
        races = _paginate(f"{BASE_URL}/{year}/{rnd}/qualifying/")
        for race in races:
            for result in race.get("QualifyingResults", []):
                rows.append({
                    "season":      year,
                    "round":       rnd,
                    "position":    result.get("position"),
                    "driverId":    result.get("Driver", {}).get("driverId"),
                    "constructorId": result.get("Constructor", {}).get("constructorId"),
                    "q1":          result.get("Q1"),
                    "q2":          result.get("Q2"),
                    "q3":          result.get("Q3"),
                })
    return pd.DataFrame(rows)


def _fetch_driver_standings(year: int) -> pd.DataFrame:
    lists = _paginate(f"{BASE_URL}/{year}/driverStandings/")
    rows = []
    for standings_list in lists:
        for s in standings_list.get("DriverStandings", []):
            rows.append({
                "season":       year,
                "position":     s.get("position"),
                "points":       s.get("points"),
                "wins":         s.get("wins"),
                "driverId":     s.get("Driver", {}).get("driverId"),
                "constructorId": s.get("Constructors", [{}])[0].get("constructorId"),
            })
    return pd.DataFrame(rows)


def _fetch_constructor_standings(year: int) -> pd.DataFrame:
    lists = _paginate(f"{BASE_URL}/{year}/constructorStandings/")
    rows = []
    for standings_list in lists:
        for s in standings_list.get("ConstructorStandings", []):
            rows.append({
                "season":        year,
                "position":      s.get("position"),
                "points":        s.get("points"),
                "wins":          s.get("wins"),
                "constructorId": s.get("Constructor", {}).get("constructorId"),
            })
    return pd.DataFrame(rows)


def _get_rounds(year: int) -> list[int]:
    """Return all round numbers for *year* from the race schedule."""
    races = _paginate(f"{BASE_URL}/{year}/races/")
    return [int(r["round"]) for r in races if "round" in r]


# ---------------------------------------------------------------------------
# Per-year ingestion
# ---------------------------------------------------------------------------

def _ingest_year(year: int, bucket: storage.Bucket, progress: Progress) -> None:
    log.info("historical: starting year %d", year)

    # Get round list (needed for per-round data types)
    rounds_key = f"historical/{year}/__rounds__"
    rounds: list[int] = []
    if not progress.is_done(rounds_key):
        rounds = _get_rounds(year)
        log.info("historical: year=%d  rounds=%s", year, rounds)
        progress.mark_done(rounds_key)
    else:
        rounds = _get_rounds(year)

    # Define all data types: (key_suffix, fetcher, blob_path)
    tasks = [
        (
            "race_results",
            lambda y=year: _fetch_race_results(y),
            f"historical/{year}/race_results.parquet",
        ),
        (
            "driver_standings",
            lambda y=year: _fetch_driver_standings(y),
            f"historical/{year}/driver_standings.parquet",
        ),
        (
            "constructor_standings",
            lambda y=year: _fetch_constructor_standings(y),
            f"historical/{year}/constructor_standings.parquet",
        ),
        (
            "lap_times",
            lambda y=year, r=rounds: _fetch_lap_times(y, r),
            f"historical/{year}/lap_times.parquet",
        ),
        (
            "qualifying",
            lambda y=year, r=rounds: _fetch_qualifying(y, r),
            f"historical/{year}/qualifying.parquet",
        ),
        (
            "pit_stops",
            lambda y=year, r=rounds: _fetch_pit_stops(y, r),
            f"historical/{year}/pit_stops.parquet",
        ),
    ]

    for data_type, fetcher, blob_path in tasks:
        key = f"historical/{year}/{data_type}"
        if progress.is_done(key):
            print(f"  [SKIP]  {year} | {data_type}  (already done)")
            continue

        attempt = 0
        while True:
            try:
                df = fetcher()
                if df.empty:
                    log.info("historical: no data  year=%d  type=%s  (marking done)", year, data_type)
                    print(f"  [SKIP]  {year} | {data_type}  (no data from API)")
                else:
                    upload_parquet(df, bucket, blob_path)
                    print(f"  [OK]    {year} | {data_type}  ({len(df):,} rows)")
                    log.info("historical done  year=%d  type=%s  rows=%d", year, data_type, len(df))
                progress.mark_done(key)
                break
            except Exception as exc:
                log.error("historical error  year=%d  type=%s  attempt=%d: %s: %s",
                          year, data_type, attempt, type(exc).__name__, exc)
                print(f"  [ERR]   {year} | {data_type}  — {type(exc).__name__}: {exc}")
                _backoff_wait(attempt)
                attempt += 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def run(task_id: int, bucket: storage.Bucket, progress: Progress) -> None:
    print(f"\n{'='*60}")
    print(f"  Historical worker  task={task_id}  years=1950-2017")
    print(f"{'='*60}\n")
    log.info("historical_worker start  task=%d", task_id)

    for year in YEARS:
        print(f"\n--- {year} ---")
        _ingest_year(year, bucket, progress)

    upload_done_marker(bucket, task_id)
    log.info("historical_worker complete  task=%d", task_id)
    print(f"\n[DONE] Task {task_id} — historical 1950-2017 complete")
