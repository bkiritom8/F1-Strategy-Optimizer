"""Tests for constructor_id handling in the simulate route."""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.routes.simulate import _parse_season, router


# ── _parse_season unit tests ──────────────────────────────────────────────────


def test_parse_season_valid():
    assert _parse_season("2024_monaco") == 2024


def test_parse_season_valid_single():
    assert _parse_season("2026_bahrain") == 2026


def test_parse_season_no_underscore():
    assert _parse_season("monaco") is None


def test_parse_season_non_numeric():
    assert _parse_season("race_monaco") is None


def test_parse_season_empty():
    assert _parse_season("") is None


def test_parse_season_none():
    assert _parse_season(None) is None  # type: ignore[arg-type]


# ── Route integration tests ───────────────────────────────────────────────────


@pytest.fixture
def mock_deps():
    """Patch out auth, coordinator, and constructor store."""
    mock_coord = MagicMock()
    mock_coord.replay_from_cache.return_value = False
    mock_coord.get_queue_depth.return_value = 0
    mock_coord.n_trials.return_value = 50

    mock_store = MagicMock()
    mock_store.get_offset_ms.return_value = -300.0

    mock_user = MagicMock()

    with (
        patch("src.api.routes.simulate._get_coordinator", return_value=mock_coord),
        patch("src.api.routes.simulate._get_constructor_store", return_value=mock_store),
        patch("src.api.routes.simulate.get_current_user", return_value=mock_user),
        patch("src.api.routes.simulate.iam_simulator") as mock_iam,
    ):
        mock_iam.check_permission.return_value = True
        yield mock_coord, mock_store


def test_constructor_offset_resolved(mock_deps):
    mock_coord, mock_store = mock_deps
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=True)

    resp = client.post(
        "/simulate/race",
        json={
            "race_id": "2024_monaco",
            "drivers": [
                {
                    "driver_id": "VER",
                    "constructor_id": "red_bull",
                    "grid_position": 1,
                }
            ],
        },
    )
    assert resp.status_code == 200
    mock_store.get_offset_ms.assert_called_once_with("red_bull", 2024)


def test_no_constructor_id_no_store_lookup(mock_deps):
    mock_coord, mock_store = mock_deps
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=True)

    resp = client.post(
        "/simulate/race",
        json={
            "race_id": "2024_monaco",
            "drivers": [
                {
                    "driver_id": "VER",
                    "grid_position": 1,
                }
            ],
        },
    )
    assert resp.status_code == 200
    mock_store.get_offset_ms.assert_not_called()
