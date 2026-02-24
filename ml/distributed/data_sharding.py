"""
Data sharding for distributed F1 training on Vertex AI.

Splits Cloud SQL race/lap data across N workers by season and race.
Each worker is assigned a disjoint set of race_ids.
Sharded data is written to GCS for fast worker access:
  gs://f1optimizer-training/shards/worker_{n}/

Workers read their shard at training start — no direct Cloud SQL access
during the hot training loop.

Usage (inside a Vertex AI training container):
    worker_index = int(os.environ.get("CLUSTER_SPEC_TASK_INDEX", 0))
    num_workers  = int(os.environ.get("CLUSTER_SPEC_NUM_WORKERS", 1))
    shards = DataSharding(num_workers=num_workers)
    race_ids = shards.get_worker_race_ids(worker_index)
    dataset  = shards.load_shard_from_gcs(worker_index)
"""

from __future__ import annotations

import json
import logging
import os

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
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "gs://f1optimizer-training").lstrip(
    "gs://"
)


class DataSharding:
    """Shards Cloud SQL F1 data across Vertex AI training workers."""

    def __init__(self, num_workers: int = 4) -> None:
        self.num_workers = num_workers
        self._connector: Connector | None = None

    # ── Cloud SQL connection ──────────────────────────────────────────────────

    def _get_connection(self):
        """Open a pg8000 connection via Cloud SQL Python Connector (ADC)."""
        if self._connector is None:
            self._connector = Connector()
        return self._connector.connect(
            INSTANCE_CONNECTION_NAME,
            "pg8000",
            user=DB_USER,
            password=DB_PASSWORD,
            db=DB_NAME,
        )

    def _fetch_all_race_ids(self) -> list[int]:
        """Return all race_ids from Cloud SQL, ordered by year and round."""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT race_id FROM races ORDER BY year ASC, round ASC")
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        finally:
            conn.close()

    # ── Shard assignment ──────────────────────────────────────────────────────

    def get_worker_race_ids(self, worker_index: int) -> list[int]:
        """
        Assign a disjoint slice of race_ids to `worker_index`.
        Handles uneven shards by distributing remainders to lower-index workers.
        """
        all_ids = self._fetch_all_race_ids()
        total = len(all_ids)
        base_size = total // self.num_workers
        remainder = total % self.num_workers

        start = worker_index * base_size + min(worker_index, remainder)
        end = start + base_size + (1 if worker_index < remainder else 0)

        assigned = all_ids[start:end]
        logger.info(
            "Worker %d/%d assigned %d races (ids %s … %s)",
            worker_index,
            self.num_workers,
            len(assigned),
            assigned[0] if assigned else "—",
            assigned[-1] if assigned else "—",
        )
        return assigned

    # ── Load shard from Cloud SQL → GCS ──────────────────────────────────────

    def write_shard_to_gcs(self, worker_index: int) -> str:
        """
        Load this worker's race data from Cloud SQL and write as Parquet to GCS.
        Returns the GCS URI of the written shard.
        Intended to run in a Cloud Run Job before training starts.
        """
        race_ids = self.get_worker_race_ids(worker_index)
        if not race_ids:
            logger.warning("Worker %d has no races assigned.", worker_index)
            return ""

        placeholders = ",".join(["%s"] * len(race_ids))
        query = f"""
            SELECT
                lf.race_id,
                lf.driver_id,
                lf.lap_number,
                lf.lap_time_ms,
                lf.tire_compound,
                lf.tire_age_laps,
                lf.gap_to_leader_ms,
                lf.gap_to_car_ahead_ms,
                lf.pit_stop_flag,
                lf.position,
                r.year,
                r.circuit_id
            FROM lap_features lf
            JOIN races r USING (race_id)
            WHERE lf.race_id IN ({placeholders})
            ORDER BY lf.race_id, lf.driver_id, lf.lap_number
        """

        conn = self._get_connection()
        try:
            df = pd.read_sql_query(query, conn, params=race_ids)
        finally:
            conn.close()

        gcs_path = f"shards/worker_{worker_index}/data.parquet"
        bucket_name = TRAINING_BUCKET
        gcs_uri = f"gs://{bucket_name}/{gcs_path}"

        buffer = df.to_parquet(index=False)
        client = storage.Client(project=PROJECT_ID)
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_path)
        blob.upload_from_string(buffer, content_type="application/octet-stream")

        logger.info(
            "Worker %d shard written to %s (%d rows, %.1f MB)",
            worker_index,
            gcs_uri,
            len(df),
            len(buffer) / 1e6,
        )

        # Write a manifest so aggregator can discover shards
        manifest_path = f"shards/worker_{worker_index}/manifest.json"
        manifest = {
            "worker_index": worker_index,
            "num_workers": self.num_workers,
            "race_ids": race_ids,
            "row_count": len(df),
            "gcs_uri": gcs_uri,
        }
        bucket.blob(manifest_path).upload_from_string(
            json.dumps(manifest, indent=2), content_type="application/json"
        )

        return gcs_uri

    def load_shard_from_gcs(self, worker_index: int) -> pd.DataFrame:
        """
        Read this worker's Parquet shard from GCS into a DataFrame.
        Called inside the Vertex AI training container at job start.
        """
        gcs_uri = f"gs://{TRAINING_BUCKET}/shards/worker_{worker_index}/data.parquet"
        logger.info("Worker %d loading shard from %s", worker_index, gcs_uri)
        df = pd.read_parquet(gcs_uri)
        logger.info("Worker %d loaded %d rows", worker_index, len(df))
        return df

    def close(self) -> None:
        if self._connector is not None:
            self._connector.close()
            self._connector = None
