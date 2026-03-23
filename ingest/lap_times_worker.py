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

import logging
import os
import sys
import pandas as pd
from google.cloud import storage

from .gcs_utils import blob_exists, upload_parquet
from .jolpica_client import paginate as _paginate

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(stream=sys.stdout, level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

YEAR_START  = int(os.environ["YEAR_START"])
YEAR_END    = int(os.environ["YEAR_END"])
WORKER_ID   = int(os.environ.get("WORKER_ID", "0"))
BUCKET_NAME = os.environ.get("GCS_BUCKET", "f1optimizer-data-lake")

BASE_URL    = "https://api.jolpi.ca/ergast/f1"
REQ_GAP     = 8.0      # seconds between requests  (450/hr, limit is 500/hr)


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
    logger.info("lap_times_worker start  worker_id=%s year_start=%s year_end=%s bucket=%s",
                WORKER_ID, YEAR_START, YEAR_END, BUCKET_NAME)

    gcs    = storage.Client()
    bucket = gcs.bucket(BUCKET_NAME)

    total_races = 0
    skipped     = 0
    fetched     = 0

    for year in range(YEAR_START, YEAR_END + 1):
        logger.info("year start  worker_id=%s year=%s", WORKER_ID, year)
        rounds = _get_rounds(year)
        logger.info("rounds  worker_id=%s year=%s rounds=%s", WORKER_ID, year, rounds)

        for rnd in rounds:
            blob_path = f"raw/lap_times_v2/{year}/round_{rnd:02d}.parquet"
            total_races += 1

            if blob_exists(bucket, blob_path):
                logger.info("skip — already in GCS  year=%s round=%s", year, rnd)
                skipped += 1
                continue

            df = _fetch_lap_times_round(year, rnd)
            if df.empty:
                logger.warning("no lap times from API  year=%s round=%s", year, rnd)
                # Write empty marker so we don't re-fetch
                upload_parquet(df, bucket, blob_path)
            else:
                upload_parquet(df, bucket, blob_path)
                logger.info("round done  year=%s round=%s rows=%s drivers=%s",
                            year, rnd, len(df),
                            df["driverId"].nunique() if not df.empty else 0)
            fetched += 1

        logger.info("year done  worker_id=%s year=%s", WORKER_ID, year)

    logger.info("lap_times_worker complete  worker_id=%s total_races=%s fetched=%s skipped=%s",
                WORKER_ID, total_races, fetched, skipped)


if __name__ == "__main__":
    main()
