# F1 Strategy Optimizer

Production-grade real-time F1 race strategy system: pit stop timing, tyre compound selection, driving mode, brake bias, and overtake decisions. Driver-aware recommendations using **76 years of F1 data (1950–2026)**. Target: **<500ms P99 latency**.

---

## Table of Contents

- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [ML Models](#ml-models)
- [Quick Start](#quick-start)
- [Module Index](#module-index)
- [Data Pipeline](#data-pipeline)
- [API Endpoints](#api-endpoints)
- [CI/CD](#cicd)
- [Infrastructure](#infrastructure)
- [Known Gaps](#known-gaps)
- [Common Commands](#common-commands)

---

## Architecture

```
Jolpica API (1950–2026)          FastF1 (2018–2026, 10Hz)
         │                                │
         └──────────────┬─────────────────┘
                        ↓
              GCS: f1optimizer-data-lake/raw/
                        ↓
              pipeline/scripts/csv_to_parquet.py
                        ↓
              GCS: f1optimizer-data-lake/processed/
                        ↓
              ml/preprocessing/preprocess_data.py
                        ↓
              GCS: f1optimizer-data-lake/ml_features/
                        ↓
              Vertex AI Pipelines (KFP v2)
                        ↓
         ┌──────────────┴──────────────────┐
         │                                 │
  Vertex AI Training Jobs          RAG Vector Index
  (6 supervised + PPO RL)     (Vertex AI Vector Search)
         │                                 │
  GCS: f1optimizer-models/                 │
         │                                 │
         └──────────────┬──────────────────┘
                        ↓
            FastAPI on Cloud Run (f1-strategy-api-dev)
            api:latest — loads models from GCS at startup
                        ↓
            React Frontend (Firebase Hosting)
            Apex Intelligence — frontend/
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Data sources** | Jolpica API (`api.jolpi.ca/ergast/f1`, 1950–2026), FastF1 (2018–2026, 10Hz) |
| **Storage** | GCS: `f1optimizer-data-lake` (raw + processed + ml_features), `f1optimizer-models`, `f1optimizer-training` |
| **ML pipeline** | Vertex AI Pipelines (KFP v2), `f1-pipeline-trigger` Cloud Run Job |
| **ML training** | Vertex AI Custom Training, SA `f1-training-dev`, bucket `gs://f1optimizer-training` |
| **ML models** | 6 supervised ensembles (XGBoost/LightGBM/CatBoost) + PPO RL agent (Stable-Baselines3) |
| **LLM** | Gemini Pro via Vertex AI — strategy chat + parse-strategy endpoints |
| **RAG** | Vertex AI Vector Search + `text-embedding-004` (768-dim) + LangChain |
| **Serving** | FastAPI on Cloud Run `f1-strategy-api-dev` (`api:latest`) |
| **Simulation** | Monte Carlo race simulation via SSE stream + Redis frame cache |
| **Frontend** | React 19 + TypeScript, Vite 6, Tailwind, Zustand — Firebase Hosting |
| **Auth** | JWT + Firestore-backed sessions |
| **Infrastructure** | Terraform in `infra/terraform/`, budget $70/month hard cap |
| **CI/CD** | GitHub Actions + Cloud Build (branches: `main`, `pipeline`) |

---

## ML Models

| Model | Algorithm | Test Metric | Output |
|---|---|---|---|
| Tire Degradation | XGBoost + LightGBM | MAE=0.285s, R²=0.850 | Degradation rate per lap |
| Driving Style | LightGBM + XGBoost | F1=0.800 | Style class |
| Safety Car | LightGBM + XGBoost | F1=0.920 | Deployment probability |
| Pit Window | XGBoost + LightGBM | MAE=1.116 laps, R²=0.968 | Optimal lap range |
| Overtake Probability | Random Forest (calibrated) | F1=0.326 | Per-position probability |
| Race Outcome | CatBoost + LightGBM | Acc=0.790, F1=0.778 | Final position distribution |
| RL Race Strategy | PPO (Stable-Baselines3) | — | `models/rl/final_policy.zip` |

**Training split**: 2018–2021 train / 2022–2023 val / 2024 test

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- GCP project `f1optimizer` with ADC configured

```bash
# Authenticate with GCP
gcloud auth application-default login
gcloud config set project f1optimizer

# Run the frontend
cd frontend && npm install && npm run dev
# → http://localhost:3001

# Run the backend (requires ADC + Redis for simulation)
pip install -r requirements-api.txt
uvicorn src.api.main:app --reload --port 8000
```

---

## Module Index

| Module | README | Purpose |
|---|---|---|
| [`frontend/`](./frontend/README.md) | ✓ | React 19 + TypeScript dashboard (Apex Intelligence), Firebase Hosting |
| [`src/`](./src/README.md) | ✓ | FastAPI backend — strategy endpoints, Gemini LLM, simulation SSE, auth |
| [`ml/`](./ml/README.md) | ✓ | ML pipeline — 6 supervised models + PPO RL agent, KFP DAG, Vertex AI |
| [`ingest/`](./ingest/README.md) | ✓ | Cloud Run Jobs — Jolpica + FastF1 data acquisition into GCS |
| [`pipeline/`](./pipeline/README.md) | ✓ | Data transformation, backfill, GCS validation, offline RL simulator |
| [`rag/`](./rag/README.md) | ✓ | RAG — natural-language F1 Q&A via Vertex AI Vector Search + Gemini |
| [`infra/`](./infra/README.md) | ✓ | Terraform IaC — all GCP resources, $70/month budget cap |
| [`scripts/`](./scripts/README.md) | ✓ | Operational scripts — backfill, deploy, cleanup, track paths, RAG reindex |
| [`tests/`](./tests/README.md) | ✓ | Unit + integration + E2E tests (backend, ML, frontend) |
| [`docs/`](./docs/README.md) | ✓ | Technical docs — architecture, ML handoff, setup guides |
| `Data-Pipeline/` | — | Legacy pipeline artifacts — **DO NOT DELETE** |

---

## Data Pipeline

```
1. Ingest        ingest/ workers → GCS raw/ (Jolpica 1950–2026, FastF1 2018–2026)
2. Transform     pipeline/scripts/csv_to_parquet.py → GCS processed/
3. Features      ml/preprocessing/preprocess_data.py → GCS ml_features/
4. Train         Vertex AI Custom Jobs (6 models + PPO) → GCS f1optimizer-models/
5. Serve         FastAPI Cloud Run loads promoted models at startup
```

**Data volumes**: 51 raw files (6.0 GB), 10+ Parquet + ml_features files in GCS

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/simulate/race` | Start Monte Carlo race simulation |
| `GET` | `/api/v1/simulate/race/stream` | SSE stream of simulation frames |
| `POST` | `/api/v1/llm/chat` | Strategy chat via Gemini Pro |
| `GET` | `/api/v1/rag/query` | Natural-language F1 history query |
| `POST` | `/api/v1/auth/register` | User registration (with email verification) |
| `POST` | `/api/v1/auth/login` | JWT login |

Base URL (production): `https://f1-strategy-api-dev-[hash].run.app`

---

## CI/CD

### GitHub Actions (`.github/workflows/ci.yml`)

Runs on every push:

- Python: flake8 lint, mypy type-check, pytest unit tests, Bandit security scan
- Terraform: `terraform validate`
- RL smoke test: single-episode PPO rollout
- Frontend: ESLint + Vitest

### Cloud Build (`cloudbuild.yaml`)

Triggers on push to `pipeline` branch:

1. Build `api:latest`, `ml:latest`, `ingest:latest` (Docker images)
2. Train 6 supervised models on Vertex AI
3. Validate model artifacts
4. Bias check
5. Push to Artifact Registry

Settings: `LEGACY` logging, `REGIONAL_USER_OWNED_BUCKET`, 20-minute timeout, `COMMIT_SHA` image tags.

**Branches**:

| Branch | Purpose |
|---|---|
| `main` | Stable production — triggers Firebase Hosting deploy |
| `pipeline` | CI/CD — triggers Cloud Build |
| `ml-dev` | ML experimentation |

---

## Infrastructure

All GCP infrastructure is managed via Terraform in `infra/terraform/`:

| Resource | Name | Purpose |
|---|---|---|
| GCS | `f1optimizer-data-lake` | Raw + processed + ml_features |
| GCS | `f1optimizer-models` | Promoted model artifacts |
| GCS | `f1optimizer-training` | Training outputs + PPO checkpoints |
| Cloud Run | `f1-strategy-api-dev` | FastAPI backend |
| Cloud Run Job | `f1-ingest` | Data ingest workers |
| Cloud Run Job | `f1-pipeline-trigger` | KFP pipeline trigger |
| Firestore | `f1optimizer` | Auth sessions + config |
| Vertex AI | Pipelines + Vector Search | KFP orchestration + RAG |
| IAM | — | Least-privilege per service |

**Budget**: $70/month hard cap enforced via GCP budget alerts.

---

## Known Gaps

1. `predict()` raises `NotImplementedError` in `ml/models/strategy_predictor.py` and `ml/models/pit_stop_optimizer.py` — API falls back to rule-based logic (the 6 new model classes in `ml/models/` are separate from these legacy wrappers)
2. `ml/training/distributed_trainer.py` imports `ray` — Ray is not in `docker/requirements-ml.txt`
3. Monitoring dashboards and alerting policies not yet created
4. Simulation and RL endpoints are external. `SIMULATION_ENDPOINT` env var configures the external service — rule-based fallback activates if unavailable
5. `car_performance.json` must be regenerated via `build_car_performance.py` when new race seasons complete

---

## Common Commands

```bash
# Build all Docker images (api, ml, ingest)
gcloud builds submit --config cloudbuild.yaml . --project=f1optimizer

# Train individual models
python ml/training/train_tire_degradation.py
python ml/training/train_rl.py --timesteps 1000000 --n-envs 4

# Submit GPU training job to Vertex AI
bash ml/scripts/submit_training_job.sh --display-name your-name-v1

# Trigger full ML pipeline
gcloud run jobs execute f1-pipeline-trigger --region=us-central1 --project=f1optimizer

# Compile + submit KFP pipeline manually
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d-%H%M%S)

# Run ML tests on Vertex AI
python ml/tests/run_tests_on_vertex.py

# Frontend dev server
cd frontend && npm install && npm run dev   # → http://localhost:3001

# Verify GCS data lake
gsutil ls gs://f1optimizer-data-lake/processed/

# Deploy infrastructure
terraform -chdir=infra/terraform plan -var-file=dev.tfvars
terraform -chdir=infra/terraform apply -var-file=dev.tfvars

# Rebuild car performance table (after new season data lands)
python pipeline/scripts/build_car_performance.py \
  --input gs://f1optimizer-data-lake/processed/race_results.parquet \
  --output frontend/public/data/car_performance.json

# Test simulation coordinator locally (requires Redis)
REDIS_HOST=localhost python -m pytest tests/unit/simulation/ -v

# Trigger a simulation manually (dev)
curl -X POST http://localhost:8000/api/v1/simulate/race \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"race_id":"monaco_2025","total_laps":78}'

# Data backfill
python scripts/backfill_jolpica.py --season 2024

# GCP cleanup (dry run first)
python scripts/gcp_cleanup.py --dry-run
```

---

**Status**: Stable Production | **Branch**: `main` | **Last Updated**: 2026-03-25
