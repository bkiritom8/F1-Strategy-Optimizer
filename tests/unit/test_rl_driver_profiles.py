"""
Unit tests for ml/rl/driver_profiles.py — driver profile lookup and lineup building.

No external deps required; all logic is pure Python.
"""

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from ml.rl.driver_profiles import (
    DRIVER_PROFILES,
    DEFAULT_GRID,
    CAR_PERFORMANCE_OFFSET_MS,
    build_race_lineup,
    get_display_name,
    get_profile,
)


class TestGetProfile:
    def test_returns_known_profile(self):
        p = get_profile("max_verstappen")
        assert p["aggression"] == pytest.approx(0.88)
        assert p["consistency"] == pytest.approx(0.96)

    def test_returns_generic_profile_for_unknown_driver(self):
        p = get_profile("unknown_driver_xyz")
        assert set(p.keys()) == {
            "aggression",
            "consistency",
            "tire_management",
            "pressure_response",
        }

    def test_returns_copy_not_reference(self):
        p1 = get_profile("lando_norris")
        p2 = get_profile("lando_norris")
        p1["aggression"] = 0.0
        assert p2["aggression"] != 0.0

    def test_all_profile_values_between_0_and_1(self):
        for driver, profile in DRIVER_PROFILES.items():
            for attr, val in profile.items():
                assert 0.0 <= val <= 1.0, f"{driver}.{attr} = {val} out of range"


class TestGetDisplayName:
    def test_known_driver_returns_full_name(self):
        assert get_display_name("lewis_hamilton") == "Lewis Hamilton"

    def test_unknown_driver_returns_title_cased_id(self):
        assert get_display_name("new_driver_id") == "New Driver Id"


class TestBuildRaceLineup:
    def test_lineup_has_20_entries(self):
        lineup = build_race_lineup("lando_norris")
        assert len(lineup) == 20

    def test_user_driver_flagged_as_user(self):
        lineup = build_race_lineup("lando_norris")
        user_entries = [e for e in lineup if e.is_user]
        assert len(user_entries) == 1
        assert user_entries[0].driver_id == "lando_norris"

    def test_user_placed_at_correct_start_position(self):
        lineup = build_race_lineup("lando_norris", user_start_position=5)
        user = next(e for e in lineup if e.is_user)
        assert user.start_position == 5

    def test_user_assigned_correct_start_compound(self):
        lineup = build_race_lineup("lando_norris", user_start_compound="SOFT")
        user = next(e for e in lineup if e.is_user)
        assert user.start_compound == "SOFT"

    def test_lineup_sorted_by_start_position(self):
        lineup = build_race_lineup("lando_norris", user_start_position=3)
        positions = [e.start_position for e in lineup]
        assert positions == sorted(positions)

    def test_custom_profile_applied_to_user(self):
        custom = {
            "aggression": 0.99,
            "consistency": 0.11,
            "tire_management": 0.50,
            "pressure_response": 0.50,
        }
        lineup = build_race_lineup("lando_norris", user_profile=custom)
        user = next(e for e in lineup if e.is_user)
        assert user.profile["aggression"] == pytest.approx(0.99)
        assert user.profile["consistency"] == pytest.approx(0.11)

    def test_user_profile_values_clamped_to_0_1(self):
        oob = {
            "aggression": 1.5,
            "consistency": -0.2,
            "tire_management": 0.5,
            "pressure_response": 0.5,
        }
        lineup = build_race_lineup("any_driver", user_profile=oob)
        user = next(e for e in lineup if e.is_user)
        assert user.profile["aggression"] == pytest.approx(1.0)
        assert user.profile["consistency"] == pytest.approx(0.0)

    def test_explicit_rivals_list_used(self):
        rivals = ["max_verstappen", "lewis_hamilton"]
        lineup = build_race_lineup(
            "lando_norris", rivals=rivals, user_start_position=3
        )
        rival_ids = {e.driver_id for e in lineup if not e.is_user}
        assert rival_ids == {"max_verstappen", "lewis_hamilton"}
        assert len(lineup) == 3

    def test_no_duplicate_positions(self):
        lineup = build_race_lineup("lando_norris")
        positions = [e.start_position for e in lineup]
        assert len(positions) == len(set(positions))

    def test_car_offset_applied_for_known_rival(self):
        lineup = build_race_lineup("lando_norris")
        max_entry = next(
            (e for e in lineup if e.driver_id == "max_verstappen"), None
        )
        if max_entry:
            assert max_entry.car_offset_ms == pytest.approx(
                CAR_PERFORMANCE_OFFSET_MS["max_verstappen"]
            )
