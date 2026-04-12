"""Bridge between race_inputs and the 6 ML model bundles.

Loads each model bundle lazily from GCS on first request.
Runs available models against the current race situation and
returns a dict of human-readable predictions for LLM prompt enrichment.
"""

from __future__ import annotations

import io
import json
import logging
import os
from typing import Any

import warnings
import joblib
from sklearn.exceptions import InconsistentVersionWarning
import pandas as pd
from google.cloud import storage

logger = logging.getLogger(__name__)

# Single source of truth for model artifacts
MANIFEST_PATH = os.path.join(os.path.dirname(__file__), "../../ml/models_manifest.json")


def _load_manifest() -> dict:
    try:
        with open(MANIFEST_PATH, "r") as f:
            return json.load(f)
    except Exception as exc:
        logger.error(
            "model_bridge: could not load manifest from %s: %s", MANIFEST_PATH, exc
        )
        return {"bucket": "f1optimizer-models", "models": {}}


_MANIFEST = _load_manifest()
_BUCKET = _MANIFEST.get("bucket", "f1optimizer-models")
_PATHS = {name: meta["path"] for name, meta in _MANIFEST.get("models", {}).items()}

_bundles: dict[str, Any] = {}
_attempted: set[str] = set()


def _load(name: str) -> Any | None:
    if name in _bundles:
        return _bundles[name]
    if name in _attempted:
        return None
    _attempted.add(name)

    path = _PATHS.get(name)
    if not path:
        logger.warning("model_bridge: no path found for %s in manifest", name)
        return None

    try:
        buf = io.BytesIO()
        storage.Client(project="f1optimizer").bucket(_BUCKET).blob(
            path
        ).download_to_file(buf)
        buf.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", InconsistentVersionWarning)
            _bundles[name] = joblib.load(buf)
        logger.info("model_bridge: loaded %s from %s", name, path)
        return _bundles[name]
    except Exception as exc:
        logger.warning("model_bridge: could not load %s from %s: %s", name, path, exc)
        return None


def _build_df(inputs: dict) -> pd.DataFrame:
    """Build a minimal single-row DataFrame from race_inputs with sensible defaults."""
    lap = int(inputs.get("current_lap") or 20)
    total = int(inputs.get("total_laps") or 66)
    tire_age_raw = inputs.get("tire_age_laps")
    tire_age = int(tire_age_raw if tire_age_raw is not None else 10)
    compound = str(inputs.get("tire_compound") or "MEDIUM").upper()
    position = int(inputs.get("position") or 10)
    gap = float(inputs.get("gap_to_leader") or 2.0)
    driver = str(inputs.get("driver") or "UNKNOWN")
    circuit = str(inputs.get("circuit") or "unknown")
    stint = max(1, lap // 25 + 1)
    fuel_pct = max(0.0, 1.0 - lap / max(total, 1))

    return pd.DataFrame(
        [
            {
                "season": 2024,
                "round": 1,
                "Driver": driver,
                "driver": driver,
                "raceName": circuit,
                "constructor": "unknown",
                "LapNumber": lap,
                "total_laps": total,
                "TyreLife": tire_age,
                "Stint": stint,
                "Compound": compound,
                "compound_SOFT": 1 if compound == "SOFT" else 0,
                "compound_MEDIUM": 1 if compound == "MEDIUM" else 0,
                "compound_HARD": 1 if compound == "HARD" else 0,
                "compound_INTERMEDIATE": 1 if compound == "INTERMEDIATE" else 0,
                "compound_WET": 1 if compound == "WET" else 0,
                "fuel_load_pct": fuel_pct,
                "mean_throttle": 75.0,
                "mean_brake": 20.0,
                "tyre_delta": 0.0,
                "deg_rate_roll3": 0.05,
                "position": position,
                "grid": position,
                "gap_ahead": gap,
                "speed_diff": 5.0,
                "drs_available": 1,
                "tyre_advantage": 0.0,
                "overtake_attempt": 0,
                "driving_style": "NEUTRAL",
                "lap_progress": lap / max(total, 1),
            }
        ]
    )


def get_predictions(race_inputs: dict) -> dict[str, str]:
    """
    Run all available ML models and return human-readable predictions.
    Any model that fails or isn't loaded yet is silently skipped.
    """
    df = _build_df(race_inputs)
    circuit = str(race_inputs.get("circuit") or "unknown")
    results: dict[str, str] = {}

    # ── Tire Degradation ─────────────────────────────────────────────────────
    bundle = _load("tire_degradation")
    if bundle:
        try:
            from ml.models.tire_degradation_model import TireDegradationModel

            m: Any = TireDegradationModel.__new__(TireDegradationModel)
            m._bundle = bundle
            row = m._engineer_features(df.copy())
            feats = bundle["features"]
            X = row[[f for f in feats if f in row.columns]].fillna(0)
            w = bundle["weight"]
            val = float(
                w * bundle["lgb"].predict(X)[0] + (1 - w) * bundle["xgb"].predict(X)[0]
            )
            results["tire_degradation"] = f"{val:+.3f}s/lap"
        except Exception as exc:
            logger.debug("tire_degradation failed: %s", exc)

    # ── Pit Window ───────────────────────────────────────────────────────────
    bundle = _load("pit_window")
    if bundle:
        try:
            from ml.models.pit_window_model import PitWindowModel

            m = PitWindowModel.__new__(PitWindowModel)
            m._bundle = bundle
            out = m.predict(df.copy())
            laps = max(0, round(float(out["prediction"].iloc[0])))
            results["pit_window"] = f"pit in ~{laps} laps"
        except Exception as exc:
            logger.debug("pit_window failed: %s", exc)

    # ── Safety Car ───────────────────────────────────────────────────────────
    # Use circuit_sc_prob lookup (probability that a SC occurs at this circuit),
    # NOT predict() which predicts pitted_under_sc and was trained only on SC laps.
    bundle = _load("safety_car")
    if bundle:
        try:
            from ml.models.safety_car_model import SafetyCarModel

            m = SafetyCarModel.__new__(SafetyCarModel)
            m._bundle = bundle
            prob = m.predict_circuit_sc_prob(circuit)
            results["safety_car_probability"] = f"{prob:.0%}"
        except Exception as exc:
            logger.debug("safety_car failed: %s", exc)

    # ── Driving Style ────────────────────────────────────────────────────────
    bundle = _load("driving_style")
    if bundle:
        try:
            from ml.models.driving_style_model import DrivingStyleModel

            m = DrivingStyleModel.__new__(DrivingStyleModel)
            m._bundle = bundle
            out = m.predict(df.copy())
            results["recommended_driving_style"] = str(out["prediction"].iloc[0])
        except Exception as exc:
            logger.debug("driving_style failed: %s", exc)

    # ── Overtake Probability ─────────────────────────────────────────────────
    bundle = _load("overtake_prob")
    if bundle:
        try:
            from ml.models.overtake_prob_model import OvertakeProbModel

            m = OvertakeProbModel.__new__(OvertakeProbModel)
            m._bundle = bundle
            out = m.predict(df.copy())
            prob = float(out["probability"].iloc[0])
            results["overtake_probability"] = f"{prob:.0%}"
        except Exception as exc:
            logger.debug("overtake_prob failed: %s", exc)

    # ── Race Outcome ─────────────────────────────────────────────────────────
    bundle = _load("race_outcome")
    if bundle:
        try:
            from ml.models.race_outcome_model import RaceOutcomeModel

            m = RaceOutcomeModel.__new__(RaceOutcomeModel)
            m._bundle = bundle
            out = m.predict(df.copy())
            results["predicted_race_outcome"] = str(out["prediction"].iloc[0])
        except Exception as exc:
            logger.debug("race_outcome failed: %s", exc)

    return results
