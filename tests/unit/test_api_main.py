"""Tests for src/api/main.py"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _get_token(client, username="admin", password="admin"):
    r = client.post("/token", data={"username": username, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class TestRootAndHealth:
    def test_root_returns_service_info(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "F1 Strategy Optimizer API"
        assert data["status"] == "running"

    def test_health_returns_healthy(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data

    def test_metrics_endpoint_returns_200(self, client):
        r = client.get("/metrics")
        assert r.status_code == 200


class TestAuth:
    def test_valid_login_returns_token(self, client):
        r = client.post("/token", data={"username": "admin", "password": "admin"})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_invalid_credentials_returns_401(self, client):
        r = client.post("/token", data={"username": "admin", "password": "wrongpass"})
        assert r.status_code == 401

    def test_nonexistent_user_returns_401(self, client):
        r = client.post("/token", data={"username": "ghost", "password": "pass"})
        assert r.status_code == 401

    def test_protected_endpoint_without_token_returns_401(self, client):
        r = client.get("/users/me")
        assert r.status_code == 401

    def test_protected_endpoint_with_invalid_token_returns_401(self, client):
        r = client.get("/users/me", headers={"Authorization": "Bearer badtoken"})
        assert r.status_code == 401


class TestUsersMe:
    def test_returns_current_user(self, client):
        token = _get_token(client)
        r = client.get("/users/me", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["username"] == "admin"


class TestStrategyRecommend:
    def _payload(self, **overrides):
        base = {
            "race_id": "2024_1",
            "driver_id": "max_verstappen",
            "current_lap": 20,
            "current_compound": "MEDIUM",
            "fuel_level": 60.0,
            "track_temp": 40.0,
            "air_temp": 28.0,
        }
        base.update(overrides)
        return base

    def test_returns_recommendation(self, client):
        token = _get_token(client)
        r = client.post("/strategy/recommend", json=self._payload(), headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert "recommended_action" in data
        assert "confidence" in data
        assert "model_source" in data

    def test_rule_based_fallback_early_lap(self, client):
        token = _get_token(client)
        r = client.post("/strategy/recommend", json=self._payload(current_lap=10), headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert data["recommended_action"] == "CONTINUE"
        assert data["model_source"] == "rule_based_fallback"

    def test_rule_based_fallback_late_lap(self, client):
        token = _get_token(client)
        r = client.post("/strategy/recommend", json=self._payload(current_lap=40), headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["recommended_action"] == "PIT_SOON"

    def test_requires_auth(self, client):
        r = client.post("/strategy/recommend", json=self._payload())
        assert r.status_code == 401

    def test_viewer_role_forbidden(self, client):
        token = _get_token(client, username="viewer", password="password")
        r = client.post("/strategy/recommend", json=self._payload(), headers=_auth(token))
        assert r.status_code == 403


class TestDataDrivers:
    def test_returns_driver_list(self, client):
        token = _get_token(client)
        r = client.get("/data/drivers", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) > 0
        assert "driver_id" in data[0]

    def test_requires_auth(self, client):
        r = client.get("/data/drivers")
        assert r.status_code == 401


class TestModelsStatus:
    def test_returns_models_list(self, client):
        token = _get_token(client)
        r = client.get("/models/status", headers=_auth(token))
        assert r.status_code == 200
        data = r.json()
        assert "models" in data
        assert isinstance(data["models"], list)

    def test_requires_auth(self, client):
        r = client.get("/models/status")
        assert r.status_code == 401


class TestV1SystemHealth:
    def test_returns_health_dict(self, client):
        r = client.get("/api/v1/health/system")
        assert r.status_code == 200
        data = r.json()
        assert "status" in data
        assert "timestamp" in data
        assert "ml_model" in data


class TestV1RaceState:
    def test_requires_auth(self, client):
        r = client.get("/api/v1/race/state", params={"race_id": "2024_1", "lap": 10})
        assert r.status_code == 401

    def test_returns_race_state(self, client):
        token = _get_token(client)
        mock_state = MagicMock()
        mock_state.race_id = "2024_1"
        mock_state.lap_number = 10
        mock_state.total_laps = 57
        mock_state.weather = "dry"
        mock_state.track_temp = 40.0
        mock_state.air_temp = 28.0
        mock_state.safety_car = False
        mock_state.drivers = []
        with patch("src.api.main._get_simulator") as mock_sim:
            mock_sim.return_value.step.return_value = mock_state
            r = client.get(
                "/api/v1/race/state",
                params={"race_id": "2024_1", "lap": 10},
                headers=_auth(token),
            )
            assert r.status_code == 200
            data = r.json()
            assert data["race_id"] == "2024_1"
            assert data["lap_number"] == 10


class TestV1RaceStandings:
    def test_requires_auth(self, client):
        r = client.get("/api/v1/race/standings", params={"race_id": "2024_1", "lap": 10})
        assert r.status_code == 401

    def test_returns_standings(self, client):
        token = _get_token(client)
        with patch("src.api.main._get_simulator") as mock_sim:
            mock_sim.return_value.get_standings.return_value = [{"position": 1, "driver_id": "VER"}]
            r = client.get(
                "/api/v1/race/standings",
                params={"race_id": "2024_1", "lap": 10},
                headers=_auth(token),
            )
            assert r.status_code == 200
            data = r.json()
            assert "standings" in data


class TestV1Drivers:
    def test_requires_auth(self, client):
        r = client.get("/api/v1/drivers")
        assert r.status_code == 401

    def test_returns_drivers_with_count(self, client):
        token = _get_token(client)
        mock_pipeline = MagicMock()
        mock_pipeline._drivers.return_value = MagicMock(
            iterrows=MagicMock(return_value=iter([]))
        )
        with patch("src.api.main._get_pipeline", return_value=mock_pipeline):
            r = client.get("/api/v1/drivers", headers=_auth(token))
            assert r.status_code == 200
            data = r.json()
            assert "count" in data
            assert "drivers" in data


class TestV1DriverHistory:
    def test_requires_auth(self, client):
        r = client.get("/api/v1/drivers/max_verstappen/history")
        assert r.status_code == 401

    def test_returns_404_when_no_races(self, client):
        token = _get_token(client)
        mock_pipeline = MagicMock()
        mock_pipeline.get_driver_history.return_value = {"races": 0}
        with patch("src.api.main._get_pipeline", return_value=mock_pipeline):
            r = client.get("/api/v1/drivers/unknown_driver/history", headers=_auth(token))
            assert r.status_code == 404

    def test_returns_history_when_found(self, client):
        token = _get_token(client)
        mock_pipeline = MagicMock()
        mock_pipeline.get_driver_history.return_value = {
            "driver_id": "max_verstappen", "races": 150, "wins": 50
        }
        with patch("src.api.main._get_pipeline", return_value=mock_pipeline):
            r = client.get("/api/v1/drivers/max_verstappen/history", headers=_auth(token))
            assert r.status_code == 200
            assert r.json()["races"] == 150


class TestV1StrategySimulate:
    def _payload(self):
        return {
            "race_id": "2024_1",
            "driver_id": "max_verstappen",
            "strategy": [[20, "MEDIUM"], [42, "HARD"]],
        }

    def test_requires_auth(self, client):
        r = client.post("/api/v1/strategy/simulate", json=self._payload())
        assert r.status_code == 401

    def test_returns_simulation_result(self, client):
        token = _get_token(client)
        mock_result = MagicMock()
        mock_result.driver_id = "max_verstappen"
        mock_result.race_id = "2024_1"
        mock_result.predicted_final_position = 1
        mock_result.predicted_total_time_s = 5400.0
        mock_result.strategy = [(20, "MEDIUM"), (42, "HARD")]
        mock_result.lap_times_s = [90.0] * 57
        with patch("src.api.main._get_simulator") as mock_sim:
            mock_sim.return_value.simulate_strategy.return_value = mock_result
            r = client.post(
                "/api/v1/strategy/simulate", json=self._payload(), headers=_auth(token)
            )
            assert r.status_code == 200
            data = r.json()
            assert data["driver_id"] == "max_verstappen"
            assert data["predicted_final_position"] == 1
