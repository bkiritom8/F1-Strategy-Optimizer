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
import fastf1
from google.cloud import storage

from .gcs_utils import upload_done_marker, upload_parquet
from .http_utils import backoff_wait, is_rate_limit
from .progress import Progress
from .telemetry_extractor import extract_telemetry

log = logging.getLogger(__name__)

CACHE_DIR = Path("/tmp/f1_cache")

SESSION_TYPES: dict[str, list[str]] = {
    "conventional":      ["FP1", "FP2", "FP3", "Q", "R"],
    "sprint_qualifying": ["FP1", "SQ", "FP2", "S", "Q", "R"],
    "sprint":            ["FP1", "SQ", "SS", "Q", "R"],
}

SESSION_PAUSE = 0.5    # seconds between sessions


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

            tel = extract_telemetry(session)
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
            if is_rate_limit(exc):
                log.warning("rate limit  year=%d  event=%s  type=%s: %s",
                            year, event_name, session_type, exc)
                print(f"  [RATE]  {year} | {event_name} | {session_type}  — rate limited, backing off")
            else:
                log.error("error  year=%d  event=%s  type=%s  attempt=%d: %s: %s",
                          year, event_name, session_type, attempt, type(exc).__name__, exc)
                print(f"  [ERR]   {year} | {event_name} | {session_type}  — {type(exc).__name__}: {exc}")

            backoff_wait(attempt)
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
