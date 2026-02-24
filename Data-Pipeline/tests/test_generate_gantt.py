"""
test_generate_gantt.py — Unit tests for Data-Pipeline/scripts/generate_gantt.py

Tests cover: PNG chart generation (with mocked matplotlib), ASCII fallback,
pipeline_runs.json loading, hardcoded-estimate fallback, and task presence.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch


# ── Import module under test via file path (hyphen in directory) ───────────────
_REPO_ROOT = Path(__file__).parents[2]
_SCRIPTS_DIR = _REPO_ROOT / "Data-Pipeline" / "scripts"

_spec = importlib.util.spec_from_file_location(
    "generate_gantt", _SCRIPTS_DIR / "generate_gantt.py"
)
_gg = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["generate_gantt"] = _gg
_spec.loader.exec_module(_gg)  # type: ignore[union-attr]

print_ascii_gantt = _gg.print_ascii_gantt
generate_png_gantt = _gg.generate_png_gantt
_resolve_tasks = _gg._resolve_tasks
_DEFAULT_TASKS = _gg._DEFAULT_TASKS


# ── PNG chart ─────────────────────────────────────────────────────────────────


def test_gantt_chart_saved(tmp_path):
    """generate_png_gantt creates a non-empty PNG file at the specified output path."""
    output_path = tmp_path / "gantt_chart.png"
    # Use real matplotlib (installed) — verify file creation and return value
    result = generate_png_gantt(list(_DEFAULT_TASKS), output_path, from_file=False)
    assert result is True
    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_ascii_gantt_printed_when_matplotlib_unavailable(capsys):
    """print_ascii_gantt must produce output; generate_png_gantt returns False when matplotlib missing."""
    # ASCII chart is always available
    print_ascii_gantt(list(_DEFAULT_TASKS), from_file=False)
    captured = capsys.readouterr()
    assert "F1 Data Pipeline" in captured.out

    # PNG returns False when matplotlib is absent (None in sys.modules triggers ImportError)
    with patch.dict(
        sys.modules,
        {
            "matplotlib": None,
            "matplotlib.patches": None,
            "matplotlib.pyplot": None,
            "matplotlib.ticker": None,
        },
    ):
        result = generate_png_gantt(
            list(_DEFAULT_TASKS), Path("/tmp/x.png"), from_file=False
        )
    assert result is False


# ── Task presence ─────────────────────────────────────────────────────────────


def test_all_tasks_present_in_chart(capsys):
    """ASCII Gantt output must include all 7 pipeline task IDs."""
    expected_tasks = [
        "fetch_jolpica_data",
        "fetch_fastf1_data",
        "validate_raw_data",
        "preprocess_data",
        "detect_anomalies",
        "build_features",
        "bias_analysis",
    ]
    print_ascii_gantt(list(_DEFAULT_TASKS), from_file=False)
    captured = capsys.readouterr()
    for task in expected_tasks:
        assert task in captured.out, f"Task '{task}' missing from ASCII Gantt output"


# ── Bottleneck ────────────────────────────────────────────────────────────────


def test_bottleneck_highlighted(capsys):
    """fetch_fastf1_data must be marked as bottleneck in ASCII Gantt output."""
    print_ascii_gantt(list(_DEFAULT_TASKS), from_file=False)
    captured = capsys.readouterr()
    assert "bottleneck" in captured.out
    # The bottleneck annotation must appear on the fetch_fastf1_data line
    lines = captured.out.splitlines()
    fastf1_line = next((ln for ln in lines if "fetch_fastf1_data" in ln), None)
    assert fastf1_line is not None
    assert "bottleneck" in fastf1_line


# ── pipeline_runs.json loading ────────────────────────────────────────────────


def test_uses_pipeline_runs_json_if_exists(tmp_path):
    """_resolve_tasks must load timings from pipeline_runs.json when it exists."""
    run_data = {
        "run_id": "test_run",
        "tasks": [
            {
                "task_id": "fetch_jolpica_data",
                "start_offset_min": 0.0,
                "duration_min": 3.0,
                "state": "success",
            },
            {
                "task_id": "fetch_fastf1_data",
                "start_offset_min": 0.0,
                "duration_min": 25.0,
                "state": "success",
                "bottleneck": True,
            },
        ],
    }
    json_path = tmp_path / "pipeline_runs.json"
    json_path.write_text(json.dumps(run_data))

    tasks, from_file = _resolve_tasks(json_path)
    assert from_file is True
    assert len(tasks) == 2
    task_ids = [t["task_id"] for t in tasks]
    assert "fetch_jolpica_data" in task_ids
    assert "fetch_fastf1_data" in task_ids


def test_falls_back_to_estimates_if_no_json(tmp_path):
    """_resolve_tasks must return hardcoded estimates when no JSON file is present."""
    missing_path = tmp_path / "nonexistent.json"
    tasks, from_file = _resolve_tasks(missing_path)
    assert from_file is False
    # Default tasks include exactly the 7 pipeline stages
    assert len(tasks) == len(_DEFAULT_TASKS)
    default_ids = {t["task_id"] for t in _DEFAULT_TASKS}
    loaded_ids = {t["task_id"] for t in tasks}
    assert loaded_ids == default_ids
