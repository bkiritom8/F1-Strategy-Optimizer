"""
Pit Stop Optimizer — LSTM sequence model.

Predicts the optimal pit stop lap given the current race state:
  - Current lap number & position
  - Tire degradation trend (last N laps)
  - Gap to car ahead/behind
  - Safety car probability
  - Competitor strategies (their tire age / pit history)

Architecture:
    Input sequence (last 10 laps) → LSTM(128) → LSTM(64) → Dense(32) → Dense(1)
    Output: pit_urgency_score in [0, 1]
            > 0.7  → pit this lap
            0.4–0.7 → pit within 3 laps
            < 0.4  → stay out

Supports:
  - GPU training via tf.distribute.MirroredStrategy (SINGLE_NODE_MULTI_GPU)
  - SHAP explanations via DeepExplainer

Run as a Vertex AI Custom Training Job.
Entry point: python -m ml.models.pit_stop_optimizer --mode train ...
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from typing import Any

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import mean_absolute_error, roc_auc_score
from sklearn.model_selection import train_test_split

from ml.models.base_model import BaseF1Model

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

SEQUENCE_LEN = 10  # laps of history fed to LSTM

SEQUENCE_FEATURES = [
    "lap_time_ms",
    "tire_age_laps",
    "gap_to_car_ahead_ms",
    "gap_to_leader_ms",
    "position",
    "lap_time_delta",
    "compound_SOFT",
    "compound_MEDIUM",
    "compound_HARD",
]

STATIC_FEATURES = [
    "circuit_id_enc",
    "year",
    "lap_number",
]

TARGET_COL = "pit_stop_flag"


class PitStopOptimizer(BaseF1Model):
    """LSTM-based pit stop timing model."""

    model_name = "pit_stop_optimizer"

    def __init__(
        self,
        sequence_len: int = SEQUENCE_LEN,
        lstm_units: list[int] | None = None,
        dense_units: list[int] | None = None,
        dropout_rate: float = 0.2,
        learning_rate: float = 1e-3,
        batch_size: int = 128,
        epochs: int = 50,
    ) -> None:
        super().__init__()
        self.sequence_len = sequence_len
        self.lstm_units = lstm_units or [128, 64]
        self.dense_units = dense_units or [32]
        self.dropout_rate = dropout_rate
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.epochs = epochs

        self._keras_model: tf.keras.Model | None = None
        self._feature_means: dict[str, float] = {}
        self._feature_stds: dict[str, float] = {}

    # ── Model construction ────────────────────────────────────────────────────

    def _build_model(self, n_seq_features: int, n_static: int) -> tf.keras.Model:
        # Sequence input: (batch, SEQUENCE_LEN, n_seq_features)
        seq_input = tf.keras.Input(
            shape=(self.sequence_len, n_seq_features), name="sequence_input"
        )
        # Static input: (batch, n_static)
        static_input = tf.keras.Input(shape=(n_static,), name="static_input")

        x = seq_input
        for i, units in enumerate(self.lstm_units):
            return_sequences = i < len(self.lstm_units) - 1
            x = tf.keras.layers.LSTM(
                units,
                return_sequences=return_sequences,
                dropout=self.dropout_rate,
            )(x)

        # Merge with static features
        x = tf.keras.layers.Concatenate()([x, static_input])

        for units in self.dense_units:
            x = tf.keras.layers.Dense(units, activation="relu")(x)
            x = tf.keras.layers.Dropout(self.dropout_rate)(x)

        output = tf.keras.layers.Dense(1, activation="sigmoid", name="pit_urgency")(x)

        model = tf.keras.Model(
            inputs=[seq_input, static_input], outputs=output, name="pit_stop_lstm"
        )
        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=self.learning_rate),
            loss="binary_crossentropy",
            metrics=["accuracy", tf.keras.metrics.AUC(name="auc")],
        )
        return model

    # ── Data preparation ──────────────────────────────────────────────────────

    def _normalise(self, df: pd.DataFrame, fit: bool = False) -> pd.DataFrame:
        df = df.copy()
        cols = SEQUENCE_FEATURES + STATIC_FEATURES
        for col in cols:
            if col not in df.columns:
                df[col] = 0.0
        if fit:
            self._feature_means = df[cols].mean().to_dict()
            self._feature_stds = df[cols].std().replace(0, 1).to_dict()
        for col in cols:
            df[col] = (
                df[col] - self._feature_means.get(col, 0)
            ) / self._feature_stds.get(col, 1)
        return df

    def _to_sequences(
        self, df: pd.DataFrame
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Slide a window of SEQUENCE_LEN over each (race_id, driver_id) group.
        Returns (seq_X, static_X, y).
        """
        seqs, statics, labels = [], [], []

        for _, grp in df.groupby(["race_id", "driver_id"]):
            grp = grp.sort_values("lap_number").reset_index(drop=True)
            seq_arr = grp[SEQUENCE_FEATURES].fillna(0).values
            static_arr = grp[STATIC_FEATURES].fillna(0).values
            target_arr = grp[TARGET_COL].fillna(0).values

            for i in range(self.sequence_len, len(grp)):
                seqs.append(seq_arr[i - self.sequence_len : i])
                statics.append(static_arr[i])
                labels.append(target_arr[i])

        if not seqs:
            raise ValueError("No sequences generated — insufficient data.")

        return np.array(seqs), np.array(statics), np.array(labels)

    def _prepare(self, df: pd.DataFrame, fit: bool = False) -> pd.DataFrame:
        df = df.copy()
        if "circuit_id" in df.columns:
            from sklearn.preprocessing import LabelEncoder

            df["circuit_id_enc"] = LabelEncoder().fit_transform(
                df["circuit_id"].astype(str)
            )
        else:
            df["circuit_id_enc"] = 0
        for col in [
            "compound_SOFT",
            "compound_MEDIUM",
            "compound_HARD",
            "compound_INTER",
            "compound_WET",
        ]:
            if col not in df.columns:
                df[col] = 0
        for col in ["lap_time_delta", "gap_delta"]:
            if col not in df.columns:
                df[col] = 0.0
        if TARGET_COL not in df.columns:
            df[TARGET_COL] = 0
        return self._normalise(df, fit=fit)

    # ── BaseF1Model interface ─────────────────────────────────────────────────

    def train(self, df: pd.DataFrame, **kwargs: Any) -> dict[str, float]:
        self.logger.info("PitStopOptimizer: training on %d rows", len(df))
        self._publish("model_train", "starting", f"rows={len(df)}")

        df = self._prepare(df, fit=True)
        seq_X, static_X, y = self._to_sequences(df)

        idx = np.arange(len(y))
        train_idx, val_idx = train_test_split(idx, test_size=0.15, random_state=42)

        # Distribution strategy (MirroredStrategy for multi-GPU)
        strategy = tf.distribute.MirroredStrategy()
        self.logger.info(
            "PitStopOptimizer: MirroredStrategy, replicas=%d",
            strategy.num_replicas_in_sync,
        )
        with strategy.scope():
            self._keras_model = self._build_model(
                n_seq_features=len(SEQUENCE_FEATURES),
                n_static=len(STATIC_FEATURES),
            )

        checkpoint_cb = tf.keras.callbacks.ModelCheckpoint(
            filepath=tempfile.mkdtemp() + "/best_weights.h5",
            monitor="val_auc",
            mode="max",
            save_best_only=True,
            save_weights_only=True,
        )
        early_stop_cb = tf.keras.callbacks.EarlyStopping(
            monitor="val_auc", patience=8, mode="max", restore_best_weights=True
        )

        history = self._keras_model.fit(
            [seq_X[train_idx], static_X[train_idx]],
            y[train_idx],
            validation_data=([seq_X[val_idx], static_X[val_idx]], y[val_idx]),
            batch_size=self.batch_size * strategy.num_replicas_in_sync,
            epochs=self.epochs,
            callbacks=[checkpoint_cb, early_stop_cb],
            verbose=1,
        )

        val_preds = self._keras_model.predict(
            [seq_X[val_idx], static_X[val_idx]], verbose=0
        ).flatten()
        metrics = {
            "val_loss": float(min(history.history["val_loss"])),
            "val_auc": float(max(history.history["val_auc"])),
            "val_accuracy": float(max(history.history["val_accuracy"])),
            "val_roc_auc": float(roc_auc_score(y[val_idx], val_preds)),
            "train_rows": int(len(train_idx)),
            "val_rows": int(len(val_idx)),
            "epochs_trained": len(history.history["loss"]),
        }
        self._train_metrics = metrics
        self._trained = True

        self.logger.info("PitStopOptimizer: train complete %s", metrics)
        self._publish("model_train", "complete", f"val_auc={metrics['val_auc']:.4f}")
        return metrics

    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        if not self._trained or self._keras_model is None:
            raise RuntimeError("Model not trained. Call train() or load() first.")
        df = self._prepare(df, fit=False)
        seq_X, static_X, _ = self._to_sequences(df)
        urgency = self._keras_model.predict([seq_X, static_X], verbose=0).flatten()
        out = df.iloc[self.sequence_len :].copy()
        out["pit_urgency"] = urgency
        out["recommend_pit"] = (urgency > 0.7).astype(int)
        return out

    def evaluate(self, df: pd.DataFrame) -> dict[str, float]:
        if self._keras_model is None:
            raise RuntimeError("Model is not trained. Call train() first.")
        df = self._prepare(df, fit=False)
        seq_X, static_X, y = self._to_sequences(df)
        preds = self._keras_model.predict([seq_X, static_X], verbose=0).flatten()
        return {
            "val_loss": float(mean_absolute_error(y, preds)),
            "val_roc_auc": float(roc_auc_score(y, preds)),
            "val_mae": float(mean_absolute_error(y, preds)),
            "n_samples": len(y),
        }

    # ── Native save / load ────────────────────────────────────────────────────

    def _save_native(self, local_dir: str) -> None:
        if self._keras_model:
            self._keras_model.save(os.path.join(local_dir, "model.keras"))
        config = {
            "sequence_len": self.sequence_len,
            "lstm_units": self.lstm_units,
            "dense_units": self.dense_units,
            "dropout_rate": self.dropout_rate,
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "epochs": self.epochs,
            "feature_means": self._feature_means,
            "feature_stds": self._feature_stds,
        }
        with open(os.path.join(local_dir, "config.json"), "w") as f:
            json.dump(config, f, indent=2)

    def _load_native(self, local_dir: str) -> None:
        cfg_path = os.path.join(local_dir, "config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                config = json.load(f)
            self.sequence_len = config.get("sequence_len", SEQUENCE_LEN)
            self.lstm_units = config.get("lstm_units", [128, 64])
            self.dense_units = config.get("dense_units", [32])
            self.dropout_rate = config.get("dropout_rate", 0.2)
            self.learning_rate = config.get("learning_rate", 1e-3)
            self.batch_size = config.get("batch_size", 128)
            self.epochs = config.get("epochs", 50)
            self._feature_means = config.get("feature_means", {})
            self._feature_stds = config.get("feature_stds", {})

        model_path = os.path.join(local_dir, "model.keras")
        if os.path.exists(model_path):
            self._keras_model = tf.keras.models.load_model(model_path)
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
    df = pd.read_parquet(args.feature_uri)

    model = PitStopOptimizer()
    metrics = model.train(df)
    logger.info("Training metrics: %s", metrics)

    checkpoint_uri = args.checkpoint_uri.rstrip("/") + "/worker_0/"
    model.save(checkpoint_uri)

    from google.cloud import storage as gcs

    bucket_name, prefix = checkpoint_uri.lstrip("gs://").split("/", 1)
    manifest = {
        "worker_index": 0,
        "checkpoint_uri": checkpoint_uri,
        "val_loss": metrics["val_loss"],
        "epoch": metrics.get("epochs_trained", 1),
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
