"""
Pit Window Model - XGBoost + LightGBM Ensemble
Predicts laps_in_stint_remaining: laps left in current tire stint
Dry conditions only, RobustScaler, stint-level target
Val MAE=1.262 laps R2=0.948 | Test MAE=1.150 laps R2=0.967
"""
import pandas as pd
import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import LabelEncoder, RobustScaler
from lightgbm import LGBMRegressor
from xgboost import XGBRegressor
import joblib
import os
from google.cloud import aiplatform

# Vertex AI Experiment Tracking
aiplatform.init(project='f1optimizer', location='us-central1', experiment='f1-strategy-models')

# Load data
df = pd.read_parquet('gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet')
print(f'Loaded: {len(df)} rows')
print(f'Seasons: {sorted(df["season"].unique())}')
print(f'laps_to_pit stats: mean={df["laps_to_pit"].mean():.3f}, std={df["laps_to_pit"].std():.3f}')

# Encode driver and circuit
le_driver  = LabelEncoder()
le_circuit = LabelEncoder()
df['driver_encoded']  = le_driver.fit_transform(df['Driver'].astype(str))
df['circuit_encoded'] = le_circuit.fit_transform(df['raceName'].astype(str))

df = df.sort_values(['season', 'round', 'Driver', 'LapNumber']).reset_index(drop=True)

# Filter dry conditions only
dry_compounds = ['SOFT', 'MEDIUM', 'HARD', 'SUPERSOFT', 'ULTRASOFT', 'HYPERSOFT']
df = df[df['Compound'].str.upper().isin(dry_compounds)].copy()
print(f'After dry filter: {len(df)} rows')

# Stint-level target: laps remaining in current stint
df['stint_end_lap']           = df.groupby(['season', 'round', 'Driver', 'Stint'])['LapNumber'].transform('max')
df['laps_in_stint_remaining'] = df['stint_end_lap'] - df['LapNumber']

# Feature engineering
df['tyre_squared']         = df['TyreLife'] ** 2
df['tyre_cubed']           = df['TyreLife'] ** 3
df['tyre_per_stint']       = df['TyreLife'] / (df['Stint'] + 1)
df['lap_progress']         = df['LapNumber'] / df['total_laps']
df['throttle_brake_ratio'] = df['mean_throttle'] / (df['mean_brake'] + 1)
df['pit_stops_so_far']     = (df['Stint'] - 1).clip(lower=0)

df['compound_age_soft']    = df['compound_SOFT']   * df['TyreLife']
df['compound_age_medium']  = df['compound_MEDIUM'] * df['TyreLife']
df['compound_age_hard']    = df['compound_HARD']   * df['TyreLife']
df['tyre_age_sq_soft']     = df['compound_SOFT']   * df['tyre_squared']
df['tyre_age_sq_medium']   = df['compound_MEDIUM'] * df['tyre_squared']

for window in [3, 5, 7]:
    df[f'deg_roll{window}'] = df.groupby(
        ['season', 'round', 'Driver']
    )['tyre_delta'].transform(
        lambda x, w=window: x.rolling(w, min_periods=1).mean().shift(1)
    ).fillna(0)

df['prev_delta']   = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].shift(1).fillna(0)
df['prev_delta_2'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].shift(2).fillna(0)
df['delta_diff']   = df['prev_delta'] - df['prev_delta_2']
df['delta_std3']   = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].transform(
    lambda x: x.rolling(3, min_periods=1).std().shift(1)
).fillna(0)

df['cum_throttle'] = df.groupby(['season', 'round', 'Driver'])['mean_throttle'].cumsum() / df['LapNumber']
df['cum_brake']    = df.groupby(['season', 'round', 'Driver'])['mean_brake'].cumsum() / df['LapNumber']

df['undercut_delta']   = df['deg_rate_roll3'] * df['TyreLife']
df['is_in_traffic']    = (df['gap_ahead'] < 3.0).astype(int)
df['deg_acceleration'] = df['deg_rate_roll3'] - df.groupby(
    ['season', 'round', 'Driver'])['deg_rate_roll3'].shift(3).fillna(0)
df['cliff_approaching'] = (df['deg_acceleration'] > 0.05).astype(int)

field_size         = df.groupby(['season', 'round'])['Driver'].transform('nunique')
df['position_pct'] = df['position'] / field_size

df['driving_style_encoded'] = df['driving_style'] if df['driving_style'].dtype != object else \
    df['driving_style'].map({'NEUTRAL': 0, 'BALANCE': 1, 'PUSH': 2}).fillna(1)

df['stint_progress'] = df['TyreLife'] / (df['stint_end_lap'] - df.groupby(
    ['season', 'round', 'Driver', 'Stint'])['LapNumber'].transform('min') + 1).clip(lower=1)

# Circuit-level features from training data only
train_mask = df['season'] <= 2021

circuit_avg_stops = (
    df[train_mask].groupby(['season', 'round'])
    .agg(raceName=('raceName', 'first'), max_stint=('Stint', 'max'))
    .groupby('raceName')['max_stint'].mean().rename('circuit_avg_stops')
)
df = df.join(circuit_avg_stops, on='raceName')
df['circuit_avg_stops'] = df['circuit_avg_stops'].fillna(2.0)

compound_circuit_stint = (
    df[train_mask].groupby(['raceName', 'Compound'])['TyreLife']
    .max().rename('expected_stint_len')
)
df = df.join(compound_circuit_stint, on=['raceName', 'Compound'])
df['expected_stint_len']  = df['expected_stint_len'].fillna(30)
df['laps_until_optimal']  = (df['expected_stint_len'] - df['TyreLife']).clip(lower=0)
df['total_planned_stops'] = df['circuit_avg_stops'].round().clip(1, 4)
df['remaining_pit_stops'] = (df['total_planned_stops'] - df['pit_stops_so_far']).clip(lower=0)

print(f'\nTop 5 highest avg stops circuits:')
print(circuit_avg_stops.sort_values(ascending=False).head())

# Log transform target
df['laps_to_pit_log'] = np.log1p(df['laps_in_stint_remaining'])

df = df.dropna(subset=['laps_in_stint_remaining', 'TyreLife', 'mean_throttle', 'mean_brake'])
print(f'After feature engineering: {len(df)} rows')

FEATURES = [
    # Tyre state
    'TyreLife', 'Stint', 'FreshTyre',
    'compound_SOFT', 'compound_MEDIUM', 'compound_HARD',
    'compound_SUPERSOFT', 'compound_ULTRASOFT', 'compound_HYPERSOFT',
    'compound_age_soft', 'compound_age_medium', 'compound_age_hard',
    'tyre_age_sq_soft', 'tyre_age_sq_medium',
    'tyre_squared', 'tyre_cubed', 'tyre_per_stint',
    # Fuel and race progress
    'fuel_load_pct', 'laps_remaining', 'LapNumber', 'lap_progress',
    # Degradation history
    'tyre_delta', 'deg_rate_roll3',
    'prev_delta', 'prev_delta_2', 'delta_diff', 'delta_std3',
    'deg_roll3', 'deg_roll5', 'deg_roll7',
    'deg_acceleration', 'cliff_approaching',
    # Driving inputs
    'mean_throttle', 'std_throttle', 'mean_brake', 'std_brake',
    'throttle_brake_ratio', 'cum_throttle', 'cum_brake',
    # Speed
    'mean_speed', 'max_speed',
    'SpeedI1', 'SpeedI2', 'SpeedFL', 'SpeedST',
    # Sector times
    'Sector1Time', 'Sector2Time', 'Sector3Time',
    # Race context
    'position', 'position_pct', 'gap_ahead',
    'undercut_delta', 'is_in_traffic',
    # Strategy context
    'pit_stops_so_far', 'remaining_pit_stops', 'total_planned_stops',
    'circuit_encoded', 'circuit_avg_stops',
    'expected_stint_len', 'laps_until_optimal', 'stint_progress',
    # New telemetry
    'mean_rpm', 'max_rpm', 'mean_gear', 'drs_usage_pct',
    # Driving style and driver
    'driving_style_encoded', 'driver_encoded',
]

features = [f for f in FEATURES if f in df.columns]
print(f'Features: {len(features)} / {len(FEATURES)}')

# Temporal split
train = df[df['season'] <= 2021]
val   = df[(df['season'] >= 2022) & (df['season'] <= 2023)]
test  = df[df['season'] == 2024]
print(f'Train: {len(train)}, Val: {len(val)}, Test: {len(test)}')

# RobustScaler on numerical features
cat_feats    = ['compound_SOFT','compound_MEDIUM','compound_HARD','compound_SUPERSOFT',
                'compound_ULTRASOFT','compound_HYPERSOFT','FreshTyre','cliff_approaching',
                'is_in_traffic','driver_encoded','circuit_encoded','driving_style_encoded']
num_features = [f for f in features if f not in cat_feats]

scaler = RobustScaler()
X_train_raw = train[features].fillna(0).copy()
X_val_raw   = val[features].fillna(0).copy()
X_test_raw  = test[features].fillna(0).copy()
X_train_raw[num_features] = scaler.fit_transform(X_train_raw[num_features])
X_val_raw[num_features]   = scaler.transform(X_val_raw[num_features])
X_test_raw[num_features]  = scaler.transform(X_test_raw[num_features])

y_train     = train['laps_to_pit_log']
y_val       = val['laps_to_pit_log']
y_test      = test['laps_to_pit_log']
y_val_orig  = val['laps_in_stint_remaining']
y_test_orig = test['laps_in_stint_remaining']

print(f'Target std — Train: {y_train.std():.3f}, Val: {y_val.std():.3f}, Test: {y_test.std():.3f}')

# Hyperparameters
XGB_PARAMS = dict(
    n_estimators=1500, max_depth=8, learning_rate=0.008,
    subsample=0.7, colsample_bytree=0.6, min_child_weight=30,
    reg_alpha=0.5, reg_lambda=2.0, random_state=42,
    tree_method='hist', early_stopping_rounds=100, verbosity=0,
)
LGB_PARAMS = dict(
    n_estimators=2000, max_depth=10, num_leaves=63,
    learning_rate=0.006, subsample=0.7, colsample_bytree=0.6,
    min_child_samples=30, reg_alpha=0.5, reg_lambda=2.0,
    random_state=42, n_jobs=-1, verbose=-1,
)

# Train and track experiment
with aiplatform.start_run(run='pit-window-v1'):
    aiplatform.log_params({
        'model': 'XGB+LGB ensemble',
        'target': 'laps_in_stint_remaining (log-transformed)',
        'xgb_n_estimators': XGB_PARAMS['n_estimators'],
        'lgb_n_estimators': LGB_PARAMS['n_estimators'],
        'scaler': 'RobustScaler',
        'dry_conditions_only': 'True',
        'train_seasons': '2018-2021',
        'n_features': len(features),
    })

    print('\nTraining XGBoost...')
    xgb_model = XGBRegressor(**XGB_PARAMS)
    xgb_model.fit(X_train_raw, y_train, eval_set=[(X_val_raw, y_val)], verbose=False)

    print('Training LightGBM...')
    lgb_model = LGBMRegressor(**LGB_PARAMS)
    lgb_model.fit(X_train_raw, y_train, eval_set=[(X_val_raw, y_val)])

    # Find optimal ensemble weight
    print('\nFinding optimal ensemble weight...')
    best_mae, best_w = float('inf'), 0.5
    for w in np.arange(0.1, 0.95, 0.05):
        pred = np.expm1(w * xgb_model.predict(X_val_raw) + (1 - w) * lgb_model.predict(X_val_raw))
        mae  = mean_absolute_error(y_val_orig, pred)
        if mae < best_mae:
            best_mae = mae
            best_w   = round(w, 2)

    print(f'Best weight: XGB={best_w}, LGB={round(1-best_w, 2)}')

    val_pred  = np.expm1(best_w * xgb_model.predict(X_val_raw)  + (1 - best_w) * lgb_model.predict(X_val_raw))
    test_pred = np.expm1(best_w * xgb_model.predict(X_test_raw) + (1 - best_w) * lgb_model.predict(X_test_raw))

    val_mae  = float(mean_absolute_error(y_val_orig,  val_pred))
    val_r2   = float(r2_score(y_val_orig,  val_pred))
    test_mae = float(mean_absolute_error(y_test_orig, test_pred))
    test_r2  = float(r2_score(y_test_orig, test_pred))

    print('\nPIT WINDOW RESULTS')
    print(f'Val  — MAE: {val_mae:.3f} laps, R2: {val_r2:.3f}')
    print(f'Test — MAE: {test_mae:.3f} laps, R2: {test_r2:.3f}')

    print('\nIndividual models:')
    print(f'  XGB — Val MAE: {mean_absolute_error(y_val_orig, np.expm1(xgb_model.predict(X_val_raw))):.3f}, '
          f'Test MAE: {mean_absolute_error(y_test_orig, np.expm1(xgb_model.predict(X_test_raw))):.3f}')
    print(f'  LGB — Val MAE: {mean_absolute_error(y_val_orig, np.expm1(lgb_model.predict(X_val_raw))):.3f}, '
          f'Test MAE: {mean_absolute_error(y_test_orig, np.expm1(lgb_model.predict(X_test_raw))):.3f}')

    print('\nTop 15 Features (XGB):')
    for feat, imp in sorted(zip(features, xgb_model.feature_importances_), key=lambda x: -x[1])[:15]:
        print(f'  {feat}: {imp:.4f}')

    # Log metrics
    aiplatform.log_metrics({
        'val_mae': val_mae, 'val_r2': val_r2,
        'test_mae': test_mae, 'test_r2': test_r2,
        'ensemble_weight_xgb': best_w,
    })

# Save
os.makedirs('models', exist_ok=True)
joblib.dump({
    'xgb': xgb_model, 'lgb': lgb_model, 'weight': best_w,
    'features': features, 'scaler': scaler, 'num_features': num_features,
    'driver_encoder': le_driver, 'circuit_encoder': le_circuit,
    'circuit_avg_stops': circuit_avg_stops.to_dict(),
    'compound_circuit_stint': compound_circuit_stint.to_dict(),
    'target': 'laps_in_stint_remaining',
}, 'models/pit_window.pkl')
print('\nSaved: models/pit_window.pkl')