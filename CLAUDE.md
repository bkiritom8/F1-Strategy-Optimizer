# F1 Complete Race Strategy Optimizer - Project Memory

**Status**: Full ML pipeline complete — 6 supervised models + PPO RL agent trained, tested, deployed. React frontend live. CI/CD stable.
**Main branch**: `main` (stable) | **CI/CD branch**: `pipeline` (triggers Cloud Build) | **ML branch**: `ml-dev`
**Last Updated**: 2026-03-25

---

## Project Summary

Production-grade real-time F1 race strategy system: pit strategy, driving mode, brake bias, throttle/braking patterns, setup recommendations. Driver-aware recommendations using 76 years of F1 data (1950–2026). Target: <500ms P99 latency.

---

## Architecture

```
Jolpica + FastF1 → GCS (raw CSV) → csv_to_parquet.py → GCS (Parquet)
                                                               |
                                              ml/preprocessing/preprocess_data.py
                                                               |
                                              GCS (ml_features/ Parquet)
                                                               |
                                                    Feature Pipeline (KFP)
                                                               |
                                      Vertex AI Training Jobs (6 models + RL agent)
                                                               |
                                                  GCS (promoted models)
                                                               |
                                              FastAPI on Cloud Run (<500ms P99)
                                                               |
                                          React Frontend (Vercel) — frontend/
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Data sources | Jolpica API (`api.jolpi.ca/ergast/f1`, 1950–2026), FastF1 (2018–2026, 10Hz) |
| Storage | GCS: `f1optimizer-data-lake` (raw + processed + ml_features), `f1optimizer-models`, `f1optimizer-training` |
| ML pipeline | Vertex AI Pipelines (KFP v2), `f1-pipeline-trigger` Cloud Run Job |
| ML training | Vertex AI Custom Training, SA `f1-training-dev`, bucket `gs://f1optimizer-training` |
| ML models | 6 supervised ensembles (XGBoost/LightGBM/CatBoost) + PPO RL agent (Stable-Baselines3) |
| Serving | FastAPI on Cloud Run `f1-strategy-api-dev` (`api:latest`) |
| Frontend | React 19 + TypeScript, Vite 6, Tailwind, Zustand — deployed on Firebase Hosting (`frontend/`) |
| Infrastructure | Terraform in `infra/terraform/`, budget $70/month hard cap |
| CI/CD | GitHub Actions + Cloud Build (branches: `main`, `pipeline`) |

---

## Docker Images

| Image | Dockerfile | Purpose |
|---|---|---|
| `api:latest` | `docker/Dockerfile.api` | FastAPI server (uvicorn, port 8000) |
| `ml:latest` | `docker/Dockerfile.ml` | ML training (nvidia/cuda:11.8, no CMD — entry point set per job) |
| `ingest:latest` | `docker/Dockerfile.ingest` | Cloud Run ingest workers |

Cloud Build builds all three on every push to `pipeline`. Uses `LEGACY` logging with `REGIONAL_USER_OWNED_BUCKET`, 20-minute timeout.

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
infra/terraform/       All GCP infrastructure
docker/                Dockerfiles + requirements
src/                   Shared API code
tests/                 Unit + integration tests
docs/                  Technical documentation
```

---

## ML Models

| Model | Algorithm | Test Metric |
|---|---|---|
| Tire Degradation | XGBoost + LightGBM | MAE=0.285s, R²=0.850 |
| Driving Style | LightGBM + XGBoost | F1=0.800 |
| Safety Car | LightGBM + XGBoost | F1=0.920 |
| Pit Window | XGBoost + LightGBM | MAE=1.116 laps, R²=0.968 |
| Overtake Probability | Random Forest (calibrated) | F1=0.326 |
| Race Outcome | CatBoost + LightGBM | Acc=0.790, F1=0.778 |
| RL Race Strategy | PPO (Stable-Baselines3) | `models/rl/final_policy.zip` |

Training split: 2018–2021 train, 2022–2023 val, 2024 test.

---

## Key Files

| File | Purpose |
|---|---|
| `infra/terraform/main.tf` | All GCP infrastructure |
| `infra/terraform/vertex_ml.tf` | Vertex AI Pipeline IAM, APIs, trigger job |
| `pipeline/scripts/csv_to_parquet.py` | Convert raw CSVs → Parquet, upload to GCS |
| `pipeline/scripts/verify_upload.py` | Verify GCS data lake contents |
| `ml/preprocessing/preprocess_data.py` | FastF1 + race results feature engineering |
| `ml/dag/f1_pipeline.py` | KFP pipeline definition (5-step DAG) |
| `ml/dag/pipeline_runner.py` | Compile + submit + monitor pipeline |
| `ml/dag/components/` | 6 individual KFP components |
| `ml/distributed/cluster_config.py` | 5 named cluster configs (VERTEX_T4, single-GPU, multi-node, HP, CPU) |
| `ml/training/train_*.py` | Individual training scripts for each of the 6 supervised models |
| `ml/training/train_rl.py` | PPO RL agent training (Stable-Baselines3, Gymnasium) |
| `ml/rl/environment.py` | F1RaceEnv (29 obs features, 7 actions) |
| `ml/features/feature_store.py` | GCS Parquet → DataFrame (ADC only) |
| `ml/tests/run_tests_on_vertex.py` | Run all tests as Vertex AI Custom Job |
| `ml/scripts/submit_training_job.sh` | Submit Vertex AI Custom Job with T4 GPU |
| `cloudbuild.yaml` | Build images → train 6 models → validate → bias check → push to registry (20-min timeout) |
| `.github/workflows/ci.yml` | Lint, type-check, test, security scan, terraform validate, RL smoke test |
| `frontend/` | React 19 + TypeScript dashboard (Apex Intelligence), deployed on Firebase Hosting |
| `docs/DEV_SETUP.md` | Developer onboarding guide |
| `docs/ml_handoff.md` | Full ML handoff document |
| `src/simulation/coordinator.py` | Scenario hashing, Redis cache, background task dispatch |
| `src/simulation/streamer.py` | SSE frame generator from Redis list |
| `src/api/routes/simulate.py` | POST /simulate/race + GET /simulate/race/stream |
| `frontend/components/simulation/RaceSimulator.tsx` | 2D track map with animated car dots |
| `pipeline/scripts/build_car_performance.py` | One-time script: GCS parquet → year-aware car offsets |
| `frontend/public/data/car_performance.json` | Year-aware constructor performance offsets (2018–2025) |

---

## Component Status

| Phase | Status |
|---|---|
| GCP infra (Cloud Run, Vertex AI, GCS, IAM) | Complete |
| Data in GCS (raw + processed Parquet + ml_features) | Complete — 51 raw files (6.0 GB), 10 Parquet + ml_features |
| Distributed training configs + data sharding | Complete |
| KFP pipeline DAG (5-step, parallel training) | Complete |
| 6 supervised ML models | Complete — trained, tested, artifacts in `models/*.pkl` |
| PPO RL agent | Complete — trained, `models/rl/final_policy.zip` |
| Feature store + feature pipeline + preprocessing | Complete |
| ML tests (87 tests, run on Vertex AI) | Complete |
| FastAPI serving connected to promoted models | Complete — loads from GCS at startup, rule-based fallback |
| React frontend (Apex Intelligence) | Complete — `frontend/`, deployed on Firebase Hosting |
| CI/CD (GitHub Actions + Cloud Build) | Stable — COMMIT_SHA fixed, LEGACY logging, 20-min timeout |
| Monitoring dashboards + alerting | Not started |
| Monte Carlo simulation pipeline (coordinator, SSE, frontend) | Complete |

---

## Known Gaps

1. `predict()` raises `NotImplementedError` in `ml/models/strategy_predictor.py` and `ml/models/pit_stop_optimizer.py` — API falls back to rule-based logic (6 new model classes in `ml/models/` are separate from these legacy wrappers)
2. `ml/training/distributed_trainer.py` imports `ray` — Ray is not in `docker/requirements-ml.txt`
3. Monitoring dashboards and alerting policies not yet created
4. Simulation and RL endpoints are external (not owned by this repo). `SIMULATION_ENDPOINT` and RL endpoint URL are configured via env vars. Rule-based fallback activates if endpoints are unavailable.
5. `car_performance.json` must be regenerated via `build_car_performance.py` when new race seasons complete.

---

## Common Commands

```bash
# Build all images (api, ml, ingest)
gcloud builds submit --config cloudbuild.yaml . --project=f1optimizer

# Train individual models
python ml/training/train_tire_degradation.py
python ml/training/train_rl.py --timesteps 1000000 --n-envs 4

# Trigger full ML pipeline
gcloud run jobs execute f1-pipeline-trigger --region=us-central1 --project=f1optimizer

# Compile + submit pipeline manually
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d-%H%M%S)

# Submit GPU training job
bash ml/scripts/submit_training_job.sh --display-name your-name-v1

# Run ML tests on Vertex AI
python ml/tests/run_tests_on_vertex.py

# Frontend dev server
cd frontend && npm install && npm run dev  # → http://localhost:3001

# Verify GCS data
gsutil ls gs://f1optimizer-data-lake/processed/

# Deploy infrastructure (show plan first)
terraform -chdir=infra/terraform plan -var-file=dev.tfvars

# Build year-aware car performance table (run after new season data lands)
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
```

---

**Working Principles**: High-signal only in CLAUDE.md — details in `docs/`. Production-first. No BigQuery. No local testing.
**Compaction Protocol**: `/compact` every ~40 messages. Append session summary to `docs/progress.md`.
**Git Commits**: All commits must be authored as `bkiritom8 <bhargavsp01@gmail.com>`. Commit messages must be single-line only (no body, no bullet points, no multi-line descriptions).
