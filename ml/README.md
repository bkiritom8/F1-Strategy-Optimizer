# ML — F1 Strategy Optimizer

All ML code lives here. Training runs on GCP Vertex AI.

## Directory Layout

```
ml/
├── preprocessing/   Data preprocessing pipeline (GCS Parquet → Features)
├── features/        Feature store + feature pipeline (GCS Parquet → DataFrame)
├── models/          Model definitions (strategy predictor, pit stop optimizer)
├── training/        Training entry points + distributed trainer
├── distributed/     Distribution strategy configs + data sharding
├── dag/             Vertex AI Pipeline (KFP v2) + 6 individual components
├── scripts/         Training job submission scripts
├── tests/           All ML tests — includes preprocessing unit tests
└── README.md
```

## Preprocessing

Data validation and sanitisation live in `src/preprocessing/`. The KFP feature
pipeline (`ml/features/feature_pipeline.py`) runs on top of processed Parquet files
already in GCS and produces ML-ready feature frames.

**Input (GCS — already uploaded):**
- `gs://f1optimizer-data-lake/processed/fastf1_laps.parquet`
- `gs://f1optimizer-data-lake/processed/fastf1_telemetry.parquet`
- `gs://f1optimizer-data-lake/processed/race_results.parquet`

**Output (GCS — written by the KFP feature engineering step):**
- `gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet` (87,036 rows, 53 columns)
- `gs://f1optimizer-data-lake/ml_features/race_results_features.parquet` (6,745 rows, 20 columns)
- `gs://f1optimizer-data-lake/ml_features/metadata.json`

**Run feature pipeline directly:**

```bash
# Requires GCP authentication
gcloud auth application-default login
pip install gcsfs pyarrow pandas

python -c "
from ml.features.feature_pipeline import FeaturePipeline
df = FeaturePipeline().run(years=list(range(2018, 2026)))
print(df.shape)
"
```

## Models

### Supervised (6 models)

| Model | Algorithm | Test Metric |
|---|---|---|
| `tire_degradation_model.py` | XGBoost + LightGBM | MAE=0.285s, R²=0.850 |
| `driving_style_model.py` | LightGBM + XGBoost | F1=0.800 |
| `safety_car_model.py` | LightGBM + XGBoost | F1=0.920 |
| `pit_window_model.py` | XGBoost + LightGBM | MAE=1.116 laps, R²=0.968 |
| `overtake_prob_model.py` | Random Forest (calibrated) | F1=0.326 |
| `race_outcome_model.py` | CatBoost + LightGBM | Acc=0.790, F1=0.778 |

Training split: 2018–2021 train, 2022–2023 val, 2024 test.

### RL Agent

`ml/rl/environment.py` — `F1RaceEnv` (Gymnasium, 29 obs features, 7 actions).
`ml/training/train_rl.py` — PPO via Stable-Baselines3.
Artifacts: `models/rl/final_policy.zip`, `models/rl/final_vec_normalize.pkl`.

### Legacy KFP Wrappers

`ml/models/strategy_predictor.py` and `ml/models/pit_stop_optimizer.py` are used by the
KFP pipeline components. Their `predict()` methods raise `NotImplementedError` — the API
falls back to rule-based logic until a full pipeline run promotes them.

## Running on GCP

**Train all supervised models individually:**

```bash
for MODEL in tire_degradation driving_style safety_car pit_window overtake_prob race_outcome; do
  python ml/training/train_${MODEL}.py
done
```

**Train RL agent:**

```bash
python ml/training/train_rl.py --timesteps 1000000 --n-envs 4
```

**Submit a GPU training job (individual experiment):**

```bash
bash ml/scripts/submit_training_job.sh --display-name your-name-experiment-1
```

Machine: `n1-standard-4` + 1× NVIDIA T4, image: `ml:latest` from Artifact Registry.

**Trigger full 5-step KFP pipeline:**

```bash
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d)
```

**Run tests on Vertex AI:**

```bash
python ml/tests/run_tests_on_vertex.py
```

## Compute Profiles

Defined in `ml/distributed/cluster_config.py`:

| Profile | Machine | GPUs | Workers | Use Case |
|---|---|---|---|---|
| `VERTEX_T4` | n1-standard-4 | 1× T4 | 1 | Individual experiment (default) |
| `SINGLE_NODE_MULTI_GPU` | n1-standard-16 | 4× T4 | 1 | Full training run |
| `MULTI_NODE_DATA_PARALLEL` | n1-standard-8 | 1× T4 each | 4 | Large dataset sharding |
| `HYPERPARAMETER_SEARCH` | n1-standard-4 | 0 | 8 | HP sweep |
| `CPU_DISTRIBUTED` | n1-highmem-16 | 0 | 8 | Feature engineering |

## GCP Resources

| Resource | Name |
|---|---|
| Training bucket | `gs://f1optimizer-training/` |
| Models bucket | `gs://f1optimizer-models/` |
| Pipeline runs bucket | `gs://f1optimizer-pipeline-runs/` |
| Data lake | `gs://f1optimizer-data-lake/` |
| ML features | `gs://f1optimizer-data-lake/ml_features/` |
| Vertex AI SA | `f1-training-dev@f1optimizer.iam.gserviceaccount.com` |
| ML image | `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest` |

## Docker Image

Built from `docker/Dockerfile.ml` (base: `nvidia/cuda:11.8.0-python3.10`).
Pushed to Artifact Registry on every push to `pipeline` via Cloud Build.

```bash
# Build locally (requires Docker Desktop)
docker build --platform linux/amd64 \
  -t us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest \
  -f docker/Dockerfile.ml .
```

## Known Gaps

- `predict()` raises `NotImplementedError` in `strategy_predictor.py` and `pit_stop_optimizer.py` (legacy KFP wrappers) — API uses rule-based fallback
- `ml/training/distributed_trainer.py` imports `ray` but `ray` is **not** in `docker/requirements-ml.txt` — Ray distributed training is not yet functional
- PPO RL agent trained but not yet integrated into the FastAPI `/recommend` endpoint

## See Also

- [`docs/ml_handoff.md`](../docs/ml_handoff.md) — full ML handoff
- [`docs/DEV_SETUP.md`](../docs/DEV_SETUP.md) — environment setup
- [`docs/models.md`](../docs/models.md) — model architecture details
- [`docs/rag.md`](../docs/rag.md) — RAG pipeline (chunker → embedder → Vector Search → Gemini)