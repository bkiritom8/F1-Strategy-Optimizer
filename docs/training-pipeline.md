# Distributed Training Pipeline

**Last Updated**: 2026-03-25

## Overview

The F1 Strategy Optimizer training pipeline uses Vertex AI — either individual Custom Jobs
for development experiments or a full KFP Pipeline for end-to-end runs. All training code
lives in `ml/`.

**Key Principles**:
- All training runs on Vertex AI — no local execution
- Reads features from GCS (`gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet`)
- Each training script uploads its `.pkl` artifact to `gs://f1optimizer-models/{model_name}/model.pkl`
- Cloud Build registers artifacts in Vertex AI Model Registry after training completes
- All jobs use `ml:latest` Docker image from Artifact Registry
- Vertex AI Experiments tracked under experiment name `f1-strategy-models`; all runs use `resume=True`

---

## Quick Start

### Individual GPU Experiment (recommended for development)

```bash
bash ml/scripts/submit_training_job.sh --display-name your-name-strategy-v1
```

Submits a Vertex AI Custom Job with:
- Machine: `n1-standard-4`
- GPU: 1× NVIDIA T4
- Image: `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest`
- Service Account: `f1-training-dev@f1optimizer.iam.gserviceaccount.com`

Use `<your-name>-<model>-v<n>` naming to avoid collisions between teammates.

### Full Pipeline Run

```bash
# Cloud Run Job (scheduled / automated)
gcloud run jobs execute f1-pipeline-trigger \
  --region=us-central1 --project=f1optimizer

# Python SDK (compile + submit + monitor)
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d)

# Compile only (no submission)
python ml/dag/pipeline_runner.py --compile-only
```

---

## KFP Pipeline (5-Step DAG)

Defined in `ml/dag/f1_pipeline.py`. Steps run in this order:

```
┌─────────────────────────────────────────────────────────┐
│ F1 Strategy Training Pipeline                           │
│                                                         │
│  ┌──────────────────┐                                   │
│  │  validate_data   │  Check GCS Parquet integrity      │
│  └────────┬─────────┘                                   │
│           │                                             │
│  ┌────────▼─────────┐                                   │
│  │feature_engineering│  GCS → feature tensors           │
│  └────┬─────────────┘                                   │
│       │                                                 │
│       ├────────────────────┐                            │
│       │                    │                            │
│  ┌────▼──────────┐  ┌──────▼──────────┐                │
│  │train_strategy │  │train_pit_stop   │  (parallel)    │
│  │  (XGBoost +   │  │  (LSTM +        │                │
│  │  LightGBM)    │  │  MirroredStrat) │                │
│  └────┬──────────┘  └──────┬──────────┘                │
│       │                    │                            │
│  ┌────▼──────────┐  ┌──────▼──────────┐                │
│  │evaluate       │  │evaluate         │  (parallel)    │
│  │strategy       │  │pit_stop         │                │
│  └────┬──────────┘  └──────┬──────────┘                │
│       └────────────────────┘                            │
│                    │                                    │
│           ┌────────▼────────┐                           │
│           │     deploy      │  Best model → promoted    │
│           └─────────────────┘                           │
└─────────────────────────────────────────────────────────┘
```

Each step is a `@dsl.component` in `ml/dag/components/`:
- `validate_data.py` — checks GCS Parquet integrity
- `feature_engineering.py` — reads Parquet, engineers features, writes to training bucket
- `train_strategy.py` — trains XGBoost + LightGBM ensemble
- `train_pit_stop.py` — trains LSTM with MirroredStrategy (multi-GPU)
- `evaluate.py` — computes metrics, logs to Vertex AI Experiments
- `deploy.py` — aggregates best checkpoint, promotes to `gs://f1optimizer-models/`

All components have `retries=2` and log to Cloud Logging.

---

## Models

Six supervised models and one RL agent are trained and deployed.

### Supervised Models (`ml/training/train_*.py`)

Each model has a dedicated training script and a wrapper class in `ml/models/`:

| Script | Wrapper | Algorithm |
|---|---|---|
| `train_tire_degradation.py` | `tire_degradation_model.py` | XGBoost + LightGBM |
| `train_driving_style.py` | `driving_style_model.py` | LightGBM + XGBoost |
| `train_safety_car.py` | `safety_car_model.py` | LightGBM + XGBoost |
| `train_pit_window.py` | `pit_window_model.py` | XGBoost + LightGBM |
| `train_overtake_prob.py` | `overtake_prob_model.py` | Random Forest (calibrated) |
| `train_race_outcome.py` | `race_outcome_model.py` | CatBoost + LightGBM |

Input features come from `ml/preprocessing/preprocess_data.py` → `gs://f1optimizer-data-lake/ml_features/`.

**Train all supervised models:**
```bash
for MODEL in tire_degradation driving_style safety_car pit_window overtake_prob race_outcome; do
  python ml/training/train_${MODEL}.py
done
```

### RL Agent (`ml/training/train_rl.py`)

PPO agent using Stable-Baselines3. Environment: `ml/rl/environment.py` (F1RaceEnv — 29 obs features, 7 actions).

```bash
python ml/training/train_rl.py --timesteps 1000000 --n-envs 4
```

Artifacts saved to `models/rl/final_policy.zip` and `models/rl/final_vec_normalize.pkl`.

### Legacy Wrappers

`ml/models/strategy_predictor.py` (XGBoost+LightGBM) and `ml/models/pit_stop_optimizer.py` (LSTM) are legacy model classes used by the KFP pipeline components. Their `predict()` methods raise `NotImplementedError` — the API falls back to rule-based logic until a full pipeline run promotes them.

---

## Compute Profiles

Defined in `ml/distributed/cluster_config.py`:

| Profile | Machine | GPUs | Workers | Use Case |
|---|---|---|---|---|
| `VERTEX_T4` | `n1-standard-4` | 1× T4 | 1 | Default for experiments |
| `SINGLE_NODE_MULTI_GPU` | `n1-standard-16` | 4× T4 | 1 | Full PitStopOptimizer training |
| `MULTI_NODE_DATA_PARALLEL` | `n1-standard-8` | 1× T4 each | 4 | Large dataset sharding |
| `HYPERPARAMETER_SEARCH` | `n1-standard-4` | 0 | 8 | HP sweep via Vertex AI Vizier |
| `CPU_DISTRIBUTED` | `n1-highmem-16` | 0 | 8 | Feature engineering |

To use programmatically:

```python
from ml.distributed.cluster_config import SINGLE_NODE_MULTI_GPU
from google.cloud import aiplatform

aiplatform.init(project="f1optimizer", location="us-central1")
job = aiplatform.CustomJob(
    display_name="full-training-run",
    worker_pool_specs=SINGLE_NODE_MULTI_GPU.worker_pool_specs(
        args=["python", "-m", "ml.models.strategy_predictor", "--mode", "train"],
    ),
)
job.run(service_account="f1-training-dev@f1optimizer.iam.gserviceaccount.com")
```

---

## Monitoring Training Jobs

### Vertex AI Console

- **All jobs**: https://console.cloud.google.com/vertex-ai/training/custom-jobs?project=f1optimizer
- Click any job → **Logs** tab for real-time Cloud Logging output

### gcloud CLI

```bash
# List recent custom jobs
gcloud ai custom-jobs list --region=us-central1 --project=f1optimizer

# Stream logs for a job
gcloud ai custom-jobs stream-logs JOB_ID \
  --region=us-central1 --project=f1optimizer
```

### Cloud Logging Query

```
resource.type="aiplatform.googleapis.com/CustomJob"
labels."ml.googleapis.com/display_name"="your-name-strategy-v1"
```

---

## Viewing Metrics in Vertex AI Experiments

All evaluation metrics are logged to the `f1-strategy-training` experiment.

1. Open: https://console.cloud.google.com/vertex-ai/experiments?project=f1optimizer
2. Click **f1-strategy-training**
3. Compare runs by `model_name`, `val_mae`, `val_roc_auc`

From Python:

```python
from google.cloud import aiplatform
aiplatform.init(project="f1optimizer", location="us-central1",
                experiment="f1-strategy-training")
runs = aiplatform.ExperimentRun.list(experiment="f1-strategy-training")
for r in runs:
    print(r.run_name, r.get_metrics())
```

---

## GCS Artifact Paths

```
gs://f1optimizer-data-lake/processed/     # Input: Parquet data
gs://f1optimizer-training/
├── features/                             # Feature exports per run
├── checkpoints/                          # Model checkpoints
│   └── <run-id>/
│       ├── strategy/
│       └── pit_stop/
└── pipeline-runs/                        # KFP pipeline artifacts

gs://f1optimizer-models/                  # Promoted (production) models
├── tire_degradation/
│   └── model.pkl
├── driving_style/
│   └── model.pkl
├── safety_car/
│   └── model.pkl
├── pit_window/
│   └── model.pkl
├── overtake_prob/
│   └── model.pkl
├── race_outcome/
│   └── model.pkl
└── champion_metrics.json                 # Rollback baseline metrics
```

---

## Running Tests

```bash
# Full test suite on Vertex AI
python ml/tests/run_tests_on_vertex.py

# Specific test file
python ml/tests/run_tests_on_vertex.py --test-path ml/tests/test_models.py

# With custom run ID
python ml/tests/run_tests_on_vertex.py --run-id 20260220-pre-release
```

Results logged to Cloud Logging: `jsonPayload.run_id="<RUN_ID>" resource.type="global"`

---

## Docker Image

The `ml:latest` image is built automatically on every push to the `pipeline` branch:

```bash
# Manual build via Cloud Build
gcloud builds submit --config cloudbuild.yaml . --project=f1optimizer

# Or build locally (requires Docker + NVIDIA toolkit)
docker build --platform linux/amd64 \
  -t us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest \
  -f docker/Dockerfile.ml .
docker push us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest
```

Base image: `nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu20.04`
Python: 3.10
Framework: PyTorch (CUDA), TensorFlow, XGBoost, LightGBM, KFP SDK
