# F1 Strategy Optimizer

Production-grade real-time F1 race strategy system: pit strategy, tyre compound selection,
driving mode, and overtake decisions. Driver-aware recommendations using 76 years of F1 data
(1950–2026). Target: <500ms P99 latency.

## Features

- **Data**: Jolpica API (1950–2026) + FastF1 telemetry (2018–2026, 10Hz)
- **Ingest**: Cloud Run Jobs — 9 parallel tasks, one per year/epoch (`ingest/`)
- **Storage**: GCS — 51 raw files (6.0 GB CSV) + processed Parquet files (1.0 GB)
- **ML**: 6 XGBoost/LightGBM/CatBoost ensemble models + PPO reinforcement learning agent
- **RAG**: Natural-language Q&A over 76 years of F1 data — `rag/` (Vertex AI Vector Search + Gemini 1.5 Flash)
- **Training**: Vertex AI Custom Jobs + KFP Pipeline (5-step DAG) + Cloud Build CI/CD
- **Serving**: FastAPI on Cloud Run (<500ms P99) — `/recommend`, `/rag/query`, `/rag/health`
- **CI/CD**: GitHub Actions (lint, test, docker, terraform) + Cloud Build on `pipeline` branch (includes RAG test gate)

## Quick Start

### Prerequisites

- `gcloud` CLI (latest) — https://cloud.google.com/sdk/docs/install
- Python 3.10
- Terraform 1.5+
- Docker Desktop (for local development)

### Setup

```bash
git clone https://github.com/bkiritom8/F1-Strategy-Optimizer.git
cd F1-Strategy-Optimizer

pip install -r docker/requirements-api.txt

# Authenticate with GCP
gcloud auth login
gcloud auth application-default login
gcloud config set project f1optimizer
```

See [`team-docs/DEV_SETUP.md`](./team-docs/DEV_SETUP.md) for the complete developer onboarding guide.

## Architecture

```
Jolpica API (1950–2026)  ──┐
                            ├──> Cloud Run Ingest Jobs (ingest/)
FastF1 SDK (2018–2026)  ───┘   9 parallel tasks (0-8)
                                        │
                          gs://f1optimizer-data-lake/raw/
                                        │
                              pipeline/scripts/csv_to_parquet.py
                                        │
                          gs://f1optimizer-data-lake/processed/
                                   (10 Parquet files)
                                        │
                    ml/preprocessing/preprocess_data.py
                                        │
                    gs://f1optimizer-data-lake/ml_features/
                          (fastf1_features.parquet etc.)
                                        │
                    ┌───────────────────┴───────────────────┐
                    │                                       │
             Vertex AI Custom Jobs                  KFP Pipeline (v2)
          ml/training/train_*.py              ml/dag/f1_pipeline.py
          (6 models + RL agent)               (5-step DAG)
                    │                                       │
                    └───────────────────┬───────────────────┘
                                        │
                          gs://f1optimizer-models/
                                        │
                              FastAPI (Cloud Run)
                         f1-strategy-api-dev  <500ms P99
```

## Repository Structure

```
ingest/                  Cloud Run ingest workers
  task.py                Entrypoint — routes CLOUD_RUN_TASK_INDEX 0–8
  fastf1_worker.py       FastF1 telemetry per year (Tasks 0–7: 2018–2025)
  historical_worker.py   Jolpica historical data 1950–2017 (Task 8)
  lap_times_worker.py    Jolpica lap-by-lap times
  gap_worker.py          Targeted backfill
  progress.py            GCS-backed optimistic locking
  gcs_utils.py           Upload helpers
ml/                      All ML code
  training/              6 supervised training scripts + RL agent
    train_tire_degradation.py
    train_driving_style.py
    train_safety_car.py
    train_pit_window.py
    train_overtake_prob.py
    train_race_outcome.py
    train_rl.py          PPO reinforcement learning agent
  models/                Model wrapper classes
    base_model.py        Abstract base: GCS save/load, Pub/Sub, Cloud Logging
    tire_degradation_model.py
    driving_style_model.py
    safety_car_model.py
    pit_window_model.py
    overtake_prob_model.py
    race_outcome_model.py
  rl/                    RL infrastructure
    environment.py       F1RaceEnv (Gymnasium, 29 obs features, 7 actions)
    agent.py             F1StrategyAgent (PPO wrapper)
    state.py             State encoder
    model_adapters.py    Supervised model adapters for environment physics
    driver_profiles.py   Driver characteristic profiles
  preprocessing/
    preprocess_data.py   FastF1 + race results feature engineering
  features/
    feature_pipeline.py  GCS Parquet -> lap-by-lap state vectors
    feature_store.py     GCS cache layer
  distributed/
    cluster_config.py    5 named Vertex AI cluster profiles
    distribution_strategy.py  DataParallel/ModelParallel/HP strategies
    data_sharding.py     Cloud SQL -> GCS shards per worker
    aggregator.py        Best checkpoint -> GCS promotion + Pub/Sub
  dag/                   Vertex AI KFP v2 pipeline
    f1_pipeline.py       5-step @dsl.pipeline definition
    pipeline_runner.py   Compile -> GCS upload -> submit -> monitor
    components/          6 @dsl.component files
  plots/                 Evaluation plots (SHAP, HP sensitivity, confusion matrices)
  tests/
    test_models.py       31 tests: all 6 model wrappers (real GCS data)
    test_preprocessing.py  16 tests: preprocessing pipeline
    test_features.py     11 tests: feature store and pipeline
    test_distributed.py  25 tests: distributed infrastructure
    test_dag.py          4 tests: pipeline runner CLI
    run_tests_on_vertex.py  Submit test suite as Vertex AI Custom Job
models/                  Saved model artifacts (.pkl bundles)
  tire_degradation.pkl
  driving_style.pkl
  safety_car.pkl
  pit_window.pkl
  overtake_prob.pkl
  race_outcome.pkl
  rl/
    final_policy.zip     PPO policy
    final_vec_normalize.pkl  VecNormalize statistics
rag/                     RAG pipeline
  config.py              RagConfig (env vars + defaults)
  chunker.py             GCS Parquet/CSV rows → LangChain Documents
  document_fetcher.py    FIA regulations + circuit guides → Documents
  embedder.py            Vertex AI text-embedding-004 (768-dim)
  vector_store.py        Vertex AI Vector Search upsert/query + GCS metadata
  retriever.py           F1Retriever: top-k retrieval + Gemini generation
  ingestion_job.py       One-shot ingestion entry point (run manually)
pipeline/                Data management utilities
  scripts/               csv_to_parquet.py, backfill_data.py, verify_upload.py
  simulator/             Race simulator
  rl/                    RL experience builder
infra/terraform/         All GCP infrastructure (Terraform)
src/                     Shared code
  api/                   FastAPI application (main.py)
  ingestion/             Ergast/FastF1 ingestion classes + HTTP client
  preprocessing/         Schema validation, data quality, sanitisation
  security/              IAM simulator + HTTPS middleware
tests/                   Unit + integration tests
  unit/                  test_iam_simulator.py, test_rl_environment.py
docker/                  Dockerfiles + requirements
  Dockerfile.api         FastAPI server (port 8000)
  Dockerfile.ml          ML training (CUDA 11.8, no CMD)
  Dockerfile.ingest      Cloud Run ingest workers
  requirements-ml.txt
docs/                    Technical documentation
team-docs/               Internal team docs (DEV_SETUP, handoffs)
cloudbuild.yaml          CI/CD pipeline (build, train, validate, deploy)
.github/workflows/
  ci.yml                 Main CI (lint, test, docker, terraform)
  ml-train.yml           RL model CI (smoke test, env validation)
```

## ML Models

Six supervised models and one RL agent are trained and deployed:

| Model | Algorithm | Target | Test Metric |
|---|---|---|---|
| Tire Degradation | XGBoost + LightGBM | tyre_delta (lap time deviation) | MAE=0.285s, R2=0.850 |
| Driving Style | LightGBM + XGBoost | PUSH / BALANCE / NEUTRAL | F1=0.800 |
| Safety Car | LightGBM + XGBoost | pitted_under_sc (0/1) | F1=0.920 |
| Pit Window | XGBoost + LightGBM | laps_to_pit | MAE=1.116 laps, R2=0.968 |
| Overtake Probability | Random Forest (calibrated) | overtake_success (0/1) | F1=0.326 |
| Race Outcome | CatBoost + LightGBM | Podium / Points / Outside | Acc=0.790, F1=0.778 |
| RL Race Strategy | PPO (Stable-Baselines3) | Race strategy (pit/compound) | models/rl/ |

All models are trained on FastF1 data 2018-2025 with a temporal split: train 2018-2021,
val 2022-2023, test 2024.

## Docker Images

| Image | Registry | Used For |
|---|---|---|
| `api:latest` | Artifact Registry | Cloud Run serving |
| `ml:latest` | Artifact Registry | Vertex AI training jobs |
| `ingest:latest` | Artifact Registry | Cloud Run ingest workers |

Cloud Build builds and pushes all images with `$COMMIT_SHA` and `latest` tags on every push to `pipeline`.

## Data

All F1 data lives in GCS.

| Bucket Path | Contents |
|---|---|
| `gs://f1optimizer-data-lake/raw/` | 51 source CSVs, 6.0 GB |
| `gs://f1optimizer-data-lake/processed/` | 10 Parquet files, 1.0 GB |
| `gs://f1optimizer-data-lake/ml_features/` | Preprocessed feature Parquet files |
| `gs://f1optimizer-models/` | Promoted model artifacts + champion metrics |
| `gs://f1optimizer-training/` | Checkpoints, feature exports, pipeline runs |

```python
import pandas as pd

# Processed features (used by training scripts)
laps = pd.read_parquet("gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet")
results = pd.read_parquet("gs://f1optimizer-data-lake/ml_features/race_results_features.parquet")
```

## Training

```bash
# Train all supervised models individually
for MODEL in tire_degradation driving_style safety_car pit_window overtake_prob race_outcome; do
  python ml/training/train_${MODEL}.py
done

# Train RL agent
python ml/training/train_rl.py --timesteps 1000000 --n-envs 4

# Full KFP pipeline (5-step DAG on Vertex AI Pipelines)
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d-%H%M%S)

# Trigger via Cloud Run Job (automated)
gcloud run jobs execute f1-pipeline-trigger --region=us-central1 --project=f1optimizer

# Run ML tests on Vertex AI
python ml/tests/run_tests_on_vertex.py
```

## CI/CD Pipeline

The Cloud Build pipeline (`cloudbuild.yaml`) runs on every push to `pipeline`:

1. **build-api / build-ml** — build Docker images with `$COMMIT_SHA` tag
2. **train-models** — submit 6 Vertex AI Custom Jobs, poll until completion
3. **validate-models** — check test metrics against thresholds via Vertex AI Experiments
4. **check-bias** — check slice disparity across seasons/circuits/compounds
5. **push-models-registry** — upload to Vertex AI Model Registry
6. **rollback-check** — compare vs champion metrics in GCS, block on >5% regression
7. **push-api / push-ml** — push images to Artifact Registry

GitHub Actions (`ci.yml`) runs lint, security scan, unit tests, Docker builds, and Terraform validation on every push.

The RL model has a dedicated workflow (`ml-train.yml`) that runs a 2000-step smoke test and validates Gymnasium API compliance on every change to `ml/rl/` or `train_rl.py`.

## Ingest Workers

```bash
# Trigger all ingest tasks (runs tasks 0–8 in parallel)
gcloud run jobs execute f1-ingest --region=us-central1 --project=f1optimizer

# Verify data lake contents
python pipeline/scripts/verify_upload.py --bucket f1optimizer-data-lake

# Backfill known gaps
python pipeline/scripts/backfill_data.py --bucket f1optimizer-data-lake --dry-run
```

| Task Index | Worker | Coverage |
|---|---|---|
| 0–7 | `fastf1_worker` | FastF1 telemetry 2018–2025 (one year per task) |
| 8 | `historical_worker` | Jolpica race results + lap times 1950–2017 |

## API

**Endpoint**: `https://f1-strategy-api-dev-694267183904.us-central1.run.app`

```bash
curl https://f1-strategy-api-dev-694267183904.us-central1.run.app/health
curl https://f1-strategy-api-dev-694267183904.us-central1.run.app/docs

# RAG natural-language query
curl -X POST https://f1-strategy-api-dev-694267183904.us-central1.run.app/rag/query \
  -H "Content-Type: application/json" \
  -d '{"query": "What was Hamilton'\''s average lap time at Monaco 2019?", "filters": {"season": 2019}}'

# RAG configuration status
curl https://f1-strategy-api-dev-694267183904.us-central1.run.app/rag/health
```

See [`docs/rag.md`](docs/rag.md) for RAG setup, environment variables, and first-time ingestion steps.

## Bias Detection & Mitigation

All supervised models include `evaluate_bias_slices()` which evaluates performance across:

- **Season** (2022 vs 2023): detects temporal distribution shift
- **Circuit type** (street vs permanent): detects circuit-specific bias
- **Tyre compound** (SOFT/MEDIUM/HARD): detects compound bias in degradation models
- **Race phase** (early/mid/late): detects race-stage performance degradation
- **Position tier** (front/mid/back): detects position-dependent bias

The RL agent is evaluated across circuit type, starting position (P1/P10/P18), and season slices. Bias metrics are logged to Vertex AI Experiments and the CI/CD pipeline includes a `check-bias` step that flags disparity beyond tolerance thresholds.

## Performance Targets

| Metric | Target |
|---|---|
| API P99 Latency | <500ms |
| Podium Accuracy | ≥70% |
| Winner Accuracy | ≥65% |
| Cost per Prediction | <$0.001 |
| Monthly Budget | <$70 |

## Infrastructure

Managed by Terraform in `infra/terraform/`. Review plan before applying:

```bash
terraform -chdir=infra/terraform plan -var-file=dev.tfvars
```

## Team Documentation

Internal team docs are in [`team-docs/`](./team-docs/).

---

**Status**: ML pipeline complete — 6 supervised models + RL agent trained, tested, and deployed. RAG pipeline added (chunker → embedder → Vector Search → Gemini).
**Last Updated**: 2026-03-26
**Branch**: `main` (stable) | `pipeline` (CI/CD) | `ml-dev` (ML development)