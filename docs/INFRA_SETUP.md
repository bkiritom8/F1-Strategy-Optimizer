# Infrastructure Setup Guide

How to provision the full DivergeX stack on GCP from scratch and run it yourself.

**Estimated time**: 60–90 minutes (most of it waiting on Terraform and data ingestion)
**Estimated monthly cost**: ~$70 at dev scale (enforced by Terraform budget alert)

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| `gcloud` CLI | Latest | https://cloud.google.com/sdk/docs/install |
| Terraform | 1.5+ | https://developer.hashicorp.com/terraform/install |
| Python | 3.10 | `pyenv install 3.10` |
| Docker Desktop | Latest | https://docs.docker.com/get-docker/ |
| Node.js | 18+ | https://nodejs.org (only needed for frontend deploy) |

You also need a GCP billing account. All resources run in a single project — the default config spends roughly $2/day when idle.

---

## Step 1 — GCP Project

Create a new GCP project or use an existing one.

```bash
# Create a new project
gcloud projects create my-f1-optimizer --name="F1 Optimizer"
gcloud config set project my-f1-optimizer

# Link billing (replace BILLING_ID with yours)
gcloud billing projects link my-f1-optimizer --billing-account=BILLING_ID

# Authenticate both CLI and Python SDK
gcloud auth login
gcloud auth application-default login
gcloud config set compute/region us-central1
```

---

## Step 2 — Configure Terraform Variables

Copy the example vars file and fill in your values:

```bash
cp infra/terraform/dev.tfvars infra/terraform/my.tfvars
```

Edit `infra/terraform/my.tfvars`:

```hcl
project_id    = "my-f1-optimizer"        # your GCP project ID
region        = "us-central1"
environment   = "dev"
email_from    = "you@example.com"        # sender address for verification emails
app_base_url  = "https://my-f1-optimizer.web.app"
alert_emails  = ["you@example.com"]      # receives monitoring alerts
budget_amount = 70                       # hard monthly spend cap in USD
api_min_instances = 0
api_max_instances = 3
```

---

## Step 3 — Provision Infrastructure

```bash
cd infra/terraform

# Initialise providers and remote state
terraform init

# Preview what will be created
terraform plan -var-file=my.tfvars

# Apply (takes ~10 minutes)
terraform apply -var-file=my.tfvars
```

### What gets created

| Resource | Details |
|---|---|
| **GCS Buckets** | `{project}-data-lake`, `{project}-models`, `{project}-training`, `{project}-pipeline-runs` |
| **Artifact Registry** | Docker repository `f1-optimizer` in `us-central1` |
| **Cloud Run Service** | `f1-strategy-api-dev` — FastAPI backend (0–3 instances, scales to zero) |
| **Cloud Run Jobs** | `f1-ingest` (10-task data ingestion), `f1-pipeline-trigger` (ML pipeline), `f1-rag-ingest` |
| **Vertex AI** | Vector Search index + endpoint for RAG, pipeline runner IAM |
| **Firestore** | Native mode database for user accounts, with indexes |
| **Cloud Build Trigger** | Listens to `pipeline` branch — builds and deploys on push |
| **Secret Manager** | `jwt-secret-key`, `smtp-user`, `smtp-pass` |
| **Service Accounts** | `api-sa`, `f1-ingest-sa`, `f1-training-dev` with scoped IAM bindings |
| **Monitoring** | Email notification channels, ML drift/accuracy/retraining alert policies |

---

## Step 4 — Build and Push Docker Images

Cloud Build handles this automatically on push to `pipeline`, but for a first-time setup run it manually:

```bash
cd /path/to/repo

gcloud builds submit . \
  --config=cloudbuild.yaml \
  --project=my-f1-optimizer \
  --substitutions=COMMIT_SHA=initial,SHORT_SHA=initial
```

This builds three images and pushes them to Artifact Registry:
- `api:latest` — FastAPI server
- `ml:latest` — ML training (CUDA 11.8)
- `ingest:latest` — Cloud Run ingest workers

Takes ~15 minutes.

---

## Step 5 — Ingest Data

Populate the data lake. This downloads 76 years of F1 data from Jolpica and 2018–2026 10Hz telemetry from FastF1, converts to Parquet, and preprocesses ML features.

```bash
PROJECT_ID=my-f1-optimizer bash scripts/ingest.sh
```

**Takes 20–40 minutes.** Progress can be monitored at:

```bash
gcloud storage cat gs://my-f1-optimizer-data-lake/status/progress.json
```

To skip data ingest and only run RAG indexing (if data already exists):

```bash
PROJECT_ID=my-f1-optimizer bash scripts/ingest.sh --skip-data-ingest
```

---

## Step 6 — Run the ML Pipeline

Train all six supervised models and the RL agent via Vertex AI Pipelines:

```bash
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d-%H%M%S)
```

Monitor pipeline progress at:
https://console.cloud.google.com/vertex-ai/pipelines?project=my-f1-optimizer

Training time: ~45 minutes on T4 GPU (provisioned automatically by Vertex AI).

---

## Step 7 — Deploy the Frontend

```bash
# Install Firebase CLI if not already present
npm install -g firebase-tools
firebase login

cd frontend
npm install
npm run build
firebase deploy --only hosting --project my-f1-optimizer
```

Firebase Hosting URL will be printed after deploy (e.g. `https://my-f1-optimizer.web.app`).

---

## One-Command Deploy

After completing Steps 1–3 (GCP project + Terraform + Docker images), you can run everything else with a single script:

```bash
PROJECT_ID=my-f1-optimizer bash scripts/deploy.sh --skip-infra
```

Skip flags available if you only want to re-run specific steps:

```bash
bash scripts/deploy.sh --skip-infra       # skip terraform (already done)
bash scripts/deploy.sh --skip-ingest      # skip data ingestion
bash scripts/deploy.sh --skip-build       # skip Cloud Build
bash scripts/deploy.sh --skip-training    # skip ML pipeline
bash scripts/deploy.sh --skip-frontend    # skip Firebase deploy
```

---

## Verify the Deployment

```bash
# Check Cloud Run service is running
gcloud run services describe f1-strategy-api-dev \
  --region=us-central1 --project=my-f1-optimizer

# Hit the health endpoint (URL from above command)
curl https://<service-url>/api/v1/health

# Check data lake contents
gcloud storage ls gs://my-f1-optimizer-data-lake/processed/

# Check promoted models
gcloud storage ls gs://my-f1-optimizer-models/
```

---

## Tear Down

When you are done testing:

```bash
PROJECT_ID=my-f1-optimizer bash scripts/cleanup.sh
```

To also delete all GCS data (irreversible):

```bash
PROJECT_ID=my-f1-optimizer bash scripts/cleanup.sh --wipe-data
```

This disables Firebase Hosting and runs `terraform destroy` — all Cloud Run, Vertex AI, Firestore, Artifact Registry, and GCS resources are removed. Secrets in Secret Manager must be deleted manually if needed.

---

## Cost Reference

| Component | Monthly cost (dev scale) |
|---|---|
| Cloud Run (0–3 instances, scales to zero) | ~$0–5 |
| Cloud Build (on push) | ~$2–5 |
| GCS storage (data lake + models, ~10 GB) | ~$2 |
| Vertex AI Pipelines (training, occasional) | ~$10–20 |
| Vertex AI Vector Search (RAG index) | ~$30–40 |
| Firebase Hosting | Free tier |
| **Total** | **~$50–70/month** |

The Terraform budget alert fires at $70 (email) to flag unexpected spend before it becomes a problem.

---

*See [`DEV_SETUP.md`](./DEV_SETUP.md) for day-to-day developer workflow after the infra is live.*
