"""
Strategy Predictor — XGBoost + LightGBM ensemble.

Predicts optimal race strategy:
  - Tire compound sequence
  - Pit stop windows (earliest / latest / optimal lap)
  - Expected lap time given strategy

Input features (per lap):
    lap_time_ms, tire_compound, tire_age_laps, gap_to_car_ahead_ms,
    gap_to_leader_ms, position, fuel_load_pct, pit_stop_flag,
    compound_SOFT, compound_MEDIUM, compound_HARD, compound_INTER,
    compound_WET, year, circuit_id (encoded)

Target:
    strategy_score — composite of position gained, time lost in pits,
                     and race finish position (lower = better strategy)

Supports:
  - Distributed training via data sharding (DataParallelStrategy)
  - Hyperparameter tuning via Vertex AI Vizier
  - SHAP explanations for strategy decisions

Run as a Vertex AI Custom Training Job.
Entry point: python -m ml.models.strategy_predictor --mode train ...
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder

from ml.models.base_model import BaseF1Model

logger = logging.getLogger(__name__)

# ── Feature / target definitions ──────────────────────────────────────────────

FEATURE_COLS = [
    "tire_age_laps",
    "gap_to_car_ahead_ms",
    "gap_to_leader_ms",
    "position",
    "lap_number",
    "compound_SOFT",
    "compound_MEDIUM",
    "compound_HARD",
    "compound_INTER",
    "compound_WET",
    "lap_time_delta",
    "gap_delta",
    "circuit_id_enc",
    "year",
]

TARGET_COL = "strategy_score"

DEFAULT_XGB_PARAMS: dict[str, Any] = {
    "n_estimators": 500,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "tree_method": "gpu_hist",  # uses T4 GPU if available
    "eval_metric": "mae",
    "random_state": 42,
}

DEFAULT_LGB_PARAMS: dict[str, Any] = {
    "n_estimators": 500,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "device": "gpu",
    "metric": "mae",
    "random_state": 42,
    "verbose": -1,
}


class StrategyPredictor(BaseF1Model):
    """XGBoost + LightGBM ensemble for race strategy prediction."""

    model_name = "strategy_predictor"

    def __init__(
        self,
        xgb_params: dict[str, Any] | None = None,
        lgb_params: dict[str, Any] | None = None,
        ensemble_weight_xgb: float = 0.5,
    ) -> None:
        super().__init__()
        self.xgb_params = xgb_params or DEFAULT_XGB_PARAMS
        self.lgb_params = lgb_params or DEFAULT_LGB_PARAMS
        self.ensemble_weight_xgb = ensemble_weight_xgb

        self._xgb_model: xgb.XGBRegressor | None = None
        self._lgb_model: lgb.LGBMRegressor | None = None
        self._label_encoder = LabelEncoder()
        self._feature_cols: list[str] = FEATURE_COLS

    # ── Data preparation ──────────────────────────────────────────────────────

    def _prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        # Encode circuit_id
        if "circuit_id" in df.columns:
            df["circuit_id_enc"] = self._label_encoder.fit_transform(
                df["circuit_id"].astype(str)
            )
        else:
            df["circuit_id_enc"] = 0

        # Compute strategy_score if not present
        if TARGET_COL not in df.columns and "position" in df.columns:
            df[TARGET_COL] = (
                df["position"].astype(float)
                + df.get("lap_time_delta", pd.Series(0, index=df.index)) / 1000.0
            )

        # Fill missing one-hot compound columns
        for col in [
            "compound_SOFT",
            "compound_MEDIUM",
            "compound_HARD",
            "compound_INTER",
            "compound_WET",
        ]:
            if col not in df.columns:
                df[col] = 0

        # Fill missing derived columns
        for col in ["lap_time_delta", "gap_delta"]:
            if col not in df.columns:
                df[col] = 0.0

        return df

    def _features(self, df: pd.DataFrame) -> pd.DataFrame:
        available = [c for c in self._feature_cols if c in df.columns]
        return df[available].fillna(0)

    # ── BaseF1Model interface ─────────────────────────────────────────────────

    def train(self, df: pd.DataFrame, **kwargs: Any) -> dict[str, float]:
        self.logger.info("StrategyPredictor: training on %d rows", len(df))
        self._publish("model_train", "starting", f"rows={len(df)}")

        df = self._prepare(df)
        X = self._features(df)
        y = df[TARGET_COL]

        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.15, random_state=42
        )

        # XGBoost
        self._xgb_model = xgb.XGBRegressor(**self.xgb_params)
        self._xgb_model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
            verbose=50,
        )

        # LightGBM
        self._lgb_model = lgb.LGBMRegressor(**self.lgb_params)
        self._lgb_model.fit(
            X_train,
            y_train,
            eval_set=[(X_val, y_val)],
        )

        val_pred = self._ensemble_predict(X_val)
        metrics = {
            "val_mae": float(mean_absolute_error(y_val, val_pred)),
            "val_rmse": float(np.sqrt(mean_squared_error(y_val, val_pred))),
            "val_r2": float(r2_score(y_val, val_pred)),
            "val_loss": float(mean_absolute_error(y_val, val_pred)),
            "train_rows": len(X_train),
            "val_rows": len(X_val),
        }
        self._train_metrics = metrics
        self._trained = True

        self.logger.info("StrategyPredictor: train complete %s", metrics)
        self._publish("model_train", "complete", f"val_mae={metrics['val_mae']:.4f}")
        return metrics

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self._trained:
            raise RuntimeError("Model not trained. Call train() or load() first.")
        df = self._prepare(df)
        X = self._features(df)
        predictions = self._ensemble_predict(X)
        out = df.copy()
        out["strategy_score_pred"] = predictions
        return out

    def evaluate(self, df: pd.DataFrame) -> dict[str, float]:
        df = self._prepare(df)
        X = self._features(df)
        y = df[TARGET_COL]
        preds = self._ensemble_predict(X)
        return {
            "val_mae": float(mean_absolute_error(y, preds)),
            "val_rmse": float(np.sqrt(mean_squared_error(y, preds))),
            "val_r2": float(r2_score(y, preds)),
            "val_loss": float(mean_absolute_error(y, preds)),
            "n_samples": len(df),
        }

    def feature_importance(self) -> pd.DataFrame:
        """Return a DataFrame of feature importances from both models."""
        rows = []
        if self._xgb_model is not None:
            scores = self._xgb_model.feature_importances_
            for feat, score in zip(self._feature_cols, scores):
                rows.append({"model": "xgb", "feature": feat, "importance": score})
        if self._lgb_model is not None:
            scores = self._lgb_model.feature_importances_
            for feat, score in zip(self._feature_cols, scores):
                rows.append({"model": "lgb", "feature": feat, "importance": score})
        return pd.DataFrame(rows).sort_values("importance", ascending=False)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _ensemble_predict(self, X: pd.DataFrame) -> np.ndarray:
        w = self.ensemble_weight_xgb
        xgb_pred = self._xgb_model.predict(X) if self._xgb_model else np.zeros(len(X))
        lgb_pred = self._lgb_model.predict(X) if self._lgb_model else np.zeros(len(X))
        return w * xgb_pred + (1 - w) * lgb_pred

    # ── Native save / load ────────────────────────────────────────────────────

    def _save_native(self, local_dir: str) -> None:
        if self._xgb_model:
            self._xgb_model.save_model(os.path.join(local_dir, "xgb_model.json"))
        if self._lgb_model:
            self._lgb_model.booster_.save_model(
                os.path.join(local_dir, "lgb_model.txt")
            )
        config = {
            "xgb_params": self.xgb_params,
            "lgb_params": self.lgb_params,
            "ensemble_weight_xgb": self.ensemble_weight_xgb,
            "feature_cols": self._feature_cols,
            "label_encoder_classes": (
                self._label_encoder.classes_.tolist()
                if hasattr(self._label_encoder, "classes_")
                else []
            ),
        }
        with open(os.path.join(local_dir, "config.json"), "w") as f:
            json.dump(config, f, indent=2)

    def _load_native(self, local_dir: str) -> None:
        xgb_path = os.path.join(local_dir, "xgb_model.json")
        lgb_path = os.path.join(local_dir, "lgb_model.txt")
        cfg_path = os.path.join(local_dir, "config.json")

        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                config = json.load(f)
            self.xgb_params = config.get("xgb_params", self.xgb_params)
            self.lgb_params = config.get("lgb_params", self.lgb_params)
            self.ensemble_weight_xgb = config.get("ensemble_weight_xgb", 0.5)
            self._feature_cols = config.get("feature_cols", FEATURE_COLS)
            classes = config.get("label_encoder_classes", [])
            if classes:
                self._label_encoder.classes_ = np.array(classes)

        if os.path.exists(xgb_path):
            self._xgb_model = xgb.XGBRegressor()
            self._xgb_model.load_model(xgb_path)

        if os.path.exists(lgb_path):
            self._lgb_model = lgb.LGBMRegressor()
            self._lgb_model._Booster = lgb.Booster(model_file=lgb_path)

        self._trained = True


# ── Vertex AI entry point ─────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["train", "predict"], default="train")
    p.add_argument("--feature-uri", required=True)
    p.add_argument("--checkpoint-uri", required=True)
    p.add_argument("--run-id", default="local")
    return p.parse_args()


def _train_entrypoint(args: argparse.Namespace) -> None:
    from ml.distributed.data_sharding import DataSharding

    worker_index = int(os.environ.get("CLUSTER_SPEC_TASK_INDEX", 0))
    num_workers = int(os.environ.get("CLUSTER_SPEC_NUM_WORKERS", 1))

    if num_workers > 1:
        sharding = DataSharding(num_workers=num_workers)
        df = sharding.load_shard_from_gcs(worker_index)
    else:
        df = pd.read_parquet(args.feature_uri)

    model = StrategyPredictor()
    metrics = model.train(df)
    logger.info("Training metrics: %s", metrics)

    checkpoint_uri = args.checkpoint_uri.rstrip("/") + f"/worker_{worker_index}/"
    model.save(checkpoint_uri)

    # Write checkpoint manifest for aggregator
    from google.cloud import storage as gcs

    bucket_name, prefix = checkpoint_uri.lstrip("gs://").split("/", 1)
    manifest = {
        "worker_index": worker_index,
        "checkpoint_uri": checkpoint_uri,
        "val_loss": metrics["val_loss"],
        "epoch": 1,
        "metrics": metrics,
    }
    gcs.Client().bucket(bucket_name).blob(
        f"{prefix.rstrip('/')}/manifest.json"
    ).upload_from_string(
        json.dumps(manifest, indent=2), content_type="application/json"
    )
    logger.info("Checkpoint manifest written to %s", checkpoint_uri)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = _parse_args()
    if args.mode == "train":
        _train_entrypoint(args)
    else:
        raise NotImplementedError("predict mode not yet implemented as standalone")
