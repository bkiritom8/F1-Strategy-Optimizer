# F1 Strategy Optimizer

Production-grade real-time F1 race strategy system: pit strategy, driving mode,
brake bias, throttle/braking patterns. Driver-aware recommendations using 76 years
of F1 data (1950–2026). Target: <500ms P99 latency.

## Features

- **Data**: Jolpica API (1950–2026) + FastF1 telemetry (2018–2026, 10Hz)
- **Storage**: GCS — 51 raw files (6.0 GB CSV) + 10 processed Parquet files (1.0 GB)
- **ML**: XGBoost+LightGBM ensemble (strategy) + LSTM (pit stop optimizer)
- **Training**: Vertex AI Custom Jobs + KFP Pipeline (5-step DAG)
- **Serving**: FastAPI on Cloud Run (<500ms P99)
- **Orchestration**: Airflow DAG on GCE VM (`f1-airflow-vm`, e2-standard-2)
- **CI/CD**: Cloud Build on `pipeline` branch — builds `api:latest`, `ml:latest`, `airflow:latest`

## Quick Start

### Prerequisites

- `gcloud` CLI (latest) — https://cloud.google.com/sdk/docs/install
- Python 3.10
- Terraform 1.5+
- Docker Desktop (for local development)

### Setup

```bash
git clone https://github.com/bkiritom8/test.git
cd test

pip install -r requirements-f1.txt

# Copy env vars
cp .env.example .env

# Authenticate with GCP
gcloud auth login
gcloud auth application-default login
gcloud config set project f1optimizer
```

See [`team-docs/DEV_SETUP.md`](./team-docs/DEV_SETUP.md) for the complete developer onboarding guide.

## Architecture

```
Jolpica API (1950-2026) ──┐
                           ├──> gs://f1optimizer-data-lake/raw/
FastF1 (2018-2026)    ────┘              │
                                  csv_to_parquet.py
                                         │
                          gs://f1optimizer-data-lake/processed/
                                         │
                          ┌──────────────┴──────────────┐
                          ▼                             ▼
                   Airflow DAG (GCE VM)        Feature Pipeline (KFP)
                   f1-airflow-vm:8080                   │
                   Data-Pipeline/dags/         Vertex AI Training Jobs
                                                        │
                                          gs://f1optimizer-models/
                                                        │
                                              FastAPI (Cloud Run)
                                  https://f1-strategy-api-dev-694267183904.us-central1.run.app
                                              <500ms P99
```

## Repository Structure

```
ml/                    ML code — features, models, dag, distributed, tests
Data-Pipeline/         Course submission — Airflow DAG, DVC pipeline, tests
pipeline/              Data management utilities
  scripts/             csv_to_parquet.py, verify_upload.py
  simulator/           Race simulator
  rl/                  Reinforcement learning utilities
infra/terraform/       All GCP infrastructure (Terraform)
  airflow_vm.tf        GCE VM for Airflow (e2-standard-2, Container-Optimized OS)
  scripts/             VM startup scripts
api/                   FastAPI serving notes
monitoring/            Observability notes
docker/                Dockerfiles + requirements
  Dockerfile.api       FastAPI server
  Dockerfile.ml        ML training (CUDA 11.8)
  Dockerfile.airflow   Airflow webserver + scheduler
  Dockerfile.mock-dataflow  Local Dataflow mock (dev only)
src/                   Shared code
  api/                 FastAPI application
  common/              Logging, metrics, security utilities
  ingestion/           Jolpica + FastF1 ingestion clients
  mocks/               Local mock servers (dev only)
  preprocessing/       Data validation (Pydantic schemas)
tests/                 Unit + integration tests
docs/                  Technical documentation
team-docs/             Internal team docs (DEV_SETUP, handoffs)
```

## Docker Images

| Image | Registry | Used For |
|---|---|---|
| `api:latest` | Artifact Registry | Cloud Run serving |
| `ml:latest` | Artifact Registry | Vertex AI training jobs |
| `airflow:latest` | Artifact Registry | GCE VM + local docker-compose |
| `mock-dataflow` | Local only | Local Dataflow simulation (dev only) |

Cloud Build builds and pushes `api`, `ml`, and `airflow` on every push to `pipeline`.

## Local Development

```bash
# Start core services
cp .env.example .env
docker-compose -f docker-compose.f1.yml up api prometheus grafana

# Start Airflow locally
docker-compose -f docker-compose.f1.yml up airflow-webserver airflow-scheduler
# UI → http://localhost:8080 (admin / admin)

# Start Dataflow mock (simulates GCP Dataflow, no cost)
docker-compose -f docker-compose.f1.yml up mock-dataflow
# API → http://localhost:8088/docs
```

## Data

All F1 data lives in GCS — no database.

| Bucket Path | Files | Size | Contents |
|---|---|---|---|
| `gs://f1optimizer-data-lake/raw/` | 51 | 6.0 GB | Source CSVs (Jolpica + FastF1) |
| `gs://f1optimizer-data-lake/processed/` | 10 | 1.0 GB | Parquet files (ML-ready) |
| `gs://f1optimizer-training/dags/` | — | — | Airflow DAGs synced to GCE VM |
| `gs://f1optimizer-models/` | — | — | Promoted model artifacts |
| `gs://f1optimizer-training/` | — | — | Checkpoints, feature exports |

```python
import pandas as pd

laps      = pd.read_parquet("gs://f1optimizer-data-lake/processed/laps_all.parquet")
telemetry = pd.read_parquet("gs://f1optimizer-data-lake/processed/telemetry_all.parquet")
```

## Data Pipeline (Course Submission)

See [`Data-Pipeline/README.md`](./Data-Pipeline/README.md) for the full pipeline docs.

```bash
# Local mode (no GCP)
USE_LOCAL_DATA=true dvc repro

# GCP mode
dvc repro

# Deploy DAG updates to GCE VM
bash Data-Pipeline/scripts/deploy_dags.sh
```

## Training

```bash
# Individual GPU experiment (recommended for dev work)
bash ml/scripts/submit_training_job.sh --display-name your-name-strategy-v1

# Full pipeline (5-step KFP)
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d)

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

## Airflow on GCP

```bash
# Provision GCE VM
terraform -chdir=infra/terraform apply -var-file=dev.tfvars

# Deploy DAGs to GCS (VM syncs every 5 min)
bash Data-Pipeline/scripts/deploy_dags.sh

# Get Airflow UI URL
terraform -chdir=infra/terraform output airflow_url
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

**Status**: Production-ready — GCE Airflow VM, 3 Docker images, full data pipeline
**Last Updated**: 2026-02-24
**Repo**: [`bkiritom8/test`](https://github.com/bkiritom8/test)
**Branch**: `main` (stable) | `pipeline` (CI/CD) | `ml-dev` (ML development)
