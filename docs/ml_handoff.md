# F1 Strategy Optimizer — ML Team Handoff

**Date:** 2026-03-19
**Status:** ML handoff complete — distributed pipeline, models, tests ready. Data in GCS.
**GCP Project:** `f1optimizer` | **Region:** `us-central1`

---

## 1. Repo Structure

```
├── ingest/                      ← Cloud Run ingest workers
│   ├── task.py                  Cloud Run entrypoint (routes CLOUD_RUN_TASK_INDEX 0–8)
│   ├── fastf1_worker.py         FastF1 telemetry per year (Tasks 0–7: 2018–2025)
│   ├── historical_worker.py     Jolpica race results + lap times 1950–2017 (Task 8)
│   ├── lap_times_worker.py      Jolpica paginated lap times (rate-limited)
│   ├── gap_worker.py            Targeted backfill for 5 known gap scenarios
│   ├── progress.py              GCS-backed optimistic locking for concurrent tasks
│   └── gcs_utils.py             Upload helpers
├── ml/                          ← All ML work
│   ├── features/                Feature store + feature pipeline
│   │   ├── feature_store.py     GCS Parquet → DataFrame (ADC, no hardcoded creds)
│   │   └── feature_pipeline.py  Tire deg, gap evolution, undercut, fuel, SC prob
│   ├── models/                  Model definitions
│   │   ├── base_model.py        Abstract base: GCS save/load, logging, Pub/Sub
│   │   ├── strategy_predictor.py  XGBoost + LightGBM ensemble
│   │   └── pit_stop_optimizer.py  LSTM sequence model (GPU)
│   ├── training/                Training utilities
│   │   └── distributed_trainer.py  (note: imports ray — not in requirements-ml.txt)
│   ├── distributed/             Distribution strategies + cluster configs
│   │   ├── cluster_config.py    5 named configs (VERTEX_T4, single-GPU, multi-node, HP, CPU)
│   │   ├── distribution_strategy.py  DataParallel / ModelParallel / HPParallel
│   │   ├── data_sharding.py     GCS Parquet → shards per worker
│   │   └── aggregator.py        Pick best checkpoint, promote to models bucket
│   ├── dag/                     Vertex AI Pipeline (KFP v2)
│   │   ├── f1_pipeline.py       Full 5-step @dsl.pipeline definition
│   │   ├── pipeline_runner.py   Compile → upload GCS → submit → monitor
│   │   └── components/          Individual @dsl.component files
│   │       ├── validate_data.py
│   │       ├── feature_engineering.py
│   │       ├── train_strategy.py
│   │       ├── train_pit_stop.py
│   │       ├── evaluate.py
│   │       └── deploy.py
│   ├── evaluation/              (extend as needed)
│   ├── tests/                   All tests — run on Vertex AI
│   │   ├── test_dag.py
│   │   ├── test_features.py
│   │   ├── test_models.py
│   │   ├── test_distributed.py
│   │   └── run_tests_on_vertex.py
│   └── README.md
├── pipeline/scripts/            Data conversion scripts
│   ├── csv_to_parquet.py        Convert raw CSVs → GCS Parquet
│   ├── backfill_data.py         Fix known data gaps (race_results, laps, FastF1)
│   └── verify_upload.py         Audit GCS data lake contents and sizes
├── infra/terraform/             All GCP infrastructure (Terraform)
├── api/                         FastAPI serving notes
├── monitoring/                  Observability notes
├── docker/
│   ├── Dockerfile.ml            CUDA 11.8 + Python 3.10, no CMD
│   ├── Dockerfile.api           FastAPI server (uvicorn, port 8000)
│   ├── Dockerfile.ingest        Cloud Run ingest workers
│   └── requirements-ml.txt
└── src/                         Shared API code
```

---

## 2. GCP Resources

| Resource | Name / ID |
|---|---|
| Project | `f1optimizer` |
| Region | `us-central1` |
| Cloud Run API | `f1-strategy-api-dev` |
| Cloud Run Job — pipeline trigger | `f1-pipeline-trigger` |
| Cloud Run Job — ingest | `f1-ingest` |
| Training SA | `f1-training-dev@f1optimizer.iam.gserviceaccount.com` |
| Artifact Registry | `us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/` |
| GCS — raw source data | `gs://f1optimizer-data-lake/raw/` — 51 files, 6.0 GB |
| GCS — processed Parquet | `gs://f1optimizer-data-lake/processed/` — 10 files, 1.0 GB |
| GCS — FastF1 telemetry | `gs://f1optimizer-data-lake/telemetry/` — per-year per-session |
| GCS — historical data | `gs://f1optimizer-data-lake/historical/` — per-season |
| GCS — ingest status | `gs://f1optimizer-data-lake/status/` — progress markers |
| GCS — training artifacts | `gs://f1optimizer-training/` |
| GCS — promoted models | `gs://f1optimizer-models/` |
| GCS — pipeline run roots | `gs://f1optimizer-pipeline-runs/` |
| GCS — Terraform state | `gs://f1-optimizer-terraform-state/` |
| Pub/Sub | `f1-predictions-dev`, `f1-alerts-dev`, `f1-race-events-dev`, `f1-telemetry-stream-dev` |

---

## 3. GCP Console Links

| Console | URL |
|---|---|
| Vertex AI Pipelines | https://console.cloud.google.com/vertex-ai/pipelines?project=f1optimizer |
| Vertex AI Training Jobs | https://console.cloud.google.com/vertex-ai/training/custom-jobs?project=f1optimizer |
| Vertex AI Experiments | https://console.cloud.google.com/vertex-ai/experiments?project=f1optimizer |
| Cloud Run Jobs | https://console.cloud.google.com/run/jobs?project=f1optimizer |
| Artifact Registry | https://console.cloud.google.com/artifacts?project=f1optimizer |
| Cloud Logging | https://console.cloud.google.com/logs/query?project=f1optimizer |
| GCS Buckets | https://console.cloud.google.com/storage/browser?project=f1optimizer |

---

## 4. Data Storage

All F1 data lives in GCS.

| Path | Files | Size | Contents |
|---|---|---|---|
| `gs://f1optimizer-data-lake/raw/` | 51 | 6.0 GB | Source CSVs from Jolpica API and FastF1 |
| `gs://f1optimizer-data-lake/processed/` | 10 | 1.0 GB | Parquet files ready for ML training |
| `gs://f1optimizer-data-lake/telemetry/` | per-year | — | FastF1 per-session Parquet (ingest workers) |
| `gs://f1optimizer-data-lake/historical/` | per-season | — | Jolpica 1950–2017 Parquet (ingest workers) |
| `gs://f1optimizer-models/` | — | — | Promoted model artifacts |
| `gs://f1optimizer-training/` | — | — | Checkpoints, feature exports, pipeline artefacts |

### Processed Parquet files

| File | Rows | Description |
|---|---|---|
| `processed/laps_all.parquet` | 93,372 | laps_1996 … laps_2025 combined |
| `processed/telemetry_all.parquet` | 30,477,110 | telemetry_2018 … telemetry_2025 combined |
| `processed/telemetry_laps_all.parquet` | 92,242 | FastF1 telemetry-session laps combined |
| `processed/circuits.parquet` | 78 | F1 circuit master list |
| `processed/drivers.parquet` | 100 | Driver master list |
| `processed/pit_stops.parquet` | 11,077 | Pit stop records |
| `processed/race_results.parquet` | 7,600 | Race results 1950-2026 |
| `processed/lap_times.parquet` | 56,720 | Aggregated lap times |
| `processed/fastf1_laps.parquet` | 92,242 | FastF1 lap data (2018-2026) |
| `processed/fastf1_telemetry.parquet` | 90,302 | FastF1 telemetry summary |

### Reading data in Python

```python
import pandas as pd

# Read processed Parquet directly from GCS (ADC credentials required — see DEV_SETUP.md §2)
laps         = pd.read_parquet("gs://f1optimizer-data-lake/processed/laps_all.parquet")
telemetry    = pd.read_parquet("gs://f1optimizer-data-lake/processed/telemetry_all.parquet")
circuits     = pd.read_parquet("gs://f1optimizer-data-lake/processed/circuits.parquet")
race_results = pd.read_parquet("gs://f1optimizer-data-lake/processed/race_results.parquet")
```

### Converting raw CSVs to Parquet

```bash
python pipeline/scripts/csv_to_parquet.py \
  --input-dir /path/to/local/csvs \
  --bucket f1optimizer-data-lake
```

---

## 5. Triggering the Full Distributed Pipeline

### Option A — Cloud Run Job (recommended for scheduled/automated runs)
```bash
gcloud run jobs execute f1-pipeline-trigger \
  --region=us-central1 \
  --project=f1optimizer
```

### Option B — Python SDK (from terminal)
```bash
# Compile + submit + monitor (blocks until done)
python ml/dag/pipeline_runner.py --run-id $(date +%Y%m%d-%H%M%S)

# Compile and upload JSON only (no submission)
python ml/dag/pipeline_runner.py --compile-only

# Submit with custom run ID, no monitoring wait
python ml/dag/pipeline_runner.py --run-id 20260319-manual --no-monitor
```

### Option C — Pub/Sub trigger
Publish a message to `f1-race-events-dev` — the pipeline trigger job listens
and auto-submits when a `pipeline_trigger` event arrives.

---

## 6. Running the Ingest Workers

Data ingestion runs as Cloud Run Jobs. `ingest/task.py` dispatches by `CLOUD_RUN_TASK_INDEX`:

| Index | Worker | Coverage |
|---|---|---|
| 0–7 | `fastf1_worker` | FastF1 telemetry 2018–2025 (one year per task) |
| 8 | `historical_worker` | Jolpica race results, lap times, standings 1950–2017 |

```bash
# Trigger all ingest tasks
gcloud run jobs execute f1-ingest --region=us-central1 --project=f1optimizer

# Run a single task locally (debugging)
CLOUD_RUN_TASK_INDEX=3 GCS_BUCKET=f1optimizer-data-lake python -m ingest.task

# Backfill known gaps
python pipeline/scripts/backfill_data.py --bucket f1optimizer-data-lake --dry-run
python pipeline/scripts/backfill_data.py --bucket f1optimizer-data-lake --skip-fastf1
```

Workers are idempotent — safe to re-run. They check GCS before downloading.

---

## 7. Triggering Individual Pipeline Components

Each component is a standalone `@dsl.component` — it can be invoked directly
as a Vertex AI Custom Job without running the full pipeline.

### Validate data only
```python
from google.cloud import aiplatform
from ml.distributed.cluster_config import CPU_DISTRIBUTED

aiplatform.init(project="f1optimizer", location="us-central1")
job = aiplatform.CustomJob(
    display_name="validate-data-manual",
    worker_pool_specs=CPU_DISTRIBUTED.worker_pool_specs(
        args=["python", "-m", "ml.dag.components.validate_data"],
    ),
)
job.run(service_account="f1-training-dev@f1optimizer.iam.gserviceaccount.com")
```

### Train strategy model only
```bash
gcloud ai custom-jobs create \
  --region=us-central1 \
  --project=f1optimizer \
  --display-name="strategy-train-manual" \
  --worker-pool-spec=machine-type=n1-standard-8,accelerator-type=NVIDIA_TESLA_T4,\
accelerator-count=1,replica-count=4,\
container-image-uri=us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest \
  --args="python,-m,ml.models.strategy_predictor,--mode,train,\
--feature-uri,gs://f1optimizer-data-lake/processed/laps.parquet,\
--checkpoint-uri,gs://f1optimizer-training/checkpoints/manual-001/strategy/"
```

---

## 8. Switching Distribution Strategies

All cluster configs are in `ml/distributed/cluster_config.py`.

```python
from ml.distributed.cluster_config import (
    SINGLE_NODE_MULTI_GPU,    # 1 node, 4 x T4, MirroredStrategy
    MULTI_NODE_DATA_PARALLEL, # 4 nodes, 1 x T4 each, MultiWorkerMirroredStrategy
    HYPERPARAMETER_SEARCH,    # HP tuning via Vertex AI Vizier (5 parallel trials)
    CPU_DISTRIBUTED,          # 8 CPU workers, no GPU
)

# Use in a CustomJob:
specs = MULTI_NODE_DATA_PARALLEL.worker_pool_specs(
    args=["python", "-m", "ml.models.strategy_predictor", "--mode", "train", ...],
    env_vars={"PROJECT_ID": "f1optimizer", ...},
)
```

---

## 9. Monitoring Training Jobs

### Vertex AI console
- **All jobs:** https://console.cloud.google.com/vertex-ai/training/custom-jobs?project=f1optimizer
- Click any job → **Logs** tab → streamed from Cloud Logging in real time

### Cloud Logging query for a specific run
```
resource.type="aiplatform.googleapis.com/CustomJob"
labels."ml.googleapis.com/display_name"="f1-strategy-train-<RUN_ID>"
```

### gcloud CLI
```bash
# List recent custom jobs
gcloud ai custom-jobs list --region=us-central1 --project=f1optimizer

# Stream logs for a job
gcloud ai custom-jobs stream-logs <JOB_ID> \
  --region=us-central1 --project=f1optimizer
```

---

## 10. Viewing Model Metrics in Vertex AI Experiments

All evaluation metrics are logged to the `f1-strategy-training` experiment.

1. Go to: https://console.cloud.google.com/vertex-ai/experiments?project=f1optimizer
2. Click **f1-strategy-training**
3. Compare runs side-by-side — filter by `model_name`, sort by `val_mae` or `val_roc_auc`

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

## 11. Running Tests on Vertex AI

```bash
# Run full test suite (submits a Vertex AI Custom Job)
python ml/tests/run_tests_on_vertex.py

# Run a specific test file
python ml/tests/run_tests_on_vertex.py --test-path ml/tests/test_models.py

# With a custom run ID for traceability
python ml/tests/run_tests_on_vertex.py --run-id 20260319-pre-release
```

Results are logged to Cloud Logging under `f1.tests.results`.
Query: `jsonPayload.run_id="<RUN_ID>" resource.type="global"`

---

## 12. Branch Strategy

| Branch | Purpose |
|---|---|
| `main` | Stable — infra + code, reviewed PRs only |
| `pipeline` | CI/CD trigger — Cloud Build builds all Docker images on push |
| `ml-dev` | ML team development branch — create from here for feature branches |

**Workflow:**
1. Branch off `ml-dev` for new work
2. PR → `ml-dev` for review
3. Merge `ml-dev` → `pipeline` to trigger a new `ml:latest` image build
4. Merge `pipeline` → `main` only for stable releases

---

## 13. Docker Image Build

The ML image is built automatically on every push to the `pipeline` branch
via Cloud Build (`cloudbuild.yaml`).

To build manually:
```bash
gcloud builds submit \
  --config cloudbuild.yaml \
  --project=f1optimizer \
  .
```

The image is tagged:
```
us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest
```

---

## 14. First Steps for the ML Team

In order:

1. **Authenticate** — follow `DEV_SETUP.md` §1–2
2. **Verify data** — check processed Parquet files exist:
   ```bash
   gsutil ls gs://f1optimizer-data-lake/processed/
   python pipeline/scripts/verify_upload.py --bucket f1optimizer-data-lake
   ```
3. **Run tests** to confirm the codebase is healthy:
   ```bash
   python ml/tests/run_tests_on_vertex.py
   ```
4. **Trigger the pipeline** for the first end-to-end run:
   ```bash
   python ml/dag/pipeline_runner.py --run-id first-run
   ```
5. **Check Experiments** for model metrics after the pipeline completes:
   https://console.cloud.google.com/vertex-ai/experiments?project=f1optimizer
6. **Iterate** — edit models in `ml/models/`, push to `ml-dev`, merge to `pipeline`
   to rebuild the image, re-run the pipeline.

---

## 15. Known Gaps to Address

| Gap | File | Notes |
|---|---|---|
| `predict()` not implemented | `ml/models/strategy_predictor.py`, `ml/models/pit_stop_optimizer.py` | Raises `NotImplementedError` — API falls back to rule-based logic |
| Ray dependency missing | `ml/training/distributed_trainer.py` | Imports `ray` but `ray` is not in `docker/requirements-ml.txt` |
| Monitoring dashboards | GCP Console | Cloud Monitoring alerting policies not yet created |
| SHAP explanations | `ml/models/strategy_predictor.py` | `feature_importance()` exists; SHAP DeepExplainer not yet wired up |

---

## 16. Escalation Path

For infrastructure (Terraform, Cloud Run, IAM):
→ Check `infra/terraform/` and `docs/architecture.md`
→ Raise a GitHub issue on `main` branch

For pipeline/model questions:
→ This document + `ml/README.md`
→ Raise a GitHub issue tagged `ml`
