"""Tests for pipeline/scripts/build_car_performance.py."""

import pandas as pd
import pytest

from pipeline.scripts.build_car_performance import (
    _circuit_category,
    _build_output,
    _compute_deg_profiles,
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
        "Alfa Romeo",
        "Alfa Romeo Racing",
        "AlphaTauri",
        "Alpine",
        "Aston Martin",
        "Ferrari",
        "Force India",
        "Haas F1 Team",
        "Kick Sauber",
        "McLaren",
        "Mercedes",
        "RB",
        "Racing Point",
        "Red Bull Racing",
        "Renault",
        "Sauber",
        "Toro Rosso",
        "Unknown",
        "Williams",
    ]
    for team in expected:
        assert team in CONSTRUCTOR_ID_MAP


def test_constructor_id_map_values_are_slugs():
    for name, slug in CONSTRUCTOR_ID_MAP.items():
        assert slug == slug.lower()
        assert " " not in slug


# ── _build_output ─────────────────────────────────────────────────────────────


def _mock_df():
    """Minimal df with constructor_id and team_name for _build_output."""
    return pd.DataFrame(
        {
            "constructor_id": ["red_bull", "ferrari"],
            "team_name": ["Red Bull Racing", "Ferrari"],
        }
    )


def test_build_output_structure():
    pace = {"red_bull_2024": -0.312, "ferrari_2024": 0.05}
    deg = {}
    output = _build_output(pace, deg, _mock_df())
    assert "constructors" in output
    assert "version" in output
    assert "reference" in output
    assert "red_bull" in output["constructors"]
    assert "ferrari" in output["constructors"]
    assert "2024" in output["constructors"]["red_bull"]["seasons"]


def test_build_output_pace_delta():
    pace = {"red_bull_2024": -0.312}
    output = _build_output(pace, {}, _mock_df())
    season = output["constructors"]["red_bull"]["seasons"]["2024"]
    assert season["pace_delta_s"] == -0.312
    assert season["data_tier"] == 1
    assert season["limited_data"] is False


def test_build_output_limited_data_2026():
    pace = {"red_bull_2026": -0.1}
    output = _build_output(pace, {}, _mock_df())
    season = output["constructors"]["red_bull"]["seasons"]["2026"]
    assert season["limited_data"] is True


def test_build_output_not_limited_2024():
    pace = {"ferrari_2024": 0.05}
    output = _build_output(pace, {}, _mock_df())
    season = output["constructors"]["ferrari"]["seasons"]["2024"]
    assert season["limited_data"] is False


def test_build_output_skips_malformed_key():
    pace = {"noyear": 0.1, "ferrari_2024": 0.0}
    output = _build_output(pace, {}, _mock_df())
    assert "noyear" not in output["constructors"]
    assert "ferrari" in output["constructors"]


def test_build_output_skips_unknown():
    pace = {"unknown_2024": 0.5, "ferrari_2024": 0.0}
    output = _build_output(pace, {}, _mock_df())
    assert "unknown" not in output["constructors"]
    assert "ferrari" in output["constructors"]


def test_build_output_sorted():
    pace = {"williams_2024": 0.5, "alfa_romeo_2024": 0.1, "ferrari_2024": -0.3}
    output = _build_output(pace, {}, _mock_df())
    keys = list(output["constructors"].keys())
    assert keys == sorted(keys)


def test_build_output_multiple_seasons():
    pace = {"red_bull_2023": -0.445, "red_bull_2024": -0.312}
    output = _build_output(pace, {}, _mock_df())
    seasons = output["constructors"]["red_bull"]["seasons"]
    assert "2023" in seasons
    assert "2024" in seasons
    assert seasons["2023"]["pace_delta_s"] == -0.445
    assert seasons["2024"]["pace_delta_s"] == -0.312


def test_build_output_display_name():
    pace = {"red_bull_2024": -0.3}
    output = _build_output(pace, {}, _mock_df())
    assert output["constructors"]["red_bull"]["display_name"] == "Red Bull Racing"


def test_build_output_empty():
    output = _build_output({}, {}, _mock_df())
    assert output["constructors"] == {}
    assert "version" in output


def test_build_output_with_compounds():
    pace = {"red_bull_2024": -0.312}
    deg = {
        ("red_bull", "2024"): {
            "SOFT": {
                "deg_slope_per_lap": 0.0697,
                "base_deg_s": -1.533,
                "avg_tyre_delta": -0.742,
                "r_squared": 0.094,
                "n_laps": 159,
            },
            "HARD": {
                "deg_slope_per_lap": 0.0221,
                "base_deg_s": -0.8,
                "avg_tyre_delta": -0.3,
                "r_squared": 0.048,
                "n_laps": 400,
            },
        }
    }
    output = _build_output(pace, deg, _mock_df())
    season = output["constructors"]["red_bull"]["seasons"]["2024"]
    assert season["pace_delta_s"] == -0.312
    assert "SOFT" in season["compounds"]
    assert "HARD" in season["compounds"]
    assert season["compounds"]["SOFT"]["deg_slope_per_lap"] == 0.0697
    assert season["compounds"]["HARD"]["n_laps"] == 400


def test_build_output_counts():
    pace = {"red_bull_2024": -0.3, "ferrari_2024": 0.05}
    deg = {
        ("red_bull", "2024"): {
            "SOFT": {
                "deg_slope_per_lap": 0.07,
                "base_deg_s": -1.5,
                "avg_tyre_delta": -0.7,
                "r_squared": 0.09,
                "n_laps": 100,
            },
            "MEDIUM": {
                "deg_slope_per_lap": 0.04,
                "base_deg_s": -0.5,
                "avg_tyre_delta": -0.3,
                "r_squared": 0.07,
                "n_laps": 200,
            },
        },
        ("ferrari", "2024"): {
            "SOFT": {
                "deg_slope_per_lap": 0.08,
                "base_deg_s": -1.0,
                "avg_tyre_delta": -0.5,
                "r_squared": 0.1,
                "n_laps": 150,
            },
        },
    }
    output = _build_output(pace, deg, _mock_df())
    assert output["n_constructors"] == 2
    assert output["n_compound_entries"] == 3


# ── _compute_deg_profiles ─────────────────────────────────────────────────────


def test_compute_deg_profiles_basic():
    import numpy as np

    np.random.seed(42)
    df = pd.DataFrame(
        {
            "constructor_id": ["red_bull"] * 20,
            "season": [2024] * 20,
            "Compound": ["SOFT"] * 20,
            "TyreLife": list(range(1, 21)),
            "tyre_delta": [0.01 * i + np.random.normal(0, 0.01) for i in range(1, 21)],
        }
    )
    profiles = _compute_deg_profiles(df)
    assert ("red_bull", "2024") in profiles
    assert "SOFT" in profiles[("red_bull", "2024")]
    assert profiles[("red_bull", "2024")]["SOFT"]["deg_slope_per_lap"] > 0


def test_compute_deg_profiles_skips_unknown():
    df = pd.DataFrame(
        {
            "constructor_id": ["unknown"] * 20,
            "season": [2024] * 20,
            "Compound": ["SOFT"] * 20,
            "TyreLife": list(range(1, 21)),
            "tyre_delta": [0.01 * i for i in range(1, 21)],
        }
    )
    profiles = _compute_deg_profiles(df)
    assert len(profiles) == 0


def test_compute_deg_profiles_skips_too_few_laps():
    df = pd.DataFrame(
        {
            "constructor_id": ["ferrari"] * 5,
            "season": [2024] * 5,
            "Compound": ["SOFT"] * 5,
            "TyreLife": [1, 2, 3, 4, 5],
            "tyre_delta": [0.1, 0.2, 0.3, 0.4, 0.5],
        }
    )
    profiles = _compute_deg_profiles(df)
    assert len(profiles) == 0
