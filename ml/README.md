# Machine Learning Pipeline

End-to-end ML lifecycle for F1 strategy predictions — feature engineering, supervised model training, PPO reinforcement learning, Vertex AI deployment, and KFP v2 orchestration.

## Models

| Model | Algorithm | Test Metric | Output |
|---|---|---|---|
| Tire Degradation | XGBoost + LightGBM ensemble | MAE=0.285s, R²=0.850 | Degradation rate per lap |
| Driving Style | LightGBM + XGBoost ensemble | F1=0.800 | Style class (aggressive / balanced / conservative) |
| Safety Car | LightGBM + XGBoost ensemble | F1=0.920 | Deployment probability |
| Pit Window | XGBoost + LightGBM ensemble | MAE=1.116 laps, R²=0.968 | Optimal lap range |
| Overtake Probability | Random Forest (calibrated) | F1=0.326 | Per-position probability |
| Race Outcome | CatBoost + LightGBM ensemble | Acc=0.790, F1=0.778 | Final position distribution |
| RL Race Strategy | PPO (Stable-Baselines3) | — | `models/rl/final_policy.zip` |

**Training split**: 2018–2021 train / 2022–2023 val / 2024 test

## Directory Structure

```
ml/
├── training/           # 6 supervised training scripts + train_rl.py (PPO)
├── models/             # Python model wrapper classes + base_model.py
│   └── rl/             # PPO policy artifacts
├── rl/                 # RL infrastructure
│   ├── environment.py  # F1RaceEnv (29 obs features, 7 actions)
│   ├── agent.py
│   ├── state.py
│   ├── adapters.py
│   └── reward.py
├── preprocessing/      # FastF1 + race results feature engineering
│   └── preprocess_data.py
├── features/           # GCS-backed feature store
│   └── feature_store.py
├── distributed/        # Vertex AI cluster configurations
│   └── cluster_config.py
├── dag/                # KFP v2 pipeline (5-step DAG)
│   ├── f1_pipeline.py
│   ├── pipeline_runner.py
│   └── components/     # 6 KFP components + feature calculators
├── tests/              # 87 model and feature validation tests
│   └── run_tests_on_vertex.py
├── scripts/
│   └── submit_training_job.sh
└── plots/
```

## RL Environment

`rl/environment.py` — `F1RaceEnv`:

- **Observation space**: 29 features (lap number, tyre age, fuel load, gap to leader, sector times, weather, etc.)
- **Action space**: 7 discrete actions (stay out, pit soft/medium/hard/inter/wet, adjust driving mode)
- **Reward**: Composite of lap time delta, position gained, tyre health, fuel efficiency

## Cluster Configurations (`distributed/cluster_config.py`)

| Config | Hardware | Use Case |
|---|---|---|
| `VERTEX_T4` | 1× T4 GPU | Standard supervised training |
| `single-GPU` | 1× GPU | Quick iteration |
| `multi-node` | Multi-node | Large-scale distributed |
| `HP` | — | Hyperparameter search |
| `CPU` | CPU-only | Lightweight preprocessing |

## Running Training

```bash
# Individual supervised models
python ml/training/train_tire_degradation.py
python ml/training/train_pit_window.py

# PPO RL agent
python ml/training/train_rl.py --timesteps 1000000 --n-envs 4

# Submit GPU job to Vertex AI
bash ml/scripts/submit_training_job.sh --display-name my-run-v1

# Full KFP pipeline (compile + submit + monitor)
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d-%H%M%S)

# Trigger KFP pipeline via Cloud Run job
gcloud run jobs execute f1-pipeline-trigger --region=us-central1 --project=f1optimizer

# Run all 87 tests on Vertex AI
python ml/tests/run_tests_on_vertex.py
```

## GCS Artifacts

| Bucket | Path | Contents |
|---|---|---|
| `f1optimizer-data-lake` | `ml_features/` | Preprocessed feature Parquet files |
| `f1optimizer-models` | `*.pkl` | Promoted supervised model artifacts |
| `f1optimizer-training` | `rl/final_policy.zip` | PPO policy checkpoint |

## Known Gaps

- `ml/training/distributed_trainer.py` imports `ray` — Ray is not in `docker/requirements-ml.txt` (not blocking; direct Vertex AI jobs are used instead)
- `ml/models/strategy_predictor.py` and `ml/models/pit_stop_optimizer.py` raise `NotImplementedError` — API uses the 6 new model classes directly with rule-based fallback

---

**Status**: Complete — 6 supervised models + PPO RL agent trained and promoted to GCS
