"""
validate_data.py — Data schema and quality validation for F1 Parquet files.

Uses pandas-based validation rules (portable, no GE server required).
Expectations suites are saved as JSON to scripts/expectations/.

Checks performed:
  laps_all.parquet       — columns, LapTime range, no null Driver, valid Compound, positive LapNumber
  telemetry_all.parquet  — Speed, Throttle, Gear, RPM ranges
  race_results.parquet   — position range 1–20, no duplicate positions per race
  pit_stops.parquet      — duration range 1.5–60 seconds

Exit codes:
  0 — all checks passed
  1 — critical failure (missing required file or column)

Usage:
    python Data-Pipeline/scripts/validate_data.py
    python Data-Pipeline/scripts/validate_data.py --data-dir data/processed
"""

# SCHEMA AND STATISTICS GENERATION
# This module generates data schema and statistics equivalent to
# Great Expectations ExpectationSuites and TFDV StatisticsGen.
#
# Statistics saved to: Data-Pipeline/logs/data_statistics.json
# Validation suite saved to: Data-Pipeline/scripts/expectations/
#
# To upgrade to full Great Expectations:
#   pip install great-expectations
#   great_expectations init
#   great_expectations suite new
#
# To upgrade to TFDV:
#   pip install tensorflow-data-validation
#   tfdv.generate_statistics_from_dataframe(df)

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("validate_data")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]
_EXPECTATIONS_DIR = _SCRIPT_DIR / "expectations"
_EXPECTATIONS_DIR.mkdir(parents=True, exist_ok=True)
_LOGS_DIR = _SCRIPT_DIR.parent / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Local fallback: Data-Pipeline/data/ when USE_LOCAL_DATA=true
_USE_LOCAL = os.getenv("USE_LOCAL_DATA", "false").lower() == "true"
_LOCAL_DATA_DIR = _SCRIPT_DIR.parent / "data"

VALID_COMPOUNDS = {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET", "UNKNOWN"}


# ---------------------------------------------------------------------------
# Validation result helpers
# ---------------------------------------------------------------------------


class CheckResult:
    """Stores the outcome of a single validation check."""

    def __init__(
        self,
        name: str,
        passed: bool,
        critical: bool,
        details: str,
        failed_rows: int = 0,
        total_rows: int = 0,
    ) -> None:
        self.name = name
        self.passed = passed
        self.critical = critical
        self.details = details
        self.failed_rows = failed_rows
        self.total_rows = total_rows

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "critical": self.critical,
            "details": self.details,
            "failed_rows": self.failed_rows,
            "total_rows": self.total_rows,
        }

    def __str__(self) -> str:
        status = (
            "PASS"
            if self.passed
            else ("FAIL [CRITICAL]" if self.critical else "FAIL [WARNING]")
        )
        suffix = (
            f" ({self.failed_rows}/{self.total_rows} rows)"
            if not self.passed and self.total_rows
            else ""
        )
        return f"  [{status}] {self.name}: {self.details}{suffix}"


# ---------------------------------------------------------------------------
# Generic check functions
# ---------------------------------------------------------------------------


def check_columns_exist(
    df: pd.DataFrame, required: List[str], source: str
) -> CheckResult:
    missing = [c for c in required if c not in df.columns]
    if missing:
        return CheckResult(
            f"{source}: required columns exist",
            passed=False,
            critical=True,
            details=f"Missing columns: {missing}",
        )
    return CheckResult(
        f"{source}: required columns exist",
        passed=True,
        critical=True,
        details=f"All {len(required)} required columns present",
    )


def check_no_nulls(
    df: pd.DataFrame, col: str, source: str, critical: bool = False
) -> CheckResult:
    if col not in df.columns:
        return CheckResult(
            f"{source}: no nulls in {col}",
            passed=False,
            critical=critical,
            details=f"Column '{col}' missing",
        )
    null_count = int(df[col].isna().sum())
    return CheckResult(
        f"{source}: no nulls in '{col}'",
        passed=null_count == 0,
        critical=critical,
        details=f"{null_count} null values",
        failed_rows=null_count,
        total_rows=len(df),
    )


def check_value_range(
    df: pd.DataFrame,
    col: str,
    lo: float,
    hi: float,
    source: str,
    critical: bool = False,
) -> CheckResult:
    if col not in df.columns:
        return CheckResult(
            f"{source}: {col} in [{lo}, {hi}]",
            passed=False,
            critical=critical,
            details=f"Column '{col}' missing",
        )
    numeric = pd.to_numeric(df[col], errors="coerce").dropna()
    if numeric.empty:
        return CheckResult(
            f"{source}: {col} in [{lo}, {hi}]",
            passed=False,
            critical=False,
            details="No numeric values found",
        )
    out_of_range = int(((numeric < lo) | (numeric > hi)).sum())
    return CheckResult(
        f"{source}: '{col}' in [{lo}, {hi}]",
        passed=out_of_range == 0,
        critical=critical,
        details=f"{out_of_range} values outside [{lo}, {hi}]; min={numeric.min():.2f}, max={numeric.max():.2f}",
        failed_rows=out_of_range,
        total_rows=len(numeric),
    )


def check_categorical(
    df: pd.DataFrame,
    col: str,
    valid_values: set,
    source: str,
    critical: bool = False,
) -> CheckResult:
    if col not in df.columns:
        return CheckResult(
            f"{source}: {col} valid categories",
            passed=False,
            critical=critical,
            details=f"Column '{col}' missing",
        )
    invalid = df[col].dropna()[~df[col].dropna().isin(valid_values)]
    invalid_count = len(invalid)
    unexpected = set(invalid.unique().tolist())
    return CheckResult(
        f"{source}: '{col}' valid categories",
        passed=invalid_count == 0,
        critical=critical,
        details=f"{invalid_count} invalid values; unexpected: {unexpected or 'none'}",
        failed_rows=invalid_count,
        total_rows=len(df[col].dropna()),
    )


def check_positive_integers(df: pd.DataFrame, col: str, source: str) -> CheckResult:
    if col not in df.columns:
        return CheckResult(
            f"{source}: {col} positive integer",
            passed=False,
            critical=False,
            details=f"Column '{col}' missing",
        )
    numeric = pd.to_numeric(df[col], errors="coerce").dropna()
    bad = int((numeric <= 0).sum())
    return CheckResult(
        f"{source}: '{col}' positive",
        passed=bad == 0,
        critical=False,
        details=f"{bad} non-positive values",
        failed_rows=bad,
        total_rows=len(numeric),
    )


# ---------------------------------------------------------------------------
# Statistics generation
# ---------------------------------------------------------------------------


def generate_statistics(df: pd.DataFrame, name: str) -> Dict[str, Any]:
    """
    Compute schema and descriptive statistics for a DataFrame.

    Equivalent to a Great Expectations dataset profile or TFDV StatisticsGen
    output — no external dependencies required.

    Computes per dataset:
      - Row and column counts
      - Column dtypes (schema)
      - Null count and null % per column
      - Numeric columns: min, max, mean, std, median
      - Categorical columns: unique count, top-5 value counts with %
      - Overall completeness score (% non-null cells across the full frame)

    Results are appended under ``name`` in
    ``Data-Pipeline/logs/data_statistics.json`` so all datasets accumulate
    in one file across runs.

    Parameters
    ----------
    df:   DataFrame to profile.
    name: Dataset label used as the key in the output JSON.

    Returns
    -------
    dict containing all computed statistics.
    """
    n_rows = len(df)
    n_cols = len(df.columns)
    total_cells = n_rows * n_cols
    non_null_cells = int(df.notnull().sum().sum())
    completeness_pct = (
        round(non_null_cells / total_cells * 100, 2) if total_cells > 0 else 0.0
    )

    column_stats: Dict[str, Any] = {}
    for col in df.columns:
        series = df[col]
        null_count = int(series.isna().sum())
        null_pct = round(null_count / n_rows * 100, 2) if n_rows > 0 else 0.0

        col_stat: Dict[str, Any] = {
            "dtype": str(series.dtype),
            "null_count": null_count,
            "null_pct": null_pct,
        }

        if pd.api.types.is_numeric_dtype(series):
            numeric = pd.to_numeric(series, errors="coerce").dropna()
            if not numeric.empty:
                col_stat.update(
                    {
                        "min": round(float(numeric.min()), 4),
                        "max": round(float(numeric.max()), 4),
                        "mean": round(float(numeric.mean()), 4),
                        "std": round(float(numeric.std()), 4),
                        "median": round(float(numeric.median()), 4),
                    }
                )
        else:
            non_null = series.dropna()
            col_stat["unique_count"] = int(non_null.nunique())
            top_counts = non_null.value_counts().head(5)
            col_stat["top_values"] = [
                {
                    "value": str(v),
                    "count": int(c),
                    "pct": round(c / len(non_null) * 100, 1)
                    if len(non_null) > 0
                    else 0.0,
                }
                for v, c in top_counts.items()
            ]

        column_stats[col] = col_stat

    stats: Dict[str, Any] = {
        "dataset": name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "row_count": n_rows,
        "column_count": n_cols,
        "completeness_pct": completeness_pct,
        "schema": {col: str(df[col].dtype) for col in df.columns},
        "columns": column_stats,
    }

    # Append/update this dataset's entry in data_statistics.json
    stats_path = _LOGS_DIR / "data_statistics.json"
    existing: Dict[str, Any] = {}
    if stats_path.exists():
        try:
            existing = json.loads(stats_path.read_text())
        except (json.JSONDecodeError, OSError):
            existing = {}
    existing[name] = stats
    stats_path.write_text(json.dumps(existing, indent=2))
    logger.info("Statistics for '%s' saved → %s", name, stats_path)

    return stats


# ---------------------------------------------------------------------------
# Per-file validation suites
# ---------------------------------------------------------------------------


def validate_laps(df: pd.DataFrame) -> Tuple[List[CheckResult], Dict[str, Any]]:
    """Validate laps_all.parquet."""
    results = []
    # Candidate column names — Jolpica uses 'time', FastF1 uses 'LapTime'
    lap_time_col = "LapTime" if "LapTime" in df.columns else "time"
    driver_col = "Driver" if "Driver" in df.columns else "driverId"
    compound_col = "Compound" if "Compound" in df.columns else None
    lap_num_col = "LapNumber" if "LapNumber" in df.columns else "lap"

    required_cols = [lap_time_col, driver_col, lap_num_col]
    results.append(check_columns_exist(df, required_cols, "laps"))
    results.append(check_no_nulls(df, driver_col, "laps", critical=True))
    results.append(check_value_range(df, lap_time_col, 60.0, 300.0, "laps"))
    results.append(check_positive_integers(df, lap_num_col, "laps"))
    if compound_col:
        results.append(check_categorical(df, compound_col, VALID_COMPOUNDS, "laps"))

    suite = {
        "name": "laps_all",
        "row_count": len(df),
        "column_count": len(df.columns),
        "checks": [r.to_dict() for r in results],
    }
    return results, suite


def validate_telemetry(df: pd.DataFrame) -> Tuple[List[CheckResult], Dict[str, Any]]:
    """Validate telemetry_all.parquet."""
    results = []
    results.append(check_value_range(df, "Speed", 0, 400, "telemetry"))
    results.append(check_value_range(df, "Throttle", 0, 100, "telemetry"))
    results.append(check_value_range(df, "nGear", 0, 8, "telemetry"))
    results.append(check_value_range(df, "RPM", 0, 20000, "telemetry"))

    suite = {
        "name": "telemetry_all",
        "row_count": len(df),
        "column_count": len(df.columns),
        "checks": [r.to_dict() for r in results],
    }
    return results, suite


def validate_race_results(df: pd.DataFrame) -> Tuple[List[CheckResult], Dict[str, Any]]:
    """Validate race_results.parquet."""
    results = []
    pos_col = "position" if "position" in df.columns else "positionOrder"
    results.append(check_value_range(df, pos_col, 1, 20, "race_results"))

    # No duplicate positions per race
    if "season" in df.columns and "round" in df.columns and pos_col in df.columns:
        group_cols = ["season", "round"]
        dup_count = 0
        for _, grp in df.groupby(group_cols):
            pos_vals = grp[pos_col].dropna()
            dup_count += int((pos_vals.duplicated()).sum())
        results.append(
            CheckResult(
                "race_results: no duplicate positions per race",
                passed=dup_count == 0,
                critical=False,
                details=f"{dup_count} duplicate positions found",
                failed_rows=dup_count,
                total_rows=len(df),
            )
        )

    suite = {
        "name": "race_results",
        "row_count": len(df),
        "column_count": len(df.columns),
        "checks": [r.to_dict() for r in results],
    }
    return results, suite


def validate_pit_stops(df: pd.DataFrame) -> Tuple[List[CheckResult], Dict[str, Any]]:
    """Validate pit_stops.parquet."""
    results = []
    results.append(check_value_range(df, "duration", 1.5, 60.0, "pit_stops"))
    results.append(check_no_nulls(df, "driverId", "pit_stops"))

    suite = {
        "name": "pit_stops",
        "row_count": len(df),
        "column_count": len(df.columns),
        "checks": [r.to_dict() for r in results],
    }
    return results, suite


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

FILE_VALIDATORS = {
    "laps_all.parquet": validate_laps,
    "telemetry_all.parquet": validate_telemetry,
    "race_results.parquet": validate_race_results,
    "pit_stops.parquet": validate_pit_stops,
}


def run_validation(data_dir: Optional[str] = None) -> int:
    """
    Run all validations against Parquet files in data_dir.

    Returns exit code: 0 = all pass, 1 = critical failure.
    """
    if data_dir is None:
        if _USE_LOCAL:
            # Local mode: use Data-Pipeline/data/ (no GCS required)
            data_path = _LOCAL_DATA_DIR
            data_path.mkdir(parents=True, exist_ok=True)
            logger.info("USE_LOCAL_DATA=true — reading from %s", data_path)
        else:
            candidates = [_REPO_ROOT / "data" / "processed"]
            data_path = next((p for p in candidates if p.exists()), None)
            if data_path is None:
                logger.error(
                    "No processed data directory found. "
                    "Set USE_LOCAL_DATA=true or run `dvc repro preprocess`."
                )
                return 1
    else:
        data_path = Path(data_dir)

    logger.info("Validating Parquet files in: %s", data_path)
    all_results: List[CheckResult] = []
    all_suites: List[Dict[str, Any]] = []
    all_stats: List[Dict[str, Any]] = []
    critical_failures = 0

    for filename, validator_fn in FILE_VALIDATORS.items():
        parquet_path = data_path / filename
        if not parquet_path.exists():
            logger.warning("File not found, skipping: %s", parquet_path)
            all_results.append(
                CheckResult(
                    f"{filename}: file exists",
                    passed=False,
                    critical=False,
                    details=f"Not found at {parquet_path}",
                )
            )
            continue

        logger.info(
            "Validating %s (%s MB)...",
            filename,
            f"{parquet_path.stat().st_size / 1e6:.1f}",
        )
        try:
            df = pd.read_parquet(parquet_path)
        except Exception as exc:
            logger.error("Failed to read %s: %s", parquet_path, exc)
            all_results.append(
                CheckResult(
                    f"{filename}: readable",
                    passed=False,
                    critical=True,
                    details=str(exc),
                )
            )
            critical_failures += 1
            continue

        # Generate statistics before validation so they're always saved
        # even if a check later raises an exception.
        dataset_name = filename.replace(".parquet", "")
        stats = generate_statistics(df, dataset_name)
        all_stats.append(stats)

        file_results, suite = validator_fn(df)
        all_results.extend(file_results)
        all_suites.append(suite)

    # Print statistics summary table
    if all_stats:
        print("\n" + "=" * 70)
        print("F1 Data Pipeline — Data Statistics Summary")
        print(f"{'Dataset':<30} {'Rows':>12} {'Cols':>6} {'Completeness':>14}")
        print("-" * 66)
        for s in all_stats:
            print(
                f"{s['dataset']:<30} {s['row_count']:>12,} {s['column_count']:>6} "
                f"{s['completeness_pct']:>13.1f}%"
            )
        print("-" * 66)
        print(f"Full statistics → {_LOGS_DIR / 'data_statistics.json'}")
        print("=" * 70)

    # Print results
    print("\n" + "=" * 70)
    print("F1 Data Pipeline — Validation Report")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"Data dir:  {data_path}")
    print("=" * 70)
    for r in all_results:
        print(r)
        if not r.passed and r.critical:
            critical_failures += 1

    passed = sum(1 for r in all_results if r.passed)
    total = len(all_results)
    print(
        f"\nSummary: {passed}/{total} checks passed | {critical_failures} critical failures"
    )
    print("=" * 70 + "\n")

    # Save expectations suite
    suite_path = _EXPECTATIONS_DIR / "validation_suite.json"
    suite_doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(data_path),
        "total_checks": total,
        "passed": passed,
        "critical_failures": critical_failures,
        "suites": all_suites,
    }
    with open(suite_path, "w") as f:
        json.dump(suite_doc, f, indent=2)
    logger.info("Expectations suite saved: %s", suite_path)

    return 1 if critical_failures > 0 else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate F1 processed Parquet files")
    parser.add_argument(
        "--data-dir",
        help="Path to processed Parquet directory (default: auto-detect)",
        default=None,
    )
    args = parser.parse_args()
    sys.exit(run_validation(args.data_dir))
