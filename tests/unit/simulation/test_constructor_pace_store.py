"""Tests for ConstructorPaceStore."""

import json
import os

import pytest

from src.simulation.constructor_pace import ConstructorPaceStore


@pytest.fixture
def pace_json(tmp_path):
    data = {
        "constructors": {
            "red_bull": {
                "seasons": {
                    "2024": {"pace_delta_s": -0.3, "data_tier": 1, "limited_data": False},
                    "2026": {"pace_delta_s": -0.1, "data_tier": 1, "limited_data": True},
                }
            },
            "ferrari": {
                "seasons": {
                    "2024": {"pace_delta_s": 0.05, "data_tier": 1, "limited_data": False},
                }
            },
        }
    }
    p = tmp_path / "constructor_pace.json"
    p.write_text(json.dumps(data))
    return str(p)


def test_get_offset_ms_known(pace_json):
    store = ConstructorPaceStore(source=pace_json)
    assert store.get_offset_ms("red_bull", 2024) == pytest.approx(-300.0)


def test_get_offset_ms_positive(pace_json):
    store = ConstructorPaceStore(source=pace_json)
    assert store.get_offset_ms("ferrari", 2024) == pytest.approx(50.0)


def test_get_offset_ms_unknown_constructor(pace_json):
    store = ConstructorPaceStore(source=pace_json)
    assert store.get_offset_ms("williams", 2024) == 0.0


def test_get_offset_ms_unknown_season(pace_json):
    store = ConstructorPaceStore(source=pace_json)
    assert store.get_offset_ms("red_bull", 2020) == 0.0


def test_is_limited_data_true(pace_json):
    store = ConstructorPaceStore(source=pace_json)
    assert store.is_limited_data("red_bull", 2026) is True


def test_is_limited_data_false(pace_json):
    store = ConstructorPaceStore(source=pace_json)
    assert store.is_limited_data("red_bull", 2024) is False


def test_is_limited_data_unknown(pace_json):
    store = ConstructorPaceStore(source=pace_json)
    assert store.is_limited_data("alpine", 2024) is False


def test_empty_store_returns_zero(tmp_path, monkeypatch):
    monkeypatch.delenv("CONSTRUCTOR_PACE_PATH", raising=False)
    nonexistent = str(tmp_path / "missing.json")
    store = ConstructorPaceStore(source=nonexistent)
    assert store.get_offset_ms("red_bull", 2024) == 0.0
    assert len(store) == 0
