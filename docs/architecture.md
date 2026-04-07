# System Architecture and Deployment

**Last Updated**: 2026-04-07

## Overview

The F1 Strategy Optimizer is a production-grade system built on Google Cloud Platform, designed for real-time race strategy recommendations with <500ms P99 latency. Infrastructure is fully managed by Terraform and deployed to `us-central1`. Race/ML data lives in GCS. User accounts and audit records live in Firestore (Native mode).

## High-Level Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                     INGEST LAYER                               │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────┐                                               │
│  │ Jolpica API│──────────┐                                    │
│  │ (1950-2026)│          │                                    │
│  └────────────┘          ▼                                    │
│                  Cloud Run Ingest Jobs (ingest/)               │
│  ┌────────────┐  9 parallel tasks (CLOUD_RUN_TASK_INDEX 0–8) │
│  │ FastF1 SDK │          │                                    │
│  │ (2018-2026)│  Task 0–7: fastf1_worker (one year each)     │
│  └────────────┘  Task 8:  historical_worker (1950–2017)       │
│                           │                                    │
│                           ▼                                    │
│         gs://f1optimizer-data-lake/raw/       (51 files, 6 GB)│
│         gs://f1optimizer-data-lake/telemetry/ (per-year)      │
│         gs://f1optimizer-data-lake/historical/(per-season)    │
│                           │                                    │
│              pipeline/scripts/csv_to_parquet.py               │
│                           ▼                                    │
│         gs://f1optimizer-data-lake/processed/ (10 files, 1 GB)│
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  STREAMING LAYER                               │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────┐         ┌─────────────────┐                  │
│  │ Live       │────────>│   Pub/Sub       │                  │
│  │ Telemetry  │         │ f1-telemetry-   │                  │
│  └────────────┘         │ stream-dev      │                  │
│                         └─────────────────┘                  │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                   ML LAYER                                     │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  Vertex AI KFP Pipeline (5-step DAG)                         │
│  ml/dag/f1_pipeline.py + ml/dag/pipeline_runner.py           │
│                                                                │
│  validate_data                                                 │
│    └─> feature_engineering                                     │
│          ├─> train_strategy    (XGBoost+LightGBM, 4×VM×T4)  │
│          └─> train_pit_stop   (LSTM+MirroredStrategy, 4×T4) │
│                ├─> eval_strategy  (parallel)                  │
│                └─> eval_pit_stop  (parallel)                  │
│                      └─> deploy                               │
│                                                                │
│  Artifacts promoted to: gs://f1optimizer-models/              │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  CI / CD LAYER                                 │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  GitHub push (pipeline branch)                                 │
│    ├─> GitHub Actions (.github/workflows/ci.yml)              │
│    │   lint / security / test / integration / docker-build /  │
│    │   terraform-validate / docs / rl-smoke-test /            │
│    │   all-checks-passed                                       │
│    └─> Cloud Build (cloudbuild.yaml) — 20-min timeout         │
│         Build api:latest + ml:latest + ingest:latest           │
│         Train 6 Vertex AI Custom Jobs                          │
│         Validate metrics + bias check + model registry         │
│         Push → us-central1-docker.pkg.dev/f1optimizer/        │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  FRONTEND LAYER                                │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  React 19 + TypeScript (frontend/)                            │
│  Vite 6 · Tailwind CSS · Zustand · Recharts                   │
│  Deployed on Firebase Hosting (f1optimizer GCP project)       │
│  Auto-deploy on every git push via GitHub Actions CI/CD       │
│                                                                │
│  Routes:  / (Race Command Center)                             │
│           /drivers   /strategy   /ai   /circuits              │
│           /analysis  /admin (password-protected MLOps)        │
│                                                                │
│  3-tier fallback: Cloud Run → static JSON → mock constants    │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                     RAG LAYER                                  │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  rag/chunker.py   ← GCS Parquet/CSV rows → Documents         │
│       │                                                        │
│  rag/document_fetcher.py  ← FIA regulations + circuit guides  │
│       │                                                        │
│  rag/embedder.py  ← Vertex AI text-embedding-004 (768-dim)   │
│       │                                                        │
│  Vertex AI Vector Search  ← streaming upsert                  │
│       │                                                        │
│  rag/retriever.py ← top-k retrieval + Gemini 2.5 Flash        │
│       │                                                        │
│  FastAPI /rag/query + /rag/health                             │
│                                                                │
│  Metadata: gs://f1optimizer-models/rag/metadata.json          │
│  Ingestion: python rag/ingestion_job.py (one-time + refresh)  │
│  Lazy init: returns [] / 503 if index env vars not set        │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  SERVING LAYER                                 │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  FastAPI (Cloud Run) — f1-strategy-api-dev                    │
│  https://f1-strategy-api-dev-694267183904.us-central1.run.app │
│  <500ms P99                                                    │
│                                                                │
│  Loads models from gs://f1optimizer-models/ at startup.       │
│  Falls back to rule-based strategy if models not promoted.    │
│                                                                │
│  Key endpoints:                                               │
│  GET  /health            — health check                       │
│  POST /recommend         — strategy recommendations (<500ms)  │
│  POST /rag/query         — natural-language F1 Q&A (RAG)      │
│  GET  /rag/health        — RAG configuration status           │
│  POST /llm/chat          — Gemini 2.5 Flash + ML bridge +     │
│                            two-layer semantic cache           │
│  POST /users/register    — create account (PBKDF2-SHA256)     │
│  POST /users/login       — authenticate, returns JWT          │
│  GET  /users/me          — current user profile               │
│  GET  /users/me/data     — GDPR data export                   │
│  DELETE /users/me        — GDPR erasure                       │
│  PUT  /users/me/password — change password                    │
│  GET  /admin/users       — list all users (admin only)        │
│  GET  /admin/dashboard   — system metrics (admin only)        │
│  GET  /docs              — interactive API documentation      │
│                                                                │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                MONITORING & OPERATIONS                         │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  Cloud Logging   │   Cloud Monitoring   │   Vertex AI Expts  │
│                                                                │
│  Alerting via f1-alerts-dev Pub/Sub topic                     │
└───────────────────────────────────────────────────────────────┘
```

## GCP Components

### Data Storage: GCS

All F1 data is stored in Google Cloud Storage.

| Bucket | Contents |
|---|---|
| `gs://f1optimizer-data-lake/raw/` | 51 source CSV files, 6.0 GB (Jolpica + FastF1) |
| `gs://f1optimizer-data-lake/processed/` | 10 Parquet files, 1.0 GB (ML-ready) |
| `gs://f1optimizer-data-lake/telemetry/` | Per-year FastF1 telemetry Parquet (ingest workers) |
| `gs://f1optimizer-data-lake/historical/` | Jolpica 1950–2017 per-season Parquet (ingest workers) |
| `gs://f1optimizer-data-lake/status/` | Ingest progress markers (`progress.json`, `task_N.done`) |
| `gs://f1optimizer-models/` | Promoted model artifacts |
| `gs://f1optimizer-training/` | Checkpoints, feature exports, pipeline artifacts |
| `gs://f1optimizer-pipeline-runs/` | KFP pipeline run roots |
| `gs://f1-optimizer-terraform-state/` | Terraform remote state |

### Processed Parquet Files

| File | Rows | Description |
|---|---|---|
| `laps_all.parquet` | 93,372 | Lap data 1996–2025 (Jolpica) |
| `telemetry_all.parquet` | 30,477,110 | FastF1 telemetry 2018–2025 |
| `telemetry_laps_all.parquet` | 92,242 | FastF1 session laps |
| `circuits.parquet` | 78 | Circuit master list |
| `drivers.parquet` | 100 | Driver master list |
| `pit_stops.parquet` | 11,077 | Pit stop records |
| `race_results.parquet` | 7,600 | Race results 1950–2026 |
| `lap_times.parquet` | 56,720 | Aggregated lap times |
| `fastf1_laps.parquet` | 92,242 | FastF1 lap data 2018–2026 |
| `fastf1_telemetry.parquet` | 90,302 | FastF1 telemetry summary |

### Reading Data

```python
import pandas as pd

# ADC credentials required — see DEV_SETUP.md §2
laps         = pd.read_parquet("gs://f1optimizer-data-lake/processed/laps_all.parquet")
telemetry    = pd.read_parquet("gs://f1optimizer-data-lake/processed/telemetry_all.parquet")
race_results = pd.read_parquet("gs://f1optimizer-data-lake/processed/race_results.parquet")
circuits     = pd.read_parquet("gs://f1optimizer-data-lake/processed/circuits.parquet")
```

### User Store: Firestore

User accounts and audit records are stored in Firestore (Native mode, `nam5`, OPTIMISTIC concurrency). Provisioned by `infra/terraform/firestore.tf`.

| Collection | Contents |
|---|---|
| `users/{username}` | Profile: username, email, full_name, role, disabled, created_at, consent_at |
| `user_credentials/{username}` | Password hash only (PBKDF2-HMAC-SHA256, 260k iterations, 32-byte salt) |
| `audit_log/{auto_id}` | GDPR append-only audit: event, username, SERVER_TIMESTAMP |

Key design decisions:
- **Atomic registration**: `@firestore.transactional` checks username uniqueness and creates profile + credentials in one transaction — safe for 100+ concurrent registrations
- **Batch auth read**: `db.get_all([user_ref, cred_ref])` fetches profile and credentials in a single round trip
- **GDPR erasure**: transactionally deletes both `users/` and `user_credentials/` documents, then appends an erasure record to `audit_log/`
- **Separate collections**: credentials are never returned by user-facing read operations

### Ingest Layer: Cloud Run Jobs

Data ingestion runs as Cloud Run Jobs. The dispatcher `ingest/task.py` reads `CLOUD_RUN_TASK_INDEX` and routes to the appropriate worker:

| Task Index | Worker | Data |
|---|---|---|
| 0–7 | `fastf1_worker.py` | FastF1 telemetry for years 2018–2025 |
| 8 | `historical_worker.py` | Jolpica race results, lap times, pit stops 1950–2017 |

Supporting workers:
- `lap_times_worker.py` — Jolpica paginated lap times (rate-limited to 450 req/hr)
- `gap_worker.py` — Targeted backfill for 5 known data-gap scenarios

Design patterns:
- **Idempotent**: every worker checks GCS before downloading
- **Infinite backoff**: retries forever on transient errors (60s → 3600s cap)
- **Atomic progress**: `ingest/progress.py` uses GCS generation-match for lock-free concurrent writes
- **Structured logging**: JSON logs → Cloud Logging auto-parsed

### Data Sources

**Jolpica** (`ingest/historical_worker.py`, `ingest/lap_times_worker.py`):
- Base URL: `https://api.jolpi.ca/ergast/f1`
- Coverage: 1950–2026, 1,300+ races
- Rate limit: 500 req/hr (workers enforce ≥8s between requests)

**FastF1** (`ingest/fastf1_worker.py`):
- Coverage: 2018–2026, all session types (FP1–FP3, Q, Sprint, Race)
- 10 Hz telemetry: throttle, speed, brake, DRS, gear
- Session types adjust by format year (conventional / sprint_qualifying / sprint)

### Streaming Layer (Pub/Sub)

Pub/Sub topics provisioned for live telemetry and pipeline events:

| Topic | Purpose |
|---|---|
| `f1-race-events-dev` | Race status updates, pipeline triggers |
| `f1-telemetry-stream-dev` | Live car telemetry |
| `f1-predictions-dev` | Strategy outputs + pipeline stage status |
| `f1-alerts-dev` | System alerts and training job status |

### ML Layer: Vertex AI

**Training**: Vertex AI Custom Jobs via `ml/scripts/submit_training_job.sh`

**Pipeline**: Vertex AI Pipelines (KFP v2) — 5-step DAG:
```
validate_data
    └──> feature_engineering
             ├──> train_strategy_predictor   (XGBoost + LightGBM)
             └──> train_pit_stop_optimizer   (LSTM + MirroredStrategy)
                       ├──> evaluate_strategy
                       └──> evaluate_pit_stop
                                   └──> deploy
```

**Cluster configs** (`ml/distributed/cluster_config.py`):

| Profile | Machine | GPUs | Workers | Use Case |
|---|---|---|---|---|
| `VERTEX_T4` | `n1-standard-4` | 1× T4 | 1 | Default for experiments |
| `SINGLE_NODE_MULTI_GPU` | `n1-standard-16` | 4× T4 | 1 | Full PitStopOptimizer training |
| `MULTI_NODE_DATA_PARALLEL` | `n1-standard-8` | 1× T4 each | 4 | Large dataset sharding |
| `HYPERPARAMETER_SEARCH` | `n1-standard-4` | 0 | 8 | HP sweep via Vertex AI Vizier |
| `CPU_DISTRIBUTED` | `n1-highmem-16` | 0 | 8 | Feature engineering |

**Service Account**: `f1-training-dev@f1optimizer.iam.gserviceaccount.com`
**Roles**: `storage.objectAdmin`, `aiplatform.user`, `aiplatform.customCodeServiceAgent`

### LLM Chat: `/llm/chat`

`POST /llm/chat` provides Gemini 2.5 Flash strategy chat enriched with live ML model predictions and served through a two-layer semantic cache.

**ML Model Bridge** (`src/llm/model_bridge.py`):
- Lazily loads 6 model bundles from `gs://f1optimizer-models/<name>/model.pkl` at first call
- Builds a minimal single-row DataFrame from `race_inputs`, filling missing features with sensible defaults
- Runs all 6 models and returns a human-readable predictions dict injected into the Gemini prompt
- Silently skips any model that fails to load or predict

**Two-Layer Semantic Cache** (`src/llm/cache.py`):

| Layer | Class | Threshold | TTL | Scope |
|---|---|---|---|---|
| 1 | `GenericCache` | cosine ≥ 0.85 | permanent | 20 pre-warmed generic F1 Q&A |
| 2 | `RealtimeCache` | cosine ≥ 0.88 | 3 minutes | bucketed by driver + lap//3 + tire_age//5 + compound + position |

- Layer 1 is pre-warmed at API startup in a daemon background thread
- Layer 2 detects cache invalidation on tire compound change (pit stop) or safety car flag change
- Embeddings use Vertex AI `text-embedding-004` (768-dim)
- **TurboQuant compression** (`src/llm/turboquant.py`): 768-dim float32 embeddings are product-quantized into compact codes via `TurboQuant_prod`, reducing cache memory footprint with configurable accuracy/compression trade-off

### Model Serving: FastAPI on Cloud Run

**Service**: `f1-strategy-api-dev` (`us-central1`)
**URL**: `https://f1-strategy-api-dev-694267183904.us-central1.run.app`
**Image**: `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api:latest`
**Resources**: min instances 0 (scale-to-zero), max 3, CPU throttling enabled; 512 Mi memory, 1 vCPU

The API loads model artifacts from `gs://f1optimizer-models/` at startup and falls
back to rule-based strategy recommendations when promoted models are not yet available.

See SERVING LAYER diagram above for endpoint list.

### CI/CD

**GitHub Actions** (`.github/workflows/ci.yml`) — triggered on push to `pipeline`, `main`, `develop`, `claude/**`:

| Job | What |
|---|---|
| `lint` | Black, MyPy |
| `security` | Bandit + Safety CVE scan |
| `test` | pytest unit tests + Codecov coverage |
| `integration-test` | pytest integration tests |
| `docker-build` | Matrix build: api / ml / ingest |
| `terraform-validate` | fmt check, init, validate |
| `docs` | mkdocs build |
| `rl-smoke-test` | 2000-step PPO smoke test (path-gated) |
| `rl-env-validation` | Gymnasium API compliance check |
| `all-checks-passed` | Gating job |

**Cloud Build** (`cloudbuild.yaml`) — triggered on push to `pipeline` (20-min timeout, `LEGACY` logging):
1. Build `api:latest`, `ml:latest` with `$COMMIT_SHA` + `latest` tags (parallel)
2. Submit 6 Vertex AI Custom Jobs (`train_<model>.py`), poll until completion
3. Validate model metrics against thresholds via Vertex AI Experiments
4. Check bias slice disparity across seasons / circuits / compounds
5. Push models to Vertex AI Model Registry
6. Rollback check — compare vs champion metrics in GCS
7. **test-rag** — run RAG unit tests (`tests/unit/rag/`, ≥60% coverage, `rag/ingestion_job.py` omitted)
8. Push images to `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/`

### Infrastructure: Terraform

All GCP resources are managed by Terraform in `infra/terraform/`.
Remote state: `gs://f1-optimizer-terraform-state/`.

```bash
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan -var-file=dev.tfvars
terraform -chdir=infra/terraform apply -var-file=dev.tfvars
```

## Environment Variables

Required for API (`src/api/main.py`):

```bash
GOOGLE_CLOUD_PROJECT=f1optimizer
PROJECT_ID=f1optimizer
REGION=us-central1
TRAINING_BUCKET=gs://f1optimizer-training
MODELS_BUCKET=gs://f1optimizer-models
DATA_BUCKET=gs://f1optimizer-data-lake
```

Required for ingest workers (`ingest/task.py`):
```bash
CLOUD_RUN_TASK_INDEX=0        # Set automatically by Cloud Run
GCS_BUCKET=f1optimizer-data-lake
```

See `docs/DEV_SETUP.md` §9 for the full list.

## Performance Targets

| Metric | Target |
|---|---|
| API P99 Latency | <500ms |
| System Uptime (race weekends) | 99.5% |
| Podium Accuracy | ≥70% |
| Winner Accuracy | ≥65% |
| Cost per Prediction | <$0.001 |
| Monthly Budget | <$70 |

## Known Gaps

1. `predict()` raises `NotImplementedError` in `ml/models/strategy_predictor.py` and `ml/models/pit_stop_optimizer.py` — API falls back to rule-based logic (the 6 new `ml/models/*.py` wrappers are separate)
2. `ml/training/distributed_trainer.py` imports `ray` but Ray is not in `docker/requirements-ml.txt`
3. Monitoring dashboards and alerting policies not yet created
4. Monitoring dashboards and alerting policies not yet created (Cloud Monitoring)
