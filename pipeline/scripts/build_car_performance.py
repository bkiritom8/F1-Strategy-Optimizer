"""
Build year-aware car performance offsets from race_results.parquet.

Usage:
    python pipeline/scripts/build_car_performance.py \
        --input gs://f1optimizer-data-lake/processed/race_results.parquet \
        --output frontend/public/data/car_performance.json
"""
import argparse
import json
import pandas as pd
from pathlib import Path


def compute_offsets(df: pd.DataFrame) -> dict:
    """
    For each constructor+year, compute avg finishing position delta vs
    field median finishing position.

    Returns: { constructor: { str(year): delta_positions } }
    """
    result: dict = {}
    for (constructor, year), group in df.groupby(["constructorId", "year"]):
        year_df = df[df["year"] == year]
        field_median = year_df["positionOrder"].median()
        constructor_avg = group["positionOrder"].mean()
        delta = constructor_avg - field_median  # negative = faster than median
        if constructor not in result:
            result[constructor] = {}
        result[constructor][str(year)] = round(delta, 4)
    return result


def normalise_to_ms(offsets: dict, avg_lap_time_s: float = 90.0) -> dict:
    """
    Convert position delta to milliseconds.
    Each position ~= 1.5s gap at median circuits (empirical F1 approximation).
    """
    POSITION_TO_MS = 1500.0  # 1 position ahead of median ≈ -1500ms lap time delta
    out = {}
    for constructor, years in offsets.items():
        out[constructor] = {}
        for year, delta in years.items():
            out[constructor][year] = round(delta * POSITION_TO_MS, 1)
    return out


def _normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Map actual GCS parquet column names to the canonical column names used by
    compute_offsets (constructorId, year, positionOrder).

    The raw race_results.parquet from Jolpica stores:
      - Constructor: serialised dict with key 'constructorId'
      - season: int year
      - position: finishing position (int)
    """
    df = df.copy()

    # Extract constructorId from nested Constructor dict string if needed
    if "constructorId" not in df.columns and "Constructor" in df.columns:
        import ast

        def _extract_constructor_id(val: object) -> str:
            if isinstance(val, dict):
                return str(val.get("constructorId", "unknown"))
            try:
                parsed = ast.literal_eval(str(val))
                if isinstance(parsed, dict):
                    return str(parsed.get("constructorId", "unknown"))
            except Exception:
                pass
            return str(val)

        df["constructorId"] = df["Constructor"].apply(_extract_constructor_id)

    # Map season → year
    if "year" not in df.columns and "season" in df.columns:
        df["year"] = df["season"]

    # Map position → positionOrder
    if "positionOrder" not in df.columns and "position" in df.columns:
        df["positionOrder"] = df["position"]

    return df


def build(input_path: str, output_path: str) -> None:
    df = pd.read_parquet(input_path)
    df = _normalise_columns(df)

    required = {"constructorId", "year", "positionOrder"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns in parquet: {missing}")

    df = df[df["positionOrder"].notna()].copy()
    df["positionOrder"] = pd.to_numeric(df["positionOrder"], errors="coerce")
    df = df.dropna(subset=["positionOrder"])

    offsets = compute_offsets(df)
    offsets_ms = normalise_to_ms(offsets)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(offsets_ms, f, indent=2, sort_keys=True)
    print(f"Written {len(offsets_ms)} constructors to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="frontend/public/data/car_performance.json")
    args = parser.parse_args()
    build(args.input, args.output)
