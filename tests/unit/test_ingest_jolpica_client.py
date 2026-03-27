"""
Unit tests for ingest/jolpica_client.py — Jolpica/Ergast API helpers.

All HTTP I/O is mocked via the rate_limited_get / backoff_wait / is_rate_limit
layer so no network calls are made.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def _resp(status_code: int, json_data=None):
    r = MagicMock()
    r.status_code = status_code
    r.json.return_value = json_data or {}
    r.raise_for_status.return_value = None
    return r


class TestFetchJson:
    def test_returns_none_on_404(self):
        from ingest.jolpica_client import fetch_json

        with patch("ingest.jolpica_client.rate_limited_get", return_value=_resp(404)):
            result = fetch_json("http://example.com/data")

        assert result is None

    def test_returns_json_on_200(self):
        from ingest.jolpica_client import fetch_json

        payload = {"MRData": {"total": "0"}}
        with patch(
            "ingest.jolpica_client.rate_limited_get", return_value=_resp(200, payload)
        ):
            result = fetch_json("http://example.com/data")

        assert result == payload

    def test_retries_once_on_429_then_succeeds(self):
        from ingest.jolpica_client import fetch_json

        payload = {"MRData": {}}
        responses = [_resp(429), _resp(200, payload)]

        with patch(
            "ingest.jolpica_client.rate_limited_get", side_effect=responses
        ), patch("ingest.jolpica_client.backoff_wait") as mock_wait:
            result = fetch_json("http://example.com/data")

        assert result == payload
        mock_wait.assert_called_once_with(0)

    def test_retries_on_generic_exception_then_succeeds(self):
        from ingest.jolpica_client import fetch_json

        payload = {"MRData": {}}
        with patch(
            "ingest.jolpica_client.rate_limited_get",
            side_effect=[ConnectionError("timeout"), _resp(200, payload)],
        ), patch("ingest.jolpica_client.backoff_wait"), patch(
            "ingest.jolpica_client.is_rate_limit", return_value=False
        ):
            result = fetch_json("http://example.com/data")

        assert result == payload

    def test_calls_raise_for_status_on_non_special_codes(self):
        from ingest.jolpica_client import fetch_json

        resp = _resp(500)
        resp.raise_for_status.side_effect = Exception("server error")

        with patch(
            "ingest.jolpica_client.rate_limited_get",
            side_effect=[resp, _resp(200, {})],
        ), patch("ingest.jolpica_client.backoff_wait"), patch(
            "ingest.jolpica_client.is_rate_limit", return_value=False
        ):
            fetch_json("http://example.com/data")

        resp.raise_for_status.assert_called_once()


class TestPaginate:
    def _race_page(self, races, total, limit=100):
        return {
            "MRData": {
                "total": str(total),
                "limit": str(limit),
                "RaceTable": {"Races": races},
            }
        }

    def test_returns_empty_list_when_fetch_returns_none(self):
        from ingest.jolpica_client import paginate

        with patch("ingest.jolpica_client.fetch_json", return_value=None):
            result = paginate("http://example.com/races")

        assert result == []

    def test_returns_all_records_in_single_page(self):
        from ingest.jolpica_client import paginate

        races = [{"raceName": "Bahrain"}, {"raceName": "Saudi Arabia"}]
        page = self._race_page(races, total=2)

        with patch("ingest.jolpica_client.fetch_json", return_value=page):
            result = paginate("http://example.com/races")

        assert result == races

    def test_paginates_across_multiple_pages(self):
        from ingest.jolpica_client import paginate

        page1_races = [{"raceName": f"Race{i}"} for i in range(3)]
        page2_races = [{"raceName": "Race3"}]

        pages = [
            self._race_page(page1_races, total=4, limit=3),
            self._race_page(page2_races, total=4, limit=3),
        ]

        with patch("ingest.jolpica_client.fetch_json", side_effect=pages):
            result = paginate("http://example.com/races", limit=3)

        assert len(result) == 4
        assert result[0]["raceName"] == "Race0"
        assert result[3]["raceName"] == "Race3"

    def test_stops_when_no_rows_returned(self):
        from ingest.jolpica_client import paginate

        page1 = self._race_page([{"raceName": "Bahrain"}], total=100, limit=1)
        page2 = self._race_page([], total=100, limit=1)

        with patch("ingest.jolpica_client.fetch_json", side_effect=[page1, page2]):
            result = paginate("http://example.com/races", limit=1)

        assert result == [{"raceName": "Bahrain"}]

    def test_url_includes_limit_and_offset(self):
        from ingest.jolpica_client import paginate

        page = self._race_page([], total=0)
        with patch(
            "ingest.jolpica_client.fetch_json", return_value=page
        ) as mock_fetch:
            paginate("http://example.com/races", limit=50)

        mock_fetch.assert_called_once_with("http://example.com/races?limit=50&offset=0")

    def test_handles_standings_table(self):
        from ingest.jolpica_client import paginate

        standings = [{"position": "1", "Driver": {}}]
        page = {
            "MRData": {
                "total": "1",
                "limit": "100",
                "StandingsTable": {"StandingsLists": standings},
            }
        }

        with patch("ingest.jolpica_client.fetch_json", return_value=page):
            result = paginate("http://example.com/standings")

        assert result == standings
