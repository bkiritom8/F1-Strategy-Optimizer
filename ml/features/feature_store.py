"""
Feature Store — Cloud SQL → GCS via ADC.

Loads feature sets by race_id, season, or driver from Cloud SQL.
Writes feature DataFrames to GCS as Parquet for fast training access.
NO hardcoded credentials — ADC only (Cloud SQL Python Connector).

Usage (inside Vertex AI Workbench or training container):
    fs = FeatureStore()
    df = fs.load_race_features(race_id=1120)
    df = fs.load_season_features(year=2023)
    df = fs.load_driver_features(driver_id="hamilton")
    uri = fs.write_to_gcs(df, "features/2023_season.parquet")
"""

from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd
from google.cloud import storage
from google.cloud.sql.connector import Connector

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
INSTANCE_CONNECTION_NAME = os.environ.get(
    "INSTANCE_CONNECTION_NAME", "f1optimizer:us-central1:f1-optimizer-dev"
)
DB_NAME = os.environ.get("DB_NAME", "f1_strategy")
DB_USER = os.environ.get("DB_USER", "f1_app")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "gs://f1optimizer-training")


class FeatureStore:
    """
    Thin wrapper around Cloud SQL that returns feature DataFrames.
    All reads go through Cloud SQL Python Connector with ADC — no passwords
    in code.
    """

    def __init__(self) -> None:
        self._connector = Connector()
        self._gcs_client = storage.Client(project=PROJECT_ID)

    def _conn(self):
        return self._connector.connect(
            INSTANCE_CONNECTION_NAME,
            "pg8000",
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
        )

    def _query(self, sql: str, params: Any = None) -> pd.DataFrame:
        conn = self._conn()
        try:
            return pd.read_sql_query(sql, conn, params=params)
        finally:
            conn.close()

    # ── Feature loading ───────────────────────────────────────────────────────

    def load_race_features(self, race_id: int) -> pd.DataFrame:
        """Load all lap features for a single race."""
        logger.info("FeatureStore: loading race_id=%d", race_id)
        df = self._query(
            """
            SELECT lf.*, r.year, r.circuit_id, r.race_name,
                   d.driver_ref, d.nationality
            FROM lap_features lf
            JOIN races r USING (race_id)
            JOIN drivers d USING (driver_id)
            WHERE lf.race_id = %s
            ORDER BY lf.driver_id, lf.lap_number
            """,
            params=(race_id,),
        )
        logger.info("FeatureStore: loaded %d rows for race_id=%d", len(df), race_id)
        return df

    def load_season_features(self, year: int) -> pd.DataFrame:
        """Load all lap features for a full season."""
        logger.info("FeatureStore: loading year=%d", year)
        df = self._query(
            """
            SELECT lf.*, r.year, r.circuit_id, r.race_name, r.round,
                   d.driver_ref, d.nationality
            FROM lap_features lf
            JOIN races r USING (race_id)
            JOIN drivers d USING (driver_id)
            WHERE r.year = %s
            ORDER BY r.round, lf.driver_id, lf.lap_number
            """,
            params=(year,),
        )
        logger.info(
            "FeatureStore: loaded %d rows for year=%d (%d races)",
            len(df),
            year,
            df["race_id"].nunique() if len(df) > 0 else 0,
        )
        return df

    def load_driver_features(self, driver_ref: str) -> pd.DataFrame:
        """Load all lap features for a specific driver across all seasons."""
        logger.info("FeatureStore: loading driver=%s", driver_ref)
        df = self._query(
            """
            SELECT lf.*, r.year, r.circuit_id, r.race_name,
                   d.driver_ref, d.nationality
            FROM lap_features lf
            JOIN races r USING (race_id)
            JOIN drivers d USING (driver_id)
            WHERE d.driver_ref = %s
            ORDER BY r.year, r.round, lf.lap_number
            """,
            params=(driver_ref,),
        )
        logger.info("FeatureStore: loaded %d rows for driver=%s", len(df), driver_ref)
        return df

    def load_telemetry_features(
        self, race_id: int, driver_id: int | None = None
    ) -> pd.DataFrame:
        """Load telemetry features (10Hz, 2018+) for a race."""
        sql = """
            SELECT tf.*, r.year, r.circuit_id
            FROM telemetry_features tf
            JOIN races r USING (race_id)
            WHERE tf.race_id = %s
        """
        params: tuple = (race_id,)
        if driver_id is not None:
            sql += " AND tf.driver_id = %s"
            params = (race_id, driver_id)
        sql += " ORDER BY tf.driver_id, tf.lap_number, tf.time_ms"
        return self._query(sql, params=params)

    def load_driver_profiles(self) -> pd.DataFrame:
        """Load driver profiles (aggregated per-driver statistics)."""
        return self._query("""
            SELECT dp.*, d.driver_ref, d.nationality
            FROM driver_profiles dp
            JOIN drivers d USING (driver_id)
            ORDER BY d.driver_ref
            """)

    def load_multi_season_features(
        self, years: list[int], include_telemetry: bool = False
    ) -> pd.DataFrame:
        """Load lap features for multiple seasons."""
        placeholders = ",".join(["%s"] * len(years))
        df = self._query(
            f"""
            SELECT lf.*, r.year, r.circuit_id, r.race_name, r.round,
                   d.driver_ref
            FROM lap_features lf
            JOIN races r USING (race_id)
            JOIN drivers d USING (driver_id)
            WHERE r.year IN ({placeholders})
            ORDER BY r.year, r.round, lf.driver_id, lf.lap_number
            """,
            params=tuple(years),
        )
        logger.info("FeatureStore: loaded %d rows for years=%s", len(df), years)
        return df

    # ── GCS write ─────────────────────────────────────────────────────────────

    def write_to_gcs(self, df: pd.DataFrame, gcs_path: str) -> str:
        """
        Write a DataFrame to GCS as Parquet.
        gcs_path: relative path under TRAINING_BUCKET, or full gs:// URI.
        Returns the full GCS URI.
        """
        if gcs_path.startswith("gs://"):
            bucket_name, blob_path = gcs_path.lstrip("gs://").split("/", 1)
        else:
            bucket_name = TRAINING_BUCKET.lstrip("gs://")
            blob_path = gcs_path

        gcs_uri = f"gs://{bucket_name}/{blob_path}"
        data = df.to_parquet(index=False)
        self._gcs_client.bucket(bucket_name).blob(blob_path).upload_from_string(
            data, content_type="application/octet-stream"
        )
        logger.info(
            "FeatureStore: wrote %d rows (%.1f MB) to %s",
            len(df),
            len(data) / 1e6,
            gcs_uri,
        )
        return gcs_uri

    def close(self) -> None:
        self._connector.close()

    def __enter__(self) -> "FeatureStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
