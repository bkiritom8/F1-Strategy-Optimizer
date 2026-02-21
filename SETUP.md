# F1 Strategy Optimizer — Setup

This project runs entirely on GCP — there is no local Docker or database setup.

**See `DEV_SETUP.md` for the complete developer onboarding guide**, covering:

1. Prerequisites (`gcloud`, Python 3.10, Terraform 1.5+)
2. GCP authentication (user account + Application Default Credentials)
3. Data storage (GCS buckets, processed Parquet files)
4. Accessing GCS buckets locally
5. Building and pushing the ML Docker image
6. Submitting a Vertex AI Training Job with GPU
7. Colab Enterprise (interactive GPU notebooks)
8. Required environment variables

## Quick Reference

```bash
# Authenticate
gcloud auth login
gcloud auth application-default login
gcloud config set project f1optimizer

# Install Python dependencies
pip install -r requirements-f1.txt

# Read processed data
python -c "
import pandas as pd
df = pd.read_parquet('gs://f1optimizer-data-lake/processed/laps_all.parquet')
print(df.shape)
"

# Submit a training job
bash ml/scripts/submit_training_job.sh --display-name your-name-experiment-1

# Trigger full pipeline
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d)

# Build all Docker images
gcloud builds submit --config cloudbuild.yaml . --project=f1optimizer
```

## Infrastructure

Infrastructure is Terraform-managed in `infra/terraform/`. To review or apply:

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan -var-file=dev.tfvars
terraform -chdir=infra/terraform apply -var-file=dev.tfvars
```

---

*Last Updated: 2026-02-20 — See `DEV_SETUP.md` for complete instructions.*
