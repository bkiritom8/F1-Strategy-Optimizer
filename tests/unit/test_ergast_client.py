"""
Unit tests for Ergast API client
"""

import pytest
from unittest.mock import Mock, patch
import requests

import sys

sys.path.insert(0, "/home/user/test")

from src.ingestion.ergast_client import ErgastClient, CircuitBreaker, Race, Driver


class TestCircuitBreaker:
    """Test circuit breaker functionality"""

    def test_circuit_breaker_closed_state(self):
        """Test circuit breaker in closed state"""
        cb = CircuitBreaker(failure_threshold=3)
        assert cb.state == "CLOSED"

        # Successful calls should keep circuit closed
        result = cb.call(lambda: "success")
        assert result == "success"
        assert cb.state == "CLOSED"

    def test_circuit_breaker_opens_after_failures(self):
        """Test circuit breaker opens after threshold failures"""
        cb = CircuitBreaker(failure_threshold=3)

        # Simulate failures
        for _ in range(3):
            with pytest.raises(requests.RequestException):
                cb.call(lambda: self._failing_function())

        assert cb.state == "OPEN"

    def _failing_function(self):
        raise requests.RequestException("Test failure")


class TestErgastClient:
    """Test Ergast API client"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        return ErgastClient(timeout=10, max_retries=2)

    @pytest.fixture
    def mock_response(self):
        """Create mock HTTP response"""
        mock = Mock()
        mock.status_code = 200
        mock.json.return_value = {
            "MRData": {"total": "1", "SeasonTable": {"Seasons": [{"season": "2024"}]}}
        }
        return mock

    def test_client_initialization(self, client):
        """Test client initialization"""
        assert client.base_url == ErgastClient.BASE_URL
        assert client.timeout == 10
        assert client.max_retries == 2

    @patch("src.ingestion.ergast_client.requests.Session.get")
    def test_get_seasons(self, mock_get, client, mock_response):
        """Test getting seasons"""
        mock_get.return_value = mock_response

        seasons = client.get_seasons(2024, 2024)

        assert len(seasons) == 1
        assert 2024 in seasons
        mock_get.assert_called_once()

    @patch("src.ingestion.ergast_client.requests.Session.get")
    def test_get_races(self, mock_get, client):
        """Test getting races for a season"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "MRData": {
                "RaceTable": {
                    "Races": [
                        {
                            "season": "2024",
                            "round": "1",
                            "raceName": "Bahrain Grand Prix",
                            "Circuit": {
                                "circuitId": "bahrain",
                                "circuitName": "Bahrain International Circuit",
                            },
                            "date": "2024-03-02",
                            "time": "15:00:00Z",
                            "url": "http://example.com",
                        }
                    ]
                }
            }
        }
        mock_get.return_value = mock_response

        races = client.get_races(2024)

        assert len(races) == 1
        assert isinstance(races[0], Race)
        assert races[0].season == 2024
        assert races[0].raceName == "Bahrain Grand Prix"

    @patch("src.ingestion.ergast_client.requests.Session.get")
    def test_get_drivers(self, mock_get, client):
        """Test getting drivers"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "MRData": {
                "DriverTable": {
                    "Drivers": [
                        {
                            "driverId": "max_verstappen",
                            "permanentNumber": "1",
                            "code": "VER",
                            "givenName": "Max",
                            "familyName": "Verstappen",
                            "dateOfBirth": "1997-09-30",
                            "nationality": "Dutch",
                            "url": "http://example.com",
                        }
                    ]
                }
            }
        }
        mock_get.return_value = mock_response

        drivers = client.get_drivers(2024)

        assert len(drivers) == 1
        assert isinstance(drivers[0], Driver)
        assert drivers[0].driverId == "max_verstappen"
        assert drivers[0].code == "VER"

    @patch("src.ingestion.ergast_client.requests.Session.get")
    def test_rate_limiting(self, mock_get, client, mock_response):
        """Test rate limiting enforcement"""
        import time

        mock_get.return_value = mock_response

        start = time.time()
        client.get_seasons(2024, 2024)
        client.get_seasons(2024, 2024)
        elapsed = time.time() - start

        # Should have at least one rate limit delay
        assert elapsed >= client.RATE_LIMIT_DELAY

    @patch("src.ingestion.ergast_client.requests.Session.get")
    def test_error_handling(self, mock_get, client):
        """Test error handling for failed requests"""
        mock_get.side_effect = requests.RequestException("Network error")

        seasons = client.get_seasons(2024, 2024)

        # Should return empty list on error
        assert seasons == []

    @patch("src.ingestion.ergast_client.requests.Session.get")
    def test_retry_logic(self, mock_get, client, mock_response):
        """Test retry logic on transient failures"""
        # First call fails, second succeeds
        mock_get.side_effect = [requests.Timeout("Timeout"), mock_response]

        seasons = client.get_seasons(2024, 2024)

        # Should eventually succeed
        assert len(seasons) == 1
        assert mock_get.call_count == 2


class TestDataModels:
    """Test Pydantic data models"""

    def test_race_model(self):
        """Test Race model validation"""
        race = Race(
            season=2024,
            round=1,
            raceName="Bahrain GP",
            circuitId="bahrain",
            circuitName="Bahrain International Circuit",
            date="2024-03-02",
            url="http://example.com",
        )

        assert race.season == 2024
        assert race.round == 1
        assert race.raceName == "Bahrain GP"

    def test_driver_model(self):
        """Test Driver model validation"""
        driver = Driver(
            driverId="max_verstappen",
            givenName="Max",
            familyName="Verstappen",
            dateOfBirth="1997-09-30",
            nationality="Dutch",
            url="http://example.com",
        )

        assert driver.driverId == "max_verstappen"
        assert driver.givenName == "Max"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
