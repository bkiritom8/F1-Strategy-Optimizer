# ML Models - Architecture, Training, and Validation

**Last Updated**: 2026-02-18

## Overview

The F1 Strategy Optimizer employs 4 specialized ML models integrated into a unified optimization engine. Each model targets a specific prediction task with domain-appropriate architectures and validation strategies.

## Model Architecture Summary

| Model | Algorithm | Target | Input Features | Output | Target Accuracy |
|-------|-----------|--------|----------------|--------|-----------------|
| **Tire Degradation** | XGBoost | Lap time delta | Tire age, compound, track, fuel, driver profile | Lap time +X ms | MAE <50ms |
| **Fuel Consumption** | LSTM | Fuel burn rate | Throttle pattern, lap, circuit, driver aggression | kg/lap | RMSE <0.5 kg/lap |
| **Brake Bias** | Linear Regression | Optimal brake bias | Tire age, fuel load, track, tire temp, driver | Bias % (front) | ±1% error |
| **Driving Style** | Decision Tree | Driving mode | Gap to leader, lap, fuel, position, driver | PUSH/BALANCED/CONSERVE | ≥75% accuracy |

## Driver Profile Extraction

**Purpose**: Quantify individual driver behavioral patterns to enable personalized recommendations.

### Methodology

Extract 4 behavioral dimensions from 74 years of historical data:

1. **Aggression Score**: Mean throttle percentage and overtake frequency
2. **Consistency**: Standard deviation of lap times (lower = more consistent)
3. **Pressure Response**: Lap time delta when within 1s of competitor
4. **Tire Management**: Degradation rate compared to teammates

### Implementation

```python
# drivers/extract_profiles.py

def extract_driver_profile(driver_id, races_df, telemetry_df):
    """
    Extract behavioral profile for a single driver.

    Args:
        driver_id: Three-letter driver code (e.g., 'VER')
        races_df: Historical race results
        telemetry_df: Telemetry data (2018+)

    Returns:
        dict: Driver profile with aggression, consistency, pressure, tire_mgmt
    """

    # 1. Aggression Score
    if driver_id in telemetry_df['driver_id'].values:
        mean_throttle = telemetry_df[telemetry_df['driver_id'] == driver_id]['Throttle'].mean()
        overtake_freq = calculate_overtake_frequency(races_df, driver_id)
        aggression = (mean_throttle / 100) * 0.7 + overtake_freq * 0.3  # Weighted
    else:
        # Pre-2018: Use race aggression proxies (overtakes, incidents)
        aggression = calculate_historical_aggression(races_df, driver_id)

    # 2. Consistency
    lap_times = races_df[races_df['driver_id'] == driver_id]['lap_time']
    consistency = 1 / (lap_times.std() + 1)  # Inverse std (higher = more consistent)

    # 3. Pressure Response
    pressure_laps = races_df[
        (races_df['driver_id'] == driver_id) &
        (races_df['gap_to_next'] < 1.0)  # Within 1s of competitor
    ]
    baseline_laps = races_df[
        (races_df['driver_id'] == driver_id) &
        (races_df['gap_to_next'] > 3.0)  # Clear air
    ]
    pressure_delta = pressure_laps['lap_time'].mean() - baseline_laps['lap_time'].mean()
    pressure_response = max(0, 1 - (pressure_delta / 1000))  # Normalize to 0-1

    # 4. Tire Management
    teammate_comparison = calculate_tire_deg_vs_teammate(races_df, driver_id)
    tire_mgmt = teammate_comparison  # Higher = better tire management

    return {
        'driver_id': driver_id,
        'aggression': aggression,
        'consistency': consistency,
        'pressure_response': pressure_response,
        'tire_management': tire_mgmt
    }

def extract_all_profiles(races_df, telemetry_df):
    """Extract profiles for all 200+ drivers."""
    drivers = races_df['driver_id'].unique()
    profiles = [extract_driver_profile(d, races_df, telemetry_df) for d in drivers]

    # Save to JSON
    with open('drivers/profiles.json', 'w') as f:
        json.dump(profiles, f, indent=2)

    return profiles
```

### Output Format

```json
{
  "driver_id": "VER",
  "name": "Max Verstappen",
  "aggression": 0.87,
  "consistency": 0.92,
  "pressure_response": 0.89,
  "tire_management": 0.78,
  "career_races": 180,
  "data_quality": 0.95
}
```

### Validation

**Correlation Test**: Compare extracted aggression score to actual mean throttle % from telemetry

```python
# Expected: Pearson correlation r > 0.7
from scipy.stats import pearsonr

actual_throttle = telemetry_df.groupby('driver_id')['Throttle'].mean()
predicted_aggression = profiles_df['aggression']

r, p_value = pearsonr(actual_throttle, predicted_aggression * 100)
assert r > 0.7, f"Aggression correlation {r} below target 0.7"
```

**Consistency Accuracy**: Predicted std_dev within ±5% of actual variance

```python
actual_std = races_df.groupby('driver_id')['lap_time'].std()
predicted_consistency = profiles_df['consistency']

# Inverse consistency to get std_dev estimate
predicted_std = 1 / (predicted_consistency + 1e-6)

error = abs(actual_std - predicted_std) / actual_std
assert (error < 0.05).mean() > 0.95, "Consistency error >5% for too many drivers"
```

## Model 1: Tire Degradation (XGBoost)

### Problem Statement

Predict lap time increase due to tire wear as tires age during a stint.

**Input**: Tire age (laps), compound, track characteristics, fuel load, driver profile
**Output**: Lap time delta in milliseconds (e.g., +450ms at lap 15 vs lap 1)

### Architecture

**Algorithm**: XGBoost Regressor

**Hyperparameters**:
```python
params = {
    'max_depth': 6,
    'learning_rate': 0.05,
    'n_estimators': 500,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'objective': 'reg:squarederror',
    'eval_metric': 'mae',
    'tree_method': 'hist',  # Fast histogram-based method
    'early_stopping_rounds': 50
}
```

### Features (15 total)

**Tire Features** (4):
- `tire_age`: Laps since pit stop (1-40)
- `tire_compound`: One-hot encoded (Soft/Medium/Hard)
- `tire_temp_front`: Front tire temperature (°C)
- `tire_temp_rear`: Rear tire temperature (°C)

**Track Features** (3):
- `circuit_id`: Categorical encoding
- `track_temp`: Track surface temperature (°C)
- `track_abrasiveness`: Scale 1-10 (Monaco=2, Silverstone=8)

**Car Features** (3):
- `fuel_load`: Estimated fuel remaining (kg)
- `downforce_level`: Circuit-specific (Low/Medium/High)
- `car_damage`: Boolean (any damage indicators)

**Driver Features** (3):
- `driver_aggression`: From driver profile (0-1)
- `driver_tire_mgmt`: From driver profile (0-1)
- `driver_id`: Categorical encoding

**Context Features** (2):
- `lap_number`: Current lap (1-70)
- `stint_number`: Current stint (1-5)

### Training Procedure

```python
# models/tire_degradation.py

import xgboost as xgb
from sklearn.model_selection import train_test_split

def train_tire_degradation_model(train_df, val_df):
    """
    Train XGBoost tire degradation model.

    Args:
        train_df: Training data (1950-2022)
        val_df: Validation data (2023 Q1-Q2)

    Returns:
        Trained XGBoost model
    """

    # Feature engineering
    features = [
        'tire_age', 'tire_compound', 'tire_temp_front', 'tire_temp_rear',
        'circuit_id', 'track_temp', 'track_abrasiveness',
        'fuel_load', 'downforce_level', 'car_damage',
        'driver_aggression', 'driver_tire_mgmt', 'driver_id',
        'lap_number', 'stint_number'
    ]

    target = 'lap_time_delta'  # Delta vs lap 1 of stint

    X_train = train_df[features]
    y_train = train_df[target]

    X_val = val_df[features]
    y_val = val_df[target]

    # Encode categorical features
    X_train_encoded = pd.get_dummies(X_train, columns=['tire_compound', 'circuit_id', 'driver_id'])
    X_val_encoded = pd.get_dummies(X_val, columns=['tire_compound', 'circuit_id', 'driver_id'])

    # Align columns (in case val has unseen categories)
    X_train_encoded, X_val_encoded = X_train_encoded.align(X_val_encoded, join='left', axis=1, fill_value=0)

    # Train XGBoost
    dtrain = xgb.DMatrix(X_train_encoded, label=y_train)
    dval = xgb.DMatrix(X_val_encoded, label=y_val)

    params = {
        'max_depth': 6,
        'learning_rate': 0.05,
        'n_estimators': 500,
        'subsample': 0.8,
        'colsample_bytree': 0.8,
        'objective': 'reg:squarederror',
        'eval_metric': 'mae'
    }

    model = xgb.train(
        params,
        dtrain,
        num_boost_round=500,
        evals=[(dtrain, 'train'), (dval, 'val')],
        early_stopping_rounds=50,
        verbose_eval=10
    )

    # Save model
    model.save_model('models/artifacts/tire_degradation_v1.json')

    return model
```

### Validation Metrics

**Target**: MAE < 50ms on test set

```python
# Evaluate on test set (2023 Q3-Q4 + 2024)
y_pred = model.predict(X_test)
mae = mean_absolute_error(y_test, y_pred)
rmse = mean_squared_error(y_test, y_pred, squared=False)

print(f"MAE: {mae:.2f} ms (target: <50ms)")
print(f"RMSE: {rmse:.2f} ms")
```

**Feature Importance**: Understand which factors drive tire degradation

```python
importance = model.get_score(importance_type='gain')
# Expected top features: tire_age, tire_compound, track_abrasiveness
```

## Model 2: Fuel Consumption (LSTM)

### Problem Statement

Predict fuel burn rate (kg/lap) based on driving style and circuit characteristics.

**Input**: Throttle pattern (time-series), lap number, circuit, driver aggression
**Output**: Fuel consumption in kg/lap

### Architecture

**Algorithm**: LSTM (Long Short-Term Memory) neural network

**Architecture Diagram**:
```
Input (10 timesteps × 5 features)
    ↓
LSTM Layer (64 units, return_sequences=True)
    ↓
Dropout (0.2)
    ↓
LSTM Layer (32 units)
    ↓
Dropout (0.2)
    ↓
Dense (16 units, ReLU)
    ↓
Dense (1 unit, Linear) → Fuel consumption (kg/lap)
```

**Implementation**:
```python
# models/fuel_consumption.py

import tensorflow as tf
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout

def build_fuel_model(sequence_length=10, n_features=5):
    """
    Build LSTM model for fuel consumption prediction.

    Args:
        sequence_length: Number of timesteps (10 laps lookback)
        n_features: Number of input features per timestep

    Returns:
        Compiled Keras model
    """

    model = Sequential([
        LSTM(64, return_sequences=True, input_shape=(sequence_length, n_features)),
        Dropout(0.2),
        LSTM(32, return_sequences=False),
        Dropout(0.2),
        Dense(16, activation='relu'),
        Dense(1, activation='linear')  # Output: kg/lap
    ])

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss='mse',
        metrics=['mae', 'mse']
    )

    return model

def prepare_sequences(df, sequence_length=10):
    """
    Create time-series sequences for LSTM training.

    Args:
        df: DataFrame with lap-by-lap data
        sequence_length: Number of laps to look back

    Returns:
        X: (n_samples, sequence_length, n_features)
        y: (n_samples,) fuel consumption
    """

    features = ['throttle_mean', 'speed_max', 'brake_count', 'drs_usage', 'circuit_fuel_factor']

    X, y = [], []

    for race_id in df['race_id'].unique():
        race_df = df[df['race_id'] == race_id].sort_values('lap')

        for i in range(sequence_length, len(race_df)):
            X.append(race_df.iloc[i-sequence_length:i][features].values)
            y.append(race_df.iloc[i]['fuel_consumed'])

    return np.array(X), np.array(y)

def train_fuel_model(train_df, val_df):
    """Train LSTM fuel consumption model."""

    X_train, y_train = prepare_sequences(train_df, sequence_length=10)
    X_val, y_val = prepare_sequences(val_df, sequence_length=10)

    model = build_fuel_model(sequence_length=10, n_features=5)

    # Callbacks
    callbacks = [
        tf.keras.callbacks.EarlyStopping(patience=10, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(factor=0.5, patience=5),
        tf.keras.callbacks.ModelCheckpoint('models/artifacts/fuel_consumption_best.h5', save_best_only=True)
    ]

    # Train
    history = model.fit(
        X_train, y_train,
        validation_data=(X_val, y_val),
        epochs=100,
        batch_size=64,
        callbacks=callbacks,
        verbose=1
    )

    # Save final model
    model.save('models/artifacts/fuel_consumption_v1.h5')

    return model, history
```

### Validation Metrics

**Target**: RMSE < 0.5 kg/lap

```python
y_pred = model.predict(X_test)
rmse = np.sqrt(mean_squared_error(y_test, y_pred))
mae = mean_absolute_error(y_test, y_pred)

print(f"RMSE: {rmse:.3f} kg/lap (target: <0.5)")
print(f"MAE: {mae:.3f} kg/lap")
```

## Model 3: Brake Bias Optimization (Linear Regression)

### Problem Statement

Recommend optimal brake bias percentage (front vs rear) based on tire age, fuel load, and track conditions.

**Input**: Tire age, fuel load, track characteristics, tire temperatures, driver profile
**Output**: Brake bias percentage (e.g., 58% front, 42% rear)

### Architecture

**Algorithm**: scikit-learn Linear Regression (simple, interpretable, fast)

**Justification**: Brake bias has strong linear relationship with fuel load and tire age

### Features (8 total)

```python
features = [
    'tire_age_front',       # Front tire age (laps)
    'tire_age_rear',        # Rear tire age (laps)
    'fuel_load',            # Current fuel (kg)
    'tire_temp_front',      # Front tire temperature (°C)
    'tire_temp_rear',       # Rear tire temperature (°C)
    'track_braking_zones',  # Number of heavy braking zones
    'driver_brake_pref',    # Driver preference (from profile)
    'downforce_level'       # Circuit downforce (Low/Medium/High)
]
```

### Training Procedure

```python
# models/brake_bias.py

from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

def train_brake_bias_model(train_df, val_df):
    """
    Train linear regression brake bias model.

    Args:
        train_df: Training data with telemetry
        val_df: Validation data

    Returns:
        Trained model and scaler
    """

    features = [
        'tire_age_front', 'tire_age_rear', 'fuel_load',
        'tire_temp_front', 'tire_temp_rear', 'track_braking_zones',
        'driver_brake_pref', 'downforce_level'
    ]

    target = 'brake_bias_front'  # Percentage (50-65%)

    X_train = train_df[features]
    y_train = train_df[target]

    X_val = val_df[features]
    y_val = val_df[target]

    # Standardize features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)

    # Train linear regression
    model = LinearRegression()
    model.fit(X_train_scaled, y_train)

    # Save model and scaler
    joblib.dump(model, 'models/artifacts/brake_bias_v1.pkl')
    joblib.dump(scaler, 'models/artifacts/brake_bias_scaler.pkl')

    return model, scaler
```

### Validation Metrics

**Target**: ±1% error

```python
y_pred = model.predict(X_test_scaled)
error = np.abs(y_test - y_pred)

mae = error.mean()
within_1pct = (error < 1.0).mean()

print(f"MAE: {mae:.2f}% (target: <1%)")
print(f"Within ±1%: {within_1pct*100:.1f}% of predictions")
```

## Model 4: Driving Style Classifier (Decision Tree)

### Problem Statement

Classify recommended driving mode (PUSH/BALANCED/CONSERVE) based on race situation.

**Input**: Gap to leader, lap number, fuel remaining, position, driver profile
**Output**: One of 3 classes (PUSH/BALANCED/CONSERVE)

### Architecture

**Algorithm**: Decision Tree Classifier

**Justification**: Interpretable rules, fast inference, handles categorical features well

### Features (10 total)

```python
features = [
    'gap_to_leader',        # Seconds behind leader
    'gap_to_next',          # Seconds to car ahead
    'lap_number',           # Current lap
    'laps_remaining',       # Laps to finish
    'fuel_remaining',       # Fuel (kg)
    'position',             # Current position (1-20)
    'tire_age',             # Current tire age
    'driver_aggression',    # Driver profile
    'points_delta',         # Points gap in championship
    'safety_car_active'     # Boolean
]
```

### Training Procedure

```python
# models/driving_style.py

from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import classification_report

def train_driving_style_model(train_df, val_df):
    """
    Train decision tree driving style classifier.

    Args:
        train_df: Training data with labeled driving modes
        val_df: Validation data

    Returns:
        Trained decision tree model
    """

    features = [
        'gap_to_leader', 'gap_to_next', 'lap_number', 'laps_remaining',
        'fuel_remaining', 'position', 'tire_age', 'driver_aggression',
        'points_delta', 'safety_car_active'
    ]

    # Create labels from telemetry
    # aggressive_score from throttle patterns
    train_df['mode'] = pd.cut(
        train_df['aggressive_score'],
        bins=[0, 0.4, 0.7, 1.0],
        labels=['CONSERVE', 'BALANCED', 'PUSH']
    )

    X_train = train_df[features]
    y_train = train_df['mode']

    X_val = val_df[features]
    y_val = val_df['mode']

    # Train decision tree
    model = DecisionTreeClassifier(
        max_depth=8,
        min_samples_split=20,
        min_samples_leaf=10,
        class_weight='balanced',  # Handle class imbalance
        random_state=42
    )

    model.fit(X_train, y_train)

    # Save model
    joblib.dump(model, 'models/artifacts/driving_style_v1.pkl')

    return model
```

### Validation Metrics

**Target**: ≥75% accuracy

```python
y_pred = model.predict(X_test)
accuracy = accuracy_score(y_test, y_pred)
report = classification_report(y_test, y_pred, target_names=['CONSERVE', 'BALANCED', 'PUSH'])

print(f"Accuracy: {accuracy*100:.1f}% (target: ≥75%)")
print(report)
```

## Monte Carlo Race Simulator

### Purpose

Simulate race with different pit strategies to identify optimal decisions.

### Implementation

```python
# simulation/race_simulator.py

def simulate_race(
    race_context,
    pit_strategy,
    driver_profile,
    models
):
    """
    Simulate race with given pit strategy.

    Args:
        race_context: Current race state (lap, position, fuel, tires)
        pit_strategy: Proposed strategy (pit laps, compounds)
        driver_profile: Driver behavioral profile
        models: Dict of trained models

    Returns:
        Simulated finishing position, lap times, fuel consumption
    """

    total_laps = race_context['total_laps']
    current_lap = race_context['current_lap']

    lap_times = []
    fuel_remaining = race_context['fuel_remaining']
    tire_age = race_context['tire_age']
    tire_compound = race_context['tire_compound']

    for lap in range(current_lap, total_laps + 1):
        # Check if pit lap
        if lap in pit_strategy['pit_laps']:
            lap_times.append(race_context['pit_loss_time'])  # e.g., +25 seconds
            tire_age = 0
            tire_compound = pit_strategy['compounds'][pit_strategy['pit_laps'].index(lap)]
        else:
            # Predict lap time with tire degradation
            tire_deg = models['tire_degradation'].predict({
                'tire_age': tire_age,
                'tire_compound': tire_compound,
                'fuel_load': fuel_remaining,
                'driver_aggression': driver_profile['aggression'],
                # ... other features
            })

            base_lap_time = race_context['base_lap_time']
            lap_time = base_lap_time + tire_deg
            lap_times.append(lap_time)

            # Update fuel
            fuel_burn = models['fuel_consumption'].predict({
                'throttle_mean': driver_profile['aggression'] * 95,
                # ... other features
            })
            fuel_remaining -= fuel_burn

            tire_age += 1

    # Calculate finishing position (simplified: compare total time)
    total_time = sum(lap_times)

    return {
        'total_time': total_time,
        'lap_times': lap_times,
        'fuel_remaining': fuel_remaining,
        'finishing_position': estimate_position(total_time, race_context)
    }

def monte_carlo_optimization(race_context, driver_profile, models, n_scenarios=10000):
    """
    Run Monte Carlo simulation to find optimal pit strategy.

    Args:
        race_context: Current race state
        driver_profile: Driver profile
        models: Trained models
        n_scenarios: Number of scenarios to simulate

    Returns:
        Top 3 pit strategies ranked by win probability
    """

    # Generate candidate pit strategies
    strategies = generate_pit_strategies(race_context)  # ~500-1000 candidates

    results = []

    for strategy in strategies:
        # Run multiple simulations with noise (safety cars, variability)
        outcomes = []
        for _ in range(20):  # 20 runs per strategy
            outcome = simulate_race(
                race_context,
                strategy,
                driver_profile,
                models
            )
            outcomes.append(outcome)

        # Aggregate results
        avg_position = np.mean([o['finishing_position'] for o in outcomes])
        win_prob = np.mean([o['finishing_position'] == 1 for o in outcomes])
        podium_prob = np.mean([o['finishing_position'] <= 3 for o in outcomes])

        results.append({
            'strategy': strategy,
            'avg_position': avg_position,
            'win_prob': win_prob,
            'podium_prob': podium_prob
        })

    # Rank by win probability
    results_sorted = sorted(results, key=lambda x: x['win_prob'], reverse=True)

    return results_sorted[:3]  # Top 3 strategies
```

## Model Integration Pipeline

```python
# models/train.py

def train_all_models(train_df, val_df):
    """
    Unified training pipeline for all 4 models.

    Returns:
        Dict of trained models
    """

    print("Training Tire Degradation model...")
    tire_model = train_tire_degradation_model(train_df, val_df)

    print("Training Fuel Consumption model...")
    fuel_model = train_fuel_model(train_df, val_df)

    print("Training Brake Bias model...")
    brake_model, brake_scaler = train_brake_bias_model(train_df, val_df)

    print("Training Driving Style model...")
    style_model = train_driving_style_model(train_df, val_df)

    return {
        'tire_degradation': tire_model,
        'fuel_consumption': fuel_model,
        'brake_bias': brake_model,
        'brake_bias_scaler': brake_scaler,
        'driving_style': style_model
    }
```

## Model Versioning and Registry

**Vertex AI Model Registry**:
```python
# Register models in Vertex AI
from google.cloud import aiplatform

aiplatform.init(project='f1optimizer', location='us-central1')

model = aiplatform.Model.upload(
    display_name='tire_degradation_v1',
    artifact_uri='gs://f1optimizer-models/tire_degradation/',
    serving_container_image_uri='us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api:latest'
)
```

**Local Versioning**:
```bash
models/artifacts/
├── tire_degradation_v1.json
├── tire_degradation_v2.json  # After retraining
├── fuel_consumption_v1.h5
├── brake_bias_v1.pkl
├── driving_style_v1.pkl
└── metadata.json  # Training dates, metrics, hyperparameters
```

## Model Monitoring and Retraining

**Weekly Retraining**:
```bash
# Cron job: Every Monday 02:00 UTC
0 2 * * 1 /path/to/models/retrain.sh
```

**Drift Detection**:
```python
# Compare model performance on latest races vs validation set
if current_mae > validation_mae * 1.1:
    trigger_alert("Model drift detected: MAE increased by >10%")
    trigger_retraining()
```

---

**See Also**:
- CLAUDE.md: High-level architecture
- docs/data.md: Feature engineering details
- docs/metrics.md: Model validation metrics
- docs/architecture.md: Model serving infrastructure
