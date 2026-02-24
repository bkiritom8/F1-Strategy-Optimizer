"""
test_ingestion.py — Unit tests for src/ingestion/ergast_ingestion.py

Tests:
  - Successful fetch returns correct data structure
  - Rate limit (HTTP 429) triggers retry with backoff
  - Network error raises appropriate exception
  - Data saved to correct output path
  - Missing endpoint raises HTTPError
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

# Ensure repo root is on sys.path
_REPO_ROOT = Path(__file__).parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.ingestion.ergast_ingestion import (  # noqa: E402
    ErgastIngestion,
    _fetch_json,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ingestion(tmp_path: Path) -> ErgastIngestion:
    """Return an ErgastIngestion instance that writes to a temp directory."""
    return ErgastIngestion(output_dir=str(tmp_path / "jolpica"))


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    """Build a mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    if status_code >= 400:
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    else:
        resp.raise_for_status.return_value = None
    return resp


def _jolpica_seasons_payload() -> dict:
    return {
        "MRData": {
            "total": "2",
            "SeasonTable": {
                "Seasons": [
                    {"season": "2023", "url": "https://example.com/2023"},
                    {"season": "2024", "url": "https://example.com/2024"},
                ]
            },
        }
    }


def _jolpica_results_payload() -> dict:
    return {
        "MRData": {
            "total": "1",
            "RaceTable": {
                "Races": [
                    {
                        "season": "2024",
                        "round": "1",
                        "raceName": "Bahrain Grand Prix",
                        "Results": [
                            {"Driver": {"driverId": "max_verstappen"}, "position": "1"},
                        ],
                    }
                ]
            },
        }
    }


# ---------------------------------------------------------------------------
# Tests — _fetch_json
# ---------------------------------------------------------------------------


class TestFetchJson:
    def test_successful_fetch_returns_dict(self) -> None:
        payload = {"MRData": {"total": "1"}}
        mock_resp = _mock_response(payload)
        with patch(
            "src.ingestion.ergast_ingestion._rate_limited_get", return_value=mock_resp
        ):
            result = _fetch_json("https://api.jolpi.ca/ergast/f1/seasons/")
        assert result == payload

    def test_network_error_raises_connection_error(self) -> None:
        with patch(
            "src.ingestion.ergast_ingestion._rate_limited_get",
            side_effect=requests.ConnectionError("network unreachable"),
        ):
            with pytest.raises(requests.ConnectionError):
                _fetch_json("https://api.jolpi.ca/ergast/f1/seasons/")

    def test_timeout_raises_timeout_error(self) -> None:
        with patch(
            "src.ingestion.ergast_ingestion._rate_limited_get",
            side_effect=requests.Timeout("timed out"),
        ):
            with pytest.raises(requests.Timeout):
                _fetch_json("https://api.jolpi.ca/ergast/f1/seasons/")

    def test_404_raises_http_error(self) -> None:
        # Patch requests.get directly so _rate_limited_get runs and calls raise_for_status()
        mock_resp = _mock_response({}, status_code=404)
        with patch("requests.get", return_value=mock_resp):
            with pytest.raises(requests.HTTPError):
                _fetch_json("https://api.jolpi.ca/ergast/f1/9999/99/results/")

    def test_retries_on_429(self) -> None:
        """HTTP 429 triggers the 60s-sleep-and-retry path; second call succeeds."""
        rate_limit_resp = _mock_response({}, status_code=429)
        success_resp = _mock_response({"MRData": {"total": "0", "SeasonTable": {}}})
        with (
            patch(
                "src.ingestion.ergast_ingestion._rate_limited_get",
                side_effect=[rate_limit_resp, success_resp],
            ) as mock_get,
            patch("src.ingestion.ergast_ingestion.time.sleep") as mock_sleep,
        ):
            result = _fetch_json("https://api.jolpi.ca/ergast/f1/seasons/")
        # _rate_limited_get called twice: once for 429, once for the retry
        assert mock_get.call_count == 2
        # sleep was called with 60 seconds
        mock_sleep.assert_called_once_with(60)
        assert result == {"MRData": {"total": "0", "SeasonTable": {}}}


# ---------------------------------------------------------------------------
# Tests — ErgastIngestion.fetch_seasons
# ---------------------------------------------------------------------------


class TestFetchSeasons:
    def test_fetch_seasons_returns_list(self, ingestion: ErgastIngestion) -> None:
        payload = _jolpica_seasons_payload()
        mock_resp = _mock_response(payload)
        with patch(
            "src.ingestion.ergast_ingestion._rate_limited_get", return_value=mock_resp
        ):
            seasons = ingestion.fetch_seasons()
        assert isinstance(seasons, list)
        assert len(seasons) == 2
        assert seasons[0]["season"] == "2023"

    def test_fetch_seasons_saves_json(self, ingestion: ErgastIngestion) -> None:
        payload = _jolpica_seasons_payload()
        mock_resp = _mock_response(payload)
        with patch(
            "src.ingestion.ergast_ingestion._rate_limited_get", return_value=mock_resp
        ):
            ingestion.fetch_seasons()
        out = Path(ingestion.output_dir) / "seasons.json"
        assert out.exists(), f"Expected {out} to exist"
        with open(out) as f:
            saved = json.load(f)
        assert len(saved) == 2

    def test_fetch_seasons_correct_output_path(
        self, ingestion: ErgastIngestion
    ) -> None:
        payload = _jolpica_seasons_payload()
        mock_resp = _mock_response(payload)
        with patch(
            "src.ingestion.ergast_ingestion._rate_limited_get", return_value=mock_resp
        ):
            ingestion.fetch_seasons()
        assert (Path(ingestion.output_dir) / "seasons.json").exists()


# ---------------------------------------------------------------------------
# Tests — ErgastIngestion.fetch_race_results
# ---------------------------------------------------------------------------


class TestFetchRaceResults:
    def test_returns_race_dict(self, ingestion: ErgastIngestion) -> None:
        payload = _jolpica_results_payload()
        mock_resp = _mock_response(payload)
        with patch(
            "src.ingestion.ergast_ingestion._rate_limited_get", return_value=mock_resp
        ):
            result = ingestion.fetch_race_results(2024, 1)
        assert isinstance(result, dict)
        assert result.get("raceName") == "Bahrain Grand Prix"

    def test_saves_to_correct_path(self, ingestion: ErgastIngestion) -> None:
        payload = _jolpica_results_payload()
        mock_resp = _mock_response(payload)
        with patch(
            "src.ingestion.ergast_ingestion._rate_limited_get", return_value=mock_resp
        ):
            ingestion.fetch_race_results(2024, 1)
        expected = Path(ingestion.output_dir) / "results" / "2024" / "1.json"
        assert expected.exists()

    def test_empty_race_list_returns_empty_dict(
        self, ingestion: ErgastIngestion
    ) -> None:
        payload = {"MRData": {"total": "0", "RaceTable": {"Races": []}}}
        mock_resp = _mock_response(payload)
        with patch(
            "src.ingestion.ergast_ingestion._rate_limited_get", return_value=mock_resp
        ):
            result = ingestion.fetch_race_results(2024, 99)
        assert result == {}

    def test_network_error_propagates(self, ingestion: ErgastIngestion) -> None:
        with patch(
            "src.ingestion.ergast_ingestion._rate_limited_get",
            side_effect=requests.ConnectionError("unreachable"),
        ):
            with pytest.raises(requests.ConnectionError):
                ingestion.fetch_race_results(2024, 1)


# ---------------------------------------------------------------------------
# Tests — ErgastIngestion.fetch_drivers
# ---------------------------------------------------------------------------


class TestFetchDrivers:
    def test_fetch_all_drivers_path(self, ingestion: ErgastIngestion) -> None:
        payload = {
            "MRData": {
                "total": "1",
                "DriverTable": {
                    "Drivers": [{"driverId": "max_verstappen", "givenName": "Max"}]
                },
            }
        }
        mock_resp = _mock_response(payload)
        with patch(
            "src.ingestion.ergast_ingestion._rate_limited_get", return_value=mock_resp
        ):
            drivers = ingestion.fetch_drivers()
        assert isinstance(drivers, list)
        out = Path(ingestion.output_dir) / "drivers" / "all.json"
        assert out.exists()

    def test_fetch_season_drivers_path(self, ingestion: ErgastIngestion) -> None:
        payload = {
            "MRData": {
                "total": "1",
                "DriverTable": {"Drivers": [{"driverId": "hamilton"}]},
            }
        }
        mock_resp = _mock_response(payload)
        with patch(
            "src.ingestion.ergast_ingestion._rate_limited_get", return_value=mock_resp
        ):
            ingestion.fetch_drivers(year=2024)
        out = Path(ingestion.output_dir) / "drivers" / "2024.json"
        assert out.exists()
