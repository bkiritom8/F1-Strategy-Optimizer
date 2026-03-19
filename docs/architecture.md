# System Architecture and Deployment

**Last Updated**: 2026-03-19

## Overview

The F1 Strategy Optimizer is a production-grade system built on Google Cloud Platform, designed for real-time race strategy recommendations with <500ms P99 latency. Infrastructure is fully managed by Terraform and deployed to `us-central1`. All data lives in GCS — there is no operational database.

## High-Level Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                     INGEST LAYER                               │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────┐                                               │
│  │ Jolpica API│──────────┐                                    │
│  │ (1950-2026)│          │                                    │
│  └────────────┘          ▼                                    │
│                  Cloud Run Ingest Jobs (ingest/)               │
│  ┌────────────┐  9 parallel tasks (CLOUD_RUN_TASK_INDEX 0–8) │
│  │ FastF1 SDK │          │                                    │
│  │ (2018-2026)│  Task 0–7: fastf1_worker (one year each)     │
│  └────────────┘  Task 8:  historical_worker (1950–2017)       │
│                           │                                    │
│                           ▼                                    │
│         gs://f1optimizer-data-lake/raw/       (51 files, 6 GB)│
│         gs://f1optimizer-data-lake/telemetry/ (per-year)      │
│         gs://f1optimizer-data-lake/historical/(per-season)    │
│                           │                                    │
│              pipeline/scripts/csv_to_parquet.py               │
│                           ▼                                    │
│         gs://f1optimizer-data-lake/processed/ (10 files, 1 GB)│
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  STREAMING LAYER                               │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────┐         ┌─────────────────┐                  │
│  │ Live       │────────>│   Pub/Sub       │                  │
│  │ Telemetry  │         │ f1-telemetry-   │                  │
│  └────────────┘         │ stream-dev      │                  │
│                         └─────────────────┘                  │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                   ML LAYER                                     │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  Vertex AI KFP Pipeline (5-step DAG)                         │
│  ml/dag/f1_pipeline.py + ml/dag/pipeline_runner.py           │
│                                                                │
│  validate_data                                                 │
│    └─> feature_engineering                                     │
│          ├─> train_strategy    (XGBoost+LightGBM, 4×VM×T4)  │
│          └─> train_pit_stop   (LSTM+MirroredStrategy, 4×T4) │
│                ├─> eval_strategy  (parallel)                  │
│                └─> eval_pit_stop  (parallel)                  │
│                      └─> deploy                               │
│                                                                │
│  Artifacts promoted to: gs://f1optimizer-models/              │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  CI / CD LAYER                                 │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  GitHub push (pipeline branch)                                 │
│    ├─> GitHub Actions (.github/workflows/ci.yml)              │
│    │   lint / security / test / integration / docker-build /  │
│    │   terraform-validate / docs / all-checks-passed          │
│    └─> Cloud Build (cloudbuild.yaml)                          │
│         Build api:latest + ml:latest + airflow:latest          │
│         Push → us-central1-docker.pkg.dev/f1optimizer/        │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  SERVING LAYER                                 │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  FastAPI (Cloud Run) — f1-strategy-api-dev                    │
│  https://f1-strategy-api-dev-694267183904.us-central1.run.app │
│  <500ms P99                                                    │
│                                                                │
│  Loads models from gs://f1optimizer-models/ at startup.       │
│  Falls back to rule-based strategy if models not promoted.    │
│                                                                │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                MONITORING & OPERATIONS                         │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  Cloud Logging   │   Cloud Monitoring   │   Vertex AI Expts  │
│                                                                │
│  Alerting via f1-alerts-dev Pub/Sub topic                     │
└───────────────────────────────────────────────────────────────┘
```

## GCP Components

### Data Storage: GCS

All F1 data is stored in Google Cloud Storage.

| Bucket | Contents |
|---|---|
| `gs://f1optimizer-data-lake/raw/` | 51 source CSV files, 6.0 GB (Jolpica + FastF1) |
| `gs://f1optimizer-data-lake/processed/` | 10 Parquet files, 1.0 GB (ML-ready) |
| `gs://f1optimizer-data-lake/telemetry/` | Per-year FastF1 telemetry Parquet (ingest workers) |
| `gs://f1optimizer-data-lake/historical/` | Jolpica 1950–2017 per-season Parquet (ingest workers) |
| `gs://f1optimizer-data-lake/status/` | Ingest progress markers (`progress.json`, `task_N.done`) |
| `gs://f1optimizer-models/` | Promoted model artifacts |
| `gs://f1optimizer-training/` | Checkpoints, feature exports, pipeline artifacts |
| `gs://f1optimizer-pipeline-runs/` | KFP pipeline run roots |
| `gs://f1-optimizer-terraform-state/` | Terraform remote state |

### Processed Parquet Files

| File | Rows | Description |
|---|---|---|
| `laps_all.parquet` | 93,372 | Lap data 1996–2025 (Jolpica) |
| `telemetry_all.parquet` | 30,477,110 | FastF1 telemetry 2018–2025 |
| `telemetry_laps_all.parquet` | 92,242 | FastF1 session laps |
| `circuits.parquet` | 78 | Circuit master list |
| `drivers.parquet` | 100 | Driver master list |
| `pit_stops.parquet` | 11,077 | Pit stop records |
| `race_results.parquet` | 7,600 | Race results 1950–2026 |
| `lap_times.parquet` | 56,720 | Aggregated lap times |
| `fastf1_laps.parquet` | 92,242 | FastF1 lap data 2018–2026 |
| `fastf1_telemetry.parquet` | 90,302 | FastF1 telemetry summary |

### Reading Data

```python
import pandas as pd

# ADC credentials required — see DEV_SETUP.md §2
laps         = pd.read_parquet("gs://f1optimizer-data-lake/processed/laps_all.parquet")
telemetry    = pd.read_parquet("gs://f1optimizer-data-lake/processed/telemetry_all.parquet")
race_results = pd.read_parquet("gs://f1optimizer-data-lake/processed/race_results.parquet")
circuits     = pd.read_parquet("gs://f1optimizer-data-lake/processed/circuits.parquet")
```

### Ingest Layer: Cloud Run Jobs

Data ingestion runs as Cloud Run Jobs. The dispatcher `ingest/task.py` reads `CLOUD_RUN_TASK_INDEX` and routes to the appropriate worker:

| Task Index | Worker | Data |
|---|---|---|
| 0–7 | `fastf1_worker.py` | FastF1 telemetry for years 2018–2025 |
| 8 | `historical_worker.py` | Jolpica race results, lap times, pit stops 1950–2017 |

Supporting workers:
- `lap_times_worker.py` — Jolpica paginated lap times (rate-limited to 450 req/hr)
- `gap_worker.py` — Targeted backfill for 5 known data-gap scenarios

Design patterns:
- **Idempotent**: every worker checks GCS before downloading
- **Infinite backoff**: retries forever on transient errors (60s → 3600s cap)
- **Atomic progress**: `ingest/progress.py` uses GCS generation-match for lock-free concurrent writes
- **Structured logging**: JSON logs → Cloud Logging auto-parsed

### Data Sources

**Jolpica** (`ingest/historical_worker.py`, `ingest/lap_times_worker.py`):
- Base URL: `https://api.jolpi.ca/ergast/f1`
- Coverage: 1950–2026, 1,300+ races
- Rate limit: 500 req/hr (workers enforce ≥8s between requests)

**FastF1** (`ingest/fastf1_worker.py`):
- Coverage: 2018–2026, all session types (FP1–FP3, Q, Sprint, Race)
- 10 Hz telemetry: throttle, speed, brake, DRS, gear
- Session types adjust by format year (conventional / sprint_qualifying / sprint)

### Streaming Layer (Pub/Sub)

Pub/Sub topics provisioned for live telemetry and pipeline events:

| Topic | Purpose |
|---|---|
| `f1-race-events-dev` | Race status updates, pipeline triggers |
| `f1-telemetry-stream-dev` | Live car telemetry |
| `f1-predictions-dev` | Strategy outputs + pipeline stage status |
| `f1-alerts-dev` | System alerts and training job status |

### ML Layer: Vertex AI

**Training**: Vertex AI Custom Jobs via `ml/scripts/submit_training_job.sh`

**Pipeline**: Vertex AI Pipelines (KFP v2) — 5-step DAG:
```
validate_data
    └──> feature_engineering
             ├──> train_strategy_predictor   (XGBoost + LightGBM)
             └──> train_pit_stop_optimizer   (LSTM + MirroredStrategy)
                       ├──> evaluate_strategy
                       └──> evaluate_pit_stop
                                   └──> deploy
```

**Cluster configs** (`ml/distributed/cluster_config.py`):

| Profile | Machine | GPUs | Workers | Use Case |
|---|---|---|---|---|
| `VERTEX_T4` | `n1-standard-4` | 1× T4 | 1 | Default for experiments |
| `SINGLE_NODE_MULTI_GPU` | `n1-standard-16` | 4× T4 | 1 | Full PitStopOptimizer training |
| `MULTI_NODE_DATA_PARALLEL` | `n1-standard-8` | 1× T4 each | 4 | Large dataset sharding |
| `HYPERPARAMETER_SEARCH` | `n1-standard-4` | 0 | 8 | HP sweep via Vertex AI Vizier |
| `CPU_DISTRIBUTED` | `n1-highmem-16` | 0 | 8 | Feature engineering |

**Service Account**: `f1-training-dev@f1optimizer.iam.gserviceaccount.com`
**Roles**: `storage.objectAdmin`, `aiplatform.user`, `aiplatform.customCodeServiceAgent`

### Model Serving: FastAPI on Cloud Run

**Service**: `f1-strategy-api-dev` (`us-central1`)
**URL**: `https://f1-strategy-api-dev-694267183904.us-central1.run.app`
**Image**: `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api:latest`
**Resources**: min instances 0 (dev), max 3; 512 Mi memory, 1 vCPU

The API loads model artifacts from `gs://f1optimizer-models/` at startup and falls
back to rule-based strategy recommendations when promoted models are not yet available.

**Key endpoints**:
- `GET /health` — health check
- `POST /recommend` — strategy recommendations (<500ms P99)
- `GET /docs` — interactive API documentation

### CI/CD

**GitHub Actions** (`.github/workflows/ci.yml`) — triggered on push to `pipeline`, `main`, `develop`, `claude/**`:

| Job | What |
|---|---|
| `lint` | Ruff, Black, MyPy |
| `security` | Bandit + Safety CVE scan |
| `test` | pytest unit tests + Codecov coverage |
| `integration-test` | pytest integration tests |
| `docker-build` | Matrix build: api / ml / airflow |
| `terraform-validate` | fmt check, init, validate |
| `docs` | mkdocs build |
| `all-checks-passed` | Gating job |

**Cloud Build** (`cloudbuild.yaml`) — triggered on push to `pipeline`:
1. Build `api:latest`, `ml:latest`, `airflow:latest` (parallel)
2. Run Data-Pipeline tests
3. Validate Airflow DAG import
4. Push all images to `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/`

### Infrastructure: Terraform

All GCP resources are managed by Terraform in `infra/terraform/`.
Remote state: `gs://f1-optimizer-terraform-state/`.

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan -var-file=dev.tfvars
terraform -chdir=infra/terraform apply -var-file=dev.tfvars
```

## Environment Variables

Required for API (`src/api/main.py`):

```bash
GOOGLE_CLOUD_PROJECT=f1optimizer
PROJECT_ID=f1optimizer
REGION=us-central1
TRAINING_BUCKET=gs://f1optimizer-training
MODELS_BUCKET=gs://f1optimizer-models
DATA_BUCKET=gs://f1optimizer-data-lake
```

Required for ingest workers (`ingest/task.py`):
```bash
CLOUD_RUN_TASK_INDEX=0        # Set automatically by Cloud Run
GCS_BUCKET=f1optimizer-data-lake
```

See `team-docs/DEV_SETUP.md` §8 for the full list.

## Performance Targets

| Metric | Target |
|---|---|
| API P99 Latency | <500ms |
| System Uptime (race weekends) | 99.5% |
| Podium Accuracy | ≥70% |
| Winner Accuracy | ≥65% |
| Cost per Prediction | <$0.001 |
| Monthly Budget | <$70 |

## Known Gaps

1. `predict()` raises `NotImplementedError` in both models — API falls back to rule-based logic
2. `ml/training/distributed_trainer.py` imports `ray` but Ray is not in `docker/requirements-ml.txt`
3. Monitoring dashboards and alerting policies not yet created
