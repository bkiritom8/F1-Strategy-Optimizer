"""
task.py — Cloud Run Jobs entry point.

Cloud Run sets CLOUD_RUN_TASK_INDEX (0-based) and GCS_BUCKET automatically.

  Task index 0-8  → FastF1 telemetry worker for year (2018 + index, i.e. 2018-2026)
  Task index 9    → Ergast/Jolpica historical worker  (1996-2017)
"""

from __future__ import annotations

import json
import logging
import os
import sys

from google.cloud import logging as cloud_logging, storage

from .fastf1_worker import run as run_fastf1
from .historical_worker import run as run_historical
from .progress import Progress

# ---------------------------------------------------------------------------
# Structured JSON logging → Cloud Logging picks it up automatically
# ---------------------------------------------------------------------------

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format=json.dumps(
        {
            "time": "%(asctime)s",
            "severity": "%(levelname)s",
            "logger": "%(name)s",
            "message": "%(message)s",
        }
    ),
)

# Also attach the Cloud Logging handler so logs appear in the GCP console
try:
    cloud_logging.Client().setup_logging(log_level=logging.INFO)
except Exception:
    pass  # falls back to stdout-only, which Cloud Run already captures

log = logging.getLogger(__name__)


def main() -> None:
    task_index = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    bucket_name = os.environ["GCS_BUCKET"]

    log.info("task starting  index=%d  bucket=%s", task_index, bucket_name)

    gcs_client = storage.Client()
    bucket = gcs_client.bucket(bucket_name)
    progress = Progress(bucket)

    if task_index < 9:
        year = 2018 + task_index
        run_fastf1(year, task_index, bucket, progress)
    elif task_index == 9:
        run_historical(task_index, bucket, progress)
    else:
        log.error("unexpected task index: %d", task_index)
        sys.exit(1)


if __name__ == "__main__":
    main()
