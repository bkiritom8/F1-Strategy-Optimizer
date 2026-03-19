# F1 Strategy Optimizer — Data Pipeline

**Course submission for MLOps Data Pipeline assignment.**
This directory is fully self-contained. All pipeline code, tests, and documentation are here.

---

## Overview

End-to-end MLOps data pipeline for 76 years of F1 data (1950–2026):

- **Ingestion** — Jolpica API (historical results) + FastF1 (10Hz telemetry)
- **Preprocessing** — CSV normalization, Parquet conversion, timedelta handling
- **Validation** — Schema checks and data quality assertions
- **Anomaly Detection** — Outlier detection with optional Slack alerts
- **Feature Engineering** — Lap-by-lap ML state vectors
- **Bias Analysis** — Representation slicing by era, team, circuit, weather

---

## Architecture

```
Jolpica API ──► src/ingestion/ergast_ingestion.py ──► data/raw/jolpica/
FastF1 API  ──► src/ingestion/fastf1_ingestion.py ──► data/raw/fastf1/
                                │
                pipeline/scripts/csv_to_parquet.py
                                │
                    gs://f1optimizer-data-lake/processed/  (Parquet)
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                  ▼
    scripts/validate_data  scripts/anomaly_    ml/features/
    logs/data_statistics   detection.py        feature_pipeline.py
    scripts/expectations/  logs/anomaly_           │
                           report.json         data/features/
                                                    │
                                   scripts/bias_analysis.py
                                                    │
                                    logs/bias_report.json
```

---

## Folder Structure

```
Data-Pipeline/
├── dags/
│   └── f1_pipeline.py          Airflow DAG (weekly, 7 tasks)
├── data/
│   └── .gitkeep                Local data directory (gitignored; GCS is the source of truth)
├── logs/
│   ├── .gitkeep
│   └── gantt_chart.png         Generated at runtime (gitignored)
├── scripts/
│   ├── validate_data.py        Schema + data quality validation + statistics
│   ├── anomaly_detection.py    Outlier and missing-value detection (Slack alerts)
│   ├── bias_analysis.py        Representation bias via data slicing
│   ├── generate_gantt.py       Gantt chart from task durations (PNG + ASCII)
│   ├── deploy_dags.sh          Push DAG to GCS for GCE VM auto-sync
│   └── expectations/
│       └── .gitkeep            GE-style JSON suites written here at runtime
├── tests/
│   ├── __init__.py
│   ├── test_ingestion.py       Unit tests for Jolpica ingestion
│   ├── test_csv_to_parquet.py  Unit tests for CSV → Parquet conversion
│   ├── test_preprocessing.py   Unit tests for preprocessing logic
│   ├── test_validator.py       Unit tests for Pydantic schema validator
│   ├── test_anomaly_detection.py  Unit tests for anomaly detection
│   ├── test_bias_analysis.py   Unit tests for bias analysis
│   ├── test_fastf1_ingestion.py   Unit tests for FastF1 ingestion
│   └── test_generate_gantt.py  Unit tests for Gantt chart generation
├── dvc.yaml                    Pipeline stages for this directory
└── README.md                   This file
```

Also at repo root:
```
dvc.yaml                        Root-level DVC pipeline (full repo stages)
.dvcignore                      DVC ignore rules
src/ingestion/
├── ergast_ingestion.py         Jolpica API client
└── fastf1_ingestion.py         FastF1 telemetry client
src/preprocessing/
└── validator.py                Pydantic schema validator (DataValidator)
data/
└── .gitignore                  Keeps data/ out of git (DVC manages it)
docs/bias.md                    Bias findings and mitigation documentation
```

---

## Prerequisites

- Python 3.10+
- (Optional) GCP account for GCS data access

```bash
# Install all dependencies
pip install -r requirements-f1.txt

# Install pipeline-specific tools
pip install dvc apache-airflow pandas pyarrow numpy tenacity
```

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/bkiritom8/test.git
cd test

# 2. Install dependencies
pip install -r requirements-f1.txt

# 3. Copy and edit env vars
cp Data-Pipeline/.env.example Data-Pipeline/.env
# Edit .env: set GCS paths or USE_LOCAL_DATA=true for local dev

# 4. (GCP only) Authenticate and configure DVC remote
gcloud auth application-default login
# DVC GCS remote is pre-configured in .dvc/config
dvc pull   # pull processed data from gs://f1optimizer-data-lake/dvc-cache
```

---

## Running the Pipeline

### Local mode (no GCP required)

Use `USE_LOCAL_DATA=true` to run entirely offline. Scripts read from `Data-Pipeline/data/`
instead of GCS. Ideal for development and CI.

```bash
# Full pipeline (DVC)
USE_LOCAL_DATA=true dvc repro

# Or run scripts directly against local data
export USE_LOCAL_DATA=true
python Data-Pipeline/scripts/validate_data.py
python Data-Pipeline/scripts/anomaly_detection.py
python Data-Pipeline/scripts/bias_analysis.py
```

### GCP mode (reads/writes GCS)

```bash
# Authenticate first (see team-docs/DEV_SETUP.md §2)
gcloud auth application-default login

# Full pipeline — DVC uses gs://f1optimizer-data-lake/dvc-cache as remote
dvc repro

# Or individual stages
dvc repro ingest_jolpica      # Fetch historical data from Jolpica API
dvc repro ingest_fastf1       # Fetch telemetry from FastF1
dvc repro preprocess          # Convert CSVs → Parquet, upload to GCS_PROCESSED
dvc repro validate            # Run schema validation
dvc repro detect_anomalies    # Run anomaly detection
dvc repro build_features      # Build ML feature vectors
dvc repro bias_analysis       # Run bias analysis
```

Key env vars (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `GCS_RAW` | `gs://f1optimizer-data-lake/raw` | Raw data destination |
| `GCS_PROCESSED` | `gs://f1optimizer-data-lake/processed` | Parquet output |
| `USE_LOCAL_DATA` | `false` | Set `true` to skip GCS entirely |
| `SLACK_WEBHOOK_URL` | _(empty)_ | Optional anomaly alerts |
| `AIRFLOW__CORE__EXECUTOR` | `LocalExecutor` | Airflow executor |

### Running Locally (Docker Compose)

```bash
# 1. Set up env
cp .env.example .env          # edit as needed

# 2. Start Airflow
docker-compose -f docker-compose.f1.yml up airflow-webserver airflow-scheduler

# Airflow UI → http://localhost:8080  (admin / admin)
# Trigger the pipeline from the UI, or:
docker-compose -f docker-compose.f1.yml exec airflow-scheduler \
  airflow dags trigger f1_data_pipeline
```

### Accessing the Airflow UI

| Mode | URL | Credentials |
|---|---|---|
| Local (Docker Compose) | http://localhost:8080 | admin / admin |
| GCP VM | http://\<VM_IP\>:8080 | admin / admin |
| Cloud Composer | GCP Console → Composer environments | GCP account |

Get VM IP: `terraform -chdir=infra/terraform output -raw airflow_vm_ip`

### Running on GCP (GCE VM)

The VM is provisioned by Terraform (`infra/terraform/airflow_vm.tf`):

```bash
# 1. Apply Terraform (provisions GCE VM + firewall rule)
terraform -chdir=infra/terraform apply -var-file=dev.tfvars

# 2. Deploy DAGs to GCS (VM auto-syncs every 5 minutes)
bash Data-Pipeline/scripts/deploy_dags.sh
```

### Deploying DAG Updates

Any time you update `Data-Pipeline/dags/f1_pipeline.py`:

```bash
bash Data-Pipeline/scripts/deploy_dags.sh
# The GCE VM syncs from GCS automatically within 5 minutes.
```

### Mock Dataflow (local dev only, not on GCP)

Simulates the Dataflow REST API locally on port 8088:

```bash
docker-compose -f docker-compose.f1.yml up mock-dataflow
# API docs → http://localhost:8088/docs
```

This container is **not** deployed to GCP or Artifact Registry.

### Airflow (pip install, no Docker)

```bash
# Initialize Airflow database
airflow db init

# Start the scheduler and webserver
airflow scheduler &
airflow webserver --port 8080 &

# Trigger the pipeline
airflow dags trigger f1_data_pipeline

# Or use the web UI at http://localhost:8080
```

### Cloud Composer (GCP managed Airflow)

```bash
# 1. Find your Composer environment's GCS bucket
gcloud composer environments describe f1-composer-env \
  --location=us-central1 --project=f1optimizer \
  --format="value(config.dagGcsPrefix)"
# Returns something like: gs://us-central1-f1-composer-XXXXX-bucket/dags

# 2. Upload the DAG
gsutil cp Data-Pipeline/dags/f1_pipeline.py \
  gs://[composer-bucket]/dags/

# 3. Set environment variables in Composer
gcloud composer environments update f1-composer-env \
  --location=us-central1 --project=f1optimizer \
  --update-env-variables=\
GCS_RAW=gs://f1optimizer-data-lake/raw,\
GCS_PROCESSED=gs://f1optimizer-data-lake/processed,\
DATA_BUCKET=f1optimizer-data-lake,\
MODELS_BUCKET=f1optimizer-models

# 4. Trigger via CLI
gcloud composer environments run f1-composer-env \
  --location=us-central1 --project=f1optimizer \
  dags trigger -- f1_data_pipeline
```

The DAG (`Data-Pipeline/dags/f1_pipeline.py`) runs weekly and includes:

| Task | Description |
|---|---|
| `fetch_jolpica` | Jolpica API → data/raw/jolpica/ |
| `fetch_fastf1` | FastF1 → data/raw/fastf1/ |
| `validate_raw` | Check raw files exist and are non-empty |
| `preprocess` | CSV → Parquet normalization |
| `detect_anomalies` | Outlier + missing value checks |
| `build_features` | Lap-by-lap ML feature vectors |
| `bias_analysis` | Representation bias report |

---

## Pipeline Flow Optimization

The DAG is optimised for wall-clock time by running the two ingest tasks in
parallel (`fetch_jolpica_data` ∥ `fetch_fastf1_data`). The FastF1 download is
the dominant bottleneck (~30 min for 3 seasons of 10Hz telemetry); all
downstream tasks wait on it.

```
fetch_jolpica_data  ──┐
                       ├──► validate_raw ──► preprocess ──► detect_anomalies ──► build_features ──► bias_analysis
fetch_fastf1_data  ───┘ ← bottleneck
```

### Gantt Chart

Visualise task durations without the Airflow UI:

```bash
# Generate Gantt chart (PNG + ASCII terminal output)
python Data-Pipeline/scripts/generate_gantt.py
# Output: Data-Pipeline/logs/gantt_chart.png

# ASCII only (no matplotlib required)
python Data-Pipeline/scripts/generate_gantt.py --ascii-only

# Use real timings from a previous run
python Data-Pipeline/scripts/generate_gantt.py \
  --data-file Data-Pipeline/logs/pipeline_runs.json

# Via DVC
dvc repro generate_gantt
```

When `pipeline_runs.json` is absent the script uses hardcoded estimates:

```
Task                    | 0         10        20        30        40        50        60 min
------------------------|----------------------------------------------------------------------
fetch_jolpica_data      | [=====]
fetch_fastf1_data       | [==============================] ← bottleneck
validate_raw_data       |                               [==]
preprocess_data         |                                 [=====]
detect_anomalies        |                                      [=]
build_features          |                                       [=======]
bias_analysis           |                                               [==]
```

Wall-clock total: **47 min** (parallel ingest saves ~5 min vs sequential).

---

## Schema and Statistics

`Data-Pipeline/scripts/validate_data.py` generates data statistics equivalent
to a Great Expectations profile or TFDV `StatisticsGen` output — no external
dependency required.

```bash
# Generate data statistics and validate schema
python Data-Pipeline/scripts/validate_data.py

# Output files:
# Data-Pipeline/logs/data_statistics.json  — full statistics per dataset
# Data-Pipeline/scripts/expectations/      — validation suite results

# Via DVC (tracks both output files)
dvc repro generate_statistics
```

`data_statistics.json` contains per-dataset entries with:
- Row count, column count, completeness %
- Column dtypes (schema)
- Null count and null % per column
- Numeric columns: min, max, mean, std, median
- Categorical columns: unique count + top-5 value frequencies

Terminal output (example with real data):

```
Dataset                        Rows   Cols   Completeness
------------------------------------------------------------------
laps_all                     93,372     12          99.8%
telemetry_all            30,477,110     15          97.2%
race_results                  7,600      8          98.5%
pit_stops                    11,077      6          99.1%
------------------------------------------------------------------
Full statistics → Data-Pipeline/logs/data_statistics.json
```

To upgrade to full Great Expectations or TFDV when needed:

```bash
# Great Expectations
pip install great-expectations
great_expectations init && great_expectations suite new

# TFDV
pip install tensorflow-data-validation
python -c "import tensorflow_data_validation as tfdv; \
  stats = tfdv.generate_statistics_from_dataframe(df); \
  tfdv.visualize_statistics(stats)"
```

---

## Running Tests

```bash
# Run all pipeline tests
pytest Data-Pipeline/tests/ -v

# Run specific test modules
pytest Data-Pipeline/tests/test_anomaly_detection.py -v
pytest Data-Pipeline/tests/test_bias_analysis.py -v
pytest Data-Pipeline/tests/test_fastf1_ingestion.py -v
pytest Data-Pipeline/tests/test_validator.py -v
pytest Data-Pipeline/tests/test_generate_gantt.py -v
pytest Data-Pipeline/tests/test_ingestion.py -v
pytest Data-Pipeline/tests/test_csv_to_parquet.py -v
pytest Data-Pipeline/tests/test_preprocessing.py -v

# With coverage
pytest Data-Pipeline/tests/ -v --cov=Data-Pipeline/scripts --cov=src/ingestion --cov-report=term-missing

# All project tests
pytest tests/ ml/tests/ Data-Pipeline/tests/ -v
```

Expected output: all tests pass (all network calls are mocked).

---

## Code Quality

All code in this repository passes the following checks with **0 errors**:

```bash
# Linting (PEP 8 + style)
ruff check src/ ml/ pipeline/ Data-Pipeline/ tests/
# Expected: no output (0 errors)

# Auto-formatting check (ruff replaces black — no pathspec dependency conflict)
ruff format --check src/ ml/ pipeline/ Data-Pipeline/ tests/
# Expected: no output (0 files would be reformatted)

# Type checking
mypy src/ ml/ --ignore-missing-imports
# Expected: Success: no issues found
```

These checks are enforced in CI/CD (`.github/workflows/ci.yml`).

---

## DVC Remote Setup (GCS)

```bash
# Add GCS as the default DVC remote
dvc remote add -d gcs_remote gs://f1optimizer-data-lake
dvc remote modify gcs_remote credentialpath ~/.config/gcloud/application_default_credentials.json

# Push processed data to GCS
dvc push

# Pull data on another machine
dvc pull
```

The DVC pipeline is defined in `dvc.yaml` at the repo root.
Stages: `ingest_jolpica → ingest_fastf1 → preprocess → validate → detect_anomalies → build_features → bias_analysis → generate_gantt`

---

## Pipeline Outputs

| File | Description |
|---|---|
| `data/raw/jolpica/` | Raw JSON from Jolpica API |
| `data/raw/fastf1/` | Raw CSVs from FastF1 library |
| `data/processed/*.parquet` | Normalized Parquet files (10 files) |
| `data/features/` | ML-ready state vectors |
| `Data-Pipeline/scripts/expectations/validation_suite.json` | Validation results |
| `Data-Pipeline/logs/anomaly_report.json` | Anomaly detection report |
| `Data-Pipeline/logs/bias_report.json` | Bias analysis report |
| `Data-Pipeline/logs/gantt_chart.png` | Pipeline Gantt chart (PNG) |

---

## Troubleshooting

**`dvc repro` fails at `ingest_jolpica`**
→ Check internet connectivity. Jolpica API rate limit: 500 req/hr.
→ Retry after 1 hour or use `export USE_LOCAL_DATA=true` to skip ingestion.

**`validate_data.py` exits with code 1**
→ Critical schema violation. Check `scripts/expectations/validation_suite.json` for details.

**`anomaly_detection.py` exits with code 2**
→ Critical errors (e.g. missing Driver IDs). Investigate the input Parquet file.

**FastF1 download very slow**
→ FastF1 caches to `data/raw/fastf1_cache/`. First run is slow; subsequent runs are instant.

**`ImportError: fastf1`**
→ Install with `pip install fastf1`. FastF1 ingestion is optional; pipeline degrades gracefully.

**Airflow `ModuleNotFoundError`**
→ Ensure the repo root is on `PYTHONPATH`: `export PYTHONPATH=/path/to/test:$PYTHONPATH`

---

## See Also

- [`docs/bias.md`](../docs/bias.md) — Bias analysis findings and mitigation
- [`docs/architecture.md`](../docs/architecture.md) — Full system architecture
- [`team-docs/DEV_SETUP.md`](../team-docs/DEV_SETUP.md) — Developer onboarding (team-internal)
- [`ml/README.md`](../ml/README.md) — ML models and training documentation
