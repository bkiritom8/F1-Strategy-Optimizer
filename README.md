# F1 Complete Race Strategy Optimizer

> **Production-grade, real-time Formula 1 race strategy intelligence — powered by 76 years of F1 data, six machine learning models, a reinforcement learning agent, a Retrieval-Augmented Generation (RAG) knowledge base, and a Monte Carlo race simulator. Driver-aware recommendations with a <500ms P99 latency target, deployed on Google Cloud.**

---

## What We Are Building

Formula 1 race strategy is one of the most consequential and time-pressured decision-making environments in professional sport. A single pit stop decision — timed a lap too early or a lap too late — can swing a race result by multiple positions. The compounding complexity of tyre degradation curves, safety car probability windows, competitor undercut threat, fuel load, brake temperature, and real-time weather creates a decision space that is difficult even for experienced race engineers armed with telemetry and decades of institutional knowledge.

**The F1 Complete Race Strategy Optimizer** is a full-stack AI system designed to replicate and exceed the reasoning quality of an F1 strategy wall — in real time, for any driver, at any circuit, under live race conditions. The system ingests raw telemetry and historical race data at the 10Hz level, runs it through a seven-model ML ensemble, and surfaces actionable strategy decisions through a modern web dashboard. It is not a toy. It is architected as a production service: containerized, deployed to Cloud Run, continuously trained on Vertex AI, tested across 87 automated test cases, and monitored through a CI/CD pipeline on Google Cloud Build.

This is the kind of system that a real F1 team's data science group would build. The goal is to demonstrate that an end-to-end production ML system — from raw data acquisition to a live user interface — can be built as a solo engineering project, at scale, with correct infrastructure choices.

---

## The Problem Space

### Why F1 Strategy is Hard

F1 race strategy involves simultaneous optimization across several competing dimensions:

- **Tyre compounds**: Soft, Medium, Hard, and Intermediate compounds degrade at different rates depending on circuit surface abrasion, ambient temperature, driving style, and fuel load. The optimal pit window is a function of the degradation curve intersecting the time cost of pit entry/exit (~20–25 seconds).
- **Undercut / overcut mechanics**: Pitting one lap before a competitor forces them onto degraded rubber while you gain fresh tyre pace. Predicting whether an undercut will succeed requires estimating both cars' pace deltas over the in-lap, pit stop, and out-lap cycle.
- **Safety car windows**: A well-timed safety car can allow a "free" pit stop — zero time loss on track. Predicting safety car deployment probability during a window dramatically changes expected pit stop value.
- **Driver adaptation**: Different drivers degrade tyres differently, carry brake bias differently, and respond differently to undercut pressure. A strategy that works for Max Verstappen will not necessarily work for a driver with a different throttle application pattern.
- **Overtaking difficulty**: Circuit-specific overtake probability changes whether the optimal strategy is to track-position-defend or to take a strategic undercut gamble. Monaco and Monza require fundamentally different approaches.

These variables interact non-linearly. No simple rule-based heuristic handles all of them. This is precisely the problem that machine learning, reinforcement learning, and simulation are well-suited to solve.

---

## What the System Does

At a high level, the system does five things:

### 1. Continuous Data Acquisition
The ingest layer pulls from two primary sources: the **Jolpica API** (the successor to the Ergast F1 API), which exposes structured race results, qualifying times, pit stop records, and constructor standings going back to **1950**, and **FastF1**, which provides lap-by-lap telemetry channels — speed, throttle, brake, DRS, tyre compound, sector times — sampled at **10Hz** from the 2018 season onward. This data is staged into **Google Cloud Storage** as raw CSV files (6.0 GB, 51 files) and then processed into columnar Parquet format for efficient querying.

### 2. Feature Engineering and ML Training
The preprocessing pipeline extracts machine learning features from the raw data: degradation rates per compound per driver per circuit, safety car frequency distributions by lap and session type, pit window optimality labels, overtake probability by circuit layout and pace delta, and driver-level style fingerprints. These features feed into **six supervised ensemble models** — combining XGBoost, LightGBM, CatBoost, and Random Forest — trained and validated on Vertex AI Custom Training jobs with GPU acceleration.

### 3. Reinforcement Learning Strategy Agent
In addition to the supervised models, a **Proximal Policy Optimization (PPO) agent** trained via Stable-Baselines3 learns an end-to-end race strategy policy. The RL environment (`F1RaceEnv`) exposes 29 observation features and 7 discrete actions (pit stop variants, push modes, conservation modes), and the agent is trained via reward shaping that aligns with final race position. The trained policy (`models/rl/final_policy.zip`) can be queried at inference time to suggest the globally optimal strategy sequence — not just the locally optimal next decision.

### 4. Real-Time Strategy Recommendations via FastAPI
The backend is a **FastAPI** service deployed on **Cloud Run** that loads all model artifacts from GCS at startup. On each request it assembles the current race state — lap number, compound age, gap to competitor, safety car status — and routes it through the appropriate model(s) to generate a strategy recommendation with a confidence score. All endpoints are authenticated with JWT, responses are cached via Redis, and the P99 latency target is **<500ms** under sustained load.

### 5. Intelligent Chat, RAG Knowledge Base, and Monte Carlo Simulation
Beyond direct ML inference, the system includes three intelligence layers:

- **LLM Strategy Chat**: A Gemini Pro-backed chatbot endpoint that answers natural-language strategy questions ("Should I undercut Leclerc at lap 32 on a Medium that's done 18 laps?") with context-aware responses grounded in the race state.
- **RAG F1 Knowledge Base**: Vertex AI Vector Search indexes 76 years of F1 race history as 768-dimensional embeddings (via `text-embedding-004`). When a user asks a historical or comparative question ("How often does a safety car appear at Monaco in the last 20 laps?"), the RAG pipeline retrieves the most relevant race records and feeds them into the LLM context window for grounded generation.
- **Monte Carlo Race Simulator**: A probabilistic simulation engine that runs hundreds of race scenarios in parallel, streams results back to the frontend via **Server-Sent Events (SSE)**, and renders them as a live animated 2D track map. The simulator accounts for stochastic safety car deployment, tyre degradation variance, and competitor strategy perturbations.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          DATA SOURCES                                │
│                                                                      │
│   Jolpica API (api.jolpi.ca/ergast/f1)      FastF1 (10Hz telemetry) │
│   1950–2026 race results, pit stops,        2018–2026: speed,        │
│   qualifying, standings, constructors       throttle, brake, DRS,    │
│                                             sector times, compound   │
└───────────────────────────┬──────────────────────────┬──────────────┘
                            │                          │
                            ▼                          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   INGEST LAYER (ingest/)                             │
│   Cloud Run Jobs — `f1-ingest` — pulls from both sources into GCS   │
│   GCS: gs://f1optimizer-data-lake/raw/  (51 CSV files, 6.0 GB)      │
└───────────────────────────────────────────┬─────────────────────────┘
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   TRANSFORMATION (pipeline/scripts/)                 │
│   csv_to_parquet.py → GCS: processed/ (columnar Parquet)            │
│   preprocess_data.py → GCS: ml_features/ (ML-ready features)        │
└───────────────────────────────────────────┬─────────────────────────┘
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  ML TRAINING (ml/ + Vertex AI)                       │
│                                                                      │
│   Vertex AI Pipelines (KFP v2) — 5-step parallel DAG                │
│                                                                      │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│   │ Tire Degrad. │  │ Driving Style│  │  Safety Car  │             │
│   │ XGB+LGBM     │  │ LGBM+XGB     │  │ LGBM+XGB     │             │
│   │ MAE=0.285s   │  │ F1=0.800     │  │ F1=0.920     │             │
│   └──────────────┘  └──────────────┘  └──────────────┘             │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│   │ Pit Window   │  │  Overtake    │  │ Race Outcome │             │
│   │ XGB+LGBM     │  │ RF Calibrated│  │ CatB+LGBM    │             │
│   │ R²=0.968     │  │ F1=0.326     │  │ Acc=0.790    │             │
│   └──────────────┘  └──────────────┘  └──────────────┘             │
│                                                                      │
│   PPO RL Agent (Stable-Baselines3) — 29 obs, 7 actions              │
│   → GCS: gs://f1optimizer-models/ (promoted artifacts)              │
└───────────────────────────────────────────┬─────────────────────────┘
                                            │
                         ┌──────────────────┴──────────────────┐
                         │                                     │
                         ▼                                     ▼
┌──────────────────────────────────┐   ┌───────────────────────────────┐
│     RAG KNOWLEDGE BASE (rag/)    │   │    FASTAPI BACKEND (src/)     │
│                                  │   │                               │
│  Vertex AI Vector Search          │   │  Cloud Run: f1-strategy-api   │
│  text-embedding-004 (768-dim)     │   │  Port 8000 — api:latest       │
│  76 years of race history indexed │   │  JWT auth, Redis cache        │
│  LangChain retrieval chains      │   │  Loads all models from GCS    │
│  Gemini Pro generation           │   │  at startup                   │
└──────────────────┬───────────────┘   └─────────────────┬─────────────┘
                   │                                     │
                   └──────────────────┬──────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────┐
│               REACT FRONTEND (frontend/) — Apex Intelligence         │
│                                                                      │
│  React 19 + TypeScript + Vite 6 + Tailwind CSS + Zustand            │
│  Firebase Hosting — https://f1optimizer.web.app                      │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────────┐  │
│  │  Strategy       │  │  Race Simulator │  │  LLM Chat +        │  │
│  │  Dashboard      │  │  (2D track map, │  │  RAG Q&A           │  │
│  │  (pit window,   │  │   animated cars,│  │  (Gemini Pro,      │  │
│  │   tyre recs,    │  │   SSE stream)   │  │   grounded in 76yr │  │
│  │   driver style) │  │                 │  │   F1 history)      │  │
│  └─────────────────┘  └─────────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Technology | Details |
|---|---|---|
| **Data — historical** | Jolpica API | 1950–2026: race results, pit stops, standings, constructors |
| **Data — telemetry** | FastF1 | 2018–2026: 10Hz speed, throttle, brake, DRS, tyre compound, sector times |
| **Storage** | Google Cloud Storage | `f1optimizer-data-lake` (raw + processed + ml_features), `f1optimizer-models`, `f1optimizer-training` |
| **ML pipeline** | Vertex AI Pipelines (KFP v2) | 5-step parallel DAG, `f1-pipeline-trigger` Cloud Run Job |
| **ML training** | Vertex AI Custom Training | T4 GPU jobs, SA `f1-training-dev`, `gs://f1optimizer-training` |
| **Supervised models** | XGBoost, LightGBM, CatBoost, Random Forest | 6 ensemble models (see ML Models section) |
| **RL agent** | Stable-Baselines3 (PPO) | Gymnasium environment, 29 observations, 7 discrete actions |
| **LLM** | Gemini Pro via Vertex AI | Strategy chat (`/api/v1/llm/chat`) + parse-strategy endpoints |
| **RAG** | Vertex AI Vector Search + LangChain | `text-embedding-004`, 768-dim, 76yr F1 history indexed |
| **Backend** | FastAPI + uvicorn | Cloud Run `f1-strategy-api-dev`, loads models from GCS at startup |
| **Simulation** | Monte Carlo (Python) | SSE stream via Redis frame cache + `coordinator.py` |
| **Frontend** | React 19 + TypeScript, Vite 6, Tailwind, Zustand | Firebase Hosting, <http://localhost:3001> in dev |
| **Auth** | JWT + Firestore | Firestore-backed sessions, email verification |
| **Infrastructure** | Terraform | `infra/terraform/`, $70/month hard cap, GCP budget alerts |
| **Containerization** | Docker | `api:latest`, `ml:latest`, `ingest:latest` — Artifact Registry |
| **CI/CD** | GitHub Actions + Google Cloud Build | Lint, type-check, test, security scan, model training, push |

---

## ML Models

The system uses seven machine learning models working in concert. Six are supervised ensembles; one is a reinforcement learning policy.

| Model | Algorithm | Metric | What it predicts |
|---|---|---|---|
| **Tire Degradation** | XGBoost + LightGBM ensemble | MAE=0.285s, R²=0.850 | Per-lap pace loss rate for each compound, driver, circuit combination |
| **Driving Style** | LightGBM + XGBoost ensemble | F1=0.800 | Driver style class (aggressive, balanced, conservative) based on telemetry fingerprints |
| **Safety Car** | LightGBM + XGBoost ensemble | F1=0.920 | Probability of safety car deployment in the next N laps — used to value pit window timing |
| **Pit Window** | XGBoost + LightGBM ensemble | MAE=1.116 laps, R²=0.968 | Optimal pit lap range given current tyre age, degradation curve, and race context |
| **Overtake Probability** | Random Forest (Platt-calibrated) | F1=0.326 | Probability of completing an on-track pass at a given circuit position and pace delta |
| **Race Outcome** | CatBoost + LightGBM ensemble | Acc=0.790, F1=0.778 | Final position distribution — P(top 3), P(points), P(DNF) given current race state |
| **RL Race Strategy** | PPO (Stable-Baselines3) | Reward maximization | Globally optimal strategy sequence for the remainder of the race (pit timing + mode) |

**Training split**: 2018–2021 train / 2022–2023 validation / 2024 test

---

## Data

The dataset spans **76 years of Formula 1** (1950–2026):

- **Jolpica API**: Race results, qualifying times, lap times, pit stop records, driver standings, constructor standings, circuit metadata — structured JSON, paginated, ingested by Cloud Run Jobs into GCS raw CSVs.
- **FastF1**: Lap-by-lap car telemetry at 10Hz for all sessions from 2018 onward — speed trace, throttle position, brake pressure, gear, DRS, tyre compound per lap, sector and mini-sector times. This higher-resolution data is what enables driver-style modeling and accurate degradation curves.

**Volumes in GCS**:
- Raw: 51 CSV files, ~6.0 GB
- Processed (Parquet): 10+ columnar files
- ML features: partitioned Parquet ready for training

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/simulate/race` | Start a Monte Carlo race simulation, returns a session ID |
| `GET` | `/api/v1/simulate/race/stream` | SSE stream of simulation frames keyed to session ID |
| `POST` | `/api/v1/llm/chat` | Gemini Pro strategy chatbot — natural-language race strategy questions |
| `GET` | `/api/v1/rag/query` | Historical F1 Q&A via RAG pipeline (Vector Search + Gemini) |
| `POST` | `/api/v1/auth/register` | User registration with email verification |
| `POST` | `/api/v1/auth/login` | JWT login, returns access token |

Base URL (production): `https://f1-strategy-api-dev-[hash].run.app`

---

## Repo Structure

```
ml/                    All ML code — features, models, training, rl, dag, distributed, tests
  training/            6 supervised training scripts + train_rl.py (PPO)
  models/              6 model wrapper classes + base_model.py
  rl/                  RL infrastructure (environment, agent, state, adapters, reward)
  preprocessing/       FastF1 + race results feature engineering
  features/            Feature pipeline + GCS cache layer
  distributed/         Cluster configs + distribution strategies
  dag/                 KFP v2 pipeline + 6 components
  tests/               All ML tests (87 tests total)
frontend/              React 19 + TypeScript dashboard (Apex Intelligence)
pipeline/scripts/      Data scripts (csv_to_parquet.py, verify_upload.py, backfill_data.py)
rag/                   RAG pipeline — Vertex AI Vector Search, LangChain, embeddings
ingest/                Cloud Run Jobs — Jolpica + FastF1 data acquisition
src/                   FastAPI backend — routes, simulation coordinator, LLM, auth
infra/terraform/       All GCP infrastructure as code
docker/                Dockerfiles + pip requirements per image
tests/                 Unit + integration + E2E tests (backend, ML, frontend)
docs/                  Technical documentation
scripts/               Operational scripts — backfill, deploy, cleanup, reindex
```

Full module-level READMEs: [`frontend/`](./frontend/README.md), [`src/`](./src/README.md), [`ml/`](./ml/README.md), [`ingest/`](./ingest/README.md), [`pipeline/`](./pipeline/README.md), [`rag/`](./rag/README.md), [`infra/`](./infra/README.md), [`scripts/`](./scripts/README.md), [`tests/`](./tests/README.md), [`docs/`](./docs/README.md).

---

## CI/CD

### GitHub Actions (`.github/workflows/ci.yml`)

Triggered on every push. Runs:

- Python: `black` formatting, `flake8` lint, `mypy` type-check, `pytest` unit tests, `bandit` security scan
- Terraform: `terraform validate`
- RL smoke test: single-episode PPO rollout to verify agent loads and steps without error
- Frontend: ESLint + Vitest

### Cloud Build (`cloudbuild.yaml`)

Triggered on push to `pipeline` branch. Pipeline:

1. Build Docker images: `api:latest`, `ml:latest`, `ingest:latest`
2. Push to Artifact Registry with `COMMIT_SHA` tags
3. Train 6 supervised models on Vertex AI Custom Jobs
4. Validate model artifacts (format, metric thresholds)
5. Bias check (fairness evaluation across driver demographic groups)
6. Promote to `f1optimizer-models` GCS bucket

Settings: `LEGACY` logging, `REGIONAL_USER_OWNED_BUCKET`, 20-minute timeout.

**Branch strategy**:

| Branch | Purpose |
|---|---|
| `main` | Stable production — triggers Firebase Hosting deploy |
| `pipeline` | CI/CD — triggers Cloud Build (Docker build + model train) |
| `ml-dev` | ML experimentation — no CI trigger |

---

## Infrastructure

All GCP resources are managed via Terraform in `infra/terraform/`. Budget cap: **$70/month** enforced via GCP budget alerts.

| Resource | Name | Purpose |
|---|---|---|
| GCS | `f1optimizer-data-lake` | Raw CSVs + processed Parquet + ml_features |
| GCS | `f1optimizer-models` | Promoted model artifacts (all 7 models) |
| GCS | `f1optimizer-training` | Training outputs, PPO checkpoints |
| Cloud Run | `f1-strategy-api-dev` | FastAPI backend (api:latest, port 8000) |
| Cloud Run Job | `f1-ingest` | Jolpica + FastF1 data acquisition workers |
| Cloud Run Job | `f1-pipeline-trigger` | KFP pipeline trigger |
| Firestore | `f1optimizer` | Auth sessions + application config |
| Vertex AI | Pipelines + Vector Search | KFP orchestration + RAG embedding index |
| Artifact Registry | `f1optimizer` | Docker image storage |
| IAM | — | Least-privilege service accounts per workload |

---

## Quick Start

**Prerequisites**: Python 3.12+, Node.js 18+, GCP project `f1optimizer` with ADC configured.

```bash
# Authenticate with GCP
gcloud auth application-default login
gcloud config set project f1optimizer

# Run the frontend (no GCP required)
cd frontend && npm install && npm run dev
# → http://localhost:3001

# Run the backend (requires ADC + Redis for simulation)
pip install -r requirements-api.txt
uvicorn src.api.main:app --reload --port 8000
```

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

# Trigger full ML pipeline (KFP)
gcloud run jobs execute f1-pipeline-trigger --region=us-central1 --project=f1optimizer

# Compile + submit KFP pipeline manually
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d-%H%M%S)

# Run ML tests on Vertex AI
python ml/tests/run_tests_on_vertex.py

# Frontend dev server
cd frontend && npm install && npm run dev   # → http://localhost:3001

# Verify GCS data lake
gsutil ls gs://f1optimizer-data-lake/processed/

# Deploy infrastructure (show plan first)
terraform -chdir=infra/terraform plan -var-file=dev.tfvars
terraform -chdir=infra/terraform apply -var-file=dev.tfvars

# Rebuild year-aware car performance table (after new season data lands)
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

## Known Gaps

1. `predict()` raises `NotImplementedError` in `ml/models/strategy_predictor.py` and `ml/models/pit_stop_optimizer.py` — API falls back to rule-based logic. The 6 new model classes in `ml/models/` are separate from these legacy wrappers and are the active inference path.
2. `ml/training/distributed_trainer.py` imports `ray` — Ray is not in `docker/requirements-ml.txt`. Multi-node Ray training is disabled until Ray is added.
3. Monitoring dashboards and Cloud Monitoring alerting policies are not yet created.
4. Simulation and RL endpoints are external services. `SIMULATION_ENDPOINT` env var configures the external simulation service — rule-based fallback activates if the endpoint is unavailable.
5. `car_performance.json` must be regenerated via `build_car_performance.py` when new race seasons complete.

---

**Status**: Stable Production | **Branch**: `main` | **Last Updated**: 2026-04-07
