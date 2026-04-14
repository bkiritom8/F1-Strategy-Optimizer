"""
Build constructor pace model.

Fits a statsmodels MixedLM across three data tiers to isolate car pace
from driver skill, writing constructor_pace.json to GCS and/or local disk.

Three data tiers:
  - Tier 1 (2018-2026): FastF1 qualifying lap times (telemetry_laps_all.parquet)
  - Tier 2 (2003-2017): Ergast qualifying times (race_results.parquet)
  - Tier 3 (1996-2002): Ergast race finish times (race_results.parquet)

Output JSON format per constructor:
  {
    "seasons": {
      "2024": {
        "pace_delta_s": -0.234,
        "data_tier": 1,
        "limited_data": false
      }
    }
  }

Usage:
  python pipeline/scripts/build_constructor_pace.py \
    --output gs://f1optimizer-data-lake/processed/constructor_pace.json
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Circuits grouped by category (affects median lap times)
CIRCUIT_CATEGORIES = {
    "street": [
        "monaco", "baku", "singapore", "las_vegas", "miami", "jeddah",
        "melbourne", "montreal",
    ],
    "high_speed": [
        "monza", "spa", "silverstone", "austria", "bahrain", "sakhir",
        "suzuka", "interlagos",
    ],
    "technical": [
        "hungary", "abu_dhabi", "barcelona", "zandvoort", "imola",
        "portimao", "istanbul", "nurburgring",
    ],
}

_CIRCUIT_TO_CATEGORY: dict[str, str] = {}
for _cat, _circuits in CIRCUIT_CATEGORIES.items():
    for _c in _circuits:
        _CIRCUIT_TO_CATEGORY[_c] = _cat


def slugify(name: str) -> str:
    """Convert a display name to a slug (lowercase, underscores)."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def get_circuit_category(circuit_slug: str) -> str:
    for key, cat in _CIRCUIT_TO_CATEGORY.items():
        if key in circuit_slug:
            return cat
    return "technical"


def assign_tier(season: int) -> int:
    if season >= 2018:
        return 1
    if season >= 2003:
        return 2
    return 3


def compute_relative_pace(df: pd.DataFrame, time_col: str) -> pd.DataFrame:
    """
    Add relative_pace and session_median_s columns.
    relative_pace = lap_time / session_median - 1.0  (dimensionless, negative = faster)
    """
    df = df.copy()
    group_keys = ["season", "circuit_slug"]
    medians = df.groupby(group_keys)[time_col].median().rename("session_median_s")
    df = df.join(medians, on=group_keys)
    df["relative_pace"] = df[time_col] / df["session_median_s"] - 1.0
    return df


def fit_constructor_pace(df: pd.DataFrame) -> dict[str, float]:
    """
    Fit a MixedLM. Driver skill is absorbed by the random effect.
    Returns {constructor_season_slug: pace_delta_s} centered so field median = 0.
    pace_delta_s < 0 means faster than field median.
    """
    import statsmodels.formula.api as smf

    if (
        df.empty
        or df["driver_id"].nunique() < 2
        or df["constructor_season"].nunique() < 2
    ):
        return {}

    mean_lap_s = float(df["session_median_s"].mean())

    try:
        model = smf.mixedlm(
            "relative_pace ~ C(constructor_season) + C(circuit_category)",
            data=df,
            groups=df["driver_id"],
        )
        result = model.fit(reml=True, disp=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MixedLM fitting failed: %s", exc)
        return {}

    # Extract fixed-effect coefficients for constructor_season terms
    coefs: dict[str, float] = {}
    ref_level = None
    for name, val in result.params.items():
        if name.startswith("C(constructor_season)[T."):
            key = name[len("C(constructor_season)[T.") : -1]
            coefs[key] = float(val)
        elif name == "Intercept":
            # The reference level (first alphabetically) maps to the intercept offset
            ref_level = float(val)

    if not coefs:
        return {}

    # Add reference level at 0.0 (relative to itself)
    all_levels = sorted(df["constructor_season"].unique())
    reference = all_levels[0]
    coefs[reference] = 0.0

    # Center so field median = 0.0
    median_coef = float(np.median(list(coefs.values())))
    centered = {k: v - median_coef for k, v in coefs.items()}

    # Convert dimensionless → seconds/lap
    return {k: round(v * mean_lap_s, 4) for k, v in centered.items()}


def build_output(
    pace_by_constructor_season: dict[str, float],
    tier_map: dict[str, int],
    limited_seasons: set[str],
) -> dict[str, Any]:
    """
    Build the output dict keyed by constructor_id → {seasons: {year: {...}}}.
    constructor_season slugs have the form "constructor_id_YYYY".
    """
    output: dict[str, Any] = {}
    for cs_key, delta_s in pace_by_constructor_season.items():
        # Split off the trailing 4-digit year
        match = re.match(r"^(.+)_(\d{4})$", cs_key)
        if not match:
            continue
        constructor_id, season_str = match.group(1), match.group(2)
        tier = tier_map.get(cs_key, tier_map.get(f"{constructor_id}_{season_str}", 2))
        limited = cs_key in limited_seasons or f"{constructor_id}_{season_str}" in limited_seasons
        output.setdefault(constructor_id, {"seasons": {}})
        output[constructor_id]["seasons"][season_str] = {
            "pace_delta_s": delta_s,
            "data_tier": tier,
            "limited_data": limited,
        }
    return output


# ── GCS loaders ───────────────────────────────────────────────────────────────


def _gcs_read_parquet(gcs_path: str) -> pd.DataFrame:
    import gcsfs  # lazy import

    fs = gcsfs.GCSFileSystem()
    with fs.open(gcs_path, "rb") as f:
        return pd.read_parquet(f)


def load_tier1_data(data_bucket: str) -> pd.DataFrame:
    """FastF1 qualifying laps (2018–2026) from telemetry_laps_all.parquet."""
    path = f"gs://{data_bucket}/processed/telemetry_laps_all.parquet"
    df = _gcs_read_parquet(path)

    # Normalise column names
    col_map = {
        c: c.lower().replace(" ", "_") for c in df.columns
    }
    df = df.rename(columns=col_map)

    required = {"season", "driver_id", "constructor_id", "circuit_slug", "lap_time_s"}
    if not required.issubset(df.columns):
        # Try alternative column names
        renames = {
            "year": "season",
            "driverid": "driver_id",
            "constructorid": "constructor_id",
            "circuitid": "circuit_slug",
            "laptime": "lap_time_s",
            "laptime_s": "lap_time_s",
        }
        df = df.rename(columns={k: v for k, v in renames.items() if k in df.columns})

    df = df[df["lap_time_s"].notna() & (df["lap_time_s"] > 50)].copy()
    df["season"] = df["season"].astype(int)
    df["data_tier"] = 1
    df["constructor_season"] = (
        df["constructor_id"].apply(slugify) + "_" + df["season"].astype(str)
    )
    df["circuit_category"] = df["circuit_slug"].apply(
        lambda x: get_circuit_category(str(x))
    )
    return df


def load_tier2_data(data_bucket: str) -> pd.DataFrame:
    """Ergast qualifying times (2003–2017) from race_results.parquet."""
    path = f"gs://{data_bucket}/processed/race_results.parquet"
    df = _gcs_read_parquet(path)

    col_map = {c: c.lower().replace(" ", "_") for c in df.columns}
    df = df.rename(columns=col_map)

    renames = {
        "year": "season",
        "driverid": "driver_id",
        "constructorid": "constructor_id",
        "circuitid": "circuit_slug",
        "qualifyingtime_s": "lap_time_s",
        "q3": "lap_time_s",
    }
    df = df.rename(columns={k: v for k, v in renames.items() if k in df.columns})

    if "lap_time_s" not in df.columns and "q1" in df.columns:
        # Use best qualifying time
        for col in ["q3", "q2", "q1"]:
            if col in df.columns:
                df["lap_time_s"] = pd.to_numeric(df[col], errors="coerce")
                break

    df = df[df["season"].between(2003, 2017)].copy()
    df = df[df["lap_time_s"].notna() & (df["lap_time_s"] > 50)].copy()
    df["season"] = df["season"].astype(int)
    df["data_tier"] = 2
    df["constructor_season"] = (
        df["constructor_id"].apply(slugify) + "_" + df["season"].astype(str)
    )
    df["circuit_category"] = df["circuit_slug"].apply(
        lambda x: get_circuit_category(str(x))
    )
    return df


def load_tier3_data(data_bucket: str) -> pd.DataFrame:
    """Ergast race finish times (1996–2002) from race_results.parquet."""
    path = f"gs://{data_bucket}/processed/race_results.parquet"
    df = _gcs_read_parquet(path)

    col_map = {c: c.lower().replace(" ", "_") for c in df.columns}
    df = df.rename(columns=col_map)

    renames = {
        "year": "season",
        "driverid": "driver_id",
        "constructorid": "constructor_id",
        "circuitid": "circuit_slug",
        "racetime_s": "lap_time_s",
        "fastestlaptime": "lap_time_s",
    }
    df = df.rename(columns={k: v for k, v in renames.items() if k in df.columns})

    if "lap_time_s" not in df.columns and "time" in df.columns:
        df["lap_time_s"] = pd.to_numeric(df["time"], errors="coerce")

    df = df[df["season"].between(1996, 2002)].copy()
    df = df[df["lap_time_s"].notna() & (df["lap_time_s"] > 50)].copy()
    df["season"] = df["season"].astype(int)
    df["data_tier"] = 3
    df["constructor_season"] = (
        df["constructor_id"].apply(slugify) + "_" + df["season"].astype(str)
    )
    df["circuit_category"] = df["circuit_slug"].apply(
        lambda x: get_circuit_category(str(x))
    )
    return df


# ── Output writers ────────────────────────────────────────────────────────────


def write_output(
    output: dict[str, Any],
    gcs_uri: str | None,
    local_path: str | None,
) -> None:
    payload = json.dumps(output, indent=2)

    if gcs_uri:
        import gcsfs  # lazy import

        fs = gcsfs.GCSFileSystem()
        with fs.open(gcs_uri, "w") as f:
            f.write(payload)
        logger.info("Wrote constructor_pace.json to %s", gcs_uri)

    if local_path:
        import os

        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        with open(local_path, "w") as f:
            f.write(payload)
        logger.info("Wrote constructor_pace.json to %s", local_path)


# ── Main orchestrator ─────────────────────────────────────────────────────────


def main(
    data_bucket: str = "f1optimizer-data-lake",
    gcs_output: str | None = None,
    local_output: str | None = None,
) -> dict[str, Any]:
    """
    Fit the constructor pace model and write output.
    Returns the output dict (also written to gcs_output / local_output).
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    frames: list[pd.DataFrame] = []
    limited_seasons: set[str] = set()

    # Tier 1: FastF1 (2018–2026)
    try:
        t1 = load_tier1_data(data_bucket)
        # Mark 2026 as limited_data
        for row in t1[t1["season"] == 2026]["constructor_season"].unique():
            limited_seasons.add(row)
        frames.append(t1)
        logger.info("Tier 1 loaded: %d rows", len(t1))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tier 1 load failed: %s", exc)

    # Tier 2: Ergast qualifying (2003–2017)
    try:
        t2 = load_tier2_data(data_bucket)
        frames.append(t2)
        logger.info("Tier 2 loaded: %d rows", len(t2))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tier 2 load failed: %s", exc)

    # Tier 3: Ergast race times (1996–2002)
    try:
        t3 = load_tier3_data(data_bucket)
        frames.append(t3)
        logger.info("Tier 3 loaded: %d rows", len(t3))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tier 3 load failed: %s", exc)

    if not frames:
        logger.error("No data loaded from any tier — returning empty output")
        result: dict[str, Any] = {"constructors": {}, "version": "0.0.0"}
        write_output(result, gcs_output, local_output)
        return result

    df = pd.concat(frames, ignore_index=True)
    df = compute_relative_pace(df, "lap_time_s")

    # Build tier_map: constructor_season → data_tier
    tier_map: dict[str, int] = (
        df.groupby("constructor_season")["data_tier"].first().to_dict()
    )

    logger.info(
        "Fitting MixedLM on %d rows, %d constructor-seasons",
        len(df),
        df["constructor_season"].nunique(),
    )
    pace_coefs = fit_constructor_pace(df)
    logger.info("Fitted %d constructor-season coefficients", len(pace_coefs))

    constructors_output = build_output(pace_coefs, tier_map, limited_seasons)

    result = {
        "constructors": constructors_output,
        "version": "1.0.0",
        "n_rows": len(df),
        "n_constructor_seasons": len(pace_coefs),
    }

    write_output(result, gcs_output, local_output)
    logger.info("Done — %d constructors written", len(constructors_output))
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build constructor pace model")
    parser.add_argument("--bucket", default="f1optimizer-data-lake")
    parser.add_argument("--output", default=None, help="GCS output URI")
    parser.add_argument("--local-output", default=None, help="Local output path")
    args = parser.parse_args()

    main(
        data_bucket=args.bucket,
        gcs_output=args.output,
        local_output=args.local_output,
    )
