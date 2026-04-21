"""
Append-only JSONL logger to GCS + optional Cloud Monitoring metric publishing.

GCS paths:
    gs://f1optimizer-training/monitoring/drift_log.jsonl
    gs://f1optimizer-training/monitoring/accuracy_log.jsonl

Each line is a self-contained JSON object with a timestamp field added
automatically. Existing content is preserved on each append.

When publish_metrics=True, drift PSI and accuracy degradation are also written
as custom time-series to Cloud Monitoring so they can drive alert policies.
"""

from __future__ import annotations

import io
import json
import logging
import os
import time
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
        publish_metrics: bool = False,
    ) -> None:
        self._bucket_name = bucket
        self._project = project
        self._publish = publish_metrics
        self._client = storage.Client(project=project)

    # GCS JSONL helpers

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
        """Append a DriftReport to drift_log.jsonl and optionally publish to Cloud Monitoring."""
        self._append_jsonl("monitoring/drift_log.jsonl", report.as_dict())
        if self._publish:
            self._publish_drift(report)

    def log_accuracy(self, report: AccuracyReport) -> None:
        """Append an AccuracyReport to accuracy_log.jsonl and optionally publish to Cloud Monitoring."""
        self._append_jsonl("monitoring/accuracy_log.jsonl", report.as_dict())
        if self._publish:
            self._publish_accuracy(report)

    # Cloud Monitoring publishers

    def _write_time_series(
        self,
        metric_type: str,
        labels: dict[str, str],
        value: float,
        value_type: str = "double_value",
    ) -> None:
        """Write a single-point time series to Cloud Monitoring."""
        try:
            from google.cloud import monitoring_v3

            client = monitoring_v3.MetricServiceClient()
            project_name = f"projects/{self._project}"

            series = monitoring_v3.TimeSeries()
            series.metric.type = metric_type
            for k, v in labels.items():
                series.metric.labels[k] = v
            series.resource.type = "global"
            series.resource.labels["project_id"] = self._project

            now = time.time()
            seconds = int(now)
            nanos = int((now - seconds) * 10**9)
            interval = monitoring_v3.TimeInterval(
                {"end_time": {"seconds": seconds, "nanos": nanos}}
            )
            point = monitoring_v3.Point(
                {"interval": interval, "value": {value_type: value}}
            )
            series.points = [point]

            client.create_time_series(name=project_name, time_series=[series])
            logger.info(
                "monitoring_logger: published %s=%s labels=%s",
                metric_type,
                value,
                labels,
            )
        except Exception as exc:
            logger.warning(
                "monitoring_logger: failed to publish %s: %s", metric_type, exc
            )

    def _publish_drift(self, report: DriftReport) -> None:
        max_psi = max(report.feature_psi.values(), default=0.0)
        self._write_time_series(
            metric_type="custom.googleapis.com/f1/drift_psi",
            labels={"model_name": report.model_name, "status": report.overall_status},
            value=round(max_psi, 6),
        )

    def _publish_accuracy(self, report: AccuracyReport) -> None:
        max_degradation = max(report.degradation_pct.values(), default=0.0)
        self._write_time_series(
            metric_type="custom.googleapis.com/f1/accuracy_degradation_pct",
            labels={
                "model_name": report.model_name,
                "degraded": str(report.degraded).lower(),
            },
            value=round(max_degradation, 4),
        )

    def publish_retraining_triggered(self, reason: str = "drift_or_decay") -> None:
        """Publish a retraining_triggered event counter to Cloud Monitoring."""
        self._write_time_series(
            metric_type="custom.googleapis.com/f1/retraining_triggered",
            labels={"reason": reason},
            value=1.0,
        )
