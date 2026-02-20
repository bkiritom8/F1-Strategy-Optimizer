# System Architecture and Deployment

**Last Updated**: 2026-02-18

## Overview

The F1 Strategy Optimizer is a production-grade system built on Google Cloud Platform, designed for real-time race strategy recommendations with <500ms P99 latency. Infrastructure is fully managed by Terraform and deployed to `us-central1`.

## High-Level Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                     DATA LAYER                                 │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────┐         ┌─────────────────┐                  │
│  │ Jolpica API│────────>│  Cloud SQL      │                  │
│  │ (1950-2026)│         │  PostgreSQL 15  │                  │
│  └────────────┘         │  (lap_features) │                  │
│                         └────────┬────────┘                  │
│  ┌────────────┐                 │                            │
│  │ FastF1 SDK │────────>┌───────▼────────┐                  │
│  │ (2018-2026)│         │  Preprocessing  │                  │
│  └────────────┘         │    Pipeline     │                  │
│                         └───────┬────────┘                  │
│                                 │                            │
│                         ┌───────▼────────┐                  │
│                         │ Feature Store   │                  │
│                         │  (Cloud SQL)    │                  │
│                         └────────────────┘                  │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  STREAMING LAYER                               │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────┐         ┌─────────────────┐                  │
│  │ Live       │────────>│   Pub/Sub       │                  │
│  │ Telemetry  │         │   (10K msg/sec) │                  │
│  └────────────┘         └────────┬────────┘                  │
│                                   │                            │
│                         ┌─────────▼────────┐                  │
│                         │   Dataflow       │                  │
│                         │   (Beam Pipeline)│                  │
│                         └─────────┬────────┘                  │
│                                   │                            │
│                         ┌─────────▼────────┐                  │
│                         │ Real-Time        │                  │
│                         │ Features (SQL)   │                  │
│                         └────────────────┘                  │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                   ML LAYER                                     │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│  │   Driver   │  │   Tire     │  │   Fuel     │             │
│  │  Profiles  │  │ Degradation│  │Consumption │             │
│  │  (Static)  │  │  (XGBoost) │  │   (LSTM)   │             │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘             │
│        │               │               │                      │
│        └───────────────┴───────────────┘                      │
│                        │                                       │
│  ┌────────────┐  ┌─────▼──────┐  ┌────────────┐             │
│  │Brake Bias  │  │ Monte Carlo│  │  Driving   │             │
│  │(LinReg)    │  │ Simulator  │  │   Style    │             │
│  │            │  │(10K runs)  │  │(DecisionTree)│           │
│  └────────────┘  └────────────┘  └────────────┘             │
│                                                                │
│                   Vertex AI Model Registry                     │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  CI / CD LAYER                                 │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  GitHub push                                                   │
│  (pipeline branch) ──> Cloud Build ──> Artifact Registry      │
│                         (cloudbuild.yaml)  (Docker image)      │
│                                │                               │
│                                v                               │
│                         Cloud Run deploy                       │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  SERVING LAYER                                 │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│                    ┌─────────────────┐                        │
│                    │   FastAPI       │                        │
│                    │   (Cloud Run)   │                        │
│                    │   <500ms P99    │                        │
│                    └────────┬────────┘                        │
│                             │                                  │
│              ┌──────────────┼──────────────┐                 │
│              │              │              │                  │
│      ┌───────▼──────┐ ┌────▼─────┐ ┌─────▼──────┐          │
│      │ React        │ │  Mobile  │ │  Internal  │          │
│      │ Dashboard    │ │   API    │ │   Tools    │          │
│      └──────────────┘ └──────────┘ └────────────┘          │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                MONITORING & OPERATIONS                         │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│  │   Cloud    │  │   Cloud    │  │   Drift    │             │
│  │  Logging   │  │ Monitoring │  │ Detection  │             │
│  └────────────┘  └────────────┘  └────────────┘             │
│                                                                │
│          Alerting -> Email (bhargavsp01@gmail.com)            │
└───────────────────────────────────────────────────────────────┘
```

## GCP Components

### Data Storage: Cloud SQL (PostgreSQL 15)

**Instance**: `f1-optimizer-dev` (`db-f1-micro`, `us-central1`)
**Database**: `f1_data`
**User**: `f1_api` (password auto-generated, stored in Secret Manager)
**Connectivity**: Private IP via VPC peering (no public IP)
**SSL**: `ENCRYPTED_ONLY`
**Backups**: Automated daily, deletion protection enabled

**Key Tables** (see `src/database/schema.sql`):
- `lap_features` — Historical race/lap data from Jolpica (1950-2026)
- `telemetry_features` — FastF1 10 Hz telemetry (2018-2026)
- `driver_profiles` — Extracted behavioral profiles (200+ drivers)

### Data Ingestion

**Sources**: Jolpica REST API + FastF1 Python library
**Orchestration**: Airflow DAG (`airflow/dags/f1_data_ingestion.py`)
**Execution**: Cloud Run Job (`f1-data-ingestion`, max timeout 3600 s)
**Auto-trigger**: Terraform `null_resource` fires `gcloud run jobs execute` after infrastructure is provisioned

**Jolpica ingestion** (`src/ingestion/ergast_ingestion.py`):
```python
import requests
import psycopg2
import os

def download_ergast_data(year_start=1950, year_end=2026):
    """Download race data from Jolpica API and insert into Cloud SQL."""

    base_url = "https://api.jolpi.ca/ergast/f1"
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        port=int(os.environ.get("DB_PORT", 5432)),
    )
    cursor = conn.cursor()

    for year in range(year_start, year_end + 1):
        response = requests.get(f"{base_url}/{year}.json")
        races = response.json()["MRData"]["RaceTable"]["Races"]

        for race in races:
            cursor.execute(
                """
                INSERT INTO lap_features (race_id, year, round, circuit_id, date)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (race_id) DO NOTHING
                """,
                (race["raceId"], year, race["round"], race["Circuit"]["circuitId"], race["date"]),
            )

        import time
        time.sleep(1)  # Rate limiting

    conn.commit()
    cursor.close()
    conn.close()
```

**FastF1 ingestion** (`src/ingestion/fastf1_ingestion.py`):
```python
import fastf1
import psycopg2
import os

def download_fastf1_telemetry(year: int, race_name: str):
    """Download telemetry for a single race and insert into Cloud SQL."""

    session = fastf1.get_session(year, race_name, "R")
    session.load()

    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    cursor = conn.cursor()

    laps = session.laps
    for _, lap in laps.iterrows():
        tel = lap.get_telemetry()
        for _, row in tel.iterrows():
            cursor.execute(
                """
                INSERT INTO telemetry_features
                  (race_id, driver_id, lap_number, timestamp, throttle, speed, brake, drs)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    f"{year}_{race_name}",
                    lap["Driver"],
                    int(lap["LapNumber"]),
                    row.name,
                    row["Throttle"],
                    row["Speed"],
                    row["Brake"],
                    row["DRS"],
                ),
            )

    conn.commit()
    cursor.close()
    conn.close()
```

**Error handling**: Retry on HTTP 5xx with exponential backoff; cache intermediate results locally.

### Streaming Pipeline (Real-Time)

**Technology**: Apache Beam on Dataflow
**Purpose**: Process live telemetry during race weekends for real-time recommendations
**Topics** (Pub/Sub):
- `f1-race-events` — Race status updates
- `f1-telemetry-stream` — Live car telemetry
- `f1-predictions` — Strategy outputs
- `f1-alerts` — System alerts

**Pipeline** (`src/dataflow/`):
```python
import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions

def run_pipeline():
    options = PipelineOptions(
        runner="DataflowRunner",
        project="f1optimizer",
        region="us-central1",
        streaming=True,
    )

    with beam.Pipeline(options=options) as p:
        (
            p
            | "Read from Pub/Sub" >> beam.io.ReadFromPubSub(
                subscription="projects/f1optimizer/subscriptions/telemetry-sub"
            )
            | "Parse JSON" >> beam.Map(lambda x: __import__("json").loads(x))
            | "Extract Features" >> beam.Map(process_telemetry)
            | "Write to Cloud SQL" >> beam.ParDo(CloudSQLWriteDoFn())
        )
```

**Windowing**: 5-second tumbling windows
**Scaling**: Auto-scales 1-10 workers based on Pub/Sub backlog

### ML Layer

4 specialized models + Monte Carlo simulator (see `docs/models.md`):
- Tire Degradation (XGBoost) — MAE <50 ms
- Fuel Consumption (LSTM) — RMSE <0.5 kg/lap
- Brake Bias (Linear Regression) — ±1% accuracy
- Driving Style (Decision Tree) — ≥75% accuracy

**Artifacts**: GCS bucket `gs://f1optimizer-models/` (versioned)
**Registry**: Vertex AI Model Registry (project: `f1optimizer`, region: `us-central1`)

### Model Serving: FastAPI on Cloud Run

**Service**: `f1-strategy-api-dev` (`us-central1`)
**Image**: `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api:latest`
**Resources**: 512 Mi memory, 1 vCPU
**Scaling**: min=0 (dev), max=3; timeout=60 s
**Environment variables**: `DB_HOST`, `DB_NAME`, `DB_PORT`, `PUBSUB_PROJECT_ID`

**Endpoints**:

`POST /recommend` — main pit wall endpoint (<500 ms P99):
```python
from fastapi import FastAPI
from pydantic import BaseModel
import joblib, json, os

app = FastAPI()

class RaceContext(BaseModel):
    driver_id: str
    lap: int
    position: int
    tire_age: int
    tire_compound: str
    fuel_remaining: float
    gap_to_leader: float
    circuit_id: str

@app.post("/recommend")
async def get_recommendation(context: RaceContext):
    driver_profile = load_driver_profile(context.driver_id)
    pit_strategies = monte_carlo_optimization(
        context.dict(), driver_profile, models, n_scenarios=5000
    )
    driving_mode = models["driving_style"].predict([...])
    brake_bias = models["brake_bias"].predict([...])

    return {
        "pit_strategy": {
            "recommended_lap": pit_strategies[0]["pit_lap"],
            "compound": pit_strategies[0]["compound"],
            "win_probability": pit_strategies[0]["win_prob"],
        },
        "driving_mode": driving_mode,
        "brake_bias": brake_bias,
        "confidence": 0.87,
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
```

### CI/CD: Cloud Build

**Trigger**: Every push to the `pipeline` branch of `bkiritom8/F1-Strategy-Optimizer`
**Config**: `cloudbuild.yaml` (project root)
**Output**: Docker image pushed to Artifact Registry (`f1-optimizer` repository)

```yaml
# cloudbuild.yaml
steps:
  - name: "gcr.io/cloud-builders/docker"
    args:
      - "build"
      - "--platform"
      - "linux/amd64"
      - "-t"
      - "us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api:latest"
      - "-f"
      - "docker/Dockerfile.api"
      - "."

images:
  - "us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api:latest"
```

**IAM**: Cloud Build SA (`{PROJECT_NUMBER}@cloudbuild.gserviceaccount.com`) has `roles/artifactregistry.writer`.

## Infrastructure as Code

All resources are managed in `terraform/main.tf`. Key resources:

| Resource | Name | Purpose |
|----------|------|---------|
| `google_sql_database_instance` | `f1-optimizer-dev` | PostgreSQL 15, private IP |
| `google_cloud_run_v2_service` | `f1-strategy-api-dev` | FastAPI serving |
| `google_cloud_run_v2_job` | `f1-data-ingestion` | Batch data ingestion |
| `google_artifact_registry_repository` | `f1-optimizer` | Docker images |
| `google_cloudbuild_trigger` | `f1-api-docker-build` | CI on pipeline branch |
| `google_pubsub_topic` (x4) | `f1-race-events`, etc. | Streaming |
| `google_storage_bucket` (x2) | `f1optimizer-data-lake`, `f1optimizer-models` | GCS storage |
| `google_secret_manager_secret` | `f1-db-password` | PostgreSQL password |
| `google_compute_global_address` | VPC peering range /16 | Cloud SQL private IP |

**Providers**: `google ~>5.0`, `random ~>3.0`, `null ~>3.0`
**Backend**: `gs://f1-optimizer-terraform-state`

### Deploy Infrastructure

```bash
# One-time: create Terraform state bucket
gsutil mb -p f1optimizer gs://f1-optimizer-terraform-state
gsutil versioning set on gs://f1-optimizer-terraform-state

# Authenticate
gcloud auth application-default login

# Initialize and apply
terraform -chdir=terraform init
terraform -chdir=terraform apply -var-file=dev.tfvars
```

### Build and Push Docker Image

```bash
# Option 1: via Cloud Build (automatic on pipeline branch push)
git push origin pipeline

# Option 2: manual Cloud Build submission
gcloud builds submit --config cloudbuild.yaml . --project=f1optimizer

# Option 3: local build and push (requires auth)
gcloud auth configure-docker us-central1-docker.pkg.dev
docker build --platform linux/amd64 \
  -t us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api:latest \
  -f docker/Dockerfile.api .
docker push us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api:latest
```

### Run Data Ingestion (Cloud Run Job)

```bash
# Execute the ingestion job (async by default)
gcloud run jobs execute f1-data-ingestion \
  --region=us-central1 \
  --project=f1optimizer

# Wait for completion
gcloud run jobs execute f1-data-ingestion \
  --region=us-central1 \
  --project=f1optimizer \
  --wait
```

## Security

### Service Accounts and IAM

| Service Account | Role | Purpose |
|----------------|------|---------|
| `f1-airflow-dev` | `roles/pubsub.admin` | DAG orchestration |
| `f1-dataflow-dev` | `roles/dataflow.worker` | Dataflow pipeline |
| `f1-api-dev` | `roles/cloudsql.client` | DB access from Cloud Run |
| `f1-api-dev` | `roles/run.invoker` | Allow self-invocation |
| Cloud Build SA | `roles/artifactregistry.writer` | Push Docker images |
| Compute SA | `roles/secretmanager.secretAccessor` | Read DB password |

**Least Privilege**: Each SA has only the permissions required for its function.

### Data Encryption

- **At Rest**: GCP default AES-256 encryption for Cloud SQL, GCS, Secret Manager
- **In Transit**: TLS 1.3 for all API calls; Cloud SQL `ENCRYPTED_ONLY` SSL mode
- **Secrets**: PostgreSQL password auto-generated (32 chars) by Terraform, stored in Secret Manager

### Authentication

- API keys / Cloud IAP for dashboard access
- Service-to-service via service account identity
- No public unauthenticated access (except `/health`)

## Cost

**Hard budget cap**: $70/month (enforced in `dev.tfvars` and `prod.tfvars`)
**Target**: <$0.001 per prediction

| Service | Dev Usage | Estimated Cost |
|---------|-----------|----------------|
| Cloud SQL (`db-f1-micro`) | Always on | ~$15/month |
| Cloud Run | On demand (min=0) | ~$3/month |
| Pub/Sub | 1M msg/month | ~$1/month |
| Dataflow | Race weekends only | ~$10/month |
| GCS (data-lake + models) | 50 GB | ~$3/month |
| Artifact Registry | Image storage | ~$2/month |
| Cloud Build | On push | ~$2/month |
| Secret Manager | 1 secret | <$1/month |
| **Total (dev)** | | **~$37/month** |

**Cost controls** (configured in Terraform):
- Cloud Run min instances = 0 in dev (no idle cost)
- Dataflow auto-scales to 0 workers between races
- GCS lifecycle rules: 30d → Nearline, 365d → Coldline

## Disaster Recovery

**Backup strategy**:
- Cloud SQL: Automated daily backups (30-day retention)
- Model artifacts: Versioned in GCS (`f1optimizer-models` bucket)
- Code: GitHub (`main` branch, protected)
- Infrastructure: Terraform state in GCS (versioning enabled)

**Recovery Time Objective (RTO)**: <30 minutes
**Recovery Point Objective (RPO)**: <24 hours

**Failure scenarios**:

| Scenario | Detection | Recovery |
|----------|-----------|---------|
| API downtime | Cloud Monitoring uptime check | Auto-restart Cloud Run; traffic failover |
| Cloud SQL failure | Health check | Restore from automated backup |
| Model degradation | Drift alert | Rollback to previous Vertex AI model version |
| Data pipeline failure | Dataflow lag alert | Restart Cloud Run Job; re-ingest from Jolpica |
| Budget overrun | Cost alert >$60 | Scale down Dataflow/Cloud Run instances |

---

**See Also**:
- CLAUDE.md: High-level overview and project status
- docs/data.md: Data pipeline details
- docs/models.md: Model architectures
- docs/monitoring.md: Operational monitoring
