"""Tests for pipeline/scripts/build_constructor_pace.py."""

import json

import numpy as np
import pandas as pd
import pytest

from pipeline.scripts.build_constructor_pace import (
    assign_tier,
    build_output,
    compute_relative_pace,
    fit_constructor_pace,
    get_circuit_category,
    slugify,
)


# ── slugify ───────────────────────────────────────────────────────────────────


def test_slugify_basic():
    assert slugify("Red Bull") == "red_bull"


def test_slugify_special_chars():
    assert slugify("Mercedes-AMG Petronas") == "mercedes_amg_petronas"


def test_slugify_already_slug():
    assert slugify("ferrari") == "ferrari"


# ── get_circuit_category ──────────────────────────────────────────────────────


def test_circuit_category_street():
    assert get_circuit_category("monaco") == "street"


def test_circuit_category_high_speed():
    assert get_circuit_category("monza") == "high_speed"


def test_circuit_category_unknown():
    assert get_circuit_category("unknown_track") == "technical"


# ── assign_tier ───────────────────────────────────────────────────────────────


def test_assign_tier_1():
    assert assign_tier(2023) == 1


def test_assign_tier_2():
    assert assign_tier(2010) == 2


def test_assign_tier_3():
    assert assign_tier(1998) == 3


def test_assign_tier_boundary_2018():
    assert assign_tier(2018) == 1


def test_assign_tier_boundary_2003():
    assert assign_tier(2003) == 2


# ── compute_relative_pace ─────────────────────────────────────────────────────


def test_compute_relative_pace_columns():
    df = pd.DataFrame(
        {
            "season": [2024, 2024, 2024],
            "circuit_slug": ["monaco", "monaco", "monaco"],
            "lap_time_s": [90.0, 90.0, 91.0],
        }
    )
    result = compute_relative_pace(df, "lap_time_s")
    assert "relative_pace" in result.columns
    assert "session_median_s" in result.columns


def test_compute_relative_pace_values():
    df = pd.DataFrame(
        {
            "season": [2024, 2024],
            "circuit_slug": ["monza", "monza"],
            "lap_time_s": [80.0, 100.0],
        }
    )
    result = compute_relative_pace(df, "lap_time_s")
    median = 90.0
    assert result["session_median_s"].iloc[0] == pytest.approx(median)
    assert result["relative_pace"].iloc[0] == pytest.approx(80.0 / 90.0 - 1.0)


# ── fit_constructor_pace ──────────────────────────────────────────────────────


def _make_df(n_drivers=3, n_constructors=2, n_circuits=2, n_seasons=1):
    """Build a minimal synthetic DataFrame for MixedLM fitting."""
    rows = []
    for season in range(2022, 2022 + n_seasons):
        for c_idx in range(n_constructors):
            for d_idx in range(n_drivers):
                for circ in range(n_circuits):
                    rows.append(
                        {
                            "season": season,
                            "driver_id": f"driver_{d_idx}",
                            "constructor_season": f"constructor_{c_idx}_{season}",
                            "circuit_category": "high_speed" if circ == 0 else "technical",
                            "relative_pace": -0.01 * c_idx + np.random.normal(0, 0.001),
                            "session_median_s": 90.0,
                        }
                    )
    return pd.DataFrame(rows)


def test_fit_constructor_pace_returns_dict():
    df = _make_df()
    result = fit_constructor_pace(df)
    assert isinstance(result, dict)


def test_fit_constructor_pace_empty_df():
    df = pd.DataFrame(
        columns=["driver_id", "constructor_season", "circuit_category", "relative_pace", "session_median_s"]
    )
    result = fit_constructor_pace(df)
    assert result == {}


def test_fit_constructor_pace_too_few_drivers():
    df = _make_df(n_drivers=1)
    result = fit_constructor_pace(df)
    assert result == {}


# ── build_output ──────────────────────────────────────────────────────────────


def test_build_output_structure():
    coefs = {"red_bull_2024": -0.3, "ferrari_2024": 0.05}
    tier_map = {"red_bull_2024": 1, "ferrari_2024": 1}
    limited = set()
    output = build_output(coefs, tier_map, limited)
    assert "red_bull" in output
    assert "ferrari" in output
    assert "2024" in output["red_bull"]["seasons"]
    assert output["red_bull"]["seasons"]["2024"]["pace_delta_s"] == -0.3


def test_build_output_limited_flag():
    coefs = {"red_bull_2026": -0.1}
    tier_map = {"red_bull_2026": 1}
    limited = {"red_bull_2026"}
    output = build_output(coefs, tier_map, limited)
    assert output["red_bull"]["seasons"]["2026"]["limited_data"] is True


def test_build_output_not_limited():
    coefs = {"ferrari_2024": 0.05}
    tier_map = {"ferrari_2024": 1}
    limited = set()
    output = build_output(coefs, tier_map, limited)
    assert output["ferrari"]["seasons"]["2024"]["limited_data"] is False


def test_build_output_skips_malformed_key():
    coefs = {"noyear": 0.1, "ferrari_2024": 0.0}
    tier_map = {"ferrari_2024": 1}
    limited = set()
    output = build_output(coefs, tier_map, limited)
    assert "noyear" not in output
    assert "ferrari" in output
