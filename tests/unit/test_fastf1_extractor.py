"""Tests for src/ingestion/fastf1_extractor.py"""
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.ingestion.fastf1_extractor import (
    _FASTF1_AVAILABLE,
    SESSION_LABELS,
    enable_cache,
    extract_laps,
    extract_telemetry,
    extract_weather,
    normalize_timedeltas,
)


class TestFastF1Available:
    def test_flag_is_bool(self):
        assert isinstance(_FASTF1_AVAILABLE, bool)


class TestSessionLabels:
    def test_known_labels(self):
        assert SESSION_LABELS["R"] == "Race"
        assert SESSION_LABELS["Q"] == "Qualifying"
        assert SESSION_LABELS["FP1"] == "Practice 1"
        assert SESSION_LABELS["S"] == "Sprint"


class TestEnableCache:
    def test_no_op_when_fastf1_unavailable(self, tmp_path):
        with patch("src.ingestion.fastf1_extractor._FASTF1_AVAILABLE", False):
            enable_cache(str(tmp_path / "cache"))
            # should not raise, dir may or may not be created

    def test_creates_dir_and_calls_cache_when_available(self, tmp_path):
        cache_dir = tmp_path / "cache"
        mock_fastf1 = MagicMock()
        with patch("src.ingestion.fastf1_extractor._FASTF1_AVAILABLE", True), \
             patch("src.ingestion.fastf1_extractor.fastf1", mock_fastf1):
            enable_cache(str(cache_dir))
            assert cache_dir.exists()
            mock_fastf1.Cache.enable_cache.assert_called_once_with(str(cache_dir))


class TestNormalizeTimedeltas:
    def test_converts_timedelta_to_seconds(self):
        df = pd.DataFrame({
            "time": pd.to_timedelta(["00:01:30", "00:02:00"]),
            "value": [1, 2],
        })
        result = normalize_timedeltas(df)
        assert result["time"].iloc[0] == pytest.approx(90.0)
        assert result["time"].iloc[1] == pytest.approx(120.0)

    def test_leaves_non_timedelta_columns_unchanged(self):
        df = pd.DataFrame({"speed": [100, 200], "name": ["a", "b"]})
        result = normalize_timedeltas(df)
        assert result["speed"].tolist() == [100, 200]

    def test_empty_dataframe_unchanged(self):
        df = pd.DataFrame()
        result = normalize_timedeltas(df)
        assert result.empty


class TestExtractLaps:
    def _mock_session(self):
        session = MagicMock()
        session.laps = pd.DataFrame({
            "Driver": ["VER", "HAM"],
            "LapNumber": [1, 1],
            "LapTime": pd.to_timedelta(["00:01:30", "00:01:31"]),
        })
        return session

    def test_adds_metadata_columns(self):
        session = self._mock_session()
        result = extract_laps(session, 2024, 1, "R")
        assert "season" in result.columns
        assert "round" in result.columns
        assert "session_type" in result.columns

    def test_metadata_values_correct(self):
        session = self._mock_session()
        result = extract_laps(session, 2024, 3, "Q")
        assert (result["season"] == 2024).all()
        assert (result["round"] == 3).all()
        assert (result["session_type"] == "Q").all()

    def test_timedeltas_converted(self):
        session = self._mock_session()
        result = extract_laps(session, 2024, 1, "R")
        assert result["LapTime"].dtype != "timedelta64[ns]"


class TestExtractTelemetry:
    def _mock_session_with_telemetry(self):
        tel = pd.DataFrame({"Speed": [300, 280], "RPM": [11000, 10500]})
        lap = pd.Series({"Driver": "VER", "LapNumber": 5})
        lap.get_telemetry = MagicMock(return_value=tel)

        mock_laps = MagicMock()
        mock_laps.iterlaps = MagicMock(return_value=iter([(0, lap)]))

        session = MagicMock()
        session.laps = mock_laps
        return session

    def test_returns_dataframe(self):
        session = self._mock_session_with_telemetry()
        result = extract_telemetry(session, 2024, 1, "R")
        assert isinstance(result, pd.DataFrame)

    def test_returns_empty_df_when_no_telemetry(self):
        lap = pd.Series({"Driver": "VER", "LapNumber": 5})
        lap.get_telemetry = MagicMock(return_value=None)
        mock_laps = MagicMock()
        mock_laps.iterlaps = MagicMock(return_value=iter([(0, lap)]))
        session = MagicMock()
        session.laps = mock_laps
        result = extract_telemetry(session, 2024, 1, "R")
        assert result.empty

    def test_driver_filter_calls_pick_driver(self):
        session = MagicMock()
        filtered_laps = MagicMock()
        filtered_laps.iterlaps = MagicMock(return_value=iter([]))
        session.laps.pick_driver = MagicMock(return_value=filtered_laps)
        extract_telemetry(session, 2024, 1, "R", driver="VER")
        session.laps.pick_driver.assert_called_once_with("VER")


class TestExtractWeather:
    def test_adds_metadata_columns(self):
        session = MagicMock()
        session.weather_data = pd.DataFrame({
            "AirTemp": [25.0, 26.0],
            "TrackTemp": [40.0, 41.0],
        })
        result = extract_weather(session, 2024, 1, "R")
        assert "season" in result.columns
        assert "round" in result.columns
        assert "session_type" in result.columns

    def test_metadata_values_correct(self):
        session = MagicMock()
        session.weather_data = pd.DataFrame({"AirTemp": [25.0]})
        result = extract_weather(session, 2023, 5, "FP2")
        assert result["season"].iloc[0] == 2023
        assert result["round"].iloc[0] == 5
        assert result["session_type"].iloc[0] == "FP2"
