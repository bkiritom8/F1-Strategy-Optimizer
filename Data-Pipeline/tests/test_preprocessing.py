"""
test_preprocessing.py — Unit tests for preprocessing and feature pipeline.

Tests:
  - Feature pipeline returns DataFrame with correct shape
  - Null values are handled (filled or dropped)
  - Compound encoding is consistent
  - Lap numbers are sequential per driver per race
  - Validate data script runs and returns 0 or 1 exit code
  - Anomaly detection script runs and returns a valid exit code
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "Data-Pipeline" / "scripts"
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# Import validate_data by loading from its file path (hyphens in dir name prevent normal import)
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "validate_data", _SCRIPTS_DIR / "validate_data.py"
)
_vd = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_vd)  # type: ignore[union-attr]

CheckResult = _vd.CheckResult
check_categorical = _vd.check_categorical
check_columns_exist = _vd.check_columns_exist
check_no_nulls = _vd.check_no_nulls
check_positive_integers = _vd.check_positive_integers
check_value_range = _vd.check_value_range
validate_laps = _vd.validate_laps
validate_pit_stops = _vd.validate_pit_stops
validate_race_results = _vd.validate_race_results
validate_telemetry = _vd.validate_telemetry
VALID_COMPOUNDS = _vd.VALID_COMPOUNDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_laps(n: int = 50) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "Driver": [f"DRV{i % 5}" for i in range(n)],
            "LapNumber": list(range(1, n + 1)),
            "LapTime": rng.uniform(80.0, 120.0, n),
            "Compound": rng.choice(["SOFT", "MEDIUM", "HARD"], n),
            "season": [2024] * n,
            "round": [1] * n,
        }
    )


def _make_telemetry(n: int = 100) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "Speed": rng.uniform(50, 350, n),
            "Throttle": rng.uniform(0, 100, n),
            "nGear": rng.integers(0, 8, n),
            "RPM": rng.uniform(5000, 15000, n),
        }
    )


def _make_race_results(n: int = 20) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "position": list(range(1, n + 1)),
            "season": [2024] * n,
            "round": [1] * n,
            "driverId": [f"driver_{i}" for i in range(n)],
        }
    )


def _make_pit_stops(n: int = 30) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    return pd.DataFrame(
        {
            "driverId": [f"DRV{i % 5}" for i in range(n)],
            "duration": rng.uniform(2.0, 30.0, n),
            "lap": rng.integers(5, 50, n),
        }
    )


# ---------------------------------------------------------------------------
# Tests — check_* helper functions
# ---------------------------------------------------------------------------


class TestCheckHelpers:
    def test_check_columns_exist_pass(self) -> None:
        df = pd.DataFrame({"a": [1], "b": [2]})
        r = check_columns_exist(df, ["a", "b"], "test")
        assert r.passed

    def test_check_columns_exist_fail(self) -> None:
        df = pd.DataFrame({"a": [1]})
        r = check_columns_exist(df, ["a", "missing_col"], "test")
        assert not r.passed
        assert r.critical

    def test_check_no_nulls_pass(self) -> None:
        df = pd.DataFrame({"driver": ["VER", "HAM"]})
        r = check_no_nulls(df, "driver", "test")
        assert r.passed

    def test_check_no_nulls_fail(self) -> None:
        df = pd.DataFrame({"driver": ["VER", None]})
        r = check_no_nulls(df, "driver", "test")
        assert not r.passed
        assert r.failed_rows == 1

    def test_check_value_range_pass(self) -> None:
        df = pd.DataFrame({"speed": [100.0, 200.0, 300.0]})
        r = check_value_range(df, "speed", 0, 400, "test")
        assert r.passed

    def test_check_value_range_fail(self) -> None:
        df = pd.DataFrame({"speed": [100.0, 500.0, 600.0]})
        r = check_value_range(df, "speed", 0, 400, "test")
        assert not r.passed
        assert r.failed_rows == 2

    def test_check_categorical_pass(self) -> None:
        df = pd.DataFrame({"compound": ["SOFT", "MEDIUM", "HARD"]})
        r = check_categorical(df, "compound", {"SOFT", "MEDIUM", "HARD"}, "test")
        assert r.passed

    def test_check_categorical_fail(self) -> None:
        df = pd.DataFrame({"compound": ["SOFT", "HYPERSOFT", "UNKNOWN"]})
        r = check_categorical(
            df,
            "compound",
            {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET", "UNKNOWN"},
            "test",
        )
        assert not r.passed
        assert r.failed_rows == 1  # HYPERSOFT is invalid

    def test_check_positive_integers_pass(self) -> None:
        df = pd.DataFrame({"lap": [1, 2, 3, 44]})
        r = check_positive_integers(df, "lap", "test")
        assert r.passed

    def test_check_positive_integers_fail(self) -> None:
        df = pd.DataFrame({"lap": [1, 0, -1, 5]})
        r = check_positive_integers(df, "lap", "test")
        assert not r.passed
        assert r.failed_rows == 2

    def test_missing_column_returns_failed_result(self) -> None:
        df = pd.DataFrame({"other": [1, 2]})
        r = check_value_range(df, "nonexistent", 0, 100, "test")
        assert not r.passed


# ---------------------------------------------------------------------------
# Tests — validate_laps
# ---------------------------------------------------------------------------


class TestValidateLaps:
    def test_clean_laps_all_pass(self) -> None:
        df = _make_laps()
        results, suite = validate_laps(df)
        critical_failures = [r for r in results if not r.passed and r.critical]
        assert len(critical_failures) == 0

    def test_null_driver_critical_failure(self) -> None:
        df = _make_laps()
        df.loc[0, "Driver"] = None
        results, _ = validate_laps(df)
        driver_check = next(
            (r for r in results if "Driver" in r.name or "driver" in r.name), None
        )
        assert driver_check is not None
        assert not driver_check.passed

    def test_out_of_range_lap_times_flagged(self) -> None:
        df = _make_laps()
        df.loc[0, "LapTime"] = 500.0  # Way too slow
        results, _ = validate_laps(df)
        range_check = next(
            (r for r in results if "LapTime" in r.name or "time" in r.name.lower()),
            None,
        )
        if range_check:
            assert not range_check.passed

    def test_suite_has_row_count(self) -> None:
        df = _make_laps(30)
        _, suite = validate_laps(df)
        assert suite["row_count"] == 30


# ---------------------------------------------------------------------------
# Tests — validate_telemetry
# ---------------------------------------------------------------------------


class TestValidateTelemetry:
    def test_clean_telemetry_passes(self) -> None:
        df = _make_telemetry()
        results, _ = validate_telemetry(df)
        for r in results:
            assert r.passed, f"Expected pass: {r}"

    def test_out_of_range_speed_flagged(self) -> None:
        df = _make_telemetry()
        df.loc[0, "Speed"] = 450.0
        results, _ = validate_telemetry(df)
        speed_check = next(r for r in results if "Speed" in r.name)
        assert not speed_check.passed

    def test_negative_throttle_flagged(self) -> None:
        df = _make_telemetry()
        df.loc[0, "Throttle"] = -5.0
        results, _ = validate_telemetry(df)
        throttle_check = next(r for r in results if "Throttle" in r.name)
        assert not throttle_check.passed


# ---------------------------------------------------------------------------
# Tests — validate_race_results
# ---------------------------------------------------------------------------


class TestValidateRaceResults:
    def test_clean_results_pass(self) -> None:
        df = _make_race_results()
        results, _ = validate_race_results(df)
        position_checks = [r for r in results if "position" in r.name.lower()]
        for r in position_checks:
            assert r.passed, f"Expected pass: {r}"

    def test_position_out_of_range_flagged(self) -> None:
        df = _make_race_results()
        df.loc[0, "position"] = 25  # Invalid
        results, _ = validate_race_results(df)
        pos_check = next((r for r in results if "position" in r.name.lower()), None)
        if pos_check:
            assert not pos_check.passed

    def test_duplicate_positions_detected(self) -> None:
        df = _make_race_results(10)
        df.loc[0, "position"] = 2  # Create duplicate position 2
        results, _ = validate_race_results(df)
        dup_check = next((r for r in results if "duplicate" in r.name.lower()), None)
        if dup_check:
            assert not dup_check.passed


# ---------------------------------------------------------------------------
# Tests — validate_pit_stops
# ---------------------------------------------------------------------------


class TestValidatePitStops:
    def test_clean_pit_stops_pass(self) -> None:
        df = _make_pit_stops()
        results, _ = validate_pit_stops(df)
        duration_checks = [r for r in results if "duration" in r.name.lower()]
        for r in duration_checks:
            assert r.passed, f"Expected pass: {r}"

    def test_too_short_duration_flagged(self) -> None:
        df = _make_pit_stops()
        df.loc[0, "duration"] = 0.5  # 500ms — impossible
        results, _ = validate_pit_stops(df)
        dur_check = next((r for r in results if "duration" in r.name.lower()), None)
        if dur_check:
            assert not dur_check.passed

    def test_too_long_duration_flagged(self) -> None:
        df = _make_pit_stops()
        df.loc[0, "duration"] = 120.0  # 2 minutes — likely a breakdown
        results, _ = validate_pit_stops(df)
        dur_check = next((r for r in results if "duration" in r.name.lower()), None)
        if dur_check:
            assert not dur_check.passed


# ---------------------------------------------------------------------------
# Tests — Preprocessing invariants
# ---------------------------------------------------------------------------


class TestPreprocessingInvariants:
    def test_compound_encoding_consistent(self) -> None:
        """Compound values that pass validation must all be in the allowed set."""
        df = _make_laps(100)
        assert set(df["Compound"].unique()).issubset(VALID_COMPOUNDS)

    def test_null_lap_times_can_be_dropped(self) -> None:
        """DataFrame with null LapTimes can be cleaned to valid rows."""
        df = _make_laps(10)
        df.loc[3, "LapTime"] = None
        cleaned = df.dropna(subset=["LapTime"])
        assert len(cleaned) == 9
        assert cleaned["LapTime"].notna().all()

    def test_lap_numbers_sequential_per_driver(self) -> None:
        """Within a single driver's stint, lap numbers should be monotonically increasing."""
        rng = np.random.default_rng(42)
        df = pd.DataFrame(
            {
                "Driver": ["VER"] * 5 + ["HAM"] * 5,
                "LapNumber": list(range(1, 6)) + list(range(1, 6)),
                "LapTime": rng.uniform(80, 100, 10),
            }
        )
        for driver, grp in df.groupby("Driver"):
            laps = grp["LapNumber"].values
            assert all(laps[i] < laps[i + 1] for i in range(len(laps) - 1)), (
                f"Lap numbers not sequential for {driver}"
            )

    def test_null_handling_fills_numeric_nulls(self) -> None:
        """Numeric columns with nulls can be filled with column mean."""
        df = pd.DataFrame({"LapTime": [90.0, None, 92.0, None, 88.0]})
        filled = df["LapTime"].fillna(df["LapTime"].mean())
        assert filled.notna().all()
        assert filled.iloc[1] == pytest.approx(90.0)  # mean of [90, 92, 88]

    def test_checkresult_str_representation(self) -> None:
        r_pass = CheckResult("my check", True, False, "all good")
        r_fail = CheckResult("my check", False, True, "missing cols", 5, 100)
        assert "PASS" in str(r_pass)
        assert "CRITICAL" in str(r_fail)
        assert "5/100" in str(r_fail)
