"""
lap_times_worker.py — Re-fetch all lap times for a year range from Jolpica.

Reads from env:
  YEAR_START   inclusive start year (e.g. 1996)
  YEAR_END     inclusive end year   (e.g. 1999)
  WORKER_ID    integer label for logging
  GCS_BUCKET   GCS bucket name (default: f1optimizer-data-lake)

Output:
  gs://{bucket}/raw/lap_times_v2/{year}/round_{round:02d}.parquet

Rate-limits to 1 request / 8 s (450 req/hr), safely under the 500 req/hr
per-IP cap on Jolpica. Every race is checked in GCS before fetching.
On any error (network, 5xx, …) the script sleeps 60 s and retries
the same page forever. On 429 it sleeps 300 s before retrying.
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
import time
from typing import Any, Optional

import pandas as pd
import requests
from google.cloud import storage

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")


def _log(severity: str, msg: str, **kw) -> None:
    print(json.dumps({"severity": severity, "message": msg, **kw}), flush=True)


def info(msg, **kw):  _log("INFO",    msg, **kw)
def warn(msg, **kw):  _log("WARNING", msg, **kw)
def error(msg, **kw): _log("ERROR",   msg, **kw)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

YEAR_START  = int(os.environ["YEAR_START"])
YEAR_END    = int(os.environ["YEAR_END"])
WORKER_ID   = int(os.environ.get("WORKER_ID", "0"))
BUCKET_NAME = os.environ.get("GCS_BUCKET", "f1optimizer-data-lake")

BASE_URL    = "https://api.jolpi.ca/ergast/f1"
REQ_GAP     = 8.0      # seconds between requests  (450/hr, limit is 500/hr)
RETRY_WAIT  = 60       # seconds on generic error
RATE_WAIT   = 300      # seconds on 429

_last_req: float = 0.0


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str) -> requests.Response:
    global _last_req
    elapsed = time.monotonic() - _last_req
    if elapsed < REQ_GAP:
        time.sleep(REQ_GAP - elapsed)
    resp = requests.get(url, timeout=30)
    _last_req = time.monotonic()
    return resp


def _fetch_json(url: str) -> Optional[dict[str, Any]]:
    """Fetch with retry-forever. Returns None on 404."""
    attempt = 0
    while True:
        try:
            resp = _get(url)
            if resp.status_code == 404:
                return None
            if resp.status_code == 429:
                warn("rate limited 429", url=url, sleeping=RATE_WAIT)
                time.sleep(RATE_WAIT)
                attempt += 1
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            attempt += 1
            error("fetch error", url=url, attempt=attempt,
                  exc_type=type(exc).__name__, exc=str(exc),
                  sleeping=RETRY_WAIT)
            time.sleep(RETRY_WAIT)


def _paginate(base_url: str, limit: int = 100) -> list[dict[str, Any]]:
    """Page through a Jolpica endpoint, collecting all records."""
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
        # Use the actual limit the API applied (may differ from requested)
        actual_limit = int(mr.get("limit", limit))
        offset += actual_limit
        if offset >= total or not rows:
            break
    return results


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


# ---------------------------------------------------------------------------
# Per-round fetcher
# ---------------------------------------------------------------------------

def _fetch_lap_times_round(year: int, round_num: int) -> pd.DataFrame:
    laps = _paginate(f"{BASE_URL}/{year}/{round_num}/laps/")
    rows = []
    for lap in laps:
        lap_num = lap.get("number")
        for timing in lap.get("Timings", []):
            rows.append({
                "season":   year,
                "round":    round_num,
                "lap":      lap_num,
                "driverId": timing.get("driverId"),
                "position": timing.get("position"),
                "time":     timing.get("time"),
            })
    return pd.DataFrame(rows)


def _get_rounds(year: int) -> list[int]:
    races = _paginate(f"{BASE_URL}/{year}/races/")
    return sorted(int(r["round"]) for r in races if "round" in r)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    info("lap_times_worker start",
         worker_id=WORKER_ID, year_start=YEAR_START, year_end=YEAR_END,
         bucket=BUCKET_NAME)

    gcs    = storage.Client()
    bucket = gcs.bucket(BUCKET_NAME)

    total_races = 0
    skipped     = 0
    fetched     = 0

    for year in range(YEAR_START, YEAR_END + 1):
        info("year start", worker_id=WORKER_ID, year=year)
        rounds = _get_rounds(year)
        info("rounds", worker_id=WORKER_ID, year=year, rounds=rounds)

        for rnd in rounds:
            blob_path = f"raw/lap_times_v2/{year}/round_{rnd:02d}.parquet"
            total_races += 1

            if blob_exists(bucket, blob_path):
                info("skip — already in GCS", year=year, round=rnd)
                skipped += 1
                continue

            df = _fetch_lap_times_round(year, rnd)
            if df.empty:
                warn("no lap times from API", year=year, round=rnd)
                # Write empty marker so we don't re-fetch
                upload_parquet(bucket, blob_path, df)
            else:
                upload_parquet(bucket, blob_path, df)
                info("round done", year=year, round=rnd, rows=len(df),
                     drivers=df["driverId"].nunique() if not df.empty else 0)
            fetched += 1

        info("year done", worker_id=WORKER_ID, year=year)

    info("lap_times_worker complete",
         worker_id=WORKER_ID, total_races=total_races,
         fetched=fetched, skipped=skipped)


if __name__ == "__main__":
    main()
