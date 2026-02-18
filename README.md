# F1 Strategy Optimizer - Local Development Pipeline

Production-grade F1 race strategy system with full local testing capabilities.

## Features

- [OK] **Data Ingestion**: Ergast API + FastF1 telemetry
- [OK] **Processing**: Airflow DAGs with operational guarantees
- [OK] **Storage**: Cloud SQL PostgreSQL 15 (private VPC, automated backups)
- [OK] **Messaging**: Pub/Sub event streaming
- [OK] **Compute**: Dataflow pipeline orchestration
- [OK] **ML Infrastructure**: Distributed training skeleton
- [OK] **Security**: IAM/RBAC simulation + HTTPS
- [OK] **CI/CD**: GitHub Actions with testing
- [OK] **Cross-Platform**: Windows, Linux, macOS support

## Quick Start

### Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine (Linux)
- Docker Compose v2.0+
- Python 3.10+
- 8GB RAM minimum

### Local Development (All Platforms)

```bash
# 1. Clone and navigate
cd test

# 2. Create Python virtual environment
# Linux/macOS:
python3 -m venv venv
source venv/bin/activate

# Windows (PowerShell):
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements-f1.txt

# 4. Start local infrastructure
docker-compose -f docker-compose.f1.yml up -d

# 5. Initialize database
python scripts/init_db.py

# 6. Run sample DAG
airflow dags test f1_data_ingestion 2024-01-01

# 7. Run tests
pytest tests/ -v

# 8. Access services
# Airflow UI: http://localhost:8080 (admin/admin)
# Monitoring: http://localhost:3000 (admin/admin)
# API Docs: http://localhost:8000/docs
```

### Production Deployment (GCP)

```bash
# 1. Authenticate with GCP
gcloud auth login
gcloud auth application-default login
gcloud config set project <your-project-id>

# 2. Create Terraform state bucket (once, before terraform init)
gsutil mb -p f1optimizer gs://f1-optimizer-terraform-state
gsutil versioning set on gs://f1-optimizer-terraform-state

# 3. Initialize Terraform
cd terraform
terraform init
terraform plan -var-file=dev.tfvars
terraform apply -var-file=dev.tfvars

# 4. Deploy DAGs
./scripts/deploy_dags.sh

# 5. Configure secrets
gcloud secrets create ergast-api-key --data-file=secrets/ergast.key
```

## Architecture

```
+----------------------------------------------------------+
|                    Data Sources                          |
|              Ergast API  |  FastF1                       |
+------------+------------------------+--------------------+
             |                        |
             v                        v
+----------------------------------------------------------+
|              Airflow DAG Orchestrator                    |
|   +---------------+  +---------------+  +------------+  |
|   |  Ingestion    |  | Preprocessing |  |  Training  |  |
|   |   Tasks       |  |    Tasks      |  |   Tasks    |  |
|   +---------------+  +---------------+  +------------+  |
+------------+---------------------------------------------+
             |
             v
+----------------------------------------------------------+
|                 Message Bus (Pub/Sub)                    |
+------------+---------------------------------------------+
             |
             v
+----------------------------------------------------------+
|              Dataflow Processing                         |
|         (Validation, Enrichment, Routing)                |
+------------+---------------------------------------------+
             |
             v
+----------------------------------------------------------+
|                 Data Store                               |
|          Cloud SQL PostgreSQL 15 (Private VPC)           |
+------------+---------------------------------------------+
             |
             v
+----------------------------------------------------------+
|         Distributed ML Training Infrastructure           |
|     (Ray Cluster, Model Registry, Feature Store)         |
+----------------------------------------------------------+
```

## Directory Structure

```
test/
+-- airflow/
|   +-- dags/              # Airflow DAG definitions
|   +-- plugins/           # Custom Airflow plugins
|   +-- config/            # Airflow configuration
+-- src/
|   +-- ingestion/         # Data ingestion modules
|   +-- preprocessing/     # Data cleaning and feature engineering
|   +-- dataflow/          # Apache Beam pipelines
|   +-- ml/                # ML training infrastructure
|   +-- api/               # FastAPI service
|   +-- common/            # Shared utilities
|   +-- mocks/             # Mock GCP services for local dev
+-- terraform/             # Infrastructure as Code
+-- docker/                # Dockerfiles for all services
+-- tests/                 # Pytest test suite
+-- scripts/               # Utility scripts
+-- .github/workflows/     # CI/CD pipelines
+-- docs/                  # Technical documentation
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run specific test suites
pytest tests/test_ingestion.py -v
pytest tests/test_dags.py -v
pytest tests/test_dataflow.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Integration tests (requires Docker)
pytest tests/integration/ -v --docker

# Load tests
locust -f tests/load/locustfile.py
```

## Monitoring and Observability

### Metrics Tracked
- DAG run duration, success/failure rates
- Task-level execution time, retry counts
- API latency (P50, P95, P99)
- Data pipeline throughput
- Cost per DAG run
- Model training metrics

### Alerts
- DAG failures (Slack/PagerDuty)
- SLA violations (>5min late)
- Cost threshold exceeded
- API error rate >5%

## Performance Targets

| Metric | Target | Current |
|--------|--------|---------|
| API P99 Latency | <500ms | - |
| End-to-End Latency | <5s | - |
| System Uptime | 99.5% | - |
| Cost per Prediction | <$0.001 | - |
| Podium Accuracy | >=70% | - |
| Winner Accuracy | >=65% | - |

## License

MIT License

---

**Status**: Terraform infrastructure complete - Cloud SQL provisioned, IAM bindings in place
**Last Updated**: 2026-02-18
**Branch**: `main`
