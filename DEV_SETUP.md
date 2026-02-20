# F1 Strategy Optimizer — Developer Setup Guide

**Project**: `f1optimizer` (GCP, `us-central1`)
**Repo**: `bkiritom8/test` | Branch: `main`

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Authenticate with GCP](#2-authenticate-with-gcp)
3. [Connect to Cloud SQL Locally](#3-connect-to-cloud-sql-locally)
4. [Access GCS Buckets Locally](#4-access-gcs-buckets-locally)
5. [Build and Push the ML Image](#5-build-and-push-the-ml-image)
6. [Submit a Vertex AI Training Job with GPU](#6-submit-a-vertex-ai-training-job-with-gpu)
7. [Colab Enterprise (GPU Alternative)](#7-colab-enterprise-gpu-alternative)
8. [Required Environment Variables](#8-required-environment-variables)

---

## 1. Prerequisites

Install the following before starting:

| Tool | Version | Install |
|---|---|---|
| `gcloud` CLI | Latest | https://cloud.google.com/sdk/docs/install |
| Docker Desktop | Latest | https://docs.docker.com/get-docker/ |
| Python | 3.10 | `pyenv install 3.10` or system package |
| Cloud SQL Auth Proxy | v2.14+ | See §3 |
| Terraform | 1.5+ | https://developer.hashicorp.com/terraform/install |

### Clone and install Python dependencies

```bash
git clone https://github.com/bkiritom8/test.git
cd test

# Install all ML + dev dependencies
pip install -r requirements-f1.txt
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

## 3. Connect to Cloud SQL Locally

The database uses a **private IP only** — it is not reachable from the internet. Use the Cloud SQL Auth Proxy to create a local tunnel.

### Install the Proxy (macOS, ARM)

```bash
curl -o cloud-sql-proxy \
  https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.1/cloud-sql-proxy.darwin.arm64
chmod +x cloud-sql-proxy
mv cloud-sql-proxy /usr/local/bin/
```

### Install the Proxy (macOS, Intel)

```bash
curl -o cloud-sql-proxy \
  https://storage.googleapis.com/cloud-sql-connectors/cloud-sql-proxy/v2.14.1/cloud-sql-proxy.darwin.amd64
chmod +x cloud-sql-proxy
mv cloud-sql-proxy /usr/local/bin/
```

### Start the proxy

```bash
# Binds to localhost:5432 using your ADC credentials
cloud-sql-proxy f1optimizer:us-central1:f1-optimizer-dev &
```

### Connect with psql

```bash
# Get the password from Secret Manager
DB_PASS=$(gcloud secrets versions access latest \
  --secret=f1-db-password-dev --project=f1optimizer)

psql -h 127.0.0.1 -p 5432 -U postgres -d f1_strategy
# or using the app user:
psql -h 127.0.0.1 -p 5432 -U f1_api -d f1_strategy
```

### Connect from Python

```python
import os
import psycopg2

conn = psycopg2.connect(
    host="127.0.0.1",   # proxy is running locally
    port=5432,
    database="f1_strategy",
    user="f1_api",
    password=os.environ["DB_PASSWORD"],
)
```

Set `DB_PASSWORD` in your shell (see §8) or fetch it from Secret Manager at runtime.

---

## 4. Access GCS Buckets Locally

ADC credentials (§2) are sufficient for `gsutil` and the Python `google-cloud-storage` SDK.

```bash
# List training artifacts
gsutil ls gs://f1optimizer-training/

# List promoted models
gsutil ls gs://f1optimizer-models/

# Download a model artifact
gsutil cp gs://f1optimizer-models/strategy_predictor/latest/xgb_model.pkl .

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

## 5. Build and Push the ML Image

After making changes to ML code, rebuild and push the `ml:latest` image so Vertex AI jobs pick up the new code.

### Build all 3 images (recommended)

```bash
# Builds api:latest, ingestion:latest, ml:latest via Cloud Build
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

## 6. Submit a Vertex AI Training Job with GPU

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

## 7. Colab Enterprise (GPU Alternative)

Colab Enterprise gives you an interactive GPU notebook without provisioning a Workbench instance. It uses the same GCP project and ADC credentials.

### Access

1. Open: https://console.cloud.google.com/colab/notebooks?project=f1optimizer
2. Click **New notebook**
3. Select **Runtime** → **Change runtime type** → choose **T4 GPU**
4. The notebook runs inside your GCP project with access to GCS and Cloud SQL via VPC

### Connect to GCS from Colab Enterprise

```python
from google.cloud import storage

client = storage.Client(project="f1optimizer")
bucket = client.bucket("f1optimizer-training")
# ... same as local dev
```

### Connect to Cloud SQL from Colab Enterprise

Use the Connector library (no proxy needed from inside GCP):

```python
from google.cloud.sql.connector import Connector
import pg8000

connector = Connector()

def get_conn():
    return connector.connect(
        "f1optimizer:us-central1:f1-optimizer-dev",
        "pg8000",
        user="f1_api",
        password=DB_PASSWORD,
        db="f1_strategy",
    )
```

### Clone the repo in Colab

```python
import subprocess
subprocess.run(["git", "clone", "https://github.com/bkiritom8/test.git"], check=True)
import sys
sys.path.insert(0, "/content/test")
```

---

## 8. Required Environment Variables

Set these in your shell or in a local `.env` file (never commit `.env`).

```bash
# GCP project (usually set via gcloud config)
export GOOGLE_CLOUD_PROJECT=f1optimizer
export PROJECT_ID=f1optimizer
export REGION=us-central1

# Database password (fetch from Secret Manager at startup)
export DB_PASSWORD=$(gcloud secrets versions access latest \
  --secret=f1-db-password-dev --project=f1optimizer)

# Database host — use 127.0.0.1 when running Cloud SQL Auth Proxy locally
export DB_HOST=127.0.0.1

# GCS paths
export TRAINING_BUCKET=gs://f1optimizer-training
export MODELS_BUCKET=gs://f1optimizer-models

# FastF1 cache (optional — speeds up local development)
export FASTF1_CACHE=/tmp/fastf1_cache
```

### `.env` file for local development

```bash
GOOGLE_CLOUD_PROJECT=f1optimizer
PROJECT_ID=f1optimizer
REGION=us-central1
DB_HOST=127.0.0.1
DB_NAME=f1_strategy
DB_USER=f1_api
TRAINING_BUCKET=gs://f1optimizer-training
MODELS_BUCKET=gs://f1optimizer-models
```

Load with:

```bash
export $(grep -v '^#' .env | xargs)
# or with python-dotenv in your scripts (already a dependency)
```

---

*Last updated: 2026-02-19. See `ML_HANDOFF.md` for infrastructure details and known gaps.*
