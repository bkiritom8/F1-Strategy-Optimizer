"""
Overtake Probability Model - RandomForest with Isotonic Calibration
Predicts binary overtake_success (0/1) per lap
Uses cumulative race time gap to car ahead
"""
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import (
    accuracy_score, f1_score, precision_score,
    recall_score, classification_report,
)
from sklearn.preprocessing import LabelEncoder
import joblib
import os

df = pd.read_parquet('gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet')
print(f'Loaded: {len(df)} rows')
print(f'Seasons: {sorted(df["season"].unique())}')

le_driver = LabelEncoder()
df['driver_encoded'] = le_driver.fit_transform(df['Driver'].astype(str))

df = df.sort_values(['season', 'round', 'Driver', 'LapNumber']).reset_index(drop=True)

print(f'\novertake_success distribution:')
print(df['overtake_success'].value_counts())
print(df['overtake_success'].value_counts(normalize=True).round(3))

# Compute proper cumulative gap to car ahead
print('\nComputing cumulative race gaps...')
df['cum_race_time'] = df.groupby(['season', 'round', 'Driver'])['LapTime'].cumsum()

def compute_gaps(group):
    group = group.sort_values('cum_race_time')
    group['real_gap_ahead'] = group['cum_race_time'].diff().fillna(0)
    return group

gap_df = df.groupby(['season', 'round', 'LapNumber'], group_keys=False).apply(compute_gaps)
df['real_gap_ahead'] = gap_df['real_gap_ahead'].reindex(df.index).fillna(0).clip(-60, 60)
df['in_drs_zone']   = (df['real_gap_ahead'].abs() < 1.0).astype(int)
df['in_drs_zone_2'] = (df['real_gap_ahead'].abs() < 2.0).astype(int)

print(f'  Real DRS zone laps (< 1s): {df["in_drs_zone"].sum()}')
print(f'  Real DRS zone laps (< 2s): {df["in_drs_zone_2"].sum()}')

# Feature engineering
df['tyre_squared']        = df['TyreLife'] ** 2
df['tyre_cubed']          = df['TyreLife'] ** 3
df['tyre_per_stint']      = df['TyreLife'] / (df['Stint'] + 1)
df['lap_progress']        = df['LapNumber'] / df['total_laps']

df['compound_age_soft']   = df['compound_SOFT']   * df['TyreLife']
df['compound_age_medium'] = df['compound_MEDIUM']  * df['TyreLife']
df['compound_age_hard']   = df['compound_HARD']    * df['TyreLife']

for window in [3, 5, 7]:
    df[f'delta_roll{window}'] = df.groupby(
        ['season', 'round', 'Driver']
    )['tyre_delta'].transform(
        lambda x, w=window: x.rolling(w, min_periods=1).mean().shift(1)
    ).fillna(0)

df['prev_delta']   = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].shift(1).fillna(0)
df['prev_delta_2'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].shift(2).fillna(0)
df['delta_diff']   = df['prev_delta'] - df['prev_delta_2']

df['cum_throttle'] = df.groupby(['season', 'round', 'Driver'])['mean_throttle'].cumsum() / df['LapNumber']
df['cum_brake']    = df.groupby(['season', 'round', 'Driver'])['mean_brake'].cumsum() / df['LapNumber']

df['overtake_roll3'] = df.groupby(['season', 'round', 'Driver'])['overtake_success'].transform(
    lambda x: x.rolling(3, min_periods=1).mean().shift(1)
).fillna(0)

df['throttle_roll3'] = df.groupby(['season', 'round', 'Driver'])['mean_throttle'].transform(
    lambda x: x.rolling(3, min_periods=1).mean().shift(1)
).fillna(df['mean_throttle'])
df['brake_roll3'] = df.groupby(['season', 'round', 'Driver'])['mean_brake'].transform(
    lambda x: x.rolling(3, min_periods=1).mean().shift(1)
).fillna(df['mean_brake'])

df['drs_zone']        = (df['gap_ahead'].abs() < 1.0).astype(int)
df['tyre_x_throttle'] = df['TyreLife'] * df['mean_throttle'] / 100
df['tyre_x_brake']    = df['TyreLife'] * df['mean_brake']    / 100

df['speed_roll3'] = df.groupby(['season', 'round', 'Driver'])['mean_speed'].transform(
    lambda x: x.rolling(3, min_periods=1).mean().shift(1)
).fillna(df['mean_speed'])
df['speed_delta'] = df['mean_speed'] - df['speed_roll3']

field_size         = df.groupby(['season', 'round'])['Driver'].transform('nunique')
df['position_pct'] = df['position'] / field_size
df['field_size']   = field_size

df['driving_style_encoded'] = df['driving_style'] if df['driving_style'].dtype != object else \
    df['driving_style'].map({'NEUTRAL': 0, 'BALANCE': 1, 'PUSH': 2}).fillna(1)

df = df.dropna(subset=['overtake_success', 'position'])
print(f'\nAfter feature engineering: {len(df)} rows')

FEATURES = [
    'real_gap_ahead', 'in_drs_zone', 'in_drs_zone_2',
    'gap_ahead', 'drs_zone',
    'TyreLife', 'Stint', 'FreshTyre',
    'compound_SOFT', 'compound_MEDIUM', 'compound_HARD',
    'compound_INTERMEDIATE', 'compound_WET',
    'compound_SUPERSOFT', 'compound_ULTRASOFT', 'compound_HYPERSOFT',
    'compound_age_soft', 'compound_age_medium', 'compound_age_hard',
    'tyre_squared', 'tyre_cubed', 'tyre_per_stint',
    'tyre_x_throttle', 'tyre_x_brake',
    'tyre_delta', 'deg_rate_roll3',
    'prev_delta', 'prev_delta_2', 'delta_diff',
    'delta_roll3', 'delta_roll5', 'delta_roll7',
    'mean_throttle', 'std_throttle', 'throttle_roll3',
    'mean_brake', 'std_brake', 'brake_roll3',
    'cum_throttle', 'cum_brake',
    'mean_speed', 'max_speed', 'speed_delta',
    'SpeedI1', 'SpeedI2', 'SpeedFL', 'SpeedST',
    'Sector1Time', 'Sector2Time', 'Sector3Time',
    'LapNumber', 'lap_progress', 'laps_remaining', 'fuel_load_pct',
    'position', 'position_pct', 'field_size',
    'overtake_roll3',
    'mean_rpm', 'max_rpm', 'mean_gear', 'drs_usage_pct',
    'driving_style_encoded',
    'driver_encoded',
]

features = [f for f in FEATURES if f in df.columns]
print(f'Features: {len(features)} / {len(FEATURES)}')

train = df[df['season'] <= 2021]
val   = df[(df['season'] >= 2022) & (df['season'] <= 2023)]
test  = df[df['season'] == 2024]
print(f'Train: {len(train)}, Val: {len(val)}, Test: {len(test)}')

X_train, y_train = train[features].fillna(0), train['overtake_success']
X_val,   y_val   = val[features].fillna(0),   val['overtake_success']
X_test,  y_test  = test[features].fillna(0),  test['overtake_success']

print(f'\nClass balance — Train: {y_train.mean():.3f}, Val: {y_val.mean():.3f}, Test: {y_test.mean():.3f}')

print('\nTraining RandomForest...')
base_rf = RandomForestClassifier(
    n_estimators=1000,
    max_depth=12,
    min_samples_leaf=30,
    max_features='sqrt',
    class_weight='balanced',
    random_state=42,
    n_jobs=-1,
)
model = CalibratedClassifierCV(base_rf, method='isotonic', cv=3)
model.fit(X_train, y_train)

val_proba = model.predict_proba(X_val)[:, 1]

best_f1, best_thresh = 0, 0.5
for thresh in np.arange(0.1, 0.6, 0.01):
    pred = (val_proba >= thresh).astype(int)
    f1 = f1_score(y_val, pred, zero_division=0)
    if f1 > best_f1:
        best_f1 = f1
        best_thresh = round(thresh, 2)

print(f'Optimal threshold: {best_thresh}')

val_pred   = (val_proba >= best_thresh).astype(int)
test_proba = model.predict_proba(X_test)[:, 1]
test_pred  = (test_proba >= best_thresh).astype(int)

try:
    frac_pos, mean_pred = calibration_curve(y_val, val_proba, n_bins=10)
    ece = float(np.mean(np.abs(frac_pos - mean_pred)))
except Exception:
    ece = float('nan')

print('\nOVERTAKE PROBABILITY RESULTS')
print(f'Val  — F1: {f1_score(y_val, val_pred, zero_division=0):.3f}, '
      f'Acc: {accuracy_score(y_val, val_pred):.3f}, '
      f'Prec: {precision_score(y_val, val_pred, zero_division=0):.3f}, '
      f'Rec: {recall_score(y_val, val_pred, zero_division=0):.3f}')
print(f'Test — F1: {f1_score(y_test, test_pred, zero_division=0):.3f}, '
      f'Acc: {accuracy_score(y_test, test_pred):.3f}, '
      f'Prec: {precision_score(y_test, test_pred, zero_division=0):.3f}, '
      f'Rec: {recall_score(y_test, test_pred, zero_division=0):.3f}')
print(f'Val ECE: {ece:.4f} (target < 0.05)')

print('\nVal Classification Report:')
print(classification_report(y_val, val_pred, target_names=['No overtake', 'Overtake'], zero_division=0))

print('\nTop 15 Features:')
rf = model.calibrated_classifiers_[0].estimator
for feat, imp in sorted(zip(features, rf.feature_importances_), key=lambda x: -x[1])[:15]:
    print(f'  {feat}: {imp:.4f}')

os.makedirs('models', exist_ok=True)
joblib.dump({
    'model': model,
    'threshold': best_thresh,
    'features': features,
    'driver_encoder': le_driver,
}, 'models/overtake_prob.pkl')
print('\nSaved: models/overtake_prob.pkl')