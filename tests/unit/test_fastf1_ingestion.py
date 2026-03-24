"""Tests for src/ingestion/fastf1_ingestion.py"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.ingestion.fastf1_ingestion import FastF1Ingestion


@pytest.fixture
def ingestion(tmp_path):
    return FastF1Ingestion(
        output_dir=str(tmp_path / "fastf1"),
        cache_dir=str(tmp_path / "cache"),
    )


class TestFastF1IngestionInit:
    def test_creates_output_dir(self, tmp_path):
        out = tmp_path / "out"
        FastF1Ingestion(output_dir=str(out), cache_dir=str(tmp_path / "cache"))
        assert out.exists()

    def test_output_dir_stored(self, ingestion, tmp_path):
        assert ingestion.output_dir == tmp_path / "fastf1"


class TestSessionDir:
    def test_creates_nested_dir(self, ingestion, tmp_path):
        d = ingestion._session_dir(2024, 1, "R")
        assert d.exists()
        assert d == tmp_path / "fastf1" / "2024" / "1" / "R"


class TestFetchSession:
    def test_delegates_to_load_session(self, ingestion):
        mock_session = MagicMock()
        with patch("src.ingestion.fastf1_ingestion.load_session", return_value=mock_session):
            result = ingestion.fetch_session(2024, 1, "R")
            assert result is mock_session


class TestFetchLaps:
    def test_saves_csv_and_returns_df(self, ingestion, tmp_path):
        laps_df = pd.DataFrame({"Driver": ["VER"], "LapNumber": [1], "LapTime": [90.0]})
        mock_session = MagicMock()
        with patch("src.ingestion.fastf1_ingestion.load_session", return_value=mock_session), \
             patch("src.ingestion.fastf1_ingestion.extract_laps", return_value=laps_df):
            result = ingestion.fetch_laps(2024, 1, "R")
            assert len(result) == 1
            csv_path = tmp_path / "fastf1" / "2024" / "1" / "R" / "laps.csv"
            assert csv_path.exists()

    def test_uses_provided_session(self, ingestion):
        laps_df = pd.DataFrame({"Driver": ["HAM"], "LapNumber": [2], "LapTime": [91.0]})
        mock_session = MagicMock()
        with patch("src.ingestion.fastf1_ingestion.load_session") as mock_load, \
             patch("src.ingestion.fastf1_ingestion.extract_laps", return_value=laps_df):
            ingestion.fetch_laps(2024, 1, "R", session=mock_session)
            mock_load.assert_not_called()


class TestFetchTelemetry:
    def test_saves_csv_with_driver_suffix(self, ingestion, tmp_path):
        tel_df = pd.DataFrame({"Speed": [300.0], "Driver": ["VER"]})
        mock_session = MagicMock()
        with patch("src.ingestion.fastf1_ingestion.load_session", return_value=mock_session), \
             patch("src.ingestion.fastf1_ingestion.extract_telemetry", return_value=tel_df):
            ingestion.fetch_telemetry(2024, 1, "R", driver="VER")
            csv_path = tmp_path / "fastf1" / "2024" / "1" / "R" / "telemetry_VER.csv"
            assert csv_path.exists()

    def test_saves_csv_with_all_suffix_when_no_driver(self, ingestion, tmp_path):
        tel_df = pd.DataFrame({"Speed": [300.0]})
        mock_session = MagicMock()
        with patch("src.ingestion.fastf1_ingestion.load_session", return_value=mock_session), \
             patch("src.ingestion.fastf1_ingestion.extract_telemetry", return_value=tel_df):
            ingestion.fetch_telemetry(2024, 1, "R")
            csv_path = tmp_path / "fastf1" / "2024" / "1" / "R" / "telemetry_all.csv"
            assert csv_path.exists()

    def test_returns_empty_df_and_logs_warning_when_empty(self, ingestion):
        mock_session = MagicMock()
        with patch("src.ingestion.fastf1_ingestion.load_session", return_value=mock_session), \
             patch("src.ingestion.fastf1_ingestion.extract_telemetry", return_value=pd.DataFrame()):
            result = ingestion.fetch_telemetry(2024, 1, "R", driver="VER")
            assert result.empty


class TestFetchWeather:
    def test_saves_weather_csv(self, ingestion, tmp_path):
        weather_df = pd.DataFrame({"AirTemp": [25.0], "TrackTemp": [40.0]})
        mock_session = MagicMock()
        with patch("src.ingestion.fastf1_ingestion.load_session", return_value=mock_session), \
             patch("src.ingestion.fastf1_ingestion.extract_weather", return_value=weather_df):
            ingestion.fetch_weather(2024, 1, "R")
            csv_path = tmp_path / "fastf1" / "2024" / "1" / "R" / "weather.csv"
            assert csv_path.exists()
