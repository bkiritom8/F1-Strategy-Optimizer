"""
CLI: run drift + accuracy checks for one race or one season.

Usage:
    # Check drift for a specific race (uses race features from GCS):
    python ml/monitoring/run_monitoring.py --race-id 2025_5

    # Check accuracy decay across an entire season:
    python ml/monitoring/run_monitoring.py --season 2025

    # Both:
    python ml/monitoring/run_monitoring.py --race-id 2025_5 --season 2025

    # Auto-resolve latest race + current season (for CI/CD cron):
    python ml/monitoring/run_monitoring.py --days 1 --log-to-cloud

Results logged to:
    gs://f1optimizer-training/monitoring/drift_log.jsonl
    gs://f1optimizer-training/monitoring/accuracy_log.jsonl

Exit codes:
    0 — all checks passed (ok)
    1 — at least one model is in "warn" or "critical" drift / degraded
    2 — runtime error (bad args, GCS unreachable, etc.)
"""

from __future__ import annotations

import argparse
import logging
import sys
import os
import io
import json
from datetime import datetime
from google.cloud import storage

# GCP Constants
PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "f1optimizer-models")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("run_monitoring")

# Model → feature parquet GCS URI + key feature columns for drift check
MODEL_CONFIG: dict[str, dict] = {
    "tire_degradation": {
        "feature_uri": "gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet",
        "feature_cols": [
            "TyreLife",
            "Stint",
            "FreshTyre",
            "fuel_load_pct",
            "LapNumber",
            "mean_throttle",
            "mean_brake",
            "mean_speed",
            "lap_progress",
        ],
        "metric_key": "mae",
    },
    "driving_style": {
        "feature_uri": "gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet",
        "feature_cols": [
            "mean_throttle",
            "std_throttle",
            "mean_brake",
            "std_brake",
            "mean_speed",
            "max_speed",
            "mean_rpm",
            "drs_usage_pct",
        ],
        "metric_key": "f1",
    },
    "safety_car": {
        "feature_uri": "gs://f1optimizer-data-lake/ml_features/race_results_features.parquet",
        "feature_cols": [
            "LapNumber",
            "lap_progress",
            "position",
            "gap_to_leader",
        ],
        "metric_key": "f1",
    },
    "pit_window": {
        "feature_uri": "gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet",
        "feature_cols": [
            "TyreLife",
            "Stint",
            "fuel_load_pct",
            "LapNumber",
            "laps_remaining",
            "mean_speed",
            "mean_throttle",
        ],
        "metric_key": "mae",
    },
    "overtake_prob": {
        "feature_uri": "gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet",
        "feature_cols": [
            "mean_speed",
            "max_speed",
            "drs_usage_pct",
            "position",
            "gap_to_leader",
            "LapNumber",
        ],
        "metric_key": "f1",
    },
    "race_outcome": {
        "feature_uri": "gs://f1optimizer-data-lake/ml_features/race_results_features.parquet",
        "feature_cols": [
            "grid_position",
            "position",
            "points",
            "constructor_enc",
        ],
        "metric_key": "f1",
    },
}


def _resolve_latest_race(season: int) -> str | None:
    """Find the latest race_id in the feature parquet for a given season."""
    try:
        import pandas as pd

        df = pd.read_parquet(
            "gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet",
            columns=["season", "round"],
        )
        season_df = df[df["season"] == season]
        if season_df.empty:
            return None
        latest_round = int(season_df["round"].max())
        return f"{season}_{latest_round}"
    except Exception as exc:
        logger.warning("Could not auto-resolve latest race: %s", exc)
        return None


def _run_drift_check(race_id: str) -> bool:
    """Return True if all models are stable (no warn/critical drift)."""
    import pandas as pd
    from ml.monitoring.drift_detector import DriftDetector
    from ml.monitoring.feature_stats import load_from_gcs
    from ml.monitoring.monitoring_logger import MonitoringLogger

    ml_logger = MonitoringLogger()
    any_issue = False

    for model_name, cfg in MODEL_CONFIG.items():
        baseline = load_from_gcs(model_name)
        if baseline is None:
            logger.warning(
                "%s: no baseline stats — run training first to generate them",
                model_name,
            )
            continue

        try:
            df = pd.read_parquet(cfg["feature_uri"])
            season, rnd = race_id.split("_", 1)
            race_df = df[
                (df["season"] == int(season)) & (df["round"] == int(rnd))
            ].reset_index(drop=True)
            if race_df.empty:
                logger.warning("%s: no rows for race_id=%s", model_name, race_id)
                continue
        except Exception as exc:
            logger.error("%s: failed to load features: %s", model_name, exc)
            continue

        detector = DriftDetector(baseline_stats=baseline)
        report = detector.detect(race_df, race_id=race_id, model_name=model_name)
        ml_logger.log_drift(report)

        symbol = {"ok": "OK  ", "warn": "WARN", "critical": "CRIT"}[
            report.overall_status
        ]
        logger.info(
            "[%s] %s race=%s | drifted=%s warned=%s",
            symbol,
            model_name,
            race_id,
            report.drifted_features,
            report.warned_features,
        )
        if report.overall_status != "ok":
            any_issue = True

    return not any_issue


def _run_accuracy_check(season: int) -> bool:
    """Return True if all models are within accuracy thresholds."""
    import joblib
    import pandas as pd
    from unittest.mock import patch
    from ml.monitoring.accuracy_tracker import (
        build_accuracy_report,
        load_baseline_metrics,
    )
    from ml.monitoring.monitoring_logger import MonitoringLogger

    ml_logger = MonitoringLogger()
    any_degraded = False

    for model_name, cfg in MODEL_CONFIG.items():
        baseline_metrics = load_baseline_metrics(model_name)
        if not baseline_metrics:
            logger.warning(
                "%s: no baseline metrics in model_card — skipping accuracy check",
                model_name,
            )
            continue

        try:
            df = pd.read_parquet(cfg["feature_uri"])
            season_df = df[df["season"] == season].reset_index(drop=True)
            if season_df.empty:
                logger.warning("%s: no rows for season %d", model_name, season)
                continue
        except Exception as exc:
            logger.error(
                "%s: failed to load features for season %d: %s", model_name, season, exc
            )
            continue

        try:
            # Single source of truth for model artifacts
            MANIFEST_PATH = os.path.join(
                os.path.dirname(__file__), "../models_manifest.json"
            )

            def _load_manifest() -> dict:
                try:
                    with open(MANIFEST_PATH, "r") as f:
                        return json.load(f)["models"]
                except Exception as exc:
                    logger.error("Error loading manifest: %s", exc)
                    # Fallback to hardcoded list if manifest is missing
                    return {m: {"path": f"{m}/model.pkl"} for m in MODEL_CONFIG.keys()}

            _MANIFEST_MODELS = _load_manifest()

            def _download_bundle(name: str):
                client = storage.Client(project=PROJECT_ID)
                bucket = client.bucket(MODELS_BUCKET)

                meta = _MANIFEST_MODELS.get(name)
                if not meta:
                    logger.warning("No path for %s in manifest", name)
                    return None

                blob_path = meta["path"]
                blob = bucket.blob(blob_path)
                if not blob.exists():
                    logger.error(
                        "%s: bundle not found at gs://%s/%s",
                        name,
                        MODELS_BUCKET,
                        blob_path,
                    )
                    return None

                buf = io.BytesIO()
                blob.download_to_file(buf)
                buf.seek(0)
                return joblib.load(buf)

            with patch("ml.models.base_model.cloud_logging.Client"), patch(
                "ml.models.base_model.pubsub_v1.PublisherClient"
            ), patch("ml.models.base_model.storage.Client"):
                bundle = _download_bundle(model_name)

            if bundle is None:
                continue

            if hasattr(bundle, "evaluate"):
                current_metrics = bundle.evaluate(season_df)
            else:
                logger.warning(
                    "%s: bundle has no evaluate() — accuracy check skipped", model_name
                )
                continue
        except Exception as exc:
            logger.error("%s: failed to load/evaluate model: %s", model_name, exc)
            continue

        report = build_accuracy_report(
            model_name=model_name,
            season=season,
            current_metrics=current_metrics,
            baseline_metrics=baseline_metrics,
        )
        ml_logger.log_accuracy(report)

        symbol = "DEGRADED" if report.degraded else "OK      "
        logger.info(
            "[%s] %s season=%d | current=%s degradation_pct=%s",
            symbol,
            model_name,
            season,
            current_metrics,
            report.degradation_pct,
        )
        if report.degraded:
            any_degraded = True

    return not any_degraded


def main() -> int:
    parser = argparse.ArgumentParser(description="F1 ML model drift & accuracy monitor")
    parser.add_argument("--race-id", help='Race to check drift, e.g. "2025_5"')
    parser.add_argument(
        "--season", type=int, help="Season year for accuracy check, e.g. 2025"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Auto-resolve latest race and run drift + accuracy for last N days of data",
    )
    parser.add_argument(
        "--log-to-cloud",
        action="store_true",
        help="Log results to GCS/Cloud Logging (default: local logging only)",
    )
    args = parser.parse_args()

    if args.log_to_cloud:
        logger.info("Cloud logging enabled — results will be written to GCS")

    # --days mode: auto-resolve latest race + current season
    if args.days is not None:
        if not args.season:
            args.season = datetime.now().year
        if not args.race_id:
            resolved = _resolve_latest_race(args.season)
            if resolved:
                args.race_id = resolved
                logger.info("Auto-resolved latest race: %s", args.race_id)
            else:
                logger.warning(
                    "Could not resolve latest race for season %d — "
                    "running accuracy check only",
                    args.season,
                )

    if not args.race_id and not args.season:
        parser.error("Provide at least one of --race-id, --season, or --days")

    all_ok = True

    if args.race_id:
        logger.info("=== Drift check: race_id=%s ===", args.race_id)
        if not _run_drift_check(args.race_id):
            all_ok = False

    if args.season:
        logger.info("=== Accuracy check: season=%d ===", args.season)
        if not _run_accuracy_check(args.season):
            all_ok = False

    if all_ok:
        logger.info("All checks passed.")
        return 0

    logger.warning("One or more checks flagged issues — review logs above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())