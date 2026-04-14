"""
build_car_performance.py — Unified car performance artifact.

Combines two analyses into a single car_performance.json:
  1. Constructor pace (MixedLM): isolates car speed from driver skill
  2. Compound degradation (linear regression): per-compound tire deg curves

For each constructor x season, the output contains:
  - pace_delta_s: seconds/lap vs field median (negative = faster)
  - compounds.{SOFT,MEDIUM,HARD}: deg_slope_per_lap, base_deg_s, avg_tyre_delta

Usage:
    python pipeline/scripts/build_car_performance.py \
      --output gs://f1optimizer-data-lake/processed/car_performance.json \
      --local-output frontend/public/data/car_performance.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats as sp_stats

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_car_performance")

FEATURES_URI = "gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet"
CONSTRUCTOR_MAP_URI = "gs://f1optimizer-data-lake/ml_features/constructor_map.json"

DRY_COMPOUNDS = ["SOFT", "MEDIUM", "HARD"]
MIN_LAPS_DEG = 10

STREET_CIRCUITS = {
    "Monaco Grand Prix", "Azerbaijan Grand Prix", "Singapore Grand Prix",
    "Saudi Arabian Grand Prix", "Miami Grand Prix", "Las Vegas Grand Prix",
}
HIGH_SPEED_CIRCUITS = {
    "Italian Grand Prix", "Belgian Grand Prix", "Mexican Grand Prix",
    "Canadian Grand Prix", "Austrian Grand Prix",
}

CONSTRUCTOR_ID_MAP = {
    "Alfa Romeo": "alfa_romeo",
    "Alfa Romeo Racing": "alfa_romeo",
    "AlphaTauri": "alphatauri",
    "Alpine": "alpine",
    "Aston Martin": "aston_martin",
    "Ferrari": "ferrari",
    "Force India": "force_india",
    "Haas F1 Team": "haas",
    "Kick Sauber": "sauber",
    "McLaren": "mclaren",
    "Mercedes": "mercedes",
    "RB": "rb",
    "Racing Point": "racing_point",
    "Red Bull Racing": "red_bull",
    "Renault": "renault",
    "Sauber": "sauber",
    "Toro Rosso": "toro_rosso",
    "Unknown": "unknown",
    "Williams": "williams",
}


def _circuit_category(race_name: str) -> str:
    if race_name in STREET_CIRCUITS:
        return "street"
    if race_name in HIGH_SPEED_CIRCUITS:
        return "high_speed"
    return "balanced"


def _load_constructor_map() -> dict:
    try:
        import gcsfs
        fs = gcsfs.GCSFileSystem()
        with fs.open(CONSTRUCTOR_MAP_URI) as f:
            name_to_int = json.load(f)
    except Exception:
        local = "data/ml_features/constructor_map.json"
        if os.path.exists(local):
            with open(local) as f:
                name_to_int = json.load(f)
        else:
            logger.error("Could not load constructor_map.json")
            return {}
    reverse = {v: k for k, v in name_to_int.items()}
    logger.info("Loaded constructor map: %d teams", len(reverse))
    return reverse


def _load_features() -> pd.DataFrame:
    cols = [
        "season", "round", "Driver", "constructor_enc", "raceName",
        "Compound", "TyreLife", "tyre_delta", "LapTime", "fuel_load_pct",
    ]
    logger.info("Loading features from %s", FEATURES_URI)
    try:
        df = pd.read_parquet(FEATURES_URI, columns=cols)
    except Exception:
        local = "data/ml_features/fastf1_features.parquet"
        logger.info("GCS failed, trying local %s", local)
        df = pd.read_parquet(local, columns=cols)

    df = df[df["Compound"].isin(DRY_COMPOUNDS)].copy()
    df = df.dropna(subset=["LapTime", "constructor_enc", "Driver"])
    df = df[df["LapTime"] > 0].copy()
    df["constructor_enc"] = df["constructor_enc"].astype(int)

    logger.info("Loaded %d rows, seasons %s", len(df), sorted(df["season"].unique()))
    return df


def _prepare_data(df: pd.DataFrame, reverse_map: dict) -> pd.DataFrame:
    session_median = df.groupby(["season", "round"])["LapTime"].transform("median")
    df["relative_pace"] = df["LapTime"] / session_median - 1.0
    df["session_median"] = session_median

    df["team_name"] = df["constructor_enc"].map(reverse_map).fillna("Unknown")
    df["constructor_id"] = df["team_name"].map(CONSTRUCTOR_ID_MAP).fillna("unknown")
    df["constructor_season"] = df["constructor_id"] + "_" + df["season"].astype(str)
    df["circuit_category"] = df["raceName"].apply(_circuit_category)
    df["driver_id"] = df["Driver"].astype(str)

    logger.info("Prepared: %d rows, %d constructor-seasons, %d drivers",
                len(df), df["constructor_season"].nunique(), df["driver_id"].nunique())
    return df


def _fit_pace_model(df: pd.DataFrame) -> dict:
    """Fit MixedLM to extract per constructor-season pace delta."""
    driver_counts = df.groupby("driver_id").size()
    valid_drivers = driver_counts[driver_counts >= 3].index
    fit_df = df[df["driver_id"].isin(valid_drivers)].copy()

    if len(fit_df) < 50 or fit_df["constructor_season"].nunique() < 2:
        logger.error("Not enough data for pace model")
        return {}

    logger.info("Fitting pace MixedLM: %d rows, %d drivers, %d constructor-seasons",
                len(fit_df), fit_df["driver_id"].nunique(), fit_df["constructor_season"].nunique())

    model = smf.mixedlm(
        "relative_pace ~ C(constructor_season) + C(circuit_category) + TyreLife + fuel_load_pct",
        data=fit_df,
        groups=fit_df["driver_id"],
    )
    result = model.fit(reml=True, method="lbfgs", maxiter=500)

    logger.info("Pace model converged. Random effect variance: %.6f", result.cov_re.iloc[0, 0])

    coefficients = {}
    for param, value in result.fe_params.items():
        if "constructor_season" not in param:
            continue
        cs = param.split("[T.")[1].rstrip("]") if "[T." in param else None
        if cs:
            coefficients[cs] = float(value)

    for cs in fit_df["constructor_season"].unique():
        if cs not in coefficients:
            coefficients[cs] = 0.0

    avg_median = fit_df["session_median"].mean()
    pace_deltas = {cs: round(coeff * avg_median, 3) for cs, coeff in coefficients.items()}

    logger.info("Extracted %d pace deltas", len(pace_deltas))
    return pace_deltas


def _compute_deg_profiles(df: pd.DataFrame) -> dict:
    """Compute per constructor x season x compound degradation curves."""
    profiles = {}

    for (cid, season, comp), g in df.groupby(["constructor_id", "season", "Compound"]):
        if cid == "unknown" or len(g) < MIN_LAPS_DEG:
            continue

        g_clean = g.dropna(subset=["tyre_delta", "TyreLife"])
        if len(g_clean) < MIN_LAPS_DEG:
            continue

        slope, intercept, r, _, _ = sp_stats.linregress(g_clean["TyreLife"], g_clean["tyre_delta"])

        key = (cid, str(int(season)))
        if key not in profiles:
            profiles[key] = {}

        profiles[key][comp] = {
            "deg_slope_per_lap": round(float(slope), 4),
            "base_deg_s": round(float(intercept), 3),
            "avg_tyre_delta": round(float(g_clean["tyre_delta"].mean()), 3),
            "r_squared": round(float(r ** 2), 3),
            "n_laps": len(g_clean),
        }

    logger.info("Computed deg profiles for %d constructor-season pairs", len(profiles))
    return profiles


def _build_output(pace_deltas: dict, deg_profiles: dict, df: pd.DataFrame) -> dict:
    constructors = {}

    team_names = df.drop_duplicates("constructor_id").set_index("constructor_id")["team_name"].to_dict()

    all_cs = set(pace_deltas.keys())
    for key in deg_profiles.keys():
        cid, season = key
        all_cs.add(f"{cid}_{season}")

    for cs in all_cs:
        parts = cs.rsplit("_", 1)
        if len(parts) != 2:
            continue
        cid, season_str = parts[0], parts[1]
        try:
            season = int(season_str)
        except ValueError:
            continue

        if cid == "unknown":
            continue

        if cid not in constructors:
            display = None
            for name, slug in CONSTRUCTOR_ID_MAP.items():
                if slug == cid:
                    display = name
                    break
            if not display:
                display = team_names.get(cid, cid.replace("_", " ").title())
            constructors[cid] = {"display_name": display, "seasons": {}}

        season_data = {
            "pace_delta_s": pace_deltas.get(cs, 0.0),
            "data_tier": 1,
            "limited_data": season >= 2026,
            "compounds": deg_profiles.get((cid, season_str), {}),
        }
        constructors[cid]["seasons"][season_str] = season_data

    constructors = dict(sorted(constructors.items()))

    # Log summary
    all_entries = []
    for cid, data in constructors.items():
        for s, info in data["seasons"].items():
            all_entries.append((cid, s, info["pace_delta_s"]))
    all_entries.sort(key=lambda x: x[2])

    if all_entries:
        logger.info("Top 5 fastest (pace_delta_s):")
        for cid, s, d in all_entries[:5]:
            logger.info("  %s %s: %.3fs", cid, s, d)
        logger.info("Top 5 slowest (pace_delta_s):")
        for cid, s, d in all_entries[-5:]:
            logger.info("  %s %s: %.3fs", cid, s, d)

    n_compounds = sum(
        len(s.get("compounds", {}))
        for c in constructors.values()
        for s in c["seasons"].values()
    )

    return {
        "version": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reference": "field_median",
        "description": "Unified car performance: pace_delta_s + compound-specific tire degradation profiles",
        "n_constructors": len(constructors),
        "n_constructor_seasons": len(all_entries),
        "n_compound_entries": n_compounds,
        "constructors": constructors,
    }


def main(
    data_bucket: str = "f1optimizer-data-lake",
    gcs_output: Optional[str] = None,
    local_output: Optional[str] = None,
) -> dict:
    reverse_map = _load_constructor_map()
    if not reverse_map:
        return {"constructors": {}}

    df = _load_features()
    if df.empty:
        return {"constructors": {}}

    df = _prepare_data(df, reverse_map)

    pace_deltas = _fit_pace_model(df)
    deg_profiles = _compute_deg_profiles(df)

    output = _build_output(pace_deltas, deg_profiles, df)

    logger.info("Final: %d constructors, %d constructor-seasons, %d compound entries",
                output["n_constructors"], output["n_constructor_seasons"], output["n_compound_entries"])

    output_json = json.dumps(output, indent=2)

    if gcs_output and gcs_output.startswith("gs://"):
        try:
            from google.cloud import storage
            bucket_name = gcs_output.split("/")[2]
            blob_path = "/".join(gcs_output.split("/")[3:])
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            bucket.blob(blob_path).upload_from_string(output_json, content_type="application/json")
            logger.info("Uploaded to %s", gcs_output)
        except Exception as exc:
            logger.error("GCS upload failed: %s", exc)

    if local_output:
        os.makedirs(os.path.dirname(local_output) or ".", exist_ok=True)
        with open(local_output, "w") as f:
            f.write(output_json)
        logger.info("Wrote local file: %s", local_output)

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build unified car performance artifact")
    parser.add_argument(
        "--output",
        default="gs://f1optimizer-data-lake/processed/car_performance.json",
        help="GCS output path",
    )
    parser.add_argument(
        "--local-output",
        default="frontend/public/data/car_performance.json",
        help="Local output path",
    )
    args = parser.parse_args()

    result = main(gcs_output=args.output, local_output=args.local_output)

    n = result.get("n_constructors", 0)
    e = result.get("n_compound_entries", 0)
    print(f"\nDone: {n} constructors, {e} compound entries")
    sys.exit(0 if n > 0 else 1)