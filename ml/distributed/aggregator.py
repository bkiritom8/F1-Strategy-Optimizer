"""
Aggregator for distributed F1 training on Vertex AI.

After all workers finish:
  1. Collects model checkpoints from GCS (one per worker or per trial)
  2. Picks the best checkpoint by validation loss
  3. Saves the final model to gs://f1optimizer-models/<model_name>/
  4. Publishes a completion event to Pub/Sub f1-predictions-dev

Usage (called at end of training pipeline deploy step):
    agg = Aggregator(model_name="strategy_predictor", run_id="20260218-001")
    best = agg.pick_best_checkpoint()
    agg.save_final_model(best)
    agg.publish_completion(best)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from google.cloud import pubsub_v1, storage

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "gs://f1optimizer-models").lstrip(
    "gs://"
)
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "gs://f1optimizer-training").lstrip(
    "gs://"
)
PUBSUB_TOPIC = os.environ.get("PUBSUB_TOPIC", "f1-predictions-dev")


@dataclass
class CheckpointMeta:
    gcs_uri: str
    worker_index: int
    val_loss: float
    epoch: int
    metrics: dict[str, float]


class Aggregator:
    """
    Collects worker checkpoints from GCS, picks the best one,
    and promotes it as the final model.
    """

    def __init__(self, model_name: str, run_id: str) -> None:
        self.model_name = model_name
        self.run_id = run_id
        self._storage_client = storage.Client(project=PROJECT_ID)
        self._publisher = pubsub_v1.PublisherClient()
        self._topic_path = self._publisher.topic_path(PROJECT_ID, PUBSUB_TOPIC)

    # ── Checkpoint discovery ──────────────────────────────────────────────────

    def list_checkpoints(self) -> list[CheckpointMeta]:
        """
        Scan gs://f1optimizer-training/checkpoints/<run_id>/
        for checkpoint manifests written by each worker.
        """
        prefix = f"checkpoints/{self.run_id}/"
        bucket = self._storage_client.bucket(TRAINING_BUCKET)
        blobs = list(bucket.list_blobs(prefix=prefix, match_glob="**/manifest.json"))

        checkpoints: list[CheckpointMeta] = []
        for blob in blobs:
            raw = blob.download_as_text()
            data = json.loads(raw)
            checkpoints.append(
                CheckpointMeta(
                    gcs_uri=data["checkpoint_uri"],
                    worker_index=data.get("worker_index", 0),
                    val_loss=data["val_loss"],
                    epoch=data.get("epoch", 0),
                    metrics=data.get("metrics", {}),
                )
            )

        logger.info(
            "Aggregator found %d checkpoints for run %s", len(checkpoints), self.run_id
        )
        return checkpoints

    # ── Best checkpoint selection ─────────────────────────────────────────────

    def pick_best_checkpoint(self) -> CheckpointMeta:
        """Return the checkpoint with the lowest validation loss."""
        checkpoints = self.list_checkpoints()
        if not checkpoints:
            raise RuntimeError(
                f"No checkpoints found for run {self.run_id} in "
                f"gs://{TRAINING_BUCKET}/checkpoints/{self.run_id}/"
            )

        best = min(checkpoints, key=lambda c: c.val_loss)
        logger.info(
            "Best checkpoint: worker=%d, val_loss=%.6f, epoch=%d, uri=%s",
            best.worker_index,
            best.val_loss,
            best.epoch,
            best.gcs_uri,
        )
        return best

    # ── Model promotion ───────────────────────────────────────────────────────

    def save_final_model(self, checkpoint: CheckpointMeta) -> str:
        """
        Copy the best checkpoint to gs://f1optimizer-models/<model_name>/latest/
        and a timestamped version path.
        Returns the GCS URI of the promoted model.
        """
        source_bucket_name, *parts = checkpoint.gcs_uri.lstrip("gs://").split("/")
        source_prefix = "/".join(parts)

        source_bucket = self._storage_client.bucket(source_bucket_name)
        dest_bucket = self._storage_client.bucket(MODELS_BUCKET)

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        dest_versioned = f"{self.model_name}/{timestamp}/"
        dest_latest = f"{self.model_name}/latest/"

        blobs = list(source_bucket.list_blobs(prefix=source_prefix))
        for blob in blobs:
            relative = blob.name[len(source_prefix) :].lstrip("/")
            for dest_prefix in (dest_versioned, dest_latest):
                dest_blob = dest_bucket.blob(f"{dest_prefix}{relative}")
                token, _, _ = dest_blob.rewrite(blob)
                # rewrite is synchronous for small files; for large files
                # loop until token is None
                while token is not None:
                    token, _, _ = dest_blob.rewrite(blob, rewrite_token=token)

        final_uri = f"gs://{MODELS_BUCKET}/{dest_versioned}"
        logger.info("Final model saved to %s (also at latest/)", final_uri)

        # Write a model card manifest
        card: dict[str, Any] = {
            "model_name": self.model_name,
            "run_id": self.run_id,
            "promoted_at": timestamp,
            "val_loss": checkpoint.val_loss,
            "epoch": checkpoint.epoch,
            "metrics": checkpoint.metrics,
            "source_checkpoint": checkpoint.gcs_uri,
            "gcs_uri": final_uri,
        }
        dest_bucket.blob(f"{dest_versioned}model_card.json").upload_from_string(
            json.dumps(card, indent=2), content_type="application/json"
        )
        dest_bucket.blob(f"{dest_latest}model_card.json").upload_from_string(
            json.dumps(card, indent=2), content_type="application/json"
        )

        return final_uri

    # ── Pub/Sub notification ──────────────────────────────────────────────────

    def publish_completion(
        self, checkpoint: CheckpointMeta, model_uri: str = ""
    ) -> None:
        """Publish a training-complete event to f1-predictions-dev."""
        payload = {
            "event": "training_complete",
            "model_name": self.model_name,
            "run_id": self.run_id,
            "val_loss": checkpoint.val_loss,
            "model_uri": model_uri,
            "published_at": datetime.now(timezone.utc).isoformat(),
        }
        data = json.dumps(payload).encode("utf-8")
        future = self._publisher.publish(self._topic_path, data=data)
        message_id = future.result(timeout=30)
        logger.info(
            "Published completion event to %s (message_id=%s)", PUBSUB_TOPIC, message_id
        )

    # ── Convenience: run full aggregation ────────────────────────────────────

    def run(self) -> str:
        """Pick best checkpoint, save model, publish event. Returns final GCS URI."""
        best = self.pick_best_checkpoint()
        model_uri = self.save_final_model(best)
        self.publish_completion(best, model_uri=model_uri)
        return model_uri
