"""
Tire Degradation Model - LGB+XGB Ensemble
Target: tyre_delta | Val MAE=0.294s R2=0.819 | Test MAE=0.285s R2=0.850
"""
import pandas as pd
import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import LabelEncoder
from lightgbm import LGBMRegressor
from xgboost import XGBRegressor
import joblib
import os
from google.cloud import aiplatform

# Vertex AI Experiment Tracking
aiplatform.init(project='f1optimizer', location='us-central1', experiment='f1-strategy-models')

# Load pre-filtered data
df = pd.read_parquet('gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet')
print(f'Loaded: {len(df)} rows')
print(f'Seasons: {sorted(df["season"].unique())}')
print(f'tyre_delta stats: mean={df["tyre_delta"].mean():.3f}, std={df["tyre_delta"].std():.3f}')

# Encode driver
le_driver = LabelEncoder()
df['driver_encoded'] = le_driver.fit_transform(df['Driver'].astype(str))

# Sort for rolling features
df = df.sort_values(['season', 'round', 'Driver', 'LapNumber']).reset_index(drop=True)

# Core interaction features
df['tyre_fuel_interaction'] = df['TyreLife'] * df['fuel_load_pct']
df['tyre_squared']          = df['TyreLife'] ** 2
df['tyre_cubed']            = df['TyreLife'] ** 3
df['lap_progress']          = df['LapNumber'] / df['total_laps']
df['tyre_per_stint']        = df['TyreLife'] / (df['Stint'] + 1)
df['throttle_brake_ratio']  = df['mean_throttle'] / (df['mean_brake'] + 1)
df['tyre_x_throttle']       = df['TyreLife'] * df['mean_throttle'] / 100
df['tyre_x_brake']          = df['TyreLife'] * df['mean_brake'] / 100
df['fuel_x_throttle']       = df['fuel_load_pct'] * df['mean_throttle']

# Compound-age physics interactions
df['compound_age_soft']   = df['compound_SOFT']   * df['TyreLife']
df['compound_age_medium'] = df['compound_MEDIUM'] * df['TyreLife']
df['compound_age_hard']   = df['compound_HARD']   * df['TyreLife']
df['tyre_age_sq_soft']    = df['compound_SOFT']   * df['tyre_squared']
df['tyre_age_sq_medium']  = df['compound_MEDIUM'] * df['tyre_squared']

# Rolling/lagged features (no leakage)
for window in [3, 5, 7]:
    df[f'delta_roll{window}'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].transform(
        lambda x, w=window: x.rolling(w, min_periods=1).mean().shift(1)
    ).fillna(0)

# Previous lap deltas (strongest signal)
df['prev_delta']   = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].shift(1).fillna(0)
df['prev_delta_2'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].shift(2).fillna(0)

# Degradation trend (accelerating or decelerating?)
df['delta_diff'] = df['prev_delta'] - df['prev_delta_2']

# Rolling std (consistency of recent performance)
df['delta_std3'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].transform(
    lambda x: x.rolling(3, min_periods=1).std().shift(1)
).fillna(0)

# Cumulative tyre stress
df['cum_throttle'] = df.groupby(['season', 'round', 'Driver'])['mean_throttle'].cumsum() / df['LapNumber']
df['cum_brake']    = df.groupby(['season', 'round', 'Driver'])['mean_brake'].cumsum() / df['LapNumber']

# Position momentum
df['position_prev']   = df.groupby(['season', 'round', 'Driver'])['position'].shift(1).fillna(df['position'])
df['position_change'] = df['position'] - df['position_prev']

df = df.dropna(subset=['tyre_delta', 'TyreLife', 'mean_throttle', 'mean_brake'])
print(f'After feature engineering: {len(df)} rows')

FEATURES = [
    # Tire state
    'TyreLife', 'Stint', 'FreshTyre',
    'compound_SOFT', 'compound_MEDIUM', 'compound_HARD',
    'compound_INTERMEDIATE', 'compound_WET',
    'compound_SUPERSOFT', 'compound_ULTRASOFT', 'compound_HYPERSOFT',
    # Compound-age physics
    'compound_age_soft', 'compound_age_medium', 'compound_age_hard',
    'tyre_squared', 'tyre_cubed', 'tyre_per_stint',
    # Fuel
    'fuel_load_pct', 'laps_remaining', 'LapNumber', 'lap_progress',
    # Throttle/brake
    'mean_throttle', 'std_throttle', 'mean_brake', 'std_brake',
    'driving_style', 'throttle_brake_ratio',
    'tyre_x_throttle', 'tyre_x_brake', 'fuel_x_throttle', 'tyre_fuel_interaction',
    # Speed
    'mean_speed', 'max_speed', 'speed_delta',
    'SpeedI1', 'SpeedI2', 'SpeedFL', 'SpeedST',
    # New telemetry features (2022+)
    'mean_rpm', 'max_rpm', 'mean_gear', 'drs_usage_pct', 'lap_distance',
    # Sector times
    'Sector1Time', 'Sector2Time', 'Sector3Time',
    # Race context
    'position', 'gap_ahead',
    # Degradation history (key features)
    'lap_time_delta', 'deg_rate_roll3',
    'prev_delta', 'prev_delta_2', 'delta_diff', 'delta_std3',
    'delta_roll3', 'delta_roll5', 'delta_roll7',
]

features = [f for f in FEATURES if f in df.columns]
print(f'Features: {len(features)} / {len(FEATURES)}')

# Temporal split
train = df[df['season'] <= 2021]
val   = df[(df['season'] >= 2022) & (df['season'] <= 2023)]
test  = df[df['season'] == 2024]
print(f'Train: {len(train)}, Val: {len(val)}, Test: {len(test)}')

X_train, y_train = train[features].fillna(0), train['tyre_delta']
X_val,   y_val   = val[features].fillna(0),   val['tyre_delta']
X_test,  y_test  = test[features].fillna(0),  test['tyre_delta']

print(f'Target std — Train: {y_train.std():.3f}, Val: {y_val.std():.3f}, Test: {y_test.std():.3f}')

# Hyperparameters
LGB_PARAMS = dict(
    n_estimators=2000, max_depth=10, num_leaves=63,
    learning_rate=0.006, subsample=0.7, colsample_bytree=0.6,
    min_child_samples=30, reg_alpha=0.5, reg_lambda=2.0,
    random_state=42, n_jobs=-1, verbose=-1
)
XGB_PARAMS = dict(
    n_estimators=1500, max_depth=8, learning_rate=0.008,
    subsample=0.7, colsample_bytree=0.6, min_child_weight=30,
    reg_alpha=0.5, reg_lambda=2.0, random_state=42,
    tree_method='hist', early_stopping_rounds=100, verbosity=0
)

# Train and track experiment
with aiplatform.start_run(run='tire-degradation-v1'):
    aiplatform.log_params({
        'model': 'LGB+XGB ensemble',
        'lgb_n_estimators': LGB_PARAMS['n_estimators'],
        'lgb_max_depth': LGB_PARAMS['max_depth'],
        'lgb_learning_rate': LGB_PARAMS['learning_rate'],
        'xgb_n_estimators': XGB_PARAMS['n_estimators'],
        'xgb_max_depth': XGB_PARAMS['max_depth'],
        'xgb_learning_rate': XGB_PARAMS['learning_rate'],
        'train_seasons': '2018-2021',
        'val_seasons': '2022-2023',
        'test_season': '2024',
        'n_features': len(features),
        'train_rows': len(train),
    })

    print('\nTraining LightGBM...')
    lgb = LGBMRegressor(**LGB_PARAMS)
    lgb.fit(X_train, y_train, eval_set=[(X_val, y_val)])

    print('Training XGBoost...')
    xgb = XGBRegressor(**XGB_PARAMS)
    xgb.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    # Find optimal ensemble weight
    print('\nFinding optimal ensemble weight...')
    best_mae = float('inf')
    best_w   = 0.5
    for w in np.arange(0.1, 0.95, 0.05):
        pred = w * lgb.predict(X_val) + (1 - w) * xgb.predict(X_val)
        mae  = mean_absolute_error(y_val, pred)
        if mae < best_mae:
            best_mae = mae
            best_w   = round(w, 2)

    print(f'Best weight: LGB={best_w}, XGB={round(1-best_w, 2)}')

    val_pred  = best_w * lgb.predict(X_val)  + (1 - best_w) * xgb.predict(X_val)
    test_pred = best_w * lgb.predict(X_test) + (1 - best_w) * xgb.predict(X_test)

    val_mae  = float(mean_absolute_error(y_val,  val_pred))
    val_r2   = float(r2_score(y_val,  val_pred))
    test_mae = float(mean_absolute_error(y_test, test_pred))
    test_r2  = float(r2_score(y_test, test_pred))

    print('\nTIRE DEGRADATION RESULTS')
    print(f'Val  — MAE: {val_mae:.3f}s, R2: {val_r2:.3f}')
    print(f'Test — MAE: {test_mae:.3f}s, R2: {test_r2:.3f}')

    print('\nIndividual models:')
    print(f'  LGB — Val R2: {r2_score(y_val,  lgb.predict(X_val)):.3f}, Test R2: {r2_score(y_test, lgb.predict(X_test)):.3f}')
    print(f'  XGB — Val R2: {r2_score(y_val,  xgb.predict(X_val)):.3f}, Test R2: {r2_score(y_test, xgb.predict(X_test)):.3f}')

    # Log metrics
    aiplatform.log_metrics({
        'val_mae': val_mae, 'val_r2': val_r2,
        'test_mae': test_mae, 'test_r2': test_r2,
        'lgb_val_r2': float(r2_score(y_val, lgb.predict(X_val))),
        'xgb_val_r2': float(r2_score(y_val, xgb.predict(X_val))),
        'ensemble_weight_lgb': best_w,
    })

print('\nTop 15 Features (LGB):')
for feat, imp in sorted(zip(features, lgb.feature_importances_), key=lambda x: -x[1])[:15]:
    print(f'  {feat}: {imp}')

# Save
os.makedirs('models', exist_ok=True)
joblib.dump({
    'lgb': lgb, 'xgb': xgb,
    'weight': best_w,
    'features': features,
    'driver_encoder': le_driver,
}, 'models/tire_degradation.pkl')
print('\nSaved: models/tire_degradation.pkl')