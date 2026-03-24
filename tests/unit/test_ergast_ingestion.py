"""Tests for src/ingestion/ergast_ingestion.py"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.ingestion.ergast_ingestion import ErgastIngestion


@pytest.fixture
def ingestion(tmp_path):
    return ErgastIngestion(output_dir=str(tmp_path))


class TestErgastIngestionInit:
    def test_creates_output_dir(self, tmp_path):
        out = tmp_path / "jolpica"
        ErgastIngestion(output_dir=str(out))
        assert out.exists()

    def test_default_output_dir_set(self, tmp_path):
        ing = ErgastIngestion(output_dir=str(tmp_path))
        assert ing.output_dir == tmp_path


class TestFetchSeasons:
    def test_returns_list_and_saves_json(self, ingestion, tmp_path):
        seasons = [{"season": "2024"}, {"season": "2023"}]
        with patch("src.ingestion.ergast_ingestion._paginate", return_value=seasons):
            result = ingestion.fetch_seasons()
            assert result == seasons
            saved = json.loads((tmp_path / "seasons.json").read_text())
            assert saved == seasons

    def test_empty_seasons(self, ingestion, tmp_path):
        with patch("src.ingestion.ergast_ingestion._paginate", return_value=[]):
            result = ingestion.fetch_seasons()
            assert result == []


class TestFetchCircuits:
    def test_returns_list_and_saves_json(self, ingestion, tmp_path):
        circuits = [{"circuitId": "bahrain"}]
        with patch("src.ingestion.ergast_ingestion._paginate", return_value=circuits):
            result = ingestion.fetch_circuits()
            assert result == circuits
            saved = json.loads((tmp_path / "circuits.json").read_text())
            assert saved == circuits


class TestFetchDrivers:
    def test_all_drivers(self, ingestion, tmp_path):
        drivers = [{"driverId": "hamilton"}]
        with patch("src.ingestion.ergast_ingestion._paginate", return_value=drivers):
            result = ingestion.fetch_drivers()
            assert result == drivers
            assert (tmp_path / "drivers" / "all.json").exists()

    def test_year_specific_drivers(self, ingestion, tmp_path):
        drivers = [{"driverId": "verstappen"}]
        with patch("src.ingestion.ergast_ingestion._paginate", return_value=drivers):
            result = ingestion.fetch_drivers(year=2024)
            assert result == drivers
            assert (tmp_path / "drivers" / "2024.json").exists()


class TestFetchRaceResults:
    def test_returns_first_race(self, ingestion, tmp_path):
        api_resp = {
            "MRData": {
                "RaceTable": {
                    "Races": [{"raceName": "Bahrain GP", "Results": [{"position": "1"}]}]
                }
            }
        }
        with patch("src.ingestion.ergast_ingestion._fetch_json", return_value=api_resp):
            result = ingestion.fetch_race_results(2024, 1)
            assert result["raceName"] == "Bahrain GP"
            assert (tmp_path / "results" / "2024" / "1.json").exists()

    def test_empty_races_returns_empty_dict(self, ingestion):
        api_resp = {"MRData": {"RaceTable": {"Races": []}}}
        with patch("src.ingestion.ergast_ingestion._fetch_json", return_value=api_resp):
            result = ingestion.fetch_race_results(2024, 99)
            assert result == {}


class TestFetchLapTimes:
    def test_returns_list_and_saves(self, ingestion, tmp_path):
        laps = [{"number": "1", "Timings": []}]
        with patch("src.ingestion.ergast_ingestion._paginate", return_value=laps):
            result = ingestion.fetch_lap_times(2024, 1)
            assert result == laps
            assert (tmp_path / "laps" / "2024" / "1.json").exists()


class TestFetchPitStops:
    def test_returns_list_and_saves(self, ingestion, tmp_path):
        pits = [{"driverId": "hamilton", "lap": "20"}]
        with patch("src.ingestion.ergast_ingestion._paginate", return_value=pits):
            result = ingestion.fetch_pit_stops(2024, 1)
            assert result == pits
            assert (tmp_path / "pit_stops" / "2024" / "1.json").exists()


class TestFetchQualifying:
    def test_returns_first_race(self, ingestion, tmp_path):
        api_resp = {
            "MRData": {
                "RaceTable": {"Races": [{"raceName": "Bahrain Q", "QualifyingResults": []}]}
            }
        }
        with patch("src.ingestion.ergast_ingestion._fetch_json", return_value=api_resp):
            result = ingestion.fetch_qualifying(2024, 1)
            assert result["raceName"] == "Bahrain Q"
            assert (tmp_path / "qualifying" / "2024" / "1.json").exists()


class TestIngestSeason:
    def test_returns_counts_dict(self, ingestion):
        with patch.object(ingestion, "fetch_race_results", return_value={"Results": [1, 2]}), \
             patch.object(ingestion, "fetch_lap_times", return_value=[1, 2, 3]), \
             patch.object(ingestion, "fetch_pit_stops", return_value=[1]):
            counts = ingestion.ingest_season(2024, max_rounds=1)
            assert "results" in counts
            assert "laps" in counts
            assert "pit_stops" in counts

    def test_stops_on_404(self, ingestion):
        http_err = requests.HTTPError("404")
        http_err.response = MagicMock()
        http_err.response.status_code = 404
        with patch.object(ingestion, "fetch_race_results", side_effect=http_err), \
             patch.object(ingestion, "fetch_lap_times", return_value=[]), \
             patch.object(ingestion, "fetch_pit_stops", return_value=[]):
            counts = ingestion.ingest_season(2024, max_rounds=5)
            assert counts["results"] == 0

    def test_continues_on_exception(self, ingestion):
        results = [Exception("network"), {"Results": [1]}]
        with patch.object(ingestion, "fetch_race_results", side_effect=results), \
             patch.object(ingestion, "fetch_lap_times", return_value=[]), \
             patch.object(ingestion, "fetch_pit_stops", return_value=[]):
            counts = ingestion.ingest_season(2024, max_rounds=2)
            assert counts["results"] == 1
