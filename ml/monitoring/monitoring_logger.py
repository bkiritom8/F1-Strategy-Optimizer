"""
Append-only JSONL logger to GCS.

GCS paths:
    gs://f1optimizer-training/monitoring/drift_log.jsonl
    gs://f1optimizer-training/monitoring/accuracy_log.jsonl

Each line is a self-contained JSON object with a timestamp field added
automatically. Existing content is preserved on each append.
"""

from __future__ import annotations

import io
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from google.cloud import storage

from ml.monitoring.accuracy_tracker import AccuracyReport
from ml.monitoring.drift_detector import DriftReport

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "f1optimizer-training")


class MonitoringLogger:
    def __init__(
        self,
        bucket: str = TRAINING_BUCKET,
        project: str = PROJECT_ID,
    ) -> None:
        self._bucket_name = bucket
        self._client = storage.Client(project=project)

    def _append_jsonl(self, blob_path: str, row: dict[str, Any]) -> None:
        """Download existing JSONL, append one row, re-upload."""
        row["timestamp"] = datetime.now(timezone.utc).isoformat()
        blob = self._client.bucket(self._bucket_name).blob(blob_path)

        existing = b""
        if blob.exists():
            buf = io.BytesIO()
            blob.download_to_file(buf)
            existing = buf.getvalue()

        line = (json.dumps(row) + "\n").encode()
        blob.upload_from_string(existing + line, content_type="application/x-ndjson")
        logger.info(
            "monitoring_logger: appended to gs://%s/%s", self._bucket_name, blob_path
        )

    def log_drift(self, report: DriftReport) -> None:
        """Append a DriftReport to drift_log.jsonl."""
        self._append_jsonl("monitoring/drift_log.jsonl", report.as_dict())

    def log_accuracy(self, report: AccuracyReport) -> None:
        """Append an AccuracyReport to accuracy_log.jsonl."""
        self._append_jsonl("monitoring/accuracy_log.jsonl", report.as_dict())
