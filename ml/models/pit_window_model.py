from __future__ import annotations
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, r2_score
from .base_model import BaseF1Model

class PitWindowModel(BaseF1Model):
    model_name = "pit_window"

    def __init__(self):
        super().__init__()
        self._bundle = None

    def train(self, df: pd.DataFrame, **kwargs):
        raise NotImplementedError("Train via ml/training/train_pit_window.py")

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy().sort_values(['season', 'round', 'Driver', 'LapNumber']).reset_index(drop=True)
        # Filter dry only
        dry = ['SOFT', 'MEDIUM', 'HARD', 'SUPERSOFT', 'ULTRASOFT', 'HYPERSOFT']
        df  = df[df['Compound'].str.upper().isin(dry)].copy()
        df['tyre_squared']         = df['TyreLife'] ** 2
        df['tyre_cubed']           = df['TyreLife'] ** 3
        df['tyre_per_stint']       = df['TyreLife'] / (df['Stint'] + 1)
        df['lap_progress']         = df['LapNumber'] / df['total_laps']
        df['throttle_brake_ratio'] = df['mean_throttle'] / (df['mean_brake'] + 1)
        df['pit_stops_so_far']     = (df['Stint'] - 1).clip(lower=0)
        df['compound_age_soft']    = df['compound_SOFT']   * df['TyreLife']
        df['compound_age_medium']  = df['compound_MEDIUM'] * df['TyreLife']
        df['compound_age_hard']    = df['compound_HARD']   * df['TyreLife']
        df['tyre_age_sq_soft']     = df['compound_SOFT']   * df['tyre_squared']
        df['tyre_age_sq_medium']   = df['compound_MEDIUM'] * df['tyre_squared']
        for window in [3, 5, 7]:
            df[f'deg_roll{window}'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].transform(
                lambda x, w=window: x.rolling(w, min_periods=1).mean().shift(1)
            ).fillna(0)
        df['prev_delta']   = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].shift(1).fillna(0)
        df['prev_delta_2'] = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].shift(2).fillna(0)
        df['delta_diff']   = df['prev_delta'] - df['prev_delta_2']
        df['delta_std3']   = df.groupby(['season', 'round', 'Driver'])['tyre_delta'].transform(
            lambda x: x.rolling(3, min_periods=1).std().shift(1)
        ).fillna(0)
        df['cum_throttle']    = df.groupby(['season', 'round', 'Driver'])['mean_throttle'].cumsum() / df['LapNumber']
        df['cum_brake']       = df.groupby(['season', 'round', 'Driver'])['mean_brake'].cumsum() / df['LapNumber']
        df['undercut_delta']  = df['deg_rate_roll3'] * df['TyreLife']
        df['is_in_traffic']   = (df['gap_ahead'] < 3.0).astype(int)
        df['deg_acceleration'] = df['deg_rate_roll3'] - df.groupby(
            ['season', 'round', 'Driver'])['deg_rate_roll3'].shift(3).fillna(0)
        df['cliff_approaching'] = (df['deg_acceleration'] > 0.05).astype(int)
        field_size             = df.groupby(['season', 'round'])['Driver'].transform('nunique')
        df['position_pct']     = df['position'] / field_size
        # Stint end lap and stint progress
        df['stint_end_lap']    = df.groupby(['season', 'round', 'Driver', 'Stint'])['LapNumber'].transform('max')
        df['stint_progress']   = df['TyreLife'] / (df['stint_end_lap'] - df.groupby(
            ['season', 'round', 'Driver', 'Stint'])['LapNumber'].transform('min') + 1).clip(lower=1)
        # Circuit features from bundle
        if self._bundle and 'circuit_avg_stops' in self._bundle:
            df['circuit_avg_stops'] = df['raceName'].map(self._bundle['circuit_avg_stops']).fillna(2.0)
        else:
            df['circuit_avg_stops'] = 2.0
        if self._bundle and 'compound_circuit_stint' in self._bundle:
            df['expected_stint_len'] = df.set_index(['raceName', 'Compound']).index.map(
                self._bundle['compound_circuit_stint']
            ).fillna(30)
        else:
            df['expected_stint_len'] = 30
        df['laps_until_optimal'] = (df['expected_stint_len'] - df['TyreLife']).clip(lower=0)
        df['total_planned_stops'] = df['circuit_avg_stops'].round().clip(1, 4)
        df['remaining_pit_stops'] = (df['total_planned_stops'] - df['pit_stops_so_far']).clip(lower=0)
        if self._bundle and 'circuit_encoder' in self._bundle:
            le = self._bundle['circuit_encoder']
            known = set(le.classes_)
            df['circuit_encoded'] = df['raceName'].apply(
                lambda v: le.transform([v])[0] if v in known else -1
            )
        else:
            df['circuit_encoded'] = -1
        df['driving_style_encoded'] = df['driving_style'] if df['driving_style'].dtype != object else \
            df['driving_style'].map({'NEUTRAL': 0, 'BALANCE': 1, 'PUSH': 2}).fillna(1)
        
        if 'Team' in df.columns:
            df['constructor_enc'] = self.get_constructor_enc(df['Team'])
        elif 'constructor_enc' not in df.columns:
            df['constructor_enc'] = -1
        
        return df

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        assert self._bundle, "Model not loaded"
        df          = self._engineer_features(df)
        feats       = self._bundle['features']
        num_feats   = self._bundle['num_features']
        scaler      = self._bundle['scaler']
        X           = df[[f for f in feats if f in df.columns]].fillna(0)
        for f in feats:
            if f not in X.columns:
                X[f] = 0
        X = X[feats].copy()
        overlap = [f for f in num_feats if f in X.columns]
        X[overlap] = scaler.transform(X[overlap])
        w    = self._bundle['weight']
        pred = np.expm1(w * self._bundle['xgb'].predict(X) + (1 - w) * self._bundle['lgb'].predict(X))
        return pd.DataFrame({'prediction': pred}, index=df.index)

    def evaluate(self, df: pd.DataFrame) -> dict:
        preds  = self.predict(df)['prediction']
        target = df.get('laps_in_stint_remaining', df.get('laps_to_pit'))
        return {
            'mae': float(mean_absolute_error(target, preds)),
            'r2':  float(r2_score(target, preds)),
        }

    def _save_native(self, local_dir: str):
        joblib.dump(self._bundle, os.path.join(local_dir, 'bundle.pkl'))

    def _load_native(self, local_dir: str):
        self._bundle = joblib.load(os.path.join(local_dir, 'bundle.pkl'))