# Ingest Workers

This module handles data acquisition from various sources into the Google Cloud Storage data lake.

## Components

- `task.py`: The entrypoint that routes the sequence of tasks via `CLOUD_RUN_TASK_INDEX`.
- `fastf1_worker.py`: Fetches high-frequency telemetry data from FastF1 for seasons 2018–2025.
- `historical_worker.py`: Parses historical data (1950-2017) from the Jolpica API.
- `lap_times_worker.py`: Collects granular lap-by-lap timing arrays.
- `gap_worker.py`: Specifically targets missed records or interrupted ingest periods.
- `progress.py`: A GCS-backed state manager utilizing optimistic locking.
- `gcs_utils.py`: Google Cloud Storage upload and connectivity helpers.

## Running Workers

These Python tasks are dockerized and deployed as Cloud Run Jobs.
```bash
gcloud run jobs execute f1-ingest --region=us-central1 --project=f1optimizer
```
