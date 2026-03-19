"""
gap_worker.py — Targeted gap-fill jobs for missing F1 data.

Routes by JOB_ID env var:
  1 → 2022 FastF1 missing sessions
  2 → 2023 FastF1 full year
  3 → 2024 FastF1 missing sessions
  4 → 2025 FastF1 full year
  5 → race_results pagination fix (all seasons) + 2023 Abu Dhabi lap_times

All jobs:
  - Check GCS before downloading — skip anything already present
  - On ANY error: sleep 3600s and retry the same session indefinitely, never skip
  - Upload gs://{bucket}/status/job{N}.done on completion
  - Log all progress to stdout (Cloud Logging picks this up automatically)
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests
from google.cloud import storage

# ---------------------------------------------------------------------------
# Logging — structured JSON so Cloud Logging can parse fields
# ---------------------------------------------------------------------------

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(message)s",
)
def _log(level: str, msg: str, **kw) -> None:
    record = {"severity": level, "message": msg, **kw}
    print(json.dumps(record), flush=True)

def info(msg: str, **kw):  _log("INFO",    msg, **kw)
def warn(msg: str, **kw):  _log("WARNING", msg, **kw)
def error(msg: str, **kw): _log("ERROR",   msg, **kw)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BUCKET_NAME   = os.environ["GCS_BUCKET"]
RETRY_SLEEP   = 3600   # seconds — sleep on ANY error before retry
FASTF1_CACHE  = Path("/tmp/f1_cache")

SESSION_TYPES = {
    "conventional":      ["FP1", "FP2", "FP3", "Q", "R"],
    "sprint_qualifying": ["FP1", "SQ", "FP2", "S", "Q", "R"],
    "sprint":            ["FP1", "SQ", "SS", "Q", "R"],
}

# Sprint event names by year
SPRINT_EVENTS: dict[int, set[str]] = {
    2022: {"Emilia Romagna Grand Prix", "Austrian Grand Prix", "Brazilian Grand Prix"},
    2023: {"Azerbaijan Grand Prix", "Austrian Grand Prix", "Belgian Grand Prix",
           "Sao Paulo Grand Prix", "Qatar Grand Prix", "United States Grand Prix"},
    2024: {"Chinese Grand Prix", "Miami Grand Prix", "Austrian Grand Prix",
           "United States Grand Prix", "Sao Paulo Grand Prix", "Qatar Grand Prix"},
    2025: {"Chinese Grand Prix", "Miami Grand Prix", "Belgian Grand Prix",
           "United States Grand Prix", "Sao Paulo Grand Prix", "Qatar Grand Prix"},
}

JOLPICA_BASE   = "https://api.jolpi.ca/ergast/f1"
JOLPICA_GAP    = 1.0  # seconds between API calls

_last_req: float = 0.0


# ---------------------------------------------------------------------------
# GCS helpers
# ---------------------------------------------------------------------------

def blob_exists(bucket: storage.Bucket, path: str) -> bool:
    return bucket.blob(path).exists()


def upload_parquet(bucket: storage.Bucket, path: str, df: pd.DataFrame) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    buf.seek(0)
    bucket.blob(path).upload_from_file(buf, content_type="application/octet-stream")
    info("uploaded", path=path, rows=len(df))


def upload_done_marker(bucket: storage.Bucket, job_id: int) -> None:
    bucket.blob(f"status/job{job_id}.done").upload_from_string(
        "", content_type="text/plain"
    )
    info("done marker uploaded", job_id=job_id)


# ---------------------------------------------------------------------------
# Retry wrapper — sleeps RETRY_SLEEP on any exception, retries forever
# ---------------------------------------------------------------------------

def retry_forever(fn, label: str):
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            attempt += 1
            error("error — will retry after 3600s",
                  label=label, attempt=attempt,
                  exc_type=type(exc).__name__, exc=str(exc))
            time.sleep(RETRY_SLEEP)


# ---------------------------------------------------------------------------
# FastF1 workers (jobs 1-4)
# ---------------------------------------------------------------------------

def _extract_telemetry(session) -> Optional[pd.DataFrame]:
    """Per-lap raw telemetry, Driver + LapNumber prepended, no other additions."""
    frames = []
    for _, lap in session.laps.iterlaps():
        try:
            tel = lap.get_telemetry()
            if tel is None or tel.empty:
                continue
            tel.insert(0, "LapNumber", lap["LapNumber"])
            tel.insert(0, "Driver",    lap["Driver"])
            frames.append(tel)
        except Exception:
            pass
    return pd.concat(frames, ignore_index=True) if frames else None


def _download_session(
    bucket: storage.Bucket,
    year: int,
    event_name: str,
    session_type: str,
) -> None:
    import fastf1  # imported here so job5 (no fastf1) doesn't fail at import
    import logging as _logging
    _logging.getLogger("fastf1").setLevel(_logging.ERROR)

    blob_path = f"telemetry/{year}/{event_name}/{session_type}.parquet"

    if blob_exists(bucket, blob_path):
        info("skip — already in GCS", year=year, event=event_name, session=session_type)
        return

    def _do():
        session = fastf1.get_session(year, event_name, session_type)
        session.load(telemetry=True, laps=True, weather=False, messages=False)
        tel = _extract_telemetry(session)
        if tel is None:
            info("no telemetry data", year=year, event=event_name, session=session_type)
            return
        upload_parquet(bucket, blob_path, tel)
        info("session done", year=year, event=event_name, session=session_type, rows=len(tel))

    retry_forever(_do, label=f"{year}/{event_name}/{session_type}")


def run_fastf1_year(job_id: int, year: int, bucket: storage.Bucket) -> None:
    import fastf1
    import logging as _logging
    _logging.getLogger("fastf1").setLevel(_logging.ERROR)

    FASTF1_CACHE.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(FASTF1_CACHE))

    info("fastf1 year start", job_id=job_id, year=year)

    def _get_schedule():
        return fastf1.get_event_schedule(year, include_testing=False)

    schedule = retry_forever(_get_schedule, label=f"schedule/{year}")
    sprint_events = SPRINT_EVENTS.get(year, set())

    for _, event in schedule.iterrows():
        event_name   = event["EventName"]
        event_format = event.get("EventFormat", "conventional")
        # Use actual EventFormat when available, fall back to our sprint map
        if event_format not in SESSION_TYPES:
            event_format = "sprint" if event_name in sprint_events else "conventional"
        sessions = SESSION_TYPES[event_format]

        info("event", year=year, event=event_name, format=event_format,
             sessions=sessions)

        for stype in sessions:
            _download_session(bucket, year, event_name, stype)
            time.sleep(0.5)

    upload_done_marker(bucket, job_id)
    info("fastf1 year complete", job_id=job_id, year=year)


# ---------------------------------------------------------------------------
# Jolpica worker (job 5)
# ---------------------------------------------------------------------------

def _rate_get(url: str) -> requests.Response:
    global _last_req
    elapsed = time.monotonic() - _last_req
    if elapsed < JOLPICA_GAP:
        time.sleep(JOLPICA_GAP - elapsed)
    resp = requests.get(url, timeout=30)
    _last_req = time.monotonic()
    return resp


def _fetch_json(url: str) -> Optional[dict[str, Any]]:
    """Fetch with infinite retry on errors, return None on 404."""
    attempt = 0
    while True:
        try:
            resp = _rate_get(url)
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                warn("rate limited 429", url=url)
                time.sleep(RETRY_SLEEP)
                attempt += 1
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            attempt += 1
            error("fetch error", url=url, attempt=attempt,
                  exc_type=type(exc).__name__, exc=str(exc))
            time.sleep(RETRY_SLEEP)


def _paginate(base_url: str, limit: int = 100) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    offset = 0
    while True:
        data = _fetch_json(f"{base_url}?limit={limit}&offset={offset}")
        if data is None:
            break
        mr    = data.get("MRData", {})
        total = int(mr.get("total", 0))
        table = (mr.get("RaceTable") or mr.get("StandingsTable")
                 or mr.get("SeasonTable") or {})
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


def _fetch_race_results_year(year: int) -> pd.DataFrame:
    races = _paginate(f"{JOLPICA_BASE}/{year}/results/")
    rows = []
    for race in races:
        base = dict(
            season=year,
            round=int(race.get("round", 0)),
            raceName=race.get("raceName", ""),
            circuitId=race.get("Circuit", {}).get("circuitId", ""),
        )
        for r in race.get("Results", []):
            rows.append({
                **base,
                "position":      r.get("position"),
                "positionText":  r.get("positionText"),
                "points":        r.get("points"),
                "driverId":      r.get("Driver", {}).get("driverId"),
                "constructorId": r.get("Constructor", {}).get("constructorId"),
                "grid":          r.get("grid"),
                "laps":          r.get("laps"),
                "status":        r.get("status"),
            })
    return pd.DataFrame(rows)


def _fetch_lap_times_round(year: int, round_num: int) -> pd.DataFrame:
    laps = _paginate(f"{JOLPICA_BASE}/{year}/{round_num}/laps/")
    rows = []
    for lap in laps:
        lap_num = lap.get("number")
        for timing in lap.get("Timings", []):
            rows.append(dict(
                season=year, round=round_num, lap=lap_num,
                driverId=timing.get("driverId"),
                position=timing.get("position"),
                time=timing.get("time"),
            ))
    return pd.DataFrame(rows)


def run_historical(job_id: int, bucket: storage.Bucket) -> None:
    info("historical job start", job_id=job_id)

    # 1. Race results — all seasons 1950-2025 with correct pagination
    seasons_data = _paginate(f"{JOLPICA_BASE}/seasons/")
    seasons = sorted(int(s["season"]) for s in seasons_data)
    info("fetching race_results", total_seasons=len(seasons),
         range=f"{seasons[0]}-{seasons[-1]}")

    for year in seasons:
        blob_path = f"historical/race_results/{year}.parquet"
        if blob_exists(bucket, blob_path):
            info("skip race_results — already in GCS", year=year)
            continue

        def _fetch(y=year):
            df = _fetch_race_results_year(y)
            if df.empty:
                warn("no race results", year=y)
                return
            upload_parquet(bucket, f"historical/race_results/{y}.parquet", df)
            info("race_results done", year=y,
                 rounds=df["round"].nunique(), rows=len(df))

        retry_forever(_fetch, label=f"race_results/{year}")

    # 2. 2023 Abu Dhabi GP lap times (round 22 — last race of 2023 season)
    abu_dhabi_path = "historical/lap_times/2023/round_22_abu_dhabi.parquet"
    if not blob_exists(bucket, abu_dhabi_path):
        def _fetch_abu_dhabi():
            df = _fetch_lap_times_round(2023, 22)
            if df.empty:
                warn("no lap times for 2023 round 22")
                return
            upload_parquet(bucket, abu_dhabi_path, df)
            info("2023 Abu Dhabi lap_times done", rows=len(df))

        retry_forever(_fetch_abu_dhabi, label="lap_times/2023/22")
    else:
        info("skip 2023 Abu Dhabi lap_times — already in GCS")

    upload_done_marker(bucket, job_id)
    info("historical job complete", job_id=job_id)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

FASTF1_JOBS = {1: 2022, 2: 2023, 3: 2024, 4: 2025}

def main() -> None:
    job_id = int(os.environ.get("JOB_ID", "0"))
    if job_id == 0:
        error("JOB_ID env var not set")
        sys.exit(1)

    info("gap_worker starting", job_id=job_id, bucket=BUCKET_NAME)
    gcs = storage.Client()
    bucket = gcs.bucket(BUCKET_NAME)

    if job_id in FASTF1_JOBS:
        run_fastf1_year(job_id, FASTF1_JOBS[job_id], bucket)
    elif job_id == 5:
        run_historical(job_id, bucket)
    else:
        error("unknown JOB_ID", job_id=job_id)
        sys.exit(1)


if __name__ == "__main__":
    main()
