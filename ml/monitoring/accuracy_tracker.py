"""
Accuracy decay tracker.

Loads a trained model's baseline metrics from its GCS model_card.json,
then evaluates the model on a given season's data and flags degradation.

Degradation thresholds (matches monitoring.md):
    tire_degradation  MAE > 0.40s        → degraded
    driving_style     F1  < 0.70         → degraded
    safety_car        F1  < 0.85         → degraded
    pit_window        MAE > 2.0 laps     → degraded
    overtake_prob     F1  < 0.25         → degraded
    race_outcome      F1  < 0.55         → degraded
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from google.cloud import storage

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "f1optimizer-models")

# (metric_key, higher_is_better, warn_threshold)
MODEL_THRESHOLDS: dict[str, tuple[str, bool, float]] = {
    "tire_degradation": ("mae", False, 0.40),
    "driving_style":    ("f1",  True,  0.70),
    "safety_car":       ("f1",  True,  0.85),
    "pit_window":       ("mae", False, 2.0),
    "overtake_prob":    ("f1",  True,  0.25),
    "race_outcome":     ("f1",  True,  0.55),
}


def compute_degradation_pct(
    baseline: dict[str, float],
    current: dict[str, float],
    higher_is_better: dict[str, bool],
) -> dict[str, float]:
    """
    Return % degradation per metric (positive = worse).

    For higher-is-better metrics (e.g. F1):
        degradation = (baseline - current) / baseline * 100

    For lower-is-better metrics (e.g. MAE):
        degradation = (current - baseline) / baseline * 100
    """
    result: dict[str, float] = {}
    for key in baseline:
        if key not in current or baseline[key] == 0:
            continue
        if higher_is_better.get(key, False):
            result[key] = (baseline[key] - current[key]) / baseline[key] * 100
        else:
            result[key] = (current[key] - baseline[key]) / baseline[key] * 100
    return result


@dataclass
class AccuracyReport:
    model_name: str
    season: int
    current_metrics: dict[str, float]
    baseline_metrics: dict[str, float]
    degradation_pct: dict[str, float] = field(default_factory=dict)
    degraded: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "season": self.season,
            "current_metrics": self.current_metrics,
            "baseline_metrics": self.baseline_metrics,
            "degradation_pct": self.degradation_pct,
            "degraded": self.degraded,
        }


def load_baseline_metrics(
    model_name: str,
    bucket: str = MODELS_BUCKET,
    project: str = PROJECT_ID,
) -> dict[str, float]:
    """Load train_metrics from the model's GCS model_card.json."""
    blob_path = f"{model_name}/model_card.json"
    try:
        client = storage.Client(project=project)
        data = client.bucket(bucket).blob(blob_path).download_as_text()
        card = json.loads(data)
        return card.get("train_metrics", {})
    except Exception as exc:
        logger.warning("accuracy_tracker: could not load model_card for %s: %s", model_name, exc)
        return {}


def build_accuracy_report(
    model_name: str,
    season: int,
    current_metrics: dict[str, float],
    baseline_metrics: dict[str, float],
) -> AccuracyReport:
    """
    Compare current_metrics to baseline and return an AccuracyReport.

    Degraded = primary metric crosses its warn threshold from MODEL_THRESHOLDS.
    """
    threshold_info = MODEL_THRESHOLDS.get(model_name)
    if threshold_info is None:
        logger.warning("accuracy_tracker: no threshold config for %s", model_name)
        return AccuracyReport(
            model_name=model_name,
            season=season,
            current_metrics=current_metrics,
            baseline_metrics=baseline_metrics,
        )

    metric_key, higher_is_better_flag, warn_threshold = threshold_info
    higher_is_better_map = {metric_key: higher_is_better_flag}
    degradation = compute_degradation_pct(baseline_metrics, current_metrics, higher_is_better_map)

    current_val = current_metrics.get(metric_key)
    if current_val is None:
        degraded = False
    elif higher_is_better_flag:
        degraded = current_val < warn_threshold
    else:
        degraded = current_val > warn_threshold

    return AccuracyReport(
        model_name=model_name,
        season=season,
        current_metrics=current_metrics,
        baseline_metrics=baseline_metrics,
        degradation_pct=degradation,
        degraded=degraded,
    )
