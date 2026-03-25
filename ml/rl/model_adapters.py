"""
Model adapters — thin wrappers that bridge trained pkl models to the RL env.

Each adapter:
  1. Loads a joblib pkl from a local path or GCS URI
  2. Constructs the exact feature row each model was trained on
  3. Exposes a clean predict() that accepts only RL state fields

Telemetry features unavailable during simulation (mean_throttle, mean_brake,
SpeedI1-ST, sector times) are estimated from driving mode using constants
derived from the fastf1_features dataset quartile analysis.

PKL structures (from training scripts)
───────────────────────────────────────
tire_degradation.pkl  → {lgb, xgb, weight*, features, driver_encoder}
fuel_consumption.pkl  → {lgb, xgb, weight*, features, driver_encoder}
driving_style.pkl     → {lgb, xgb, weight*, features, driver_encoder, label_encoder}
safety_car.pkl        → {pit_lgb, pit_xgb, pit_weight, circuit_sc_prob, features}
pit_window.pkl        → {xgb, lgb, weight**, features, scaler, num_features,
                          driver_encoder, circuit_encoder, circuit_avg_stops,
                          compound_circuit_stint, target="laps_in_stint_remaining"}
race_outcome.pkl      → {cat, lgb, weight***, features, driver_encoder,
                          constructor_encoder, classes, rolling_window}
overtake_prob.pkl     → {lgb, xgb, weight*, features}          (not yet pushed)

Weight conventions:
  *   weight = LGB weight  → pred = weight*lgb + (1-weight)*xgb
  **  weight = XGB weight  → pred = expm1(weight*xgb + (1-weight)*lgb)
  *** weight = CatBoost weight → pred = weight*cat_proba + (1-weight)*lgb_proba

State dict keys expected by adapters (all in F1RaceEnv._build_state_dict()):
  lap_number, total_laps, tire_age_laps, pit_stops_count
  tire_compound, position, gap_to_ahead, gap_to_leader
  lap_time_ms, lap_time_delta_ms, driving_mode, driving_style_int
  sector1_ms, sector2_ms, sector3_ms
  delta_roll3, delta_roll5   (rolling mean of tire_delta, tracked by env)
  deg_rate_roll3             (rolling mean of lap_time_delta, tracked by env)
  tyre_delta_roll3           (same as delta_roll3, alias for feature name alignment)
  tyre_delta_trend           (rolling 5-lap mean of tire_delta, tracked by env)
  prev_style_int             (previous lap driving_style_int, tracked by env)
  race_name                  (e.g. "Bahrain Grand Prix" for circuit_sc_prob lookup)
  tyre_delta                 (current lap tire_delta estimate)
  safety_car                 (bool)
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ── Telemetry estimates per driving mode ──────────────────────────────────────
# Derived from fastf1_features.parquet quartile analysis (2018-2025).

_TELEMETRY_EST: dict[str, dict[str, float]] = {
    "PUSH": {
        "mean_throttle": 74.0,
        "std_throttle": 16.0,
        "mean_brake": 24.0,
        "std_brake": 10.0,
        "mean_speed": 232.0,
        "max_speed": 312.0,
        "SpeedI1": 188.0,
        "SpeedI2": 212.0,
        "SpeedFL": 262.0,
        "SpeedST": 292.0,
        "brake_roll3": 24.0,
        "throttle_roll3": 74.0,
    },
    "BALANCED": {
        "mean_throttle": 61.0,
        "std_throttle": 13.0,
        "mean_brake": 18.0,
        "std_brake": 8.0,
        "mean_speed": 220.0,
        "max_speed": 305.0,
        "SpeedI1": 177.0,
        "SpeedI2": 201.0,
        "SpeedFL": 251.0,
        "SpeedST": 281.0,
        "brake_roll3": 18.0,
        "throttle_roll3": 61.0,
    },
    "NEUTRAL": {
        "mean_throttle": 50.0,
        "std_throttle": 10.0,
        "mean_brake": 14.0,
        "std_brake": 6.0,
        "mean_speed": 209.0,
        "max_speed": 298.0,
        "SpeedI1": 166.0,
        "SpeedI2": 191.0,
        "SpeedFL": 241.0,
        "SpeedST": 271.0,
        "brake_roll3": 14.0,
        "throttle_roll3": 50.0,
    },
}

OPTIMAL_STINT: dict[str, int] = {
    "SOFT": 20,
    "MEDIUM": 30,
    "HARD": 45,
    "INTERMEDIATE": 25,
    "WET": 20,
}


def _tel(state: dict, key: str) -> float:
    """Return telemetry value from state if present, else estimate from driving mode."""
    if key in state and state[key] is not None:
        return float(state[key])
    mode = state.get("driving_mode", "BALANCED")
    return _TELEMETRY_EST.get(mode, _TELEMETRY_EST["BALANCED"]).get(key, 0.0)


def _compound_flags(compound: str) -> dict[str, int]:
    c = (compound or "MEDIUM").upper()
    return {
        "compound_SOFT": int(c == "SOFT"),
        "compound_MEDIUM": int(c == "MEDIUM"),
        "compound_HARD": int(c == "HARD"),
        "compound_INTERMEDIATE": int(c in ("INTER", "INTERMEDIATE")),
        "compound_WET": int(c == "WET"),
    }


def _load_pkl(path: str, project: str = "f1optimizer") -> Any:
    import joblib

    if path.startswith("gs://"):
        from google.cloud import storage

        client = storage.Client(project=project)
        bucket, blob_path = path[5:].split("/", 1)
        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as f:
            tmp = f.name
        client.bucket(bucket).blob(blob_path).download_to_filename(tmp)
        obj = joblib.load(tmp)
        os.unlink(tmp)
        return obj
    return joblib.load(path)


# ── Base ──────────────────────────────────────────────────────────────────────


class _BaseAdapter:
    model_name: str = "base"

    def __init__(self, path: Optional[str], project: str = "f1optimizer") -> None:
        self._bundle: Any = None
        self._project = project
        if path:
            try:
                self._bundle = _load_pkl(path, project)
                logger.info("%s: loaded from %s", self.model_name, path)
            except Exception as exc:
                logger.warning(
                    "%s: load failed (%s) — fallback active", self.model_name, exc
                )

    @property
    def loaded(self) -> bool:
        return self._bundle is not None

    def _predict_regression(self, X: pd.DataFrame) -> float:
        lgb = self._bundle["lgb"]
        xgb = self._bundle["xgb"]
        w = self._bundle.get("weight", 0.5)
        return float(w * lgb.predict(X)[0] + (1 - w) * xgb.predict(X)[0])

    def _predict_regression_batch(self, X: pd.DataFrame) -> np.ndarray:
        """Predict regression for a batch of rows — one model call instead of N."""
        lgb = self._bundle["lgb"]
        xgb = self._bundle["xgb"]
        w = self._bundle.get("weight", 0.5)
        return w * lgb.predict(X) + (1 - w) * xgb.predict(X)

    def _predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        lgb = self._bundle["lgb"]
        xgb = self._bundle["xgb"]
        w = self._bundle.get("weight", 0.5)
        return w * lgb.predict_proba(X) + (1 - w) * xgb.predict_proba(X)

    def _align(self, row: dict) -> pd.DataFrame:
        features = self._bundle["features"]
        return pd.DataFrame([{f: row.get(f, 0.0) for f in features}])[features].fillna(
            0.0
        )

    def _align_batch(self, rows: list[dict]) -> pd.DataFrame:
        """Align a list of state dicts into a single feature DataFrame."""
        features = self._bundle["features"]
        return pd.DataFrame([{f: r.get(f, 0.0) for f in features} for r in rows])[
            features
        ].fillna(0.0)


# ── Tire Degradation ──────────────────────────────────────────────────────────


class TireDegradationAdapter(_BaseAdapter):
    """
    Predicts tire_delta (seconds above the per-lap median baseline).
    Positive = slower than expected = degraded tire.

    Output fed back into env as lap time penalty (convert s → ms).
    """

    model_name = "tire_degradation"

    def predict(self, state: dict) -> float:
        """Returns tire_delta in seconds. Fallback: physics linear degradation."""
        if not self.loaded:
            return _physics_tire_deg(state)
        try:
            lap = state.get("lap_number", 1)
            total = max(state.get("total_laps", 60), 1)
            tire_age = state.get("tire_age_laps", 0)
            stint = state.get("pit_stops_count", 0)
            compound = (state.get("tire_compound") or "MEDIUM").upper()
            fuel_pct = 1.0 - (lap - 1) / total
            laps_rem = total - lap
            mt = _tel(state, "mean_throttle")
            mb = _tel(state, "mean_brake")
            st = _tel(state, "std_throttle")
            sb = _tel(state, "std_brake")

            row = {
                "TyreLife": tire_age,
                "Stint": stint,
                "LapNumber": lap,
                **_compound_flags(compound),
                "fuel_load_pct": fuel_pct,
                "laps_remaining": laps_rem,
                "mean_throttle": mt,
                "std_throttle": st,
                "mean_brake": mb,
                "std_brake": sb,
                "driving_style": state.get("driving_style_int", 1),
                "position": state.get("position", 10),
                "gap_ahead": state.get("gap_to_ahead", 5.0),
                "tyre_fuel_interaction": tire_age * fuel_pct,
                "tyre_squared": tire_age**2,
                "tyre_cubed": tire_age**3,
                "lap_progress": lap / total,
                "tyre_per_stint": tire_age / (stint + 1),
                "throttle_brake_ratio": mt / (mb + 1),
                "tyre_x_throttle": tire_age * mt / 100,
                "tyre_x_brake": tire_age * mb / 100,
                "fuel_x_throttle": fuel_pct * mt,
                "delta_roll3": state.get("delta_roll3", 0.0),
                "delta_roll5": state.get("delta_roll5", 0.0),
            }
            return self._predict_regression(self._align(row))
        except Exception as exc:
            logger.warning("TireDegradationAdapter.predict error: %s", exc)
            return _physics_tire_deg(state)

    def predict_batch(self, states: list[dict]) -> list[float]:
        """
        Batch-predict tire_delta for a list of driver states.
        One LGB + XGB call instead of len(states) calls — ~20x faster.
        """
        if not self.loaded or not states:
            return [_physics_tire_deg(s) for s in states]
        try:
            rows = []
            for state in states:
                lap = state.get("lap_number", 1)
                total = max(state.get("total_laps", 60), 1)
                tire_age = state.get("tire_age_laps", 0)
                stint = state.get("pit_stops_count", 0)
                compound = (state.get("tire_compound") or "MEDIUM").upper()
                fuel_pct = 1.0 - (lap - 1) / total
                mt = _tel(state, "mean_throttle")
                mb = _tel(state, "mean_brake")
                rows.append(
                    {
                        "TyreLife": tire_age,
                        "Stint": stint,
                        "LapNumber": lap,
                        **_compound_flags(compound),
                        "fuel_load_pct": fuel_pct,
                        "laps_remaining": total - lap,
                        "mean_throttle": mt,
                        "std_throttle": _tel(state, "std_throttle"),
                        "mean_brake": mb,
                        "std_brake": _tel(state, "std_brake"),
                        "driving_style": state.get("driving_style_int", 1),
                        "position": state.get("position", 10),
                        "gap_ahead": state.get("gap_to_ahead", 5.0),
                        "tyre_fuel_interaction": tire_age * fuel_pct,
                        "tyre_squared": tire_age**2,
                        "tyre_cubed": tire_age**3,
                        "lap_progress": lap / total,
                        "tyre_per_stint": tire_age / (stint + 1),
                        "throttle_brake_ratio": mt / (mb + 1),
                        "tyre_x_throttle": tire_age * mt / 100,
                        "tyre_x_brake": tire_age * mb / 100,
                        "fuel_x_throttle": fuel_pct * mt,
                        "delta_roll3": state.get("delta_roll3", 0.0),
                        "delta_roll5": state.get("delta_roll5", 0.0),
                    }
                )
            X = self._align_batch(rows)
            return list(self._predict_regression_batch(X))
        except Exception as exc:
            logger.warning("TireDegradationAdapter.predict_batch error: %s", exc)
            return [_physics_tire_deg(s) for s in states]


def _physics_tire_deg(state: dict) -> float:
    _RATES = {"SOFT": 0.08, "MEDIUM": 0.05, "HARD": 0.03, "INTER": 0.06, "WET": 0.04}
    compound = (state.get("tire_compound") or "MEDIUM").upper()
    return _RATES.get(compound, 0.05) * max(0, state.get("tire_age_laps", 0) - 1)


# ── Fuel Consumption ──────────────────────────────────────────────────────────


class FuelConsumptionAdapter(_BaseAdapter):
    """
    Predicts fuel_consumed (kg per lap).
    Fallback: 1.8 kg/lap (F1 regulation average).
    """

    model_name = "fuel_consumption"

    def predict(self, state: dict) -> float:
        """Returns kg consumed this lap, clamped to [0.5, 3.5]."""
        if not self.loaded:
            return _physics_fuel(state)
        try:
            lap = state.get("lap_number", 1)
            total = max(state.get("total_laps", 60), 1)
            tire_age = state.get("tire_age_laps", 0)
            stint = state.get("pit_stops_count", 0)
            compound = (state.get("tire_compound") or "MEDIUM").upper()
            fuel_pct = 1.0 - (lap - 1) / total

            row = {
                "LapNumber": lap,
                "total_laps": total,
                "laps_remaining": total - lap,
                "fuel_load_pct": fuel_pct,
                "mean_brake": _tel(state, "mean_brake"),
                "std_brake": _tel(state, "std_brake"),
                "mean_speed": _tel(state, "mean_speed"),
                "max_speed": _tel(state, "max_speed"),
                "SpeedI1": _tel(state, "SpeedI1"),
                "SpeedI2": _tel(state, "SpeedI2"),
                "SpeedFL": _tel(state, "SpeedFL"),
                "SpeedST": _tel(state, "SpeedST"),
                "Sector1Time": state.get("sector1_ms", 28_000.0) / 1000.0,
                "Sector2Time": state.get("sector2_ms", 32_000.0) / 1000.0,
                "Sector3Time": state.get("sector3_ms", 22_000.0) / 1000.0,
                "lap_time_delta": state.get("lap_time_delta_ms", 0.0) / 1000.0,
                "deg_rate_roll3": state.get("deg_rate_roll3", 0.0),
                "TyreLife": tire_age,
                "Stint": stint,
                **_compound_flags(compound),
                "position": state.get("position", 10),
                "gap_ahead": state.get("gap_to_ahead", 5.0),
            }
            result = self._predict_regression(self._align(row))
            return float(np.clip(result, 0.5, 3.5))
        except Exception as exc:
            logger.warning("FuelConsumptionAdapter.predict error: %s", exc)
            return _physics_fuel(state)

    def predict_batch(self, states: list[dict]) -> list[float]:
        """Batch-predict fuel_consumed for multiple drivers in one model call."""
        if not self.loaded or not states:
            return [_physics_fuel(s) for s in states]
        try:
            rows = []
            for state in states:
                lap = state.get("lap_number", 1)
                total = max(state.get("total_laps", 60), 1)
                tire_age = state.get("tire_age_laps", 0)
                stint = state.get("pit_stops_count", 0)
                compound = (state.get("tire_compound") or "MEDIUM").upper()
                rows.append(
                    {
                        "LapNumber": lap,
                        "total_laps": total,
                        "laps_remaining": total - lap,
                        "fuel_load_pct": 1.0 - (lap - 1) / total,
                        "mean_brake": _tel(state, "mean_brake"),
                        "std_brake": _tel(state, "std_brake"),
                        "mean_speed": _tel(state, "mean_speed"),
                        "max_speed": _tel(state, "max_speed"),
                        "SpeedI1": _tel(state, "SpeedI1"),
                        "SpeedI2": _tel(state, "SpeedI2"),
                        "SpeedFL": _tel(state, "SpeedFL"),
                        "SpeedST": _tel(state, "SpeedST"),
                        "Sector1Time": state.get("sector1_ms", 28_000.0) / 1000.0,
                        "Sector2Time": state.get("sector2_ms", 32_000.0) / 1000.0,
                        "Sector3Time": state.get("sector3_ms", 22_000.0) / 1000.0,
                        "lap_time_delta": state.get("lap_time_delta_ms", 0.0) / 1000.0,
                        "deg_rate_roll3": state.get("deg_rate_roll3", 0.0),
                        "TyreLife": tire_age,
                        "Stint": stint,
                        **_compound_flags(compound),
                        "position": state.get("position", 10),
                        "gap_ahead": state.get("gap_to_ahead", 5.0),
                    }
                )
            X = self._align_batch(rows)
            return list(np.clip(self._predict_regression_batch(X), 0.5, 3.5))
        except Exception as exc:
            logger.warning("FuelConsumptionAdapter.predict_batch error: %s", exc)
            return [_physics_fuel(s) for s in states]


def _physics_fuel(state: dict) -> float:
    return {"PUSH": 2.1, "BALANCED": 1.8, "NEUTRAL": 1.5}.get(
        state.get("driving_mode", "BALANCED"), 1.8
    )


# ── Driving Style ─────────────────────────────────────────────────────────────


class DrivingStyleAdapter(_BaseAdapter):
    """
    Predicts the lap-level driving style label (0=NEUTRAL, 1=BALANCE, 2=PUSH).

    In the RL env the agent *commands* a driving mode, but this adapter
    predicts what style the current car state most resembles — useful for
    reward shaping and post-race analysis.
    """

    model_name = "driving_style"

    def predict(self, state: dict) -> int:
        """Returns 0 (NEUTRAL), 1 (BALANCE), or 2 (PUSH)."""
        if not self.loaded:
            return state.get("driving_style_int", 1)
        try:
            lap = state.get("lap_number", 1)
            total = max(state.get("total_laps", 60), 1)
            tire_age = state.get("tire_age_laps", 0)
            stint = state.get("pit_stops_count", 0)
            compound = (state.get("tire_compound") or "MEDIUM").upper()
            cflags = _compound_flags(compound)

            row = {
                "LapNumber": lap,
                "total_laps": total,
                "laps_remaining": total - lap,
                "fuel_load_pct": 1.0 - (lap - 1) / total,
                "lap_progress": lap / total,
                "mean_speed": _tel(state, "mean_speed"),
                "max_speed": _tel(state, "max_speed"),
                "SpeedI1": _tel(state, "SpeedI1"),
                "SpeedI2": _tel(state, "SpeedI2"),
                "SpeedFL": _tel(state, "SpeedFL"),
                "SpeedST": _tel(state, "SpeedST"),
                "Sector1Time": state.get("sector1_ms", 28_000.0) / 1000.0,
                "Sector2Time": state.get("sector2_ms", 32_000.0) / 1000.0,
                "Sector3Time": state.get("sector3_ms", 22_000.0) / 1000.0,
                "mean_brake": _tel(state, "mean_brake"),
                "std_brake": _tel(state, "std_brake"),
                "brake_roll3": _tel(state, "brake_roll3"),
                "TyreLife": tire_age,
                "Stint": stint,
                "FreshTyre": int(tire_age == 0),
                "compound_SOFT": cflags["compound_SOFT"],
                "compound_MEDIUM": cflags["compound_MEDIUM"],
                "compound_HARD": cflags["compound_HARD"],
                "lap_time_delta": state.get("lap_time_delta_ms", 0.0) / 1000.0,
                "deg_rate_roll3": state.get("deg_rate_roll3", 0.0),
                "tyre_delta_roll3": state.get("tyre_delta_roll3", 0.0),
                "position": state.get("position", 10),
                "gap_ahead": state.get("gap_to_ahead", 5.0),
                "throttle_roll3": _tel(state, "throttle_roll3"),
                "prev_style": state.get("prev_style_int", 1),
            }
            proba = self._predict_proba(self._align(row))[0]
            return int(np.argmax(proba))
        except Exception as exc:
            logger.warning("DrivingStyleAdapter.predict error: %s", exc)
            return state.get("driving_style_int", 1)


# ── Safety Car ────────────────────────────────────────────────────────────────


class SafetyCarAdapter(_BaseAdapter):
    """
    Wraps safety_car.pkl.

    Two responsibilities:
      1. sc_deploy_prob(race_name) — P(SC deploys this lap) from circuit lookup table
      2. predict_pit(state)        — P(should pit now given SC is active) from classifier

    Note: pkl uses non-standard keys: pit_lgb, pit_xgb, pit_weight.
    """

    model_name = "safety_car"

    # SC deployment base rate when circuit not found in lookup
    _DEFAULT_SC_PROB = 0.04

    def sc_deploy_prob(self, race_name: str) -> float:
        """
        Returns per-lap SC deployment probability for a given circuit.
        Source: circuit_sc_prob lookup table in safety_car.pkl.
        """
        if not self.loaded:
            return self._DEFAULT_SC_PROB
        circuit_probs: dict = self._bundle.get("circuit_sc_prob", {})
        return float(circuit_probs.get(race_name, self._DEFAULT_SC_PROB))

    def predict_pit(self, state: dict) -> float:
        """
        Returns P(optimal to pit under SC) ∈ [0, 1].
        Used by the env to inform the reward function, not to override agent actions.
        """
        if not self.loaded:
            return float(state.get("tire_age_laps", 0) > 10)
        try:
            lap = state.get("lap_number", 1)
            total = max(state.get("total_laps", 60), 1)
            tire_age = state.get("tire_age_laps", 0)
            stint = state.get("pit_stops_count", 0)
            compound = (state.get("tire_compound") or "MEDIUM").upper()
            cflags = _compound_flags(compound)
            laps_rem = total - lap
            fuel_pct = 1.0 - (lap - 1) / total
            opt_len = OPTIMAL_STINT.get(compound, 30)

            row = {
                "TyreLife": tire_age,
                "tyre_life_pct": tire_age / max(total, 1),
                "Stint": stint,
                "FreshTyre": int(tire_age == 0),
                **cflags,
                "soft_age": cflags["compound_SOFT"] * tire_age,
                "medium_age": cflags["compound_MEDIUM"] * tire_age,
                "hard_age": cflags["compound_HARD"] * tire_age,
                "laps_past_optimal": max(0, tire_age - opt_len),
                "optimal_stint_len": opt_len,
                "LapNumber": lap,
                "laps_remaining": laps_rem,
                "lap_progress": lap / total,
                "total_laps": total,
                "fuel_load_pct": fuel_pct,
                "race_phase": min(2, int((lap / total) / 0.33)),
                "pit_stops_so_far": max(0, stint - 1),
                "position": state.get("position", 10),
                "gap_ahead": state.get("gap_to_ahead", 5.0),
                "tyre_delta": state.get("tyre_delta", 0.0),
                "tyre_delta_trend": state.get("tyre_delta_trend", 0.0),
                "lap_time_delta": state.get("lap_time_delta_ms", 0.0) / 1000.0,
                "deg_rate_roll3": state.get("deg_rate_roll3", 0.0),
                "mean_speed": _tel(state, "mean_speed"),
                "max_speed": _tel(state, "max_speed"),
                "Sector1Time": state.get("sector1_ms", 28_000.0) / 1000.0,
                "Sector2Time": state.get("sector2_ms", 32_000.0) / 1000.0,
                "Sector3Time": state.get("sector3_ms", 22_000.0) / 1000.0,
                "SpeedI1": _tel(state, "SpeedI1"),
                "SpeedI2": _tel(state, "SpeedI2"),
                "SpeedFL": _tel(state, "SpeedFL"),
                "SpeedST": _tel(state, "SpeedST"),
            }
            features = self._bundle["features"]
            X = pd.DataFrame([{f: row.get(f, 0.0) for f in features}])[features].fillna(
                0.0
            )

            pit_lgb = self._bundle["pit_lgb"]
            pit_xgb = self._bundle["pit_xgb"]
            w = self._bundle.get("pit_weight", 0.5)
            proba = (
                w * pit_lgb.predict_proba(X)[:, 1]
                + (1 - w) * pit_xgb.predict_proba(X)[:, 1]
            )
            return float(proba[0])
        except Exception as exc:
            logger.warning("SafetyCarAdapter.predict_pit error: %s", exc)
            return float(state.get("tire_age_laps", 0) > 10)


# ── Pit Window ────────────────────────────────────────────────────────────────


class PitWindowAdapter(_BaseAdapter):
    """
    Predicts laps_in_stint_remaining — laps left before the optimal pit stop.

    PKL specifics:
      - weight = XGB weight  → expm1(weight*xgb + (1-weight)*lgb)
      - scaler (RobustScaler) must be applied to num_features before inference
      - dry compounds only; INTER/WET fall back to heuristic
    """

    model_name = "pit_window"

    # Compound-specific optimal stint lengths (fallback heuristic)
    _OPTIMAL: dict[str, int] = {
        "SOFT": 20,
        "MEDIUM": 30,
        "HARD": 45,
        "SUPERSOFT": 18,
        "ULTRASOFT": 15,
        "HYPERSOFT": 12,
        "INTERMEDIATE": 25,
        "WET": 20,
    }

    def predict(self, state: dict) -> float:
        """
        Returns estimated laps remaining in the current tire stint.
        Falls back to a simple heuristic when the model is not loaded.
        """
        compound = (state.get("tire_compound") or "MEDIUM").upper()
        if not self.loaded:
            return _heuristic_pit_window(state)
        if compound in ("INTERMEDIATE", "WET", "INTER"):
            return _heuristic_pit_window(state)
        try:
            lap = state.get("lap_number", 1)
            total = max(state.get("total_laps", 60), 1)
            tire_age = state.get("tire_age_laps", 0)
            stint = state.get("pit_stops_count", 0)
            fuel_pct = 1.0 - (lap - 1) / total
            laps_rem = total - lap
            cflags = _compound_flags(compound)
            mt = _tel(state, "mean_throttle")
            mb = _tel(state, "mean_brake")
            st_thr = _tel(state, "std_throttle")
            sb = _tel(state, "std_brake")

            tyre_sq = tire_age**2
            tyre_cu = tire_age**3
            delta = state.get("tyre_delta", 0.0)
            drr3 = state.get("deg_rate_roll3", 0.0)
            dr3 = state.get("delta_roll3", 0.0)
            dr5 = state.get("delta_roll5", 0.0)

            row = {
                "TyreLife": tire_age,
                "Stint": stint,
                "FreshTyre": int(tire_age == 0),
                **cflags,
                "compound_SUPERSOFT": int(compound == "SUPERSOFT"),
                "compound_ULTRASOFT": int(compound == "ULTRASOFT"),
                "compound_HYPERSOFT": int(compound == "HYPERSOFT"),
                "compound_age_soft": cflags["compound_SOFT"] * tire_age,
                "compound_age_medium": cflags["compound_MEDIUM"] * tire_age,
                "compound_age_hard": cflags["compound_HARD"] * tire_age,
                "tyre_age_sq_soft": cflags["compound_SOFT"] * tyre_sq,
                "tyre_age_sq_medium": cflags["compound_MEDIUM"] * tyre_sq,
                "tyre_squared": tyre_sq,
                "tyre_cubed": tyre_cu,
                "tyre_per_stint": tire_age / (stint + 1),
                "stint_progress": min(
                    1.0, tire_age / max(self._OPTIMAL.get(compound, 30), 1)
                ),
                "fuel_load_pct": fuel_pct,
                "laps_remaining": laps_rem,
                "LapNumber": lap,
                "lap_progress": lap / total,
                "tyre_delta": delta,
                "deg_rate_roll3": drr3,
                "prev_delta": dr3,
                "prev_delta_2": dr5,
                "delta_diff": dr3 - dr5,
                "delta_std3": abs(dr3 - dr5) * 0.5,
                "deg_roll3": drr3,
                "deg_roll5": state.get("delta_roll5", drr3),
                "deg_roll7": state.get("delta_roll5", drr3),
                "deg_acceleration": 0.0,
                "cliff_approaching": int(drr3 > 0.05),
                "mean_throttle": mt,
                "std_throttle": st_thr,
                "mean_brake": mb,
                "std_brake": sb,
                "throttle_brake_ratio": mt / (mb + 1),
                "cum_throttle": mt,
                "cum_brake": mb,
                "mean_speed": _tel(state, "mean_speed"),
                "max_speed": _tel(state, "max_speed"),
                "SpeedI1": _tel(state, "SpeedI1"),
                "SpeedI2": _tel(state, "SpeedI2"),
                "SpeedFL": _tel(state, "SpeedFL"),
                "SpeedST": _tel(state, "SpeedST"),
                "Sector1Time": state.get("sector1_ms", 28_000.0) / 1000.0,
                "Sector2Time": state.get("sector2_ms", 32_000.0) / 1000.0,
                "Sector3Time": state.get("sector3_ms", 22_000.0) / 1000.0,
                "position": state.get("position", 10),
                "position_pct": state.get("position", 10) / 20.0,
                "gap_ahead": state.get("gap_to_ahead", 5.0),
                "undercut_delta": drr3 * tire_age,
                "is_in_traffic": int(state.get("gap_to_ahead", 99.0) < 3.0),
                "pit_stops_so_far": max(0, stint - 1),
                "remaining_pit_stops": max(0, 2 - max(0, stint - 1)),
                "total_planned_stops": 2,
                "circuit_encoded": 0,
                "circuit_avg_stops": self._bundle.get("circuit_avg_stops", {}).get(
                    state.get("race_name", ""), 2.0
                ),
                "expected_stint_len": self._OPTIMAL.get(compound, 30),
                "laps_until_optimal": max(
                    0, self._OPTIMAL.get(compound, 30) - tire_age
                ),
                "mean_rpm": 11500.0,
                "max_rpm": 13000.0,
                "mean_gear": 6.5,
                "drs_usage_pct": 0.25,
                "driving_style_encoded": state.get("driving_style_int", 1),
                "driver_encoded": 0,
            }

            features = self._bundle["features"]
            num_features = self._bundle["num_features"]
            scaler = self._bundle["scaler"]
            xgb_m = self._bundle["xgb"]
            lgb_m = self._bundle["lgb"]
            w = self._bundle.get("weight", 0.5)  # XGB weight

            X = pd.DataFrame([{f: row.get(f, 0.0) for f in features}])[features].fillna(
                0.0
            )
            # Apply RobustScaler to numerical features
            num_cols_present = [c for c in num_features if c in X.columns]
            X[num_cols_present] = scaler.transform(X[num_cols_present])

            log_pred = w * xgb_m.predict(X)[0] + (1.0 - w) * lgb_m.predict(X)[0]
            return float(max(0.0, np.expm1(log_pred)))
        except Exception as exc:
            logger.warning("PitWindowAdapter.predict error: %s", exc)
            return _heuristic_pit_window(state)


def _heuristic_pit_window(state: dict) -> float:
    compound = (state.get("tire_compound") or "MEDIUM").upper()
    tire_age = state.get("tire_age_laps", 0)
    optimal = OPTIMAL_STINT.get(compound, 30)
    return float(max(0, optimal - tire_age))


# ── Overtake Probability (stub — model not yet pushed) ────────────────────────


class OvertakeProbAdapter(_BaseAdapter):
    """
    Predicts P(gain >= 1 position this lap) ∈ [0, 1].

    Expected pkl when pushed:
      keys:     lgb, xgb, weight, features
      features: gap_to_ahead, lap_time_delta, position, TyreLife,
                fuel_load_pct, LapNumber, total_laps,
                compound_SOFT/MEDIUM/HARD, mean_speed, driving_style
      target:   overtake_success = (position_change >= 1)  [binary, from preprocess_data.py]
    """

    model_name = "overtake_probability"

    def predict(self, state: dict) -> float:
        """Returns overtake probability. Falls back to gap-based heuristic."""
        if not self.loaded:
            return _heuristic_overtake_prob(state)
        try:
            lap = state.get("lap_number", 1)
            total = max(state.get("total_laps", 60), 1)
            compound = (state.get("tire_compound") or "MEDIUM").upper()

            row = {
                "gap_to_ahead": state.get("gap_to_ahead", 5.0),
                "lap_time_delta": state.get("lap_time_delta_ms", 0.0) / 1000.0,
                "position": state.get("position", 10),
                "TyreLife": state.get("tire_age_laps", 0),
                "fuel_load_pct": 1.0 - (lap - 1) / total,
                "LapNumber": lap,
                "total_laps": total,
                "mean_speed": _tel(state, "mean_speed"),
                "driving_style": state.get("driving_style_int", 1),
                **_compound_flags(compound),
            }
            proba = self._predict_proba(self._align(row))[0]
            return float(proba[1]) if len(proba) > 1 else float(proba[0])
        except Exception as exc:
            logger.warning("OvertakeProbAdapter.predict error: %s", exc)
            return _heuristic_overtake_prob(state)


def _heuristic_overtake_prob(state: dict) -> float:
    gap = state.get("gap_to_ahead", 99.0)
    if gap <= 0.5:
        return 0.35
    if gap <= 1.0:
        return 0.20
    if gap <= 2.0:
        return 0.08
    return 0.02


# ── Race Outcome ──────────────────────────────────────────────────────────────


class RaceOutcomeAdapter(_BaseAdapter):
    """
    Predicts finish tier: Podium / Points / Outside.

    PKL specifics:
      - Ensemble: weight*cat_proba + (1-weight)*lgb_proba  (weight = CatBoost weight)
      - 3-class classifier trained on pre-race features only
      - Features: grid, championship points, rolling averages (no lap-by-lap data)
      - classes key gives CatBoost class order (e.g. ['Outside', 'Points', 'Podium'])

    predict()       → int estimated position (Podium→2, Points→6, Outside→15)
    predict_tier()  → str tier label
    predict_proba() → dict[str, float] per-tier probabilities
    """

    model_name = "race_outcome"

    _TIER_POSITION = {"Podium": 2, "Points": 6, "Outside": 15}

    def _predict_tier_proba(self, state: dict) -> dict[str, float]:
        """Core inference — returns {tier: probability} dict."""
        grid = state.get("start_position", state.get("position", 10))
        driver_id = state.get("driver_id", "")
        season = state.get("season", 2025)

        le_driver = self._bundle["driver_encoder"]
        if driver_id in le_driver.classes_:
            driver_enc = int(le_driver.transform([driver_id])[0])
        else:
            driver_enc = -1

        # Championship / form features — use state if provided, else neutral defaults
        row = {
            "grid": grid,
            "grid_last": state.get("grid_last", grid),
            "grid_improvement": state.get("grid_improvement", 0.0),
            "driver_enc": driver_enc,
            "constructor_enc": state.get("constructor_enc", -1),
            "circuitId_encoded": state.get("circuitId_encoded", 0),
            "season": season,
            "driver_rolling_avg_finish": state.get("driver_rolling_avg_finish", 10.0),
            "constructor_rolling_avg_finish": state.get(
                "constructor_rolling_avg_finish", 10.0
            ),
            "driver_season_avg_finish": state.get("driver_season_avg_finish", 10.0),
            "driver_rolling_podiums": state.get("driver_rolling_podiums", 0.0),
            "constructor_rolling_podiums": state.get(
                "constructor_rolling_podiums", 0.0
            ),
            "driver_rolling_points_finishes": state.get(
                "driver_rolling_points_finishes", 0.3
            ),
            "driver_cum_points": state.get("driver_cum_points", 0.0),
            "driver_champ_pos": state.get("driver_champ_pos", 10.0),
            "constructor_cum_points": state.get("constructor_cum_points", 0.0),
            "constructor_champ_pos": state.get("constructor_champ_pos", 10.0),
            "driver_points_last3": state.get("driver_points_last3", 0.0),
        }

        features = self._bundle["features"]
        X = pd.DataFrame([{f: row.get(f, 0.0) for f in features}])[features].fillna(0.0)

        cat_m = self._bundle["cat"]
        lgb_m = self._bundle["lgb"]
        w = self._bundle.get("weight", 0.5)  # CatBoost weight
        classes = list(self._bundle["classes"])  # CatBoost class order

        cat_p = cat_m.predict_proba(X)[0]  # shape (3,)
        lgb_p = lgb_m.predict_proba(X)[0]  # shape (3,) — may differ in order
        lgb_cls = list(lgb_m.classes_)

        # Align LGB proba to CatBoost class order
        lgb_aligned = np.zeros(len(classes))
        for i, c in enumerate(classes):
            if c in lgb_cls:
                lgb_aligned[i] = lgb_p[lgb_cls.index(c)]

        blended = w * cat_p + (1.0 - w) * lgb_aligned
        return {cls: float(p) for cls, p in zip(classes, blended)}

    def predict_tier(self, state: dict) -> str:
        """Returns the most probable finish tier: Podium / Points / Outside."""
        if not self.loaded:
            pos = state.get("position", 10)
            if pos <= 3:
                return "Podium"
            if pos <= 10:
                return "Points"
            return "Outside"
        try:
            proba = self._predict_tier_proba(state)
            return max(proba, key=proba.get)
        except Exception as exc:
            logger.warning("RaceOutcomeAdapter.predict_tier error: %s", exc)
            pos = state.get("position", 10)
            return "Podium" if pos <= 3 else ("Points" if pos <= 10 else "Outside")

    def predict_tier_proba(self, state: dict) -> dict[str, float]:
        """Returns per-tier probability dict. Falls back to position-based heuristic."""
        if not self.loaded:
            return _heuristic_tier_proba(state)
        try:
            return self._predict_tier_proba(state)
        except Exception as exc:
            logger.warning("RaceOutcomeAdapter.predict_tier_proba error: %s", exc)
            return _heuristic_tier_proba(state)

    def predict(self, state: dict) -> int:
        """
        Returns an estimated finishing position (1–20) mapped from the predicted tier.
        Podium→2, Points→6, Outside→15.
        Falls back to current race position.
        """
        if not self.loaded:
            return state.get("position", 10)
        try:
            tier = self.predict_tier(state)
            return self._TIER_POSITION.get(tier, state.get("position", 10))
        except Exception as exc:
            logger.warning("RaceOutcomeAdapter.predict error: %s", exc)
            return state.get("position", 10)


def _heuristic_tier_proba(state: dict) -> dict[str, float]:
    pos = state.get("position", 10)
    if pos <= 3:
        return {"Podium": 0.70, "Points": 0.25, "Outside": 0.05}
    if pos <= 10:
        return {"Podium": 0.10, "Points": 0.65, "Outside": 0.25}
    return {"Podium": 0.03, "Points": 0.20, "Outside": 0.77}


# ── Convenience loader ────────────────────────────────────────────────────────


def load_all_adapters(
    tire_deg_path: Optional[str] = None,
    fuel_path: Optional[str] = None,
    driving_style_path: Optional[str] = None,
    sc_path: Optional[str] = None,
    pit_window_path: Optional[str] = None,
    race_outcome_path: Optional[str] = None,
    overtake_path: Optional[str] = None,
    project: str = "f1optimizer",
) -> dict[str, _BaseAdapter]:
    """
    Load all model adapters in one call.  Any path left as None → adapter
    runs in fallback mode (physics constants / heuristics).

    Default local paths assume models/ at repo root (as saved by training scripts):
      tire_deg_path      = "models/tire_degradation.pkl"
      fuel_path          = "models/fuel_consumption.pkl"
      driving_style_path = "models/driving_style.pkl"
      sc_path            = "models/safety_car.pkl"
      pit_window_path    = "models/pit_window.pkl"
      race_outcome_path  = "models/race_outcome.pkl"

    GCS paths (after deployment):
      "gs://f1optimizer-models/tire_degradation/latest/model.pkl"
    """
    return {
        "tire_deg": TireDegradationAdapter(tire_deg_path, project),
        "fuel": FuelConsumptionAdapter(fuel_path, project),
        "driving_style": DrivingStyleAdapter(driving_style_path, project),
        "sc": SafetyCarAdapter(sc_path, project),
        "pit_window": PitWindowAdapter(pit_window_path, project),
        "race_outcome": RaceOutcomeAdapter(race_outcome_path, project),
        "overtake": OvertakeProbAdapter(overtake_path, project),
    }


def load_local_adapters(
    models_dir: str = "models",
    project: str = "f1optimizer",
) -> dict[str, _BaseAdapter]:
    """
    Convenience: load all available models from a local models/ directory.
    OvertakeProbAdapter remains in fallback mode (model not yet pushed).
    """
    return load_all_adapters(
        tire_deg_path=os.path.join(models_dir, "tire_degradation.pkl"),
        fuel_path=os.path.join(models_dir, "fuel_consumption.pkl"),
        driving_style_path=os.path.join(models_dir, "driving_style.pkl"),
        sc_path=os.path.join(models_dir, "safety_car.pkl"),
        pit_window_path=os.path.join(models_dir, "pit_window.pkl"),
        race_outcome_path=os.path.join(models_dir, "race_outcome.pkl"),
        project=project,
    )
