"""
Abstract base class for all F1 strategy models.

Every model must implement:
    train(df)     — fit on a DataFrame of lap features
    predict(df)   — return predictions as a DataFrame
    evaluate(df)  — return metrics dict
    save(uri)     — persist to GCS
    load(uri)     — restore from GCS

Built-in behaviours (inherited):
    - Structured Cloud Logging on every major step
    - GCS save/load via pickle + optional framework-native format
    - Vertex AI Experiments metric logging
    - Pub/Sub event publishing
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from google.cloud import logging as cloud_logging, pubsub_v1, storage

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
REGION = os.environ.get("REGION", "us-central1")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "gs://f1optimizer-models")
PUBSUB_TOPIC = os.environ.get("PUBSUB_TOPIC", "f1-predictions-dev")


class BaseF1Model(ABC):
    """Abstract base for F1 strategy models."""

    #: Subclasses set this to identify themselves in logs and GCS paths.
    model_name: str = "base"

    def __init__(self) -> None:
        # Cloud Logging
        cloud_logging.Client(project=PROJECT_ID).setup_logging()
        self.logger = logging.getLogger(f"f1.models.{self.model_name}")

        # Pub/Sub
        self._publisher = pubsub_v1.PublisherClient()
        self._topic_path = self._publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)

        # GCS
        self._storage_client = storage.Client(project=PROJECT_ID)
        self._bucket_name = MODELS_BUCKET.lstrip("gs://")

        self._trained = False
        self._train_metrics: dict[str, float] = {}

    # ── Abstract interface ────────────────────────────────────────────────────

    @abstractmethod
    def train(self, df: pd.DataFrame, **kwargs: Any) -> dict[str, float]:
        """
        Fit the model on `df`.
        Returns a dict of training metrics (e.g. {"train_loss": 0.12}).
        """

    @abstractmethod
    def predict(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate predictions for `df`.
        Returns a DataFrame with at minimum a `prediction` column.
        """

    @abstractmethod
    def evaluate(self, df: pd.DataFrame) -> dict[str, float]:
        """
        Score the model on `df`.
        Returns a dict of evaluation metrics (e.g. {"val_loss": 0.15, "mae": 1.2}).
        """

    @abstractmethod
    def _save_native(self, local_dir: str) -> None:
        """
        Save model in its native format (e.g. XGBoost .json, PyTorch .pt)
        under `local_dir`. Called by save().
        """

    @abstractmethod
    def _load_native(self, local_dir: str) -> None:
        """
        Load model from its native format under `local_dir`.
        Called by load().
        """

    # ── GCS persistence ───────────────────────────────────────────────────────

    def save(self, gcs_uri: str) -> None:
        """
        Save model artefacts to GCS.
        Writes:
          <gcs_uri>/model.pkl      — full model pickle (fallback)
          <gcs_uri>/model_card.json — metadata
          <gcs_uri>/native/        — native format files (framework-specific)
        """
        self.logger.info("%s: saving to %s", self.model_name, gcs_uri)
        self._publish("model_save", "saving", gcs_uri)

        bucket_name, prefix = gcs_uri.lstrip("gs://").split("/", 1)
        prefix = prefix.rstrip("/")
        bucket = self._storage_client.bucket(bucket_name)

        with tempfile.TemporaryDirectory() as tmp:
            # Native format
            native_dir = os.path.join(tmp, "native")
            os.makedirs(native_dir)
            self._save_native(native_dir)
            for fname in os.listdir(native_dir):
                bucket.blob(f"{prefix}/native/{fname}").upload_from_filename(
                    os.path.join(native_dir, fname)
                )

            # Pickle fallback
            pkl_path = os.path.join(tmp, "model.pkl")
            with open(pkl_path, "wb") as f:
                pickle.dump(self, f)
            bucket.blob(f"{prefix}/model.pkl").upload_from_filename(pkl_path)

        # Model card
        card = {
            "model_name": self.model_name,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "gcs_uri": gcs_uri,
            "train_metrics": self._train_metrics,
        }
        bucket.blob(f"{prefix}/model_card.json").upload_from_string(
            json.dumps(card, indent=2), content_type="application/json"
        )

        self.logger.info("%s: saved OK to %s", self.model_name, gcs_uri)
        self._publish("model_save", "complete", gcs_uri)

    def load(self, gcs_uri: str) -> None:
        """
        Load model artefacts from GCS (native format preferred).
        Falls back to pickle if native load fails.
        """
        self.logger.info("%s: loading from %s", self.model_name, gcs_uri)

        bucket_name, prefix = gcs_uri.lstrip("gs://").split("/", 1)
        prefix = prefix.rstrip("/")
        bucket = self._storage_client.bucket(bucket_name)

        with tempfile.TemporaryDirectory() as tmp:
            native_dir = os.path.join(tmp, "native")
            os.makedirs(native_dir)

            native_blobs = list(bucket.list_blobs(prefix=f"{prefix}/native/"))
            if native_blobs:
                for blob in native_blobs:
                    fname = blob.name.split("/")[-1]
                    blob.download_to_filename(os.path.join(native_dir, fname))
                self._load_native(native_dir)
                self.logger.info("%s: loaded via native format", self.model_name)
            else:
                # Fallback: pickle
                pkl_path = os.path.join(tmp, "model.pkl")
                bucket.blob(f"{prefix}/model.pkl").download_to_filename(pkl_path)
                with open(pkl_path, "rb") as f:
                    loaded: BaseF1Model = pickle.load(f)
                self.__dict__.update(loaded.__dict__)
                self.logger.info("%s: loaded via pickle fallback", self.model_name)

        self._trained = True

    # ── Vertex AI Experiments logging ─────────────────────────────────────────

    def log_to_experiment(
        self,
        experiment_name: str,
        run_name: str,
        params: dict[str, Any],
        metrics: dict[str, float],
    ) -> None:
        """Log params and metrics to a Vertex AI Experiment run."""
        try:
            from google.cloud import aiplatform

            aiplatform.init(
                project=PROJECT_ID, location=REGION, experiment=experiment_name
            )
            with aiplatform.start_run(run=run_name):
                aiplatform.log_params(params)
                aiplatform.log_metrics(metrics)
            self.logger.info(
                "%s: logged to experiment=%s run=%s",
                self.model_name,
                experiment_name,
                run_name,
            )
        except Exception as exc:
            self.logger.warning(
                "%s: Vertex AI Experiments logging failed: %s", self.model_name, exc
            )

    # ── Pub/Sub ───────────────────────────────────────────────────────────────

    def _publish(self, event: str, status: str, detail: str = "") -> None:
        try:
            payload = json.dumps(
                {
                    "event": event,
                    "model": self.model_name,
                    "status": status,
                    "detail": detail,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ).encode()
            self._publisher.publish(self._topic_path, data=payload)
        except Exception as exc:
            self.logger.warning("Pub/Sub publish failed: %s", exc)
