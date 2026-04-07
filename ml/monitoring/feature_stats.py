"""
Save and load percentile-histogram baselines for PSI-based drift detection.

Written at training time by each train_*.py script.
Read at monitoring time by drift_detector.py.

GCS path: gs://f1optimizer-training/monitoring/feature_stats_{model_name}.json
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import numpy as np
import pandas as pd
from google.cloud import storage

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "f1optimizer-training")
N_BINS = 10  # percentile-equal bins


def extract_feature_stats(
    df: pd.DataFrame, feature_cols: list[str], n_bins: int = N_BINS
) -> dict[str, Any]:
    """
    Compute percentile-histogram baseline for each numeric feature column.

    Returns:
        {
          "TyreLife": {
            "n_bins": 10,
            "bin_edges": [1.0, 5.3, ..., 39.0],   # n_bins+1 values
            "expected_pcts": [0.1, 0.1, ..., 0.1],  # n_bins values, sum=1.0
            "n": 4500,
          },
          ...
        }
    """
    stats: dict[str, Any] = {}
    percentiles = np.linspace(0, 100, n_bins + 1)

    for col in feature_cols:
        if col not in df.columns:
            logger.warning("feature_stats: column %s not found, skipping", col)
            continue
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) == 0:
            logger.warning(
                "feature_stats: column %s is empty after dropna, skipping", col
            )
            continue

        edges = np.unique(np.percentile(series, percentiles))
        if len(edges) < 2:
            # Constant column — use [val-eps, val+eps] as a single bin
            val = float(series.iloc[0])
            edges = np.array([val - 1e-9, val + 1e-9])

        # Count samples in each bin (include rightmost edge)
        counts, _ = np.histogram(series, bins=edges)
        # Laplace smoothing so ln() never hits -inf in PSI
        counts = counts + 1
        total = counts.sum()
        expected_pcts = (counts / total).tolist()

        stats[col] = {
            "n_bins": len(edges) - 1,
            "bin_edges": edges.tolist(),
            "expected_pcts": expected_pcts,
            "n": int(len(series)),
        }

    return stats


def save_to_gcs(
    stats: dict[str, Any],
    model_name: str,
    bucket: str = TRAINING_BUCKET,
    project: str = PROJECT_ID,
) -> str:
    """Upload feature stats JSON to GCS. Returns the gs:// URI."""
    blob_path = f"monitoring/feature_stats_{model_name}.json"
    gcs_uri = f"gs://{bucket}/{blob_path}"
    payload = json.dumps(stats, indent=2)
    client = storage.Client(project=project)
    client.bucket(bucket).blob(blob_path).upload_from_string(
        payload, content_type="application/json"
    )
    logger.info("feature_stats: saved baseline for %s → %s", model_name, gcs_uri)
    return gcs_uri


def load_from_gcs(
    model_name: str,
    bucket: str = TRAINING_BUCKET,
    project: str = PROJECT_ID,
) -> dict[str, Any] | None:
    """Download feature stats JSON from GCS. Returns None if not found."""
    blob_path = f"monitoring/feature_stats_{model_name}.json"
    try:
        client = storage.Client(project=project)
        data = client.bucket(bucket).blob(blob_path).download_as_text()
        return json.loads(data)
    except Exception as exc:
        logger.warning(
            "feature_stats: could not load baseline for %s: %s", model_name, exc
        )
        return None
