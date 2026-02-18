# Operational Monitoring and Alerting

**Last Updated**: 2026-02-14

## Overview

Production monitoring for the F1 Strategy Optimizer using Google Cloud Monitoring, Cloud Logging, and custom alerting. This document covers metrics collection, dashboards, alert rules, and incident response procedures.

## Monitoring Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     APPLICATION LAYER                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │ FastAPI  │  │ Dataflow │  │BigQuery  │                 │
│  │(Cloud Run)│  │Pipeline  │  │Queries   │                 │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                 │
│       │             │             │                         │
│       └─────────────┴─────────────┘                         │
│                     │                                        │
│             ┌───────▼────────┐                              │
│             │  Cloud Logging │                              │
│             │  (Structured)  │                              │
│             └───────┬────────┘                              │
└─────────────────────┼──────────────────────────────────────┘
                      │
                      │
┌─────────────────────▼──────────────────────────────────────┐
│                 MONITORING LAYER                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │ Cloud Monitoring │  │  Custom Metrics  │               │
│  │   (GCP Native)   │  │  (Pub/Sub based) │               │
│  └────────┬─────────┘  └────────┬─────────┘               │
│           │                     │                           │
│           └──────────┬──────────┘                           │
│                      │                                       │
│           ┌──────────▼──────────┐                           │
│           │  Alerting Engine    │                           │
│           │  (Alert Policies)   │                           │
│           └──────────┬──────────┘                           │
└──────────────────────┼──────────────────────────────────────┘
                       │
           ┌───────────┴───────────┐
           │                       │
┌──────────▼─────────┐  ┌─────────▼──────────┐
│  Slack Webhook     │  │  PagerDuty (future)│
│  (Immediate Alerts)│  │  (Critical Only)    │
└────────────────────┘  └────────────────────┘
```

## What to Monitor

### 1. Model Performance Metrics

**Metrics**:
- `f1/model/tire_degradation/mae`: Mean absolute error (target: <50ms)
- `f1/model/fuel_consumption/rmse`: Root mean square error (target: <0.5 kg/lap)
- `f1/model/brake_bias/accuracy`: Percentage within ±1% (target: >95%)
- `f1/model/driving_style/accuracy`: Classification accuracy (target: >75%)

**Collection Method**:
```python
# models/monitoring.py

from google.cloud import monitoring_v3

def log_model_metric(metric_name, value):
    """
    Log model performance metric to Cloud Monitoring.

    Args:
        metric_name: e.g., 'tire_degradation_mae'
        value: Metric value (float)
    """

    client = monitoring_v3.MetricServiceClient()
    project_name = f"projects/{PROJECT_ID}"

    series = monitoring_v3.TimeSeries()
    series.metric.type = f"custom.googleapis.com/f1/model/{metric_name}"

    now = time.time()
    seconds = int(now)
    nanos = int((now - seconds) * 10 ** 9)

    interval = monitoring_v3.TimeInterval(
        {"end_time": {"seconds": seconds, "nanos": nanos}}
    )

    point = monitoring_v3.Point(
        {"interval": interval, "value": {"double_value": value}}
    )

    series.points = [point]
    client.create_time_series(name=project_name, time_series=[series])

# Usage
mae = calculate_mae(y_true, y_pred)
log_model_metric('tire_degradation_mae', mae)
```

**Frequency**: After each race (post-race analysis), weekly aggregation

**Alert Rules**:
| Metric | Condition | Threshold | Action |
|--------|-----------|-----------|--------|
| MAE (Tire) | > | 60ms | Warning: Review model |
| MAE (Tire) | > | 100ms | Critical: Retrain required |
| RMSE (Fuel) | > | 0.7 kg/lap | Warning: Monitor |
| RMSE (Fuel) | > | 1.0 kg/lap | Critical: Retrain required |
| Accuracy (Brake) | < | 90% | Warning: Check data quality |
| Accuracy (Style) | < | 70% | Warning: Review classifier |

### 2. API Latency Metrics

**Metrics**:
- `f1/api/latency/p50`: 50th percentile (median)
- `f1/api/latency/p95`: 95th percentile
- `f1/api/latency/p99`: 99th percentile (target: <500ms)
- `f1/api/latency/max`: Maximum latency

**Collection Method**:
```python
# serving/api.py

import time
from fastapi import Request
from prometheus_client import Histogram

# Prometheus histogram for latency tracking
REQUEST_LATENCY = Histogram(
    'f1_api_request_latency_seconds',
    'API request latency in seconds',
    buckets=[0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0]
)

@app.middleware("http")
async def track_latency(request: Request, call_next):
    start_time = time.time()

    response = await call_next(request)

    latency = time.time() - start_time
    REQUEST_LATENCY.observe(latency)

    # Also log to Cloud Monitoring
    log_metric('api_latency', latency * 1000)  # Convert to ms

    return response
```

**Frequency**: Every request (sampled at 10% for high volume)

**Alert Rules**:
| Metric | Condition | Threshold | Duration | Action |
|--------|-----------|-----------|----------|--------|
| P99 | > | 600ms | 5 min | Page on-call engineer |
| P99 | > | 800ms | 2 min | Auto-rollback trigger |
| P50 | > | 300ms | 10 min | Investigate performance |
| Max | > | 5000ms | 1 request | Log for analysis |

### 3. Data Pipeline Metrics

**Metrics**:
- `f1/dataflow/lag_seconds`: Delay between telemetry arrival and processing
- `f1/dataflow/throughput`: Messages processed per second
- `f1/dataflow/error_rate`: Percentage of failed messages
- `f1/bigquery/query_latency`: Query execution time

**Collection Method**:
```python
# pipeline/dataflow_job.py

import apache_beam as beam

class MonitoringDoFn(beam.DoFn):
    def process(self, element):
        # Calculate lag
        arrival_time = element['timestamp']
        processing_time = time.time()
        lag = processing_time - arrival_time

        # Log to Cloud Monitoring
        log_metric('dataflow_lag_seconds', lag)

        yield element
```

**Frequency**: Continuous (streaming pipeline)

**Alert Rules**:
| Metric | Condition | Threshold | Duration | Action |
|--------|-----------|-----------|----------|--------|
| Lag | > | 60s | 5 min | Alert data team |
| Lag | > | 300s | 1 min | Critical: Check Dataflow |
| Error Rate | > | 1% | 10 min | Investigate errors |
| Error Rate | > | 5% | 1 min | Critical: Pipeline failing |

### 4. Data Quality Metrics

**Metrics**:
- `f1/data/completeness`: Percentage of non-NULL values
- `f1/data/freshness`: Age of most recent data (hours)
- `f1/data/outliers`: Percentage of flagged outlier records
- `f1/data/schema_drift`: Schema changes detected

**Collection Method**:
```python
# data/quality_checks.py

def check_data_quality(table_name):
    """Run data quality checks on BigQuery table."""

    client = bigquery.Client()

    # Completeness check
    query = f"""
    SELECT
        COUNTIF(lap_time IS NOT NULL) / COUNT(*) AS completeness
    FROM `{table_name}`
    WHERE DATE(race_date) = CURRENT_DATE()
    """

    result = client.query(query).result()
    completeness = list(result)[0].completeness

    log_metric('data_completeness', completeness)

    # Freshness check
    query = f"""
    SELECT
        TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), MAX(ingestion_timestamp), HOUR) AS age_hours
    FROM `{table_name}`
    """

    result = client.query(query).result()
    age_hours = list(result)[0].age_hours

    log_metric('data_freshness_hours', age_hours)

    return {
        'completeness': completeness,
        'age_hours': age_hours
    }
```

**Frequency**: Daily (automated job at 02:00 UTC)

**Alert Rules**:
| Metric | Condition | Threshold | Action |
|--------|-----------|-----------|--------|
| Completeness | < | 95% | Investigate missing data |
| Completeness | < | 90% | Critical: Data quality issue |
| Freshness | > | 48h | Warning: Stale data |
| Freshness | > | 120h (5 days) | Critical: Ingestion broken |
| Outliers | > | 1% | Review data validation |

### 5. Cost Metrics

**Metrics**:
- `f1/cost/bigquery_daily`: BigQuery spend per day
- `f1/cost/cloud_run_daily`: Cloud Run spend per day
- `f1/cost/dataflow_daily`: Dataflow spend per day
- `f1/cost/total_projected`: Projected monthly spend

**Collection Method**:
```python
# monitoring/cost_tracking.py

from google.cloud import billing_v1

def get_daily_costs():
    """Retrieve daily GCP costs from Cloud Billing API."""

    client = billing_v1.CloudBillingClient()
    # Query billing export in BigQuery
    bq_client = bigquery.Client()

    query = """
    SELECT
        service.description AS service,
        SUM(cost) AS total_cost
    FROM `f1-strategy.billing_export.gcp_billing_export_v1_*`
    WHERE DATE(_TABLE_SUFFIX) = CURRENT_DATE()
    GROUP BY service
    """

    results = bq_client.query(query).result()

    costs = {row.service: row.total_cost for row in results}

    # Log individual service costs
    for service, cost in costs.items():
        log_metric(f"cost_{service.lower().replace(' ', '_')}_daily", cost)

    # Calculate projected monthly cost
    projected_monthly = sum(costs.values()) * 30

    log_metric('cost_total_projected', projected_monthly)

    return costs
```

**Frequency**: Daily at 06:00 UTC

**Alert Rules**:
| Metric | Condition | Threshold | Action |
|--------|-----------|-----------|--------|
| Projected Monthly | > | $300 | Warning: Review costs |
| Projected Monthly | > | $400 | Critical: Optimize immediately |
| Dataflow Daily | > | $15 | Investigate Dataflow usage |
| BigQuery Daily | > | $5 | Review query patterns |

### 6. System Health Metrics

**Metrics**:
- `f1/system/uptime`: Percentage of successful health checks
- `f1/system/error_rate`: API error rate (4xx, 5xx)
- `f1/system/active_users`: Number of concurrent dashboard users
- `f1/system/request_rate`: Requests per second

**Collection Method**:
```python
# serving/health.py

from fastapi import FastAPI, Response

@app.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        200 OK if healthy, 503 Service Unavailable if not
    """

    # Check model loading
    if models is None:
        return Response(status_code=503, content="Models not loaded")

    # Check BigQuery connectivity
    try:
        client = bigquery.Client()
        client.query("SELECT 1").result()
    except Exception as e:
        return Response(status_code=503, content=f"BigQuery unreachable: {e}")

    # Check driver profiles loaded
    if not driver_profiles:
        return Response(status_code=503, content="Driver profiles not loaded")

    # All checks passed
    log_metric('system_health', 1)  # 1 = healthy
    return {"status": "healthy", "timestamp": time.time()}
```

**Frequency**: Health check every 30 seconds (Cloud Monitoring uptime check)

**Alert Rules**:
| Metric | Condition | Threshold | Duration | Action |
|--------|-----------|-----------|----------|--------|
| Uptime | < | 99% | Race weekend | Page infrastructure team |
| Error Rate | > | 1% | 10 min | Investigate errors |
| Error Rate | > | 5% | 1 min | Critical: Rollback |

## Monitoring Dashboards

### 1. Model Performance Dashboard

**Panels**:
1. Tire Degradation MAE (line chart, last 30 days)
2. Fuel Consumption RMSE (line chart, last 30 days)
3. Brake Bias Accuracy (gauge, current value)
4. Driving Style Accuracy (gauge, current value)
5. Podium Prediction Accuracy (bar chart, per race)
6. Winner Prediction Accuracy (bar chart, per race)

**Refresh Rate**: Every 5 minutes

**Access**: Public dashboard (read-only)

### 2. API Performance Dashboard

**Panels**:
1. API Latency (P50, P95, P99) (line chart, last 24 hours)
2. Request Rate (requests/sec) (line chart, last 24 hours)
3. Error Rate (4xx, 5xx) (stacked area chart, last 24 hours)
4. Uptime (SLA gauge, current month)
5. Top Slowest Endpoints (table, last hour)
6. Active Users (gauge, current)

**Refresh Rate**: Every 30 seconds

**Access**: Internal team only

### 3. Data Pipeline Dashboard

**Panels**:
1. Dataflow Lag (line chart, last 6 hours)
2. Dataflow Throughput (line chart, last 6 hours)
3. BigQuery Query Latency (histogram, last hour)
4. Data Freshness (gauge, current)
5. Data Completeness (gauge, current)
6. Outlier Rate (line chart, last 7 days)

**Refresh Rate**: Every 1 minute

**Access**: Data engineering team

### 4. Cost Dashboard

**Panels**:
1. Daily Costs by Service (stacked bar chart, last 30 days)
2. Projected Monthly Cost (gauge, current month)
3. Cost per Prediction (line chart, last 30 days)
4. Top 10 Most Expensive Queries (table, last 7 days)
5. Dataflow Worker Hours (line chart, last 30 days)
6. Budget Status (progress bar, current month)

**Refresh Rate**: Daily

**Access**: Project leads, finance team

## Alert Policies

### Critical Alerts (Page On-Call)

**1. API P99 Latency > 800ms**
```yaml
alert_policy:
  display_name: "Critical: API Latency P99 > 800ms"
  conditions:
    - display_name: "P99 latency exceeds 800ms"
      condition_threshold:
        filter: 'metric.type="custom.googleapis.com/f1/api/latency/p99"'
        comparison: COMPARISON_GT
        threshold_value: 800
        duration: 120s  # 2 minutes
  notification_channels:
    - slack_critical
    - pagerduty  # future
  documentation:
    content: "API latency critical. Check Cloud Run logs. Consider auto-rollback."
```

**2. System Uptime < 99% (Race Weekend)**
```yaml
alert_policy:
  display_name: "Critical: Uptime < 99% during race weekend"
  conditions:
    - display_name: "Uptime below SLA"
      condition_threshold:
        filter: 'metric.type="custom.googleapis.com/f1/system/uptime"'
        comparison: COMPARISON_LT
        threshold_value: 0.99
        duration: 300s  # 5 minutes
  notification_channels:
    - slack_critical
  documentation:
    content: "System uptime below SLA. Investigate immediately. Check /health endpoint."
```

**3. Dataflow Lag > 300s**
```yaml
alert_policy:
  display_name: "Critical: Dataflow lag > 5 minutes"
  conditions:
    - display_name: "Pipeline severely delayed"
      condition_threshold:
        filter: 'metric.type="custom.googleapis.com/f1/dataflow/lag_seconds"'
        comparison: COMPARISON_GT
        threshold_value: 300
        duration: 60s
  notification_channels:
    - slack_critical
  documentation:
    content: "Dataflow pipeline severely delayed. Check Dataflow job status and worker logs."
```

### Warning Alerts (Slack Only)

**4. Model Accuracy Degradation**
```yaml
alert_policy:
  display_name: "Warning: Model accuracy dropped > 5%"
  conditions:
    - display_name: "Podium accuracy < 65%"
      condition_threshold:
        filter: 'metric.type="custom.googleapis.com/f1/model/podium_accuracy"'
        comparison: COMPARISON_LT
        threshold_value: 0.65
        duration: 86400s  # 1 day
  notification_channels:
    - slack_warnings
  documentation:
    content: "Model performance degraded. Review recent races. Consider retraining."
```

**5. Cost Projection > $300**
```yaml
alert_policy:
  display_name: "Warning: Projected monthly cost > $300"
  conditions:
    - display_name: "Budget exceeded"
      condition_threshold:
        filter: 'metric.type="custom.googleapis.com/f1/cost/total_projected"'
        comparison: COMPARISON_GT
        threshold_value: 300
        duration: 3600s  # 1 hour
  notification_channels:
    - slack_warnings
  documentation:
    content: "Monthly cost projection exceeded budget. Review cost dashboard. Optimize queries/Dataflow."
```

### Info Alerts (Logging Only)

**6. Data Freshness > 48h**
```yaml
alert_policy:
  display_name: "Info: Data freshness > 48 hours"
  conditions:
    - display_name: "Stale data detected"
      condition_threshold:
        filter: 'metric.type="custom.googleapis.com/f1/data/freshness_hours"'
        comparison: COMPARISON_GT
        threshold_value: 48
        duration: 3600s
  notification_channels:
    - slack_info
  documentation:
    content: "Data hasn't been updated in 48h. Check ingestion pipeline."
```

## Incident Response Runbook

### Scenario 1: API Latency Spike (P99 > 800ms)

**Symptoms**:
- Alert: "Critical: API Latency P99 > 800ms"
- Dashboard shows sudden spike in P99 latency

**Investigation Steps**:
1. Check Cloud Run logs for errors or exceptions
2. Review recent deployments (last 2 hours)
3. Check Dataflow lag (may be causing feature extraction delay)
4. Review BigQuery query performance (slow queries)
5. Check Monte Carlo simulation time (may need optimization)

**Immediate Actions**:
- If deployment caused issue → Rollback to previous version
- If Monte Carlo slow → Reduce scenarios from 5K to 2K
- If BigQuery slow → Cancel long-running queries
- If Cloud Run overloaded → Manually scale up instances

**Resolution**:
- Confirm latency returns to <500ms P99
- Document root cause in incident log
- Create follow-up task if code changes needed

### Scenario 2: Model Accuracy Degradation

**Symptoms**:
- Alert: "Warning: Model accuracy dropped > 5%"
- Recent races show poor podium predictions

**Investigation Steps**:
1. Review recent race results (any anomalies?)
2. Check if regulation changes occurred
3. Validate input data quality (completeness, outliers)
4. Test models on historical validation set (check if drift)
5. Review feature distributions (any shifts?)

**Immediate Actions**:
- Run drift detection script
- Compare recent race features to training distribution
- If drift detected → Trigger model retraining
- If data quality issue → Fix data pipeline, re-ingest

**Resolution**:
- Retrain models with latest data
- Validate new model on holdout set
- Deploy new model if accuracy improves
- Document in progress.md

### Scenario 3: Cost Overrun

**Symptoms**:
- Alert: "Warning: Projected monthly cost > $300"
- Cost dashboard shows spike in specific service

**Investigation Steps**:
1. Identify which service caused spike (BigQuery, Dataflow, Cloud Run)
2. If BigQuery → Review most expensive queries (last 7 days)
3. If Dataflow → Check worker hours, auto-scaling behavior
4. If Cloud Run → Review request volume, instance count

**Immediate Actions**:
- If BigQuery → Optimize queries (add partition pruning, reduce SELECT *)
- If Dataflow → Scale down workers during non-race periods
- If Cloud Run → Reduce max instances if traffic lower than expected

**Resolution**:
- Confirm projected cost returns to <$250/month
- Implement cost optimizations
- Update budget alerts if justified

## Review Cadence

### Daily (Automated Email)

**To**: Engineering team
**Time**: 08:00 UTC

**Content**:
- Previous race: Accuracy metrics, recommendations quality
- System health: Uptime, error rate, latency (last 24h)
- Data freshness: Age of most recent data
- Cost: Daily spend, projected monthly
- Incidents: Any alerts triggered

### Weekly (Team Sync Meeting)

**Duration**: 30 minutes
**Attendees**: Full team

**Agenda**:
1. Model drift analysis (review accuracy trends)
2. Cost optimization opportunities
3. Incident postmortems (if any)
4. Upcoming race calendar
5. Planned deployments

### Monthly (Formal Report)

**To**: Stakeholders
**Format**: Written report + presentation

**Content**:
1. Accuracy summary (podium %, winner %, pit timing)
2. Operational summary (uptime %, avg latency, total cost)
3. Roadmap update (planned improvements, new features)
4. Competitive analysis (performance vs expectations)

---

**See Also**:
- CLAUDE.md: High-level monitoring overview
- docs/metrics.md: Detailed metric definitions
- docs/architecture.md: System components to monitor
