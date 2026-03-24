from __future__ import annotations
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from .base_model import BaseF1Model

class SafetyCarModel(BaseF1Model):
    model_name = "safety_car"

    def __init__(self):
        super().__init__()
        self._bundle = None

    def train(self, df: pd.DataFrame, **kwargs):
        raise NotImplementedError("Train via ml/training/train_safety_car.py")

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy().sort_values(['season', 'round', 'Driver', 'LapNumber']).reset_index(drop=True)
        df['lap_progress']    = df['LapNumber'] / df['total_laps']
        df['tyre_life_pct']   = df['TyreLife'] / df['total_laps'].clip(lower=1)
        df['soft_age']        = df['compound_SOFT']   * df['TyreLife']
        df['medium_age']      = df['compound_MEDIUM'] * df['TyreLife']
        df['hard_age']        = df['compound_HARD']   * df['TyreLife']
        df['pit_stops_so_far'] = (df['Stint'] - 1).clip(lower=0)
        df['tyre_delta_trend'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].transform(
            lambda x: x.rolling(5, min_periods=2).mean().shift(1)
        ).fillna(0)
        df['race_phase'] = pd.cut(
            df['lap_progress'], bins=[0, 0.33, 0.66, 1.0], labels=[0, 1, 2]
        ).astype(float)
        OPTIMAL_STINT = {'SOFT': 20, 'MEDIUM': 30, 'HARD': 45, 'INTERMEDIATE': 25, 'WET': 20}
        df['optimal_stint_len'] = df['Compound'].str.upper().map(OPTIMAL_STINT).fillna(30)
        df['laps_past_optimal'] = (df['TyreLife'] - df['optimal_stint_len']).clip(lower=0)
        return df

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        assert self._bundle, "Model not loaded"
        df      = self._engineer_features(df)
        feats   = self._bundle['features']
        X       = df[[f for f in feats if f in df.columns]].fillna(0)
        w       = self._bundle['pit_weight']
        lgb_p   = self._bundle['pit_lgb'].predict_proba(X)[:, 1]
        xgb_p   = self._bundle['pit_xgb'].predict_proba(X)[:, 1]
        proba   = w * lgb_p + (1 - w) * xgb_p
        preds   = (proba >= 0.5).astype(int)
        return pd.DataFrame({'prediction': preds, 'probability': proba}, index=df.index)

    def predict_circuit_sc_prob(self, circuit_name: str) -> float:
        return self._bundle['circuit_sc_prob'].get(circuit_name, 0.1)

    def evaluate(self, df: pd.DataFrame) -> dict:
        out = self.predict(df)
        return {
            'accuracy': float(accuracy_score(df['pitted_under_sc'], out['prediction'])),
            'f1_macro': float(f1_score(df['pitted_under_sc'], out['prediction'],
                                       average='macro', zero_division=0)),
        }

    def _save_native(self, local_dir: str):
        joblib.dump(self._bundle, os.path.join(local_dir, 'bundle.pkl'))

    def _load_native(self, local_dir: str):
        self._bundle = joblib.load(os.path.join(local_dir, 'bundle.pkl'))