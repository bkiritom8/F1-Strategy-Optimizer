"""Tests for pipeline/scripts/build_constructor_pace.py."""

import json

import numpy as np
import pandas as pd
import pytest

from pipeline.scripts.build_constructor_pace import (
    _circuit_category,
    _build_output,
    CONSTRUCTOR_ID_MAP,
)


# ── _circuit_category ─────────────────────────────────────────────────────────


def test_circuit_category_street():
    assert _circuit_category("Monaco Grand Prix") == "street"


def test_circuit_category_high_speed():
    assert _circuit_category("Italian Grand Prix") == "high_speed"


def test_circuit_category_balanced():
    assert _circuit_category("Hungarian Grand Prix") == "balanced"


def test_circuit_category_unknown():
    assert _circuit_category("Some Unknown GP") == "balanced"


# ── CONSTRUCTOR_ID_MAP ────────────────────────────────────────────────────────


def test_constructor_id_map_has_all_teams():
    expected = [
        "Alfa Romeo", "Alfa Romeo Racing", "AlphaTauri", "Alpine",
        "Aston Martin", "Ferrari", "Force India", "Haas F1 Team",
        "Kick Sauber", "McLaren", "Mercedes", "RB", "Racing Point",
        "Red Bull Racing", "Renault", "Sauber", "Toro Rosso",
        "Unknown", "Williams",
    ]
    for team in expected:
        assert team in CONSTRUCTOR_ID_MAP


def test_constructor_id_map_values_are_slugs():
    for name, slug in CONSTRUCTOR_ID_MAP.items():
        assert slug == slug.lower()
        assert " " not in slug


# ── _build_output ─────────────────────────────────────────────────────────────


def test_build_output_structure():
    pace_deltas = {"red_bull_2024": -0.312, "ferrari_2024": 0.05}
    output = _build_output(pace_deltas)
    assert "constructors" in output
    assert "version" in output
    assert "reference" in output
    assert "red_bull" in output["constructors"]
    assert "ferrari" in output["constructors"]
    assert "2024" in output["constructors"]["red_bull"]["seasons"]


def test_build_output_pace_delta():
    pace_deltas = {"red_bull_2024": -0.312}
    output = _build_output(pace_deltas)
    season = output["constructors"]["red_bull"]["seasons"]["2024"]
    assert season["pace_delta_s"] == -0.312
    assert season["data_tier"] == 1
    assert season["limited_data"] is False


def test_build_output_limited_data_2026():
    pace_deltas = {"red_bull_2026": -0.1}
    output = _build_output(pace_deltas)
    season = output["constructors"]["red_bull"]["seasons"]["2026"]
    assert season["limited_data"] is True


def test_build_output_not_limited_2024():
    pace_deltas = {"ferrari_2024": 0.05}
    output = _build_output(pace_deltas)
    season = output["constructors"]["ferrari"]["seasons"]["2024"]
    assert season["limited_data"] is False


def test_build_output_skips_malformed_key():
    pace_deltas = {"noyear": 0.1, "ferrari_2024": 0.0}
    output = _build_output(pace_deltas)
    constructors = output["constructors"]
    assert "noyear" not in constructors
    assert "ferrari" in constructors


def test_build_output_sorted():
    pace_deltas = {"williams_2024": 0.5, "alfa_romeo_2024": 0.1, "ferrari_2024": -0.3}
    output = _build_output(pace_deltas)
    keys = list(output["constructors"].keys())
    assert keys == sorted(keys)


def test_build_output_multiple_seasons():
    pace_deltas = {
        "red_bull_2023": -0.445,
        "red_bull_2024": -0.312,
    }
    output = _build_output(pace_deltas)
    seasons = output["constructors"]["red_bull"]["seasons"]
    assert "2023" in seasons
    assert "2024" in seasons
    assert seasons["2023"]["pace_delta_s"] == -0.445
    assert seasons["2024"]["pace_delta_s"] == -0.312


def test_build_output_display_name():
    pace_deltas = {"red_bull_2024": -0.3}
    output = _build_output(pace_deltas)
    assert output["constructors"]["red_bull"]["display_name"] == "Red Bull Racing"


def test_build_output_empty():
    output = _build_output({})
    assert output["constructors"] == {}
    assert "version" in output