"""
PSI-based feature drift detector.

Population Stability Index (PSI) compares the distribution of a feature
in new (production) data against the training-time histogram baseline.

    PSI = Σ (actual_pct - expected_pct) × ln(actual_pct / expected_pct)

Thresholds (industry standard):
    PSI < 0.10  →  "ok"       (stable)
    PSI < 0.25  →  "warn"     (slight shift)
    PSI ≥ 0.25  →  "critical" (significant shift — consider retraining)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

PSI_WARN = 0.10
PSI_CRITICAL = 0.25


def compute_psi(feature_stat: dict[str, Any], actual_series: pd.Series) -> float:
    """
    Compute PSI for one feature.

    Args:
        feature_stat: dict from extract_feature_stats() for this feature.
            Must have keys: bin_edges, expected_pcts.
        actual_series: production/current data for this feature (numeric).

    Returns:
        PSI score (float ≥ 0).
    """
    edges = np.array(feature_stat["bin_edges"])
    expected_pcts = np.array(feature_stat["expected_pcts"])

    series = pd.to_numeric(actual_series, errors="coerce").dropna()
    if len(series) == 0:
        return 0.0

    # Extend edges to ±inf so out-of-range production values land in
    # the first/last bin rather than being silently dropped.
    extended_edges = np.concatenate([[-np.inf], edges[1:-1], [np.inf]])
    counts, _ = np.histogram(series, bins=extended_edges)
    # Laplace smoothing so ln() never hits -inf
    counts = counts + 1
    actual_pcts = counts / counts.sum()

    # Clip to same length in case of edge mismatch
    n = min(len(actual_pcts), len(expected_pcts))
    actual_pcts = actual_pcts[:n]
    expected = expected_pcts[:n]
    # Re-normalise after slicing
    actual_pcts = actual_pcts / actual_pcts.sum()
    expected = expected / expected.sum()

    psi = float(np.sum((actual_pcts - expected) * np.log(actual_pcts / expected)))
    return max(psi, 0.0)  # numerical noise can produce tiny negatives


@dataclass
class DriftReport:
    model_name: str
    race_id: str
    feature_psi: dict[str, float]           # {feature_name: psi_score}
    drifted_features: list[str] = field(default_factory=list)
    warned_features: list[str] = field(default_factory=list)
    overall_status: str = "ok"              # "ok" | "warn" | "critical"

    def as_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "race_id": self.race_id,
            "feature_psi": self.feature_psi,
            "drifted_features": self.drifted_features,
            "warned_features": self.warned_features,
            "overall_status": self.overall_status,
        }


class DriftDetector:
    """Detect feature drift for one model using a pre-loaded baseline."""

    def __init__(self, baseline_stats: dict[str, Any]) -> None:
        """
        Args:
            baseline_stats: output of feature_stats.load_from_gcs() or
                extract_feature_stats().
        """
        self._baseline = baseline_stats

    def detect(
        self,
        current_df: pd.DataFrame,
        race_id: str,
        model_name: str,
    ) -> DriftReport:
        """
        Compute PSI for every feature in the baseline that exists in current_df.

        Args:
            current_df: DataFrame of features for the race being monitored.
            race_id:    e.g. "2025_5"
            model_name: e.g. "tire_degradation"

        Returns:
            DriftReport with per-feature PSI and an overall status.
        """
        feature_psi: dict[str, float] = {}
        drifted: list[str] = []
        warned: list[str] = []

        for col, stat in self._baseline.items():
            if col not in current_df.columns:
                logger.debug("drift_detector: column %s not in current_df, skipping", col)
                continue
            psi = compute_psi(stat, current_df[col])
            feature_psi[col] = round(psi, 6)
            if psi >= PSI_CRITICAL:
                drifted.append(col)
            elif psi >= PSI_WARN:
                warned.append(col)

        if drifted:
            status = "critical"
        elif warned:
            status = "warn"
        else:
            status = "ok"

        report = DriftReport(
            model_name=model_name,
            race_id=race_id,
            feature_psi=feature_psi,
            drifted_features=drifted,
            warned_features=warned,
            overall_status=status,
        )
        logger.info(
            "drift_detector: %s race=%s status=%s drifted=%s",
            model_name,
            race_id,
            status,
            drifted,
        )
        return report
