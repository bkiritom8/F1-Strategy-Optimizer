"""
csv_to_parquet.py — Convert F1 raw CSVs to Parquet and upload to GCS.

Usage:
    python pipeline/scripts/csv_to_parquet.py \\
        --input-dir raw/ \\
        --bucket f1optimizer-data-lake

Output (all uploaded to gs://<bucket>/processed/):
    laps_all.parquet            combined laps_YYYY.csv (1996-2025)
    telemetry_all.parquet       combined telemetry/telemetry_YYYY.csv
    telemetry_laps_all.parquet  combined telemetry/laps_YYYY.csv
    circuits.parquet
    drivers.parquet
    pit_stops.parquet
    race_results.parquet
    lap_times.parquet
    fastf1_laps.parquet
    fastf1_telemetry.parquet

Requirements: pandas, pyarrow, google-cloud-storage
"""

import argparse
import io
import logging
import re
from pathlib import Path
from typing import Dict, List

import pandas as pd
from google.cloud import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Matches pandas timedelta repr: "0 days 00:01:39.019000" or "-1 days +23:58:20"
_TIMEDELTA_RE = re.compile(r"^-?\d+ days [+\-]?\d{2}:\d{2}:\d{2}(\.\d+)?$")


def fix_timedelta_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Detect columns containing pandas timedelta strings and convert to float seconds.

    A column is considered a timedelta column if at least one value in a sample
    drawn from across the full column matches '0 days 00:01:39.019000'.
    Sampling across the column (not just head) catches columns where the first
    rows happen to be NaN or numeric while timedelta strings appear later.
    Non-parseable values become NaN.
    """
    for col in df.columns:
        if df[col].dtype != object:
            continue
        non_null = df[col].dropna()
        if non_null.empty:
            continue
        # Sample up to 50 values spread across the column to detect mixed columns
        step = max(1, len(non_null) // 50)
        sample = non_null.iloc[::step].head(50)
        if sample.astype(str).str.match(_TIMEDELTA_RE).any():
            logger.info("  Converting timedelta column '%s' to float seconds", col)
            df[col] = pd.to_timedelta(df[col], errors="coerce").dt.total_seconds()
    return df


# Individual CSV stems to convert one-to-one
INDIVIDUAL_FILES = [
    "circuits",
    "drivers",
    "pit_stops",
    "race_results",
    "lap_times",
    "fastf1_laps",
    "fastf1_telemetry",
]


def _upload_df(df: pd.DataFrame, bucket: storage.Bucket, blob_name: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    buf.seek(0)
    blob = bucket.blob(blob_name)
    blob.upload_from_file(buf, content_type="application/octet-stream")
    logger.info("  Uploaded gs://%s/%s", bucket.name, blob_name)


def _read_yearly_csvs(paths: List[Path], label: str) -> pd.DataFrame:
    """Read and concatenate year-stamped CSVs in chronological order."""
    paths = sorted(
        paths,
        key=lambda p: int(re.search(r"(\d{4})", p.name).group(1)),  # type: ignore[union-attr]
    )
    frames = []
    for p in paths:
        logger.info("  Reading %s (%.1f MB)", p.name, p.stat().st_size / 1e6)
        frames.append(pd.read_csv(p, low_memory=False))
    combined = pd.concat(frames, ignore_index=True)
    logger.info("  %s: %d rows from %d files", label, len(combined), len(paths))
    return combined


def convert_and_upload(input_dir: str, bucket_name: str) -> Dict[str, int]:
    """Convert all CSVs to Parquet and upload. Returns {name: row_count}."""
    base = Path(input_dir)
    if not base.is_dir():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    prefix = "processed"
    row_counts: Dict[str, int] = {}

    # 1. Combined: laps_YYYY.csv → laps_all.parquet
    laps_csvs = sorted(base.glob("laps_*.csv"))
    if laps_csvs:
        logger.info("Combining %d laps_YYYY.csv files...", len(laps_csvs))
        df = _read_yearly_csvs(laps_csvs, "laps_all")
        df = fix_timedelta_columns(df)
        _upload_df(df, bucket, f"{prefix}/laps_all.parquet")
        row_counts["laps_all"] = len(df)
    else:
        logger.warning("No laps_YYYY.csv files found in %s", base)

    # 2. Telemetry subdirectory
    telemetry_dir = base / "telemetry"
    if telemetry_dir.is_dir():
        # telemetry_YYYY.csv → telemetry_all.parquet
        tel_csvs = sorted(telemetry_dir.glob("telemetry_*.csv"))
        if tel_csvs:
            logger.info(
                "Combining %d telemetry/telemetry_YYYY.csv files...", len(tel_csvs)
            )
            df = _read_yearly_csvs(tel_csvs, "telemetry_all")
            df = fix_timedelta_columns(df)
            _upload_df(df, bucket, f"{prefix}/telemetry_all.parquet")
            row_counts["telemetry_all"] = len(df)

        # laps_YYYY.csv (inside telemetry/) → telemetry_laps_all.parquet
        tel_laps_csvs = sorted(telemetry_dir.glob("laps_*.csv"))
        if tel_laps_csvs:
            logger.info(
                "Combining %d telemetry/laps_YYYY.csv files...", len(tel_laps_csvs)
            )
            df = _read_yearly_csvs(tel_laps_csvs, "telemetry_laps_all")
            df = fix_timedelta_columns(df)
            _upload_df(df, bucket, f"{prefix}/telemetry_laps_all.parquet")
            row_counts["telemetry_laps_all"] = len(df)
    else:
        logger.warning("No telemetry/ subdirectory found in %s", base)

    # 3. Individual files
    for stem in INDIVIDUAL_FILES:
        csv_path = base / f"{stem}.csv"
        if not csv_path.exists():
            logger.warning("Not found, skipping: %s", csv_path)
            continue
        logger.info(
            "Converting %s (%.1f MB)...", csv_path.name, csv_path.stat().st_size / 1e6
        )
        df = pd.read_csv(csv_path, low_memory=False)
        logger.info("  %s: %d rows", stem, len(df))
        df = fix_timedelta_columns(df)
        _upload_df(df, bucket, f"{prefix}/{stem}.parquet")
        row_counts[stem] = len(df)

    return row_counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert F1 raw CSVs to Parquet and upload to GCS"
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Local directory containing raw CSV files (e.g. raw/)",
    )
    parser.add_argument(
        "--bucket",
        required=True,
        help="GCS bucket name (e.g. f1optimizer-data-lake)",
    )
    args = parser.parse_args()

    logger.info("Starting CSV -> Parquet conversion")
    logger.info("  input-dir : %s", args.input_dir)
    logger.info("  bucket    : gs://%s/processed/", args.bucket)

    row_counts = convert_and_upload(args.input_dir, args.bucket)

    logger.info("")
    logger.info("Row counts:")
    for name, count in sorted(row_counts.items()):
        logger.info("  %-30s %d", name, count)
    logger.info("Done.")


if __name__ == "__main__":
    main()
