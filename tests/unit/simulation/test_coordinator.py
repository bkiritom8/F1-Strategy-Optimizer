import pytest
from unittest.mock import MagicMock, patch
from src.simulation.coordinator import scenario_hash, n_trials, SimulationCoordinator


def test_scenario_hash_deterministic():
    h1 = scenario_hash("monaco_2025", {"driver": "hamilton"})
    h2 = scenario_hash("monaco_2025", {"driver": "hamilton"})
    assert h1 == h2
    assert len(h1) == 16


def test_scenario_hash_different_scenarios():
    h1 = scenario_hash("monaco_2025", {"driver": "hamilton"})
    h2 = scenario_hash("monaco_2025", {"driver": "norris"})
    assert h1 != h2


def test_n_trials_full_load():
    assert n_trials(0) == 50
    assert n_trials(99) == 50


def test_n_trials_high_load():
    assert n_trials(100) == 20
    assert n_trials(499) == 20


def test_n_trials_overloaded():
    assert n_trials(500) == 10
    assert n_trials(9999) == 10


def test_coordinator_cache_hit(monkeypatch):
    mock_redis = MagicMock()
    mock_redis.exists.return_value = True
    mock_redis.get.return_value = '{"winner": "norris"}'

    coord = SimulationCoordinator(redis_client=mock_redis)
    result = coord.check_cache("abc123")
    assert result is not None
    assert result["winner"] == "norris"


def test_coordinator_cache_miss(monkeypatch):
    mock_redis = MagicMock()
    mock_redis.exists.return_value = False

    coord = SimulationCoordinator(redis_client=mock_redis)
    result = coord.check_cache("abc123")
    assert result is None
