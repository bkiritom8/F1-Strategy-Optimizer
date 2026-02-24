"""
test_anomaly_detection.py — Unit tests for Data-Pipeline/scripts/anomaly_detection.py

Tests cover: lap time outlier detection, missing driver IDs, invalid compound
values, pit stop duration bounds, anomaly report persistence, and Slack alerts.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

# ── Import module under test via file path (hyphen in directory) ───────────────
_REPO_ROOT = Path(__file__).parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "Data-Pipeline" / "scripts"

_spec = importlib.util.spec_from_file_location(
    "anomaly_detection", _SCRIPTS_DIR / "anomaly_detection.py"
)
_ad = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["anomaly_detection"] = _ad
_spec.loader.exec_module(_ad)  # type: ignore[union-attr]

check_laps = _ad.check_laps
check_pit_stops = _ad.check_pit_stops
run_anomaly_detection = _ad.run_anomaly_detection
_send_slack_alert = _ad._send_slack_alert


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def normal_laps_df():
    """50 laps tightly clustered around 90 s — no outliers expected."""
    return pd.DataFrame(
        {
            "Driver": ["VER"] * 50,
            "LapTime": [90.0 + i * 0.01 for i in range(50)],
            "CircuitId": ["monza"] * 50,
            "Compound": ["SOFT"] * 50,
        }
    )


@pytest.fixture
def outlier_laps_df():
    """49 normal laps + 1 extreme outlier on the same circuit (z ≈ 6.9 > 3)."""
    times = [90.0] * 49 + [9000.0]
    return pd.DataFrame(
        {
            "Driver": ["VER"] * 50,
            "LapTime": times,
            "CircuitId": ["monza"] * 50,
            "Compound": ["SOFT"] * 50,
        }
    )


# ── Lap-time outlier ──────────────────────────────────────────────────────────


def test_lap_time_outlier_detected(outlier_laps_df):
    """A lap time 10 σ above circuit mean must be flagged as WARNING."""
    anomalies = check_laps(outlier_laps_df)
    checks = [a["check"] for a in anomalies]
    assert "lap_time_outlier" in checks
    outlier_anomaly = next(a for a in anomalies if a["check"] == "lap_time_outlier")
    assert outlier_anomaly["severity"] == "WARNING"


def test_lap_time_within_normal_range(normal_laps_df):
    """Lap times within 2 σ of circuit mean must not trigger an outlier flag."""
    anomalies = check_laps(normal_laps_df)
    assert all(a["check"] != "lap_time_outlier" for a in anomalies)


# ── Missing driver ID ─────────────────────────────────────────────────────────


def test_missing_driver_id_detected():
    """Null Driver column must produce an ERROR anomaly."""
    df = pd.DataFrame(
        {
            "Driver": [None, "VER", "HAM"],
            "LapTime": [90.0, 91.0, 92.0],
            "CircuitId": ["monza"] * 3,
        }
    )
    anomalies = check_laps(df)
    by_check = {a["check"]: a for a in anomalies}
    assert "missing_driver_id" in by_check
    assert by_check["missing_driver_id"]["severity"] == "ERROR"


# ── Invalid compound ──────────────────────────────────────────────────────────


def test_invalid_compound_detected():
    """Compound values not in the valid set must trigger a WARNING anomaly."""
    df = pd.DataFrame(
        {
            "Driver": ["VER"] * 3,
            "LapTime": [90.0, 91.0, 92.0],
            "CircuitId": ["monza"] * 3,
            "Compound": ["SOFT", "SUPERSOFT", "HYPERSOFT"],
        }
    )
    anomalies = check_laps(df)
    checks = [a["check"] for a in anomalies]
    assert "invalid_compound" in checks


# ── Pit-stop duration ─────────────────────────────────────────────────────────


def test_pit_stop_too_short():
    """Pit stop shorter than 1.5 s must be flagged as WARNING."""
    df = pd.DataFrame({"duration": [0.5]})
    anomalies = check_pit_stops(df)
    assert any(a["check"] == "pit_stop_too_short" for a in anomalies)


def test_pit_stop_too_long():
    """Pit stop longer than 60 s must be flagged as WARNING."""
    df = pd.DataFrame({"duration": [120.0]})
    anomalies = check_pit_stops(df)
    assert any(a["check"] == "pit_stop_too_long" for a in anomalies)


def test_pit_stop_normal_duration():
    """A 25 s pit stop is within bounds — no anomaly expected."""
    df = pd.DataFrame({"duration": [25.0]})
    anomalies = check_pit_stops(df)
    assert len(anomalies) == 0


# ── Report persistence ────────────────────────────────────────────────────────


def test_anomaly_report_saved(tmp_path, monkeypatch):
    """run_anomaly_detection must save anomaly_report.json even when no parquet files exist."""
    monkeypatch.setattr(_ad, "_LOGS_DIR", tmp_path)
    data_dir = tmp_path / "processed"
    data_dir.mkdir()
    # No parquet files → all dataset checks are skipped; report still written
    run_anomaly_detection(str(data_dir))
    report_file = tmp_path / "anomaly_report.json"
    assert report_file.exists()
    report = json.loads(report_file.read_text())
    assert "timestamp" in report
    assert "total_anomalies" in report


# ── Slack webhook ─────────────────────────────────────────────────────────────


def test_slack_webhook_called_when_env_set(tmp_path, monkeypatch):
    """_send_slack_alert is called when SLACK_WEBHOOK_URL is set and anomalies exist."""
    monkeypatch.setattr(_ad, "_LOGS_DIR", tmp_path)
    data_dir = tmp_path / "processed"
    data_dir.mkdir()
    # Parquet with null Driver generates an ERROR anomaly so total > 0
    df = pd.DataFrame(
        {
            "Driver": [None, "VER"],
            "LapTime": [90.0, 91.0],
            "CircuitId": ["monza", "monza"],
        }
    )
    df.to_parquet(data_dir / "laps_all.parquet", index=False)
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.example/test")

    with patch.object(_ad, "_send_slack_alert") as mock_slack:
        run_anomaly_detection(str(data_dir))
        mock_slack.assert_called_once()


def test_slack_not_called_when_env_not_set(tmp_path, monkeypatch):
    """_send_slack_alert must NOT be called when SLACK_WEBHOOK_URL is absent."""
    monkeypatch.setattr(_ad, "_LOGS_DIR", tmp_path)
    data_dir = tmp_path / "processed"
    data_dir.mkdir()
    monkeypatch.delenv("SLACK_WEBHOOK_URL", raising=False)

    with patch.object(_ad, "_send_slack_alert") as mock_slack:
        run_anomaly_detection(str(data_dir))
        mock_slack.assert_not_called()


# ── Empty DataFrame ───────────────────────────────────────────────────────────


def test_empty_dataframe_handled_gracefully():
    """check_laps and check_pit_stops must not crash on an empty DataFrame."""
    empty = pd.DataFrame()
    assert check_laps(empty) == []
    assert check_pit_stops(empty) == []
