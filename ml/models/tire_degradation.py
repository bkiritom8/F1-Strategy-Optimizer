"""
Tire Degradation Model - Optimized (LightGBM + XGBoost Ensemble)
"""
import pandas as pd
import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import LabelEncoder
from lightgbm import LGBMRegressor
from xgboost import XGBRegressor
import joblib
import os

# Load data
df = pd.read_parquet('gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet')
print(f'Loaded: {len(df)} rows')

# Encode
le_driver = LabelEncoder()
df['driver_encoded'] = le_driver.fit_transform(df['Driver'].astype(str))

# Better target: per-lap baseline (captures track evolution)
df = df.sort_values(['season', 'round', 'LapNumber', 'Driver']).reset_index(drop=True)
df['lap_baseline'] = df.groupby(['season', 'round', 'LapNumber'])['LapTime'].transform('median')
df['tire_delta'] = df['LapTime'] - df['lap_baseline']

# Filter
df = df[df['is_pit_lap'] == 0]
df = df[df['is_sc_lap'] == 0]
df = df[df['tire_delta'].between(-5, 10)]
df = df[df['TyreLife'] >= 1]
df = df.dropna(subset=['tire_delta', 'TyreLife', 'mean_throttle', 'mean_brake'])

print(f'After filtering: {len(df)} rows')

# Interaction features
df['tyre_fuel_interaction'] = df['TyreLife'] * df['fuel_load_pct']
df['tyre_squared'] = df['TyreLife'] ** 2
df['tyre_cubed'] = df['TyreLife'] ** 3
df['lap_progress'] = df['LapNumber'] / df['total_laps']
df['tyre_per_stint'] = df['TyreLife'] / (df['Stint'] + 1)
df['throttle_brake_ratio'] = df['mean_throttle'] / (df['mean_brake'] + 1)
df['tyre_x_throttle'] = df['TyreLife'] * df['mean_throttle'] / 100
df['tyre_x_brake'] = df['TyreLife'] * df['mean_brake'] / 100
df['fuel_x_throttle'] = df['fuel_load_pct'] * df['mean_throttle']

# Rolling features (lagged - no leakage)
df['delta_roll3'] = df.groupby(['season', 'round', 'Driver'])['tire_delta'].transform(
    lambda x: x.rolling(3, min_periods=1).mean().shift(1)
).fillna(0)
df['delta_roll5'] = df.groupby(['season', 'round', 'Driver'])['tire_delta'].transform(
    lambda x: x.rolling(5, min_periods=1).mean().shift(1)
).fillna(0)

# Features
FEATURES = [
    'TyreLife', 'Stint', 'LapNumber',
    'compound_SOFT', 'compound_MEDIUM', 'compound_HARD',
    'compound_INTERMEDIATE', 'compound_WET',
    'fuel_load_pct', 'laps_remaining',
    'mean_throttle', 'std_throttle', 'mean_brake', 'std_brake',
    'driving_style',
    'position', 'gap_ahead',
    'tyre_fuel_interaction', 'tyre_squared', 'tyre_cubed',
    'lap_progress', 'tyre_per_stint',
    'throttle_brake_ratio', 'tyre_x_throttle', 'tyre_x_brake',
    'fuel_x_throttle',
    'delta_roll3', 'delta_roll5',
]
features = [f for f in FEATURES if f in df.columns]
print(f'Features: {len(features)}')

# Split
train = df[df['season'] <= 2021]
val = df[(df['season'] >= 2022) & (df['season'] <= 2023)]
test = df[df['season'] == 2024]
print(f'Train: {len(train)}, Val: {len(val)}, Test: {len(test)}')

X_train, y_train = train[features].fillna(0), train['tire_delta']
X_val, y_val = val[features].fillna(0), val['tire_delta']
X_test, y_test = test[features].fillna(0), test['tire_delta']

print(f'Target std - Train: {y_train.std():.3f}, Val: {y_val.std():.3f}, Test: {y_test.std():.3f}')

# Train LightGBM
print('\nTraining LightGBM...')
lgb = LGBMRegressor(
    n_estimators=2000,
    max_depth=10,
    num_leaves=63,
    learning_rate=0.006,
    subsample=0.7,
    colsample_bytree=0.6,
    min_child_samples=30,
    reg_alpha=0.5,
    reg_lambda=2.0,
    random_state=42,
    n_jobs=-1,
    verbose=-1
)
lgb.fit(X_train, y_train, eval_set=[(X_val, y_val)])

# Train XGBoost
print('Training XGBoost...')
xgb = XGBRegressor(
    n_estimators=1500,
    max_depth=8,
    learning_rate=0.008,
    subsample=0.7,
    colsample_bytree=0.6,
    min_child_weight=30,
    reg_alpha=0.5,
    reg_lambda=2.0,
    random_state=42,
    tree_method='hist',
    early_stopping_rounds=100,
    verbosity=0
)
xgb.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

# Find optimal ensemble weight
print('\nFinding optimal weight...')
best_mae = float('inf')
best_w = 0.5

for w in np.arange(0.1, 0.95, 0.05):
    pred = w * lgb.predict(X_val) + (1 - w) * xgb.predict(X_val)
    mae = mean_absolute_error(y_val, pred)
    if mae < best_mae:
        best_mae = mae
        best_w = round(w, 2)

print(f'Best weight: LGB={best_w}, XGB={1-best_w}')

# Final predictions
val_pred = best_w * lgb.predict(X_val) + (1 - best_w) * xgb.predict(X_val)
test_pred = best_w * lgb.predict(X_test) + (1 - best_w) * xgb.predict(X_test)

# Results
print('\n' + '='*50)
print('TIRE DEGRADATION RESULTS (OPTIMIZED)')
print('='*50)
print(f'Val  - MAE: {mean_absolute_error(y_val, val_pred):.3f}s, R2: {r2_score(y_val, val_pred):.3f}')
print(f'Test - MAE: {mean_absolute_error(y_test, test_pred):.3f}s, R2: {r2_score(y_test, test_pred):.3f}')

print('\nIndividual Models:')
print(f'  LGB  - Val MAE: {mean_absolute_error(y_val, lgb.predict(X_val)):.3f}, Test MAE: {mean_absolute_error(y_test, lgb.predict(X_test)):.3f}')
print(f'  XGB  - Val MAE: {mean_absolute_error(y_val, xgb.predict(X_val)):.3f}, Test MAE: {mean_absolute_error(y_test, xgb.predict(X_test)):.3f}')

print('\nTop 10 Features (LGB):')
for feat, imp in sorted(zip(features, lgb.feature_importances_), key=lambda x: -x[1])[:10]:
    print(f'  {feat}: {imp}')

# Save
os.makedirs('models', exist_ok=True)
joblib.dump({
    'lgb': lgb,
    'xgb': xgb,
    'weight': best_w,
    'features': features,
    'driver_encoder': le_driver
}, 'models/tire_degradation.pkl')
print('\nSaved: models/tire_degradation.pkl')