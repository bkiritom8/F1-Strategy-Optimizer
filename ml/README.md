# ML — F1 Strategy Optimizer

All ML code lives here. Training runs on GCP Vertex AI.

## Directory Layout

```
ml/
├── features/        Feature store + feature pipeline (GCS Parquet → DataFrame)
├── models/          Model definitions (strategy predictor, pit stop optimizer)
├── training/        Training entry points + distributed trainer
├── distributed/     Distribution strategy configs + data sharding
├── dag/             Vertex AI Pipeline (KFP v2) + 6 individual components
├── scripts/         Training job submission scripts
├── tests/           All ML tests — run on Vertex AI
└── README.md
```

## Models

| Model | Architecture | Status |
|---|---|---|
| `StrategyPredictor` | XGBoost + LightGBM ensemble | Ready for training run |
| `PitStopOptimizer` | LSTM + MirroredStrategy (multi-GPU) | Ready for training run |

Both models fall back to rule-based logic via the API until a training run completes and
artifacts are promoted to `gs://f1optimizer-models/`.

## Running on GCP

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
| Vertex AI SA | `f1-training-dev@f1optimizer.iam.gserviceaccount.com` |
| ML image | `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest` |

## Docker Image

Built from `docker/Dockerfile.ml` (base: `nvidia/cuda:11.8.0-python3.10`).
Pushed to Artifact Registry on every push to `main` via Cloud Build.

```bash
# Build locally (requires Docker Desktop)
docker build --platform linux/amd64 \
  -t us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest \
  -f docker/Dockerfile.ml .
```

## Known Gaps

- `predict()` raises `NotImplementedError` in both models — API uses rule-based fallback
- Ray distributed training requires `ray` in `docker/requirements-ml.txt` (added; untested on Vertex)

## See Also

- [`team-docs/ml_module_handoff.md`](../team-docs/ml_module_handoff.md) — full ML handoff
- [`team-docs/DEV_SETUP.md`](../team-docs/DEV_SETUP.md) — environment setup
- [`docs/models.md`](../docs/models.md) — model architecture details
