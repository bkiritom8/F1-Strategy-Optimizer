# Team Documentation

Internal developer documentation for the F1 Strategy Optimizer project.
These files are for contributors — not part of the course submission.

## Contents

| File | Purpose |
|---|---|
| [`DEV_SETUP.md`](./DEV_SETUP.md) | Developer onboarding — GCP auth, GCS access, Vertex AI, env vars |
| [`ml_module_handoff.md`](./ml_module_handoff.md) | Full ML module handoff — Vertex AI components, training infra, commands |
| [`SETUP.md`](./SETUP.md) | Quick setup reference for new contributors |

## For the Course Submission

The graded submission lives in [`Data-Pipeline/`](../Data-Pipeline/).
Start there for:
- Airflow DAG (`Data-Pipeline/dags/f1_pipeline.py`)
- DVC pipeline (`dvc.yaml`, `.dvc/config`)
- Validation, anomaly detection, bias analysis scripts
- Local and GCP run instructions
- Cloud Composer and GCE VM deployment

## GCP Infrastructure Overview

All infrastructure is Terraform-managed in `infra/terraform/`:

| Resource | File | Description |
|---|---|---|
| GCS buckets, Cloud Run, Pub/Sub | `main.tf` | Core infra |
| Vertex AI IAM + pipeline runs | `vertex_ml.tf` | ML training infra |
| GCE VM (Airflow, legacy) | `airflow_vm.tf` | `f1-airflow-vm` — provisioned but not actively used |

## Docker Images

| Image | Dockerfile | Registry |
|---|---|---|
| `api:latest` | `docker/Dockerfile.api` | Artifact Registry |
| `ml:latest` | `docker/Dockerfile.ml` | Artifact Registry |
| `ingest:latest` | `docker/Dockerfile.ingest` | Artifact Registry |

## Cross-References

- Architecture → [`docs/architecture.md`](../docs/architecture.md)
- ML models → [`docs/models.md`](../docs/models.md)
- Bias analysis → [`docs/bias.md`](../docs/bias.md)
- Monitoring → [`docs/monitoring.md`](../docs/monitoring.md)
- Training pipeline → [`docs/training-pipeline.md`](../docs/training-pipeline.md)
- Frontend → [`frontend/README.md`](../frontend/README.md)
