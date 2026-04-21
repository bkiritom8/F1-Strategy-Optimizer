# Operational Scripts

Deployment, ingestion, and teardown scripts for the DivergeX F1 Strategy platform.

## Contents

| Script | Purpose |
|---|---|
| `deploy.sh` | Full end-to-end deployment: Terraform, data ingestion, Cloud Build, ML pipeline, Firebase |
| `ingest.sh` | Data ingestion pipeline: build ingest image, run Cloud Run job, convert/verify/preprocess data, RAG indexing |
| `cleanup.sh` | Tear down cloud resources: Firebase hosting, optional GCS wipe, Terraform destroy |

## Usage

### Full Deployment

```bash
# Complete deployment (terraform -> ingest -> build -> train -> frontend)
bash scripts/deploy.sh

# Skip individual steps
bash scripts/deploy.sh --skip-infra       # skip terraform apply
bash scripts/deploy.sh --skip-ingest      # skip data ingestion
bash scripts/deploy.sh --skip-build       # skip Cloud Build
bash scripts/deploy.sh --skip-training    # skip ML pipeline
bash scripts/deploy.sh --skip-frontend    # skip Firebase deploy
```

### Data Ingestion Only

```bash
# Full ingestion (data + RAG)
bash scripts/ingest.sh

# Skip data ingest (only run RAG ingestion)
bash scripts/ingest.sh --skip-data-ingest

# Skip RAG ingestion (only run data pipeline)
bash scripts/ingest.sh --skip-rag
```

### Teardown

```bash
# Disable Firebase hosting + Terraform destroy (prompts for confirmation)
bash scripts/cleanup.sh

# Also wipe all GCS data buckets (irreversible)
bash scripts/cleanup.sh --wipe-data
```

> [!WARNING]
> `cleanup.sh --wipe-data` permanently deletes all data in `f1optimizer-data-lake`, `f1optimizer-models`, and `f1optimizer-training`. Always confirm before proceeding.

---

**Prerequisites**: `gcloud auth application-default login` and `gcloud config set project f1optimizer`
