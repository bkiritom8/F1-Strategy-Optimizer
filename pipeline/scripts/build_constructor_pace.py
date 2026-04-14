"""
build_constructor_pace.py — Fit mixed-effects model to isolate constructor car pace.

Uses fastf1_features.parquet (2018-2025) with constructor_enc and constructor_map.json
for team name resolution. Driver skill is absorbed by the random effect; constructor
fixed-effect coefficients become the per-season car pace delta (seconds/lap vs field median).

Usage:
    python pipeline/scripts/build_constructor_pace.py \
      --output gs://f1optimizer-data-lake/processed/constructor_pace.json \
      --local-output frontend/public/data/constructor_pace.json
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

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("build_constructor_pace")

FEATURES_URI = "gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet"
CONSTRUCTOR_MAP_URI = "gs://f1optimizer-data-lake/ml_features/constructor_map.json"

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
    """Load constructor_map.json from GCS, return {int_code: team_name}."""
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
            logger.error("Could not load constructor_map.json from GCS or local")
            return {}
    reverse = {v: k for k, v in name_to_int.items()}
    logger.info("Loaded constructor map: %d teams", len(reverse))
    return reverse


def _load_features() -> pd.DataFrame:
    """Load fastf1_features.parquet with columns needed for the model."""
    cols = [
        "season", "round", "Driver", "constructor_enc", "raceName",
        "LapTime", "TyreLife", "Stint", "fuel_load_pct", "Compound",
    ]
    logger.info("Loading features from %s", FEATURES_URI)
    try:
        df = pd.read_parquet(FEATURES_URI, columns=cols)
    except Exception:
        local = "data/ml_features/fastf1_features.parquet"
        logger.info("GCS failed, trying local %s", local)
        df = pd.read_parquet(local, columns=cols)

    df = df.dropna(subset=["LapTime", "constructor_enc", "Driver"])
    df = df[df["LapTime"] > 0].copy()
    df["constructor_enc"] = df["constructor_enc"].astype(int)

    dry = ["SOFT", "MEDIUM", "HARD", "ULTRASOFT", "SUPERSOFT", "HYPERSOFT"]
    df = df[df["Compound"].isin(dry)].copy()

    logger.info("Loaded %d rows, seasons %s", len(df), sorted(df["season"].unique()))
    return df


def _prepare_model_data(df: pd.DataFrame, reverse_map: dict) -> pd.DataFrame:
    """Add derived columns needed for the mixed-effects model."""
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


def _fit_mixed_model(df: pd.DataFrame) -> tuple[dict, float]:
    """Fit MixedLM, return ({constructor_season: pace_delta_s}, avg_session_median)."""
    driver_counts = df.groupby("driver_id").size()
    valid_drivers = driver_counts[driver_counts >= 3].index
    df = df[df["driver_id"].isin(valid_drivers)].copy()

    if len(df) < 50 or df["constructor_season"].nunique() < 2:
        logger.error("Not enough data: %d rows, %d constructor-seasons",
                     len(df), df["constructor_season"].nunique())
        return {}, 0.0

    logger.info("Fitting MixedLM: %d rows, %d drivers, %d constructor-seasons",
                len(df), df["driver_id"].nunique(), df["constructor_season"].nunique())

    model = smf.mixedlm(
        "relative_pace ~ C(constructor_season) + C(circuit_category) + TyreLife + fuel_load_pct",
        data=df,
        groups=df["driver_id"],
    )
    result = model.fit(reml=True, method="lbfgs", maxiter=500)

    logger.info("Model converged. AIC=%.1f, BIC=%.1f", result.aic, result.bic)
    logger.info("Random effect variance (driver): %.6f", result.cov_re.iloc[0, 0])

    coefficients = {}
    for param, value in result.fe_params.items():
        if "constructor_season" not in param:
            continue
        cs = param.split("[T.")[1].rstrip("]") if "[T." in param else None
        if cs:
            coefficients[cs] = float(value)

    all_cs = df["constructor_season"].unique()
    for cs in all_cs:
        if cs not in coefficients:
            coefficients[cs] = 0.0

    avg_median = df["session_median"].mean()
    pace_deltas = {cs: round(coeff * avg_median, 3) for cs, coeff in coefficients.items()}

    logger.info("Extracted %d constructor-season pace deltas", len(pace_deltas))
    return pace_deltas, avg_median


def _build_output(pace_deltas: dict) -> dict:
    """Assemble the final constructor_pace.json structure."""
    constructors: dict = {}

    for cs, delta in pace_deltas.items():
        parts = cs.rsplit("_", 1)
        if len(parts) != 2:
            continue

        constructor_id = parts[0]
        try:
            season = int(parts[1])
        except ValueError:
            continue

        if constructor_id not in constructors:
            display = None
            for name, cid in CONSTRUCTOR_ID_MAP.items():
                if cid == constructor_id:
                    display = name
                    break
            if not display:
                display = constructor_id.replace("_", " ").title()

            constructors[constructor_id] = {
                "display_name": display,
                "seasons": {},
            }

        constructors[constructor_id]["seasons"][str(season)] = {
            "pace_delta_s": delta,
            "data_tier": 1,
            "limited_data": season >= 2026,
        }

    constructors = dict(sorted(constructors.items()))

    all_entries = []
    for cid, data in constructors.items():
        for s, info in data["seasons"].items():
            all_entries.append((cid, s, info["pace_delta_s"]))
    all_entries.sort(key=lambda x: x[2])

    logger.info("Top 5 fastest constructor-seasons:")
    for cid, s, d in all_entries[:5]:
        logger.info("  %s %s: %.3fs", cid, s, d)
    logger.info("Top 5 slowest constructor-seasons:")
    for cid, s, d in all_entries[-5:]:
        logger.info("  %s %s: %.3fs", cid, s, d)

    return {
        "version": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "reference": "field_median",
        "constructors": constructors,
    }


def main(
    data_bucket: str = "f1optimizer-data-lake",
    gcs_output: Optional[str] = None,
    local_output: Optional[str] = None,
) -> dict:
    reverse_map = _load_constructor_map()
    if not reverse_map:
        logger.error("No constructor map available, aborting")
        return {"constructors": {}}

    df = _load_features()
    if df.empty:
        logger.error("No feature data available, aborting")
        return {"constructors": {}}

    df = _prepare_model_data(df, reverse_map)

    pace_deltas, avg_median = _fit_mixed_model(df)
    if not pace_deltas:
        logger.error("Model fitting produced no results")
        return {"constructors": {}}

    output = _build_output(pace_deltas)
    n_constructors = len(output["constructors"])
    n_seasons = sum(len(c["seasons"]) for c in output["constructors"].values())
    logger.info("Final: %d constructors, %d constructor-seasons", n_constructors, n_seasons)

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
    parser = argparse.ArgumentParser(description="Build constructor pace table")
    parser.add_argument(
        "--output",
        default="gs://f1optimizer-data-lake/processed/constructor_pace.json",
        help="GCS output path",
    )
    parser.add_argument(
        "--local-output",
        default="frontend/public/data/constructor_pace.json",
        help="Local output path",
    )
    args = parser.parse_args()

    result = main(gcs_output=args.output, local_output=args.local_output)

    n = len(result.get("constructors", {}))
    print(f"\nDone: {n} constructors written")
    sys.exit(0 if n > 0 else 1)