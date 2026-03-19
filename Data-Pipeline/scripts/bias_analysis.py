"""
bias_analysis.py — Detect representation bias in the F1 dataset via data slicing.

Slices data by:
  - Era:          pre-2010 (V10/V8 NA), 2010–2013 (V8 + KERS), 2014+ (hybrid turbo)
  - Team tier:    top (constructor top-3 historically), mid, backmarker
  - Circuit type: street, permanent, mixed
  - Weather:      dry, wet (sessions with Rainfall flag)

For each slice computes:
  - Sample count and representation %
  - Mean and std lap time
  - Missing value rate (all columns)

Outputs ASCII table to stdout and saves bias_report.json.

Usage:
    python Data-Pipeline/scripts/bias_analysis.py
    python Data-Pipeline/scripts/bias_analysis.py --data-dir data/processed
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("bias_analysis")

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]
_LOGS_DIR = _SCRIPT_DIR.parent / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Local fallback: Data-Pipeline/data/ when USE_LOCAL_DATA=true
_USE_LOCAL = os.getenv("USE_LOCAL_DATA", "false").lower() == "true"
_LOCAL_DATA_DIR = _SCRIPT_DIR.parent / "data"

# ---------------------------------------------------------------------------
# Classification lookups
# ---------------------------------------------------------------------------

# Teams historically in the top-3 constructors championships (simplified)
_TOP_TEAMS = {
    "ferrari",
    "mercedes",
    "red_bull",
    "mclaren",
    "williams",
    "lotus_f1",
    "brawn",
    "renault",
    "alpine",
}
_MID_TEAMS = {
    "force_india",
    "racing_point",
    "aston_martin",
    "haas",
    "alfa",
    "toro_rosso",
    "alphatauri",
    "sauber",
}
# Everything else is backmarker

# Street circuits (tight, slow, urban)
_STREET_CIRCUITS = {
    "monaco",
    "singapore",
    "baku",
    "azerbaijan",
    "jeddah",
    "las_vegas",
    "miami",
    "long_beach",
}
# Mixed (hybrid permanent + some barriers)
_MIXED_CIRCUITS = {
    "albert_park",
    "hungaroring",
    "marina_bay",
    "istanbul",
}


def _classify_team(constructor: str) -> str:
    c = str(constructor).lower().replace(" ", "_").replace("-", "_")
    if any(t in c for t in _TOP_TEAMS):
        return "top"
    if any(t in c for t in _MID_TEAMS):
        return "mid"
    return "backmarker"


def _classify_circuit(circuit_id: str) -> str:
    cid = str(circuit_id).lower().replace(" ", "_").replace("-", "_")
    if any(s in cid for s in _STREET_CIRCUITS):
        return "street"
    if any(s in cid for s in _MIXED_CIRCUITS):
        return "mixed"
    return "permanent"


# ---------------------------------------------------------------------------
# Slice statistics helper
# ---------------------------------------------------------------------------

SliceStats = Dict[str, Any]


def _compute_slice_stats(
    df: pd.DataFrame,
    label: str,
    total_rows: int,
    lap_time_col: Optional[str] = None,
) -> SliceStats:
    count = len(df)
    if count == 0:
        return {
            "slice": label,
            "count": 0,
            "representation_pct": 0.0,
            "mean_lap_time_s": None,
            "std_lap_time_s": None,
            "missing_pct": None,
        }
    rep = round(count / total_rows * 100, 1) if total_rows > 0 else 0.0
    missing_pct = round(df.isna().mean().mean() * 100, 1)

    mean_lt = std_lt = None
    if lap_time_col and lap_time_col in df.columns:
        lt = pd.to_numeric(df[lap_time_col], errors="coerce").dropna()
        if not lt.empty:
            mean_lt = round(float(lt.mean()), 1)
            std_lt = round(float(lt.std()), 1)

    return {
        "slice": label,
        "count": count,
        "representation_pct": rep,
        "mean_lap_time_s": mean_lt,
        "std_lap_time_s": std_lt,
        "missing_pct": missing_pct,
    }


# ---------------------------------------------------------------------------
# ASCII table printer
# ---------------------------------------------------------------------------


def _print_table(rows: List[SliceStats], title: str) -> None:
    cols = ["slice", "count", "mean_lap_time_s", "missing_pct", "representation_pct"]
    headers = ["Slice", "Count", "Mean LapTime (s)", "Missing%", "Representation%"]
    widths = [
        max(len(h), max((len(str(r.get(c, ""))) for r in rows), default=0))
        for h, c in zip(headers, cols)
    ]

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    header_row = "|" + "|".join(f" {h:<{w}} " for h, w in zip(headers, widths)) + "|"

    print(f"\n{title}")
    print(sep)
    print(header_row)
    print(sep)
    for r in rows:
        cells = [str(r.get(c, "N/A")) for c in cols]
        row_line = "|" + "|".join(f" {c:<{w}} " for c, w in zip(cells, widths)) + "|"
        print(row_line)
    print(sep)


# ---------------------------------------------------------------------------
# Slicing functions
# ---------------------------------------------------------------------------


def slice_by_era(df: pd.DataFrame, lap_time_col: Optional[str]) -> List[SliceStats]:
    if "season" not in df.columns:
        return []
    total = len(df)
    seasons = pd.to_numeric(df["season"], errors="coerce")
    slices = []
    for label, mask in [
        ("pre-2010 (NA)", seasons < 2010),
        ("2010-2013 (V8 KERS)", (seasons >= 2010) & (seasons <= 2013)),
        ("2014+ (hybrid)", seasons >= 2014),
    ]:
        slices.append(_compute_slice_stats(df[mask], label, total, lap_time_col))
    return slices


def slice_by_team(df: pd.DataFrame, lap_time_col: Optional[str]) -> List[SliceStats]:
    ctor_col = next(
        (
            c
            for c in ["constructorId", "Constructor", "Team", "teamId"]
            if c in df.columns
        ),
        None,
    )
    if ctor_col is None:
        return []
    total = len(df)
    df = df.copy()
    df["_tier"] = df[ctor_col].apply(_classify_team)
    slices = []
    for tier in ["top", "mid", "backmarker"]:
        slices.append(
            _compute_slice_stats(
                df[df["_tier"] == tier], f"team:{tier}", total, lap_time_col
            )
        )
    return slices


def slice_by_circuit(df: pd.DataFrame, lap_time_col: Optional[str]) -> List[SliceStats]:
    cid_col = next(
        (
            c
            for c in ["circuitId", "Circuit", "circuit_id", "raceName"]
            if c in df.columns
        ),
        None,
    )
    if cid_col is None:
        return []
    total = len(df)
    df = df.copy()
    df["_ctype"] = df[cid_col].apply(_classify_circuit)
    slices = []
    for ctype in ["street", "permanent", "mixed"]:
        slices.append(
            _compute_slice_stats(
                df[df["_ctype"] == ctype], f"circuit:{ctype}", total, lap_time_col
            )
        )
    return slices


def slice_by_weather(df: pd.DataFrame, lap_time_col: Optional[str]) -> List[SliceStats]:
    rain_col = next(
        (
            c
            for c in ["Rainfall", "rainfall", "rain", "IsWet", "wet"]
            if c in df.columns
        ),
        None,
    )
    if rain_col is None:
        return []
    total = len(df)
    rain = pd.to_numeric(df[rain_col], errors="coerce").fillna(0).astype(bool)
    slices = [
        _compute_slice_stats(df[~rain], "weather:dry", total, lap_time_col),
        _compute_slice_stats(df[rain], "weather:wet", total, lap_time_col),
    ]
    return slices


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_bias_analysis(data_dir: Optional[str] = None) -> int:
    """Run bias analysis on processed Parquet data. Returns exit code."""
    if data_dir is None:
        if _USE_LOCAL:
            data_path = _LOCAL_DATA_DIR
            data_path.mkdir(parents=True, exist_ok=True)
            logger.info("USE_LOCAL_DATA=true — reading from %s", data_path)
        else:
            data_path = _REPO_ROOT / "data" / "processed"
    else:
        data_path = Path(data_dir)

    if not data_path.exists():
        logger.error("Data directory not found: %s", data_path)
        return 1

    logger.info("Running bias analysis on: %s", data_path)

    # Load laps data (primary source for bias analysis)
    laps_path = data_path / "laps_all.parquet"
    if not laps_path.exists():
        logger.warning("laps_all.parquet not found, trying race_results.parquet")
        laps_path = data_path / "race_results.parquet"
    if not laps_path.exists():
        logger.error("No laps or race_results Parquet found in %s", data_path)
        return 1

    logger.info("Loading %s...", laps_path)
    df = pd.read_parquet(laps_path)
    logger.info("Loaded %d rows, %d columns", len(df), len(df.columns))

    total = len(df)
    lap_time_col = next(
        (
            c
            for c in ["LapTime", "time", "lap_time", "LapTimeSeconds"]
            if c in df.columns
        ),
        None,
    )
    if lap_time_col:
        logger.info("Using lap time column: %s", lap_time_col)

    # Run all slicers
    all_slices: Dict[str, List[SliceStats]] = {}
    all_slices["Era"] = slice_by_era(df, lap_time_col)
    all_slices["Team Tier"] = slice_by_team(df, lap_time_col)
    all_slices["Circuit Type"] = slice_by_circuit(df, lap_time_col)
    all_slices["Weather"] = slice_by_weather(df, lap_time_col)

    # Print ASCII tables
    print("\n" + "=" * 70)
    print("F1 Data Pipeline — Bias Analysis Report")
    print(f"Timestamp : {datetime.now(timezone.utc).isoformat()}")
    print(f"Data dir  : {data_path}")
    print(f"Total rows: {total:,}")
    print("=" * 70)

    for dimension, slices in all_slices.items():
        if slices:
            _print_table(slices, f"[{dimension}]")

    # Identify potential bias issues
    print("\n[Bias Findings]")
    findings: List[str] = []
    for dimension, slices in all_slices.items():
        for s in slices:
            if s["count"] == 0:
                findings.append(
                    f"  - {s['slice']}: NO DATA — this subgroup is completely absent"
                )
            elif s["representation_pct"] < 5.0:
                findings.append(
                    f"  - {s['slice']}: underrepresented ({s['representation_pct']}% of data)"
                )
            if s.get("missing_pct") is not None and s["missing_pct"] > 20.0:
                findings.append(
                    f"  - {s['slice']}: high missing rate ({s['missing_pct']}%)"
                )
    if findings:
        for f in findings:
            print(f)
    else:
        print("  No significant representation bias detected.")
    print("=" * 70 + "\n")

    # Save report
    report: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(data_path),
        "source_file": str(laps_path),
        "total_rows": total,
        "lap_time_column": lap_time_col,
        "slices": all_slices,
        "findings": findings,
    }
    report_path = _LOGS_DIR / "bias_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("Bias report saved: %s", report_path)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bias analysis via data slicing")
    parser.add_argument(
        "--data-dir", default=None, help="Path to processed Parquet directory"
    )
    args = parser.parse_args()
    sys.exit(run_bias_analysis(args.data_dir))
