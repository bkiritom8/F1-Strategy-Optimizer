"""
backfill_data.py — Fix missing F1 data in GCS.

Gaps addressed:
  1. race_results.csv  — only 5-6 rounds per season; re-fetches all 76 seasons
                         via the season-level Jolpica endpoint (faster than per-round)
  2. laps_2023.csv     — missing round 23 (Abu Dhabi GP)
  3. FastF1 laps/telemetry — 2022 rounds 4-22, 2023 all, 2024 rounds 2-24, 2025 all

After patching raw CSVs in GCS, re-runs csv_to_parquet for affected files.

Usage:
    python pipeline/scripts/backfill_data.py \\
        --bucket f1optimizer-data-lake \\
        [--skip-fastf1]          # skip FastF1 (takes hours)
        [--fastf1-only]          # only run FastF1 backfill
        [--dry-run]              # print what would be done, no writes
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
from google.cloud import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BASE_URL = "https://api.jolpi.ca/ergast/f1"
_MIN_REQUEST_INTERVAL = 1.0
_last_request_time: float = 0.0

# FastF1 missing rounds to backfill: {year: list of round numbers}
# Based on audit of raw/telemetry/ contents (2026-03-19):
#   2022: rounds 1-3 present, 4-22 missing
#   2023: all rounds present (complete) — omitted
#   2024: round 1 present, 2-24 missing
#   2025: rounds 1-16 present, 17-24 missing (2025 season complete)
FASTF1_MISSING: Dict[int, List[int]] = {
    2022: list(range(4, 23)),   # rounds 4-22
    2024: list(range(2, 25)),   # rounds 2-24
    2025: list(range(17, 25)),  # rounds 17-24
}


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _rate_limited_get(url: str, timeout: int = 30) -> requests.Response:
    global _last_request_time
    elapsed = time.monotonic() - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    resp = requests.get(url, timeout=timeout)
    _last_request_time = time.monotonic()
    return resp


def _fetch_json(url: str, retries: int = 5) -> Dict[str, Any]:
    for attempt in range(retries):
        try:
            logger.debug("GET %s", url)
            resp = _rate_limited_get(url)
            if resp.status_code == 429:
                logger.warning("Rate limited (429) — sleeping 60s")
                time.sleep(60)
                resp = _rate_limited_get(url)
            resp.raise_for_status()
            return resp.json()
        except (requests.ConnectionError, requests.Timeout) as exc:
            wait = 2 ** attempt
            logger.warning("Request failed (%s), retry %d/%d in %ds", exc, attempt + 1, retries, wait)
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch {url} after {retries} retries")


def _paginate(base_url: str, limit: int = 1000) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    offset = 0
    while True:
        url = f"{base_url}?limit={limit}&offset={offset}"
        data = _fetch_json(url)
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
        offset += len(rows)
        if offset >= total or not rows:
            break
    return results


# ---------------------------------------------------------------------------
# GCS helpers
# ---------------------------------------------------------------------------

def _gcs_download_csv(bucket: storage.Bucket, blob_name: str) -> Optional[pd.DataFrame]:
    blob = bucket.blob(blob_name)
    if not blob.exists():
        logger.warning("GCS blob not found: gs://%s/%s", bucket.name, blob_name)
        return None
    buf = io.BytesIO()
    blob.download_to_file(buf)
    buf.seek(0)
    return pd.read_csv(buf, low_memory=False)


def _gcs_upload_csv(df: pd.DataFrame, bucket: storage.Bucket, blob_name: str) -> None:
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    blob = bucket.blob(blob_name)
    blob.upload_from_file(buf, content_type="text/csv")
    logger.info("Uploaded gs://%s/%s (%d rows)", bucket.name, blob_name, len(df))


def _gcs_upload_parquet(df: pd.DataFrame, bucket: storage.Bucket, blob_name: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    buf.seek(0)
    blob = bucket.blob(blob_name)
    blob.upload_from_file(buf, content_type="application/octet-stream")
    logger.info("Uploaded gs://%s/%s (%d rows)", bucket.name, blob_name, len(df))


# ---------------------------------------------------------------------------
# Race results backfill
# ---------------------------------------------------------------------------

def _flatten_race_results(races: List[Dict[str, Any]]) -> pd.DataFrame:
    """Flatten Jolpica Races[] → one row per driver per race."""
    rows = []
    for race in races:
        season = int(race.get("season", 0))
        round_num = int(race.get("round", 0))
        race_name = race.get("raceName", "")
        circuit_id = race.get("Circuit", {}).get("circuitId", "")
        for result in race.get("Results", []):
            rows.append({
                "number": result.get("number"),
                "position": result.get("position"),
                "positionText": result.get("positionText"),
                "points": result.get("points"),
                "Driver": str(result.get("Driver", {})),
                "Constructor": str(result.get("Constructor", {})),
                "grid": result.get("grid"),
                "laps": result.get("laps"),
                "status": result.get("status"),
                "Time": str(result.get("Time", "")),
                "season": season,
                "round": round_num,
                "raceName": race_name,
                "circuitId": circuit_id,
                "FastestLap": str(result.get("FastestLap", "")),
            })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["number"] = pd.to_numeric(df["number"], errors="coerce")
        df["position"] = pd.to_numeric(df["position"], errors="coerce")
        df["points"] = pd.to_numeric(df["points"], errors="coerce")
        df["grid"] = pd.to_numeric(df["grid"], errors="coerce")
        df["laps"] = pd.to_numeric(df["laps"], errors="coerce")
    return df


def backfill_race_results(bucket: storage.Bucket, dry_run: bool = False) -> None:
    """Re-fetch complete race results for all seasons and overwrite GCS raw CSV."""
    logger.info("=== Backfilling race_results ===")

    # Determine all seasons
    seasons_data = _paginate(f"{BASE_URL}/seasons/")
    seasons = sorted(int(s["season"]) for s in seasons_data)
    logger.info("Fetching race results for %d seasons (%d–%d)", len(seasons), seasons[0], seasons[-1])

    all_frames: List[pd.DataFrame] = []
    for i, year in enumerate(seasons):
        logger.info("[%d/%d] Fetching %d...", i + 1, len(seasons), year)
        try:
            races = _paginate(f"{BASE_URL}/{year}/results/")
            if not races:
                logger.warning("  No races found for %d", year)
                continue
            df = _flatten_race_results(races)
            logger.info("  %d: %d races, %d result rows", year, len(races), len(df))
            all_frames.append(df)
        except Exception:
            logger.exception("  Failed to fetch results for %d", year)

    if not all_frames:
        logger.error("No race results fetched — aborting")
        return

    combined = pd.concat(all_frames, ignore_index=True)
    logger.info("Total race result rows: %d across %d seasons", len(combined), combined["season"].nunique())

    if not dry_run:
        _gcs_upload_csv(combined, bucket, "raw/race_results.csv")
        _gcs_upload_parquet(combined, bucket, "processed/race_results.parquet")
        logger.info("race_results backfill complete")
    else:
        logger.info("[dry-run] Would upload %d rows to race_results.csv + race_results.parquet", len(combined))


# ---------------------------------------------------------------------------
# Lap times 2023 round 23 backfill
# ---------------------------------------------------------------------------

def _fetch_lap_times_round(year: int, round_num: int) -> pd.DataFrame:
    """Fetch lap times for one round from Jolpica, return as DataFrame."""
    url = f"{BASE_URL}/{year}/{round_num}/laps/"
    laps = _paginate(url, limit=100)
    rows = []
    for lap in laps:
        lap_num = lap.get("number")
        for timing in lap.get("Timings", []):
            rows.append({
                "driverId": timing.get("driverId"),
                "position": timing.get("position"),
                "time": timing.get("time"),
                "season": year,
                "round": round_num,
                "lap": lap_num,
            })
    return pd.DataFrame(rows)


def backfill_lap_times_2023(bucket: storage.Bucket, dry_run: bool = False) -> None:
    """Append missing round 23 to laps_2023.csv and regenerate lap_times.parquet."""
    logger.info("=== Backfilling lap_times 2023 round 23 ===")

    # Download existing 2023 laps
    existing = _gcs_download_csv(bucket, "raw/laps_2023.csv")
    if existing is None:
        logger.error("raw/laps_2023.csv not found in GCS — aborting")
        return

    existing_rounds = sorted(existing["round"].unique()) if "round" in existing.columns else []
    logger.info("Existing rounds in laps_2023.csv: %s", existing_rounds)

    # Check which rounds are missing
    # 2023 had 23 rounds
    all_rounds = set(range(1, 24))
    present = set(existing_rounds)
    missing = sorted(all_rounds - present)
    if not missing:
        logger.info("laps_2023.csv already has all 23 rounds — nothing to do")
        return

    logger.info("Missing rounds in 2023: %s", missing)

    new_frames = [existing]
    for rnd in missing:
        logger.info("Fetching 2023 round %d...", rnd)
        try:
            df = _fetch_lap_times_round(2023, rnd)
            logger.info("  Round %d: %d lap rows", rnd, len(df))
            new_frames.append(df)
        except Exception:
            logger.exception("  Failed to fetch 2023 round %d", rnd)

    combined = pd.concat(new_frames, ignore_index=True)
    combined = combined.sort_values(["round", "lap"]).reset_index(drop=True)

    if not dry_run:
        _gcs_upload_csv(combined, bucket, "raw/laps_2023.csv")

        # Regenerate laps_all.parquet from all years
        logger.info("Regenerating laps_all.parquet...")
        _regenerate_laps_all(bucket)
        logger.info("lap_times 2023 backfill complete")
    else:
        logger.info("[dry-run] Would upload %d rows to laps_2023.csv + regenerate lap_times parquet", len(combined))


def _regenerate_laps_all(bucket: storage.Bucket) -> None:
    """Rebuild lap_times.parquet and laps_all.parquet from all raw laps_YYYY.csv files."""
    logger.info("Downloading all laps_YYYY.csv from GCS...")
    frames: List[pd.DataFrame] = []
    blobs = list(bucket.list_blobs(prefix="raw/laps_"))
    for blob in sorted(blobs, key=lambda b: b.name):
        if not blob.name.endswith(".csv"):
            continue
        logger.info("  Reading %s...", blob.name)
        buf = io.BytesIO()
        blob.download_to_file(buf)
        buf.seek(0)
        frames.append(pd.read_csv(buf, low_memory=False))

    if not frames:
        logger.error("No laps_YYYY.csv files found — aborting laps_all rebuild")
        return

    combined = pd.concat(frames, ignore_index=True)
    logger.info("laps_all: %d rows total", len(combined))
    _gcs_upload_parquet(combined, bucket, "processed/laps_all.parquet")
    _gcs_upload_parquet(combined, bucket, "processed/lap_times.parquet")


# ---------------------------------------------------------------------------
# FastF1 backfill
# ---------------------------------------------------------------------------

def backfill_fastf1(bucket: storage.Bucket, dry_run: bool = False) -> None:
    """Re-fetch missing FastF1 rounds and update year-level CSVs in GCS."""
    try:
        import fastf1  # type: ignore[import]
    except ImportError:
        logger.error("fastf1 not installed. Run: pip install fastf1")
        return

    cache_dir = Path("/tmp/fastf1_cache")
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))

    for year, missing_rounds in sorted(FASTF1_MISSING.items()):
        logger.info("=== FastF1 backfill: %d — %d rounds ===", year, len(missing_rounds))

        # Download existing year CSV files from GCS
        existing_laps = _gcs_download_csv(bucket, f"raw/telemetry/laps_{year}.csv")
        existing_tel = _gcs_download_csv(bucket, f"raw/telemetry/telemetry_{year}.csv")

        laps_frames: List[pd.DataFrame] = [existing_laps] if existing_laps is not None else []
        tel_frames: List[pd.DataFrame] = [existing_tel] if existing_tel is not None else []

        # Filter to only truly missing rounds
        if existing_laps is not None and "round" in existing_laps.columns:
            already_have = set(existing_laps["round"].unique())
            rounds_to_fetch = [r for r in missing_rounds if r not in already_have]
        else:
            rounds_to_fetch = missing_rounds

        if not rounds_to_fetch:
            logger.info("  %d: all rounds already present — skipping", year)
            continue

        logger.info("  %d: fetching rounds %s", year, rounds_to_fetch)

        for rnd in rounds_to_fetch:
            logger.info("  %d round %d...", year, rnd)
            try:
                session = fastf1.get_session(year, rnd, "R")
                session.load(telemetry=True, laps=True, weather=False)

                # Laps
                laps_df = session.laps.copy()
                laps_df["season"] = year
                laps_df["round"] = rnd
                laps_df["raceName"] = session.event["EventName"]
                for col in laps_df.select_dtypes(include=["timedelta64[ns]"]).columns:
                    laps_df[col] = laps_df[col].dt.total_seconds()
                keep_laps = [c for c in [
                    "Driver", "LapNumber", "LapTime", "Sector1Time", "Sector2Time",
                    "Sector3Time", "Compound", "TyreLife", "Stint", "FreshTyre",
                    "SpeedI1", "SpeedI2", "SpeedFL", "SpeedST", "season", "round", "raceName"
                ] if c in laps_df.columns]
                laps_frames.append(laps_df[keep_laps])

                # Telemetry (aggregated per lap per driver for size)
                tel_rows = []
                tel_rows.append({
                    "season": year,
                    "round": rnd,
                    "Driver": lap["Driver"],
                    "LapNumber": lap["LapNumber"],
                    # Throttle
                    "mean_throttle": tel["Throttle"].mean() if "Throttle" in tel.columns else None,
                    "std_throttle": tel["Throttle"].std() if "Throttle" in tel.columns else None,
                    # Brake
                    "mean_brake": tel["Brake"].mean() if "Brake" in tel.columns else None,
                    "std_brake": tel["Brake"].std() if "Brake" in tel.columns else None,
                    # Speed
                    "mean_speed": tel["Speed"].mean() if "Speed" in tel.columns else None,
                    "max_speed": tel["Speed"].max() if "Speed" in tel.columns else None,
                    # RPM — engine load proxy
                    "mean_rpm": tel["RPM"].mean() if "RPM" in tel.columns else None,
                    "max_rpm": tel["RPM"].max() if "RPM" in tel.columns else None,
                    # Gear — driving style/circuit character
                    "mean_gear": tel["nGear"].mean() if "nGear" in tel.columns else None,
                    "mode_gear": tel["nGear"].mode()[0] if "nGear" in tel.columns and not tel["nGear"].empty else None,
                    # DRS — percentage of lap with DRS open
                    "drs_usage_pct": (tel["DRS"].gt(0).sum() / len(tel) * 100) if "DRS" in tel.columns else None,
                    # Distance
                    "lap_distance": tel["Distance"].max() if "Distance" in tel.columns else None,
                })
                for _, lap in session.laps.iterlaps():
                    try:
                        tel = lap.get_telemetry()
                        if tel is not None and not tel.empty:
                            tel_rows.append({
                                "season": year,
                                "round": rnd,
                                "Driver": lap["Driver"],
                                "LapNumber": lap["LapNumber"],
                                "mean_throttle": tel["Throttle"].mean() if "Throttle" in tel.columns else None,
                                "std_throttle": tel["Throttle"].std() if "Throttle" in tel.columns else None,
                                "mean_brake": tel["Brake"].mean() if "Brake" in tel.columns else None,
                                "std_brake": tel["Brake"].std() if "Brake" in tel.columns else None,
                                "mean_speed": tel["Speed"].mean() if "Speed" in tel.columns else None,
                                "max_speed": tel["Speed"].max() if "Speed" in tel.columns else None,
                            })
                    except Exception:
                        pass
                if tel_rows:
                    tel_frames.append(pd.DataFrame(tel_rows))

                logger.info("    %d round %d: %d laps, %d telemetry rows", year, rnd, len(laps_df), len(tel_rows))

            except Exception:
                logger.exception("    Failed %d round %d — skipping", year, rnd)

        if dry_run:
            logger.info("[dry-run] Would update telemetry/laps_%d.csv + telemetry/telemetry_%d.csv", year, year)
            continue

        # Upload updated year files
        if laps_frames:
            combined_laps = pd.concat(laps_frames, ignore_index=True)
            _gcs_upload_csv(combined_laps, bucket, f"raw/telemetry/laps_{year}.csv")

        if tel_frames:
            combined_tel = pd.concat(tel_frames, ignore_index=True)
            _gcs_upload_csv(combined_tel, bucket, f"raw/telemetry/telemetry_{year}.csv")

    if not dry_run:
        logger.info("Regenerating fastf1_laps.parquet and fastf1_telemetry.parquet...")
        _regenerate_fastf1_parquets(bucket)


def _regenerate_fastf1_parquets(bucket: storage.Bucket) -> None:
    """Rebuild fastf1_laps.parquet and fastf1_telemetry.parquet from year CSVs."""
    for prefix, parquet_name in [("laps_", "fastf1_laps"), ("telemetry_", "fastf1_telemetry")]:
        frames: List[pd.DataFrame] = []
        blobs = list(bucket.list_blobs(prefix="raw/telemetry/"))
        for blob in sorted(blobs, key=lambda b: b.name):
            fname = blob.name.split("/")[-1]
            if not fname.startswith(prefix) or not fname.endswith(".csv"):
                continue
            logger.info("  Reading %s...", blob.name)
            buf = io.BytesIO()
            blob.download_to_file(buf)
            buf.seek(0)
            frames.append(pd.read_csv(buf, low_memory=False))

        if frames:
            combined = pd.concat(frames, ignore_index=True)
            logger.info("%s: %d rows total", parquet_name, len(combined))
            _gcs_upload_parquet(combined, bucket, f"processed/{parquet_name}.parquet")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missing F1 data in GCS")
    parser.add_argument("--bucket", default="f1optimizer-data-lake", help="GCS bucket name")
    parser.add_argument("--skip-fastf1", action="store_true", help="Skip FastF1 backfill (takes hours)")
    parser.add_argument("--fastf1-only", action="store_true", help="Only run FastF1 backfill")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done, no writes")
    args = parser.parse_args()

    client = storage.Client()
    bucket = client.bucket(args.bucket)

    if args.dry_run:
        logger.info("DRY RUN — no changes will be made")

    if not args.fastf1_only:
        backfill_race_results(bucket, dry_run=args.dry_run)

    if not args.skip_fastf1:
        backfill_fastf1(bucket, dry_run=args.dry_run)

    logger.info("=== Backfill complete ===")


if __name__ == "__main__":
    main()
