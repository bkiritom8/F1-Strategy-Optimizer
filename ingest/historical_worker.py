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
import pandas as pd
from google.cloud import storage

from .gcs_utils import upload_done_marker, upload_parquet
from .http_utils import backoff_wait
from .jolpica_client import paginate as _paginate
from .progress import Progress

log = logging.getLogger(__name__)

BASE_URL      = "https://api.jolpi.ca/ergast/f1"
YEARS         = range(1950, 2018)   # 1950 … 2017 inclusive


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
                backoff_wait(attempt)
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
