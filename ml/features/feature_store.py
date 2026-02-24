"""
Feature Store — GCS Parquet reader with local + GCS cache.

Reads from gs://f1optimizer-data-lake/processed/ via FeaturePipeline.
Caches computed feature vectors:
  1. Local disk: /tmp/f1_cache/race_{race_id}.parquet
  2. GCS:        gs://f1optimizer-training/cache/race_{race_id}.parquet

Keyed by race_id string ("{season}_{round}").

Usage:
    fs = FeatureStore()
    df = fs.load_race_features("2024_1")
    df = fs.load_season_features(2023)
    df = fs.load_driver_features("lewis_hamilton")
    uri = fs.write_to_gcs(df, "features/enriched.parquet")
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd
from google.cloud import storage

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "gs://f1optimizer-training")
LOCAL_CACHE_DIR = os.environ.get("F1_LOCAL_CACHE", "/tmp/f1_cache")


class FeatureStore:
    """
    Cache layer over GCS Parquet feature data.

    On cache miss: computes features via FeaturePipeline, then saves to
    local disk and GCS so subsequent calls are instant.
    """

    GCS_CACHE_PREFIX = "cache"

    def __init__(
        self,
        project: str = PROJECT_ID,
        training_bucket: str = TRAINING_BUCKET,
        local_cache_dir: str = LOCAL_CACHE_DIR,
    ) -> None:
        self._project = project
        self._training_bucket_uri = training_bucket
        self._training_bucket_name = training_bucket.removeprefix("gs://")
        self._local_cache_dir = Path(local_cache_dir)
        self._local_cache_dir.mkdir(parents=True, exist_ok=True)
        self._gcs_client = storage.Client(project=project)
        self._pipeline: Any = None  # lazy import to avoid circular deps

    # ── Cache helpers ─────────────────────────────────────────────────────────

    def _local_path(self, race_id: str) -> Path:
        safe = race_id.replace("/", "_")
        return self._local_cache_dir / f"race_{safe}.parquet"

    def _gcs_blob_path(self, race_id: str) -> str:
        safe = race_id.replace("/", "_")
        return f"{self.GCS_CACHE_PREFIX}/race_{safe}.parquet"

    def _read_gcs_cache(self, race_id: str) -> pd.DataFrame | None:
        blob_path = self._gcs_blob_path(race_id)
        blob = self._gcs_client.bucket(self._training_bucket_name).blob(blob_path)
        try:
            if blob.exists():
                buf = io.BytesIO()
                blob.download_to_file(buf)
                buf.seek(0)
                logger.info("FeatureStore: GCS cache hit race_id=%s", race_id)
                return pd.read_parquet(buf)
        except Exception as exc:
            logger.debug("GCS cache read failed for %s: %s", race_id, exc)
        return None

    def _write_caches(self, race_id: str, df: pd.DataFrame) -> None:
        # Local
        local = self._local_path(race_id)
        try:
            df.to_parquet(local, index=False)
            logger.debug("FeatureStore: wrote local cache %s", local)
        except Exception as exc:
            logger.debug("Local cache write failed: %s", exc)
        # GCS
        try:
            buf = io.BytesIO()
            df.to_parquet(buf, index=False)
            buf.seek(0)
            self._gcs_client.bucket(self._training_bucket_name).blob(
                self._gcs_blob_path(race_id)
            ).upload_from_file(buf, content_type="application/octet-stream")
            logger.debug("FeatureStore: wrote GCS cache race_id=%s", race_id)
        except Exception as exc:
            logger.debug("GCS cache write failed: %s", exc)

    def _pipeline_instance(self):
        if self._pipeline is None:
            from ml.features.feature_pipeline import FeaturePipeline

            self._pipeline = FeaturePipeline(project=self._project)
        return self._pipeline

    # ── Public feature loading ─────────────────────────────────────────────

    def load_race_features(
        self, race_id: str, force_recompute: bool = False
    ) -> pd.DataFrame:
        """
        Load all drivers' state vectors for one race.

        Checks local cache → GCS cache → recomputes from source.
        """
        if not force_recompute:
            local = self._local_path(race_id)
            if local.exists():
                logger.info("FeatureStore: local cache hit race_id=%s", race_id)
                return pd.read_parquet(local)
            cached = self._read_gcs_cache(race_id)
            if cached is not None:
                try:
                    cached.to_parquet(local, index=False)
                except Exception:
                    pass
                return cached

        logger.info("FeatureStore: computing features for race_id=%s", race_id)
        df = self._pipeline_instance().build_race_features(race_id)
        if not df.empty:
            self._write_caches(race_id, df)
        return df

    def load_driver_features(
        self, driver_id: str, race_id: str, force_recompute: bool = False
    ) -> pd.DataFrame:
        """
        Load state vector for a single driver in a single race.

        Falls back to loading the full race and filtering if race is cached.
        """
        race_df = self.load_race_features(race_id, force_recompute=force_recompute)
        if race_df.empty or "driver_id" not in race_df.columns:
            return race_df
        return race_df[race_df["driver_id"] == driver_id].reset_index(drop=True)

    def load_season_features(self, year: int) -> pd.DataFrame:
        """Load features for an entire season (all races, all drivers)."""
        pipeline = self._pipeline_instance()
        races = pipeline.get_available_races()
        season_races = [r for r in races if r["season"] == year]
        if not season_races:
            logger.warning("No races found for season %d", year)
            return pd.DataFrame()

        frames = []
        for race in season_races:
            rid = race["race_id"]
            df = self.load_race_features(rid)
            if not df.empty:
                frames.append(df)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def load_multi_season_features(self, years: list[int]) -> pd.DataFrame:
        """Load features for multiple seasons."""
        frames = [self.load_season_features(y) for y in years]
        non_empty = [f for f in frames if not f.empty]
        if not non_empty:
            return pd.DataFrame()
        return pd.concat(non_empty, ignore_index=True)

    def load_driver_profiles(self) -> pd.DataFrame:
        """Return career stats for all drivers found in the dataset."""
        pipeline = self._pipeline_instance()
        laps = pipeline._laps()
        if "driverId" not in laps.columns:
            return pd.DataFrame()
        driver_ids = laps["driverId"].unique().tolist()
        rows = [pipeline.get_driver_history(d) for d in driver_ids]
        return pd.DataFrame(rows)

    # ── GCS write ─────────────────────────────────────────────────────────────

    def write_to_gcs(self, df: pd.DataFrame, gcs_path: str) -> str:
        """
        Write a DataFrame to GCS as Parquet.
        gcs_path: relative path under TRAINING_BUCKET, or full gs:// URI.
        Returns the full GCS URI.
        """
        if gcs_path.startswith("gs://"):
            remainder = gcs_path[5:]
            bucket_name, blob_path = remainder.split("/", 1)
        else:
            bucket_name = self._training_bucket_name
            blob_path = gcs_path

        gcs_uri = f"gs://{bucket_name}/{blob_path}"
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        data = buf.getvalue()
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

    # ── Context manager ────────────────────────────────────────────────────────

    def close(self) -> None:
        pass

    def __enter__(self) -> "FeatureStore":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
