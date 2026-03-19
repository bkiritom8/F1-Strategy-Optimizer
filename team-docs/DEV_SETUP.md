# F1 Strategy Optimizer — Developer Setup Guide

**Project**: `f1optimizer` (GCP, `us-central1`)
**Repo**: [`bkiritom8/F1-Strategy-Optimizer`](https://github.com/bkiritom8/F1-Strategy-Optimizer) | Branch: `main` (stable) | `pipeline` (CI/CD)

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Authenticate with GCP](#2-authenticate-with-gcp)
3. [Data Storage](#3-data-storage)
4. [Access GCS Buckets Locally](#4-access-gcs-buckets-locally)
5. [Run Ingest Workers](#5-run-ingest-workers)
6. [Build and Push the ML Image](#6-build-and-push-the-ml-image)
7. [Submit a Vertex AI Training Job with GPU](#7-submit-a-vertex-ai-training-job-with-gpu)
8. [Colab Enterprise (GPU Alternative)](#8-colab-enterprise-gpu-alternative)
9. [Required Environment Variables](#9-required-environment-variables)

---

## 1. Prerequisites

Install the following before starting:

| Tool | Version | Install |
|---|---|---|
| `gcloud` CLI | Latest | https://cloud.google.com/sdk/docs/install |
| Docker Desktop | Latest | https://docs.docker.com/get-docker/ |
| Python | 3.10 | `pyenv install 3.10` or system package |
| Terraform | 1.5+ | https://developer.hashicorp.com/terraform/install |

### Clone and install Python dependencies

```bash
git clone https://github.com/bkiritom8/F1-Strategy-Optimizer.git
cd F1-Strategy-Optimizer

# Install API + dev dependencies
pip install -r docker/requirements-api.txt
```

---

## 2. Authenticate with GCP

You need two separate credentials: one for `gcloud` CLI commands and one for SDK usage in Python code.

### Step 1 — User account login (for gcloud commands)

```bash
gcloud auth login
gcloud config set project f1optimizer
gcloud config set compute/region us-central1
```

### Step 2 — Application Default Credentials (for Python SDKs)

```bash
gcloud auth application-default login
```

This writes `~/.config/gcloud/application_default_credentials.json`, which is picked up automatically by all Google Cloud Python libraries (`google-cloud-storage`, `google-cloud-aiplatform`, etc.).

### Verify

```bash
gcloud auth list                          # shows active account
gcloud auth application-default print-access-token   # should print a token
```

---

## 3. Data Storage

All F1 data is stored in GCS.

| Bucket | Path | Contents |
|---|---|---|
| `gs://f1optimizer-data-lake/raw/` | Source CSVs | 51 files, 6.0 GB — Jolpica API + FastF1 |
| `gs://f1optimizer-data-lake/processed/` | Parquet | 10 files, 1.0 GB — ML-ready, compressed |
| `gs://f1optimizer-data-lake/telemetry/` | Per-year FastF1 | Written by ingest workers |
| `gs://f1optimizer-data-lake/historical/` | Per-season Jolpica | Written by ingest workers |
| `gs://f1optimizer-models/` | Promoted models | `strategy_predictor/latest/model.pkl` etc. |
| `gs://f1optimizer-training/` | Training artifacts | Checkpoints, feature files, pipeline runs |

### Processed Parquet files

| GCS Path | Rows | Description |
|---|---|---|
| `processed/laps_all.parquet` | 93,372 | laps_1996.csv … laps_2025.csv combined |
| `processed/telemetry_all.parquet` | 30,477,110 | telemetry_2018 … telemetry_2025 combined |
| `processed/telemetry_laps_all.parquet` | 92,242 | FastF1 telemetry-session laps combined |
| `processed/circuits.parquet` | 78 | F1 circuit master list |
| `processed/drivers.parquet` | 100 | Driver master list |
| `processed/pit_stops.parquet` | 11,077 | Pit stop records |
| `processed/race_results.parquet` | 7,600 | Race results 1950-2026 |
| `processed/lap_times.parquet` | 56,720 | Aggregated lap times |
| `processed/fastf1_laps.parquet` | 92,242 | FastF1 lap data (2018-2026) |
| `processed/fastf1_telemetry.parquet` | 90,302 | FastF1 telemetry summary |

### Reading processed data in Python

```python
import pandas as pd

# Read processed Parquet files directly from GCS (ADC credentials required — see §2)
laps         = pd.read_parquet("gs://f1optimizer-data-lake/processed/laps_all.parquet")
telemetry    = pd.read_parquet("gs://f1optimizer-data-lake/processed/telemetry_all.parquet")
circuits     = pd.read_parquet("gs://f1optimizer-data-lake/processed/circuits.parquet")
drivers      = pd.read_parquet("gs://f1optimizer-data-lake/processed/drivers.parquet")
race_results = pd.read_parquet("gs://f1optimizer-data-lake/processed/race_results.parquet")
```

ADC credentials (§2) are all that is required — no proxy or VPN needed.

### Converting raw CSVs to Parquet

```bash
python pipeline/scripts/csv_to_parquet.py \
  --input-dir /path/to/local/csvs \
  --bucket f1optimizer-data-lake

# Verify data lake contents
python pipeline/scripts/verify_upload.py --bucket f1optimizer-data-lake

# Backfill known data gaps (dry-run first)
python pipeline/scripts/backfill_data.py --bucket f1optimizer-data-lake --dry-run
```

---

## 4. Access GCS Buckets Locally

ADC credentials (§2) are sufficient for `gsutil` and the Python `google-cloud-storage` SDK.

```bash
# List processed data
gsutil ls gs://f1optimizer-data-lake/processed/

# List promoted models
gsutil ls gs://f1optimizer-models/

# Download a model artifact
gsutil cp gs://f1optimizer-models/strategy_predictor/latest/model.pkl .

# Upload a file
gsutil cp my_notebook.ipynb gs://f1optimizer-training/notebooks/
```

From Python:

```python
from google.cloud import storage

client = storage.Client(project="f1optimizer")
bucket = client.bucket("f1optimizer-training")
blob = bucket.blob("features/my_run/train_features.parquet")
blob.download_to_filename("train_features.parquet")
```

---

## 5. Run Ingest Workers

Data ingestion runs as Cloud Run Jobs. The `ingest/task.py` dispatcher routes `CLOUD_RUN_TASK_INDEX` (0–8) to the appropriate worker.

| Task Index | Worker | Data |
|---|---|---|
| 0–7 | `fastf1_worker.py` | FastF1 telemetry for 2018–2025 (one year per task) |
| 8 | `historical_worker.py` | Jolpica race results, lap times, pit stops 1950–2017 |

### Trigger all tasks via Cloud Run Job

```bash
gcloud run jobs execute f1-ingest \
  --region=us-central1 \
  --project=f1optimizer
```

### Run a single task locally (for debugging)

```bash
pip install -r docker/requirements-ingest.txt

# Task 3 = FastF1 year 2021
CLOUD_RUN_TASK_INDEX=3 GCS_BUCKET=f1optimizer-data-lake python -m ingest.task

# Task 8 = historical 1950–2017
CLOUD_RUN_TASK_INDEX=8 GCS_BUCKET=f1optimizer-data-lake python -m ingest.task
```

### Ingest design patterns

- **Idempotent**: every worker checks GCS for an existing blob before downloading — safe to re-run
- **Infinite backoff**: retries forever on transient errors (60s → 3600s cap)
- **Atomic progress**: `ingest/progress.py` uses GCS generation-match to prevent concurrent write conflicts
- **Rate limiting**: Jolpica workers enforce ≥8s between requests (≤450 req/hr, safely under the 500 req/hr cap)

### Check progress

```bash
# View ingest completion markers
gsutil ls gs://f1optimizer-data-lake/status/

# Check progress tracker
gsutil cat gs://f1optimizer-data-lake/status/progress.json
```

---

## 6. Build and Push the ML Image

After making changes to ML code, rebuild and push the `ml:latest` image so Vertex AI jobs pick up the new code.

### Build all images (recommended)

```bash
# Builds api:latest, ml:latest, and airflow:latest via Cloud Build
gcloud builds submit --config cloudbuild.yaml . --project=f1optimizer
```

Monitor the build at:
https://console.cloud.google.com/cloud-build/builds?project=f1optimizer

### Build only the ML image locally

```bash
# Authenticate Docker with Artifact Registry first (one-time)
gcloud auth configure-docker us-central1-docker.pkg.dev

# Build and push
docker build \
  --platform linux/amd64 \
  -t us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest \
  -f docker/Dockerfile.ml \
  .

docker push us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest
```

> **Note**: The ML image uses `nvidia/cuda:11.8.0` as base. Building locally requires Docker Desktop. The image is large (~6 GB); use Cloud Build for faster iteration.

---

## 7. Submit a Vertex AI Training Job with GPU

The recommended way to run GPU training is to submit a **Vertex AI Custom Job** using the convenience script.

### Quick start

```bash
bash ml/scripts/submit_training_job.sh --display-name your-name-experiment-1
```

This submits a job with:
- Machine: `n1-standard-4`
- GPU: 1× NVIDIA T4
- Image: `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest`
- Service Account: `f1-training-dev@f1optimizer.iam.gserviceaccount.com`

### Naming convention

Use `<your-name>-<model>-v<n>` to avoid collisions between teammates:

```bash
bash ml/scripts/submit_training_job.sh --display-name alice-strategy-v1
bash ml/scripts/submit_training_job.sh --display-name bob-pit-v2
```

### Monitor your job

```bash
# List recent custom jobs
gcloud ai custom-jobs list \
  --region=us-central1 \
  --project=f1optimizer \
  --filter="displayName:your-name*"

# Stream logs
gcloud ai custom-jobs stream-logs JOB_ID \
  --region=us-central1 --project=f1optimizer
```

Console: https://console.cloud.google.com/vertex-ai/training/custom-jobs?project=f1optimizer

### Available compute profiles

Defined in `ml/distributed/cluster_config.py`:

| Profile | Machine | GPUs | Workers | Use Case |
|---|---|---|---|---|
| `VERTEX_T4` | `n1-standard-4` | 1× T4 | 1 | Individual experiment (default for submit script) |
| `SINGLE_NODE_MULTI_GPU` | `n1-standard-16` | 4× T4 | 1 | Full training run |
| `MULTI_NODE_DATA_PARALLEL` | `n1-standard-8` | 1× T4 each | 4 | Large dataset sharding |
| `HYPERPARAMETER_SEARCH` | `n1-standard-4` | 0 | 8 | HP sweep |
| `CPU_DISTRIBUTED` | `n1-highmem-16` | 0 | 8 | Feature engineering |

To use a different profile programmatically:

```python
from ml.distributed.cluster_config import SINGLE_NODE_MULTI_GPU
from google.cloud import aiplatform

aiplatform.init(project="f1optimizer", location="us-central1")

job = aiplatform.CustomJob(
    display_name="full-training-run",
    worker_pool_specs=SINGLE_NODE_MULTI_GPU.worker_pool_specs(),
)
job.run(service_account="f1-training-dev@f1optimizer.iam.gserviceaccount.com")
```

---

## 8. Colab Enterprise (GPU Alternative)

Colab Enterprise gives you an interactive GPU notebook without provisioning a dedicated instance. It uses the same GCP project and ADC credentials.

### Access

1. Open: https://console.cloud.google.com/colab/notebooks?project=f1optimizer
2. Click **New notebook**
3. Select **Runtime** → **Change runtime type** → choose **T4 GPU**
4. The notebook runs inside your GCP project with full access to GCS buckets

### Connect to GCS from Colab Enterprise

```python
from google.cloud import storage

client = storage.Client(project="f1optimizer")
bucket = client.bucket("f1optimizer-training")
# ... same as local dev
```

### Read processed data from GCS

```python
import pandas as pd

df = pd.read_parquet("gs://f1optimizer-data-lake/processed/laps_all.parquet")
```

### Clone the repo in Colab

```python
import subprocess
subprocess.run(["git", "clone",
    "https://github.com/bkiritom8/F1-Strategy-Optimizer.git"], check=True)
import sys
sys.path.insert(0, "/content/F1-Strategy-Optimizer")
```

---

## 9. Required Environment Variables

Set these in your shell or in a local `.env` file (never commit `.env`).

```bash
# GCP project (usually set via gcloud config)
export GOOGLE_CLOUD_PROJECT=f1optimizer
export PROJECT_ID=f1optimizer
export REGION=us-central1

# GCS paths
export TRAINING_BUCKET=gs://f1optimizer-training
export MODELS_BUCKET=gs://f1optimizer-models
export DATA_BUCKET=gs://f1optimizer-data-lake

# FastF1 cache (optional — speeds up local development)
export FASTF1_CACHE=/tmp/fastf1_cache

# Ingest workers (set automatically by Cloud Run; needed for local runs)
export GCS_BUCKET=f1optimizer-data-lake
export CLOUD_RUN_TASK_INDEX=0
```

### `.env` file for local development

```bash
GOOGLE_CLOUD_PROJECT=f1optimizer
PROJECT_ID=f1optimizer
REGION=us-central1
TRAINING_BUCKET=gs://f1optimizer-training
MODELS_BUCKET=gs://f1optimizer-models
DATA_BUCKET=gs://f1optimizer-data-lake
GCS_BUCKET=f1optimizer-data-lake
```

Load with:

```bash
export $(grep -v '^#' .env | xargs)
# or with python-dotenv in your scripts (already a dependency)
```

---

*Last updated: 2026-03-19. See `team-docs/ml_module_handoff.md` for infrastructure details and known gaps.*
