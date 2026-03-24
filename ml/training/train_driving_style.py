"""
Driving Style Classifier - LGB+XGB Ensemble
Predicts PUSH/BALANCE/NEUTRAL per lap
Target is a composite aggression score normalized within season
Val F1=0.793 | Test F1=0.800
"""
import pandas as pd
import numpy as np
from sklearn.metrics import classification_report, accuracy_score, f1_score
from sklearn.preprocessing import LabelEncoder
from lightgbm import LGBMClassifier
from xgboost import XGBClassifier
import joblib
import os
from google.cloud import aiplatform

# Vertex AI Experiment Tracking
aiplatform.init(project='f1optimizer', location='us-central1', experiment='f1-strategy-models')

# Load data
df = pd.read_parquet('gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet')
print(f'Loaded: {len(df)} rows')
print(f'Seasons: {sorted(df["season"].unique())}')

# Encode driver
le_driver = LabelEncoder()
df['driver_encoded'] = le_driver.fit_transform(df['Driver'].astype(str))

df = df.sort_values(['season', 'round', 'Driver', 'LapNumber']).reset_index(drop=True)

# Composite aggression score normalized within season
for col in ['mean_throttle', 'std_throttle', 'mean_brake', 'mean_speed']:
    season_mean = df.groupby('season')[col].transform('mean')
    season_std  = df.groupby('season')[col].transform('std')
    df[f'{col}_norm'] = (df[col] - season_mean) / (season_std + 1e-8)

df['aggression_score'] = (
    0.5 * df['mean_throttle_norm'] +
    0.3 * df['mean_brake_norm'] +
    0.2 * df['std_throttle_norm']
)

p33 = df.groupby('season')['aggression_score'].transform(lambda x: x.quantile(0.33))
p66 = df.groupby('season')['aggression_score'].transform(lambda x: x.quantile(0.66))

df['style_label'] = 'BALANCE'
df.loc[df['aggression_score'] < p33, 'style_label'] = 'NEUTRAL'
df.loc[df['aggression_score'] > p66, 'style_label'] = 'PUSH'

print(f'\nLabel distribution:')
print(df['style_label'].value_counts())
print(df['style_label'].value_counts(normalize=True))

le_label = LabelEncoder()
df['style_encoded'] = le_label.fit_transform(df['style_label'])

# Rolling features
df['throttle_roll3'] = df.groupby(['season', 'round', 'Driver'])['mean_throttle'].transform(
    lambda x: x.rolling(3, min_periods=1).mean().shift(1)
).fillna(df['mean_throttle'])

df['brake_roll3'] = df.groupby(['season', 'round', 'Driver'])['mean_brake'].transform(
    lambda x: x.rolling(3, min_periods=1).mean().shift(1)
).fillna(df['mean_brake'])

df['prev_style'] = df.groupby(['season', 'round', 'Driver'])['style_encoded'].shift(1).fillna(1)

df['tyre_delta_roll3'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].transform(
    lambda x: x.rolling(3, min_periods=1).mean().shift(1)
).fillna(0)

df['lap_progress'] = df['LapNumber'] / df['total_laps']

df = df.dropna(subset=['style_encoded', 'mean_throttle', 'mean_brake'])
print(f'\nAfter feature engineering: {len(df)} rows')

FEATURES = [
    # Race context
    'LapNumber', 'total_laps', 'laps_remaining', 'fuel_load_pct', 'lap_progress',
    # Speed
    'mean_speed', 'max_speed',
    'SpeedI1', 'SpeedI2', 'SpeedFL', 'SpeedST',
    # Sector times
    'Sector1Time', 'Sector2Time', 'Sector3Time',
    # Brake only (not throttle - that defines the label)
    'mean_brake', 'std_brake', 'brake_roll3',
    # Tire state
    'TyreLife', 'Stint', 'FreshTyre',
    'compound_SOFT', 'compound_MEDIUM', 'compound_HARD',
    # Lap time context
    'lap_time_delta', 'deg_rate_roll3', 'tyre_delta_roll3',
    # Position
    'position', 'gap_ahead',
    # Rolling throttle (lagged — no leakage)
    'throttle_roll3',
    # Previous style
    'prev_style',
    # New telemetry features (2022+)
    'mean_rpm', 'max_rpm', 'mean_gear', 'drs_usage_pct',
]

features = [f for f in FEATURES if f in df.columns]
print(f'Features: {len(features)} / {len(FEATURES)}')

# Temporal split
train = df[df['season'] <= 2021]
val   = df[(df['season'] >= 2022) & (df['season'] <= 2023)]
test  = df[df['season'] == 2024]
print(f'Train: {len(train)}, Val: {len(val)}, Test: {len(test)}')

X_train, y_train = train[features].fillna(0), train['style_encoded']
X_val,   y_val   = val[features].fillna(0),   val['style_encoded']
X_test,  y_test  = test[features].fillna(0),  test['style_encoded']

# Hyperparameters
LGB_PARAMS = dict(
    n_estimators=1500, max_depth=8, num_leaves=63,
    learning_rate=0.008, subsample=0.7, colsample_bytree=0.6,
    min_child_samples=30, reg_alpha=0.5, reg_lambda=2.0,
    random_state=42, n_jobs=-1, verbose=-1, class_weight='balanced'
)
XGB_PARAMS = dict(
    n_estimators=1000, max_depth=7, learning_rate=0.01,
    subsample=0.7, colsample_bytree=0.6, min_child_weight=30,
    reg_alpha=0.5, reg_lambda=2.0, random_state=42,
    tree_method='hist', early_stopping_rounds=100,
    verbosity=0, eval_metric='mlogloss'
)

# Train and track experiment
with aiplatform.start_run(run='driving-style-v1'):
    aiplatform.log_params({
        'model': 'LGB+XGB ensemble',
        'lgb_n_estimators': LGB_PARAMS['n_estimators'],
        'lgb_max_depth': LGB_PARAMS['max_depth'],
        'xgb_n_estimators': XGB_PARAMS['n_estimators'],
        'xgb_max_depth': XGB_PARAMS['max_depth'],
        'learning_rate': LGB_PARAMS['learning_rate'],
        'classes': 'PUSH/BALANCE/NEUTRAL',
        'train_seasons': '2018-2021',
        'n_features': len(features),
        'train_rows': len(train),
    })

    print('\nTraining LightGBM...')
    lgb = LGBMClassifier(**LGB_PARAMS)
    lgb.fit(X_train, y_train, eval_set=[(X_val, y_val)])

    print('Training XGBoost...')
    xgb = XGBClassifier(**XGB_PARAMS)
    xgb.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

    # Find optimal ensemble weight
    print('\nFinding optimal ensemble weight...')
    best_f1 = 0
    best_w  = 0.5
    for w in np.arange(0.1, 0.95, 0.05):
        lgb_proba = lgb.predict_proba(X_val)
        xgb_proba = xgb.predict_proba(X_val)
        combined  = w * lgb_proba + (1 - w) * xgb_proba
        pred      = np.argmax(combined, axis=1)
        f1 = f1_score(y_val, pred, average='macro')
        if f1 > best_f1:
            best_f1 = f1
            best_w  = round(w, 2)

    print(f'Best weight: LGB={best_w}, XGB={round(1-best_w, 2)}')

    lgb_proba  = lgb.predict_proba(X_val)
    xgb_proba  = xgb.predict_proba(X_val)
    val_pred   = np.argmax(best_w * lgb_proba + (1 - best_w) * xgb_proba, axis=1)

    lgb_proba_t  = lgb.predict_proba(X_test)
    xgb_proba_t  = xgb.predict_proba(X_test)
    test_pred    = np.argmax(best_w * lgb_proba_t + (1 - best_w) * xgb_proba_t, axis=1)

    val_acc  = float(accuracy_score(y_val,  val_pred))
    val_f1   = float(f1_score(y_val,  val_pred, average='macro'))
    test_acc = float(accuracy_score(y_test, test_pred))
    test_f1  = float(f1_score(y_test, test_pred, average='macro'))

    print('\nDRIVING STYLE RESULTS')
    print(f'Val  — Accuracy: {val_acc:.3f}, F1 macro: {val_f1:.3f}')
    print(f'Test — Accuracy: {test_acc:.3f}, F1 macro: {test_f1:.3f}')

    print('\nVal Classification Report:')
    print(classification_report(y_val, val_pred, target_names=le_label.classes_))

    print('\nTop 15 Features (LGB):')
    for feat, imp in sorted(zip(features, lgb.feature_importances_), key=lambda x: -x[1])[:15]:
        print(f'  {feat}: {imp}')

    # Log metrics
    aiplatform.log_metrics({
        'val_accuracy': val_acc, 'val_f1_macro': val_f1,
        'test_accuracy': test_acc, 'test_f1_macro': test_f1,
        'ensemble_weight_lgb': best_w,
    })

# Save
os.makedirs('models', exist_ok=True)
joblib.dump({
    'lgb': lgb, 'xgb': xgb,
    'weight': best_w,
    'features': features,
    'driver_encoder': le_driver,
    'label_encoder': le_label,
}, 'models/driving_style.pkl')
print('\nSaved: models/driving_style.pkl')