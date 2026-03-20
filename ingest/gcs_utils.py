"""
gcs_utils.py — GCS upload helpers for ingest tasks.
"""

from __future__ import annotations

import io
import logging

import pandas as pd
from google.cloud import storage

log = logging.getLogger(__name__)


def upload_parquet(df: pd.DataFrame, bucket: storage.Bucket, blob_path: str) -> None:
    """Serialise *df* to Parquet in memory and upload to GCS."""
    buf = io.BytesIO()
    df.to_parquet(buf, index=False, engine="pyarrow")
    buf.seek(0)
    blob = bucket.blob(blob_path)
    blob.upload_from_file(buf, content_type="application/octet-stream")
    log.info("uploaded gs://%s/%s  (%d rows)", bucket.name, blob_path, len(df))


def upload_done_marker(bucket: storage.Bucket, task_id: int) -> None:
    """Write an empty completion marker for *task_id*."""
    blob = bucket.blob(f"status/task_{task_id}.done")
    blob.upload_from_string("", content_type="text/plain")
    log.info("completion marker uploaded: status/task_%d.done", task_id)


def blob_exists(bucket: storage.Bucket, path: str) -> bool:
    """Return True if *path* exists in *bucket*."""
    return bucket.blob(path).exists()
