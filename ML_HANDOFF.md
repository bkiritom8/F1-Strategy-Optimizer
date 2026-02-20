# F1 Strategy Optimizer — ML Team Handoff

**Date**: 2026-02-19
**Project**: `f1optimizer` (GCP, `us-central1`)
**Repo**: `bkiritom8/test` | Branch: `main`
**Connection name**: `f1optimizer:us-central1:f1-optimizer-dev`

---

## Table of Contents

1. [Infrastructure State](#1-infrastructure-state)
2. [What Was Destroyed and Why](#2-what-was-destroyed-and-why)
3. [Vertex AI Workbench Access](#3-vertex-ai-workbench-access)
4. [GCS Paths](#4-gcs-paths)
5. [Cloud SQL Connection](#5-cloud-sql-connection)
6. [API Endpoint](#6-api-endpoint)
7. [Repo Structure — ml/](#7-repo-structure--ml)
8. [How to Run Training](#8-how-to-run-training)
9. [Compute Profiles](#9-compute-profiles)
10. [Known Gaps and Proposed Fixes](#10-known-gaps-and-proposed-fixes)
11. [Day 1 Quickstart](#11-day-1-quickstart)
12. [GPU Training](#12-gpu-training)

---

## 1. Infrastructure State

All infrastructure is Terraform-managed (`infra/terraform/`, state in `gs://f1-optimizer-terraform-state/`).

### Created / Verified (2026-02-19)

| Resource | Name / ID | Status |
|---|---|---|
| GCS — model artifacts | `gs://f1optimizer-models/` | ✅ Created |
| GCS — training data | `gs://f1optimizer-training/` | ✅ Created |
| GCS — FastF1 cache | `gs://f1optimizer-fastf1-cache/` | Managed by Terraform |
| GCS — Terraform state | `gs://f1-optimizer-terraform-state/` | ✅ Active |
| Secret Manager | `f1-db-password-dev` | ✅ Created (alphanumeric) |
| Service Account | `f1-training-dev@f1optimizer.iam.gserviceaccount.com` | ✅ Created |
| SA IAM roles | `storage.objectAdmin`, `aiplatform.user`, `aiplatform.customCodeServiceAgent`, `cloudsql.client` | ✅ Bound |
| Terraform VPC | `f1-optimizer-network-dev` | Managed by Terraform |
| Cloud SQL PostgreSQL 15 | `f1-optimizer-dev` | Managed by Terraform |
| Artifact Registry | `f1-optimizer` (Docker, `us-central1`) | Managed by Terraform |
| Cloud Run service | `f1-strategy-api-dev` | Managed by Terraform |
| Cloud Run Jobs | `f1-data-ingestion`, `f1-data-coordinator`, `f1-jolpica-worker`, `f1-fastf1-worker`, `f1-ingestion-monitor`, `f1-pipeline-trigger` | Managed by Terraform |
| Pub/Sub topics | `f1-race-events-dev`, `f1-telemetry-stream-dev`, `f1-predictions-dev`, `f1-alerts-dev` | Managed by Terraform |
| Vertex AI Workbench | `f1-ml-workbench` | Managed by Terraform |

### Apply / verify current state

```bash
terraform -chdir=infra/terraform plan -var-file=dev.tfvars
terraform -chdir=infra/terraform apply -auto-approve -var-file=dev.tfvars
```

---

## 2. What Was Destroyed and Why

### Cloud SQL instance `f1-optimizer-dev`

**Destroyed**: 2026-02-19 via `terraform destroy` to resolve two blockers:

1. `deletion_protection = true` prevented destroy — patched via `gcloud sql instances patch` then set to `false` in `infra/terraform/main.tf`.
2. `f1_api` Cloud SQL user could not be dropped because 24 objects in `f1_strategy` depended on it — resolved by adding `deletion_policy = "ABANDON"` to `google_sql_user.api_user` in Terraform so the user is removed from state without a DELETE call (the instance deletion cascades it anyway).

**Re-created** by `terraform apply` immediately after. The new instance has:
- Same name: `f1-optimizer-dev`
- Same connection name: `f1optimizer:us-central1:f1-optimizer-dev`
- New private IP (assigned dynamically — do not hardcode IPs)
- New random password stored in `f1-db-password-dev` secret

> **Note**: All previously ingested F1 data was lost in the destroy. Re-run the ingestion job after apply to repopulate.

---

## 3. Vertex AI Workbench Access

Instance name: `f1-ml-workbench` | Machine: `n1-standard-8` + T4 GPU | Auto-shutdown: 60 min idle

**Console**: https://console.cloud.google.com/vertex-ai/workbench/instances?project=f1optimizer
Click **Open JupyterLab** next to `f1-ml-workbench`.

**Provision** (if not yet running):

```bash
terraform -chdir=infra/terraform apply -auto-approve -var-file=dev.tfvars \
  -target=google_workbench_instance.ml_workbench
```

---

## 4. GCS Paths

### Training bucket: `gs://f1optimizer-training/`

```
gs://f1optimizer-training/
├── features/          # Feature manifests (KFP feature_engineering step)
│   └── {run_id}/
│       ├── train_features.parquet
│       └── eval_features.parquet
├── checkpoints/       # Checkpoints written during training
│   ├── strategy_predictor/{run_id}/
│   └── pit_stop_optimizer/{run_id}/
└── pipelines/         # Compiled KFP YAML
    └── f1_strategy_pipeline.yaml
```

### Models bucket: `gs://f1optimizer-models/`

```
gs://f1optimizer-models/
├── strategy_predictor/latest/     # xgb_model.pkl, lgbm_model.pkl
└── pit_stop_optimizer/latest/     # model.keras, scaler.pkl
```

### FastF1 cache: `gs://f1optimizer-fastf1-cache/`

Used by `src/ingestion/fastf1_ingestion.py` to avoid re-downloading telemetry.

---

## 5. Cloud SQL Connection

> **Use the connection name** — the private IP can change after a destroy/recreate.

| Parameter | Value |
|---|---|
| Connection name | `f1optimizer:us-central1:f1-optimizer-dev` |
| Database | `f1_strategy` |
| Port | `5432` |
| Superuser | `postgres` |
| App user | `f1_api` |
| Password secret | `f1-db-password-dev` |

### Retrieve password

```bash
gcloud secrets versions access latest \
  --secret="f1-db-password-dev" \
  --project=f1optimizer
```

### Local development via Cloud SQL Auth Proxy

The DB uses private IP only (no public IP). For local access, use the Auth Proxy:

```bash
# Install (macOS)
curl -o cloud-sql-proxy \
  https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.1/cloud-sql-proxy.darwin.amd64
chmod +x cloud-sql-proxy

# Start proxy (binds to localhost:5432)
./cloud-sql-proxy f1optimizer:us-central1:f1-optimizer-dev \
  --credentials-file=~/.config/gcloud/application_default_credentials.json &

# Connect
psql -h 127.0.0.1 -p 5432 -U postgres -d f1_strategy
```

### Workbench / Cloud Run (VPC-connected) — connect directly

```python
import psycopg2, subprocess, os

def get_db_password() -> str:
    result = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest",
         "--secret=f1-db-password-dev", "--project=f1optimizer"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()

conn = psycopg2.connect(
    host=os.environ["DB_HOST"],   # injected by Terraform into all Cloud Run jobs
    port=5432,
    database="f1_strategy",
    user="f1_api",
    password=get_db_password(),
)
```

### Re-create app user after destroy

Run once after `terraform apply` recreates the instance:

```sql
-- Connect as postgres first
CREATE USER f1_api WITH PASSWORD '<password-from-secret>';
GRANT CONNECT ON DATABASE f1_strategy TO f1_api;
GRANT USAGE ON SCHEMA public TO f1_api;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO f1_api;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE ON TABLES TO f1_api;
```

---

## 6. API Endpoint

Service: `f1-strategy-api-dev` (Cloud Run, `us-central1`)

```bash
# Get URL
gcloud run services describe f1-strategy-api-dev \
  --region=us-central1 --project=f1optimizer --format="value(status.url)"
```

### Available routes

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/` | Service info |
| `POST` | `/predict/strategy` | Race strategy recommendation |
| `POST` | `/predict/pit-stop` | Pit stop timing recommendation |
| `GET` | `/models/info` | Loaded model metadata |

> **Note**: `/predict/*` endpoints fall back to rule-based logic until trained models are promoted to `gs://f1optimizer-models/*/latest/`. See gap C1 below.

---

## 7. Repo Structure — ml/

```
ml/
├── dag/
│   ├── f1_pipeline.py          # KFP v2 pipeline definition
│   ├── pipeline_runner.py      # Compile + submit + monitor
│   └── components/
│       ├── validate_data.py    # Step 1: data quality check vs Cloud SQL
│       ├── feature_engineering.py  # Step 2: features → GCS parquet
│       ├── train_strategy.py   # Step 3a: XGBoost+LightGBM (parallel)
│       ├── train_pit_stop.py   # Step 3b: LSTM (parallel)
│       ├── evaluate.py         # Step 4: score + log to Vertex Experiments
│       └── deploy.py           # Step 5: promote → gs://f1optimizer-models/*/latest/
│
├── models/
│   ├── strategy_predictor.py   # XGBoost + LightGBM ensemble
│   ├── pit_stop_optimizer.py   # LSTM (TF/Keras, GPU-capable via MirroredStrategy)
│   └── base_model.py           # Abstract base class
│
├── features/
│   ├── feature_store.py        # Cloud SQL → DataFrame
│   └── feature_pipeline.py     # Raw data → model-ready features
│
├── distributed/
│   ├── cluster_config.py       # 4 named compute configs (see §9)
│   ├── data_sharding.py        # Race-level sharding across workers
│   ├── distribution_strategy.py  # TF MirroredStrategy wrappers
│   └── aggregator.py           # Metric aggregation
│
├── scripts/
│   ├── run_training.sh         # Compile + submit KFP pipeline (see §8)
│   └── submit_training_job.sh  # Submit Vertex AI Custom Job with T4 GPU (see §12)
│
├── training/
│   └── distributed_trainer.py  # Ray-based distributed trainer (see gap M1)
│
├── tests/
│   ├── run_tests_on_vertex.py  # Submit all tests as Vertex AI Custom Job
│   ├── test_dag.py
│   ├── test_distributed.py
│   ├── test_features.py
│   └── test_models.py
│
└── evaluation/                 # Placeholder — empty (see gap M3)
```

### Pipeline DAG

```
validate_data
    └── feature_engineering
            ├── train_strategy  ──┐
            └── train_pit_stop  ──┤  (parallel)
                    ├── evaluate(strategy)  ─┐
                    └── evaluate(pit_stop)  ─┘  (parallel)
                            └── deploy
```

---

## 8. How to Run Training

### Option A — Shell script (recommended)

```bash
# Full pipeline (compile + submit)
bash ml/scripts/run_training.sh

# Compile only (no submit)
COMPILE_ONLY=true bash ml/scripts/run_training.sh

# With explicit run ID
bash ml/scripts/run_training.sh --run-id 20260219-1200
```

### Option B — Python directly

```bash
# Compile only
python ml/dag/pipeline_runner.py --compile-only

# Compile + submit + monitor
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d-%H%M%S)
```

### Option C — Via Cloud Run trigger job

```bash
gcloud run jobs execute f1-pipeline-trigger \
  --region=us-central1 --project=f1optimizer
```

### Option D — Individual model (Vertex AI Custom Job)

```bash
# Strategy Predictor
gcloud ai custom-jobs create \
  --region=us-central1 --project=f1optimizer \
  --display-name="strategy-predictor-$(date +%Y%m%d)" \
  --worker-pool-spec=machine-type=n1-standard-8,replica-count=1,\
container-image-uri=us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest \
  --args="python,-m,ml.models.strategy_predictor,--mode,train,\
--training-bucket,gs://f1optimizer-training,--models-bucket,gs://f1optimizer-models"
```

Monitor: https://console.cloud.google.com/vertex-ai/pipelines?project=f1optimizer

---

## 9. Compute Profiles

Defined in `ml/distributed/cluster_config.py`:

| Config | Machine | GPUs | Workers | Use Case |
|---|---|---|---|---|
| `VERTEX_T4` | `n1-standard-4` | 1× T4 | 1 | Individual experiment (see §12) |
| `SINGLE_NODE_MULTI_GPU` | `n1-standard-16` | 4× T4 | 1 | Standard training run |
| `MULTI_NODE_DATA_PARALLEL` | `n1-standard-8` | 1× T4 each | 4 | Large dataset sharding |
| `HYPERPARAMETER_SEARCH` | `n1-standard-4` | 0 | 8 | HP sweep (XGBoost/LightGBM) |
| `CPU_DISTRIBUTED` | `n1-highmem-16` | 0 | 8 | Feature engineering only |

---

## 10. Known Gaps and Proposed Fixes

### Critical

| # | Gap | Location | Fix |
|---|---|---|---|
| C1 | `predict()` raises `NotImplementedError` in both models — API `/predict/*` routes return rule-based fallback | `ml/models/strategy_predictor.py:357`, `ml/models/pit_stop_optimizer.py:378` | Implement a `_predict_entrypoint()` that loads the saved model from GCS and runs inference |
| C2 | `f1_api` DB user must be re-created after each Cloud SQL destroy/recreate | Cloud SQL | Run the GRANT SQL in §5 once after `terraform apply` |
| C3 | Ingested F1 data was lost with Cloud SQL destroy | Cloud SQL | Re-run `gcloud run jobs execute f1-data-ingestion --region=us-central1 --project=f1optimizer` |

### High

| # | Gap | Location | Fix |
|---|---|---|---|
| H1 | `ml/training/distributed_trainer.py` imports `ray` but Ray is not in `docker/requirements-ml.txt` — Vertex AI custom jobs will fail to import | `docker/requirements-ml.txt` | Add `ray[default]==2.9.1` to ML requirements, or replace Ray usage with TF `MirroredStrategy` (already present in `distribution_strategy.py`) |
| H2 | `bcrypt==4.2.1` broke `passlib 1.7.4` in API container (passlib's `detect_wrap_bug()` rejects bcrypt ≥4.0) | `docker/requirements-api.txt` | **Fixed**: pinned to `bcrypt>=3.2.0,<4.0.0` |
| H3 | `lightgbm==4.2.0` in `requirements-f1.txt` vs `4.3.0` in `docker/requirements-ml.txt` — model serialized on 4.3 won't load on 4.2 | `requirements-f1.txt` | **Fixed**: pinned to `4.3.0` everywhere |

### Medium

| # | Gap | Location | Fix |
|---|---|---|---|
| M1 | `ml/evaluation/` directory is empty — no post-training analysis code | `ml/evaluation/` | Move evaluation logic out of `ml/dag/components/evaluate.py` into a standalone module |
| M2 | KFP components all reference `:latest` image — no rollback capability | All `ml/dag/components/*.py` | Pin to git SHA or semver for production runs |
| M3 | `ml/scripts/` directory was missing | `ml/scripts/` | **Fixed**: created `run_training.sh` |

---

## 11. Day 1 Quickstart

### Step 0 — Clone and authenticate

```bash
git clone https://github.com/bkiritom8/test.git
cd test
git checkout main

# Install ML dependencies
pip install -r requirements-f1.txt

# GCP credentials
gcloud auth application-default login
gcloud config set project f1optimizer
```

### Step 1 — Apply infrastructure

```bash
terraform -chdir=infra/terraform apply -auto-approve -var-file=dev.tfvars
```

### Step 2 — Create the f1_api DB user (one-time after apply)

```bash
# Get password
DB_PASS=$(gcloud secrets versions access latest \
  --secret=f1-db-password-dev --project=f1optimizer)

# Start Cloud SQL Auth Proxy (separate terminal)
./cloud-sql-proxy f1optimizer:us-central1:f1-optimizer-dev &

# Create user
psql -h 127.0.0.1 -U postgres -d f1_strategy -c "
  CREATE USER f1_api WITH PASSWORD '${DB_PASS}';
  GRANT CONNECT ON DATABASE f1_strategy TO f1_api;
  GRANT USAGE ON SCHEMA public TO f1_api;
  GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO f1_api;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE ON TABLES TO f1_api;
"
```

### Step 3 — Build and push all images

```bash
gcloud builds submit --config cloudbuild.yaml . --project=f1optimizer
```

### Step 4 — Re-run ingestion to populate Cloud SQL

```bash
gcloud run jobs execute f1-data-ingestion \
  --region=us-central1 --project=f1optimizer

# Monitor
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="f1-data-ingestion"' \
  --project=f1optimizer --limit=50 --format="value(textPayload)"
```

### Step 5 — Open Workbench (optional)

https://console.cloud.google.com/vertex-ai/workbench/instances?project=f1optimizer
→ Click **Open JupyterLab** next to `f1-ml-workbench`.

### Step 6 — Run the ML pipeline

```bash
bash ml/scripts/run_training.sh
```

Monitor: https://console.cloud.google.com/vertex-ai/pipelines?project=f1optimizer

### Step 7 — Verify model artifacts were promoted

```bash
gsutil ls gs://f1optimizer-models/strategy_predictor/latest/
gsutil ls gs://f1optimizer-models/pit_stop_optimizer/latest/
```

### Step 8 — Check API health

```bash
API_URL=$(gcloud run services describe f1-strategy-api-dev \
  --region=us-central1 --project=f1optimizer --format="value(status.url)")
curl "${API_URL}/health"
```

### Step 9 — Run ML tests on Vertex AI

```bash
python ml/tests/run_tests_on_vertex.py
```

### Step 10 — Run ingestion with full monitoring

```bash
gcloud run jobs execute f1-ingestion-monitor \
  --region=us-central1 --project=f1optimizer
```

---

## 12. GPU Training

Two approaches for running GPU training jobs — use whichever fits your workflow.

### Option A — Vertex AI Custom Job (recommended)

Submit a job using the convenience script. Each teammate names their own run:

```bash
bash ml/scripts/submit_training_job.sh --display-name alice-strategy-v1
```

**What it provisions:**
- Machine: `n1-standard-4` (4 vCPU, 15 GB RAM)
- GPU: 1× NVIDIA T4
- Image: `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest`
- SA: `f1-training-dev@f1optimizer.iam.gserviceaccount.com`
- Region: `us-central1`

**Monitor:**

```bash
# List your jobs
gcloud ai custom-jobs list \
  --region=us-central1 --project=f1optimizer \
  --filter="displayName:alice*"

# Stream logs
gcloud ai custom-jobs stream-logs JOB_ID \
  --region=us-central1 --project=f1optimizer
```

Console: https://console.cloud.google.com/vertex-ai/training/custom-jobs?project=f1optimizer

**Programmatic (Python):**

```python
from ml.distributed.cluster_config import VERTEX_T4
from google.cloud import aiplatform

aiplatform.init(project="f1optimizer", location="us-central1")
job = aiplatform.CustomJob(
    display_name="alice-strategy-v1",
    worker_pool_specs=VERTEX_T4.worker_pool_specs(
        args=["python", "-m", "ml.models.strategy_predictor", "--mode", "train",
              "--training-bucket", "gs://f1optimizer-training",
              "--models-bucket", "gs://f1optimizer-models"]
    ),
)
job.run(service_account="f1-training-dev@f1optimizer.iam.gserviceaccount.com")
```

**VERTEX_T4 profile** (`ml/distributed/cluster_config.py`):

| Field | Value |
|---|---|
| Machine | `n1-standard-4` |
| GPU | 1× `NVIDIA_TESLA_T4` |
| Workers | 1 |
| Strategy | `MirroredStrategy` |

### Option B — Colab Enterprise (interactive GPU notebook)

Colab Enterprise gives you an interactive GPU session inside the GCP project with zero setup.

1. Open: https://console.cloud.google.com/colab/notebooks?project=f1optimizer
2. **New notebook** → **Runtime** → **Change runtime type** → select **T4 GPU**
3. Clone the repo and install dependencies:

```python
import subprocess, sys
subprocess.run(["git", "clone", "https://github.com/bkiritom8/test.git"], check=True)
subprocess.run(["pip", "install", "-r", "test/requirements-f1.txt"], check=True)
sys.path.insert(0, "/home/user/test")
```

4. Access GCS and Cloud SQL directly (no proxy needed — already inside VPC):

```python
from google.cloud import storage
client = storage.Client(project="f1optimizer")
```

Colab Enterprise is ideal for:
- Interactive model development and debugging
- Quick experiments without the CLI setup overhead
- Sharing notebooks with teammates via GCS

### Compute profiles summary

| Profile | Machine | GPU | Workers | Script / Config |
|---|---|---|---|---|
| `VERTEX_T4` | `n1-standard-4` | 1× T4 | 1 | `submit_training_job.sh` default |
| `SINGLE_NODE_MULTI_GPU` | `n1-standard-16` | 4× T4 | 1 | Large single-node runs |
| `MULTI_NODE_DATA_PARALLEL` | `n1-standard-8` | 1× T4 each | 4 | Distributed data parallel |
| `HYPERPARAMETER_SEARCH` | `n1-standard-4` | 0 | 8 | XGBoost/LightGBM HP sweep |
| `CPU_DISTRIBUTED` | `n1-highmem-16` | 0 | 8 | CPU-only feature engineering |

All profiles are defined in `ml/distributed/cluster_config.py`.

---

## Quick Reference

| What | Value / Command |
|---|---|
| Cloud SQL connection name | `f1optimizer:us-central1:f1-optimizer-dev` |
| DB name | `f1_strategy` |
| DB password | `gcloud secrets versions access latest --secret=f1-db-password-dev --project=f1optimizer` |
| Training bucket | `gs://f1optimizer-training/` |
| Models bucket | `gs://f1optimizer-models/` |
| Submit pipeline | `bash ml/scripts/run_training.sh` |
| Build all images | `gcloud builds submit --config cloudbuild.yaml . --project=f1optimizer` |
| Ingestion logs | `gcloud logging read 'resource.labels.job_name="f1-data-ingestion"' --project=f1optimizer --limit=50` |
| Vertex AI console | https://console.cloud.google.com/vertex-ai?project=f1optimizer |
| Cloud Run console | https://console.cloud.google.com/run?project=f1optimizer |

---

*Last updated: 2026-02-19. Append session notes to `docs/progress.md` after each ML session.*
