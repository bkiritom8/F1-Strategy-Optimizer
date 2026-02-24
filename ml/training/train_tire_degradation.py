"""
Tire Degradation Model - XGBoost + LightGBM Ensemble
Predicts lap time based on tire life, fuel, and conditions.
"""

import pandas as pd
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor
import joblib
import os

DATA_PATH = "data/processed/fastf1_features.csv"
MODEL_DIR = "ml/models/artifacts"
os.makedirs(MODEL_DIR, exist_ok=True)

FEATURES = [
    # Tire features
    'TyreLife', 'compound_SOFT', 'compound_MEDIUM', 'compound_HARD',
    'compound_INTERMEDIATE', 'compound_WET',
    # Fuel features
    'fuel_load_pct', 'laps_remaining',
    # Speed features (from speed traps, not sector times)
    'SpeedI1', 'SpeedI2', 'SpeedFL', 'SpeedST',
    'mean_speed', 'max_speed',
    # Driving features
    'mean_throttle', 'std_throttle', 'mean_brake', 'std_brake',
    # Race context
    'LapNumber', 'Stint', 'total_laps', 'position',
    'is_sc_lap',
    # Track/season (encoded)
    'season', 'round', 'driver_encoded'
]
TARGET = 'LapTime'


def load_data():
    print("Loading data...")
    df = pd.read_csv(DATA_PATH)
    
    # Encode driver
    le = LabelEncoder()
    df['driver_encoded'] = le.fit_transform(df['Driver'].astype(str))
    
    # Filter out outliers (keep SC laps but mark them)
    df = df[df['is_pit_lap'] == 0]
    df = df[df['LapTime'].between(60, 180)]  # Allow SC laps (slower)
    df = df[df['TyreLife'] >= 1]
    df = df.dropna(subset=[TARGET])
    
    print(f"  Loaded: {len(df)} rows")
    print(f"  SC laps: {df['is_sc_lap'].sum()} ({df['is_sc_lap'].mean()*100:.1f}%)")
    print(f"  LapTime range: {df[TARGET].min():.1f}s - {df[TARGET].max():.1f}s")
    return df, le


def split_data(df):
    train = df[df['season'] <= 2021]
    val = df[df['season'] == 2022]
    test = df[df['season'] == 2024]
    print(f"  Train: {len(train)}, Val: {len(val)}, Test: {len(test)}")
    return train, val, test


def train(train_df, val_df):
    features = [f for f in FEATURES if f in train_df.columns]
    print(f"  Features ({len(features)}): {features}")
    
    X_train = train_df[features].fillna(0)
    y_train = train_df[TARGET]
    X_val = val_df[features].fillna(0)
    y_val = val_df[TARGET]
    
    print("Training XGBoost...")
    xgb = XGBRegressor(
        n_estimators=800,
        max_depth=10,
        learning_rate=0.015,
        subsample=0.85,
        colsample_bytree=0.75,
        min_child_weight=5,
        reg_alpha=0.3,
        reg_lambda=1.5,
        gamma=0.1,
        random_state=42,
        tree_method='hist',
        early_stopping_rounds=50
    )
    xgb.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    
    print("Training LightGBM...")
    lgb = LGBMRegressor(
        n_estimators=800,
        max_depth=10,
        learning_rate=0.015,
        subsample=0.85,
        colsample_bytree=0.75,
        min_child_samples=20,
        reg_alpha=0.3,
        reg_lambda=1.5,
        random_state=42,
        verbose=-1
    )
    lgb.fit(X_train, y_train, eval_set=[(X_val, y_val)])
    
    # Find optimal ensemble weight
    best_weight = 0.5
    best_mae = float('inf')
    for w in np.arange(0.1, 0.91, 0.05):
        pred = w * xgb.predict(X_val) + (1 - w) * lgb.predict(X_val)
        mae = mean_absolute_error(y_val, pred)
        if mae < best_mae:
            best_mae = mae
            best_weight = round(w, 2)
    
    ensemble_pred = best_weight * xgb.predict(X_val) + (1 - best_weight) * lgb.predict(X_val)
    
    mae = mean_absolute_error(y_val, ensemble_pred)
    rmse = np.sqrt(mean_squared_error(y_val, ensemble_pred))
    r2 = r2_score(y_val, ensemble_pred)
    
    print(f"Validation - MAE: {mae:.3f}s, RMSE: {rmse:.3f}s, R2: {r2:.4f}")
    print(f"  Best ensemble weight (XGB): {best_weight}")
    
    print("Feature importance (top 10):")
    importance = sorted(zip(features, xgb.feature_importances_), key=lambda x: -x[1])[:10]
    for feat, imp in importance:
        print(f"    {feat}: {imp:.4f}")
    
    return {
        'xgb': xgb, 
        'lgb': lgb, 
        'ensemble_weight': best_weight,
        'features': features,
        'val_metrics': {'mae': mae, 'rmse': rmse, 'r2': r2}
    }


def evaluate(model_dict, test_df):
    features = model_dict['features']
    w = model_dict['ensemble_weight']
    
    X_test = test_df[features].fillna(0)
    y_test = test_df[TARGET]
    
    xgb_pred = model_dict['xgb'].predict(X_test)
    lgb_pred = model_dict['lgb'].predict(X_test)
    ensemble_pred = w * xgb_pred + (1 - w) * lgb_pred
    
    mae = mean_absolute_error(y_test, ensemble_pred)
    rmse = np.sqrt(mean_squared_error(y_test, ensemble_pred))
    r2 = r2_score(y_test, ensemble_pred)
    
    print(f"Test - MAE: {mae:.3f}s, RMSE: {rmse:.3f}s, R2: {r2:.4f}")
    
    # Breakdown by SC vs normal laps
    normal_mask = test_df['is_sc_lap'] == 0
    if normal_mask.sum() > 0:
        normal_mae = mean_absolute_error(y_test[normal_mask], ensemble_pred[normal_mask])
        print(f"  Normal laps MAE: {normal_mae:.3f}s")
    
    sc_mask = test_df['is_sc_lap'] == 1
    if sc_mask.sum() > 0:
        sc_mae = mean_absolute_error(y_test[sc_mask], ensemble_pred[sc_mask])
        print(f"  SC laps MAE: {sc_mae:.3f}s")
    
    # Sample predictions
    print("\nSample predictions vs actual:")
    sample_idx = test_df.head(5).index
    sample_pred = ensemble_pred[:5]
    sample_actual = y_test.iloc[:5].values
    for pred, actual in zip(sample_pred, sample_actual):
        print(f"    Predicted: {pred:.2f}s, Actual: {actual:.2f}s, Error: {pred-actual:+.2f}s")
    
    return {'mae': mae, 'rmse': rmse, 'r2': r2}


def main():
    df, driver_encoder = load_data()
    train_df, val_df, test_df = split_data(df)
    
    model_dict = train(train_df, val_df)
    model_dict['test_metrics'] = evaluate(model_dict, test_df)
    model_dict['driver_encoder'] = driver_encoder
    
    joblib.dump(model_dict, f"{MODEL_DIR}/tire_degradation.pkl")
    print(f"Saved: {MODEL_DIR}/tire_degradation.pkl")


if __name__ == "__main__":
    main()