"""
Race Outcome Model - CatBoost + LightGBM Ensemble
Predicts finish tier: Podium / Points / Outside Points
Pre-race features only — no leakage
Championship points features from race_results.parquet
"""
import ast
import pandas as pd
import numpy as np
from sklearn.metrics import accuracy_score, f1_score, classification_report
from sklearn.preprocessing import LabelEncoder
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
import joblib
import os

def extract_id(s, key):
    try:
        d = ast.literal_eval(str(s))
        return d[key] if isinstance(d, dict) else str(s)
    except:
        return str(s)

# Load main features
df = pd.read_parquet('gs://f1optimizer-data-lake/ml_features/race_results_features.parquet')
print(f'Loaded: {len(df)} rows')

df = df[df['season'] >= 2000].copy()
print(f'After 2000+ filter: {len(df)} rows')

df['position'] = pd.to_numeric(df['position'], errors='coerce')
df['grid']     = pd.to_numeric(df['grid'], errors='coerce').fillna(0)
df = df.dropna(subset=['position', 'grid'])
df = df.sort_values(['season', 'round', 'grid']).reset_index(drop=True)

# Extract clean IDs
df['driverId']      = df['driver'].apply(lambda x: extract_id(x, 'driverId'))
df['constructorId'] = df['constructor'].apply(lambda x: extract_id(x, 'constructorId'))
print(f'Sample driverId: {df["driverId"].head(3).tolist()}')

# 3-class target
df['finish_tier'] = pd.cut(
    df['position'],
    bins=[0, 3, 10, 100],
    labels=['Podium', 'Points', 'Outside']
).astype(str)

print(f'\nFinish tier distribution:')
print(df['finish_tier'].value_counts())

# Championship points from race_results.parquet
print('\nLoading race results for championship features...')
rr = pd.read_parquet('gs://f1optimizer-data-lake/processed/race_results.parquet')
rr['points']   = pd.to_numeric(rr['points'], errors='coerce').fillna(0)
rr['position'] = pd.to_numeric(rr['position'], errors='coerce')
rr['driverId_rr']      = rr['Driver'].apply(lambda x: extract_id(x, 'driverId'))
rr['constructorId_rr'] = rr['Constructor'].apply(lambda x: extract_id(x, 'constructorId'))
rr = rr[rr['season'] >= 2000].sort_values(['season', 'round']).reset_index(drop=True)

print(f'Sample rr driverId: {rr["driverId_rr"].head(3).tolist()}')

# Cumulative points before each race — shift(1) per driver per season
rr['driver_cum_points'] = rr.groupby(['season', 'driverId_rr'])['points'].transform(
    lambda x: x.shift(1).cumsum().fillna(0)
)
rr['constructor_cum_points'] = rr.groupby(['season', 'constructorId_rr'])['points'].transform(
    lambda x: x.shift(1).cumsum().fillna(0)
)

# Championship position going into each race
rr['driver_champ_pos'] = rr.groupby(['season', 'round'])['driver_cum_points'].rank(
    ascending=False, method='min'
)
rr['constructor_champ_pos'] = rr.groupby(['season', 'round'])['constructor_cum_points'].rank(
    ascending=False, method='min'
)

# Points in last 3 races — form indicator
rr['driver_points_last3'] = rr.groupby(['season', 'driverId_rr'])['points'].transform(
    lambda x: x.shift(1).rolling(3, min_periods=1).sum()
).fillna(0)

rr_features = rr[['season', 'round', 'driverId_rr',
                   'driver_cum_points', 'driver_champ_pos',
                   'constructor_cum_points', 'constructor_champ_pos',
                   'driver_points_last3']].drop_duplicates(
    subset=['season', 'round', 'driverId_rr']
)

df = df.merge(
    rr_features,
    left_on=['season', 'round', 'driverId'],
    right_on=['season', 'round', 'driverId_rr'],
    how='left'
)
df['driver_cum_points']      = df['driver_cum_points'].fillna(0)
df['driver_champ_pos']       = df['driver_champ_pos'].fillna(10)
df['constructor_cum_points'] = df['constructor_cum_points'].fillna(0)
df['constructor_champ_pos']  = df['constructor_champ_pos'].fillna(10)
df['driver_points_last3']    = df['driver_points_last3'].fillna(0)
print(f'After championship merge: {len(df)} rows')
print(f'driver_cum_points non-zero: {(df["driver_cum_points"] > 0).sum()}')

# Rolling features — properly lagged
ROLLING_WINDOW = 10
df['driver_rolling_avg_finish'] = (
    df.groupby('driverId')['position']
    .transform(lambda s: s.shift(1).rolling(ROLLING_WINDOW, min_periods=1).mean())
    .fillna(10.0)
)
df['constructor_rolling_avg_finish'] = (
    df.groupby('constructorId')['position']
    .transform(lambda s: s.shift(1).rolling(ROLLING_WINDOW, min_periods=1).mean())
    .fillna(10.0)
)
df['driver_season_avg_finish'] = (
    df.groupby(['driverId', 'season'])['position']
    .transform(lambda s: s.shift(1).expanding().mean())
    .fillna(10.0)
)
df['driver_rolling_podiums'] = (
    df.groupby('driverId')['position']
    .transform(lambda s: (s.shift(1) <= 3).rolling(ROLLING_WINDOW, min_periods=1).mean())
    .fillna(0.0)
)
df['constructor_rolling_podiums'] = (
    df.groupby('constructorId')['position']
    .transform(lambda s: (s.shift(1) <= 3).rolling(ROLLING_WINDOW, min_periods=1).mean())
    .fillna(0.0)
)
df['driver_rolling_points_finishes'] = (
    df.groupby('driverId')['position']
    .transform(lambda s: (s.shift(1) <= 10).rolling(ROLLING_WINDOW, min_periods=1).mean())
    .fillna(0.0)
)
df['grid_last']        = df.groupby('driverId')['grid'].shift(1).fillna(10.0)
df['grid_improvement'] = df['grid_last'] - df['grid']

df = df.dropna(subset=['finish_tier'])
print(f'After feature engineering: {len(df)} rows')

# Temporal split
train = df[df['season'] <= 2021].copy()
val   = df[df['season'].between(2022, 2023)].copy()
test  = df[df['season'] == 2024].copy()
print(f'Train: {len(train)}, Val: {len(val)}, Test: {len(test)}')

# Fit encoders on train only
le_driver      = LabelEncoder()
le_constructor = LabelEncoder()

train['driver_enc']      = le_driver.fit_transform(train['driverId'])
train['constructor_enc'] = le_constructor.fit_transform(train['constructorId'])

def safe_encode(le, series):
    known = set(le.classes_)
    return series.apply(lambda v: le.transform([v])[0] if v in known else -1)

val['driver_enc']       = safe_encode(le_driver,      val['driverId'])
val['constructor_enc']  = safe_encode(le_constructor, val['constructorId'])
test['driver_enc']      = safe_encode(le_driver,      test['driverId'])
test['constructor_enc'] = safe_encode(le_constructor, test['constructorId'])

FEATURES = [
    'grid', 'grid_last', 'grid_improvement',
    'driver_enc', 'constructor_enc', 'circuitId_encoded', 'season',
    'driver_rolling_avg_finish', 'constructor_rolling_avg_finish',
    'driver_season_avg_finish',
    'driver_rolling_podiums', 'constructor_rolling_podiums',
    'driver_rolling_points_finishes',
    'driver_cum_points', 'driver_champ_pos',
    'constructor_cum_points', 'constructor_champ_pos',
    'driver_points_last3',
]

features = [f for f in FEATURES if f in train.columns]
print(f'Features: {len(features)} / {len(FEATURES)}')

X_train, y_train = train[features].fillna(0), train['finish_tier']
X_val,   y_val   = val[features].fillna(0),   val['finish_tier']
X_test,  y_test  = test[features].fillna(0),  test['finish_tier']

print(f'\nVal class distribution:')
print(pd.Series(y_val).value_counts())

print('\nTraining CatBoost...')
cat_model = CatBoostClassifier(
    iterations=1000, depth=6, learning_rate=0.01,
    l2_leaf_reg=3.0, random_seed=42,
    loss_function='MultiClass', eval_metric='Accuracy',
    early_stopping_rounds=50, verbose=False,
    class_weights={'Podium': 3, 'Points': 2, 'Outside': 1},
)
cat_model.fit(X_train, y_train, eval_set=(X_val, y_val))

print('Training LightGBM...')
lgb_model = LGBMClassifier(
    n_estimators=1000, max_depth=6, num_leaves=31,
    learning_rate=0.01, subsample=0.8, colsample_bytree=0.7,
    min_child_samples=20, reg_alpha=0.5, reg_lambda=1.0,
    random_state=42, n_jobs=-1, verbose=-1,
    class_weight='balanced',
)
lgb_model.fit(X_train, y_train, eval_set=[(X_val, y_val)])

print('\nFinding optimal ensemble weight...')
best_f1, best_w = 0, 0.5
classes     = cat_model.classes_
lgb_classes = lgb_model.classes_

for w in np.arange(0.1, 0.95, 0.05):
    cat_p = cat_model.predict_proba(X_val)
    lgb_p = lgb_model.predict_proba(X_val)
    lgb_aligned = np.zeros_like(cat_p)
    for i, c in enumerate(classes):
        if c in lgb_classes:
            lgb_aligned[:, i] = lgb_p[:, list(lgb_classes).index(c)]
    pred = classes[np.argmax(w * cat_p + (1 - w) * lgb_aligned, axis=1)]
    f1 = f1_score(y_val, pred, average='macro', zero_division=0)
    if f1 > best_f1:
        best_f1 = f1
        best_w  = round(w, 2)

print(f'Best weight: CatBoost={best_w}, LGB={round(1-best_w, 2)}')

def predict_ensemble(X):
    cat_p = cat_model.predict_proba(X)
    lgb_p = lgb_model.predict_proba(X)
    lgb_aligned = np.zeros_like(cat_p)
    for i, c in enumerate(classes):
        if c in lgb_classes:
            lgb_aligned[:, i] = lgb_p[:, list(lgb_classes).index(c)]
    return classes[np.argmax(best_w * cat_p + (1 - best_w) * lgb_aligned, axis=1)]

val_pred  = predict_ensemble(X_val)
test_pred = predict_ensemble(X_test)

print('\nRACE OUTCOME RESULTS')
print(f'Val  — Accuracy: {accuracy_score(y_val,  val_pred):.3f}, F1 macro: {f1_score(y_val,  val_pred,  average="macro", zero_division=0):.3f}')
print(f'Test — Accuracy: {accuracy_score(y_test, test_pred):.3f}, F1 macro: {f1_score(y_test, test_pred, average="macro", zero_division=0):.3f}')

print('\nIndividual models:')
print(f'  CatBoost — Val Acc: {accuracy_score(y_val, cat_model.predict(X_val)):.3f}, Test Acc: {accuracy_score(y_test, cat_model.predict(X_test)):.3f}')
print(f'  LGB      — Val Acc: {accuracy_score(y_val, lgb_model.predict(X_val)):.3f}, Test Acc: {accuracy_score(y_test, lgb_model.predict(X_test)):.3f}')

print('\nVal Classification Report:')
print(classification_report(y_val, val_pred, zero_division=0))

print('\nTop 10 features (LGB):')
for feat, imp in sorted(zip(features, lgb_model.feature_importances_), key=lambda x: -x[1])[:10]:
    print(f'  {feat}: {imp}')

os.makedirs('models', exist_ok=True)
joblib.dump({
    'cat': cat_model, 'lgb': lgb_model,
    'weight': best_w, 'features': features,
    'driver_encoder': le_driver,
    'constructor_encoder': le_constructor,
    'classes': list(classes),
    'rolling_window': ROLLING_WINDOW,
}, 'models/race_outcome.pkl')
print('\nSaved: models/race_outcome.pkl')