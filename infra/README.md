# Infrastructure as Code

Terraform manages all GCP infrastructure for the F1 Strategy Optimizer. Budget hard cap: **$70/month**.

## Structure

```
infra/
└── terraform/
    ├── main.tf              # Core resources (GCS, Cloud Run, Firestore, IAM)
    ├── vertex_ml.tf         # Vertex AI Pipelines, APIs, trigger job IAM
    ├── dev.tfvars           # Dev environment variable values
    ├── modules/
    │   ├── compute/         # Cloud Run service configurations
    │   ├── dataflow/        # Dataflow pipeline configs
    │   └── pubsub/          # Pub/Sub topic + subscription definitions
    └── scripts/             # Terraform helper scripts
```

## Resources Managed

| Resource | Name | Purpose |
|---|---|---|
| GCS Bucket | `f1optimizer-data-lake` | Raw CSVs, processed Parquet, ml_features |
| GCS Bucket | `f1optimizer-models` | Promoted supervised model artifacts |
| GCS Bucket | `f1optimizer-training` | Training job outputs, PPO checkpoints |
| Cloud Run | `f1-strategy-api-dev` | FastAPI backend (`api:latest`) |
| Cloud Run Job | `f1-ingest` | Ingest workers (`ingest:latest`) |
| Cloud Run Job | `f1-pipeline-trigger` | Triggers KFP ML pipeline |
| Firestore | `f1optimizer` | User auth sessions, config |
| Vertex AI | Pipelines + Search | KFP orchestration + RAG vector index |
| Service Account | `f1-training-dev` | Vertex AI training job identity |
| IAM | — | Least-privilege bindings per service |

## Usage

```bash
cd infra/terraform

# Initialize (first time or after provider updates)
terraform init

# Preview changes — always do this first
terraform plan -var-file=dev.tfvars

# Apply to dev
terraform apply -var-file=dev.tfvars
```

> [!CAUTION]
> Always review `terraform plan` output before applying. Destructive operations on `f1optimizer-data-lake` will cause permanent data loss.

## Cloud Build Integration

`cloudbuild.yaml` at the repo root builds `api:latest`, `ml:latest`, and `ingest:latest` on every push to `pipeline`:

- Logging: `LEGACY` with `REGIONAL_USER_OWNED_BUCKET`
- Timeout: 20 minutes
- Image tagging: `COMMIT_SHA`

---

**Project**: `f1optimizer` | **Region**: `us-central1` | **Budget cap**: $70/month | **Last Updated**: 2026-04-08
