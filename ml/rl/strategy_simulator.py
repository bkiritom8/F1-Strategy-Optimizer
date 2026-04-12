"""
StrategySimulator — high-level race strategy simulation API.

Runs a full 20-driver race using RaceRunner and returns:
  - Three strategy variants for the user's driver (Optimal / Undercut / Conserve)
  - Full lap-by-lap data for all drivers
  - Final race standings
  - Finishing probability distribution (P1–P10) from n stochastic runs

Strategy variants match the UI layout:
  OPTIMAL N-STOP     — RL agent's chosen strategy (deterministic)
  AGGRESSIVE UNDERCUT — forced early pit onto SOFT, then HARD
  CONSERVE 1-STOP    — single pit at ~55 % race distance, MEDIUM → HARD

Usage:
    from ml.rl.model_adapters import load_local_adapters
    from ml.rl.driver_profiles import build_race_lineup

    adapters = load_local_adapters("models/")
    sim      = StrategySimulator(adapters=adapters)
    sim.load_agent("gs://f1optimizer-models/rl_strategy/latest")

    output = sim.simulate(
        race_id        = "2024_1",
        user_driver_id = "lando_norris",
        driver_profile = {"aggression": 0.79, "consistency": 0.84,
                          "tire_management": 0.76, "pressure_response": 0.76},
        rivals         = ["max_verstappen", "lewis_hamilton", ...],
    )

    for v in output.variants:
        print(v.name, v.predicted_position, v.risk_level)
    print(output.final_standings)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:
    from ml.rl.agent import F1StrategyAgent

import numpy as np

from ml.rl.actions import Action, decode
from ml.rl.driver_profiles import build_race_lineup, get_profile
from ml.rl.race_runner import LapRecord, RaceResult, RaceRunner, _extract_stints
from ml.rl.reward import COMPOUND_OPTIMAL_LAPS

logger = logging.getLogger(__name__)

_PROJECT_DEFAULT = "f1optimizer"


# ── Output types ──────────────────────────────────────────────────────────────


@dataclass
class StintPlan:
    compound: str
    laps: int
    driving_mode: str  # PUSH / BALANCED / NEUTRAL


@dataclass
class StrategyVariant:
    name: str  # "OPTIMAL 2-STOP" / "AGGRESSIVE UNDERCUT" / "CONSERVE 1-STOP"
    stint_plan: list[StintPlan]
    pit_laps: list[int]
    win_probability: float
    podium_probability: float
    risk_level: str  # LOW / MEDIUM / HIGH
    estimated_total_time_s: float
    predicted_position: int
    fuel_load_start_kg: float = 110.0


@dataclass
class SimulationOutput:
    """Complete output from StrategySimulator.simulate()."""

    race_id: str
    user_driver_id: str
    circuit_id: str
    total_laps: int
    variants: list[StrategyVariant]
    finishing_probabilities: list[float]  # P(finish P1)…P(finish P10)
    # Full race data from the optimal run
    final_standings: list[dict]
    lap_data: dict[str, list[LapRecord]]  # driver_id → laps
    strategy_summary: list[dict]  # per-driver stints


# ── Simulator ─────────────────────────────────────────────────────────────────


class StrategySimulator:
    """
    Runs full 20-driver races using RaceRunner to produce strategy variants.

    All ML adapters are forwarded to each RaceRunner instance created.
    Any unloaded adapter falls back to physics constants automatically.
    """

    def __init__(
        self,
        project: str = _PROJECT_DEFAULT,
        adapters: Optional[dict] = None,
    ) -> None:
        self._project = project
        self._adapters = adapters or {}
        self._agent: Optional["F1StrategyAgent"] = None

    def load_agent(self, gcs_uri: str) -> None:
        """Load a trained F1StrategyAgent from GCS."""
        from ml.rl.agent import F1StrategyAgent

        self._agent = F1StrategyAgent(project=self._project)
        self._agent.load(gcs_uri)
        logger.info("Agent loaded from %s", gcs_uri)

    # ── Main entry point ──────────────────────────────────────────────────────

    def simulate(
        self,
        race_id: str,
        user_driver_id: str,
        driver_profile: Optional[dict] = None,
        rivals: Optional[list[str]] = None,
        start_position: int = 10,
        start_compound: str = "MEDIUM",
        n_stochastic_runs: int = 6,
    ) -> SimulationOutput:
        """
        Simulate a full race and return three strategy options.

        Args:
            race_id:           e.g. "2024_1"
            user_driver_id:    e.g. "lando_norris"
            driver_profile:    aggression/consistency/tire_management/pressure_response
            rivals:            List of rival driver IDs (None = DEFAULT_GRID minus user)
            start_position:    Grid slot 1–20
            start_compound:    Starting tire
            n_stochastic_runs: Episodes to estimate win/podium probability

        Returns:
            SimulationOutput with 3 variants, full lap data, standings
        """
        profile = driver_profile or get_profile(user_driver_id)

        # ── Deterministic optimal run ──────────────────────────────────────
        optimal_result = self._run_race(
            race_id,
            user_driver_id,
            profile,
            rivals,
            start_position,
            start_compound,
            strategy_override=None,
            seed=42,
        )

        # ── Stochastic runs for probability distribution ───────────────────
        position_counts = [0] * 21
        for seed in range(n_stochastic_runs):
            r = self._run_race(
                race_id,
                user_driver_id,
                profile,
                rivals,
                start_position,
                start_compound,
                seed=seed,
            )
            pos = max(1, min(r.user_final_position, 20))
            position_counts[pos] += 1

        finishing_probs = [
            position_counts[p] / max(n_stochastic_runs, 1) for p in range(1, 11)
        ]
        win_prob = finishing_probs[0]
        podium_prob = sum(finishing_probs[:3])

        # ── Build three strategy variants ──────────────────────────────────
        optimal_variant = self._build_optimal_variant(
            optimal_result, win_prob, podium_prob
        )

        undercut_result = self._run_race(
            race_id,
            user_driver_id,
            profile,
            rivals,
            start_position,
            start_compound,
            strategy_override=self._undercut_override(optimal_result),
            seed=10,
        )
        undercut_variant = self._build_undercut_variant(undercut_result, win_prob)

        conserve_result = self._run_race(
            race_id,
            user_driver_id,
            profile,
            rivals,
            start_position,
            start_compound,
            strategy_override=self._conserve_override(optimal_result),
            seed=20,
        )
        conserve_variant = self._build_conserve_variant(conserve_result, win_prob)

        return SimulationOutput(
            race_id=race_id,
            user_driver_id=user_driver_id,
            circuit_id=optimal_result.circuit_id,
            total_laps=optimal_result.total_laps,
            variants=[optimal_variant, undercut_variant, conserve_variant],
            finishing_probabilities=finishing_probs,
            final_standings=optimal_result.final_standings,
            lap_data=optimal_result.lap_data,
            strategy_summary=optimal_result.strategy_summary,
        )

    # ── Race runner ───────────────────────────────────────────────────────────

    def _run_race(
        self,
        race_id: str,
        user_driver_id: str,
        driver_profile: dict,
        rivals: Optional[list[str]],
        start_position: int,
        start_compound: str,
        strategy_override: Optional[list[tuple[int, str]]] = None,
        seed: int = 0,
    ) -> RaceResult:
        """Run one full race and return the RaceResult."""
        lineup = build_race_lineup(
            user_driver_id=user_driver_id,
            user_profile=driver_profile,
            user_start_position=start_position,
            user_start_compound=start_compound,
            rivals=rivals,
        )

        runner = RaceRunner(
            race_id=race_id,
            drivers=lineup,
            adapters=self._adapters,
            project=self._project,
            seed=seed,
        )

        forced_pits: dict[int, str] = (
            {lap: cmp for lap, cmp in strategy_override} if strategy_override else {}
        )

        def action_fn(obs: np.ndarray, info: dict) -> int:
            lap = info.get("lap_number", 1)
            if lap in forced_pits:
                return _compound_to_action(forced_pits[lap])
            if self._agent is not None:
                return self._agent.predict(obs, deterministic=True)
            return (
                int(self._heuristic_action(info))
                if not forced_pits
                else int(Action.STAY_BALANCED)
            )

        return runner.run_full_race(action_fn)

    # ── Heuristic fallback ────────────────────────────────────────────────────

    def _heuristic_action(self, info: dict) -> int:
        lap = info.get("lap_number", 1)
        total = max(info.get("total_laps", 60), 1)
        tire_age = info.get("tire_age_laps", 0)
        compound = info.get("tire_compound", "MEDIUM").upper()
        pit_count = info.get("pit_stops_count", 0)
        laps_pct = lap / total
        optimal = COMPOUND_OPTIMAL_LAPS.get(compound, 30)

        if info.get("safety_car") and tire_age > 10:
            return int(Action.PIT_MEDIUM)
        if tire_age >= int(optimal * 1.2):
            return int(Action.PIT_HARD if laps_pct < 0.65 else Action.PIT_SOFT)
        if pit_count == 0 and 0.38 <= laps_pct <= 0.48:
            return int(Action.PIT_MEDIUM)
        if pit_count == 1 and 0.68 <= laps_pct <= 0.78:
            return int(Action.PIT_HARD)
        return int(Action.STAY_BALANCED)

    # ── Strategy overrides ────────────────────────────────────────────────────

    def _undercut_override(self, reference: RaceResult) -> list[tuple[int, str]]:
        """Pit 4 laps earlier than optimal → SOFT, then HARD."""
        total = reference.total_laps
        user_laps = reference.lap_data.get(reference.user_driver_id, [])
        pit_laps = [r.lap_number for r in user_laps if r.pit_stop]
        if pit_laps:
            early = max(2, pit_laps[0] - 4)
            second = min(early + 22, total - 6)
            return [(early, "SOFT"), (second, "HARD")]
        return [(int(total * 0.36), "SOFT"), (int(total * 0.62), "HARD")]

    def _conserve_override(self, reference: RaceResult) -> list[tuple[int, str]]:
        """Single pit at ~55 % race distance, MEDIUM → HARD."""
        total = reference.total_laps
        pit_lap = int(total * 0.55)
        return [(pit_lap, "HARD")]

    # ── Variant builders ──────────────────────────────────────────────────────

    def _build_optimal_variant(
        self,
        result: RaceResult,
        win_prob: float,
        podium_prob: float,
    ) -> StrategyVariant:
        user_laps = result.lap_data.get(result.user_driver_id, [])
        stint_plan = _laps_to_stints(user_laps)
        n_stops = sum(1 for r in user_laps if r.pit_stop)
        pit_laps = [r.lap_number for r in user_laps if r.pit_stop]
        risk = _compute_risk(user_laps)

        return StrategyVariant(
            name=f"OPTIMAL {n_stops + 1}-STOP",
            stint_plan=stint_plan,
            pit_laps=pit_laps,
            win_probability=round(win_prob, 3),
            podium_probability=round(podium_prob, 3),
            risk_level=risk,
            estimated_total_time_s=round(
                _total_time(result, result.user_driver_id) / 1000.0, 1
            ),
            predicted_position=result.user_final_position,
        )

    def _build_undercut_variant(
        self, result: RaceResult, base_win: float
    ) -> StrategyVariant:
        user_laps = result.lap_data.get(result.user_driver_id, [])
        stint_plan = _laps_to_stints(user_laps)
        pit_laps = [r.lap_number for r in user_laps if r.pit_stop]
        return StrategyVariant(
            name="AGGRESSIVE UNDERCUT",
            stint_plan=stint_plan,
            pit_laps=pit_laps,
            win_probability=round(min(1.0, base_win * 1.4), 3),
            podium_probability=round(min(1.0, base_win * 2.2), 3),
            risk_level="HIGH",
            estimated_total_time_s=round(
                _total_time(result, result.user_driver_id) / 1000.0, 1
            ),
            predicted_position=result.user_final_position,
        )

    def _build_conserve_variant(
        self, result: RaceResult, base_win: float
    ) -> StrategyVariant:
        user_laps = result.lap_data.get(result.user_driver_id, [])
        stint_plan = _laps_to_stints(user_laps)
        pit_laps = [r.lap_number for r in user_laps if r.pit_stop]
        return StrategyVariant(
            name="CONSERVE 1-STOP",
            stint_plan=stint_plan,
            pit_laps=pit_laps,
            win_probability=round(max(0.0, base_win * 0.55), 3),
            podium_probability=round(max(0.0, base_win * 1.15), 3),
            risk_level="LOW",
            estimated_total_time_s=round(
                _total_time(result, result.user_driver_id) / 1000.0, 1
            ),
            predicted_position=result.user_final_position,
        )


# ── Module-level helpers ──────────────────────────────────────────────────────


def _compound_to_action(compound: str) -> int:
    return int(
        {
            "SOFT": Action.PIT_SOFT,
            "MEDIUM": Action.PIT_MEDIUM,
            "HARD": Action.PIT_HARD,
            "INTER": Action.PIT_INTER,
            "INTERMEDIATE": Action.PIT_INTER,
        }.get(compound.upper(), Action.PIT_MEDIUM)
    )


def _laps_to_stints(laps: list[LapRecord]) -> list[StintPlan]:
    """Convert lap records to a list of StintPlan entries."""
    if not laps:
        return []
    stints: list[StintPlan] = []
    current_compound = laps[0].tire_compound
    stint_start = laps[0].lap_number
    modes: list[str] = []

    for rec in laps:
        modes.append(rec.driving_mode)
        if rec.pit_stop and rec.new_compound:
            laps_in_stint = rec.lap_number - stint_start
            modal_mode = max(set(modes), key=modes.count) if modes else "BALANCED"
            stints.append(StintPlan(current_compound, laps_in_stint, modal_mode))
            current_compound = rec.new_compound
            stint_start = rec.lap_number
            modes = []

    last_laps = laps[-1].lap_number - stint_start + 1
    modal_mode = max(set(modes), key=modes.count) if modes else "BALANCED"
    stints.append(StintPlan(current_compound, last_laps, modal_mode))
    return stints


def _compute_risk(laps: list[LapRecord]) -> str:
    if not laps:
        return "MEDIUM"
    positions = [r.position for r in laps]
    n_pits = sum(1 for r in laps if r.pit_stop)
    pos_std = float(np.std(positions)) if len(positions) > 1 else 0.0
    if pos_std > 3.5 or n_pits >= 3:
        return "HIGH"
    if pos_std < 1.5 and n_pits <= 1:
        return "LOW"
    return "MEDIUM"


def _total_time(result: RaceResult, driver_id: str) -> float:
    laps = result.lap_data.get(driver_id, [])
    return laps[-1].cumulative_time_ms if laps else 0.0
