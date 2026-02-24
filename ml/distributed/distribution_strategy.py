"""
Distribution strategy wrappers for F1 model training on Vertex AI.

Three strategies:
  A) DataParallelStrategy       — split race/lap data across workers (default)
  B) ModelParallelStrategy      — split model layers across GPUs (large telemetry models)
  C) HyperparameterParallelStrategy — parallel HP trials via Vertex AI Vizier

All strategies are configured at job-submission time and run on GCP.
No local execution.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import tensorflow as tf

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
REGION = os.environ.get("REGION", "us-central1")
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "gs://f1optimizer-training")


class BaseDistributionStrategy(ABC):
    """Abstract base for all distribution strategies."""

    @abstractmethod
    def build_strategy(self) -> tf.distribute.Strategy:
        """Return a configured tf.distribute.Strategy."""

    @abstractmethod
    def describe(self) -> dict[str, Any]:
        """Return a human-readable description for logging."""


# ── A) Data Parallel ─────────────────────────────────────────────────────────


class DataParallelStrategy(BaseDistributionStrategy):
    """
    Splits race/lap data across multiple workers.
    Each worker trains on a disjoint set of seasons/races.
    Gradients are aggregated via AllReduce.

    Single-node multi-GPU  → MirroredStrategy
    Multi-node             → MultiWorkerMirroredStrategy  (TF_CONFIG set by Vertex AI)
    """

    def __init__(self, multi_worker: bool = False) -> None:
        self.multi_worker = multi_worker

    def build_strategy(self) -> tf.distribute.Strategy:
        if self.multi_worker:
            communication = tf.distribute.experimental.CommunicationImplementation.NCCL
            options = tf.distribute.experimental.CommunicationOptions(
                implementation=communication
            )
            strategy = tf.distribute.MultiWorkerMirroredStrategy(
                communication_options=options
            )
            logger.info(
                "DataParallelStrategy: MultiWorkerMirroredStrategy, " "num_workers=%d",
                strategy.num_replicas_in_sync,
            )
        else:
            strategy = tf.distribute.MirroredStrategy()
            logger.info(
                "DataParallelStrategy: MirroredStrategy, " "num_replicas=%d",
                strategy.num_replicas_in_sync,
            )
        return strategy

    def describe(self) -> dict[str, Any]:
        return {
            "strategy": (
                "MultiWorkerMirroredStrategy"
                if self.multi_worker
                else "MirroredStrategy"
            ),
            "type": "data_parallel",
            "use_case": "F1 strategy model — split by season/race",
        }


# ── B) Model Parallel ────────────────────────────────────────────────────────


class ModelParallelStrategy(BaseDistributionStrategy):
    """
    Splits model layers across multiple GPUs using pipeline stages.

    Pipeline stages:
      0 → feature_extraction
      1 → sequence_model  (LSTM / Transformer)
      2 → predictor

    Used when the telemetry model is too large for a single GPU.
    Implemented via tf.distribute.experimental.ParameterServerStrategy
    or manual device placement depending on model size.
    """

    def __init__(self, num_gpus: int = 4) -> None:
        self.num_gpus = num_gpus

    def build_strategy(self) -> tf.distribute.Strategy:
        # ParameterServerStrategy is the closest TF equivalent for model parallelism.
        # Layer-level device placement is handled inside the model definition.
        cluster_resolver = tf.distribute.cluster_resolver.TFConfigClusterResolver()
        strategy = tf.distribute.experimental.ParameterServerStrategy(cluster_resolver)
        logger.info(
            "ModelParallelStrategy: ParameterServerStrategy, num_gpus=%d",
            self.num_gpus,
        )
        return strategy

    def describe(self) -> dict[str, Any]:
        return {
            "strategy": "ParameterServerStrategy",
            "type": "model_parallel",
            "stages": ["feature_extraction", "sequence_model", "predictor"],
            "num_gpus": self.num_gpus,
            "use_case": "Large telemetry models that exceed single-GPU memory",
        }


# ── C) Hyperparameter Parallel ───────────────────────────────────────────────


class HyperparameterParallelStrategy(BaseDistributionStrategy):
    """
    Runs multiple training jobs simultaneously, each testing different
    hyperparameters. Uses Vertex AI Vizier for HP optimization.

    - parallel_trial_count: jobs running at the same time (default 5)
    - max_trial_count: total HP trials (default 20)
    - algorithm: GRID_SEARCH | RANDOM_SEARCH | BAYESIAN_OPTIMIZATION
    """

    def __init__(
        self,
        parallel_trial_count: int = 5,
        max_trial_count: int = 20,
        algorithm: str = "GRID_SEARCH",
    ) -> None:
        self.parallel_trial_count = parallel_trial_count
        self.max_trial_count = max_trial_count
        self.algorithm = algorithm

    def build_strategy(self) -> tf.distribute.Strategy:
        # Each HP trial uses a single MirroredStrategy internally.
        strategy = tf.distribute.MirroredStrategy()
        logger.info(
            "HyperparameterParallelStrategy: MirroredStrategy per trial, "
            "parallel_trials=%d, max_trials=%d, algorithm=%s",
            self.parallel_trial_count,
            self.max_trial_count,
            self.algorithm,
        )
        return strategy

    def vizier_study_spec(
        self,
        metric_id: str = "val_loss",
        parameters: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Returns a Vertex AI HyperparameterTuningJob study_spec dict.
        Pass to aiplatform.HyperparameterTuningJob(study_spec=...).
        """
        if parameters is None:
            parameters = [
                {
                    "parameter_id": "learning_rate",
                    "double_value_spec": {"min_value": 1e-5, "max_value": 1e-2},
                    "scale_type": "UNIT_LOG_SCALE",
                },
                {
                    "parameter_id": "batch_size",
                    "discrete_value_spec": {"values": [32, 64, 128, 256]},
                },
                {
                    "parameter_id": "num_layers",
                    "integer_value_spec": {"min_value": 1, "max_value": 6},
                },
                {
                    "parameter_id": "dropout_rate",
                    "double_value_spec": {"min_value": 0.0, "max_value": 0.5},
                },
            ]

        return {
            "metrics": [{"metric_id": metric_id, "goal": "MINIMIZE"}],
            "parameters": parameters,
            "algorithm": self.algorithm,
            "parallel_trial_count": self.parallel_trial_count,
            "max_trial_count": self.max_trial_count,
        }

    def describe(self) -> dict[str, Any]:
        return {
            "strategy": self.algorithm,
            "type": "hyperparameter_parallel",
            "parallel_trial_count": self.parallel_trial_count,
            "max_trial_count": self.max_trial_count,
            "use_case": "HP tuning via Vertex AI Vizier",
        }
