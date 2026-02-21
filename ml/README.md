# ML — F1 Strategy Optimizer

All ML code lives here. Everything runs on GCP — no local execution.

## Directory layout

```
ml/
├── features/        Feature store + feature pipeline (GCS Parquet → DataFrame)
├── models/          Model definitions (strategy predictor, pit stop optimizer)
├── training/        Training entry points + distributed trainer
├── evaluation/      Evaluation logic, metrics, SHAP analysis
├── distributed/     Distribution strategy configs + data sharding
├── dag/             Vertex AI Pipeline (KFP) + individual components
├── scripts/         Training job submission scripts
├── tests/           All ML tests — run on Vertex AI, not locally
└── README.md
```

## Running on GCP

**Submit a GPU training job (recommended for individual experiments):**
```bash
bash ml/scripts/submit_training_job.sh --display-name your-name-experiment-1
```

**Trigger full pipeline (5-step KFP):**
```bash
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d)
```

**Run tests on Vertex AI:**
```bash
python ml/tests/run_tests_on_vertex.py
```

See `ml/HANDOFF.md` and `DEV_SETUP.md` for the full setup and usage guide.

## GCP Resources

| Resource | Name |
|---|---|
| Training bucket | gs://f1optimizer-training/ |
| Models bucket | gs://f1optimizer-models/ |
| Pipeline runs bucket | gs://f1optimizer-pipeline-runs/ |
| Data lake | gs://f1optimizer-data-lake/ |
| Vertex AI SA | f1-training-dev@f1optimizer.iam.gserviceaccount.com |
| Artifact Registry | us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest |

## Docker image

Built via `docker/Dockerfile.ml` and pushed to Artifact Registry on every push
to the `pipeline` branch via Cloud Build.
