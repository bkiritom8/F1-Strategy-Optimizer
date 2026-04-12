"""
Unit tests for ml/rl/strategy_simulator.py — high-level race strategy simulation.

The RaceRunner and related simulation helpers are mocked so tests are fast and
do not require any GCS or ML model files.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from ml.rl.strategy_simulator import (
    StrategySimulator,
    SimulationOutput,
    StrategyVariant,
    _compound_to_action,
    _compute_risk,
    _laps_to_stints,
    _total_time,
)
from ml.rl.race_runner import LapRecord, RaceResult
from ml.rl.actions import Action


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_lap(
    lap_number: int,
    compound: str = "MEDIUM",
    pit_stop: bool = False,
    new_compound: str | None = None,
    position: int = 5,
    cumulative_time_ms: float = 0.0,
    driving_mode: str = "BALANCED",
) -> LapRecord:
    return LapRecord(
        driver_id="test_user",
        display_name="Test User",
        lap_number=lap_number,
        position=position,
        lap_time_ms=90_000.0 + lap_number * 100,
        tire_compound=compound,
        tire_age_laps=lap_number,
        fuel_remaining_kg=100.0,
        pit_stop=pit_stop,
        new_compound=new_compound,
        driving_mode=driving_mode,
        gap_to_leader=0.0,
        gap_to_ahead=0.0,
        safety_car=False,
        vsc=False,
        cumulative_time_ms=cumulative_time_ms,
    )


def _make_race_result(
    user_id: str = "test_user",
    laps: list | None = None,
    final_position: int = 5,
    total_laps: int = 10,
) -> RaceResult:
    if laps is None:
        laps = [_make_lap(i, cumulative_time_ms=i * 90_000.0) for i in range(1, total_laps + 1)]
    return RaceResult(
        race_id="2024_1",
        circuit_id="bahrain",
        total_laps=total_laps,
        user_driver_id=user_id,
        lap_data={user_id: laps, "rival": laps},
        final_standings=[{"position": final_position, "driver_id": user_id}],
        user_final_position=final_position,
        strategy_summary=[],
    )


# ── Unit tests for module-level helpers ────────────────────────────────────────


class TestCompoundToAction:
    def test_soft_maps_to_pit_soft(self):
        assert _compound_to_action("SOFT") == int(Action.PIT_SOFT)

    def test_medium_maps_to_pit_medium(self):
        assert _compound_to_action("MEDIUM") == int(Action.PIT_MEDIUM)

    def test_hard_maps_to_pit_hard(self):
        assert _compound_to_action("HARD") == int(Action.PIT_HARD)

    def test_inter_maps_to_pit_inter(self):
        assert _compound_to_action("INTER") == int(Action.PIT_INTER)

    def test_intermediate_maps_to_pit_inter(self):
        assert _compound_to_action("INTERMEDIATE") == int(Action.PIT_INTER)

    def test_unknown_defaults_to_medium(self):
        assert _compound_to_action("UNKNOWN") == int(Action.PIT_MEDIUM)

    def test_case_insensitive(self):
        assert _compound_to_action("soft") == int(Action.PIT_SOFT)


class TestLapsToStints:
    def test_empty_laps_returns_empty_list(self):
        assert _laps_to_stints([]) == []

    def test_no_pit_single_stint(self):
        laps = [_make_lap(i, compound="MEDIUM") for i in range(1, 6)]
        stints = _laps_to_stints(laps)
        assert len(stints) == 1
        assert stints[0].compound == "MEDIUM"
        assert stints[0].laps == 5

    def test_one_pit_produces_two_stints(self):
        laps = [_make_lap(i, compound="MEDIUM") for i in range(1, 4)]
        pit_lap = _make_lap(4, compound="MEDIUM", pit_stop=True, new_compound="HARD")
        laps.append(pit_lap)
        laps += [_make_lap(i, compound="HARD") for i in range(5, 8)]
        stints = _laps_to_stints(laps)
        assert len(stints) == 2
        assert stints[0].compound == "MEDIUM"
        assert stints[1].compound == "HARD"

    def test_modal_driving_mode_captured(self):
        laps = [
            _make_lap(1, driving_mode="PUSH"),
            _make_lap(2, driving_mode="PUSH"),
            _make_lap(3, driving_mode="BALANCED"),
        ]
        stints = _laps_to_stints(laps)
        assert stints[0].driving_mode == "PUSH"


class TestComputeRisk:
    def test_empty_laps_returns_medium(self):
        assert _compute_risk([]) == "MEDIUM"

    def test_consistent_positions_few_pits_low_risk(self):
        laps = [_make_lap(i, position=3) for i in range(1, 11)]
        risk = _compute_risk(laps)
        assert risk == "LOW"

    def test_many_pits_high_risk(self):
        laps = []
        for i in range(1, 11):
            pit = i in (5, 10, 15)
            laps.append(
                LapRecord(
                    driver_id="test",
                    display_name="",
                    lap_number=i,
                    position=5,
                    lap_time_ms=90_000.0,
                    tire_compound="SOFT",
                    tire_age_laps=i,
                    fuel_remaining_kg=50.0,
                    pit_stop=pit,
                    new_compound="MEDIUM" if pit else None,
                    driving_mode="PUSH",
                    gap_to_leader=0.0,
                    gap_to_ahead=0.0,
                    safety_car=False,
                    vsc=False,
                    cumulative_time_ms=float(i * 90_000),
                )
            )
        risk = _compute_risk(laps)
        assert risk in ("MEDIUM", "HIGH")


class TestTotalTime:
    def test_returns_last_lap_cumulative_time(self):
        laps = [_make_lap(i, cumulative_time_ms=float(i * 90_000)) for i in range(1, 6)]
        result = _make_race_result(laps=laps, total_laps=5)
        assert _total_time(result, "test_user") == pytest.approx(5 * 90_000.0)

    def test_returns_zero_for_missing_driver(self):
        result = _make_race_result()
        assert _total_time(result, "nonexistent") == 0.0


# ── StrategySimulator integration (mocked RaceRunner) ─────────────────────────


def _mock_run_race(sim, race_result):
    """Patch StrategySimulator._run_race to always return race_result."""
    sim._run_race = MagicMock(return_value=race_result)


class TestStrategySimulatorSimulate:
    def test_simulate_returns_simulation_output(self):
        sim = StrategySimulator()
        ref = _make_race_result(total_laps=10)
        _mock_run_race(sim, ref)

        output = sim.simulate(
            race_id="2024_1",
            user_driver_id="test_user",
            n_stochastic_runs=2,
        )

        assert isinstance(output, SimulationOutput)

    def test_simulate_returns_three_variants(self):
        sim = StrategySimulator()
        ref = _make_race_result(total_laps=10)
        _mock_run_race(sim, ref)

        output = sim.simulate(
            race_id="2024_1",
            user_driver_id="test_user",
            n_stochastic_runs=2,
        )

        assert len(output.variants) == 3

    def test_simulate_variant_names(self):
        sim = StrategySimulator()
        ref = _make_race_result(total_laps=10)
        _mock_run_race(sim, ref)

        output = sim.simulate(
            race_id="2024_1",
            user_driver_id="test_user",
            n_stochastic_runs=2,
        )

        names = [v.name for v in output.variants]
        assert any("OPTIMAL" in n for n in names)
        assert any("UNDERCUT" in n for n in names)
        assert any("CONSERVE" in n for n in names)

    def test_simulate_finishing_probabilities_sum_le_1(self):
        sim = StrategySimulator()
        ref = _make_race_result(total_laps=10)
        _mock_run_race(sim, ref)

        output = sim.simulate(
            race_id="2024_1",
            user_driver_id="test_user",
            n_stochastic_runs=4,
        )

        assert sum(output.finishing_probabilities) <= 1.0 + 1e-6

    def test_simulate_output_race_id_matches(self):
        sim = StrategySimulator()
        ref = _make_race_result(total_laps=10)
        _mock_run_race(sim, ref)

        output = sim.simulate(
            race_id="2024_1",
            user_driver_id="test_user",
            n_stochastic_runs=1,
        )

        assert output.race_id == "2024_1"
        assert output.user_driver_id == "test_user"

    def test_undercut_risk_is_high(self):
        sim = StrategySimulator()
        ref = _make_race_result(total_laps=10)
        _mock_run_race(sim, ref)

        output = sim.simulate(
            race_id="2024_1",
            user_driver_id="test_user",
            n_stochastic_runs=1,
        )

        undercut = next(v for v in output.variants if "UNDERCUT" in v.name)
        assert undercut.risk_level == "HIGH"

    def test_conserve_risk_is_low(self):
        sim = StrategySimulator()
        ref = _make_race_result(total_laps=10)
        _mock_run_race(sim, ref)

        output = sim.simulate(
            race_id="2024_1",
            user_driver_id="test_user",
            n_stochastic_runs=1,
        )

        conserve = next(v for v in output.variants if "CONSERVE" in v.name)
        assert conserve.risk_level == "LOW"

    def test_heuristic_action_without_agent(self):
        """_heuristic_action should not crash and returns valid action int."""
        sim = StrategySimulator()
        info = {
            "lap_number": 30,
            "total_laps": 57,
            "tire_age_laps": 15,
            "tire_compound": "MEDIUM",
            "pit_stops_count": 0,
            "safety_car": False,
        }
        action = sim._heuristic_action(info)
        assert isinstance(action, int)
