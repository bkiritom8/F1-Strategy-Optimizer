"""
test_fastf1_ingestion.py — Unit tests for src/ingestion/fastf1_ingestion.py

FastF1 is mocked via sys.modules so tests run without network access or the
fastf1 package installed. All file I/O uses pytest tmp_path fixtures.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ── Mock fastf1 BEFORE importing the module under test ────────────────────────
# Injecting a MagicMock ensures the module-level `import fastf1` succeeds and
# _FASTF1_AVAILABLE is set to True regardless of the host environment.
_mock_fastf1 = MagicMock()
sys.modules["fastf1"] = _mock_fastf1

_REPO_ROOT = Path(__file__).parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.ingestion.fastf1_ingestion import FastF1Ingestion  # noqa: E402


# ── Shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def mock_session():
    """Minimal mock FastF1 session with realistic attributes."""
    sess = MagicMock()
    sess.event = {"EventName": "Test Grand Prix"}
    # fetch_laps: session.laps.copy() → real DataFrame
    sess.laps.copy.return_value = pd.DataFrame(
        {"Driver": ["VER", "HAM"], "LapNumber": [1, 2], "LapTime": [90.0, 91.0]}
    )
    # fetch_telemetry: session.laps.iterlaps() → empty by default
    sess.laps.iterlaps.return_value = iter([])
    # fetch_weather: session.weather_data.copy() → real DataFrame
    sess.weather_data.copy.return_value = pd.DataFrame(
        {"AirTemp": [25.0], "Humidity": [50.0]}
    )
    return sess


@pytest.fixture(autouse=True)
def reset_mock_fastf1():
    """Reset the shared fastf1 mock between tests to avoid state leakage."""
    _mock_fastf1.reset_mock()
    yield


# ── fetch_session ─────────────────────────────────────────────────────────────


def test_fetch_session_returns_session_object(tmp_path, mock_session):
    """fetch_session must return the session object supplied by fastf1.get_session."""
    _mock_fastf1.get_session.return_value = mock_session
    with patch("src.ingestion.fastf1_ingestion.fastf1", _mock_fastf1):
        ing = FastF1Ingestion(str(tmp_path / "out"), str(tmp_path / "cache"))
        result = ing.fetch_session(2024, 1, "R")
    assert result is mock_session


def test_fetch_session_loads_data(tmp_path, mock_session):
    """fetch_session must call session.load() with telemetry, laps, and weather."""
    _mock_fastf1.get_session.return_value = mock_session
    with patch("src.ingestion.fastf1_ingestion.fastf1", _mock_fastf1):
        ing = FastF1Ingestion(str(tmp_path / "out"), str(tmp_path / "cache"))
        ing.fetch_session(2024, 1, "R")
    mock_session.load.assert_called_once_with(telemetry=True, laps=True, weather=True)


# ── fetch_laps ────────────────────────────────────────────────────────────────


def test_fetch_laps_returns_dataframe(tmp_path, mock_session):
    """fetch_laps must return a DataFrame containing the session laps."""
    with patch("src.ingestion.fastf1_ingestion.fastf1", _mock_fastf1):
        ing = FastF1Ingestion(str(tmp_path / "out"), str(tmp_path / "cache"))
        result = ing.fetch_laps(2024, 1, "R", session=mock_session)
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 2  # VER + HAM


def test_fetch_laps_saves_csv(tmp_path, mock_session):
    """fetch_laps must persist laps as CSV at the expected path."""
    with patch("src.ingestion.fastf1_ingestion.fastf1", _mock_fastf1):
        ing = FastF1Ingestion(str(tmp_path / "out"), str(tmp_path / "cache"))
        ing.fetch_laps(2024, 1, "R", session=mock_session)
    csv_path = tmp_path / "out" / "2024" / "1" / "R" / "laps.csv"
    assert csv_path.exists()


# ── fetch_telemetry ───────────────────────────────────────────────────────────


def test_fetch_telemetry_returns_dataframe(tmp_path, mock_session):
    """fetch_telemetry must return a DataFrame when telemetry is available."""
    tel_df = pd.DataFrame({"Time": [0.1, 0.2], "Speed": [200.0, 210.0]})
    mock_lap = MagicMock()
    mock_lap.get_telemetry.return_value = tel_df.copy()
    mock_lap.__getitem__.side_effect = lambda k: {"Driver": "VER", "LapNumber": 1}[k]
    mock_session.laps.iterlaps.return_value = iter([(0, mock_lap)])

    with patch("src.ingestion.fastf1_ingestion.fastf1", _mock_fastf1):
        ing = FastF1Ingestion(str(tmp_path / "out"), str(tmp_path / "cache"))
        result = ing.fetch_telemetry(2024, 1, "R", session=mock_session)
    assert isinstance(result, pd.DataFrame)
    assert len(result) > 0


# ── Rate-limiting / sequential processing ─────────────────────────────────────


def test_rate_limit_respected(tmp_path, mock_session):
    """ingest_season must process all rounds sequentially (one session per round)."""
    _mock_fastf1.get_session.return_value = mock_session
    with patch("src.ingestion.fastf1_ingestion.fastf1", _mock_fastf1):
        ing = FastF1Ingestion(str(tmp_path / "out"), str(tmp_path / "cache"))
        ing.ingest_season(2024, session_types=["R"], max_rounds=3)
    # One get_session call per round (3 rounds × 1 session type = 3 calls)
    assert _mock_fastf1.get_session.call_count == 3


# ── Cache directory ───────────────────────────────────────────────────────────


def test_cache_dir_created(tmp_path):
    """FastF1Ingestion must create the cache directory on initialisation."""
    cache_dir = tmp_path / "my_cache"
    assert not cache_dir.exists()
    with patch("src.ingestion.fastf1_ingestion.fastf1", _mock_fastf1):
        FastF1Ingestion(str(tmp_path / "out"), str(cache_dir))
    assert cache_dir.exists()


# ── Invalid inputs ────────────────────────────────────────────────────────────


def test_invalid_session_type_raises(tmp_path):
    """fetch_session raises ValueError for years before 2018 (FastF1 coverage start)."""
    with patch("src.ingestion.fastf1_ingestion.fastf1", _mock_fastf1):
        ing = FastF1Ingestion(str(tmp_path / "out"), str(tmp_path / "cache"))
        with pytest.raises(ValueError, match="2018"):
            ing.fetch_session(2015, 1, "R")


# ── Empty laps ────────────────────────────────────────────────────────────────


def test_empty_laps_handled(tmp_path, mock_session):
    """fetch_laps must return an empty DataFrame without crashing when laps are absent."""
    mock_session.laps.copy.return_value = pd.DataFrame(
        columns=["Driver", "LapNumber", "LapTime"]
    )
    with patch("src.ingestion.fastf1_ingestion.fastf1", _mock_fastf1):
        ing = FastF1Ingestion(str(tmp_path / "out"), str(tmp_path / "cache"))
        result = ing.fetch_laps(2024, 1, "R", session=mock_session)
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0
