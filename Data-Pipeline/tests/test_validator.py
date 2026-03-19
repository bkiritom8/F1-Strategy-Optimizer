"""
test_validator.py — Unit tests for src/preprocessing/validator.py

Tests cover: valid record acceptance, missing-column detection, null-value
handling, range validation, schema enforcement, and empty-DataFrame resilience.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.preprocessing.validator import (  # noqa: E402
    DataValidator,
    RaceDataSchema,
    TelemetryDataSchema,
    ValidationError,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def valid_race_row():
    """One fully valid RaceDataSchema record."""
    return {
        "race_id": 1,
        "year": 2024,
        "round": 1,
        "circuit_id": "bahrain",
        "name": "Bahrain Grand Prix",
        "date": "2024-03-02",
    }


@pytest.fixture
def valid_telemetry_row():
    """One fully valid TelemetryDataSchema record."""
    return {
        "race_id": "race_2024_1",
        "driver_id": "VER",
        "lap": 1,
        "timestamp": "2024-03-02T15:00:00",
        "speed": 280.0,
        "throttle": 0.9,
        "brake": False,
        "gear": 7,
        "rpm": 12000,
    }


# ── Valid DataFrame ───────────────────────────────────────────────────────────


def test_valid_dataframe_passes(valid_race_row):
    """A clean DataFrame conforming to RaceDataSchema must be fully valid."""
    df = pd.DataFrame([valid_race_row])
    validator = DataValidator()
    valid_df, report = validator.validate_dataframe(df, RaceDataSchema)
    assert report["valid"] == 1
    assert report["invalid"] == 0
    assert report["validation_rate"] == 1.0


# ── Missing required column ───────────────────────────────────────────────────


def test_missing_required_column_fails(valid_race_row):
    """Passing required_columns that are absent must raise ValidationError."""
    df = pd.DataFrame([{"race_id": 1}])
    validator = DataValidator()
    with pytest.raises(ValidationError, match="Missing required columns"):
        validator.validate_dataframe(
            df, RaceDataSchema, required_columns=["year", "round", "circuit_id"]
        )


# ── Null values ───────────────────────────────────────────────────────────────


def test_null_values_detected(valid_race_row):
    """A record with a null in a required field must end up as invalid."""
    bad_row = dict(valid_race_row)
    bad_row["circuit_id"] = None  # Pydantic Field min_length=1 rejects None
    df = pd.DataFrame([bad_row])
    validator = DataValidator()
    _, report = validator.validate_dataframe(df, RaceDataSchema)
    assert report["invalid"] == 1


# ── Negative / out-of-range lap time ─────────────────────────────────────────


def test_invalid_lap_time_flagged(valid_telemetry_row):
    """A negative speed value must be flagged as an invalid record."""
    bad_row = dict(valid_telemetry_row)
    bad_row["speed"] = -10.0  # TelemetryDataSchema: speed ge=0
    df = pd.DataFrame([bad_row])
    validator = DataValidator()
    _, report = validator.validate_dataframe(df, TelemetryDataSchema)
    assert report["invalid"] == 1


# ── Valid compound / range values ─────────────────────────────────────────────


def test_valid_compound_passes(valid_telemetry_row):
    """A record with speed in [0, 400] and throttle in [0, 1] must be fully valid."""
    df = pd.DataFrame([valid_telemetry_row])
    validator = DataValidator()
    _, report = validator.validate_dataframe(df, TelemetryDataSchema)
    assert report["valid"] == 1
    assert report["invalid"] == 0


def test_invalid_compound_fails(valid_telemetry_row):
    """A record with speed > 400 must be rejected by TelemetryDataSchema."""
    bad_row = dict(valid_telemetry_row)
    bad_row["speed"] = 500.0  # TelemetryDataSchema: speed le=400
    df = pd.DataFrame([bad_row])
    validator = DataValidator()
    _, report = validator.validate_dataframe(df, TelemetryDataSchema)
    assert report["invalid"] == 1


# ── Empty DataFrame ───────────────────────────────────────────────────────────


def test_empty_dataframe_handled(valid_race_row):
    """validate_dataframe on an empty DataFrame must not crash and return 0 valid."""
    df = pd.DataFrame(columns=list(valid_race_row.keys()))
    validator = DataValidator()
    valid_df, report = validator.validate_dataframe(df, RaceDataSchema)
    assert len(valid_df) == 0
    assert report["total"] == 0
    assert report["valid"] == 0
