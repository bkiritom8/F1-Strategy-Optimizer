"""
Unit tests for ml/rl/race_runner.py — multi-driver race simulation.

Uses a minimal 2-driver lineup with a short circuit (5 laps) to keep
tests fast; ML adapters are not required (physics fallback is exercised).
"""

import sys
from pathlib import Path

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from ml.rl.actions import Action
from ml.rl.driver_profiles import DriverEntry, build_race_lineup
from ml.rl.race_runner import RaceRunner, RaceResult


def _make_tiny_lineup(user_id: str = "test_user") -> list[DriverEntry]:
    """Two-driver lineup: user + one rival."""
    user = DriverEntry(
        driver_id=user_id,
        display_name="Test User",
        profile={
            "aggression": 0.75,
            "consistency": 0.85,
            "tire_management": 0.80,
            "pressure_response": 0.75,
        },
        start_position=1,
        start_compound="MEDIUM",
        is_user=True,
    )
    rival = DriverEntry(
        driver_id="rival",
        display_name="Rival",
        profile={
            "aggression": 0.70,
            "consistency": 0.80,
            "tire_management": 0.75,
            "pressure_response": 0.70,
        },
        start_position=2,
        start_compound="HARD",
        is_user=False,
    )
    return [user, rival]


def _make_runner(total_laps: int = 5, seed: int = 0) -> RaceRunner:
    lineup = _make_tiny_lineup()
    return RaceRunner(
        race_id="2024_1",
        drivers=lineup,
        total_laps=total_laps,
        base_lap_time_ms=90_000,
        seed=seed,
    )


class TestRaceRunnerReset:
    def test_reset_returns_numpy_obs(self):
        runner = _make_runner()
        obs, info = runner.reset()
        assert isinstance(obs, np.ndarray)

    def test_reset_returns_info_dict(self):
        runner = _make_runner()
        obs, info = runner.reset()
        assert isinstance(info, dict)

    def test_reset_info_has_lap_number(self):
        runner = _make_runner()
        _, info = runner.reset()
        assert "lap_number" in info
        assert info["lap_number"] == 1

    def test_reset_not_finished(self):
        runner = _make_runner(total_laps=5)
        runner.reset()
        assert runner.finished is False

    def test_reset_clears_lap_data(self):
        runner = _make_runner(total_laps=2)
        runner.reset()
        runner.step_lap(int(Action.STAY_BALANCED))
        runner.reset()  # second reset should clear history
        assert runner.finished is False


class TestRaceRunnerStepLap:
    def test_step_lap_returns_tuple_of_three(self):
        runner = _make_runner()
        runner.reset()
        result = runner.step_lap(int(Action.STAY_BALANCED))
        assert len(result) == 3

    def test_step_lap_records_all_drivers(self):
        runner = _make_runner()
        runner.reset()
        lap_records, obs, info = runner.step_lap(int(Action.STAY_BALANCED))
        assert "test_user" in lap_records
        assert "rival" in lap_records

    def test_step_lap_lap_number_increments(self):
        runner = _make_runner(total_laps=5)
        runner.reset()
        runner.step_lap(int(Action.STAY_BALANCED))
        _, _, info = runner.step_lap(int(Action.STAY_BALANCED))
        assert info["lap_number"] == 3

    def test_lap_records_have_positive_lap_time(self):
        runner = _make_runner()
        runner.reset()
        lap_records, _, _ = runner.step_lap(int(Action.STAY_BALANCED))
        for rec in lap_records.values():
            assert rec.lap_time_ms > 0

    def test_pit_action_marks_pit_stop_true(self):
        runner = _make_runner(total_laps=10)
        runner.reset()
        # Run a few laps before pitting (need some tire age)
        for _ in range(3):
            runner.step_lap(int(Action.STAY_BALANCED))
        lap_records, _, _ = runner.step_lap(int(Action.PIT_HARD))
        user_rec = lap_records["test_user"]
        assert user_rec.pit_stop is True
        assert user_rec.new_compound == "HARD"

    def test_obs_is_numpy_array(self):
        runner = _make_runner()
        runner.reset()
        _, obs, _ = runner.step_lap(int(Action.STAY_BALANCED))
        assert isinstance(obs, np.ndarray)


class TestRaceRunnerFinished:
    def test_finished_false_before_last_lap(self):
        runner = _make_runner(total_laps=3)
        runner.reset()
        runner.step_lap(int(Action.STAY_BALANCED))
        assert runner.finished is False

    def test_finished_true_after_all_laps(self):
        runner = _make_runner(total_laps=3)
        runner.reset()
        for _ in range(3):
            runner.step_lap(int(Action.STAY_BALANCED))
        assert runner.finished is True


class TestRaceRunnerResult:
    def test_result_returns_race_result(self):
        runner = _make_runner(total_laps=3)
        runner.reset()
        for _ in range(3):
            runner.step_lap(int(Action.STAY_BALANCED))
        result = runner.result()
        assert isinstance(result, RaceResult)

    def test_result_has_all_drivers_in_standings(self):
        runner = _make_runner(total_laps=3)
        runner.reset()
        for _ in range(3):
            runner.step_lap(int(Action.STAY_BALANCED))
        result = runner.result()
        driver_ids = {s["driver_id"] for s in result.final_standings}
        assert "test_user" in driver_ids
        assert "rival" in driver_ids

    def test_result_lap_data_length_matches_total_laps(self):
        total = 5
        runner = _make_runner(total_laps=total)
        runner.reset()
        for _ in range(total):
            runner.step_lap(int(Action.STAY_BALANCED))
        result = runner.result()
        assert len(result.lap_data["test_user"]) == total

    def test_result_positions_are_valid(self):
        runner = _make_runner(total_laps=3)
        runner.reset()
        for _ in range(3):
            runner.step_lap(int(Action.STAY_BALANCED))
        result = runner.result()
        positions = [s["position"] for s in result.final_standings]
        assert sorted(positions) == list(range(1, len(positions) + 1))


class TestRunFullRace:
    def test_run_full_race_calls_action_fn(self):
        runner = _make_runner(total_laps=3)
        calls = []

        def action_fn(obs, info):
            calls.append(info["lap_number"])
            return int(Action.STAY_BALANCED)

        result = runner.run_full_race(action_fn)

        assert isinstance(result, RaceResult)
        assert len(calls) == 3  # once per lap

    def test_run_full_race_deterministic_with_same_seed(self):
        def stay(obs, info):
            return int(Action.STAY_BALANCED)

        r1 = _make_runner(total_laps=5, seed=42).run_full_race(stay)
        r2 = _make_runner(total_laps=5, seed=42).run_full_race(stay)

        assert r1.user_final_position == r2.user_final_position

    def test_run_full_race_user_position_within_range(self):
        runner = _make_runner(total_laps=5)

        result = runner.run_full_race(lambda obs, info: int(Action.STAY_BALANCED))

        n_drivers = 2
        assert 1 <= result.user_final_position <= n_drivers
