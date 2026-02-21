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
- **CI/CD**: Cloud Build on `pipeline` branch — builds `api:latest` + `ml:latest`

## Quick Start

### Prerequisites

- `gcloud` CLI (latest) — https://cloud.google.com/sdk/docs/install
- Python 3.10
- Terraform 1.5+

### Setup

```bash
git clone https://github.com/bkiritom8/test.git
cd test
pip install -r requirements-f1.txt

# Authenticate with GCP
gcloud auth login
gcloud auth application-default login
gcloud config set project f1optimizer
```

See `DEV_SETUP.md` for the complete developer onboarding guide.

## Architecture

```
Jolpica API (1950-2026) ──┐
                           ├──> gs://f1optimizer-data-lake/raw/
FastF1 (2018-2026)    ────┘              │
                                  csv_to_parquet.py
                                         │
                          gs://f1optimizer-data-lake/processed/
                                         │
                                  Feature Pipeline (KFP)
                                         │
                              Vertex AI Training Jobs
                                         │
                          gs://f1optimizer-models/ (promoted artifacts)
                                         │
                              FastAPI (Cloud Run)
                              https://f1-strategy-api-dev-694267183904.us-central1.run.app
                              <500ms P99
```

## Repository Structure

```
ml/                    ML code — features, models, dag, distributed, tests
pipeline/scripts/      Data scripts (csv_to_parquet.py, verify_upload.py)
infra/terraform/       All GCP infrastructure (Terraform)
api/                   FastAPI serving notes
monitoring/            Observability notes
docker/                Dockerfiles + requirements
src/                   Shared API code
tests/                 Unit + integration tests
docs/                  Technical documentation
```

## Data

All F1 data lives in GCS — no database.

| Bucket Path | Files | Size | Contents |
|---|---|---|---|
| `gs://f1optimizer-data-lake/raw/` | 51 | 6.0 GB | Source CSVs (Jolpica + FastF1) |
| `gs://f1optimizer-data-lake/processed/` | 10 | 1.0 GB | Parquet files (ML-ready) |
| `gs://f1optimizer-models/` | — | — | Promoted model artifacts |
| `gs://f1optimizer-training/` | — | — | Checkpoints, feature exports |

```python
import pandas as pd

laps      = pd.read_parquet("gs://f1optimizer-data-lake/processed/laps_all.parquet")
telemetry = pd.read_parquet("gs://f1optimizer-data-lake/processed/telemetry_all.parquet")
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

See `ml/HANDOFF.md` for full ML team documentation.

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

---

**Status**: ML handoff complete — data uploaded to GCS, models ready for training
**Last Updated**: 2026-02-20
**Branch**: `main` (stable) | `pipeline` (CI/CD trigger) | `ml-dev` (ML development)
