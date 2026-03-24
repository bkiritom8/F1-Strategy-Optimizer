"""Tests for src/ingestion/ergast_client.py"""
from unittest.mock import patch

import pytest

from src.ingestion.ergast_client import paginate


def _mr_data(rows, total, table_key="SeasonTable", row_key="Seasons", limit=1000):
    return {
        "MRData": {
            "total": str(total),
            "limit": str(limit),
            table_key: {row_key: rows},
        }
    }


class TestPaginate:
    def test_single_page_returns_all_rows(self):
        data = _mr_data([{"season": "2024"}, {"season": "2023"}], total=2)
        with patch("src.ingestion.ergast_client.fetch_json", return_value=data):
            result = paginate("http://example.com/seasons/")
            assert len(result) == 2
            assert result[0]["season"] == "2024"

    def test_multiple_pages_concatenated(self):
        page1 = _mr_data([{"season": "2024"}], total=2, limit=1)
        page2 = _mr_data([{"season": "2023"}], total=2, limit=1)
        with patch("src.ingestion.ergast_client.fetch_json", side_effect=[page1, page2]):
            result = paginate("http://example.com/seasons/", limit=1)
            assert len(result) == 2

    def test_empty_response_returns_empty_list(self):
        data = _mr_data([], total=0)
        with patch("src.ingestion.ergast_client.fetch_json", return_value=data):
            result = paginate("http://example.com/seasons/")
            assert result == []

    def test_race_table_extracted(self):
        data = {
            "MRData": {
                "total": "1",
                "limit": "1000",
                "RaceTable": {"Races": [{"raceName": "Bahrain GP"}]},
            }
        }
        with patch("src.ingestion.ergast_client.fetch_json", return_value=data):
            result = paginate("http://example.com/2024/results/")
            assert len(result) == 1
            assert result[0]["raceName"] == "Bahrain GP"

    def test_driver_table_extracted(self):
        data = {
            "MRData": {
                "total": "1",
                "limit": "1000",
                "DriverTable": {"Drivers": [{"driverId": "hamilton"}]},
            }
        }
        with patch("src.ingestion.ergast_client.fetch_json", return_value=data):
            result = paginate("http://example.com/drivers/")
            assert result[0]["driverId"] == "hamilton"

    def test_circuit_table_extracted(self):
        data = {
            "MRData": {
                "total": "1",
                "limit": "1000",
                "CircuitTable": {"Circuits": [{"circuitId": "bahrain"}]},
            }
        }
        with patch("src.ingestion.ergast_client.fetch_json", return_value=data):
            result = paginate("http://example.com/circuits/")
            assert result[0]["circuitId"] == "bahrain"

    def test_url_includes_limit_and_offset(self):
        data = _mr_data([], total=0)
        with patch("src.ingestion.ergast_client.fetch_json", return_value=data) as mock_fetch:
            paginate("http://example.com/seasons/", limit=500)
            called_url = mock_fetch.call_args[0][0]
            assert "limit=500" in called_url
            assert "offset=0" in called_url

    def test_stops_when_no_rows_returned(self):
        page1 = _mr_data([{"season": "2024"}], total=10, limit=1)
        page2 = _mr_data([], total=10, limit=1)
        with patch("src.ingestion.ergast_client.fetch_json", side_effect=[page1, page2]):
            result = paginate("http://example.com/seasons/", limit=1)
            assert len(result) == 1
