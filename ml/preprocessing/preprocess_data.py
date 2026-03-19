"""
Data Preprocessing Pipeline - GCS Version (Fixed)
"""

import pandas as pd
import numpy as np
import json
import gcsfs

RAW_DIR = "gs://f1optimizer-data-lake/processed"
PROCESSED_DIR = "gs://f1optimizer-data-lake/ml_features"

fs = gcsfs.GCSFileSystem()


def load_fastf1_data():
    print(f"Loading FastF1 data from {RAW_DIR}...")
    laps = pd.read_parquet(f"{RAW_DIR}/fastf1_laps.parquet")
    telemetry = pd.read_parquet(f"{RAW_DIR}/fastf1_telemetry.parquet")

    laps = laps.dropna(subset=["season", "round", "Driver", "LapNumber"])
    telemetry = telemetry.dropna(subset=["season", "round", "Driver", "LapNumber"])

    df = laps.merge(
        telemetry, on=["season", "round", "Driver", "LapNumber"], how="inner"
    )
    print(f"  Merged: {len(df)} rows")
    return df


def load_race_results():
    print(f"Loading race results from {RAW_DIR}...")
    df = pd.read_parquet(f"{RAW_DIR}/race_results.parquet")
    print(f"  Loaded: {len(df)} rows")
    return df


def preprocess_fastf1(df):
    print("Preprocessing FastF1 data...")

    df = df.dropna(subset=["LapTime", "TyreLife", "Compound", "mean_throttle"])
    df = df[(df["LapTime"] > 60) & (df["LapTime"] < 200)]

    df = df.sort_values(["season", "round", "Driver", "LapNumber"]).reset_index(drop=True)

    # Compound dummies (all known compounds)
    compounds = pd.get_dummies(df["Compound"].str.upper(), prefix="compound")
    all_compounds = [
        "compound_SOFT", "compound_MEDIUM", "compound_HARD",
        "compound_INTERMEDIATE", "compound_WET",
        "compound_SUPERSOFT", "compound_ULTRASOFT", "compound_HYPERSOFT",
        "compound_NONE",
    ]
    for c in all_compounds:
        if c not in compounds.columns:
            compounds[c] = False
    df = pd.concat([df, compounds], axis=1)

    # Lap time features
    df["lap_time_delta"] = df.groupby(["season", "round", "Driver"])["LapTime"].diff()
    df["lap_time_delta"] = df["lap_time_delta"].fillna(0).clip(-5, 5)

    df["deg_rate_roll3"] = df.groupby(["season", "round", "Driver"])[
        "lap_time_delta"
    ].transform(lambda x: x.rolling(3, min_periods=1).mean())

    # Race context
    df["total_laps"] = df.groupby(["season", "round"])["LapNumber"].transform("max")
    df["laps_remaining"] = df["total_laps"] - df["LapNumber"]
    df["fuel_load_pct"] = (1.0 - (df["LapNumber"] - 1) / df["total_laps"]).clip(lower=0.0)
    df["fuel_consumed"] = 1.8 * (df["mean_throttle"] / 70)

    # Driving style
    throttle_33 = df["mean_throttle"].quantile(0.33)
    throttle_66 = df["mean_throttle"].quantile(0.66)
    df["driving_style"] = df["mean_throttle"].apply(
        lambda x: 0 if x < throttle_33 else (2 if x > throttle_66 else 1)
    )

    # Pit stop features
    df["stint_change"] = (
        df.groupby(["season", "round", "Driver"])["Stint"].diff().fillna(0)
    )
    df["is_pit_lap"] = (df["stint_change"] > 0).astype(int)

    def calc_laps_to_pit(group):
        pit_laps = group[group["is_pit_lap"] == 1]["LapNumber"].values
        result = []
        for _, row in group.iterrows():
            future_pits = pit_laps[pit_laps > row["LapNumber"]]
            if len(future_pits) > 0:
                result.append(future_pits[0] - row["LapNumber"])
            else:
                result.append(row["laps_remaining"])
        return pd.Series(result, index=group.index)

    print("  Calculating laps to pit...")
    df["laps_to_pit"] = (
        df.groupby(["season", "round", "Driver"])
        .apply(calc_laps_to_pit, include_groups=False)
        .reset_index(level=[0, 1, 2], drop=True)
    )

    # Position features
    df["cum_time"] = df.groupby(["season", "round", "Driver"])["LapTime"].cumsum()
    df["position"] = df.groupby(["season", "round", "LapNumber"])["cum_time"].rank(method="first")
    df["next_position"] = df.groupby(["season", "round", "Driver"])["position"].shift(-1)
    df["position_change"] = df["position"] - df["next_position"]
    df["overtake_success"] = (df["position_change"] >= 1).astype(int)

    # Gap ahead
    df["gap_ahead"] = (
        df.groupby(["season", "round", "LapNumber"])["LapTime"].diff().fillna(1.0)
    )
    df["gap_ahead"] = df["gap_ahead"].clip(-5, 5)

    # Safety car detection
    race_medians = df.groupby(["season", "round"])["LapTime"].transform("median")
    lap_medians = df.groupby(["season", "round", "LapNumber"])["LapTime"].transform("median")
    df["is_sc_lap"] = (lap_medians > race_medians * 1.2).astype(int)

    # tyre_delta = lap time deviation from per-lap median

    lap_baseline = df.groupby(["season", "round", "LapNumber"])["LapTime"].transform("median")
    df["tyre_delta"] = df["LapTime"] - lap_baseline

    # Speed delta
    df["speed_delta"] = (
        df.groupby(["season", "round", "LapNumber"])["mean_speed"].diff().fillna(0)
    )

    # SC outcome features
    df["position_5_later"] = df.groupby(["season", "round", "Driver"])["position"].shift(-5)
    df["sc_position_change"] = df["position"] - df["position_5_later"]
    df["pitted_under_sc"] = ((df["stint_change"] > 0) & (df["is_sc_lap"] == 1)).astype(int)

    # Filter out pit laps, SC laps and extreme tyre_delta values
    df = df[df['is_pit_lap'] == 0]
    df = df[df['is_sc_lap'] == 0]
    df = df[df['tyre_delta'].between(-5, 10)]
    df = df[df['TyreLife'] >= 1]

    print(f"  Final: {len(df)} rows, {len(df.columns)} columns")

    # Sanity checks
    print("\n  Sanity checks:")
    print(f"    tyre_delta mean: {df['tyre_delta'].mean():.3f}, std: {df['tyre_delta'].std():.3f}")
    print(f"    tyre_delta range: [{df['tyre_delta'].min():.2f}, {df['tyre_delta'].max():.2f}]")
    print(f"    is_pit_lap: {df['is_pit_lap'].sum()} pit laps")
    print(f"    is_sc_lap: {df['is_sc_lap'].sum()} SC laps")
    print(f"    Compounds: {df['Compound'].str.upper().value_counts().to_dict()}")

    return df


def preprocess_race_results(df):
    print("Preprocessing race results...")

    col_map = {
        "Grid": "grid", "Position": "position", "Season": "season",
        "Driver": "driver", "Constructor": "constructor", "Circuit": "circuit",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    df = df.dropna(subset=["grid", "position"])
    df = df[df["grid"] > 0]
    df = df[df["position"] > 0]
    df = df[df["position"] <= 20]

    for col in ["driver", "constructor", "circuit", "driverId", "constructorId", "circuitId"]:
        if col in df.columns:
            df[f"{col}_encoded"] = df[col].astype("category").cat.codes

    if "season" not in df.columns:
        df["season"] = df["year"] if "year" in df.columns else 2020

    driver_col = "driver_encoded" if "driver_encoded" in df.columns else "driverId_encoded"
    constructor_col = "constructor_encoded" if "constructor_encoded" in df.columns else "constructorId_encoded"

    df = df.sort_values(["season", driver_col])

    if driver_col in df.columns:
        df["driver_avg_finish"] = (
            df.groupby(driver_col)["position"]
            .transform(lambda x: x.rolling(5, min_periods=1).mean().shift(1))
            .fillna(10)
        )

    if constructor_col in df.columns:
        df["constructor_avg_finish"] = (
            df.groupby(constructor_col)["position"]
            .transform(lambda x: x.rolling(5, min_periods=1).mean().shift(1))
            .fillna(10)
        )

    print(f"  Final: {len(df)} rows, {len(df.columns)} columns")
    return df


def save_metadata(fastf1_df, race_df):
    metadata = {
        "fastf1": {
            "rows": len(fastf1_df),
            "columns": list(fastf1_df.columns),
            "seasons": sorted(fastf1_df["season"].unique().tolist()),
            "features": {
                "tire_degradation": [
                    "TyreLife", "Stint", "LapNumber",
                    "compound_SOFT", "compound_MEDIUM", "compound_HARD",
                    "compound_INTERMEDIATE", "compound_WET",
                    "compound_SUPERSOFT", "compound_ULTRASOFT", "compound_HYPERSOFT",
                    "fuel_load_pct", "laps_remaining",
                    "mean_throttle", "std_throttle", "mean_brake", "std_brake",
                    "driving_style", "position", "gap_ahead",
                ],
                "fuel_consumption": [
                    "mean_throttle", "std_throttle", "mean_speed",
                    "max_speed", "LapTime", "LapNumber",
                ],
                "driving_style": [
                    "mean_throttle", "std_throttle", "mean_brake",
                    "std_brake", "mean_speed", "max_speed",
                ],
                "pit_window": [
                    "TyreLife", "compound_SOFT", "compound_MEDIUM", "compound_HARD",
                    "lap_time_delta", "deg_rate_roll3", "LapNumber",
                    "laps_remaining", "Stint", "fuel_load_pct",
                ],
                "overtake": [
                    "gap_ahead", "tyre_delta", "speed_delta",
                    "TyreLife", "mean_throttle", "mean_speed", "LapNumber",
                ],
                "safety_car": [
                    "LapNumber", "position", "TyreLife",
                    "compound_SOFT", "compound_MEDIUM", "compound_HARD",
                    "fuel_load_pct", "laps_remaining", "pitted_under_sc",
                ],
            },
            "targets": {
                "tire_degradation": "tyre_delta",
                "fuel_consumption": "fuel_consumed",
                "driving_style": "driving_style",
                "pit_window": "laps_to_pit",
                "overtake": "overtake_success",
                "safety_car": "sc_position_change",
            },
        },
        "race_results": {
            "rows": len(race_df),
            "columns": list(race_df.columns),
            "seasons": sorted(race_df["season"].unique().tolist()),
            "features": {
                "race_outcome": [
                    "grid", "driver_encoded", "constructor_encoded",
                    "circuit_encoded", "season",
                    "driver_avg_finish", "constructor_avg_finish",
                ]
            },
            "targets": {"race_outcome": "position"},
        },
    }

    metadata_path = f"{PROCESSED_DIR}/metadata.json"
    with fs.open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Saved metadata to {metadata_path}")


def main():
    fastf1_df = load_fastf1_data()
    race_df = load_race_results()

    fastf1_df = preprocess_fastf1(fastf1_df)
    race_df = preprocess_race_results(race_df)

    fastf1_df.to_parquet(f"{PROCESSED_DIR}/fastf1_features.parquet", index=False)
    print(f"Saved fastf1_features.parquet")

    race_df.to_parquet(f"{PROCESSED_DIR}/race_results_features.parquet", index=False)
    print(f"Saved race_results_features.parquet")

    save_metadata(fastf1_df, race_df)

    print("\nPreprocessing complete!")
    print(f"  FastF1: {len(fastf1_df)} rows")
    print(f"  Race Results: {len(race_df)} rows")





if __name__ == "__main__":
    main()