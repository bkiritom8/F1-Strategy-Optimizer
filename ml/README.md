# ML — F1 Strategy Optimizer

All ML code lives here. Everything runs on GCP — no local execution.

## Directory layout

```
ml/
├── features/        Feature store + feature pipeline (Cloud SQL → GCS)
├── models/          Model definitions (strategy predictor, pit stop optimizer)
├── training/        Training entry points + distributed trainer
├── evaluation/      Evaluation logic, metrics, SHAP analysis
├── distributed/     Distribution strategy configs + data sharding
├── dag/             Vertex AI Pipeline (KFP) + individual components
├── tests/           All ML tests — run on Vertex AI, not locally
└── README.md
```

## Running on GCP

**Trigger full pipeline:**
```bash
python ml/dag/pipeline_runner.py
```

**Run tests on Vertex AI:**
```bash
python ml/tests/run_tests_on_vertex.py
```

**Access Workbench:** Vertex AI → Workbench → `f1-ml-workbench` (us-central1)

## GCP Resources

| Resource | Name |
|---|---|
| Workbench | f1-ml-workbench |
| Training bucket | gs://f1optimizer-training/ |
| Models bucket | gs://f1optimizer-models/ |
| Pipeline runs | gs://f1optimizer-models/pipeline-runs/ |
| Vertex AI SA | f1-training-dev |
| Artifact Registry | us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest |

## Docker image

Built via `docker/Dockerfile.ml` and pushed to Artifact Registry on every push
to the `pipeline` branch via Cloud Build.
