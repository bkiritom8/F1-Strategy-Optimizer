# Data Sources, Splits, and Management

**Last Updated**: 2026-02-18

## Overview

The F1 Strategy Optimizer leverages 74 years of comprehensive Formula 1 data spanning 1950-2024, encompassing race results, pit stops, qualifying sessions, and high-frequency telemetry. This document details data sources, acquisition strategy, preprocessing, splits, and management.

## Data Card

| Attribute | Details |
|-----------|---------|
| **Time Period** | 1950-2024 (74 years) |
| **Total Races** | 1,300+ races |
| **Total Lap Records** | 20M+ laps |
| **Training Data Size** | ~150GB (Cloud SQL + GCS for large blobs) |
| **Primary Formats** | JSON (race results), CSV (telemetry), Time-series (streaming) |
| **Telemetry Frequency** | 10 Hz (FastF1 library, 2018+) |
| **Geographic Coverage** | Global (23 circuits annually) |
| **Drivers Covered** | 800+ drivers across history, ~20 active per season |

## Data Types

### Continuous Variables
- Throttle percentage (0-100%)
- Speed (km/h)
- Fuel load (kg)
- Brake pressure (bar)
- Tire temperature (°C)
- G-forces (lateral, longitudinal)
- Steering angle (degrees)

### Categorical Variables
- Tire compound (Soft/Medium/Hard/Intermediate/Wet)
- Weather conditions (Dry/Wet/Mixed)
- Track surface (Asphalt type)
- DRS status (Open/Closed)
- Safety car status (None/VSC/Full)

### Temporal Variables
- Lap times (ms)
- Sector times (ms)
- Stint duration (laps)
- Race position by lap

### Geospatial Variables
- GPS coordinates (latitude, longitude)
- Track position (distance from start line)
- Corner identification

## Primary Data Sources

### 1. Jolpica F1 API (1950-2026)

**Source**: https://api.jolpi.ca/ergast/f1

**Coverage**:
- 1,300+ races
- Race results (positions, points, retirements)
- Pit stop logs (lap, duration, compound)
- Qualifying sessions
- Driver/constructor standings
- Circuit characteristics

**Format**: JSON/XML REST API

**Update Frequency**: Automated post-race (typically within 24 hours)

**Reliability**: Comprehensive historical archive, community-maintained, high accuracy

**Rate Limits**: None specified, but recommend 1 req/sec for bulk downloads

**Sample Endpoint**:
```
GET https://api.jolpi.ca/ergast/f1/2024/
GET https://api.jolpi.ca/ergast/f1/2024/1/results/
GET https://api.jolpi.ca/ergast/f1/2024/1/pitstops/
```

**Fields Used**:
- `raceId`, `year`, `round`, `circuitId`, `date`
- `driverId`, `constructorId`, `grid`, `position`, `points`
- `lap`, `stop`, `duration`, `time`

### 2. FastF1 Library (2018-2026)

**Source**: https://github.com/theOehrly/FastF1

**Coverage**:
- 200+ races with high-frequency telemetry
- 10 Hz telemetry streams (10 data points per second)
- Car telemetry (throttle, brake, speed, gear, DRS)
- Position data (GPS coordinates, track position)
- Timing data (lap times, sector times, speed traps)

**Format**: Python library interface (pandas DataFrames)

**Data Resolution**: 10 Hz (100ms intervals)

**Telemetry Variables**:
- `Throttle`: Percentage (0-100)
- `Brake`: Boolean or pressure
- `Speed`: km/h
- `nGear`: Gear number (1-8)
- `DRS`: DRS status (0-14, with specific codes)
- `RPM`: Engine RPM
- `X`, `Y`, `Z`: GPS coordinates

**Sample Usage**:
```python
import fastf1

session = fastf1.get_session(2024, 'Monaco', 'R')
session.load()
laps = session.laps
telemetry = laps.pick_driver('VER').pick_fastest().get_telemetry()
```

**Limitations**:
- Telemetry only available from 2018 onwards
- Some sessions may have incomplete data (sensor failures)
- Requires internet connection for initial download

### 3. Supplementary Data Sources

**Track Characteristics**:
- Circuit length, number of corners, elevation changes
- Historical lap records
- Typical pit stop loss time
- Source: Manual curation + Jolpica API

**Weather Data**:
- Temperature, humidity, precipitation
- Wind speed and direction
- Track temperature
- Source: FastF1 session weather data (air temp, track temp, humidity, wind, rainfall)

**Driver Statistics**:
- Career wins, podiums, championships
- Average finishing position
- DNF rate
- Source: Jolpica API aggregation

**Vehicle Setup Specifications**:
- Wing angles (front/rear)
- Suspension settings
- Brake balance presets
- Source: Team technical reports (limited availability)

## Data Rights and Privacy

### Ownership & Licensing

**Jolpica API**:
- Public domain data aggregation (community mirror of the deprecated Ergast API)
- Provided under open-source model
- No commercial restrictions for educational use
- Attribution required: "Data provided by Jolpica/Ergast"

**FastF1**:
- Community-contributed telemetry extraction
- Non-commercial educational use permitted
- MIT License
- Attribution required: "Telemetry via FastF1 library"

**Commercial Use**:
- Competitive deployment requires licensing agreements with FIA (Fédération Internationale de l'Automobile)
- Educational/research use authorized under fair use policies
- Team-specific deployment requires team consent

### Privacy Considerations

- **No PII**: Data represents aggregated race performance and telemetry
- **Public Figures**: Driver data is professional performance (not personal)
- **GDPR-Exempt**: No personal data processing beyond public professional records
- **Compliance**: Follows fair use for educational/research purposes

### Usage Rights for This Project

- Academic/educational use authorized
- Telemetry sourced from publicly available race broadcasts
- All attributions included in codebase and documentation
- No redistribution of raw data; only derived models and insights

## Data Loading Strategy

### Stage 1: Historical Data Ingestion (Week 1-2)

**Jolpica API Download**:
```bash
# Download all seasons 1950-2026
python data/download.py --source ergast --start-year 1950 --end-year 2026

# Expected output:
# - races.json (1,300+ races)
# - results.json (50,000+ results)
# - pitstops.json (100,000+ pit stops)
# - qualifying.json (20,000+ qualifying sessions)
```

**FastF1 Telemetry Download**:
```bash
# Download telemetry 2018-2026
python data/download.py --source fastf1 --start-year 2018 --end-year 2026

# Expected output:
# - telemetry/ (200+ race sessions)
# - laps/ (lap-by-lap timing data)
# - Total: ~120GB uncompressed
```

**Cloud SQL Insert** (`src/ingestion/ergast_ingestion.py`, `src/ingestion/fastf1_ingestion.py`):
```bash
# Trigger via Cloud Run Job (auto-fired by Terraform null_resource after apply)
gcloud run jobs execute f1-data-ingestion \
  --region=us-central1 \
  --project=f1optimizer \
  --wait

# Tables populated in f1_data database (Cloud SQL PostgreSQL 15):
# - lap_features      (Jolpica race/lap results, 1950-2026)
# - telemetry_features (FastF1 10Hz, 2018-2024)
# - driver_profiles   (extracted behavioral profiles)
```

**Estimated Total**: ~150GB uncompressed; large binary blobs (telemetry) stored in GCS (`f1optimizer-data-lake`)

### Stage 2: Data Cleaning & Preprocessing (Week 2-3)

**Missing Data Handling**:
```python
# Occasional sensor failures in telemetry
# Strategy: Linear interpolation for gaps <1 second
# Longer gaps: Mark as NULL, exclude from training

# Example:
telemetry['Throttle'].interpolate(method='linear', limit=10, inplace=True)
```

**Normalization**:
```python
# Normalize throttle/brake values across different car generations
# Mechanical era (1950-1990) vs Hybrid era (2014+)
# Apply standardization: (x - mean) / std per era
```

**Alignment**:
```python
# Align race results with pit stop logs
# Join on (raceId, driverId)
# Validate: Every result should have 0-5 pit stops
```

**Outlier Removal**:
```python
# Remove outliers:
# - Lap times < 30s or > 500s (data errors)
# - DNF laps (crashes, mechanical failures)
# - Safety car periods (artificially slow laps)

# Strategy: Flag laps with lap_time > mean + 3*std
# Remove flagged laps from training
```

**Tire Compound Standardization**:
```python
# Historical tire notation changed in 2011
# Pre-2011: Option/Prime → Post-2011: Soft/Medium/Hard
# Create mapping dictionary:
tire_mapping = {
    'Option': 'Soft',
    'Prime': 'Medium',
    # ... historical mappings
}
```

### Stage 3: Feature Engineering (Week 3-4)

**Tire Age Calculation**:
```python
# Calculate laps since pit stop
# For each stint, assign tire_age = lap - pit_lap

def calculate_tire_age(df):
    df = df.sort_values(['raceId', 'driverId', 'lap'])
    df['tire_age'] = df.groupby(['raceId', 'driverId', 'stint']).cumcount() + 1
    return df
```

**Fuel Remaining Estimation**:
```python
# Model fuel consumption based on telemetry
# Starting fuel: ~110kg (max allowed)
# Consumption rate: ~1.6-2.0 kg/lap (depends on circuit)

def estimate_fuel(df):
    df['fuel_remaining'] = 110 - (df['lap'] * df['fuel_rate'])
    return df
```

**Telemetry Features**:
```python
# Extract per-lap statistics from 10Hz telemetry
features = {
    'mean_throttle': df.groupby('lap')['Throttle'].mean(),
    'std_throttle': df.groupby('lap')['Throttle'].std(),
    'max_speed': df.groupby('lap')['Speed'].max(),
    'brake_count': df.groupby('lap')['Brake'].sum(),  # Number of braking events
    'drs_usage': df.groupby('lap')['DRS'].mean()  # % of lap with DRS active
}
```

**Race Context Features**:
```python
# Position, gap to leader, delta to nearest competitor
df['gap_to_leader'] = df['cumulative_time'] - df.groupby('lap')['cumulative_time'].transform('min')
df['delta_to_next'] = df['cumulative_time'] - df.groupby(['lap', 'position'])['cumulative_time'].shift(1)
```

**Temporal Features**:
```python
# Lap number, stint age, remaining laps
df['lap_number'] = df['lap']
df['stint_age'] = df.groupby(['raceId', 'driverId', 'stint']).cumcount() + 1
df['laps_remaining'] = df['total_laps'] - df['lap']
```

## Data Splitting Strategy

### Temporal Split (Prevents Data Leakage)

| Split | Size | Time Period | Races | Purpose |
|-------|------|-------------|-------|---------|
| **Train** | ~140GB | 1950-2022 | 1,300+ | Extract driver profiles, train baseline models |
| **Validation** | ~5GB | 2023 Q1-Q2 | 10 races | Hyperparameter tuning, model selection |
| **Test** | ~10GB | 2023 Q3-Q4 + 2024 | 20+ races | Final evaluation, ground-truth validation |

### Justification for Temporal Split

1. **Prevents Data Leakage**: No future information used for past predictions
2. **Reflects Real Deployment**: New races arrive sequentially
3. **Tests Generalization**: Validates across regulation changes and eras
4. **Business Alignment**: Models must work on unseen future races

### Split Implementation

```python
# Define split boundaries
TRAIN_END = '2022-12-31'
VAL_START = '2023-01-01'
VAL_END = '2023-06-30'
TEST_START = '2023-07-01'

-- Cloud SQL (PostgreSQL 15) split views
CREATE VIEW train AS
SELECT * FROM lap_features
WHERE race_date <= '2022-12-31';

CREATE VIEW validation AS
SELECT * FROM lap_features
WHERE race_date BETWEEN '2023-01-01' AND '2023-06-30';

CREATE VIEW test AS
SELECT * FROM lap_features
WHERE race_date >= '2023-07-01';
```

### Validation Strategy

**Cross-Validation**: Not applicable (time-series data requires sequential split)

**Holdout Validation**: Use 2023 Q1-Q2 for hyperparameter tuning

**Final Test**: Evaluate on completely unseen 2023 Q3-Q4 + 2024 races

## Data Management

### Storage Architecture

**Cloud SQL Schema** (`src/database/schema.sql`):
```sql
-- PostgreSQL 15 tables (Cloud SQL instance: f1-optimizer-dev, database: f1_data)

CREATE TABLE lap_features (
    race_id         SERIAL PRIMARY KEY,
    year            INTEGER NOT NULL,
    round           INTEGER NOT NULL,
    circuit_id      VARCHAR(64),
    race_date       DATE,
    driver_id       VARCHAR(8),
    lap_number      INTEGER,
    lap_time_ms     BIGINT,
    tire_compound   VARCHAR(16),
    tire_age        INTEGER,
    pit_stop        BOOLEAN DEFAULT FALSE,
    fuel_remaining  FLOAT,
    position        INTEGER,
    ingestion_timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX ON lap_features (race_date);
CREATE INDEX ON lap_features (driver_id);

CREATE TABLE telemetry_features (
    id              BIGSERIAL PRIMARY KEY,
    race_id         VARCHAR(64),
    driver_id       VARCHAR(8),
    lap_number      INTEGER,
    timestamp       TIMESTAMPTZ,
    throttle        FLOAT,
    speed           FLOAT,
    brake           BOOLEAN,
    drs             INTEGER,
    ingestion_timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE driver_profiles (
    driver_id       VARCHAR(8) PRIMARY KEY,
    name            VARCHAR(128),
    aggression      FLOAT,
    consistency     FLOAT,
    pressure_response FLOAT,
    tire_management FLOAT,
    career_races    INTEGER,
    data_quality    FLOAT,
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);
```

**Benefits**:
- Index on `race_date` and `driver_id` for common query patterns
- Private IP — no public exposure; accessible only from VPC
- Automated daily backups with 30-day retention

### Schema Documentation

**Each table includes**:
- Field definitions with data types
- Units (e.g., kg, km/h, ms)
- Transformation logic applied
- Nullability and default values
- Validation rules

**Example**:
```yaml
# raw_telemetry schema
fields:
  - name: race_id
    type: INT64
    description: Unique identifier for race
    nullable: false

  - name: driver_id
    type: STRING
    description: Three-letter driver code (e.g., VER, HAM)
    nullable: false

  - name: lap
    type: INT64
    description: Lap number (1 to total_laps)
    nullable: false

  - name: throttle
    type: FLOAT64
    description: Throttle percentage (0-100)
    unit: percentage
    nullable: true
    validation: 0 <= value <= 100

  - name: speed
    type: FLOAT64
    description: Speed in kilometers per hour
    unit: km/h
    nullable: true
    validation: 0 <= value <= 400
```

### Versioning

**Dataset Versions**: Tagged by week to track preprocessing changes

```bash
# Version naming convention
dataset_v1_week1   # Initial raw data
dataset_v2_week3   # After cleaning
dataset_v3_week5   # After feature engineering
dataset_v4_week7   # Final training set
```

**Schema Versioning**: Git-tracked schema definitions

```bash
git tag -a data-schema-v1.0 -m "Initial schema definition"
git tag -a data-schema-v1.1 -m "Added tire_age feature"
```

### Quality Checks

**Automated Validation** (runs daily):

```python
# Lap time validation
assert (df['lap_time'] > 30000).all(), "Lap times must be > 30s"
assert (df['lap_time'] < 300000).all(), "Lap times must be < 300s"

# Fuel validation
assert (df['fuel_remaining'] >= 0).all(), "Fuel cannot be negative"
assert (df['fuel_remaining'] <= 150).all(), "Fuel cannot exceed 150kg"

# Position validation
assert (df['position'] >= 1).all(), "Position must be >= 1"
assert (df['position'] <= 24).all(), "Position must be <= 24 (max grid)"

# Completeness check
completeness = df.notnull().sum() / len(df)
assert (completeness > 0.95).all(), "Feature completeness must be >95%"
```

**Quality Metrics Dashboard**:
- Completeness percentage per table
- Null value counts per field
- Outlier detection alerts
- Schema drift detection

### Data Refresh Strategy

**Post-Race Updates** (automated):
```bash
# After each race (23 races per season)
# 1. Download new race data from Jolpica API
# 2. Download telemetry from FastF1
# 3. Insert to Cloud SQL lap_features / telemetry_features tables
# 4. Run preprocessing pipeline
# 5. Update feature store
# 6. Trigger model retraining (weekly)

# Cron job: Every Sunday 22:00 UTC (after typical race end)
0 22 * * 0 /path/to/data/refresh.sh
```

**Incremental Updates**:
- Only process new races (not full rebuild)
- Maintain data versioning for rollback
- Validate consistency with historical data

### Backup and Recovery

**Cloud SQL Backups**:
```bash
# Automated daily backups (configured in Terraform, 30-day retention)
# To restore from backup via GCP Console:
# Cloud SQL > f1-optimizer-dev > Backups > Restore

# Manual export to GCS for point-in-time recovery:
gcloud sql export csv f1-optimizer-dev \
  gs://f1optimizer-data-lake/backups/lap_features_$(date +%Y%m%d).csv \
  --database=f1_data \
  --query="SELECT * FROM lap_features" \
  --project=f1optimizer
```

**Recovery Procedure**:
1. Identify corrupted table or data issue
2. Restore from most recent automated Cloud SQL backup (GCP Console)
3. For partial recovery, import from GCS export
4. Re-run ingestion for any races missed since last backup
5. Validate data quality before resuming production

## Data Access Patterns

### Training
- Batch reads from Cloud SQL via psycopg2
- Indexed queries on `race_date` and `driver_id` for efficient splits
- Export to pandas DataFrame for model training

### Inference
- Real-time feature extraction from streaming telemetry
- Cached driver profiles (static)
- Cached circuit characteristics (static)
- Live race context from Dataflow pipeline

### Dashboard
- Aggregated queries (e.g., top drivers by aggression score)
- Historical race lookups
- Cached results for common queries

## Data Security

**Access Control**:
- Service accounts with least-privilege IAM roles (`roles/cloudsql.client`)
- Cloud SQL private IP — only accessible from within VPC
- Audit logging enabled (Cloud Audit Logs)

**Encryption**:
- Data encrypted at rest (Cloud SQL: AES-256, GCS: default)
- Data encrypted in transit (HTTPS, TLS; Cloud SQL `ENCRYPTED_ONLY` mode)

**Compliance**:
- No PII stored
- GDPR-exempt (professional sports data)
- Internal use only (educational project)

## Known Data Issues

### Missing Telemetry
- Pre-2018 races: No high-frequency telemetry available
- Solution: Use lap times and pit stop logs only for historical races

### Sensor Failures
- Occasional telemetry gaps (1-2% of laps)
- Solution: Linear interpolation for gaps <1s, mark as NULL otherwise

### Regulation Changes
- Tire compounds, fuel limits, car specifications change over time
- Solution: Temporal features (year, era) to capture context

### Circuit Layout Changes
- Some circuits modified over decades
- Solution: Track circuit_version in metadata

### Weather Data Granularity
- Historical weather data less precise than modern
- Solution: Categorical binning (Dry/Wet/Mixed) for older races

## Training Pipeline Data Flow

### Overview

ML training runs as an isolated pipeline stage with containerized, distributed execution. Training jobs are orchestrated as scheduled, retryable stages that read from validated storage and write artifacts to dedicated buckets.

### Data Sources for Training

**Input Storage** (READ-ONLY):
```
Cloud SQL Tables (PostgreSQL 15, f1_data database):
├── lap_features         # Primary feature store (Jolpica, 1950-2026)
├── telemetry_features   # FastF1 10Hz telemetry (2018-2024)
├── driver_profiles      # Driver behavioral profiles
├── VIEW: train          # Training split (1950-2022)
├── VIEW: validation     # Validation split (2023 Q1-Q2)
└── VIEW: test           # Test split (2023 Q3-2024)
```

**Prohibited Sources**:
- [FAIL] `raw_races`, `raw_results`, `raw_telemetry` (training never reads raw data)
- [FAIL] `processed_data` (must use versioned train/val/test splits)
- [FAIL] Any streaming Pub/Sub topics (training is batch-only)

### Data Output Destinations

**Artifact Storage** (WRITE-ONLY):
```
GCS Buckets:
├── gs://f1-strategy-artifacts/
│   ├── models/
│   │   ├── tire_degradation/
│   │   │   ├── v1.0/model.pkl
│   │   │   ├── v1.0/metadata.json
│   │   │   └── v1.0/metrics.json
│   │   ├── fuel_consumption/
│   │   ├── brake_bias/
│   │   └── driving_style/
│   │
│   ├── checkpoints/
│   │   └── [job_id]/epoch_*.ckpt
│   │
│   ├── metrics/
│   │   └── [job_id]/
│   │       ├── training_metrics.csv
│   │       ├── validation_metrics.csv
│   │       └── feature_importance.json
│   │
│   └── logs/
│       └── [job_id]/
│           ├── stdout.log
│           └── stderr.log
```

**Prohibited Destinations**:
- [FAIL] Training jobs NEVER write to Cloud SQL `raw_*` tables
- [FAIL] Training jobs NEVER write to `processed_data` tables
- [FAIL] Training jobs NEVER modify feature store directly

### Training Job Architecture

**Containerized Execution**:
```yaml
Training Job:
  - Base Image: gcr.io/f1-strategy/training-worker:latest
  - Entrypoint: python pipeline/training/worker.py
  - Resources: Autoscaling worker pool (CPU/GPU abstracted)
  - Networking: Secure internal VPC, no public internet access
  - IAM: Training service account (read: Cloud SQL, write: GCS artifacts)
```

**Distributed Training**:
- **Horizontal Scaling**: 1-N workers per training job
- **Communication**: Workers communicate via HTTPS (encrypted transport)
- **Coordination**: Parameter server or ring-allreduce (framework-dependent)
- **Fault Tolerance**: Worker failure does not fail job (retry logic)

### Orchestration

**Scheduler**: Vertex AI Pipelines
```python
# Example pipeline definition (Kubeflow DSL)
from kfp.v2 import dsl

@dsl.pipeline(name='f1-training-pipeline')
def training_pipeline(
    data_split: str = 'train',
    model_type: str = 'tire_degradation',
    num_workers: int = 4
):
    # Stage 1: Data validation
    validate_data = dsl.ContainerOp(
        name='validate-data',
        image='gcr.io/f1-strategy/data-validator:latest',
        arguments=['--split', data_split]
    )

    # Stage 2: Distributed training
    train_model = dsl.ContainerOp(
        name='train-model',
        image='gcr.io/f1-strategy/training-worker:latest',
        arguments=[
            '--model', model_type,
            '--data-split', data_split,
            '--num-workers', num_workers
        ]
    ).after(validate_data)

    # Stage 3: Model evaluation
    evaluate_model = dsl.ContainerOp(
        name='evaluate-model',
        image='gcr.io/f1-strategy/evaluator:latest',
        arguments=['--model-uri', train_model.outputs['model_uri']]
    ).after(train_model)
```

**Job Management**:
- **Retries**: Up to 3 retries on failure (configurable)
- **Timeout**: 12 hours max per training job
- **Failure Detection**: Worker heartbeat monitoring (60s interval)
- **Job Restart**: Failed workers automatically restarted
- **Non-Blocking**: Training stages do not block streaming or inference pipelines

**Scheduling**:
```yaml
Training Schedule:
  - Weekly Retraining: Every Monday 02:00 UTC
  - Post-Race Training: Triggered after race data validation (optional)
  - Manual Trigger: Via Vertex AI Pipelines API
  - Concurrent Jobs: Max 4 training jobs in parallel
```

### Infrastructure Provisioning

**Terraform-Managed Resources**:
```hcl
# infrastructure/terraform/training.tf
resource "google_compute_instance_template" "training_worker" {
  name         = "f1-training-worker-template"
  machine_type = var.worker_machine_type  # Abstracted (CPU/GPU)

  disk {
    source_image = "gcr.io/f1-strategy/training-worker:latest"
  }

  network_interface {
    network = google_compute_network.training_vpc.name
    # No external IP (internal-only)
  }

  service_account {
    email  = google_service_account.training_worker.email
    scopes = ["cloud-platform"]
  }
}

resource "google_compute_autoscaler" "training_workers" {
  name   = "f1-training-autoscaler"
  target = google_compute_instance_group_manager.training_workers.id

  autoscaling_policy {
    min_replicas = 0
    max_replicas = 10

    cpu_utilization {
      target = 0.7
    }
  }
}
```

**Autoscaling**:
- **Scale-to-Zero**: Worker pool scales to 0 when no jobs running
- **Scale-Up**: Workers provisioned on-demand when job submitted
- **Scale-Down**: Workers terminated after 10min idle timeout
- **Resource Types**: CPU-optimized, GPU-accelerated, or memory-optimized (abstracted)

### Security

**IAM Roles** (Least-Privilege):
```yaml
Training Service Account: f1-airflow-dev@f1optimizer.iam.gserviceaccount.com

Permissions:
  Cloud SQL:
    - roles/cloudsql.client        # Connect to f1-optimizer-dev instance

  Cloud Storage:
    - roles/storage.objectCreator  # WRITE gs://f1optimizer-models/*
    - roles/storage.objectViewer   # READ gs://f1optimizer-data-lake/*

  Vertex AI:
    - roles/aiplatform.user        # Submit training jobs

  Pub/Sub:
    - roles/pubsub.admin           # Publish/subscribe for DAG events

  Denied:
    - [FAIL] cloudsql.editor       # CANNOT modify Cloud SQL schema
    - [FAIL] storage.admin         # CANNOT delete artifacts
    - [FAIL] compute.admin         # CANNOT modify infrastructure
```

**Network Security**:
- **VPC**: Training workers run in isolated VPC
- **Firewall**: Ingress blocked, egress only to GCP APIs
- **Encryption**: All inter-worker communication uses HTTPS/TLS 1.3
- **No Public Access**: Workers have no external IP addresses

**Data Access**:
- **Read**: Training jobs read from Cloud SQL via IAM-authenticated service account connections
- **Write**: Artifacts written to GCS with server-side encryption (AES-256)
- **Audit Logging**: All data access logged to Cloud Audit Logs

### Training Data Flow Diagram

```
┌─────────────────────────────────────────────────────┐
│ Cloud SQL (PostgreSQL 15, Private IP)              │
│ ├── lap_features (READ-ONLY for training)          │
│ ├── telemetry_features (READ-ONLY)                 │
│ └── driver_profiles (READ-ONLY)                    │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ Secure Query (IAM + VPC, psycopg2)
                   ▼
┌─────────────────────────────────────────────────────┐
│ Training Pipeline (Vertex AI Pipelines)            │
│                                                     │
│  ┌──────────────┐    ┌──────────────┐             │
│  │  Worker 1    │◄──►│  Worker 2    │             │
│  │ (Container)  │    │ (Container)  │             │
│  └──────────────┘    └──────────────┘             │
│         │                    │                     │
│         │  HTTPS/TLS 1.3    │                     │
│         ▼                    ▼                     │
│  ┌──────────────┐    ┌──────────────┐             │
│  │  Worker 3    │◄──►│  Worker N    │             │
│  │ (Container)  │    │ (Container)  │             │
│  └──────────────┘    └──────────────┘             │
└──────────────────┬──────────────────────────────────┘
                   │
                   │ Write Artifacts (IAM Auth, Encrypted)
                   ▼
┌─────────────────────────────────────────────────────┐
│ GCS Artifact Storage (WRITE-ONLY)                  │
│ ├── models/ (trained model binaries)               │
│ ├── checkpoints/ (intermediate states)             │
│ ├── metrics/ (training/validation metrics)         │
│ └── logs/ (execution logs)                         │
└─────────────────────────────────────────────────────┘
```

### Data Validation Before Training

**Pre-Training Checks** (Automated):
```python
# pipeline/training/validate.py
def validate_training_data(split: str) -> bool:
    """Validate data quality before training starts."""

    # Check 1: Data completeness
    query = f"""
        SELECT COUNT(*) as total_rows,
               COUNTIF(lap_time_ms IS NULL) as null_lap_times,
               COUNTIF(tire_age IS NULL) as null_tire_age
        FROM f1_strategy.{split}
    """
    result = bq_client.query(query).result()
    row = list(result)[0]

    completeness = 1 - (row.null_lap_times + row.null_tire_age) / (row.total_rows * 2)
    assert completeness > 0.95, f"Data completeness {completeness:.2%} < 95%"

    # Check 2: Temporal consistency
    query = f"""
        SELECT MIN(race_date) as min_date, MAX(race_date) as max_date
        FROM f1_strategy.{split}
    """
    result = bq_client.query(query).result()
    row = list(result)[0]

    if split == 'train':
        assert row.min_date >= '1950-01-01', "Train split starts too early"
        assert row.max_date <= '2022-12-31', "Train split leaks into validation"

    # Check 3: Feature schema match
    expected_features = ['lap_time_ms', 'tire_age', 'fuel_remaining', ...]
    query = f"SELECT * FROM f1_strategy.{split} LIMIT 1"
    result = bq_client.query(query).result()
    actual_features = [field.name for field in result.schema]

    missing = set(expected_features) - set(actual_features)
    assert not missing, f"Missing features: {missing}"

    return True
```

**Validation Failure Handling**:
- Training job exits with error code
- Alert sent to Slack/PagerDuty
- Logs written to Cloud Logging
- No model artifacts written

### Cost Management

**Training Budget**:
- **Weekly Training**: ~$20-30 (4 workers × 2 hours × $2.50/hr)
- **Monthly Budget**: ~$80-120
- **Cost Alert**: Trigger if single job exceeds $50

**Cost Optimization**:
- Use preemptible VMs for non-critical training
- Cache preprocessed features to reduce Cloud SQL query load
- Autoscale to zero when idle
- Use spot instances (up to 70% cost reduction)

### Monitoring & Observability

**Training Metrics** (Exported to Cloud Monitoring):
```yaml
Metrics:
  - training.job.duration_seconds
  - training.job.failure_count
  - training.worker.cpu_utilization
  - training.worker.memory_usage
  - training.data.records_processed
  - training.model.loss
  - training.model.accuracy
```

**Alerts**:
```yaml
Training Alerts:
  - Job Duration > 12 hours → PagerDuty
  - Job Failure Rate > 20% → Slack
  - Worker OOM → Auto-retry with larger instance
  - Data Validation Failure → Block training, alert owner
```

**Logs**:
- All training logs streamed to Cloud Logging
- Queryable via Log Explorer
- Retention: 30 days

## DAG-Based Pipeline Orchestration

### Overview

All data pipeline stages (ingestion, processing, validation, training) are orchestrated as a Directed Acyclic Graph (DAG). The DAG executor runs in a containerized environment and manages task dependencies, parallel execution, retries, and failure isolation.

### DAG Structure

**Complete Data Pipeline DAG**:
```
┌─────────────────────────────────────────────────────────┐
│ Data Pipeline DAG (Directed Acyclic Graph)             │
│                                                         │
│  ┌──────────────┐                                      │
│  │   Ingest     │                                      │
│  │   Jolpica    │                                      │
│  └──────┬───────┘                                      │
│         │                                               │
│         ▼                                               │
│  ┌──────────────┐     ┌──────────────┐                │
│  │   Ingest     │────>│   Validate   │                │
│  │   FastF1     │     │   Raw Data   │                │
│  └──────┬───────┘     └──────┬───────┘                │
│         │                    │                         │
│         └────────┬───────────┘                         │
│                  ▼                                      │
│           ┌──────────────┐                             │
│           │   Process    │                             │
│           │   & Clean    │                             │
│           └──────┬───────┘                             │
│                  │                                      │
│                  ▼                                      │
│           ┌──────────────┐                             │
│           │   Feature    │                             │
│           │  Engineering │                             │
│           └──────┬───────┘                             │
│                  │                                      │
│       ┌──────────┼──────────┐                          │
│       ▼          ▼          ▼                          │
│  ┌────────┐ ┌────────┐ ┌────────┐                     │
│  │ Train  │ │  Val   │ │  Test  │                     │
│  │ Split  │ │ Split  │ │ Split  │                     │
│  └────┬───┘ └────┬───┘ └────┬───┘                     │
│       │          │          │                          │
│       └──────────┼──────────┘                          │
│                  ▼                                      │
│           ┌──────────────┐                             │
│           │   Driver     │                             │
│           │   Profiles   │                             │
│           └──────┬───────┘                             │
│                  │                                      │
│                  ▼                                      │
│           ┌──────────────┐                             │
│           │   Training   │ (Separate DAG)              │
│           │   Pipeline   │                             │
│           └──────────────┘                             │
└─────────────────────────────────────────────────────────┘
```

### DAG Node Definitions

**Node**: Ingest Jolpica
```yaml
task_id: ingest_jolpica
container: gcr.io/f1-strategy/data-ingestion:latest
command: ["python", "data/download.py", "--source=ergast"]
dependencies: []
retry_policy:
  max_retries: 3
  retry_delay: 60s
timeout: 3600s  # 1 hour
```

**Node**: Ingest FastF1
```yaml
task_id: ingest_fastf1
container: gcr.io/f1-strategy/data-ingestion:latest
command: ["python", "data/download.py", "--source=fastf1"]
dependencies: []
retry_policy:
  max_retries: 3
  retry_delay: 120s
timeout: 21600s  # 6 hours
```

**Node**: Validate Raw Data
```yaml
task_id: validate_raw_data
container: gcr.io/f1-strategy/data-validator:latest
command: ["python", "data/validate.py", "--stage=raw"]
dependencies: [ingest_jolpica, ingest_fastf1]
retry_policy:
  max_retries: 1
  retry_delay: 0s
timeout: 300s  # 5 minutes
```

**Node**: Process & Clean
```yaml
task_id: process_clean
container: gcr.io/f1-strategy/data-processor:latest
command: ["python", "data/preprocess.py"]
dependencies: [validate_raw_data]
retry_policy:
  max_retries: 2
  retry_delay: 30s
timeout: 7200s  # 2 hours
```

**Node**: Feature Engineering
```yaml
task_id: feature_engineering
container: gcr.io/f1-strategy/feature-builder:latest
command: ["python", "data/feature_engineering.py"]
dependencies: [process_clean]
retry_policy:
  max_retries: 2
  retry_delay: 30s
timeout: 3600s  # 1 hour
```

**Parallel Nodes**: Create Data Splits
```yaml
# These run in parallel (no dependencies on each other)
task_id: create_train_split
container: gcr.io/f1-strategy/data-splitter:latest
command: ["python", "data/split.py", "--split=train"]
dependencies: [feature_engineering]

task_id: create_val_split
container: gcr.io/f1-strategy/data-splitter:latest
command: ["python", "data/split.py", "--split=validation"]
dependencies: [feature_engineering]

task_id: create_test_split
container: gcr.io/f1-strategy/data-splitter:latest
command: ["python", "data/split.py", "--split=test"]
dependencies: [feature_engineering]
```

**Node**: Extract Driver Profiles
```yaml
task_id: extract_driver_profiles
container: gcr.io/f1-strategy/driver-profiler:latest
command: ["python", "drivers/extract_profiles.py"]
dependencies: [create_train_split, create_val_split, create_test_split]
retry_policy:
  max_retries: 2
  retry_delay: 60s
timeout: 1800s  # 30 minutes
```

### DAG Execution Model

**Orchestrator Container**:
```dockerfile
# Dockerfile.dag-orchestrator
FROM python:3.11-slim

# Install orchestration dependencies
RUN pip install --no-cache-dir \
    google-cloud-container \
    google-cloud-logging \
    networkx \
    pyyaml

# Copy orchestrator code
COPY pipeline/orchestrator/ /app/orchestrator/
WORKDIR /app

ENTRYPOINT ["python", "-m", "orchestrator.dag_executor"]
```

**Execution Flow**:
1. Orchestrator reads DAG definition (YAML)
2. Builds dependency graph using topological sort
3. Launches tasks in dependency order
4. Monitors task containers for completion
5. Handles retries on failure
6. Supports partial re-runs (start from failed node)
7. Emits logs for each DAG run and task

**Parallel Execution**:
- Tasks with no dependencies run immediately
- Tasks with satisfied dependencies run in parallel
- Max concurrent tasks: 10 (configurable)

**Failure Isolation**:
- Task failure does not fail entire DAG
- Downstream tasks are skipped if dependency fails
- Failed tasks can be retried independently
- Partial re-runs supported (e.g., re-run only failed nodes)

### DAG Definition Format

**File**: `pipeline/orchestrator/dag_definitions/data_pipeline.yaml`

```yaml
dag_id: f1_data_pipeline
description: Complete F1 data ingestion and processing pipeline
schedule: "0 2 * * 1"  # Every Monday at 2:00 AM UTC
default_timeout: 3600
default_retries: 2

tasks:
  - task_id: ingest_jolpica
    container: gcr.io/f1-strategy/data-ingestion:latest
    command: ["python", "data/download.py", "--source=ergast"]
    dependencies: []
    timeout: 3600
    retries: 3

  - task_id: ingest_fastf1
    container: gcr.io/f1-strategy/data-ingestion:latest
    command: ["python", "data/download.py", "--source=fastf1"]
    dependencies: []
    timeout: 21600
    retries: 3

  - task_id: validate_raw_data
    container: gcr.io/f1-strategy/data-validator:latest
    command: ["python", "data/validate.py", "--stage=raw"]
    dependencies: [ingest_jolpica, ingest_fastf1]
    timeout: 300
    retries: 1

  - task_id: process_clean
    container: gcr.io/f1-strategy/data-processor:latest
    command: ["python", "data/preprocess.py"]
    dependencies: [validate_raw_data]
    timeout: 7200
    retries: 2

  # ... (additional tasks)

on_failure:
  action: notify
  channels: [slack, pagerduty]

on_success:
  action: log
  message: "Data pipeline completed successfully"
```

## Pipeline Logging

### Centralized Logging Architecture

**Log Collection**:
- All pipeline tasks emit structured logs
- Logs streamed to Cloud Logging
- Logs indexed by DAG run ID and task ID
- Logs retained independently of task lifecycle

**Log Schema**:
```json
{
  "dag_run_id": "f1_data_pipeline_20260214_120000",
  "task_id": "ingest_jolpica",
  "timestamp": "2026-02-14T12:00:00Z",
  "level": "INFO",
  "event_type": "task_start",
  "message": "Starting Jolpica data ingestion",
  "metadata": {
    "container": "gcr.io/f1-strategy/data-ingestion:v1.2.0",
    "worker_node": "training-worker-3",
    "attempt": 1
  }
}
```

### Log Event Types

**Task Lifecycle Events**:
```yaml
task_start:
  level: INFO
  fields: [dag_run_id, task_id, timestamp, container_image]

task_end:
  level: INFO
  fields: [dag_run_id, task_id, timestamp, duration_seconds, status]

task_retry:
  level: WARNING
  fields: [dag_run_id, task_id, attempt_number, reason, next_retry_time]

task_failure:
  level: ERROR
  fields: [dag_run_id, task_id, error_type, error_message, stack_trace]

task_success:
  level: INFO
  fields: [dag_run_id, task_id, output_artifacts, metrics]
```

**Validation Events**:
```yaml
validation_error:
  level: ERROR
  fields: [dag_run_id, task_id, validation_rule, failed_value, expected_value]

data_quality_warning:
  level: WARNING
  fields: [dag_run_id, task_id, metric_name, measured_value, threshold]
```

**Progress Events**:
```yaml
progress_update:
  level: INFO
  fields: [dag_run_id, task_id, records_processed, total_records, percent_complete]
```

### Logging Implementation

**File**: `pipeline/logging/logger.py`

```python
import logging
import json
from google.cloud import logging as cloud_logging
from datetime import datetime

class PipelineLogger:
    """Centralized logger for pipeline tasks."""

    def __init__(self, dag_run_id: str, task_id: str):
        self.dag_run_id = dag_run_id
        self.task_id = task_id

        # Initialize Cloud Logging
        self.client = cloud_logging.Client()
        self.logger = self.client.logger('f1-pipeline')

    def log_event(self, event_type: str, level: str, message: str, **metadata):
        """Emit structured log event."""

        log_entry = {
            'dag_run_id': self.dag_run_id,
            'task_id': self.task_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': level,
            'event_type': event_type,
            'message': message,
            'metadata': metadata
        }

        # Write to Cloud Logging
        self.logger.log_struct(log_entry, severity=level)

    def task_start(self, container: str, attempt: int = 1):
        """Log task start event."""
        self.log_event(
            event_type='task_start',
            level='INFO',
            message=f'Starting task {self.task_id}',
            container=container,
            attempt=attempt
        )

    def task_end(self, status: str, duration_seconds: float):
        """Log task end event."""
        self.log_event(
            event_type='task_end',
            level='INFO',
            message=f'Task {self.task_id} completed with status {status}',
            status=status,
            duration_seconds=duration_seconds
        )

    def task_retry(self, attempt: int, reason: str, next_retry_time: str):
        """Log task retry event."""
        self.log_event(
            event_type='task_retry',
            level='WARNING',
            message=f'Retrying task {self.task_id} (attempt {attempt})',
            attempt_number=attempt,
            reason=reason,
            next_retry_time=next_retry_time
        )

    def task_failure(self, error_type: str, error_message: str, stack_trace: str):
        """Log task failure event."""
        self.log_event(
            event_type='task_failure',
            level='ERROR',
            message=f'Task {self.task_id} failed: {error_message}',
            error_type=error_type,
            error_message=error_message,
            stack_trace=stack_trace
        )

    def validation_error(self, rule: str, failed_value: str, expected_value: str):
        """Log validation error."""
        self.log_event(
            event_type='validation_error',
            level='ERROR',
            message=f'Validation failed: {rule}',
            validation_rule=rule,
            failed_value=failed_value,
            expected_value=expected_value
        )

    def progress_update(self, records_processed: int, total_records: int):
        """Log progress update."""
        percent = (records_processed / total_records) * 100 if total_records > 0 else 0
        self.log_event(
            event_type='progress_update',
            level='INFO',
            message=f'Progress: {percent:.1f}% ({records_processed}/{total_records})',
            records_processed=records_processed,
            total_records=total_records,
            percent_complete=percent
        )
```

### Log Retention Policy

```yaml
Retention:
  task_logs: 30 days
  validation_errors: 90 days
  dag_run_metadata: 1 year
  audit_logs: 1 year

Storage:
  primary: Cloud Logging
  archive: GCS bucket (gs://f1optimizer-data-lake/logs/pipeline_logs/)
  export_schedule: Daily at 01:00 UTC
```

### Log Querying

**Query DAG Run Logs**:
```sql
-- Cloud Logging query for DAG run logs (via Log Explorer)
SELECT
  timestamp,
  task_id,
  event_type,
  message,
  metadata
FROM f1_strategy.pipeline_logs
WHERE dag_run_id = 'f1_data_pipeline_20260214_120000'
ORDER BY timestamp ASC;
```

**Query Failed Tasks**:
```sql
-- Find all failed tasks in last 7 days
SELECT
  dag_run_id,
  task_id,
  timestamp,
  metadata.error_message
FROM f1_strategy.pipeline_logs
WHERE event_type = 'task_failure'
  AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY timestamp DESC;
```

### Monitoring Dashboard Integration

**Cloud Monitoring Metrics** (derived from logs):
```yaml
pipeline.dag.run_duration_seconds:
  type: gauge
  labels: [dag_id, status]

pipeline.task.failure_count:
  type: counter
  labels: [dag_id, task_id, error_type]

pipeline.task.retry_count:
  type: counter
  labels: [dag_id, task_id]

pipeline.validation.error_count:
  type: counter
  labels: [validation_rule]
```

## Operational Guarantees

### Observability

All data pipeline stages emit comprehensive metrics, logs, and execution signals for full operational visibility.

**Metrics Collection** (per DAG run and per task):

```yaml
Core Metrics:
  task_duration_seconds:
    type: gauge
    labels: [dag_id, task_id, dag_run_id]
    description: Task execution duration
    aggregations: [p50, p95, p99, max]

  task_success_count:
    type: counter
    labels: [dag_id, task_id]
    description: Successful task completions

  task_failure_count:
    type: counter
    labels: [dag_id, task_id, error_type]
    description: Failed task executions

  task_retry_count:
    type: counter
    labels: [dag_id, task_id, attempt_number]
    description: Task retry attempts

  task_queue_delay_seconds:
    type: gauge
    labels: [dag_id, task_id]
    description: Time between task ready and task start
    slo: <60s for p95

  task_scheduling_delay_seconds:
    type: gauge
    labels: [dag_id, task_id]
    description: Time between task submission and execution
    slo: <120s for p95

Data Pipeline Metrics:
  data.records_processed:
    type: counter
    labels: [task_id, table_name]
    description: Number of records processed

  data.validation_errors:
    type: counter
    labels: [task_id, validation_rule]
    description: Data validation errors detected

  data.quality_score:
    type: gauge
    labels: [task_id, metric_name]
    description: Data quality score (0-100)
    threshold: >95
```

**Alerting Rules**:

```yaml
Critical Alerts:
  - name: repeated_task_failures
    condition: task_failure_count > 3 in 1 hour for same task_id
    severity: critical
    channels: [pagerduty, slack]
    action: Block dependent tasks, notify on-call

  - name: sla_violation
    condition: task_duration_seconds > task_sla_threshold
    severity: warning
    channels: [slack]
    sla_thresholds:
      ingest_jolpica: 3600s    # 1 hour
      ingest_fastf1: 21600s    # 6 hours
      validate_raw_data: 300s  # 5 minutes
      process_clean: 7200s     # 2 hours

  - name: orchestrator_unavailable
    condition: no dag_executor heartbeat in 5 minutes
    severity: critical
    channels: [pagerduty]
    action: Restart orchestrator container

  - name: data_quality_degradation
    condition: data.quality_score < 95
    severity: warning
    channels: [slack]
    action: Flag for data team review

Medium Alerts:
  - name: high_retry_rate
    condition: rate(task_retry_count[1h]) > 0.1
    severity: warning
    channels: [slack]

  - name: queue_delay_high
    condition: task_queue_delay_seconds.p95 > 60s
    severity: warning
    channels: [slack]
    action: Check orchestrator capacity
```

**Observability Scope**:
- [OK] Data ingestion (Jolpica, FastF1)
- [OK] Data processing and cleaning
- [OK] Data validation stages
- [OK] Feature engineering and aggregation
- [OK] Distributed training (see docs/training-pipeline.md)

### Cost Controls

Cost controls are enforced across all compute-heavy pipeline stages to prevent budget overruns.

**Resource Limits Per Task**:

```yaml
Task Resource Limits:
  ingest_jolpica:
    cpu_limit: 2 cores
    memory_limit: 8Gi
    timeout: 3600s
    max_cost_per_run: $0.50

  ingest_fastf1:
    cpu_limit: 4 cores
    memory_limit: 16Gi
    timeout: 21600s
    max_cost_per_run: $2.00

  process_clean:
    cpu_limit: 8 cores
    memory_limit: 32Gi
    timeout: 7200s
    max_cost_per_run: $1.50

  feature_engineering:
    cpu_limit: 8 cores
    memory_limit: 32Gi
    timeout: 3600s
    max_cost_per_run: $1.00

  # Training tasks: See docs/training-pipeline.md
```

**Max Runtime Per Job**:

```yaml
Job Timeouts:
  data_pipeline_dag: 36000s  # 10 hours max
  training_pipeline_dag: 57600s  # 16 hours max (see training-pipeline.md)

  # Individual task timeouts enforced in DAG definitions
  # Jobs automatically terminated if timeout exceeded
```

**Autoscaling Bounds**:

```yaml
Orchestrator Autoscaling:
  min_replicas: 1  # Always one orchestrator running
  max_replicas: 3  # Max 3 concurrent DAG runs

Worker Pool Autoscaling:
  data_workers:
    min_replicas: 0  # Scale to zero when idle
    max_replicas: 10
    scale_up_trigger: tasks_queued > 5
    scale_down_delay: 600s  # 10 min idle before scale-down

  training_workers:
    min_replicas: 0
    max_replicas: 20  # Higher limit for distributed training
    scale_up_trigger: training_jobs_queued > 0
    scale_down_delay: 300s  # 5 min idle (training more time-sensitive)
```

**Budget Thresholds & Throttling**:

```yaml
Monthly Budget:
  total: $70  # Hard cap (set in dev.tfvars / prod.tfvars)
  allocation:
    data_pipeline: $15    # Cloud SQL + ingestion jobs
    training_pipeline: $20 # Vertex AI / distributed training
    inference: $10         # Cloud Run API
    storage: $10           # GCS data-lake + models
    monitoring: $5         # Cloud Monitoring
    ci_cd: $5              # Cloud Build + Artifact Registry
    other: $5              # Pub/Sub, Secret Manager, networking

Budget Actions:
  $55 (80% spent):
    action: warning_alert
    channels: [email]
    message: "80% of monthly $70 budget consumed"

  $63 (90% spent):
    action: throttle_non_critical
    scope:
      - Pause weekly retraining jobs
      - Reduce Dataflow max_replicas by 50%
      - Alert engineering

  $70 (100% spent):
    action: emergency_stop
    scope:
      - Block new training jobs
      - Scale Dataflow workers to zero
      - Only allow critical data ingestion
      - Notify project lead

  $80 (114% spent):
    action: hard_shutdown
    scope:
      - Terminate all running Dataflow jobs
      - Scale Cloud Run to zero
      - Require manual approval to restart
```

**Cost Visibility**:

```yaml
Cost Metrics (per DAG run, per stage):
  cost.dag_run_total:
    type: gauge
    labels: [dag_id, dag_run_id]
    description: Total cost for DAG run
    export: GCS cost export bucket

  cost.task_compute:
    type: gauge
    labels: [task_id, dag_run_id]
    description: Compute cost per task

  cost.task_storage:
    type: gauge
    labels: [task_id, dag_run_id]
    description: Storage I/O cost per task

  cost.cumulative_month:
    type: counter
    labels: [pipeline]
    description: Cumulative spend for current month
    reset: Monthly on 1st

Cost Dashboard:
  - Real-time cost tracking per pipeline
  - Cost per DAG run (historical trends)
  - Cost breakdown by task type
  - Projected monthly spend
  - Cost anomaly detection (>50% variance from baseline)
```

**Cost Optimization Strategies**:
- Preemptible VMs for data processing (70% cost reduction)
- Scale-to-zero for idle worker pools
- Storage lifecycle policies (move to Nearline after 30 days)
- Cached Cloud SQL query results (24hr cache)
- Spot instances for training workloads

### Failure Isolation & Blast Radius

Failures are contained to the smallest possible scope to prevent cascading failures across the pipeline.

**Failure Scope Isolation**:

```yaml
Isolation Levels:
  1. Single Task (Smallest Scope):
     - Task failure isolated to that task only
     - Downstream tasks NOT started
     - Parallel tasks continue execution
     - DAG run continues with partial success

  2. Single DAG Run:
     - All tasks in failed DAG run stopped
     - Other concurrent DAG runs unaffected
     - Retry logic scoped to this DAG run only

  3. Pipeline Type (Largest Allowed Scope):
     - Failed data pipeline does NOT impact:
       * Training pipeline
       * Inference pipeline
       * Dashboard queries
     - Failed training job does NOT impact:
       * Data ingestion
       * Streaming inference
       * Live dashboards

Prohibited Scope:
  [FAIL] System-Wide Failures:
     - One pipeline failure NEVER blocks others
     - Orchestrator failure auto-recovers (max 5min downtime)
     - No shared state between pipelines
```

**Retry Policy (Per-Task Scope)**:

```yaml
Retry Configuration:
  scope: task  # Retries apply to individual tasks, NOT entire pipeline

  max_retries: 3
  retry_delay: 60s
  backoff_multiplier: 2.0
  max_retry_delay: 600s

  retry_on:
    - network_timeout
    - resource_unavailable
    - transient_error
    - worker_preempted

  no_retry_on:
    - data_validation_failure  # Data quality issue, not transient
    - permission_denied         # IAM misconfiguration
    - invalid_configuration     # Code/config bug
    - out_of_memory            # Requires larger instance, not retry

Retry Isolation:
  - Retries do NOT reset dependent tasks
  - Retry failures do NOT trigger parent task retry
  - Retry count tracked per task, not per DAG
  - Failed retries logged separately for analysis
```

**Non-Blocking Design**:

```
Pipeline Independence:
┌─────────────────────────────────────────────────────┐
│                                                     │
│  ┌──────────────┐         ┌──────────────┐         │
│  │ Data         │    X    │ Training     │         │
│  │ Pipeline     │ Isolated│ Pipeline     │         │
│  │ (Running)    │         │ (Failed)     │         │
│  └──────────────┘         └──────────────┘         │
│         │                                           │
│         ├─> Inference (Still Works)                │
│         ├─> Dashboard (Still Works)                │
│         └─> Monitoring (Still Works)               │
│                                                     │
│  Training Failure Impact: ZERO on other systems    │
└─────────────────────────────────────────────────────┘
```

**Cascading Failure Prevention**:

```yaml
DAG Branch Isolation:
  # Example: 3 parallel tasks (Train/Val/Test splits)
  # Failure in one branch does NOT cascade to others

  ┌──────────────┐
  │  Feature     │
  │ Engineering  │
  └──────┬───────┘
         │
  ┌──────┼───────────────────┐
  │      │                   │
  ▼      ▼                   ▼
┌────┐ ┌────┐             ┌────┐
│Train│ │Val │  (Failed)  │Test│
│Split│ │Split│     X      │Split│
└────┘ └────┘             └────┘
  │      │                   │
  │      X                   │
  │                          │
  └──────────┬───────────────┘
             ▼
      ┌──────────────┐
      │ Driver       │  ← Only waits for Train/Test
      │ Profiles     │    (Val failure isolated)
      └──────────────┘

Prevention Rules:
  - Tasks only wait for explicit dependencies
  - No implicit cross-branch dependencies
  - Failed branches marked as "skipped_due_to_failure"
  - Downstream tasks check ALL required dependencies before starting
  - Optional dependencies can fail without blocking
```

**Blast Radius Containment**:

```yaml
Impact Boundaries:
  Task Failure:
    affected: 1 task + direct children
    unaffected: parallel tasks, unrelated DAG runs, other pipelines
    recovery: retry task (3x), then manual intervention

  DAG Run Failure:
    affected: all tasks in this DAG run
    unaffected: other DAG runs, other pipelines
    recovery: retry DAG from failed node (partial re-run)

  Orchestrator Failure:
    affected: current DAG runs (paused)
    unaffected: completed tasks, artifact storage, other services
    recovery: auto-restart orchestrator, resume DAG runs

  Worker Pool Exhaustion:
    affected: new tasks (queued)
    unaffected: running tasks, other pipelines
    recovery: autoscaling provisions new workers

  Data Corruption:
    affected: downstream tasks using corrupt data
    unaffected: parallel pipelines, historical data
    recovery: rollback to last good snapshot, re-run from that point
```

### Compliance & Auditability

All pipeline executions are fully auditable with immutable records for compliance and reproducibility.

**Audit Trail Requirements**:

```yaml
Immutable Records:
  1. DAG Definitions (Versioned):
     - Git commit SHA for every DAG run
     - DAG definition stored in Cloud Storage (immutable)
     - Changes tracked via Git history
     - Previous versions queryable

  2. Task Execution Metadata:
     - Task start/end timestamps
     - Container image SHA256 digest
     - Worker node hostname
     - Resource allocation (CPU, memory)
     - Input/output artifact URIs
     - Exit code and status
     - Retry history
     - All metadata written to Cloud SQL pipeline_audit_log (append-only)

  3. IAM Access Logs:
     - All data access logged to Cloud Audit Logs
     - Cloud SQL queries logged (who, what, when)
     - GCS reads/writes logged
     - Service account usage tracked
     - Retention: 1 year (compliance requirement)

  4. Data Lineage:
     - Input datasets → Task → Output artifacts
     - Full provenance chain for every artifact
     - Queryable via Cloud SQL metadata tables
```

**Audit Log Schema**:

```sql
-- Cloud SQL (PostgreSQL 15): pipeline_audit_log table
CREATE TABLE pipeline_audit_log (
  audit_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  timestamp           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  dag_id              VARCHAR(128) NOT NULL,
  dag_run_id          VARCHAR(256) NOT NULL,
  task_id             VARCHAR(128),
  event_type          VARCHAR(64) NOT NULL,  -- task_start, task_end, data_access, iam_auth, etc.
  actor               VARCHAR(256),          -- Service account or user
  resource            VARCHAR(512),          -- Cloud SQL table, GCS object, etc.
  action              VARCHAR(32),           -- read, write, delete, query
  status              VARCHAR(32),           -- success, failure, denied
  metadata            JSONB,
  git_commit_sha      VARCHAR(64),           -- DAG version
  container_image_digest VARCHAR(128)        -- Task container version
);

CREATE INDEX ON pipeline_audit_log (dag_id, task_id);
CREATE INDEX ON pipeline_audit_log (timestamp);
```

**Audit Queries**:

```sql
-- Query: Who accessed what data in the last 30 days?
SELECT
  timestamp,
  actor,
  resource,
  action,
  status
FROM pipeline_audit_log
WHERE event_type = 'data_access'
  AND timestamp >= NOW() - INTERVAL '30 days'
ORDER BY timestamp DESC;

-- Query: Full execution history for a DAG run
SELECT
  task_id,
  event_type,
  timestamp,
  status,
  metadata
FROM pipeline_audit_log
WHERE dag_run_id = 'f1_data_pipeline_20260214_120000'
ORDER BY timestamp ASC;

-- Query: All failed IAM authentication attempts
SELECT
  timestamp,
  actor,
  resource,
  metadata->>'error_message' AS error_message
FROM pipeline_audit_log
WHERE event_type = 'iam_auth'
  AND status = 'denied'
  AND timestamp >= NOW() - INTERVAL '7 days'
ORDER BY timestamp DESC;
```

**Reproducibility Guarantees**:

```yaml
Reproducibility Requirements:
  1. Deterministic Execution:
     - DAG definition (git commit SHA)
     - Container images (SHA256 digest)
     - Input data version (Cloud SQL backup timestamp)
     - Random seeds (fixed per DAG run)

  2. Artifact Versioning:
     - All outputs tagged with dag_run_id
     - GCS versioning enabled
     - Models versioned in registry
     - Checkpoints retained for 7 days

  3. Rollback Capability:
     - Restore from any previous DAG version
     - Re-run with historical data snapshots
     - Recreate exact execution environment
     - Max rollback window: 90 days

Reproducibility Example:
  # Re-run pipeline with exact configuration from 2024-01-15
  python pipeline/orchestrator/replay.py \
    --dag-run-id f1_data_pipeline_20240115_020000 \
    --verify-checksums \
    --output-path gs://f1optimizer-data-lake/replays/

  # Verifies:
  # [OK] Git commit SHA matches
  # [OK] Container image digests match
  # [OK] Input data checksums match
  # [OK] Output artifacts match (bit-for-bit)
```

**Compliance Retention**:

```yaml
Data Retention Policies:
  audit_logs: 1 year (regulatory requirement)
  task_execution_metadata: 1 year
  dag_definitions: permanent (Git history)
  pipeline_logs: 90 days (operational)
  artifact_checksums: 1 year
  cost_data: 3 years (tax/accounting)

Access Controls:
  audit_logs: Read-only (NO deletion allowed)
  execution_metadata: Append-only (immutable after write)
  dag_definitions: Versioned (previous versions preserved)

Export for Compliance:
  - Weekly export of audit logs to secure archive (Cloud Storage Coldline)
  - Encrypted with customer-managed encryption keys (CMEK)
  - Retention: 7 years for regulatory compliance
  - Access: Authorized compliance officers only
```

**Audit Alerting**:

```yaml
Security Alerts:
  - name: unauthorized_data_access
    condition: iam_auth.status = 'denied'
    severity: critical
    channels: [security_team, pagerduty]

  - name: data_deletion_attempt
    condition: action = 'delete' on production tables
    severity: critical
    channels: [security_team, pagerduty]
    action: Block operation, investigate

  - name: unusual_query_volume
    condition: data_access events > 1000 in 1 hour
    severity: warning
    channels: [security_team]
    action: Review for potential data exfiltration

Compliance Alerts:
  - name: audit_log_gap
    condition: no audit events for >10 minutes during active hours
    severity: critical
    channels: [compliance_team]
    action: Investigate logging system

  - name: retention_policy_violation
    condition: audit logs deleted before 1 year
    severity: critical
    channels: [compliance_team, legal]
    action: Block deletion, investigate
```

## Future Enhancements

- **Real-Time Telemetry**: Integrate live race feeds (requires FIA partnership)
- **Video Analysis**: Extract corner-by-corner driver behavior from onboards
- **Tire Temperature**: More granular tire deg modeling with temp data
- **Setup Database**: Expand vehicle setup specifications (currently limited)
- **Multi-Series**: Extend to Formula E, IndyCar, WEC (similar data structure)
- **Federated Learning**: Train on team-specific data without centralizing
- **AutoML Integration**: Automated hyperparameter tuning via Vertex AI AutoML
- **Dynamic DAG Generation**: Auto-generate DAG based on available data sources
- **Conditional Execution**: Skip tasks based on runtime conditions (e.g., no new data)

---

**See Also**:
- CLAUDE.md: High-level project overview
- docs/training-pipeline.md: Distributed training with DAG integration
- docs/architecture.md: DAG orchestration architecture
- docs/models.md: How data flows into ML models
- docs/metrics.md: Data quality KPIs
