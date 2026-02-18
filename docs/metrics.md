# KPIs, Metrics, and Validation

**Last Updated**: 2026-02-14

## Overview

This document defines all key performance indicators (KPIs), success metrics, and validation criteria for the F1 Strategy Optimizer. Metrics are organized into 4 categories: Driver Profiles, Model Performance, Race Predictions, and Operations.

## Metric Summary Dashboard

```
┌─────────────────────────────────────────────────────────────────┐
│                    F1 STRATEGY OPTIMIZER METRICS                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Driver Profiles (3 metrics)                                    │
│  ├─ Aggression Correlation:     r > 0.7     [Target: 0.7]      │
│  ├─ Consistency Accuracy:       < 5% error  [Target: <5%]      │
│  └─ Pressure Response MAE:      < 50ms      [Target: <50ms]    │
│                                                                  │
│  Model Performance (4 metrics)                                  │
│  ├─ Tire Degradation MAE:       < 50ms      [Target: <50ms]    │
│  ├─ Fuel Consumption RMSE:      < 0.5kg/lap [Target: <0.5]     │
│  ├─ Brake Bias Accuracy:        ±1%         [Target: ±1%]      │
│  └─ Driving Style Accuracy:     ≥ 75%       [Target: ≥75%]     │
│                                                                  │
│  Race Predictions (4 metrics)                                   │
│  ├─ Podium Accuracy:            ≥ 70%       [Target: ≥70%]     │
│  ├─ Winner Accuracy:            ≥ 65%       [Target: ≥65%]     │
│  ├─ Finishing Order Corr:       > 0.75      [Target: >0.75]    │
│  └─ Pit Timing Accuracy:        ±2 laps     [Target: ±2]       │
│                                                                  │
│  Operations (4 metrics)                                         │
│  ├─ API Latency (P99):          < 500ms     [Target: <500ms]   │
│  ├─ End-to-End Latency:         < 5s        [Target: <5s]      │
│  ├─ System Uptime:              99.5%       [Target: 99.5%]    │
│  └─ Cost Per Prediction:        < $0.001    [Target: <$0.001]  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Driver Profile Validation Metrics

### 1. Aggression Score Correlation

**Definition**: Pearson correlation between extracted aggression score and actual mean throttle percentage from telemetry

**Formula**:
```python
r, p_value = pearsonr(
    profiles['aggression'] * 100,  # Scale 0-1 to 0-100
    telemetry.groupby('driver_id')['Throttle'].mean()
)
```

**Target**: r > 0.7

**Validation Method**:
1. Extract aggression scores for all drivers with telemetry (2018+)
2. Compute actual mean throttle % from FastF1 telemetry
3. Calculate Pearson correlation on test set (100+ drivers)
4. Assert correlation exceeds 0.7

**Interpretation**:
- r = 0.7-0.8: Good correlation, model captures aggression
- r < 0.7: Model needs refinement
- r > 0.9: Excellent, may be overfitting

### 2. Consistency Accuracy

**Definition**: Predicted standard deviation of lap times within ±5% of actual variance

**Formula**:
```python
actual_std = races_df.groupby('driver_id')['lap_time'].std()
predicted_std = 1 / (profiles['consistency'] + 1e-6)

error = abs(actual_std - predicted_std) / actual_std
accuracy = (error < 0.05).mean()
```

**Target**: >95% of drivers within ±5% error

**Validation Method**:
1. Calculate actual std_dev from historical lap times
2. Invert consistency score to get predicted std_dev
3. Compute percentage error per driver
4. Assert >95% of drivers have error <5%

### 3. Pressure Response MAE

**Definition**: Mean absolute error on lap time prediction when driver is within 1s of competitor

**Formula**:
```python
pressure_laps = df[df['gap_to_next'] < 1.0]
baseline_laps = df[df['gap_to_next'] > 3.0]

predicted_delta = profiles['pressure_response'] * baseline_mean
actual_delta = pressure_laps['lap_time'].mean() - baseline_laps['lap_time'].mean()

mae = abs(predicted_delta - actual_delta).mean()
```

**Target**: MAE < 50ms (0.05 seconds)

**Validation Method**:
1. Identify laps where driver is under pressure (gap <1s)
2. Compare to baseline (clear air) lap times
3. Calculate predicted vs actual lap time delta
4. Assert MAE <50ms

## Model Performance Metrics

### 1. Tire Degradation MAE

**Definition**: Mean absolute error on lap time prediction 10 laps ahead due to tire wear

**Formula**:
```python
y_true = test_df['lap_time_delta']  # Actual lap time vs lap 1
y_pred = model.predict(X_test)

mae = mean_absolute_error(y_true, y_pred)
```

**Target**: MAE < 50ms

**Success Criteria**:
- MAE < 50ms: [OK] Pass
- MAE 50-100ms: [WARNING] Warning (acceptable but monitor)
- MAE > 100ms: [FAIL] Fail (retrain required)

**Breakdown by Compound**:
```python
# Evaluate separately for each tire compound
for compound in ['Soft', 'Medium', 'Hard']:
    compound_df = test_df[test_df['tire_compound'] == compound]
    mae_compound = mean_absolute_error(compound_df['actual'], compound_df['predicted'])
    print(f"{compound}: MAE = {mae_compound:.2f}ms")
```

**Expected**: Soft tires degrade faster (higher MAE acceptable)

### 2. Fuel Consumption RMSE

**Definition**: Root mean square error on fuel burn prediction (kg/lap)

**Formula**:
```python
y_true = test_df['fuel_consumed']  # Actual fuel per lap
y_pred = model.predict(X_test)

rmse = np.sqrt(mean_squared_error(y_true, y_pred))
```

**Target**: RMSE < 0.5 kg/lap

**Validation**:
- Test on 50+ races with known fuel data
- Validate across different circuits (Monaco vs Spa)
- Check consistency across eras (V8 vs Hybrid)

**Alert Trigger**:
- If RMSE > 0.7 kg/lap on new races → Model drift detected

### 3. Brake Bias Accuracy

**Definition**: Recommended brake bias within ±1% of actual telemetry

**Formula**:
```python
y_true = test_df['brake_bias_front']  # Actual (50-65%)
y_pred = model.predict(X_test)

error = abs(y_true - y_pred)
accuracy = (error < 1.0).mean()  # % within ±1%
```

**Target**: ≥95% of predictions within ±1%

**Validation**:
```python
# Calculate distribution of errors
mae = error.mean()
within_1pct = (error < 1.0).mean()
within_2pct = (error < 2.0).mean()

print(f"MAE: {mae:.2f}%")
print(f"Within ±1%: {within_1pct*100:.1f}%")
print(f"Within ±2%: {within_2pct*100:.1f}%")
```

**Expected**:
- 95%+ within ±1%
- 99%+ within ±2%

### 4. Driving Style Classifier Accuracy

**Definition**: Percentage of laps where predicted mode (PUSH/BALANCED/CONSERVE) matches actual behavior

**Formula**:
```python
y_true = test_df['actual_mode']  # Derived from aggressive_score
y_pred = model.predict(X_test)

accuracy = accuracy_score(y_true, y_pred)
```

**Target**: ≥75% accuracy

**Confusion Matrix**:
```python
from sklearn.metrics import confusion_matrix, classification_report

cm = confusion_matrix(y_true, y_pred, labels=['CONSERVE', 'BALANCED', 'PUSH'])
report = classification_report(y_true, y_pred)

print(report)
```

**Expected**:
```
              precision  recall  f1-score  support
CONSERVE         0.72     0.68      0.70      500
BALANCED         0.78     0.82      0.80     1200
PUSH             0.76     0.74      0.75      800
```

**Class Imbalance**: Use class_weight='balanced' in training

## Race Outcome Prediction Metrics

### 1. Podium Prediction Accuracy

**Definition**: Percentage of races where simulated top-3 includes actual top-3 finishers

**Formula**:
```python
def podium_accuracy(predicted_results, actual_results):
    """
    Calculate podium prediction accuracy.

    Args:
        predicted_results: List of simulated finishing positions
        actual_results: List of actual finishing positions

    Returns:
        Accuracy (0-1)
    """

    predicted_podium = set(predicted_results[:3])
    actual_podium = set(actual_results[:3])

    overlap = len(predicted_podium & actual_podium)

    # Full match = 100%, 2/3 match = 66%, etc.
    return overlap / 3

# Aggregate across all test races
accuracies = [podium_accuracy(pred, actual) for pred, actual in zip(predictions, actuals)]
overall_accuracy = np.mean(accuracies)
```

**Target**: ≥70% average (≥2.1 out of 3 correct per race)

**Validation**:
- Test on 20+ unseen races (2023 Q3-Q4 + 2024)
- Stratify by circuit type (street vs permanent)
- Account for random events (crashes, safety cars)

**Interpretation**:
- 70-80%: Good performance
- 60-70%: Acceptable (F1 has high variability)
- <60%: Poor (worse than expert predictions)

### 2. Winner Prediction Accuracy

**Definition**: Percentage of races where predicted winner matches actual winner

**Formula**:
```python
correct_winners = sum(pred[0] == actual[0] for pred, actual in zip(predictions, actuals))
accuracy = correct_winners / len(predictions)
```

**Target**: ≥65%

**Baseline**: Random guess = 5% (1 in 20 drivers)

**Validation**:
```python
# Log predictions and actuals
results = []
for race in test_races:
    predicted_winner = simulate_race(race)['finishing_positions'][0]
    actual_winner = race['actual_results'][0]

    correct = (predicted_winner == actual_winner)
    results.append({
        'race_id': race['race_id'],
        'predicted': predicted_winner,
        'actual': actual_winner,
        'correct': correct
    })

accuracy = sum(r['correct'] for r in results) / len(results)
```

**Breakdown by Circuit**:
- High-overtaking circuits (Monza, Spa): Harder to predict
- Low-overtaking circuits (Monaco, Hungary): Easier to predict

### 3. Finishing Order Correlation

**Definition**: Spearman rank correlation between simulated and actual finishing order

**Formula**:
```python
from scipy.stats import spearmanr

rho, p_value = spearmanr(predicted_positions, actual_positions)
```

**Target**: Spearman ρ > 0.75

**Interpretation**:
- ρ = 1.0: Perfect rank correlation
- ρ = 0.75: Strong correlation
- ρ = 0.5: Moderate correlation
- ρ = 0: No correlation

**Validation**:
```python
correlations = []

for race in test_races:
    predicted = simulate_race(race)['finishing_positions']
    actual = race['actual_positions']

    rho, _ = spearmanr(predicted, actual)
    correlations.append(rho)

average_correlation = np.mean(correlations)
print(f"Average Spearman correlation: {average_correlation:.3f}")
```

### 4. Pit Timing Accuracy

**Definition**: Recommended pit lap within ±2 laps of actual pit lap

**Formula**:
```python
recommended_pit_lap = recommendation['pit_strategy']['recommended_lap']
actual_pit_lap = race['actual_pit_lap']

error = abs(recommended_pit_lap - actual_pit_lap)
accuracy = (error <= 2)
```

**Target**: ≥70% of pit stops within ±2 laps

**Validation**:
```python
errors = []

for race in test_races:
    for driver in race['drivers']:
        recommended = get_recommendation(driver)['pit_lap']
        actual = driver['actual_pit_lap']

        error = abs(recommended - actual)
        errors.append(error)

within_2_laps = sum(e <= 2 for e in errors) / len(errors)
print(f"Pit timing accuracy: {within_2_laps*100:.1f}%")
```

## Operational Metrics

### 1. API Latency (P99)

**Definition**: 99th percentile response time for /recommend endpoint

**Measurement**: Server-side timing (request received to response sent)

**Target**: P99 < 500ms

**Implementation**:
```python
import time
from fastapi import Request

@app.middleware("http")
async def add_latency_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    latency = (time.time() - start_time) * 1000  # ms

    response.headers["X-Latency"] = str(latency)

    # Log to Cloud Monitoring
    log_metric("api_latency", latency)

    return response
```

**Monitoring**:
- P50, P95, P99 tracked in Cloud Monitoring
- Alert if P99 > 600ms for 5 minutes
- Auto-rollback if P99 > 800ms

**Breakdown**:
```
Total P99 Latency: 450ms
├─ Feature extraction: 50ms
├─ Model inference (4 models): 150ms
├─ Monte Carlo simulation: 200ms
└─ Response formatting: 50ms
```

### 2. End-to-End Latency

**Definition**: Time from telemetry ingestion (Pub/Sub) to dashboard update

**Measurement**: Timestamp telemetry message, compare to dashboard display time

**Target**: <5 seconds

**Pipeline Breakdown**:
```
Telemetry arrives (Pub/Sub) → t=0
├─ Dataflow processing: 2s
├─ BigQuery write: 1s
├─ API call: 0.5s
└─ Dashboard render: 0.5s
Total: 4s
```

**Alert**: If >10 seconds consistently → investigate Dataflow lag

### 3. System Uptime

**Definition**: Percentage of time API is available and responding to health checks

**Measurement**: Health check every 30 seconds

**Target**: 99.5% during race weekends

**Calculation**:
```python
uptime = (successful_health_checks / total_health_checks) * 100
```

**SLA**:
- Race weekends: 99.5% (max 2.5 minutes downtime per race)
- Non-race periods: 99% (more lenient)

**Downtime Categories**:
- Planned maintenance: Excluded from SLA
- Unplanned outages: Counted against SLA

### 4. Cost Per Prediction

**Definition**: Total GCP cost divided by number of API calls

**Formula**:
```python
monthly_cost = bigquery_cost + cloud_run_cost + dataflow_cost + vertex_ai_cost
api_calls = total_api_requests

cost_per_prediction = monthly_cost / api_calls
```

**Target**: <$0.001 per prediction

**Optimization**:
- Cache common queries (driver profiles, circuit data)
- Batch predictions where possible
- Use BigQuery partition pruning
- Scale down Dataflow during non-race periods

**Cost Breakdown**:
```
Monthly Budget: $200
API Calls: 100,000

BigQuery: $5 (2.5%)
Cloud Run: $20 (10%)
Dataflow: $150 (75%)
Vertex AI: $20 (10%)
Other: $5 (2.5%)

Cost per prediction: $0.002 (needs optimization)
```

## Validation Cadence

| Metric Type | Frequency | Trigger |
|-------------|-----------|---------|
| Driver Profiles | Once (initial), then quarterly | New driver or major telemetry update |
| Model Performance | After each race, weekly aggregation | Model retraining |
| Race Predictions | After each race | Ground truth available |
| Operational | Continuous (real-time) | Every API call |

## Acceptance Criteria Summary

**Project is considered successful when**:

[OK] All driver profile metrics meet targets (r >0.7, <5% error, <50ms MAE)
[OK] All 4 ML models meet accuracy targets
[OK] Podium accuracy ≥70% and winner accuracy ≥65% on test set
[OK] API P99 latency <500ms with 99.5% uptime
[OK] System operates within $250/month budget
[OK] All monitoring and alerting configured
[OK] Code coverage ≥80% with passing integration tests

---

**See Also**:
- CLAUDE.md: Success criteria overview
- docs/models.md: Model training and validation
- docs/monitoring.md: Operational monitoring setup
