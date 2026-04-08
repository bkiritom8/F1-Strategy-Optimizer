"""JSON report builder and GCS uploader for adversarial test results."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from google.cloud import storage

logger = logging.getLogger(__name__)

_GCS_BUCKET = "f1optimizer-training"
_GCS_PREFIX = "adversarial-reports"


def build_report(results: list[dict], model: str, run_id: str) -> dict:
    """Build the JSON report dict from per-prompt result dicts."""
    total = len(results)
    passed = sum(1 for r in results if r["verdict"] == "PASS")
    return {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "model": model,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "robustness_score": round(passed / total, 3) if total else 0.0,
        "results": results,
    }


def upload_to_gcs(report: dict, gcs_client: storage.Client) -> str:
    """Upload the report JSON to GCS. Returns the gs:// URI."""
    run_id = report["run_id"]
    blob_name = f"{_GCS_PREFIX}/{run_id}.json"
    bucket = gcs_client.bucket(_GCS_BUCKET)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(
        json.dumps(report, indent=2),
        content_type="application/json",
    )
    uri = f"gs://{_GCS_BUCKET}/{blob_name}"
    logger.info("Adversarial report uploaded to %s", uri)
    return uri
