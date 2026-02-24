"""
test_bias_analysis.py — Unit tests for Data-Pipeline/scripts/bias_analysis.py

Tests cover: era slicing, team-tier slicing, report persistence, ASCII table
output, representation percentages, and empty-DataFrame resilience.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd

# ── Import module under test via file path (hyphen in directory) ───────────────
_REPO_ROOT = Path(__file__).parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "Data-Pipeline" / "scripts"

_spec = importlib.util.spec_from_file_location(
    "bias_analysis", _SCRIPTS_DIR / "bias_analysis.py"
)
_ba = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["bias_analysis"] = _ba
_spec.loader.exec_module(_ba)  # type: ignore[union-attr]

slice_by_era = _ba.slice_by_era
slice_by_team = _ba.slice_by_team
_print_table = _ba._print_table
_compute_slice_stats = _ba._compute_slice_stats
run_bias_analysis = _ba.run_bias_analysis


# ── Era slicing ───────────────────────────────────────────────────────────────


def test_era_slicing_produces_three_eras():
    """slice_by_era must always return exactly three era slices."""
    df = pd.DataFrame({"season": [2005, 2012, 2020], "LapTime": [90.0, 85.0, 80.0]})
    slices = slice_by_era(df, "LapTime")
    assert len(slices) == 3


def test_pre_2010_era_correct_years():
    """Rows with season < 2010 must all land in the pre-2010 slice."""
    df = pd.DataFrame({"season": [2005, 2007, 2009, 2012, 2020], "LapTime": [90.0] * 5})
    slices = slice_by_era(df, "LapTime")
    pre2010 = next(s for s in slices if "pre-2010" in s["slice"])
    assert pre2010["count"] == 3  # 2005, 2007, 2009


def test_hybrid_era_correct_years():
    """Rows with season >= 2014 must all land in the 2014+ slice."""
    df = pd.DataFrame({"season": [2005, 2014, 2020, 2024], "LapTime": [90.0] * 4})
    slices = slice_by_era(df, "LapTime")
    hybrid = next(s for s in slices if "2014+" in s["slice"])
    assert hybrid["count"] == 3  # 2014, 2020, 2024


# ── Team-tier slicing ─────────────────────────────────────────────────────────


def test_team_tier_slicing_produces_three_tiers():
    """slice_by_team must return top, mid, and backmarker tiers."""
    df = pd.DataFrame(
        {
            "Constructor": ["mercedes", "force_india", "hrt"],
            "LapTime": [80.0, 85.0, 90.0],
        }
    )
    slices = slice_by_team(df, "LapTime")
    tier_labels = {s["slice"] for s in slices}
    assert "team:top" in tier_labels
    assert "team:mid" in tier_labels
    assert "team:backmarker" in tier_labels


# ── Report persistence ────────────────────────────────────────────────────────


def test_bias_report_saved_to_correct_path(tmp_path, monkeypatch):
    """run_bias_analysis must save bias_report.json to the logs directory."""
    monkeypatch.setattr(_ba, "_LOGS_DIR", tmp_path)
    data_dir = tmp_path / "processed"
    data_dir.mkdir()
    _make_laps_parquet(data_dir)

    result = run_bias_analysis(str(data_dir))
    assert result == 0
    assert (tmp_path / "bias_report.json").exists()


def test_bias_report_has_required_keys(tmp_path, monkeypatch):
    """Saved bias_report.json must contain timestamp and slices keys."""
    monkeypatch.setattr(_ba, "_LOGS_DIR", tmp_path)
    data_dir = tmp_path / "processed"
    data_dir.mkdir()
    _make_laps_parquet(data_dir)

    run_bias_analysis(str(data_dir))
    report = json.loads((tmp_path / "bias_report.json").read_text())
    assert "timestamp" in report
    assert "slices" in report
    assert "findings" in report  # code uses "findings", not "summary"


# ── ASCII table output ────────────────────────────────────────────────────────


def test_ascii_table_printed(capsys):
    """_print_table must print column headers to stdout."""
    rows = [
        _compute_slice_stats(
            pd.DataFrame({"LapTime": [90.0, 91.0]}),
            "pre-2010 (NA)",
            total_rows=5,
            lap_time_col="LapTime",
        )
    ]
    _print_table(rows, "[Era]")
    captured = capsys.readouterr()
    assert "Slice" in captured.out
    assert "Count" in captured.out
    assert "Representation%" in captured.out


# ── Empty DataFrame resilience ────────────────────────────────────────────────


def test_empty_dataframe_handled_gracefully(tmp_path, monkeypatch):
    """run_bias_analysis with an empty laps parquet must not crash and must save a report."""
    monkeypatch.setattr(_ba, "_LOGS_DIR", tmp_path)
    data_dir = tmp_path / "processed"
    data_dir.mkdir()
    # Empty DataFrame → parquet with no rows
    pd.DataFrame(columns=["season", "LapTime", "Constructor"]).to_parquet(
        data_dir / "laps_all.parquet", index=False
    )
    result = run_bias_analysis(str(data_dir))
    assert result == 0
    assert (tmp_path / "bias_report.json").exists()


# ── Representation percentages ────────────────────────────────────────────────


def test_representation_percentages_sum_to_100():
    """Era slice representation percentages must sum to approximately 100 %."""
    df = pd.DataFrame({"season": [2005, 2008, 2012, 2015, 2020], "LapTime": [90.0] * 5})
    slices = slice_by_era(df, "LapTime")
    total_pct = sum(s["representation_pct"] for s in slices)
    assert abs(total_pct - 100.0) < 1.0


# ── Count field in report ─────────────────────────────────────────────────────


def test_sample_size_in_report():
    """Every slice dict must expose a 'count' field."""
    df = pd.DataFrame({"season": [2005, 2012, 2020], "LapTime": [90.0] * 3})
    slices = slice_by_era(df, "LapTime")
    for s in slices:
        assert "count" in s


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_laps_parquet(data_dir: Path) -> None:
    """Write a minimal laps_all.parquet to data_dir for run_bias_analysis."""
    pd.DataFrame(
        {
            "season": [2005, 2015, 2020],
            "LapTime": [90.0, 85.0, 80.0],
            "Constructor": ["ferrari", "mercedes", "red_bull"],
        }
    ).to_parquet(data_dir / "laps_all.parquet", index=False)
