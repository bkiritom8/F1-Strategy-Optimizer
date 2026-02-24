"""
Feature Pipeline — GCS Parquet → lap-by-lap state vectors.

Reads directly from gs://f1optimizer-data-lake/processed/ using
google-cloud-storage + pyarrow.  No Cloud SQL required.

Data sources (all in processed/):
  laps_all.parquet          columns: driverId, position, time, season, round, lap
  pit_stops.parquet         columns: driverId, lap, stop, time, duration, season, round
  telemetry_laps_all.parquet columns: Driver, LapNumber, LapTime, Sector1Time,
                             Sector2Time, Sector3Time, Compound, TyreLife, ..., season, round
  race_results.parquet      columns: number, position, ..., Driver(dict), season, round, raceName
  drivers.parquet           columns: driverId, code, givenName, familyName, nationality, ...
  circuits.parquet          columns: circuitId, circuitName, ...

race_id convention: "{season}_{round}"  e.g. "2024_1"
driver_id convention: Ergast driverRef string e.g. "max_verstappen"

Usage:
    pipeline = FeaturePipeline()
    df = pipeline.build_state_vector("2024_1", "max_verstappen")
    races = pipeline.get_available_races()
    history = pipeline.get_driver_history("lewis_hamilton")
"""

from __future__ import annotations

import io
import logging
import re
from typing import Any

import numpy as np
import pandas as pd
from google.cloud import storage

logger = logging.getLogger(__name__)

DATA_BUCKET = "f1optimizer-data-lake"
PROCESSED_PREFIX = "processed"
PROJECT_ID = "f1optimizer"

# Fuel: 110 kg start, burns ~1.8 kg/lap over ~60 laps
FUEL_START_KG = 110.0

# Typical compound stint lengths (laps) for pit window heuristic
COMPOUND_STINT = {"SOFT": 20, "MEDIUM": 30, "HARD": 45, "INTER": 25, "WET": 20}


def _parse_race_id(race_id: str) -> tuple[int, int]:
    """Parse "2024_1" → (2024, 1)."""
    parts = str(race_id).split("_")
    if len(parts) != 2:
        raise ValueError(f"race_id must be '{{season}}_{{round}}', got: {race_id!r}")
    return int(parts[0]), int(parts[1])


def _parse_lap_time_ms(time_val: Any) -> float:
    """Convert lap time string '1:37.284' or float seconds to milliseconds."""
    if time_val is None or (isinstance(time_val, float) and np.isnan(time_val)):
        return np.nan
    s = str(time_val).strip()
    if not s or s in ("nan", "None", ""):
        return np.nan
    # Already numeric (seconds)
    try:
        return float(s) * 1000.0
    except ValueError:
        pass
    # "1:37.284" or "37.284"
    match = re.match(r"^(\d+):(\d+\.?\d*)$", s)
    if match:
        return (int(match.group(1)) * 60 + float(match.group(2))) * 1000.0
    return np.nan


class FeaturePipeline:
    """
    Builds lap-by-lap ML state vectors from GCS Parquet data.

    All Parquet files are loaded lazily and cached in memory for the
    lifetime of this object.
    """

    def __init__(self, project: str = PROJECT_ID, bucket: str = DATA_BUCKET) -> None:
        self._project = project
        self._bucket_name = bucket
        self._gcs = storage.Client(project=project)
        self._cache: dict[str, pd.DataFrame] = {}

    # ── Internal data loading ─────────────────────────────────────────────────

    def _load(self, name: str) -> pd.DataFrame:
        """Load a Parquet file from GCS into a cached DataFrame."""
        if name in self._cache:
            return self._cache[name]
        blob_path = f"{PROCESSED_PREFIX}/{name}.parquet"
        logger.info("FeaturePipeline: loading gs://%s/%s", self._bucket_name, blob_path)
        buf = io.BytesIO()
        self._gcs.bucket(self._bucket_name).blob(blob_path).download_to_file(buf)
        buf.seek(0)
        df = pd.read_parquet(buf)
        self._cache[name] = df
        logger.info(
            "FeaturePipeline: loaded %s — %d rows, %d cols",
            name,
            len(df),
            len(df.columns),
        )
        return df

    def _laps(self) -> pd.DataFrame:
        return self._load("laps_all")

    def _pit_stops(self) -> pd.DataFrame:
        return self._load("pit_stops")

    def _race_results(self) -> pd.DataFrame:
        return self._load("race_results")

    def _drivers(self) -> pd.DataFrame:
        return self._load("drivers")

    def _telemetry_laps(self) -> pd.DataFrame:
        return self._load("telemetry_laps_all")

    # ── Driver code mapping ───────────────────────────────────────────────────

    def _driver_code(self, driver_id: str) -> str | None:
        """Map Ergast driverRef (e.g. 'max_verstappen') to FastF1 3-letter code ('VER')."""
        drv = self._drivers()
        if "driverId" not in drv.columns or "code" not in drv.columns:
            return None
        row = drv[drv["driverId"] == driver_id]
        if row.empty:
            return None
        code = row.iloc[0]["code"]
        return str(code) if pd.notna(code) else None

    # ── Public API ────────────────────────────────────────────────────────────

    def get_available_races(self) -> list[dict]:
        """
        Return list of all available races in the dataset.

        Each entry: {race_id, season, round, raceName, circuitId}
        """
        laps = self._laps()
        required = {"season", "round"}
        if not required.issubset(laps.columns):
            logger.warning("laps_all.parquet missing season/round columns")
            return []

        # Try to get raceName from race_results
        try:
            results = self._race_results()
            race_meta_cols = [
                c
                for c in ["season", "round", "raceName", "circuitId"]
                if c in results.columns
            ]
            race_meta = results[race_meta_cols].drop_duplicates(["season", "round"])
        except Exception:
            race_meta = None

        unique_races = (
            laps[["season", "round"]].drop_duplicates().sort_values(["season", "round"])
        )
        races = []
        for _, row in unique_races.iterrows():
            season, rnd = int(row["season"]), int(row["round"])
            race_id = f"{season}_{rnd}"
            entry: dict = {"race_id": race_id, "season": season, "round": rnd}
            if race_meta is not None:
                meta_row = race_meta[
                    (race_meta["season"] == season) & (race_meta["round"] == rnd)
                ]
                if not meta_row.empty:
                    for col in ["raceName", "circuitId"]:
                        if col in meta_row.columns:
                            entry[col] = meta_row.iloc[0][col]
            races.append(entry)
        return races

    def get_driver_history(self, driver_id: str) -> dict:
        """
        Return career statistics for a driver.

        Returns {driver_id, races, wins, podiums, points_total, seasons, ...}
        """
        try:
            results = self._race_results()
        except Exception as exc:
            logger.warning("Could not load race_results: %s", exc)
            return {"driver_id": driver_id, "races": 0}

        # Driver column may be a nested dict string; try parsing driverId from it
        if "driverId" in results.columns:
            drv_df = results[results["driverId"] == driver_id]
        elif "Driver" in results.columns:
            # Try to extract driverId from dict-like string column
            try:
                drv_df = results[
                    results["Driver"]
                    .astype(str)
                    .str.contains(f"'driverId': '{driver_id}'", regex=False)
                ]
            except Exception:
                drv_df = pd.DataFrame()
        else:
            drv_df = pd.DataFrame()

        if drv_df.empty:
            # Try by partial match on laps
            try:
                laps = self._laps()
                drv_laps = laps[laps["driverId"] == driver_id]
                if drv_laps.empty:
                    return {"driver_id": driver_id, "races": 0}
                seasons = sorted(drv_laps["season"].unique().tolist())
                races = drv_laps[["season", "round"]].drop_duplicates()
                return {
                    "driver_id": driver_id,
                    "races": len(races),
                    "seasons": [int(s) for s in seasons],
                    "wins": 0,
                    "podiums": 0,
                    "points_total": 0.0,
                }
            except Exception as exc:
                logger.warning("get_driver_history fallback failed: %s", exc)
                return {"driver_id": driver_id, "races": 0}

        stats: dict = {"driver_id": driver_id, "races": len(drv_df)}
        if "position" in drv_df.columns:
            pos = pd.to_numeric(drv_df["position"], errors="coerce")
            stats["wins"] = int((pos == 1).sum())
            stats["podiums"] = int((pos <= 3).sum())
        if "points" in drv_df.columns:
            pts = pd.to_numeric(drv_df["points"], errors="coerce").fillna(0)
            stats["points_total"] = float(pts.sum())
        if "season" in drv_df.columns:
            stats["seasons"] = sorted([int(s) for s in drv_df["season"].unique()])
        return stats

    # ── State vector construction ─────────────────────────────────────────────

    def build_state_vector(self, race_id: str, driver_id: str) -> pd.DataFrame:
        """
        Build a lap-by-lap state vector for one driver in one race.

        Returns a DataFrame with one row per lap containing all state features.
        Returns empty DataFrame if data not found.
        """
        season, rnd = _parse_race_id(race_id)

        # ── 1. Lap times for all drivers (needed for gap computation) ──────────
        all_laps = self._laps()
        race_mask = (all_laps["season"] == season) & (all_laps["round"] == rnd)
        race_laps = all_laps[race_mask].copy()
        if race_laps.empty:
            logger.warning("No lap data for race_id=%s", race_id)
            return pd.DataFrame()

        # Parse lap time to ms
        race_laps["lap_time_ms"] = race_laps["time"].apply(_parse_lap_time_ms)
        race_laps["lap_number"] = pd.to_numeric(
            race_laps["lap"], errors="coerce"
        ).astype("Int64")

        # ── 2. Compute gaps ────────────────────────────────────────────────────
        race_laps = race_laps.sort_values(["driverId", "lap_number"]).reset_index(
            drop=True
        )
        race_laps["cum_time_ms"] = race_laps.groupby("driverId")["lap_time_ms"].cumsum()

        # Leader at each lap = driver with minimum cumulative time
        leader = (
            race_laps.groupby("lap_number")["cum_time_ms"]
            .min()
            .reset_index()
            .rename(columns={"cum_time_ms": "leader_cum_time_ms"})
        )
        race_laps = race_laps.merge(leader, on="lap_number", how="left")
        race_laps["gap_to_leader"] = (
            race_laps["cum_time_ms"] - race_laps["leader_cum_time_ms"]
        ) / 1000.0

        # Gap to car ahead: sort by cum_time at each lap, diff between consecutive
        race_laps_sorted = race_laps.sort_values(["lap_number", "cum_time_ms"])
        race_laps_sorted["gap_to_ahead"] = (
            race_laps_sorted.groupby("lap_number")["cum_time_ms"].diff() / 1000.0
        )
        race_laps = race_laps.merge(
            race_laps_sorted[["driverId", "lap_number", "gap_to_ahead"]],
            on=["driverId", "lap_number"],
            how="left",
        )

        # ── 3. Filter to target driver ─────────────────────────────────────────
        driver_laps = race_laps[race_laps["driverId"] == driver_id].copy()
        if driver_laps.empty:
            logger.warning(
                "No lap data for driver_id=%s in race_id=%s", driver_id, race_id
            )
            return pd.DataFrame()

        driver_laps = driver_laps.sort_values("lap_number").reset_index(drop=True)

        # Best lap so far (cumulative min)
        driver_laps["best_lap_time_ms"] = driver_laps["lap_time_ms"].cummin()
        driver_laps["last_lap_time_ms"] = driver_laps["lap_time_ms"]

        # ── 4. Pit stop count per lap ──────────────────────────────────────────
        try:
            pit = self._pit_stops()
            driver_pits = pit[
                (pit["season"] == season)
                & (pit["round"] == rnd)
                & (pit["driverId"] == driver_id)
            ].copy()
            driver_pits["pit_lap"] = pd.to_numeric(
                driver_pits["lap"], errors="coerce"
            ).astype("Int64")
            pit_laps = set(driver_pits["pit_lap"].dropna().tolist())

            # Cumulative pit count: count stops that happened on or before each lap
            driver_laps["pit_stop_flag"] = driver_laps["lap_number"].apply(
                lambda lap_n: 1 if lap_n in pit_laps else 0
            )
            driver_laps["pit_stops_count"] = driver_laps["pit_stop_flag"].cumsum()
        except Exception as exc:
            logger.warning("Pit stop data unavailable: %s", exc)
            driver_laps["pit_stop_flag"] = 0
            driver_laps["pit_stops_count"] = 0

        # ── 5. Fuel estimate ───────────────────────────────────────────────────
        max_laps = int(driver_laps["lap_number"].max()) if len(driver_laps) > 0 else 60
        driver_laps["fuel_remaining_kg"] = FUEL_START_KG * (
            1.0 - (driver_laps["lap_number"] - 1) / max(max_laps, 1)
        ).clip(lower=0.0)

        # ── 6. FastF1 telemetry lap data (2018+, best effort) ─────────────────
        driver_code = self._driver_code(driver_id)
        telem_cols = {
            "tire_compound": np.nan,
            "tire_age_laps": 0,
            "sector1_time": np.nan,
            "sector2_time": np.nan,
            "sector3_time": np.nan,
            "track_temp": np.nan,
            "air_temp": np.nan,
            "weather": "dry",
        }
        for col, default in telem_cols.items():
            driver_laps[col] = default

        if driver_code is not None:
            try:
                tel = self._telemetry_laps()
                tel_mask = (
                    (tel["season"] == season)
                    & (tel["round"] == rnd)
                    & (tel["Driver"] == driver_code)
                )
                driver_tel = tel[tel_mask].copy()
                if not driver_tel.empty:
                    driver_tel["lap_number"] = pd.to_numeric(
                        driver_tel["LapNumber"], errors="coerce"
                    ).astype("Int64")
                    # Merge telemetry into driver_laps
                    tel_feature_map = {
                        "Compound": "tire_compound",
                        "TyreLife": "tire_age_laps",
                        "Sector1Time": "sector1_time",
                        "Sector2Time": "sector2_time",
                        "Sector3Time": "sector3_time",
                        "TrackTemp": "track_temp",
                        "AirTemp": "air_temp",
                        "Rainfall": "_rainfall",
                    }
                    available = {
                        k: v
                        for k, v in tel_feature_map.items()
                        if k in driver_tel.columns
                    }
                    if available:
                        tel_subset = driver_tel[
                            ["lap_number"] + list(available.keys())
                        ].rename(columns=available)
                        driver_laps = driver_laps.drop(
                            columns=[
                                v
                                for v in available.values()
                                if v in driver_laps.columns
                            ],
                            errors="ignore",
                        )
                        driver_laps = driver_laps.merge(
                            tel_subset, on="lap_number", how="left"
                        )
                    if "_rainfall" in driver_laps.columns:
                        driver_laps["weather"] = driver_laps["_rainfall"].apply(
                            lambda r: (
                                "wet"
                                if (str(r).lower() in ("true", "1", "1.0"))
                                else "dry"
                            )
                        )
                        driver_laps = driver_laps.drop(columns=["_rainfall"])
            except Exception as exc:
                logger.info(
                    "FastF1 telemetry unavailable for %s/%s: %s",
                    race_id,
                    driver_id,
                    exc,
                )

        # ── 7. Final column selection and types ────────────────────────────────
        driver_laps["race_id"] = race_id
        driver_laps["driver_id"] = driver_id
        driver_laps["position"] = pd.to_numeric(
            driver_laps.get("position", np.nan), errors="coerce"
        ).astype("Int64")
        driver_laps["lap_number"] = driver_laps["lap_number"].astype("Int64")
        driver_laps["tire_age_laps"] = (
            pd.to_numeric(driver_laps["tire_age_laps"], errors="coerce")
            .fillna(0)
            .astype(int)
        )
        driver_laps["pit_stops_count"] = driver_laps["pit_stops_count"].astype(int)

        output_cols = [
            "race_id",
            "driver_id",
            "lap_number",
            "position",
            "gap_to_leader",
            "gap_to_ahead",
            "tire_compound",
            "tire_age_laps",
            "pit_stops_count",
            "fuel_remaining_kg",
            "track_temp",
            "air_temp",
            "weather",
            "last_lap_time_ms",
            "best_lap_time_ms",
            "sector1_time",
            "sector2_time",
            "sector3_time",
        ]
        for col in output_cols:
            if col not in driver_laps.columns:
                driver_laps[col] = np.nan

        return driver_laps[output_cols].reset_index(drop=True)

    def build_race_features(self, race_id: str) -> pd.DataFrame:
        """
        Build state vectors for ALL drivers in a race. Concatenates results
        from build_state_vector for each driver found in the data.
        """
        season, rnd = _parse_race_id(race_id)
        all_laps = self._laps()
        race_mask = (all_laps["season"] == season) & (all_laps["round"] == rnd)
        drivers_in_race = all_laps[race_mask]["driverId"].unique().tolist()

        frames = []
        for drv in drivers_in_race:
            df = self.build_state_vector(race_id, drv)
            if not df.empty:
                frames.append(df)

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)
