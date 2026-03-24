from __future__ import annotations
import ast
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sklearn.preprocessing import LabelEncoder
from .base_model import BaseF1Model

class RaceOutcomeModel(BaseF1Model):
    model_name = "race_outcome"

    def __init__(self):
        super().__init__()
        self._bundle = None

    def train(self, df: pd.DataFrame, **kwargs):
        raise NotImplementedError("Train via ml/training/train_race_outcome.py")

    @staticmethod
    def _extract_id(s, key):
        try:
            d = ast.literal_eval(str(s))
            return d[key] if isinstance(d, dict) else str(s)
        except:
            return str(s)

    def _engineer_features(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df['driverId']      = df['driver'].apply(lambda x: self._extract_id(x, 'driverId'))
        df['constructorId'] = df['constructor'].apply(lambda x: self._extract_id(x, 'constructorId'))
        df['position']      = pd.to_numeric(df['position'], errors='coerce')
        df['grid']          = pd.to_numeric(df['grid'], errors='coerce').fillna(0)
        df = df.sort_values(['season', 'round', 'grid']).reset_index(drop=True)

        ROLLING_WINDOW = self._bundle.get('rolling_window', 10) if self._bundle else 10
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

        if self._bundle:
            le_d = self._bundle['driver_encoder']
            le_c = self._bundle['constructor_encoder']
            known_d = set(le_d.classes_)
            known_c = set(le_c.classes_)
            df['driver_enc']      = df['driverId'].apply(
                lambda v: le_d.transform([v])[0] if v in known_d else -1
            )
            df['constructor_enc'] = df['constructorId'].apply(
                lambda v: le_c.transform([v])[0] if v in known_c else -1
            )
        return df

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        assert self._bundle, "Model not loaded"
        df      = self._engineer_features(df)
        feats   = self._bundle['features']
        classes = np.array(self._bundle['classes'])
        lgb_cls = self._bundle['lgb'].classes_
        X       = df[[f for f in feats if f in df.columns]].fillna(0)
        for f in feats:
            if f not in X.columns:
                X[f] = 0
        X = X[feats]
        w       = self._bundle['weight']
        cat_p   = self._bundle['cat'].predict_proba(X)
        lgb_p   = self._bundle['lgb'].predict_proba(X)
        lgb_aligned = np.zeros_like(cat_p)
        for i, c in enumerate(classes):
            if c in lgb_cls:
                lgb_aligned[:, i] = lgb_p[:, list(lgb_cls).index(c)]
        combined = w * cat_p + (1 - w) * lgb_aligned
        preds    = classes[np.argmax(combined, axis=1)]
        out      = pd.DataFrame(combined, columns=classes, index=df.index)
        out['prediction'] = preds
        return out

    def evaluate(self, df: pd.DataFrame) -> dict:
        out = self.predict(df)
        return {
            'accuracy': float(accuracy_score(df['finish_tier'], out['prediction'])),
            'f1_macro': float(f1_score(df['finish_tier'], out['prediction'],
                                       average='macro', zero_division=0)),
        }

    def _save_native(self, local_dir: str):
        joblib.dump(self._bundle, os.path.join(local_dir, 'bundle.pkl'))

    def _load_native(self, local_dir: str):
        self._bundle = joblib.load(os.path.join(local_dir, 'bundle.pkl'))