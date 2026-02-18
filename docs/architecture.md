# System Architecture and Deployment

**Last Updated**: 2026-02-14

## Overview

The F1 Strategy Optimizer is a production-grade system built on Google Cloud Platform, designed for real-time race strategy recommendations with <500ms P99 latency. This document covers the complete architecture from data ingestion to serving.

## High-Level Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                     DATA LAYER                                 │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────┐         ┌─────────────────┐                  │
│  │ Ergast API │────────>│   BigQuery      │                  │
│  │ (1950-2024)│         │   Raw Tables    │                  │
│  └────────────┘         │   (150GB)       │                  │
│                         └────────┬────────┘                  │
│  ┌────────────┐                 │                            │
│  │ FastF1 SDK │────────>┌───────▼────────┐                  │
│  │ (2018-2024)│         │  Preprocessing  │                  │
│  └────────────┘         │    Pipeline     │                  │
│                         └───────┬────────┘                  │
│                                 │                            │
│                         ┌───────▼────────┐                  │
│                         │ Feature Store   │                  │
│                         │  (BigQuery)     │                  │
│                         └────────────────┘                  │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  STREAMING LAYER                               │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────┐         ┌─────────────────┐                  │
│  │ Live       │────────>│   Pub/Sub       │                  │
│  │ Telemetry  │         │   (10K msg/sec) │                  │
│  └────────────┘         └────────┬────────┘                  │
│                                   │                            │
│                         ┌─────────▼────────┐                  │
│                         │   Dataflow       │                  │
│                         │   (Beam Pipeline)│                  │
│                         └─────────┬────────┘                  │
│                                   │                            │
│                         ┌─────────▼────────┐                  │
│                         │ Real-Time        │                  │
│                         │ Features         │                  │
│                         └────────────────┘                  │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                   ML LAYER                                     │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│  │   Driver   │  │   Tire     │  │   Fuel     │             │
│  │  Profiles  │  │ Degradation│  │Consumption │             │
│  │  (Static)  │  │  (XGBoost) │  │   (LSTM)   │             │
│  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘             │
│        │               │               │                      │
│        └───────────────┴───────────────┘                      │
│                        │                                       │
│  ┌────────────┐  ┌─────▼──────┐  ┌────────────┐             │
│  │Brake Bias  │  │ Monte Carlo│  │  Driving   │             │
│  │(LinReg)    │  │ Simulator  │  │   Style    │             │
│  │            │  │(10K runs)  │  │(DecisionTree)│           │
│  └────────────┘  └────────────┘  └────────────┘             │
│                                                                │
│                   Vertex AI Model Registry                     │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                  SERVING LAYER                                 │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│                    ┌─────────────────┐                        │
│                    │   FastAPI       │                        │
│                    │   (Cloud Run)   │                        │
│                    │   <500ms P99    │                        │
│                    └────────┬────────┘                        │
│                             │                                  │
│              ┌──────────────┼──────────────┐                 │
│              │              │              │                  │
│      ┌───────▼──────┐ ┌────▼─────┐ ┌─────▼──────┐          │
│      │ React        │ │  Mobile  │ │  Internal  │          │
│      │ Dashboard    │ │   API    │ │   Tools    │          │
│      └──────────────┘ └──────────┘ └────────────┘          │
└───────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────┐
│                MONITORING & OPERATIONS                         │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐             │
│  │   Cloud    │  │   Cloud    │  │   Drift    │             │
│  │  Logging   │  │ Monitoring │  │ Detection  │             │
│  └────────────┘  └────────────┘  └────────────┘             │
│                                                                │
│          Alerting → Slack / PagerDuty                         │
└───────────────────────────────────────────────────────────────┘
```

## Component Details

### Data Ingestion Layer

#### Ergast API Ingestion

**Technology**: Python `requests` library + BigQuery Python SDK

**Schedule**: Weekly for historical data, post-race for new races

**Implementation**:
```python
# data/download.py

import requests
import pandas as pd
from google.cloud import bigquery

def download_ergast_data(year_start=1950, year_end=2024):
    """Download race data from Ergast API."""

    base_url = "http://ergast.com/api/f1"

    all_races = []

    for year in range(year_start, year_end + 1):
        response = requests.get(f"{base_url}/{year}.json")
        data = response.json()

        races = data['MRData']['RaceTable']['Races']
        all_races.extend(races)

        time.sleep(1)  # Rate limiting

    # Convert to DataFrame
    races_df = pd.json_normalize(all_races)

    # Upload to BigQuery
    client = bigquery.Client()
    table_id = "f1-strategy.f1_strategy.raw_races"

    job = client.load_table_from_dataframe(races_df, table_id)
    job.result()

    print(f"Loaded {len(races_df)} races to BigQuery")
```

**Error Handling**:
- Retry on HTTP 5xx with exponential backoff
- Cache intermediate results
- Log failed requests for manual review

#### FastF1 Telemetry Ingestion

**Technology**: FastF1 Python library

**Storage**: BigQuery partitioned by race_date

**Implementation**:
```python
# data/download.py

import fastf1
from google.cloud import bigquery

def download_fastf1_telemetry(year, race_name):
    """Download telemetry for a single race."""

    session = fastf1.get_session(year, race_name, 'R')
    session.load()

    # Extract laps and telemetry
    laps = session.laps
    telemetry_list = []

    for idx, lap in laps.iterrows():
        tel = lap.get_telemetry()
        tel['driver_id'] = lap['Driver']
        tel['lap_number'] = lap['LapNumber']
        tel['race_id'] = f"{year}_{race_name}"
        telemetry_list.append(tel)

    telemetry_df = pd.concat(telemetry_list, ignore_index=True)

    # Upload to BigQuery
    client = bigquery.Client()
    table_id = "f1-strategy.f1_strategy.raw_telemetry"

    job = client.load_table_from_dataframe(telemetry_df, table_id)
    job.result()
```

**Caching**: FastF1 caches downloaded data locally (~/.fastf1/)

**Limitations**: Requires ~5-10 minutes per race session download

### Preprocessing Pipeline

**Technology**: BigQuery SQL + Python pandas

**Execution**: Cloud Functions triggered on new data

**Steps**:
1. Data cleaning (remove outliers, handle NULLs)
2. Feature engineering (tire age, fuel estimation, race context)
3. Normalization (standardize values across eras)
4. Feature store update

**Implementation**:
```python
# data/preprocess.py

from google.cloud import bigquery

def preprocess_races():
    """Run preprocessing SQL queries."""

    client = bigquery.Client()

    # Step 1: Clean data
    clean_query = """
    CREATE OR REPLACE TABLE f1_strategy.clean_races AS
    SELECT *
    FROM f1_strategy.raw_races
    WHERE lap_time BETWEEN 30000 AND 300000  -- Valid lap times (30s-300s)
      AND lap_time IS NOT NULL
    """

    client.query(clean_query).result()

    # Step 2: Feature engineering
    feature_query = """
    CREATE OR REPLACE TABLE f1_strategy.f1_features AS
    SELECT
        race_id,
        driver_id,
        lap,
        lap_time,

        -- Tire age calculation
        lap - LAG(lap) OVER (
            PARTITION BY race_id, driver_id
            ORDER BY lap
        ) AS tire_age,

        -- Gap to leader
        cumulative_time - MIN(cumulative_time) OVER (
            PARTITION BY lap
        ) AS gap_to_leader,

        -- Context features
        total_laps - lap AS laps_remaining,
        ...

    FROM f1_strategy.clean_races
    """

    client.query(feature_query).result()

    print("Preprocessing complete")
```

### Streaming Pipeline (Real-Time)

**Technology**: Apache Beam (Dataflow) on Google Cloud

**Purpose**: Process live telemetry during races for real-time recommendations

**Implementation**:
```python
# pipeline/dataflow_job.py

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions

def process_telemetry(element):
    """
    Process telemetry message.

    Input: {'driver_id': 'VER', 'lap': 15, 'throttle': 95, ...}
    Output: Feature dict ready for model inference
    """

    # Extract features
    features = {
        'driver_id': element['driver_id'],
        'lap': element['lap'],
        'throttle_mean': element['throttle'],
        'speed_max': element['speed'],
        'tire_age': calculate_tire_age(element),
        'fuel_remaining': estimate_fuel(element),
        # ...
    }

    return features

def run_pipeline():
    """Run Dataflow streaming pipeline."""

    options = PipelineOptions(
        runner='DataflowRunner',
        project='f1-strategy',
        region='us-central1',
        temp_location='gs://f1-telemetry/temp',
        streaming=True
    )

    with beam.Pipeline(options=options) as p:
        (
            p
            | 'Read from Pub/Sub' >> beam.io.ReadFromPubSub(
                subscription='projects/f1-strategy/subscriptions/telemetry-sub'
            )
            | 'Parse JSON' >> beam.Map(lambda x: json.loads(x))
            | 'Extract Features' >> beam.Map(process_telemetry)
            | 'Write to BigQuery' >> beam.io.WriteToBigQuery(
                'f1-strategy:f1_strategy.live_features',
                schema='...',
                write_disposition=beam.io.BigQueryDisposition.WRITE_APPEND
            )
        )
```

**Windowing**: 5-second tumbling windows to reduce message volume

**Scaling**: Auto-scales 1-10 workers based on Pub/Sub backlog

### Model Serving

#### FastAPI Application

**Technology**: FastAPI + Uvicorn on Cloud Run

**Endpoints**:

**1. `/recommend` - Main recommendation endpoint**

```python
# serving/api.py

from fastapi import FastAPI
from pydantic import BaseModel
import joblib
import numpy as np

app = FastAPI()

# Load models at startup
models = {
    'tire_degradation': joblib.load('models/tire_degradation_v1.pkl'),
    'fuel_consumption': tf.keras.models.load_model('models/fuel_consumption_v1.h5'),
    'brake_bias': joblib.load('models/brake_bias_v1.pkl'),
    'driving_style': joblib.load('models/driving_style_v1.pkl')
}

# Load driver profiles
with open('drivers/profiles.json', 'r') as f:
    driver_profiles = json.load(f)

class RaceContext(BaseModel):
    driver_id: str
    lap: int
    position: int
    tire_age: int
    tire_compound: str
    fuel_remaining: float
    gap_to_leader: float
    circuit_id: str

@app.post("/recommend")
async def get_recommendation(context: RaceContext):
    """
    Get race strategy recommendation.

    Returns:
        - Pit strategy (lap, compound, fuel)
        - Driving mode (PUSH/BALANCED/CONSERVE)
        - Brake bias (%)
        - Throttle guidance
    """

    # Get driver profile
    driver_profile = next(
        (p for p in driver_profiles if p['driver_id'] == context.driver_id),
        None
    )

    # Run Monte Carlo simulation
    pit_strategies = monte_carlo_optimization(
        context.dict(),
        driver_profile,
        models,
        n_scenarios=5000  # Reduced for live inference
    )

    # Get driving style recommendation
    driving_mode = models['driving_style'].predict({
        'gap_to_leader': context.gap_to_leader,
        'lap_number': context.lap,
        'fuel_remaining': context.fuel_remaining,
        # ...
    })

    # Get brake bias recommendation
    brake_bias = models['brake_bias'].predict({
        'tire_age_front': context.tire_age,
        'fuel_load': context.fuel_remaining,
        # ...
    })

    return {
        'pit_strategy': {
            'recommended_lap': pit_strategies[0]['pit_lap'],
            'compound': pit_strategies[0]['compound'],
            'win_probability': pit_strategies[0]['win_prob']
        },
        'driving_mode': driving_mode,
        'brake_bias': brake_bias,
        'throttle_guidance': {
            'corner_3': 'Lift early to preserve tires',
            'corner_7': 'Aggressive acceleration'
        },
        'confidence': 0.87
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy"}

@app.get("/driver-profile/{driver_id}")
async def get_driver_profile(driver_id: str):
    """Get driver behavioral profile."""
    profile = next(
        (p for p in driver_profiles if p['driver_id'] == driver_id),
        None
    )
    return profile
```

**2. `/simulate` - Race simulation endpoint**

```python
@app.post("/simulate")
async def simulate_race_endpoint(race_setup: RaceSetup):
    """
    Simulate full race with given parameters.

    Returns:
        Predicted finishing positions, lap times, fuel usage
    """

    result = simulate_race(
        race_setup.dict(),
        driver_profiles,
        models
    )

    return result
```

#### Cloud Run Deployment

**Configuration**:
```yaml
# Dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "serving.api:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Deployment**:
```bash
# Build and deploy
gcloud builds submit --tag gcr.io/f1-strategy/api
gcloud run deploy f1-api \
  --image gcr.io/f1-strategy/api \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 4Gi \
  --cpu 2 \
  --timeout 30s \
  --max-instances 20 \
  --min-instances 1
```

**Auto-Scaling**:
- Min instances: 1 (keep warm)
- Max instances: 20
- Target CPU: 70%
- Target concurrency: 100 requests

### Dashboard (React)

**Technology**: React 18 + Next.js + TypeScript + Tailwind CSS

**Components**:

1. **Driver Profile Viewer**: Scatter plot of aggression vs consistency
2. **Lap-by-Lap Guidance**: Real-time recommendations
3. **Race Simulation**: Visualize simulated race outcomes
4. **Historical Analysis**: Compare past races

**Implementation**:
```typescript
// dashboard/src/components/RecommendationPanel.tsx

import React, { useState, useEffect } from 'react';
import axios from 'axios';

interface RaceContext {
  driver_id: string;
  lap: number;
  position: number;
  // ...
}

const RecommendationPanel: React.FC = () => {
  const [context, setContext] = useState<RaceContext>({...});
  const [recommendation, setRecommendation] = useState(null);

  const fetchRecommendation = async () => {
    const response = await axios.post(
      'https://f1-api-xxx.run.app/recommend',
      context
    );
    setRecommendation(response.data);
  };

  useEffect(() => {
    fetchRecommendation();
    const interval = setInterval(fetchRecommendation, 2000);  // Update every 2s
    return () => clearInterval(interval);
  }, [context]);

  return (
    <div className="p-4 bg-gray-900 text-white">
      <h2>Race Strategy Recommendation</h2>

      {recommendation && (
        <>
          <div className="pit-strategy">
            <h3>Pit Strategy</h3>
            <p>Recommended Pit Lap: {recommendation.pit_strategy.recommended_lap}</p>
            <p>Compound: {recommendation.pit_strategy.compound}</p>
            <p>Win Probability: {recommendation.pit_strategy.win_probability * 100}%</p>
          </div>

          <div className="driving-mode">
            <h3>Driving Mode</h3>
            <p className={`mode-${recommendation.driving_mode.toLowerCase()}`}>
              {recommendation.driving_mode}
            </p>
          </div>

          <div className="brake-bias">
            <h3>Brake Bias</h3>
            <p>{recommendation.brake_bias}% front</p>
          </div>
        </>
      )}
    </div>
  );
};

export default RecommendationPanel;
```

**Deployment**: Vercel or Cloud Run (static hosting)

## Infrastructure as Code

**Terraform Configuration**:

```hcl
# infrastructure/main.tf

provider "google" {
  project = "f1-strategy"
  region  = "us-central1"
}

# BigQuery Dataset
resource "google_bigquery_dataset" "f1_strategy" {
  dataset_id = "f1_strategy"
  location   = "US"
}

# Pub/Sub Topic
resource "google_pubsub_topic" "telemetry" {
  name = "telemetry-topic"
}

# Pub/Sub Subscription
resource "google_pubsub_subscription" "telemetry_sub" {
  name  = "telemetry-sub"
  topic = google_pubsub_topic.telemetry.name

  ack_deadline_seconds = 60
}

# Cloud Run Service
resource "google_cloud_run_service" "f1_api" {
  name     = "f1-api"
  location = "us-central1"

  template {
    spec {
      containers {
        image = "gcr.io/f1-strategy/api:latest"

        resources {
          limits = {
            memory = "4Gi"
            cpu    = "2"
          }
        }
      }
    }

    metadata {
      annotations = {
        "autoscaling.knative.dev/minScale" = "1"
        "autoscaling.knative.dev/maxScale" = "20"
      }
    }
  }

  traffic {
    percent         = 100
    latest_revision = true
  }
}
```

## Security

### IAM Roles

**Service Accounts**:
- `f1-dataflow@`: BigQuery write, Pub/Sub read
- `f1-api@`: BigQuery read, Model Registry read
- `f1-monitoring@`: Cloud Logging write, Monitoring write

**Least Privilege**: Each service account has minimal permissions

### Authentication

**API Authentication**:
- API keys for dashboard (OAuth 2.0)
- Service account for internal services
- No public unauthenticated access (except health check)

### Data Encryption

**At Rest**: Default GCP encryption (AES-256)
**In Transit**: TLS 1.3 for all API calls
**Secrets**: Google Secret Manager for API keys, credentials

## Cost Optimization

**Estimated Monthly Costs**:

| Service | Usage | Cost |
|---------|-------|------|
| BigQuery Storage | 150GB | $3 |
| BigQuery Queries | 500GB/month | $2.50 |
| Cloud Run | 100K requests/month | $5 |
| Dataflow (streaming) | 2 workers × 24h | $150 |
| Vertex AI Training | 10 hrs/month | $20 |
| Pub/Sub | 10M messages/month | $2 |
| **Total** | | **~$182/month** |

**Cost Controls**:
- BigQuery partition pruning (save 90% on queries)
- Cloud Run min instances = 1 (avoid cold starts, but not expensive)
- Dataflow auto-scaling (scale down during non-race periods)
- Model caching (reduce inference costs)

## Disaster Recovery

**Backup Strategy**:
- BigQuery snapshots: Daily
- Model artifacts: Versioned in GCS
- Code: GitHub (main source of truth)

**Recovery Time Objective (RTO)**: <30 minutes
**Recovery Point Objective (RPO)**: <24 hours

**Failure Scenarios**:

1. **API Downtime**: Auto-restart Cloud Run, multi-region failover
2. **Data Corruption**: Restore from snapshot, reprocess from raw
3. **Model Failure**: Rollback to previous version in Model Registry
4. **GCP Outage**: Multi-region deployment (future enhancement)

---

**See Also**:
- CLAUDE.md: High-level overview
- docs/data.md: Data pipeline details
- docs/models.md: Model serving details
- docs/monitoring.md: Operational monitoring
