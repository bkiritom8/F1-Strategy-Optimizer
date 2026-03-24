"""Tests for src/ingestion/http_client.py"""
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.ingestion.http_client import fetch_json, rate_limited_get


class TestRateLimitedGet:
    def test_returns_response(self):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        with patch("src.ingestion.http_client.requests.get", return_value=mock_resp) as mock_get:
            result = rate_limited_get("http://example.com/api")
            mock_get.assert_called_once_with("http://example.com/api", timeout=30)
            assert result is mock_resp

    def test_custom_timeout(self):
        mock_resp = MagicMock(spec=requests.Response)
        with patch("src.ingestion.http_client.requests.get", return_value=mock_resp) as mock_get:
            rate_limited_get("http://example.com/api", timeout=10)
            mock_get.assert_called_once_with("http://example.com/api", timeout=10)


class TestFetchJson:
    def _mock_response(self, status_code=200, json_data=None):
        resp = MagicMock(spec=requests.Response)
        resp.status_code = status_code
        resp.json.return_value = json_data or {"key": "value"}
        resp.raise_for_status = MagicMock()
        return resp

    def test_returns_json_on_success(self):
        resp = self._mock_response(json_data={"MRData": {"total": "0"}})
        with patch("src.ingestion.http_client.rate_limited_get", return_value=resp):
            result = fetch_json("http://example.com/api")
            assert result == {"MRData": {"total": "0"}}

    def test_raises_for_status_on_error(self):
        resp = self._mock_response(status_code=500)
        resp.raise_for_status.side_effect = requests.HTTPError("500")
        with patch("src.ingestion.http_client.rate_limited_get", return_value=resp):
            with pytest.raises(requests.HTTPError):
                fetch_json("http://example.com/api")

    def test_handles_429_with_retry(self):
        resp_429 = self._mock_response(status_code=429)
        resp_ok = self._mock_response(status_code=200, json_data={"ok": True})
        with patch("src.ingestion.http_client.rate_limited_get", side_effect=[resp_429, resp_ok]):
            with patch("src.ingestion.http_client.time.sleep"):
                result = fetch_json("http://example.com/api")
                assert result == {"ok": True}

    def test_reraises_connection_error_after_retries(self):
        with patch(
            "src.ingestion.http_client.rate_limited_get",
            side_effect=requests.ConnectionError("unreachable"),
        ):
            with pytest.raises(requests.ConnectionError):
                fetch_json("http://example.com/api")
