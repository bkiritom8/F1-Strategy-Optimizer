"""
Fuel Consumption Model - XGBoost + LightGBM Ensemble
Predicts fuel_consumed per lap (varies by driver/driving style)
"""
import pandas as pd
import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.preprocessing import LabelEncoder
from lightgbm import LGBMRegressor
from xgboost import XGBRegressor
import joblib
import os

df = pd.read_parquet('gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet')
print(f'Loaded: {len(df)} rows')
print(f'Seasons: {sorted(df["season"].unique())}')
print(f'fuel_consumed stats: mean={df["fuel_consumed"].mean():.4f}, std={df["fuel_consumed"].std():.4f}')

le_driver = LabelEncoder()
df['driver_encoded'] = le_driver.fit_transform(df['Driver'].astype(str))

df = df.sort_values(['season', 'round', 'Driver', 'LapNumber']).reset_index(drop=True)

# Rolling throttle features
df['throttle_roll3'] = df.groupby(['season', 'round', 'Driver'])['mean_throttle'].transform(
    lambda x: x.rolling(3, min_periods=1).mean().shift(1)
).fillna(df['mean_throttle'])

df['throttle_roll5'] = df.groupby(['season', 'round', 'Driver'])['mean_throttle'].transform(
    lambda x: x.rolling(5, min_periods=1).mean().shift(1)
).fillna(df['mean_throttle'])

# Previous lap fuel consumed (lagged - no leakage)
df['prev_fuel_consumed'] = df.groupby(['season', 'round', 'Driver'])['fuel_consumed'].shift(1).fillna(
    df['fuel_consumed'].mean()
)
df['fuel_consumed_roll3'] = df.groupby(['season', 'round', 'Driver'])['fuel_consumed'].transform(
    lambda x: x.rolling(3, min_periods=1).mean().shift(1)
).fillna(df['fuel_consumed'].mean())

df = df.dropna(subset=['fuel_consumed', 'mean_throttle'])
print(f'After feature engineering: {len(df)} rows')

FEATURES = [
    'LapNumber', 'total_laps', 'laps_remaining', 'fuel_load_pct',
    'mean_brake', 'std_brake',
    'mean_speed', 'max_speed',
    'SpeedI1', 'SpeedI2', 'SpeedFL', 'SpeedST',
    'Sector1Time', 'Sector2Time', 'Sector3Time',
    'lap_time_delta', 'deg_rate_roll3',
    'TyreLife', 'Stint',
    'compound_SOFT', 'compound_MEDIUM', 'compound_HARD',
    'position', 'gap_ahead',
]

features = [f for f in FEATURES if f in df.columns]
print(f'Features: {len(features)} / {len(FEATURES)}')

train = df[df['season'] <= 2021]
val   = df[(df['season'] >= 2022) & (df['season'] <= 2023)]
test  = df[df['season'] == 2024]
print(f'Train: {len(train)}, Val: {len(val)}, Test: {len(test)}')

X_train, y_train = train[features].fillna(0), train['fuel_consumed']
X_val,   y_val   = val[features].fillna(0),   val['fuel_consumed']
X_test,  y_test  = test[features].fillna(0),  test['fuel_consumed']

print(f'Target std — Train: {y_train.std():.4f}, Val: {y_val.std():.4f}, Test: {y_test.std():.4f}')

print('\nTraining LightGBM...')
lgb = LGBMRegressor(
    n_estimators=2000, max_depth=10, num_leaves=63,
    learning_rate=0.006, subsample=0.7, colsample_bytree=0.6,
    min_child_samples=30, reg_alpha=0.5, reg_lambda=2.0,
    random_state=42, n_jobs=-1, verbose=-1
)
lgb.fit(X_train, y_train, eval_set=[(X_val, y_val)])

print('Training XGBoost...')
xgb = XGBRegressor(
    n_estimators=1500, max_depth=8, learning_rate=0.008,
    subsample=0.7, colsample_bytree=0.6, min_child_weight=30,
    reg_alpha=0.5, reg_lambda=2.0, random_state=42,
    tree_method='hist', early_stopping_rounds=100, verbosity=0
)
xgb.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

print('\nFinding optimal ensemble weight...')
best_mae = float('inf')
best_w = 0.5
for w in np.arange(0.1, 0.95, 0.05):
    pred = w * lgb.predict(X_val) + (1 - w) * xgb.predict(X_val)
    mae = mean_absolute_error(y_val, pred)
    if mae < best_mae:
        best_mae = mae
        best_w = round(w, 2)

print(f'Best weight: LGB={best_w}, XGB={round(1-best_w, 2)}')

val_pred  = best_w * lgb.predict(X_val)  + (1 - best_w) * xgb.predict(X_val)
test_pred = best_w * lgb.predict(X_test) + (1 - best_w) * xgb.predict(X_test)

print('\nFUEL CONSUMPTION RESULTS')
print(f'Val  — MAE: {mean_absolute_error(y_val,  val_pred):.4f}, R2: {r2_score(y_val,  val_pred):.3f}')
print(f'Test — MAE: {mean_absolute_error(y_test, test_pred):.4f}, R2: {r2_score(y_test, test_pred):.3f}')

print('\nIndividual models:')
print(f'  LGB — Val R2: {r2_score(y_val,  lgb.predict(X_val)):.3f}, Test R2: {r2_score(y_test, lgb.predict(X_test)):.3f}')
print(f'  XGB — Val R2: {r2_score(y_val,  xgb.predict(X_val)):.3f}, Test R2: {r2_score(y_test, xgb.predict(X_test)):.3f}')

print('\nTop 15 Features (LGB):')
for feat, imp in sorted(zip(features, lgb.feature_importances_), key=lambda x: -x[1])[:15]:
    print(f'  {feat}: {imp}')

os.makedirs('models', exist_ok=True)
joblib.dump({
    'lgb': lgb, 'xgb': xgb,
    'weight': best_w,
    'features': features,
    'driver_encoder': le_driver,
}, 'models/fuel_consumption.pkl')
print('\nSaved: models/fuel_consumption.pkl')