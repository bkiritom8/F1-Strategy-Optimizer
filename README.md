# F1 Strategy Optimizer

Production-grade real-time F1 race strategy system: pit strategy, driving mode,
brake bias, throttle/braking patterns. Driver-aware recommendations using 76 years
of F1 data (1950–2026). Target: <500ms P99 latency.

## Features

- **Data**: Jolpica API (1950–2026) + FastF1 telemetry (2018–2026, 10Hz)
- **Ingest**: Cloud Run Jobs — 9 parallel tasks, one per year/epoch (ingest/)
- **Storage**: GCS — 51 raw files (6.0 GB CSV) + 10 processed Parquet files (1.0 GB)
- **ML**: XGBoost+LightGBM ensemble (strategy) + LSTM (pit stop optimizer)
- **Training**: Vertex AI Custom Jobs + KFP Pipeline (5-step DAG)
- **Serving**: FastAPI on Cloud Run (<500ms P99)
- **CI/CD**: GitHub Actions (9 jobs) + Cloud Build on `pipeline` branch — builds `api:latest`, `ml:latest`, `airflow:latest`

## Quick Start

### Prerequisites

- `gcloud` CLI (latest) — https://cloud.google.com/sdk/docs/install
- Python 3.10
- Terraform 1.5+
- Docker Desktop (for local development)

### Setup

```bash
git clone https://github.com/bkiritom8/F1-Strategy-Optimizer.git
cd F1-Strategy-Optimizer

pip install -r docker/requirements-api.txt

# Authenticate with GCP
gcloud auth login
gcloud auth application-default login
gcloud config set project f1optimizer
```

See [`team-docs/DEV_SETUP.md`](./team-docs/DEV_SETUP.md) for the complete developer onboarding guide.

## Architecture

```
Jolpica API (1950–2026)  ──┐
                            ├──> Cloud Run Ingest Jobs (ingest/)
FastF1 SDK (2018–2026)  ───┘   9 parallel tasks (0-8)
                                        │
                          gs://f1optimizer-data-lake/raw/
                                        │
                              pipeline/scripts/csv_to_parquet.py
                                        │
                          gs://f1optimizer-data-lake/processed/
                                   (10 Parquet files)
                                        │
                               Feature Pipeline (KFP)
                              ml/dag/f1_pipeline.py
                                        │
                            Vertex AI Training Jobs
                        (XGBoost+LightGBM ∥ LSTM+MirroredStrategy)
                                        │
                          gs://f1optimizer-models/*/latest/
                                        │
                              FastAPI (Cloud Run)
                         f1-strategy-api-dev  <500ms P99
```

## Repository Structure

```
ingest/                Cloud Run ingest workers (one per year/data type)
  task.py              Cloud Run entrypoint — routes CLOUD_RUN_TASK_INDEX 0–8
  fastf1_worker.py     FastF1 telemetry per year (Tasks 0–7: 2018–2025)
  historical_worker.py Jolpica historical data 1950–2017 (Task 8)
  lap_times_worker.py  Jolpica lap-by-lap times
  gap_worker.py        Targeted backfill (5 gap scenarios)
  progress.py          GCS-backed optimistic locking
  gcs_utils.py         Upload helpers
ml/                    ML code — features, models, dag, distributed, tests
  dag/                 KFP v2 pipeline (f1_pipeline.py, pipeline_runner.py)
  dag/components/      6 KFP components (validate, features, train×2, eval×2, deploy)
  models/              StrategyPredictor, PitStopOptimizer
  features/            feature_store.py — GCS Parquet → DataFrame
  distributed/         cluster_config.py — 5 named Vertex AI cluster profiles
  tests/               run_tests_on_vertex.py
Data-Pipeline/         Course submission — Airflow DAG, DVC pipeline, tests
pipeline/              Data management utilities
  scripts/             csv_to_parquet.py, backfill_data.py, verify_upload.py
  simulator/           Race simulator
  rl/                  Reinforcement learning utilities
infra/terraform/       All GCP infrastructure (Terraform)
src/                   Shared code (FastAPI app, common utilities)
tests/                 Unit + integration tests
docker/                Dockerfiles + requirements
  Dockerfile.api       FastAPI server (port 8000)
  Dockerfile.ml        ML training (CUDA 11.8, no CMD)
  Dockerfile.ingest    Cloud Run ingest workers
docs/                  Technical documentation
team-docs/             Internal team docs (DEV_SETUP, handoffs)
```

## Docker Images

| Image | Registry | Used For |
|---|---|---|
| `api:latest` | Artifact Registry | Cloud Run serving |
| `ml:latest` | Artifact Registry | Vertex AI training jobs |
| `airflow:latest` | Artifact Registry | Airflow (course submission) |

Cloud Build builds and pushes all three on every push to `pipeline`.

## Data

All F1 data lives in GCS.

| Bucket Path | Files | Size | Contents |
|---|---|---|---|
| `gs://f1optimizer-data-lake/raw/` | 51 | 6.0 GB | Source CSVs (Jolpica + FastF1) |
| `gs://f1optimizer-data-lake/processed/` | 10 | 1.0 GB | Parquet files (ML-ready) |
| `gs://f1optimizer-data-lake/telemetry/` | — | — | Per-year FastF1 telemetry Parquet |
| `gs://f1optimizer-data-lake/historical/` | — | — | Jolpica 1950–2017 per-season Parquet |
| `gs://f1optimizer-models/` | — | — | Promoted model artifacts |
| `gs://f1optimizer-training/` | — | — | Checkpoints, feature exports, pipeline runs |

```python
import pandas as pd

laps      = pd.read_parquet("gs://f1optimizer-data-lake/processed/laps_all.parquet")
telemetry = pd.read_parquet("gs://f1optimizer-data-lake/processed/telemetry_all.parquet")
```

## Ingest Workers

Ingest runs as Cloud Run Jobs with 9 parallelised tasks:

```bash
# Trigger all ingest tasks (runs tasks 0–8 in parallel)
gcloud run jobs execute f1-ingest --region=us-central1 --project=f1optimizer

# Verify data lake contents
python pipeline/scripts/verify_upload.py --bucket f1optimizer-data-lake

# Backfill known gaps
python pipeline/scripts/backfill_data.py --bucket f1optimizer-data-lake --dry-run
```

| Task Index | Worker | Coverage |
|---|---|---|
| 0–7 | `fastf1_worker` | FastF1 telemetry 2018–2025 (one year per task) |
| 8 | `historical_worker` | Jolpica race results + lap times 1950–2017 |

## Data Pipeline (Course Submission)

See [`Data-Pipeline/README.md`](./Data-Pipeline/README.md) for the full pipeline docs.

```bash
# Local mode (no GCP)
USE_LOCAL_DATA=true dvc repro

# GCP mode
dvc repro
```

## Training

```bash
# Individual GPU experiment (recommended for dev work)
bash ml/scripts/submit_training_job.sh --display-name your-name-strategy-v1

# Full pipeline (5-step KFP DAG)
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d-%H%M%S)

# Trigger via Cloud Run Job (automated)
gcloud run jobs execute f1-pipeline-trigger --region=us-central1 --project=f1optimizer

# Run ML tests on Vertex AI
python ml/tests/run_tests_on_vertex.py
```

See [`team-docs/ml_module_handoff.md`](./team-docs/ml_module_handoff.md) for full ML documentation.

## API

**Endpoint**: `https://f1-strategy-api-dev-694267183904.us-central1.run.app`

```bash
curl https://f1-strategy-api-dev-694267183904.us-central1.run.app/health
curl https://f1-strategy-api-dev-694267183904.us-central1.run.app/docs
```

## Performance Targets

| Metric | Target |
|---|---|
| API P99 Latency | <500ms |
| Podium Accuracy | ≥70% |
| Winner Accuracy | ≥65% |
| Cost per Prediction | <$0.001 |
| Monthly Budget | <$70 |

## Infrastructure

Managed by Terraform in `infra/terraform/`. Review plan before applying:

```bash
terraform -chdir=infra/terraform plan -var-file=dev.tfvars
```

## Team Documentation

Internal team docs are in [`team-docs/`](./team-docs/).
Course submission pipeline is in [`Data-Pipeline/`](./Data-Pipeline/).

---

**Status**: ML handoff complete — distributed pipeline, models, tests ready. Data in GCS.
**Last Updated**: 2026-03-19
**Branch**: `main` (stable) | `pipeline` (CI/CD) | `ml-dev` (ML development)
