# Ingest Workers

Dockerized Cloud Run Jobs that acquire F1 data from Jolpica API and FastF1 into the GCS data lake (`gs://f1optimizer-data-lake`).

## Data Sources

| Source | Coverage | Worker |
|---|---|---|
| Jolpica API (`api.jolpi.ca/ergast/f1`) | Historical results 1950–2017 | `historical_worker.py` |
| FastF1 | High-frequency telemetry 2018–2026, 10Hz | `fastf1_worker.py` |
| Jolpica (lap times) | Granular lap-by-lap timing | `lap_times_worker.py` |

## Components

| File | Purpose |
|---|---|
| `task.py` | Entrypoint — routes to correct worker via `CLOUD_RUN_TASK_INDEX` |
| `fastf1_worker.py` | Fetches 10Hz telemetry for seasons 2018–2026 |
| `historical_worker.py` | Parses race results 1950–2017 from Jolpica |
| `lap_times_worker.py` | Collects granular lap-by-lap timing arrays |
| `gap_worker.py` | Targets missed records and interrupted ingest windows |
| `jolpica_client.py` | Typed Jolpica API client with retry and rate-limit handling |
| `telemetry_extractor.py` | FastF1 telemetry parsing utilities |
| `progress.py` | GCS-backed state manager with optimistic locking (prevents duplicate ingest) |
| `gcs_utils.py` | GCS upload helpers and connectivity checks |
| `http_utils.py` | Shared HTTP request utilities (retries, backoff) |

## Running

Deployed as Cloud Run Jobs — triggered manually or via CI/CD:

```bash
# Execute the full ingest job
gcloud run jobs execute f1-ingest --region=us-central1 --project=f1optimizer

# Target a specific task index (e.g. FastF1 worker = index 0)
gcloud run jobs execute f1-ingest \
  --region=us-central1 \
  --project=f1optimizer \
  --update-env-vars CLOUD_RUN_TASK_INDEX=0
```

## Docker

Built from `docker/Dockerfile.ingest`. Cloud Build builds `ingest:latest` automatically on push to `pipeline`.

```bash
docker build -f docker/Dockerfile.ingest -t ingest:latest .
```

## GCS Output

| Path | Contents |
|---|---|
| `gs://f1optimizer-data-lake/raw/` | Raw CSVs from Jolpica + FastF1 |
| `gs://f1optimizer-data-lake/processed/` | Parquet files (via `pipeline/scripts/csv_to_parquet.py`) |

---

**Note**: `progress.py` uses optimistic locking on a GCS state file to ensure idempotent ingest across retried or parallel Cloud Run task runs.
