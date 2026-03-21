"""
aggregate_telemetry.py — Aggregate raw telemetry to lap-level features.
Reads from:
  1. gs://f1optimizer-data-lake/telemetry/{year}/{event}/R.parquet (new ingest)
  2. gs://f1optimizer-data-lake/raw/telemetry/telemetry_YYYY.csv (old CSVs, fallback)
Output: gs://f1optimizer-data-lake/processed/fastf1_telemetry.parquet
        gs://f1optimizer-data-lake/processed/fastf1_laps.parquet
"""
import io
import logging
import pandas as pd
import numpy as np
from google.cloud import storage
import gcsfs
import fastf1

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BUCKET = "f1optimizer-data-lake"
OUTPUT_COLS = [
    'season', 'round', 'Driver', 'LapNumber',
    'mean_throttle', 'std_throttle', 'mean_brake', 'std_brake',
    'mean_speed', 'max_speed', 'mean_rpm', 'max_rpm',
    'mean_gear', 'drs_usage_pct', 'lap_distance',
]


def aggregate_raw(df: pd.DataFrame, year: int, round_num: int) -> pd.DataFrame:
    """Aggregate raw 10Hz telemetry to lap-level."""
    if 'LapNumber' not in df.columns or 'Driver' not in df.columns:
        return pd.DataFrame()

    df['season'] = year
    df['round'] = round_num

    group_cols = ['season', 'round', 'Driver', 'LapNumber']
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

    return df.groupby(group_cols).agg(**agg_dict).reset_index()


def process_old_aggregated(df: pd.DataFrame) -> pd.DataFrame:
    """Handle already-aggregated old schema — add null columns for new features."""
    if 'driver' in df.columns and 'Driver' not in df.columns:
        df = df.rename(columns={'driver': 'Driver'})
    if 'year' in df.columns and 'season' not in df.columns:
        df = df.rename(columns={'year': 'season'})
    for col in ['mean_rpm', 'max_rpm', 'mean_gear', 'drs_usage_pct', 'lap_distance']:
        if col not in df.columns:
            df[col] = np.nan
    return df[[c for c in OUTPUT_COLS if c in df.columns]]


def read_new_telemetry_year(fs: gcsfs.GCSFileSystem, year: int) -> pd.DataFrame:
    """Read Race sessions from new telemetry/ path for a given year."""
    frames = []
    try:
        schedule = fastf1.get_event_schedule(year, include_testing=False)
        name_to_round = dict(zip(schedule['EventName'], schedule['RoundNumber']))
    except Exception as e:
        logger.warning("Could not get schedule for %d: %s", year, e)
        return pd.DataFrame()

    events = fs.glob(f"gs://{BUCKET}/telemetry/{year}/*/R.parquet")
    logger.info("Year %d: found %d race sessions in new path", year, len(events))

    for f in events:
        try:
            event_name = f.split(f'/{year}/')[1].split('/')[0]
            round_num = name_to_round.get(event_name)
            if round_num is None:
                logger.warning("  Could not map round for %s %d", event_name, year)
                continue

            df = pd.read_parquet(f"gs://{f}")
            agg = aggregate_raw(df, year, int(round_num))
            if len(agg) > 0:
                frames.append(agg)
                logger.info("  %d %s (round %d): %d lap rows", year, event_name, round_num, len(agg))
        except Exception as e:
            logger.error("  Failed %s: %s", f, e)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def read_old_csv_year(bucket: storage.Bucket, year: int) -> pd.DataFrame:
    """Read old aggregated CSV for a year."""
    blob = bucket.blob(f'raw/telemetry/telemetry_{year}.csv')
    if not blob.exists():
        return pd.DataFrame()
    buf = io.BytesIO()
    blob.download_to_file(buf)
    buf.seek(0)
    df = pd.read_csv(buf, low_memory=False)
    return process_old_aggregated(df)


def read_new_laps_year(fs: gcsfs.GCSFileSystem, year: int) -> pd.DataFrame:
    """Read lap data from Race sessions in new telemetry path."""
    import fastf1 as ff1
    frames = []
    try:
        schedule = ff1.get_event_schedule(year, include_testing=False)
        name_to_round = dict(zip(schedule['EventName'], schedule['RoundNumber']))
    except Exception as e:
        logger.warning("Could not get schedule for %d: %s", year, e)
        return pd.DataFrame()

    # Laps are embedded in the parquet alongside telemetry
    # We need to load from FastF1 cache instead
    cache_dir = "/tmp/f1_cache"
    ff1.Cache.enable_cache(cache_dir)

    events = fs.glob(f"gs://{BUCKET}/telemetry/{year}/*/R.parquet")
    for f in events:
        try:
            event_name = f.split(f'/{year}/')[1].split('/')[0]
            round_num = name_to_round.get(event_name)
            if round_num is None:
                continue
            session = ff1.get_session(year, event_name, 'R')
            session.load(telemetry=False, laps=True, weather=False, messages=False)
            laps = session.laps.copy()
            laps['season'] = year
            laps['round'] = int(round_num)
            laps['raceName'] = event_name
            for col in laps.select_dtypes(include=["timedelta64[ns]"]).columns:
                laps[col] = laps[col].dt.total_seconds()
            keep = [c for c in [
                'Driver', 'LapNumber', 'LapTime', 'Sector1Time', 'Sector2Time',
                'Sector3Time', 'Compound', 'TyreLife', 'Stint', 'FreshTyre',
                'SpeedI1', 'SpeedI2', 'SpeedFL', 'SpeedST', 'season', 'round', 'raceName'
            ] if c in laps.columns]
            frames.append(laps[keep])
            logger.info("  Laps %d %s: %d rows", year, event_name, len(laps))
        except Exception as e:
            logger.error("  Laps failed %s: %s", f, e)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def main():
    client = storage.Client()
    bucket = client.bucket(BUCKET)
    fs = gcsfs.GCSFileSystem()

    tel_frames = []
    laps_frames = []

    # Years with new ingest data
    new_years = [2022, 2023, 2024, 2025]
    # Years with old CSV data only
    old_years = [2018, 2019, 2020, 2021]

    # Read new telemetry
    for year in new_years:
        events = fs.glob(f"gs://{BUCKET}/telemetry/{year}/*/R.parquet")
        if not events:
            logger.info("Year %d: no race sessions in new path, falling back to CSV", year)
            df = read_old_csv_year(bucket, year)
            if len(df) > 0:
                tel_frames.append(df)
            continue

        logger.info("Processing year %d from new path (%d race sessions)...", year, len(events))
        tel_df = read_new_telemetry_year(fs, year)
        if len(tel_df) > 0:
            tel_frames.append(tel_df)
            logger.info("Year %d telemetry: %d rows", year, len(tel_df))

        laps_df = read_new_laps_year(fs, year)
        if len(laps_df) > 0:
            laps_frames.append(laps_df)
            logger.info("Year %d laps: %d rows", year, len(laps_df))

    # Read old CSVs
    for year in old_years:
        logger.info("Processing year %d from old CSV...", year)
        df = read_old_csv_year(bucket, year)
        if len(df) > 0:
            tel_frames.append(df)
            logger.info("Year %d telemetry: %d rows", year, len(df))

        # Old laps from fastf1_laps parquet
        old_laps = pd.read_parquet(f"gs://{BUCKET}/processed/fastf1_laps.parquet")
        old_laps_year = old_laps[old_laps['season'] == year]
        if len(old_laps_year) > 0:
            laps_frames.append(old_laps_year)
            logger.info("Year %d laps from parquet: %d rows", year, len(old_laps_year))

    # Combine telemetry
    if not tel_frames:
        logger.error("No telemetry data — aborting")
        return

    tel_combined = pd.concat(tel_frames, ignore_index=True)
    tel_combined['season'] = pd.to_numeric(tel_combined['season'], errors='coerce').astype('Int64')
    tel_combined = tel_combined.dropna(subset=['season', 'round', 'Driver', 'LapNumber'])
    tel_combined = tel_combined.drop_duplicates(subset=['season', 'round', 'Driver', 'LapNumber'], keep='first')

    logger.info("Final telemetry shape: %s", tel_combined.shape)
    logger.info("Seasons: %s", sorted(tel_combined['season'].dropna().unique()))
    logger.info("Rows per season:\n%s", tel_combined['season'].value_counts().sort_index())

    buf = io.BytesIO()
    tel_combined.to_parquet(buf, index=False, engine='pyarrow')
    buf.seek(0)
    bucket.blob('processed/fastf1_telemetry.parquet').upload_from_file(buf, content_type='application/octet-stream')
    logger.info("Uploaded fastf1_telemetry.parquet")

    # Combine laps
    if laps_frames:
        laps_combined = pd.concat(laps_frames, ignore_index=True)
        laps_combined = laps_combined.drop_duplicates(subset=['season', 'round', 'Driver', 'LapNumber'], keep='first')
        logger.info("Final laps shape: %s", laps_combined.shape)

        buf = io.BytesIO()
        laps_combined.to_parquet(buf, index=False, engine='pyarrow')
        buf.seek(0)
        bucket.blob('processed/fastf1_laps.parquet').upload_from_file(buf, content_type='application/octet-stream')
        logger.info("Uploaded fastf1_laps.parquet")

    logger.info("Done!")


if __name__ == "__main__":
    main()