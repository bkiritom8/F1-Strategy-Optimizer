from __future__ import annotations
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from .base_model import BaseF1Model

class DrivingStyleModel(BaseF1Model):
    model_name = "driving_style"

    def __init__(self):
        super().__init__()
        self._bundle = None

    def train(self, df: pd.DataFrame, **kwargs):
        raise NotImplementedError("Train via ml/training/train_driving_style.py")

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy().sort_values(['season', 'round', 'Driver', 'LapNumber']).reset_index(drop=True)
        df['lap_progress']    = df['LapNumber'] / df['total_laps']
        df['throttle_roll3']  = df.groupby(['season', 'round', 'Driver'])['mean_throttle'].transform(
            lambda x: x.rolling(3, min_periods=1).mean().shift(1)
        ).fillna(df['mean_throttle'])
        df['brake_roll3']     = df.groupby(['season', 'round', 'Driver'])['mean_brake'].transform(
            lambda x: x.rolling(3, min_periods=1).mean().shift(1)
        ).fillna(df['mean_brake'])
        df['tyre_delta_roll3'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].transform(
            lambda x: x.rolling(3, min_periods=1).mean().shift(1)
        ).fillna(0)
        if 'driving_style' in df.columns and df['driving_style'].dtype != object:
            df['prev_style'] = df.groupby(['season', 'round', 'Driver'])['driving_style'].shift(1).fillna(1)
        else:
            df['prev_style'] = 1
        return df

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        assert self._bundle, "Model not loaded"
        df      = self._engineer_features(df)
        feats   = self._bundle['features']
        le      = self._bundle['label_encoder']
        X       = df[[f for f in feats if f in df.columns]].fillna(0)
        w       = self._bundle['weight']
        lgb_p   = self._bundle['lgb'].predict_proba(X)
        xgb_p   = self._bundle['xgb'].predict_proba(X)
        combined = w * lgb_p + (1 - w) * xgb_p
        encoded  = np.argmax(combined, axis=1)
        preds    = le.inverse_transform(encoded)
        return pd.DataFrame({'prediction': preds}, index=df.index)

    def evaluate(self, df: pd.DataFrame) -> dict:
        out = self.predict(df)
        return {
            'accuracy': float(accuracy_score(df['driving_style'], out['prediction'])),
            'f1_macro': float(f1_score(df['driving_style'], out['prediction'],
                                       average='macro', zero_division=0)),
        }

    def _save_native(self, local_dir: str):
        joblib.dump(self._bundle, os.path.join(local_dir, 'bundle.pkl'))

    def _load_native(self, local_dir: str):
        self._bundle = joblib.load(os.path.join(local_dir, 'bundle.pkl'))