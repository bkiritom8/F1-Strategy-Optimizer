import json
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from src.simulation.streamer import build_sse_line, frames_to_sse


def test_build_sse_line_lap_event():
    frame = {"type": "lap", "lap": 1, "cars": []}
    line = build_sse_line("sim_lap", frame)
    assert line.startswith("data: ")
    assert '"event": "sim_lap"' in line
    assert '"lap": 1' in line
    assert line.endswith("\n\n")


def test_build_sse_line_complete_event():
    frame = {"type": "complete", "p50_finish": 2}
    line = build_sse_line("sim_complete", frame)
    assert '"event": "sim_complete"' in line
    assert '"p50_finish": 2' in line


def test_build_sse_line_encodes_valid_json():
    frame = {"type": "lap", "lap": 5, "cars": [{"id": "norris", "track_pct": 0.5}]}
    line = build_sse_line("sim_lap", frame)
    payload = json.loads(line.replace("data: ", "").strip())
    assert payload["event"] == "sim_lap"
    assert payload["lap"] == 5
