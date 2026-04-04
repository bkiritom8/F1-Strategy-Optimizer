from __future__ import annotations
import os
import joblib
import pandas as pd
import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score
from .base_model import BaseF1Model

class TireDegradationModel(BaseF1Model):
    model_name = "tire_degradation"

    def __init__(self):
        super().__init__()
        self._bundle = None

    def train(self, df: pd.DataFrame, **kwargs):
        raise NotImplementedError("Train via ml/training/train_tire_degradation.py")

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy().sort_values(['season', 'round', 'Driver', 'LapNumber']).reset_index(drop=True)
        df['tyre_fuel_interaction'] = df['TyreLife'] * df['fuel_load_pct']
        df['tyre_squared']          = df['TyreLife'] ** 2
        df['tyre_cubed']            = df['TyreLife'] ** 3
        df['lap_progress']          = df['LapNumber'] / df['total_laps']
        df['tyre_per_stint']        = df['TyreLife'] / (df['Stint'] + 1)
        df['throttle_brake_ratio']  = df['mean_throttle'] / (df['mean_brake'] + 1)
        df['tyre_x_throttle']       = df['TyreLife'] * df['mean_throttle'] / 100
        df['tyre_x_brake']          = df['TyreLife'] * df['mean_brake'] / 100
        df['fuel_x_throttle']       = df['fuel_load_pct'] * df['mean_throttle']
        df['compound_age_soft']     = df['compound_SOFT']   * df['TyreLife']
        df['compound_age_medium']   = df['compound_MEDIUM'] * df['TyreLife']
        df['compound_age_hard']     = df['compound_HARD']   * df['TyreLife']
        df['tyre_age_sq_soft']      = df['compound_SOFT']   * df['tyre_squared']
        df['tyre_age_sq_medium']    = df['compound_MEDIUM'] * df['tyre_squared']
        for window in [3, 5, 7]:
            df[f'delta_roll{window}'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].transform(
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
        df['position_prev']   = df.groupby(['season', 'round', 'Driver'])['position'].shift(1).fillna(df['position'])
        df['position_change'] = df['position'] - df['position_prev']

        if 'Team' in df.columns:
            df['constructor_enc'] = self.get_constructor_enc(df['Team'])
        elif 'constructor_enc' not in df.columns:
            df['constructor_enc'] = -1
        return df

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        assert self._bundle, "Model not loaded"
        df    = self._engineer_features(df)
        feats = self._bundle['features']
        X     = df[[f for f in feats if f in df.columns]].fillna(0)
        w     = self._bundle['weight']
        preds = w * self._bundle['lgb'].predict(X) + (1 - w) * self._bundle['xgb'].predict(X)
        return pd.DataFrame({'prediction': preds}, index=df.index)

    def evaluate(self, df: pd.DataFrame) -> dict:
        preds = self.predict(df)['prediction']
        return {
            'mae': float(mean_absolute_error(df['tyre_delta'], preds)),
            'r2':  float(r2_score(df['tyre_delta'], preds)),
        }

    def _save_native(self, local_dir: str):
        joblib.dump(self._bundle, os.path.join(local_dir, 'bundle.pkl'))

    def _load_native(self, local_dir: str):
        self._bundle = joblib.load(os.path.join(local_dir, 'bundle.pkl'))