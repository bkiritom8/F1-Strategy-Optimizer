"""
RL Experience Builder — generate (state, action, reward, next_state) tuples.

Iterates over historical races, extracts lap-by-lap transitions, and saves
Parquet experience replay buffers to GCS for offline RL training.

Action space:
  - pit:      bool   (did the driver pit this lap?)
  - compound: str    (compound chosen on this lap, empty if no pit)
  - mode:     str    (driving mode inferred from lap-time ratio to best)

Reward:
  - position gained / lost vs the previous lap (+1 = gained one place)

Usage:
    builder = ExperienceBuilder()
    builder.build_all(years=[2018, 2019, 2020, 2021, 2022, 2023, 2024])
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass, asdict

import pandas as pd
from google.cloud import storage

logger = logging.getLogger(__name__)

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "gs://f1optimizer-training")

# State feature columns extracted from the feature vector
STATE_COLS = [
    "lap_number",
    "position",
    "gap_to_leader",
    "gap_to_ahead",
    "tire_age_laps",
    "pit_stops_count",
    "fuel_remaining_kg",
    "last_lap_time_ms",
    "best_lap_time_ms",
    "sector1_time",
    "sector2_time",
    "sector3_time",
]


@dataclass
class Experience:
    """Single (state, action, reward, next_state) transition."""

    race_id: str
    driver_id: str
    lap_number: int

    # State features (current lap)
    position: float
    gap_to_leader: float
    gap_to_ahead: float
    tire_age_laps: float
    pit_stops_count: float
    fuel_remaining_kg: float
    last_lap_time_ms: float
    best_lap_time_ms: float
    sector1_time: float
    sector2_time: float
    sector3_time: float
    tire_compound: str
    weather: str

    # Action
    pit: int  # 1 = pitted at end of this lap
    compound: str  # new compound if pit, else ""
    driving_mode: str  # "PUSH", "BALANCED", "SAVE"

    # Reward
    reward: float  # positions gained (positive) / lost (negative)

    # Next-state features (lap+1)
    next_position: float
    next_gap_to_leader: float
    next_gap_to_ahead: float
    next_tire_age_laps: float
    next_pit_stops_count: float
    next_fuel_remaining_kg: float
    next_last_lap_time_ms: float
    next_tire_compound: str


def _infer_driving_mode(lap_time_ms: float, best_lap_time_ms: float) -> str:
    """Infer driving mode from lap time vs personal best."""
    if best_lap_time_ms <= 0 or lap_time_ms <= 0:
        return "BALANCED"
    ratio = lap_time_ms / best_lap_time_ms
    if ratio < 1.005:
        return "PUSH"
    if ratio > 1.02:
        return "SAVE"
    return "BALANCED"


def _row_to_experience(curr: pd.Series, nxt: pd.Series) -> Experience:
    """Build one Experience from two consecutive lap rows."""
    pit_flag = int(nxt.get("pit_stops_count", 0)) > int(curr.get("pit_stops_count", 0))

    return Experience(
        race_id=str(curr.get("race_id", "")),
        driver_id=str(curr.get("driver_id", "")),
        lap_number=int(curr.get("lap_number", 0)),
        # State
        position=float(curr.get("position", 0) or 0),
        gap_to_leader=float(curr.get("gap_to_leader", 0) or 0),
        gap_to_ahead=float(curr.get("gap_to_ahead", 0) or 0),
        tire_age_laps=float(curr.get("tire_age_laps", 0) or 0),
        pit_stops_count=float(curr.get("pit_stops_count", 0) or 0),
        fuel_remaining_kg=float(curr.get("fuel_remaining_kg", 0) or 0),
        last_lap_time_ms=float(curr.get("last_lap_time_ms", 0) or 0),
        best_lap_time_ms=float(curr.get("best_lap_time_ms", 0) or 0),
        sector1_time=float(curr.get("sector1_time", 0) or 0),
        sector2_time=float(curr.get("sector2_time", 0) or 0),
        sector3_time=float(curr.get("sector3_time", 0) or 0),
        tire_compound=str(curr.get("tire_compound", "") or ""),
        weather=str(curr.get("weather", "dry") or "dry"),
        # Action
        pit=int(pit_flag),
        compound=str(nxt.get("tire_compound", "") or "") if pit_flag else "",
        driving_mode=_infer_driving_mode(
            float(curr.get("last_lap_time_ms", 0) or 0),
            float(curr.get("best_lap_time_ms", 0) or 0),
        ),
        # Reward: positions gained (current - next, since lower = better)
        reward=float((curr.get("position", 0) or 0) - (nxt.get("position", 0) or 0)),
        # Next state
        next_position=float(nxt.get("position", 0) or 0),
        next_gap_to_leader=float(nxt.get("gap_to_leader", 0) or 0),
        next_gap_to_ahead=float(nxt.get("gap_to_ahead", 0) or 0),
        next_tire_age_laps=float(nxt.get("tire_age_laps", 0) or 0),
        next_pit_stops_count=float(nxt.get("pit_stops_count", 0) or 0),
        next_fuel_remaining_kg=float(nxt.get("fuel_remaining_kg", 0) or 0),
        next_last_lap_time_ms=float(nxt.get("last_lap_time_ms", 0) or 0),
        next_tire_compound=str(nxt.get("tire_compound", "") or ""),
    )


class ExperienceBuilder:
    """
    Builds offline RL experience replay buffers from historical F1 race data.

    For each race × driver pair, extracts lap-by-lap (s, a, r, s') tuples
    and saves them as partitioned Parquet to GCS.
    """

    def __init__(self, project: str = PROJECT_ID) -> None:
        self._project = project
        self._bucket_name = TRAINING_BUCKET.removeprefix("gs://")
        self._gcs_client = storage.Client(project=project)
        self._fs: object = None  # lazy FeatureStore

    def _get_feature_store(self):
        if self._fs is None:
            from ml.features.feature_store import FeatureStore

            self._fs = FeatureStore(project=self._project)
        return self._fs

    # ── Single race processing ────────────────────────────────────────────────

    def build_race(self, race_id: str) -> list[Experience]:
        """
        Build all experience tuples for a single race.

        Returns list of Experience objects (empty on data failure).
        """
        fs = self._get_feature_store()
        try:
            race_df = fs.load_race_features(race_id)
        except Exception as exc:
            logger.warning("ExperienceBuilder: cannot load %s: %s", race_id, exc)
            return []

        if race_df.empty or "driver_id" not in race_df.columns:
            return []

        experiences: list[Experience] = []
        for driver_id, grp in race_df.groupby("driver_id"):
            grp = grp.sort_values("lap_number").reset_index(drop=True)
            for i in range(len(grp) - 1):
                curr = grp.iloc[i]
                nxt = grp.iloc[i + 1]
                experiences.append(_row_to_experience(curr, nxt))

        return experiences

    # ── GCS persistence ────────────────────────────────────────────────────────

    def _save_race_experiences(
        self, race_id: str, experiences: list[Experience]
    ) -> str:
        """Save experiences for one race to GCS. Returns URI."""
        rows = [asdict(e) for e in experiences]
        df = pd.DataFrame(rows)
        safe_race = race_id.replace("/", "_")
        blob_path = f"rl_experience/{safe_race}.parquet"
        buf = io.BytesIO()
        df.to_parquet(buf, index=False)
        buf.seek(0)
        self._gcs_client.bucket(self._bucket_name).blob(blob_path).upload_from_file(
            buf, content_type="application/octet-stream"
        )
        uri = f"gs://{self._bucket_name}/{blob_path}"
        logger.info("ExperienceBuilder: saved %d tuples to %s", len(df), uri)
        return uri

    # ── Main entry point ──────────────────────────────────────────────────────

    def build_all(
        self,
        years: list[int] | None = None,
    ) -> dict[str, int]:
        """
        Build experience tuples for all races in the given years.

        Default years: 2018–2024 (telemetry available from 2018).
        Returns {race_id: num_tuples} dict.

        Prints progress per race.
        """
        if years is None:
            years = [2018, 2019, 2020, 2021, 2022, 2023, 2024]

        from ml.features.feature_pipeline import FeaturePipeline

        pipeline = FeaturePipeline(project=self._project)
        all_races = pipeline.get_available_races()

        target_races = [r for r in all_races if int(r["season"]) in set(years)]
        logger.info(
            "ExperienceBuilder: processing %d races for years=%s",
            len(target_races),
            years,
        )

        results: dict[str, int] = {}
        for i, race in enumerate(target_races, start=1):
            race_id = race["race_id"]
            race_name = race.get("raceName", race_id)
            print(
                f"[{i}/{len(target_races)}] Building experiences: {race_id} — {race_name}",
                flush=True,
            )
            experiences = self.build_race(race_id)
            if experiences:
                self._save_race_experiences(race_id, experiences)
                results[race_id] = len(experiences)
                print(f"  → {len(experiences)} tuples saved", flush=True)
            else:
                print("  → no data, skipped", flush=True)
                results[race_id] = 0

        total = sum(results.values())
        print(
            f"\nExperienceBuilder done: {total:,} total tuples across {len(results)} races."
        )
        return results
