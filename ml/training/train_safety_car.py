"""
Safety Car Strategy Model
Trains a binary classifier for SC pit decision and builds
a circuit-level SC probability lookup table.
Saved to models/safety_car.pkl
"""
import pandas as pd
import numpy as np
from sklearn.metrics import classification_report, accuracy_score, f1_score
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier
import joblib
import os

df = pd.read_parquet('gs://f1optimizer-data-lake/ml_features/fastf1_features_unfiltered.parquet')
print(f'Loaded: {len(df)} rows')
print(f'Seasons: {sorted(df["season"].unique())}')
print(f'SC laps: {df["is_sc_lap"].sum()} ({df["is_sc_lap"].mean()*100:.1f}%)')
print(f'Pitted under SC: {df["pitted_under_sc"].sum()}')

# Circuit SC probability lookup
print('\nBuilding circuit SC probability lookup...')
circuit_sc = (
    df.groupby(['season', 'round'])
    .agg(
        total_laps=('LapNumber', 'max'),
        sc_laps=('is_sc_lap', 'sum'),
        raceName=('raceName', 'first')
    )
    .reset_index()
)
circuit_sc['sc_prob_per_lap'] = circuit_sc['sc_laps'] / circuit_sc['total_laps']
circuit_prob = (
    circuit_sc.groupby('raceName')['sc_prob_per_lap']
    .mean()
    .round(4)
    .to_dict()
)
print(f'  Circuits: {len(circuit_prob)}')
print('  Top 5 highest SC probability:')
for c, p in sorted(circuit_prob.items(), key=lambda x: -x[1])[:5]:
    print(f'    {c}: {p:.3f} per lap')

# Filter to SC laps
sc_df = df[df['is_sc_lap'] == 1].copy()
print(f'\nSC laps: {len(sc_df)}, Pit rate: {sc_df["pitted_under_sc"].mean()*100:.1f}%')

sc_df = sc_df.sort_values(['season', 'round', 'Driver', 'LapNumber']).reset_index(drop=True)

# Feature engineering
sc_df['lap_progress'] = sc_df['LapNumber'] / sc_df['total_laps']
sc_df['tyre_life_pct'] = sc_df['TyreLife'] / sc_df['total_laps'].clip(lower=1)
sc_df['soft_age'] = sc_df['compound_SOFT'] * sc_df['TyreLife']
sc_df['medium_age'] = sc_df['compound_MEDIUM'] * sc_df['TyreLife']
sc_df['hard_age'] = sc_df['compound_HARD'] * sc_df['TyreLife']

# SOTA additions: pit stop count, tyre delta trend, race phase
sc_df['pit_stops_so_far'] = sc_df['Stint'] - 1  # stint 1 = 0 stops, stint 2 = 1 stop etc.

sc_df['tyre_delta_trend'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].transform(
    lambda x: x.rolling(5, min_periods=2).mean().shift(1)
).reindex(sc_df.index).fillna(0)

sc_df['race_phase'] = pd.cut(
    sc_df['lap_progress'],
    bins=[0, 0.33, 0.66, 1.0],
    labels=[0, 1, 2]
).astype(float)

# Optimal stint length remaining (how many laps past optimal stint)
OPTIMAL_STINT = {'SOFT': 20, 'MEDIUM': 30, 'HARD': 45, 'INTERMEDIATE': 25, 'WET': 20}
sc_df['optimal_stint_len'] = sc_df['Compound'].str.upper().map(OPTIMAL_STINT).fillna(30)
sc_df['laps_past_optimal'] = (sc_df['TyreLife'] - sc_df['optimal_stint_len']).clip(lower=0)

sc_df = sc_df.dropna(subset=['pitted_under_sc', 'TyreLife', 'position', 'laps_remaining'])
print(f'After cleaning: {len(sc_df)} rows')

FEATURES = [
    # Tire state
    'TyreLife', 'tyre_life_pct', 'Stint', 'FreshTyre',
    'compound_SOFT', 'compound_MEDIUM', 'compound_HARD',
    'compound_INTERMEDIATE', 'compound_WET',
    'soft_age', 'medium_age', 'hard_age',
    'laps_past_optimal', 'optimal_stint_len',
    # Race context
    'LapNumber', 'laps_remaining', 'lap_progress', 'total_laps',
    'fuel_load_pct', 'race_phase',
    # Strategy state
    'pit_stops_so_far',
    # Position
    'position', 'gap_ahead',
    # Lap time context
    'tyre_delta', 'tyre_delta_trend', 'lap_time_delta', 'deg_rate_roll3',
    # Speed/sector
    'mean_speed', 'max_speed',
    'Sector1Time', 'Sector2Time', 'Sector3Time',
    'SpeedI1', 'SpeedI2', 'SpeedFL', 'SpeedST',
]

features = [f for f in FEATURES if f in sc_df.columns]
print(f'Features: {len(features)} / {len(FEATURES)}')

train = sc_df[sc_df['season'] <= 2021]
val   = sc_df[(sc_df['season'] >= 2022) & (sc_df['season'] <= 2023)]
test  = sc_df[sc_df['season'] == 2024]
print(f'Train: {len(train)}, Val: {len(val)}, Test: {len(test)}')

X_train = train[features].fillna(0)
X_val   = val[features].fillna(0)
X_test  = test[features].fillna(0)
y_train = train['pitted_under_sc']
y_val   = val['pitted_under_sc']
y_test  = test['pitted_under_sc']

print('\nTraining LightGBM...')
lgb_pit = LGBMClassifier(
    n_estimators=1000, max_depth=7, num_leaves=31,
    learning_rate=0.01, subsample=0.7, colsample_bytree=0.7,
    min_child_samples=20, reg_alpha=0.5, reg_lambda=1.0,
    random_state=42, n_jobs=-1, verbose=-1,
    class_weight='balanced'
)
lgb_pit.fit(X_train, y_train, eval_set=[(X_val, y_val)])

print('Training XGBoost...')
xgb_pit = XGBClassifier(
    n_estimators=800, max_depth=6, learning_rate=0.01,
    subsample=0.7, colsample_bytree=0.7, min_child_weight=20,
    reg_alpha=0.5, reg_lambda=1.0, random_state=42,
    tree_method='hist', early_stopping_rounds=50,
    verbosity=0, eval_metric='logloss',
    scale_pos_weight=(1 - y_train.mean()) / y_train.mean()
)
xgb_pit.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

print('Finding optimal ensemble weight...')
best_f1 = 0
best_w = 0.5
for w in np.arange(0.1, 0.95, 0.05):
    lgb_p = lgb_pit.predict_proba(X_val)[:, 1]
    xgb_p = xgb_pit.predict_proba(X_val)[:, 1]
    pred = ((w * lgb_p + (1 - w) * xgb_p) >= 0.5).astype(int)
    f1 = f1_score(y_val, pred, average='macro')
    if f1 > best_f1:
        best_f1 = f1
        best_w = round(w, 2)

print(f'Best weight: LGB={best_w}, XGB={round(1-best_w, 2)}')

lgb_p  = lgb_pit.predict_proba(X_val)[:, 1]
xgb_p  = xgb_pit.predict_proba(X_val)[:, 1]
val_pred = ((best_w * lgb_p + (1 - best_w) * xgb_p) >= 0.5).astype(int)

lgb_pt = lgb_pit.predict_proba(X_test)[:, 1]
xgb_pt = xgb_pit.predict_proba(X_test)[:, 1]
test_pred = ((best_w * lgb_pt + (1 - best_w) * xgb_pt) >= 0.5).astype(int)

print(f'\nSC PIT DECISION RESULTS')
print(f'Val  — Accuracy: {accuracy_score(y_val, val_pred):.3f}, F1 macro: {f1_score(y_val, val_pred, average="macro"):.3f}')
print(f'Test — Accuracy: {accuracy_score(y_test, test_pred):.3f}, F1 macro: {f1_score(y_test, test_pred, average="macro"):.3f}')
print('\nVal Classification Report:')
print(classification_report(y_val, val_pred, target_names=['Stay Out', 'Pit']))

print('\nTop 10 Features (LGB):')
for feat, imp in sorted(zip(features, lgb_pit.feature_importances_), key=lambda x: -x[1])[:10]:
    print(f'  {feat}: {imp}')

os.makedirs('models', exist_ok=True)
joblib.dump({
    'pit_lgb': lgb_pit,
    'pit_xgb': xgb_pit,
    'pit_weight': best_w,
    'circuit_sc_prob': circuit_prob,
    'features': features,
}, 'models/safety_car.pkl')
print('\nSaved: models/safety_car.pkl')
print(f'  Circuit SC probabilities: {len(circuit_prob)} circuits')
print(f'  Pit decision — Val F1: {best_f1:.3f}')