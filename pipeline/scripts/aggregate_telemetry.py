"""
aggregate_telemetry.py — Aggregate raw telemetry to lap-level features.
Reads from:
  1. gs://f1optimizer-data-lake/telemetry/{year}/{event}/R.parquet (new ingest)
  2. gs://f1optimizer-data-lake/raw/telemetry/telemetry_YYYY.csv (old CSVs, fallback)
Output: gs://f1optimizer-data-lake/processed/fastf1_telemetry.parquet
"""
import io
import logging
import pandas as pd
import numpy as np
from google.cloud import storage
import gcsfs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BUCKET = "f1optimizer-data-lake"
NEW_TELEMETRY_PREFIX = "telemetry/"
OLD_TELEMETRY_PREFIX = "raw/telemetry/telemetry_"

OUTPUT_COLS = [
    'season', 'round', 'Driver', 'LapNumber',
    'mean_throttle', 'std_throttle', 'mean_brake', 'std_brake',
    'mean_speed', 'max_speed', 'mean_rpm', 'max_rpm',
    'mean_gear', 'drs_usage_pct', 'lap_distance',
]


def is_raw_schema(df: pd.DataFrame) -> bool:
    return 'RPM' in df.columns and 'Throttle' in df.columns


def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    if 'driver' in df.columns and 'Driver' not in df.columns:
        df = df.rename(columns={'driver': 'Driver'})
    if 'year' in df.columns and 'season' not in df.columns:
        df = df.rename(columns={'year': 'season'})
    return df


def aggregate_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate raw 10Hz telemetry to lap-level."""
    df = normalize_cols(df)

    if 'LapNumber' not in df.columns:
        logger.warning("LapNumber missing — skipping")
        return pd.DataFrame()

    group_cols = [c for c in ['season', 'round', 'Driver', 'LapNumber'] if c in df.columns]
    if len(group_cols) < 4:
        logger.warning("Missing group cols: %s", set(['season','round','Driver','LapNumber']) - set(group_cols))
        return pd.DataFrame()

    agg_dict = {}
    if 'Throttle' in df.columns:
        agg_dict['mean_throttle'] = ('Throttle', 'mean')
        agg_dict['std_throttle'] = ('Throttle', 'std')
    if 'Brake' in df.columns:
        agg_dict['mean_brake'] = ('Brake', 'mean')
        agg_dict['std_brake'] = ('Brake', 'std')
    if 'Speed' in df.columns:
        agg_dict['mean_speed'] = ('Speed', 'mean')
        agg_dict['max_speed'] = ('Speed', 'max')
    if 'RPM' in df.columns:
        agg_dict['mean_rpm'] = ('RPM', 'mean')
        agg_dict['max_rpm'] = ('RPM', 'max')
    if 'nGear' in df.columns:
        agg_dict['mean_gear'] = ('nGear', 'mean')
    if 'DRS' in df.columns:
        agg_dict['drs_usage_pct'] = ('DRS', lambda x: (x > 0).sum() / len(x) * 100)
    if 'Distance' in df.columns:
        agg_dict['lap_distance'] = ('Distance', 'max')

    if not agg_dict:
        return pd.DataFrame()

    result = df.groupby(group_cols).agg(**agg_dict).reset_index()
    return result


def process_aggregated(df: pd.DataFrame) -> pd.DataFrame:
    """Handle already-aggregated old schema — add null columns for new features."""
    df = normalize_cols(df)
    for col in ['mean_rpm', 'max_rpm', 'mean_gear', 'drs_usage_pct', 'lap_distance']:
        if col not in df.columns:
            df[col] = np.nan
    return df[[c for c in OUTPUT_COLS if c in df.columns]]


def read_new_telemetry(bucket: storage.Bucket) -> list:
    """Read from new gs://telemetry/{year}/{event}/R.parquet path."""
    frames = []
    fs = gcsfs.GCSFileSystem()

    for year in range(2018, 2026):
        pattern = f"gs://{BUCKET}/telemetry/{year}/**/R.parquet"
        try:
            files = fs.glob(pattern)
            if not files:
                logger.info("No race files found for %d in new telemetry path", year)
                continue

            year_frames = []
            for f in files:
                try:
                    # Extract round from event name via schedule
                    event_name = f.split(f'/{year}/')[1].split('/')[0]
                    df = pd.read_parquet(f"gs://{f}")
                    df['season'] = year
                    # round will be mapped from event name below
                    df['event_name'] = event_name
                    year_frames.append(df)
                    logger.info("  Read %s: %d rows", f, len(df))
                except Exception as e:
                    logger.error("  Failed %s: %s", f, e)

            if year_frames:
                year_df = pd.concat(year_frames, ignore_index=True)
                # Map event_name to round number using FastF1 schedule
                try:
                    import fastf1
                    schedule = fastf1.get_event_schedule(year, include_testing=False)
                    name_to_round = dict(zip(schedule['EventName'], schedule['RoundNumber']))
                    year_df['round'] = year_df['event_name'].map(name_to_round)
                    year_df = year_df.dropna(subset=['round'])
                    year_df['round'] = year_df['round'].astype(int)
                except Exception as e:
                    logger.warning("Could not map rounds for %d: %s", year, e)

                processed = aggregate_raw(year_df) if is_raw_schema(year_df) else process_aggregated(year_df)
                if len(processed) > 0:
                    frames.append(processed)
                    logger.info("Year %d: %d output rows from new path", year, len(processed))

        except Exception as e:
            logger.error("Failed year %d new path: %s", year, e)

    return frames


def read_old_telemetry(bucket: storage.Bucket, years_covered: set) -> list:
    """Read from old raw/telemetry/telemetry_YYYY.csv for years not in new path."""
    frames = []
    blobs = sorted(bucket.list_blobs(prefix=OLD_TELEMETRY_PREFIX), key=lambda b: b.name)

    for blob in blobs:
        if not blob.name.endswith('.csv'):
            continue

        # Extract year from filename
        try:
            year = int(blob.name.split('telemetry_')[1].replace('.csv', ''))
        except Exception:
            continue

        if year in years_covered:
            logger.info("Skipping old CSV for %d — already have from new path", year)
            continue

        logger.info("Reading old CSV %s...", blob.name)
        buf = io.BytesIO()
        blob.download_to_file(buf)
        buf.seek(0)

        try:
            df = pd.read_csv(buf, low_memory=False)
            logger.info("  Shape: %s, Schema: %s", df.shape,
                       'raw_10hz' if is_raw_schema(df) else 'aggregated')

            processed = aggregate_raw(df) if is_raw_schema(df) else process_aggregated(df)

            if len(processed) > 0:
                frames.append(processed)
                logger.info("  Output rows: %d", len(processed))
            else:
                logger.warning("  No output rows for %s", blob.name)

        except Exception as e:
            logger.error("  Failed %s: %s", blob.name, e)

    return frames


def main():
    client = storage.Client()
    bucket = client.bucket(BUCKET)
    frames = []

    # 1. Try new telemetry path first
    logger.info("Reading from new telemetry path...")
    new_frames = read_new_telemetry(bucket)
    frames.extend(new_frames)

    # Track which years we got from new path
    years_covered = set()
    if new_frames:
        combined_new = pd.concat(new_frames, ignore_index=True)
        if 'season' in combined_new.columns:
            years_covered = set(combined_new['season'].dropna().astype(int).unique())
    logger.info("Years covered from new path: %s", sorted(years_covered))

    # 2. Fill remaining years from old CSV path
    logger.info("Reading from old CSV path for remaining years...")
    old_frames = read_old_telemetry(bucket, years_covered)
    frames.extend(old_frames)

    if not frames:
        logger.error("No data processed — aborting")
        return

    combined = pd.concat(frames, ignore_index=True)
    combined['season'] = pd.to_numeric(combined['season'], errors='coerce')
    combined = combined.dropna(subset=['season', 'round', 'Driver', 'LapNumber'])
    combined['season'] = combined['season'].astype(int)

    # Deduplicate — new path takes priority over old
    combined = combined.sort_values(['season', 'round', 'Driver', 'LapNumber'])
    combined = combined.drop_duplicates(subset=['season', 'round', 'Driver', 'LapNumber'], keep='first')

    logger.info("Final shape: %s", combined.shape)
    logger.info("Seasons: %s", sorted(combined['season'].unique()))
    logger.info("Columns: %s", combined.columns.tolist())
    logger.info("Rows per season:\n%s", combined['season'].value_counts().sort_index())

    buf = io.BytesIO()
    combined.to_parquet(buf, index=False, engine='pyarrow')
    buf.seek(0)
    bucket.blob('processed/fastf1_telemetry.parquet').upload_from_file(
        buf, content_type='application/octet-stream'
    )
    logger.info("Done — fastf1_telemetry.parquet uploaded (%d rows)", len(combined))


if __name__ == "__main__":
    main()