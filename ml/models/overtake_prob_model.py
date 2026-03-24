from __future__ import annotations
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from .base_model import BaseF1Model

class OvertakeProbModel(BaseF1Model):
    model_name = "overtake_prob"

    def __init__(self):
        super().__init__()
        self._bundle = None

    def train(self, df: pd.DataFrame, **kwargs):
        raise NotImplementedError("Train via ml/training/train_overtake_prob.py")

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy().sort_values(['season', 'round', 'Driver', 'LapNumber']).reset_index(drop=True)
        df['tyre_squared']    = df['TyreLife'] ** 2
        df['tyre_cubed']      = df['TyreLife'] ** 3
        df['tyre_per_stint']  = df['TyreLife'] / (df['Stint'] + 1)
        df['lap_progress']    = df['LapNumber'] / df['total_laps']
        df['compound_age_soft']   = df['compound_SOFT']   * df['TyreLife']
        df['compound_age_medium'] = df['compound_MEDIUM'] * df['TyreLife']
        df['compound_age_hard']   = df['compound_HARD']   * df['TyreLife']
        for window in [3, 5, 7]:
            df[f'delta_roll{window}'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].transform(
                lambda x, w=window: x.rolling(w, min_periods=1).mean().shift(1)
            ).fillna(0)
        df['prev_delta']   = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].shift(1).fillna(0)
        df['prev_delta_2'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].shift(2).fillna(0)
        df['delta_diff']   = df['prev_delta'] - df['prev_delta_2']
        df['cum_throttle'] = df.groupby(['season', 'round', 'Driver'])['mean_throttle'].cumsum() / df['LapNumber']
        df['cum_brake']    = df.groupby(['season', 'round', 'Driver'])['mean_brake'].cumsum() / df['LapNumber']
        df['overtake_roll3'] = df.groupby(['season', 'round', 'Driver'])['overtake_success'].transform(
            lambda x: x.rolling(3, min_periods=1).mean().shift(1)
        ).fillna(0) if 'overtake_success' in df.columns else 0
        df['throttle_roll3'] = df.groupby(['season', 'round', 'Driver'])['mean_throttle'].transform(
            lambda x: x.rolling(3, min_periods=1).mean().shift(1)
        ).fillna(df['mean_throttle'])
        df['brake_roll3'] = df.groupby(['season', 'round', 'Driver'])['mean_brake'].transform(
            lambda x: x.rolling(3, min_periods=1).mean().shift(1)
        ).fillna(df['mean_brake'])
        df['drs_zone']        = (df['gap_ahead'].abs() < 1.0).astype(int)
        df['tyre_x_throttle'] = df['TyreLife'] * df['mean_throttle'] / 100
        df['tyre_x_brake']    = df['TyreLife'] * df['mean_brake']    / 100
        df['speed_roll3']     = df.groupby(['season', 'round', 'Driver'])['mean_speed'].transform(
            lambda x: x.rolling(3, min_periods=1).mean().shift(1)
        ).fillna(df['mean_speed'])
        df['speed_delta']     = df['mean_speed'] - df['speed_roll3']
        field_size            = df.groupby(['season', 'round'])['Driver'].transform('nunique')
        df['position_pct']    = df['position'] / field_size
        df['field_size']      = field_size
        # Cumulative race time gap
        df['cum_race_time']   = df.groupby(['season', 'round', 'Driver'])['LapTime'].cumsum()
        def compute_gaps(group):
            group = group.sort_values('cum_race_time')
            group['real_gap_ahead'] = group['cum_race_time'].diff().fillna(0)
            return group
        gap_df = df.groupby(['season', 'round', 'LapNumber'], group_keys=False).apply(compute_gaps)
        df['real_gap_ahead']  = gap_df['real_gap_ahead'].reindex(df.index).fillna(0).clip(-60, 60)
        df['in_drs_zone']     = (df['real_gap_ahead'].abs() < 1.0).astype(int)
        df['in_drs_zone_2']   = (df['real_gap_ahead'].abs() < 2.0).astype(int)
        df['driving_style_encoded'] = df['driving_style'] if df['driving_style'].dtype != object else \
            df['driving_style'].map({'NEUTRAL': 0, 'BALANCE': 1, 'PUSH': 2}).fillna(1)
        return df

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        assert self._bundle, "Model not loaded"
        df      = self._engineer_features(df)
        feats   = self._bundle['features']
        X       = df[[f for f in feats if f in df.columns]].fillna(0)
        proba   = self._bundle['model'].predict_proba(X)[:, 1]
        thresh  = self._bundle['threshold']
        preds   = (proba >= thresh).astype(int)
        return pd.DataFrame({'prediction': preds, 'probability': proba}, index=df.index)

    def evaluate(self, df: pd.DataFrame) -> dict:
        out = self.predict(df)
        return {
            'accuracy': float(accuracy_score(df['overtake_success'], out['prediction'])),
            'f1_macro': float(f1_score(df['overtake_success'], out['prediction'],
                                       average='macro', zero_division=0)),
        }

    def _save_native(self, local_dir: str):
        joblib.dump(self._bundle, os.path.join(local_dir, 'bundle.pkl'))

    def _load_native(self, local_dir: str):
        self._bundle = joblib.load(os.path.join(local_dir, 'bundle.pkl'))