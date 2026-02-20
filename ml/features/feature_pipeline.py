"""
Feature Pipeline — derives ML features from raw DB tables.

Computes:
  1. Tire degradation curves     — lap time delta vs tire age per compound
  2. Gap evolution               — gap_to_car_ahead delta per lap
  3. Undercut / overcut windows  — position change after pit stop
  4. Weather impact factors      — lap time delta vs track condition
  5. Compound one-hot encoding
  6. Fuel load estimate          — decreasing linear model from lap 1
  7. Safety car probability      — rolling window over lap_time anomalies

Reads from Cloud SQL via FeatureStore.
Writes enriched Parquet to GCS.

Usage (runs as part of the KFP feature_engineering component, or standalone
      as a Cloud Run Job):
    pipeline = FeaturePipeline()
    df = pipeline.run(years=list(range(2018, 2026)))
    uri = pipeline.write(df)
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ml.features.feature_store import FeatureStore

logger = logging.getLogger(__name__)

TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "gs://f1optimizer-training")

# Fuel burn rate: assume 110kg fuel over ~60 laps → ~1.83 kg/lap → ~0.03s/lap lift
FUEL_BURN_RATE_MS_PER_LAP = 30.0

# Compounds in degradation order (fastest → slowest)
COMPOUND_ORDER = ["SOFT", "MEDIUM", "HARD", "INTER", "WET"]


class FeaturePipeline:
    """Derives ML-ready features from raw F1 data."""

    def __init__(self) -> None:
        self._feature_store = FeatureStore()

    # ── Main entry point ──────────────────────────────────────────────────────

    def run(self, years: list[int]) -> pd.DataFrame:
        """
        Load raw data for `years`, compute all derived features,
        return enriched DataFrame.
        """
        logger.info("FeaturePipeline: loading years=%s", years)
        df = self._feature_store.load_multi_season_features(years)
        logger.info("FeaturePipeline: raw rows=%d", len(df))

        df = self._sort(df)
        df = self._encode_compounds(df)
        df = self._tire_degradation(df)
        df = self._gap_evolution(df)
        df = self._undercut_windows(df)
        df = self._fuel_load_estimate(df)
        df = self._safety_car_probability(df)
        df = self._weather_impact(df)
        df = self._clean(df)

        logger.info(
            "FeaturePipeline: enriched rows=%d, cols=%d", len(df), len(df.columns)
        )
        return df

    def write(self, df: pd.DataFrame, label: str = "") -> str:
        """Write enriched DataFrame to GCS. Returns GCS URI."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        suffix = f"_{label}" if label else ""
        gcs_path = f"features/{ts}{suffix}/laps_enriched.parquet"
        return self._feature_store.write_to_gcs(df, gcs_path)

    # ── Feature computations ──────────────────────────────────────────────────

    def _sort(self, df: pd.DataFrame) -> pd.DataFrame:
        return df.sort_values(["race_id", "driver_id", "lap_number"]).reset_index(
            drop=True
        )

    def _encode_compounds(self, df: pd.DataFrame) -> pd.DataFrame:
        """One-hot encode tire_compound."""
        if "tire_compound" not in df.columns:
            for c in COMPOUND_ORDER:
                df[f"compound_{c}"] = 0
            return df
        dummies = pd.get_dummies(
            df["tire_compound"].str.upper().fillna("UNKNOWN"), prefix="compound"
        )
        # Ensure all expected columns exist
        for c in COMPOUND_ORDER:
            col = f"compound_{c}"
            if col not in dummies.columns:
                dummies[col] = 0
        df = pd.concat([df, dummies], axis=1)
        return df

    def _tire_degradation(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute lap-time degradation signal:
          - lap_time_delta: lap time change vs previous lap (same driver/race)
          - deg_rate: rolling 3-lap average of lap_time_delta / tire_age_laps
        """
        grp = df.groupby(["race_id", "driver_id"])

        df["lap_time_delta"] = grp["lap_time_ms"].diff()

        df["deg_rate"] = df["lap_time_delta"] / df["tire_age_laps"].clip(lower=1)
        df["deg_rate_roll3"] = grp["deg_rate"].transform(
            lambda s: s.rolling(3, min_periods=1).mean()
        )

        # Compound-specific mean degradation (global, not per-race)
        if "tire_compound" in df.columns:
            compound_deg = (
                df.groupby("tire_compound")["deg_rate"]
                .transform("mean")
                .rename("compound_avg_deg_rate")
            )
            df["compound_avg_deg_rate"] = compound_deg
        else:
            df["compound_avg_deg_rate"] = 0.0

        return df

    def _gap_evolution(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Gap dynamics:
          - gap_delta: change in gap_to_car_ahead vs previous lap
          - gap_trend: rolling 5-lap slope of gap_to_car_ahead (positive = falling back)
        """
        grp = df.groupby(["race_id", "driver_id"])
        df["gap_delta"] = grp["gap_to_car_ahead_ms"].diff()

        def rolling_slope(s: pd.Series) -> pd.Series:
            def _slope(window: pd.Series) -> float:
                if len(window) < 2:
                    return 0.0
                x = np.arange(len(window), dtype=float)
                return float(np.polyfit(x, window.values, 1)[0])

            return s.rolling(5, min_periods=2).apply(_slope, raw=False)

        df["gap_trend"] = grp["gap_to_car_ahead_ms"].transform(rolling_slope)
        return df

    def _undercut_windows(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        For laps where a pit stop occurred, compute:
          - position_after_pit: position 2 laps after the stop
          - position_gain: positions gained by stopping (positive = gained)
          - undercut_success: 1 if gained >= 1 position
        """
        df["position_after_pit"] = np.nan
        df["position_gain"] = np.nan
        df["undercut_success"] = 0

        if "pit_stop_flag" not in df.columns:
            return df

        pit_mask = df["pit_stop_flag"] == 1
        pit_rows = df[pit_mask].index

        for idx in pit_rows:
            row = df.loc[idx]
            future = df[
                (df["race_id"] == row["race_id"])
                & (df["driver_id"] == row["driver_id"])
                & (df["lap_number"] == row["lap_number"] + 2)
            ]
            if not future.empty:
                pos_after = future.iloc[0]["position"]
                gain = row["position"] - pos_after
                df.loc[idx, "position_after_pit"] = pos_after
                df.loc[idx, "position_gain"] = gain
                df.loc[idx, "undercut_success"] = int(gain >= 1)

        return df

    def _fuel_load_estimate(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Estimate remaining fuel load as a fraction of lap 1.
        fuel_load_pct = max(0, 1 - (lap_number - 1) / max_laps_in_race)
        """
        if "lap_number" not in df.columns:
            df["fuel_load_pct"] = 1.0
            return df

        max_laps = df.groupby("race_id")["lap_number"].transform("max").clip(lower=1)
        df["fuel_load_pct"] = (1.0 - (df["lap_number"] - 1) / max_laps).clip(lower=0.0)

        # Fuel-corrected lap time: remove estimated fuel effect
        df["lap_time_fuel_corrected_ms"] = (
            df.get("lap_time_ms", 0)
            - (1.0 - df["fuel_load_pct"]) * FUEL_BURN_RATE_MS_PER_LAP
        )
        return df

    def _safety_car_probability(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Estimate safety car probability per lap using lap time anomaly.
        A sudden drop in lap times for many drivers indicates VSC/SC.
        sc_prob: rolling average of (lap_time < median - 2*std) across drivers.
        """
        if "lap_time_ms" not in df.columns:
            df["sc_prob"] = 0.0
            return df

        race_lap_stats = (
            df.groupby(["race_id", "lap_number"])["lap_time_ms"]
            .agg(["median", "std"])
            .reset_index()
        )
        race_lap_stats.columns = ["race_id", "lap_number", "lap_median", "lap_std"]

        df = df.merge(race_lap_stats, on=["race_id", "lap_number"], how="left")
        df["lap_std"] = df["lap_std"].fillna(1)
        df["sc_anomaly"] = (
            df["lap_time_ms"] < (df["lap_median"] - 2 * df["lap_std"])
        ).astype(float)

        df["sc_prob"] = df.groupby(["race_id", "driver_id"])["sc_anomaly"].transform(
            lambda s: s.rolling(3, min_periods=1).mean()
        )
        df = df.drop(columns=["lap_median", "lap_std", "sc_anomaly"])
        return df

    def _weather_impact(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Estimate weather impact factor from lap time deviation vs circuit baseline.
        weather_delta_ms: lap time - circuit_baseline_ms
        Positive = slower than normal (wet/degraded conditions).
        """
        circuit_baseline = (
            df.groupby(["circuit_id", "year"])["lap_time_ms"]
            .transform("median")
            .rename("circuit_baseline_ms")
        )
        df["circuit_baseline_ms"] = circuit_baseline
        df["weather_delta_ms"] = df["lap_time_ms"] - df["circuit_baseline_ms"]
        return df

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop helper columns, fill NaNs, clip outliers."""
        # Fill numeric NaNs with 0
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        df[numeric_cols] = df[numeric_cols].fillna(0)

        # Clip extreme lap time deltas (safety car outlaps, anomalies)
        if "lap_time_delta" in df.columns:
            df["lap_time_delta"] = df["lap_time_delta"].clip(-5000, 5000)
        if "gap_delta" in df.columns:
            df["gap_delta"] = df["gap_delta"].clip(-30000, 30000)

        return df

    def close(self) -> None:
        self._feature_store.close()

    def __enter__(self) -> "FeaturePipeline":
        return self

    def __exit__(self, *_) -> None:
        self.close()
