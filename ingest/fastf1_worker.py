"""
fastf1_worker.py — Tasks 0-7: download FastF1 telemetry for one year (2018-2025).

Telemetry is saved to:
  gs://{bucket}/telemetry/{year}/{event_name}/{session_type}.parquet

Session sets by event format:
  conventional      FP1 FP2 FP3 Q R
  sprint_qualifying FP1 SQ  FP2 S Q R   (2021-2022)
  sprint            FP1 SQ  SS  Q R     (2023+)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import fastf1
import pandas as pd
from google.cloud import storage

from .gcs_utils import upload_done_marker, upload_parquet
from .progress import Progress

log = logging.getLogger(__name__)

CACHE_DIR = Path("/tmp/f1_cache")

SESSION_TYPES: dict[str, list[str]] = {
    "conventional":      ["FP1", "FP2", "FP3", "Q", "R"],
    "sprint_qualifying": ["FP1", "SQ", "FP2", "S", "Q", "R"],
    "sprint":            ["FP1", "SQ", "SS", "Q", "R"],
}

BACKOFF_BASE = 60      # seconds — doubles on each retry: 60, 120, 240, 480 …
BACKOFF_CAP  = 3_600   # never wait longer than 1 h between retries
SESSION_PAUSE = 0.5    # seconds between sessions


def _is_rate_limit(exc: Exception) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    return "rate limit" in s or "429" in s or "ratelimit" in s


def _backoff_wait(attempt: int) -> float:
    wait = min(BACKOFF_BASE * (2 ** attempt), BACKOFF_CAP)
    log.warning("backoff: sleeping %.0fs (attempt %d)", wait, attempt + 1)
    time.sleep(wait)
    return wait


# ---------------------------------------------------------------------------
# Telemetry extraction — raw FastF1 channels, no extra columns
# ---------------------------------------------------------------------------

def _extract_telemetry(session: fastf1.core.Session) -> Optional[pd.DataFrame]:
    """
    Iterate every lap, call get_telemetry(), concatenate.
    Only Driver and LapNumber are prepended as minimal identifiers.
    All other columns are exactly what FastF1 returns from get_telemetry().
    """
    frames = []
    for _, lap in session.laps.iterlaps():
        try:
            tel = lap.get_telemetry()
            if tel is None or tel.empty:
                continue
            tel.insert(0, "LapNumber", lap["LapNumber"])
            tel.insert(0, "Driver", lap["Driver"])
            frames.append(tel)
        except Exception as exc:
            log.debug("skipped lap %s/%s: %s", lap.get("Driver"), lap.get("LapNumber"), exc)

    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------------------
# Single-session download with infinite exponential-backoff retry
# ---------------------------------------------------------------------------

def _download_session(
    year: int,
    event_name: str,
    session_type: str,
    bucket: storage.Bucket,
    progress: Progress,
) -> None:
    """Download one session, retrying forever on any error."""
    key = f"telemetry/{year}/{event_name}/{session_type}"
    blob_path = f"telemetry/{year}/{event_name}/{session_type}.parquet"

    if progress.is_done(key):
        print(f"  [SKIP]  {year} | {event_name} | {session_type}  (already done)")
        return

    attempt = 0
    while True:
        try:
            log.info("loading session  year=%d  event=%s  type=%s  attempt=%d",
                     year, event_name, session_type, attempt)
            session = fastf1.get_session(year, event_name, session_type)
            session.load(telemetry=True, laps=True, weather=False, messages=False)

            tel = _extract_telemetry(session)
            if tel is None:
                # No telemetry data at all — mark done so we never retry
                log.warning("no telemetry  year=%d  event=%s  type=%s  marking done",
                            year, event_name, session_type)
                print(f"  [SKIP]  {year} | {event_name} | {session_type}  (no telemetry data)")
                progress.mark_done(key)
                return

            upload_parquet(tel, bucket, blob_path)
            progress.mark_done(key)
            print(f"  [OK]    {year} | {event_name} | {session_type}  ({len(tel):,} rows)")
            log.info("session done  year=%d  event=%s  type=%s  rows=%d",
                     year, event_name, session_type, len(tel))
            return

        except Exception as exc:
            if _is_rate_limit(exc):
                log.warning("rate limit  year=%d  event=%s  type=%s: %s",
                            year, event_name, session_type, exc)
                print(f"  [RATE]  {year} | {event_name} | {session_type}  — rate limited, backing off")
            else:
                log.error("error  year=%d  event=%s  type=%s  attempt=%d: %s: %s",
                          year, event_name, session_type, attempt, type(exc).__name__, exc)
                print(f"  [ERR]   {year} | {event_name} | {session_type}  — {type(exc).__name__}: {exc}")

            _backoff_wait(attempt)
            attempt += 1


# ---------------------------------------------------------------------------
# Year entry point
# ---------------------------------------------------------------------------

def run(year: int, task_id: int, bucket: storage.Bucket, progress: Progress) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(CACHE_DIR))

    print(f"\n{'='*60}")
    print(f"  FastF1 worker  task={task_id}  year={year}")
    print(f"{'='*60}\n")
    log.info("fastf1_worker start  task=%d  year=%d", task_id, year)

    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
    except Exception as exc:
        log.error("failed to load schedule  year=%d: %s", year, exc)
        raise

    for _, event in schedule.iterrows():
        event_name   = event["EventName"]
        event_format = event.get("EventFormat", "conventional")
        sessions     = SESSION_TYPES.get(event_format, SESSION_TYPES["conventional"])

        print(f"\n  {event_name}  [{event_format}]")

        for stype in sessions:
            _download_session(year, event_name, stype, bucket, progress)
            time.sleep(SESSION_PAUSE)

    upload_done_marker(bucket, task_id)
    log.info("fastf1_worker complete  task=%d  year=%d", task_id, year)
    print(f"\n[DONE] Task {task_id} — year {year} complete")
