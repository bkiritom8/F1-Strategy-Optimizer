"""
Strategy Validator — evaluate a strategy model against held-out race data.

Runs the RaceSimulator on a held-out set of races and measures:
  - Position delta vs actual (simulated_position - actual_position)
  - Pit timing accuracy (fraction of stops within ±2 laps of actual)
  - Tire compound accuracy (fraction of stops with correct compound)

Results saved to gs://f1optimizer-training/validation/.

Usage:
    validator = StrategyValidator()
    report = validator.validate(years=[2024])
    print(report.mean_position_delta)
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any

import pandas as pd
from google.cloud import storage

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "gs://f1optimizer-training")

# Tolerance for pit timing accuracy (±N laps)
PIT_TIMING_TOLERANCE = 2


@dataclass
class RaceValidationResult:
    """Validation metrics for a single race."""

    race_id: str
    driver_id: str
    actual_position: int
    simulated_position: int
    position_delta: int  # simulated - actual (negative = better prediction)
    pit_timing_matches: int
    pit_timing_total: int
    compound_matches: int
    compound_total: int


@dataclass
class ValidationReport:
    """Aggregate validation report across all validated races."""

    years: list[int]
    races_validated: int
    drivers_validated: int
    mean_position_delta: float
    mae_position: float  # mean absolute error
    pit_timing_accuracy: float  # fraction within ±PIT_TIMING_TOLERANCE laps
    compound_accuracy: float  # fraction correct
    per_race: list[RaceValidationResult] = field(default_factory=list)
    gcs_uri: str = ""


class StrategyValidator:
    """
    Validates strategy predictions against historical race outcomes.

    If a model is provided it must implement:
        model.recommend(state_df: pd.DataFrame) -> [(pit_lap, compound), ...]

    Without a model, uses RaceSimulator.get_pit_window() (rule-based).
    """

    def __init__(self, model: Any = None, project: str = PROJECT_ID) -> None:
        self._model = model
        self._project = project
        self._bucket_name = TRAINING_BUCKET.removeprefix("gs://")
        self._gcs_client = storage.Client(project=project)

    # ── Strategy extraction ────────────────────────────────────────────────────

    def _predict_strategy(
        self, sim, driver_id: str, race_df: pd.DataFrame
    ) -> list[tuple[int, str]]:
        """
        Predict pit strategy for a driver using the model or fallback heuristic.

        Returns [(pit_lap, compound), ...].
        """
        if self._model is not None:
            try:
                return self._model.recommend(race_df)
            except Exception as exc:
                logger.debug("Model predict failed, using heuristic: %s", exc)

        # Rule-based fallback: call get_pit_window() once and build a 1-stop strategy
        window = sim.get_pit_window(driver_id)
        pit_lap = (window["window_start"] + window["window_end"]) // 2
        compound = window.get("recommended_compound", "MEDIUM")
        return [(pit_lap, compound)]

    def _extract_actual_strategy(
        self, race_df: pd.DataFrame, driver_id: str
    ) -> list[tuple[int, str]]:
        """Extract actual pit stops from historical data."""
        drv = race_df[race_df["driver_id"] == driver_id].sort_values("lap_number")
        if drv.empty:
            return []
        if "pit_stop_flag" not in drv.columns:
            return []
        pit_rows = drv[drv["pit_stop_flag"] == 1]
        actual: list[tuple[int, str]] = []
        for _, row in pit_rows.iterrows():
            lap = int(row.get("lap_number", 0) or 0)
            compound = str(row.get("tire_compound", "") or "")
            actual.append((lap, compound))
        return actual

    # ── Accuracy metrics ──────────────────────────────────────────────────────

    @staticmethod
    def _timing_accuracy(
        predicted: list[tuple[int, str]], actual: list[tuple[int, str]]
    ) -> tuple[int, int]:
        """
        Count how many predicted pit laps fall within ±PIT_TIMING_TOLERANCE
        of an actual pit lap.
        Returns (matches, total_predicted).
        """
        if not predicted:
            return 0, 0
        matches = 0
        actual_laps = [a[0] for a in actual]
        for p_lap, _ in predicted:
            if any(abs(p_lap - a_lap) <= PIT_TIMING_TOLERANCE for a_lap in actual_laps):
                matches += 1
        return matches, len(predicted)

    @staticmethod
    def _compound_accuracy(
        predicted: list[tuple[int, str]], actual: list[tuple[int, str]]
    ) -> tuple[int, int]:
        """
        Count compound matches between predicted and actual (by stop index).
        Returns (matches, total).
        """
        n = min(len(predicted), len(actual))
        if n == 0:
            return 0, 0
        matches = sum(
            1 for i in range(n) if predicted[i][1].upper() == actual[i][1].upper()
        )
        return matches, n

    # ── Main validation ───────────────────────────────────────────────────────

    def validate(
        self,
        years: list[int] | None = None,
    ) -> ValidationReport:
        """
        Run validation on all races in the given years (default: 2024).

        For each race × driver:
          1. Predict strategy (model or heuristic)
          2. Simulate that strategy
          3. Compare against actual race outcome

        Returns a ValidationReport and saves it to GCS.
        """
        if years is None:
            years = [2024]

        from ml.features.feature_pipeline import FeaturePipeline
        from pipeline.simulator.race_simulator import RaceSimulator
        from ml.features.feature_store import FeatureStore

        pipeline = FeaturePipeline(project=self._project)
        all_races = pipeline.get_available_races()
        target_races = [r for r in all_races if int(r["season"]) in set(years)]

        logger.info(
            "StrategyValidator: validating %d races for years=%s",
            len(target_races),
            years,
        )

        per_race: list[RaceValidationResult] = []
        fs = FeatureStore(project=self._project)

        for race in target_races:
            race_id = race["race_id"]
            logger.info("StrategyValidator: processing %s", race_id)
            try:
                race_df = fs.load_race_features(race_id)
                if race_df.empty:
                    continue
                sim = RaceSimulator(race_id, project=self._project)
            except Exception as exc:
                logger.warning("Skipping %s: %s", race_id, exc)
                continue

            driver_ids = (
                race_df["driver_id"].unique().tolist()
                if "driver_id" in race_df.columns
                else []
            )
            for driver_id in driver_ids:
                drv_df = race_df[race_df["driver_id"] == driver_id]
                if drv_df.empty:
                    continue
                try:
                    predicted_strat = self._predict_strategy(sim, driver_id, drv_df)
                    sim_result = sim.simulate_strategy(driver_id, predicted_strat)
                    actual_strat = self._extract_actual_strategy(race_df, driver_id)

                    # Actual position from last lap
                    last_lap = drv_df.sort_values("lap_number").iloc[-1]
                    actual_pos = int(last_lap.get("position", 0) or 0)

                    t_match, t_total = self._timing_accuracy(
                        predicted_strat, actual_strat
                    )
                    c_match, c_total = self._compound_accuracy(
                        predicted_strat, actual_strat
                    )

                    per_race.append(
                        RaceValidationResult(
                            race_id=race_id,
                            driver_id=driver_id,
                            actual_position=actual_pos,
                            simulated_position=sim_result.predicted_final_position,
                            position_delta=sim_result.predicted_final_position
                            - actual_pos,
                            pit_timing_matches=t_match,
                            pit_timing_total=t_total,
                            compound_matches=c_match,
                            compound_total=c_total,
                        )
                    )
                except Exception as exc:
                    logger.debug("Driver %s/%s failed: %s", race_id, driver_id, exc)

        # Aggregate metrics
        if per_race:
            deltas = [r.position_delta for r in per_race]
            mean_delta = sum(deltas) / len(deltas)
            mae = sum(abs(d) for d in deltas) / len(deltas)

            t_matches = sum(r.pit_timing_matches for r in per_race)
            t_total = sum(r.pit_timing_total for r in per_race)
            pit_acc = t_matches / t_total if t_total > 0 else 0.0

            c_matches = sum(r.compound_matches for r in per_race)
            c_total = sum(r.compound_total for r in per_race)
            cmp_acc = c_matches / c_total if c_total > 0 else 0.0
        else:
            mean_delta = mae = pit_acc = cmp_acc = 0.0

        report = ValidationReport(
            years=years,
            races_validated=len({r.race_id for r in per_race}),
            drivers_validated=len(per_race),
            mean_position_delta=round(mean_delta, 3),
            mae_position=round(mae, 3),
            pit_timing_accuracy=round(pit_acc, 4),
            compound_accuracy=round(cmp_acc, 4),
            per_race=per_race,
        )

        # Save to GCS
        try:
            report.gcs_uri = self._save_report(report)
        except Exception as exc:
            logger.warning("Could not save report to GCS: %s", exc)

        logger.info(
            "StrategyValidator: done — %d races, %d drivers, "
            "mean_pos_delta=%.2f, pit_acc=%.2%%, compound_acc=%.2%%",
            report.races_validated,
            report.drivers_validated,
            report.mean_position_delta,
            report.pit_timing_accuracy * 100,
            report.compound_accuracy * 100,
        )
        return report

    def _save_report(self, report: ValidationReport) -> str:
        """Serialize ValidationReport to Parquet and upload to GCS."""
        rows = [asdict(r) for r in report.per_race]
        if not rows:
            rows = [{"races_validated": report.races_validated}]
        df = pd.DataFrame(rows)
        # Attach aggregate metrics
        for key in [
            "mean_position_delta",
            "mae_position",
            "pit_timing_accuracy",
            "compound_accuracy",
        ]:
            df[key] = getattr(report, key)

        years_str = "_".join(str(y) for y in sorted(report.years))
        blob_path = f"validation/report_{years_str}.parquet"
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        self._gcs_client.bucket(self._bucket_name).blob(blob_path).upload_from_file(
            buf, content_type="application/octet-stream"
        )
        uri = f"gs://{self._bucket_name}/{blob_path}"
        logger.info("StrategyValidator: saved report to %s", uri)
        return uri
