"""
Race Simulator — replay historical F1 races lap-by-lap.

Loads data from GCS Parquet via FeaturePipeline, replays a race,
and supports strategy simulation and comparison.

Usage:
    sim = RaceSimulator("2024_1")
    state = sim.step(5)                        # RaceState at lap 5
    window = sim.get_pit_window("max_verstappen")
    result = sim.simulate_strategy(
        "max_verstappen",
        strategy=[(20, "MEDIUM"), (42, "HARD")]
    )
    comparison = sim.compare_to_actual("max_verstappen", result["strategy"])
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd
from google.cloud import storage

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "gs://f1optimizer-training")

# Pit stop time loss (seconds) — standard estimate
PIT_STOP_TIME_LOSS_S = 25.0

# Compound optimal stint lengths (laps)
COMPOUND_OPTIMAL_LAPS = {"SOFT": 20, "MEDIUM": 30, "HARD": 45, "INTER": 25, "WET": 20}

# Compound lap time penalty vs SOFT (seconds/lap, positive = slower)
COMPOUND_DELTA_S = {"SOFT": 0.0, "MEDIUM": 0.4, "HARD": 0.8, "INTER": 1.5, "WET": 2.5}

# Tire degradation rate (seconds per lap, per lap on tire)
DEG_RATE_S = {"SOFT": 0.08, "MEDIUM": 0.05, "HARD": 0.03, "INTER": 0.06, "WET": 0.04}


@dataclass
class DriverState:
    """State of a single driver at a given lap."""

    driver_id: str
    position: int
    gap_to_leader: float  # seconds
    gap_to_ahead: float  # seconds
    lap_time_ms: float
    tire_compound: str
    tire_age_laps: int
    pit_stops_count: int
    fuel_remaining_kg: float
    sector1_time: float
    sector2_time: float
    sector3_time: float


@dataclass
class RaceState:
    """Full race state at a given lap."""

    race_id: str
    lap_number: int
    total_laps: int
    drivers: list[DriverState] = field(default_factory=list)
    weather: str = "dry"
    track_temp: float = float("nan")
    air_temp: float = float("nan")
    safety_car: bool = False
    virtual_safety_car: bool = False
    yellow_flag: bool = False
    red_flag: bool = False


@dataclass
class SimulationResult:
    """Outcome of simulate_strategy()."""

    driver_id: str
    race_id: str
    strategy: list[tuple[int, str]]  # [(pit_lap, compound), ...]
    predicted_total_time_s: float
    predicted_final_position: int
    lap_times_s: list[float]


class RaceSimulator:
    """
    Replays an F1 race lap by lap using GCS Parquet historical data.

    Initialization loads data for the specified race_id.  step() returns
    a RaceState for any lap. simulate_strategy() replaces one driver's
    actual pitstops with a user-defined strategy and predicts the outcome.
    """

    def __init__(self, race_id: str, project: str = PROJECT_ID) -> None:
        self.race_id = race_id
        self._project = project
        self._pipeline: Any = None
        self._race_df: pd.DataFrame | None = None
        self._all_laps: pd.DataFrame | None = None  # raw laps for all drivers
        self._gcs_client = storage.Client(project=project)
        self._training_bucket = TRAINING_BUCKET.removeprefix("gs://")
        self._load_race()

    # ── Data loading ──────────────────────────────────────────────────────────

    def _get_pipeline(self):
        if self._pipeline is None:
            from ml.features.feature_pipeline import FeaturePipeline

            self._pipeline = FeaturePipeline(project=self._project)
        return self._pipeline

    def _load_race(self) -> None:
        """Load all feature vectors for this race into memory."""
        logger.info("RaceSimulator: loading race_id=%s", self.race_id)
        try:
            from ml.features.feature_store import FeatureStore

            fs = FeatureStore(project=self._project)
            self._race_df = fs.load_race_features(self.race_id)
        except Exception as exc:
            logger.warning(
                "FeatureStore unavailable, falling back to direct load: %s", exc
            )
            pipeline = self._get_pipeline()
            self._race_df = pipeline.build_race_features(self.race_id)

        if self._race_df is None or self._race_df.empty:
            logger.warning("RaceSimulator: no data found for race_id=%s", self.race_id)
            self._race_df = pd.DataFrame()
        else:
            logger.info(
                "RaceSimulator: loaded %d rows for race_id=%s (%d drivers)",
                len(self._race_df),
                self.race_id,
                (
                    self._race_df["driver_id"].nunique()
                    if "driver_id" in self._race_df.columns
                    else 0
                ),
            )

    # ── Core replay ───────────────────────────────────────────────────────────

    @property
    def total_laps(self) -> int:
        if self._race_df is None or self._race_df.empty:
            return 0
        return int(self._race_df["lap_number"].max())

    def step(self, lap_number: int) -> RaceState:
        """
        Return the full RaceState at the given lap.

        Includes all drivers' state and race conditions.
        """
        if self._race_df is None or self._race_df.empty:
            return RaceState(
                race_id=self.race_id,
                lap_number=lap_number,
                total_laps=0,
            )

        lap_data = self._race_df[self._race_df["lap_number"] == lap_number]

        driver_states: list[DriverState] = []
        for _, row in lap_data.iterrows():
            ds = DriverState(
                driver_id=str(row.get("driver_id", "")),
                position=int(row.get("position", 0) or 0),
                gap_to_leader=float(row.get("gap_to_leader", 0.0) or 0.0),
                gap_to_ahead=float(row.get("gap_to_ahead", 0.0) or 0.0),
                lap_time_ms=float(row.get("last_lap_time_ms", 0.0) or 0.0),
                tire_compound=str(row.get("tire_compound", "") or ""),
                tire_age_laps=int(row.get("tire_age_laps", 0) or 0),
                pit_stops_count=int(row.get("pit_stops_count", 0) or 0),
                fuel_remaining_kg=float(row.get("fuel_remaining_kg", 0.0) or 0.0),
                sector1_time=float(
                    row.get("sector1_time", float("nan")) or float("nan")
                ),
                sector2_time=float(
                    row.get("sector2_time", float("nan")) or float("nan")
                ),
                sector3_time=float(
                    row.get("sector3_time", float("nan")) or float("nan")
                ),
            )
            driver_states.append(ds)

        # Sort by position
        driver_states.sort(key=lambda d: d.position if d.position > 0 else 99)

        # Extract race conditions from first available driver row
        weather = "dry"
        track_temp = float("nan")
        air_temp = float("nan")
        if not lap_data.empty:
            first = lap_data.iloc[0]
            weather = str(first.get("weather", "dry") or "dry")
            track_temp = float(first.get("track_temp", float("nan")) or float("nan"))
            air_temp = float(first.get("air_temp", float("nan")) or float("nan"))

        return RaceState(
            race_id=self.race_id,
            lap_number=lap_number,
            total_laps=self.total_laps,
            drivers=driver_states,
            weather=weather,
            track_temp=track_temp,
            air_temp=air_temp,
        )

    def get_standings(self, lap_number: int) -> list[dict]:
        """
        Return race standings at a given lap as a list of dicts.
        [{position, driver_id, gap_to_leader, tire_compound, pit_stops_count}, ...]
        """
        state = self.step(lap_number)
        return [
            {
                "position": ds.position,
                "driver_id": ds.driver_id,
                "gap_to_leader": round(ds.gap_to_leader, 3),
                "gap_to_ahead": round(ds.gap_to_ahead, 3),
                "tire_compound": ds.tire_compound,
                "tire_age_laps": ds.tire_age_laps,
                "pit_stops_count": ds.pit_stops_count,
                "last_lap_time_ms": round(ds.lap_time_ms, 1),
            }
            for ds in state.drivers
        ]

    # ── Pit window recommendation ──────────────────────────────────────────────

    def get_pit_window(self, driver_id: str) -> dict:
        """
        Return recommended pit window for a driver based on their tire stint.

        Uses historical tire degradation: computes when the current tire's
        performance falls below what a fresh compound would deliver.
        Returns {window_start, window_end, recommended_compound, reason}.
        """
        if self._race_df is None or self._race_df.empty:
            return {
                "window_start": 25,
                "window_end": 35,
                "recommended_compound": "HARD",
                "reason": "no_data",
            }

        driver_data = self._race_df[self._race_df["driver_id"] == driver_id]
        if driver_data.empty:
            return {
                "window_start": 25,
                "window_end": 35,
                "recommended_compound": "HARD",
                "reason": "driver_not_found",
            }

        # Current tire state: last known lap
        last_lap = driver_data.sort_values("lap_number").iloc[-1]
        current_compound = str(last_lap.get("tire_compound", "MEDIUM") or "MEDIUM")
        current_tire_age = int(last_lap.get("tire_age_laps", 0) or 0)
        current_lap = int(last_lap.get("lap_number", 1) or 1)
        pit_count = int(last_lap.get("pit_stops_count", 0) or 0)
        total = self.total_laps

        # Optimal stint for current compound
        optimal = COMPOUND_OPTIMAL_LAPS.get(current_compound.upper(), 30)
        remaining_optimal = max(0, optimal - current_tire_age)

        # Window: start when tire age hits 85% of optimal, end at 110%
        window_start = max(current_lap + 1, current_lap + int(remaining_optimal * 0.85))
        window_end = min(total - 5, current_lap + int(remaining_optimal * 1.10))
        window_end = max(window_start + 2, window_end)

        # Compound recommendation: use harder compound if early in race
        laps_remaining = total - current_lap
        if pit_count == 0 and laps_remaining > 30:
            recommended = "MEDIUM" if current_compound.upper() == "SOFT" else "HARD"
        elif laps_remaining <= 15:
            recommended = "SOFT"
        else:
            recommended = "HARD" if pit_count >= 1 else "MEDIUM"

        return {
            "window_start": int(window_start),
            "window_end": int(window_end),
            "recommended_compound": recommended,
            "current_compound": current_compound,
            "current_tire_age": current_tire_age,
            "reason": "degradation_model",
        }

    # ── Strategy simulation ────────────────────────────────────────────────────

    def simulate_strategy(
        self,
        driver_id: str,
        strategy: list[tuple[int, str]],
    ) -> SimulationResult:
        """
        Simulate a custom pit strategy for a driver and predict the outcome.

        strategy: [(pit_lap, compound), ...]  — sorted ascending by lap.
        Computes total race time by:
          - Using actual lap times for non-pit laps (from historical data)
          - Adding pit stop time loss (25s) at each pit lap
          - Applying compound delta and degradation curve for new tire

        Returns SimulationResult with predicted final position and race time.
        """
        if self._race_df is None or self._race_df.empty:
            return SimulationResult(
                driver_id=driver_id,
                race_id=self.race_id,
                strategy=strategy,
                predicted_total_time_s=0.0,
                predicted_final_position=0,
                lap_times_s=[],
            )

        driver_data = self._race_df[
            self._race_df["driver_id"] == driver_id
        ].sort_values("lap_number")

        if driver_data.empty:
            return SimulationResult(
                driver_id=driver_id,
                race_id=self.race_id,
                strategy=strategy,
                predicted_total_time_s=0.0,
                predicted_final_position=0,
                lap_times_s=[],
            )

        # Build a dict of actual lap times: {lap_number: ms}
        actual_times: dict[int, float] = {}
        for _, row in driver_data.iterrows():
            lap_num = int(row.get("lap_number", 0) or 0)
            t = float(row.get("last_lap_time_ms", 0.0) or 0.0)
            if lap_num > 0 and t > 0:
                actual_times[lap_num] = t

        if not actual_times:
            return SimulationResult(
                driver_id=driver_id,
                race_id=self.race_id,
                strategy=strategy,
                predicted_total_time_s=0.0,
                predicted_final_position=0,
                lap_times_s=[],
            )

        total_laps = max(actual_times.keys())
        strategy_sorted = sorted(strategy, key=lambda x: x[0])

        # Determine compound per lap based on strategy
        pit_set = {lap for lap, _ in strategy_sorted}
        compound_map: dict[int, str] = {}
        current_compound = "SOFT"  # default starting compound
        stint_start = 1
        s_idx = 0

        for lap in range(1, total_laps + 1):
            if s_idx < len(strategy_sorted) and lap == strategy_sorted[s_idx][0]:
                current_compound = strategy_sorted[s_idx][1]
                stint_start = lap
                s_idx += 1
            compound_map[lap] = current_compound

        # Simulate lap times with degradation model
        lap_times_s: list[float] = []
        total_time_ms = 0.0

        for lap in range(1, total_laps + 1):
            base_ms = actual_times.get(
                lap,
                np.nanmean(list(actual_times.values())) if actual_times else 95000.0,
            )
            compound = compound_map.get(lap, "MEDIUM")
            tire_age = lap - stint_start + 1

            # Apply compound delta (convert to ms)
            compound_delta_ms = COMPOUND_DELTA_S.get(compound.upper(), 0.0) * 1000.0

            # Apply degradation
            deg_rate = DEG_RATE_S.get(compound.upper(), 0.05)
            deg_ms = deg_rate * max(0, tire_age - 1) * 1000.0

            # Add pit stop time loss
            pit_loss_ms = PIT_STOP_TIME_LOSS_S * 1000.0 if lap in pit_set else 0.0

            simulated_lap_ms = float(base_ms + compound_delta_ms + deg_ms + pit_loss_ms)
            lap_times_s.append(simulated_lap_ms / 1000.0)
            total_time_ms += simulated_lap_ms

        # Estimate final position by comparing total race time vs others
        pred_position = self._estimate_position(driver_id, total_time_ms)

        return SimulationResult(
            driver_id=driver_id,
            race_id=self.race_id,
            strategy=strategy_sorted,
            predicted_total_time_s=round(total_time_ms / 1000.0, 3),
            predicted_final_position=pred_position,
            lap_times_s=[round(t, 3) for t in lap_times_s],
        )

    def _estimate_position(self, driver_id: str, simulated_total_ms: float) -> int:
        """
        Estimate final position by comparing simulated total time
        against actual total race times of other drivers.
        """
        if self._race_df is None or self._race_df.empty:
            return 0

        # Compute actual total times per driver
        total_times: dict[str, float] = {}
        for drv_id, grp in self._race_df.groupby("driver_id"):
            drv_times = grp.sort_values("lap_number")["last_lap_time_ms"]
            total = pd.to_numeric(drv_times, errors="coerce").fillna(0).sum()
            total_times[str(drv_id)] = float(total)

        # Replace this driver's time with simulated
        total_times[driver_id] = simulated_total_ms

        sorted_drivers = sorted(total_times.items(), key=lambda x: x[1])
        for pos, (drv, _) in enumerate(sorted_drivers, start=1):
            if drv == driver_id:
                return pos
        return 0

    # ── Actual vs simulated comparison ────────────────────────────────────────

    def compare_to_actual(
        self,
        driver_id: str,
        strategy: list[tuple[int, str]],
    ) -> dict:
        """
        Compare a simulated strategy against what actually happened.

        Returns a dict with:
          actual_position, simulated_position, position_delta,
          actual_total_time_s, simulated_total_time_s, time_delta_s,
          actual_strategy, simulated_strategy
        """
        sim = self.simulate_strategy(driver_id, strategy)

        # Actual final position and race time
        actual_position = 0
        actual_total_ms = 0.0
        actual_pit_laps: list[tuple[int, str]] = []

        if self._race_df is not None and not self._race_df.empty:
            drv_data = self._race_df[self._race_df["driver_id"] == driver_id]
            if not drv_data.empty:
                last = drv_data.sort_values("lap_number").iloc[-1]
                actual_position = int(last.get("position", 0) or 0)
                actual_total_ms = float(
                    pd.to_numeric(drv_data["last_lap_time_ms"], errors="coerce")
                    .fillna(0)
                    .sum()
                )
                # Actual pit laps
                pit_rows = drv_data[
                    (
                        drv_data.get("pit_stop_flag", pd.Series(dtype=int)).eq(1)
                        if "pit_stop_flag" in drv_data.columns
                        else pd.Series(False, index=drv_data.index)
                    )
                ]
                for _, pr in pit_rows.iterrows():
                    compound = str(pr.get("tire_compound", "") or "")
                    actual_pit_laps.append(
                        (int(pr.get("lap_number", 0) or 0), compound)
                    )

        return {
            "driver_id": driver_id,
            "race_id": self.race_id,
            "actual_position": actual_position,
            "simulated_position": sim.predicted_final_position,
            "position_delta": actual_position - sim.predicted_final_position,
            "actual_total_time_s": round(actual_total_ms / 1000.0, 3),
            "simulated_total_time_s": sim.predicted_total_time_s,
            "time_delta_s": round(
                actual_total_ms / 1000.0 - sim.predicted_total_time_s, 3
            ),
            "actual_strategy": actual_pit_laps,
            "simulated_strategy": strategy,
        }

    # ── GCS persistence ────────────────────────────────────────────────────────

    def save_simulation(self, result: SimulationResult, run_id: str = "") -> str:
        """
        Save a SimulationResult to GCS as Parquet.
        Returns the GCS URI.
        """
        rows = []
        for lap_idx, lt in enumerate(result.lap_times_s, start=1):
            rows.append(
                {
                    "race_id": result.race_id,
                    "driver_id": result.driver_id,
                    "run_id": run_id,
                    "lap_number": lap_idx,
                    "lap_time_s": lt,
                    "strategy": str(result.strategy),
                    "predicted_final_position": result.predicted_final_position,
                    "predicted_total_time_s": result.predicted_total_time_s,
                }
            )
        df = pd.DataFrame(rows)

        safe_race = self.race_id.replace("/", "_")
        blob_path = (
            f"simulations/{safe_race}/{result.driver_id}_{run_id or 'sim'}.parquet"
        )
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        self._gcs_client.bucket(self._training_bucket).blob(blob_path).upload_from_file(
            buf, content_type="application/octet-stream"
        )
        uri = f"gs://{self._training_bucket}/{blob_path}"
        logger.info("RaceSimulator: saved simulation to %s", uri)
        return uri
