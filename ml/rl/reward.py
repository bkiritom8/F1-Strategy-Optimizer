"""
RewardFunction — per-lap and terminal reward for the F1 RL agent.

Reward components
─────────────────
position_gain      +5.0 per position gained this lap; -3.0 per position lost
lap_time_bonus     deviation from an exponential moving average baseline
                   (±1 s relative → ±0.5 reward)
tire_overstay      −0.3 per lap past 110 % of compound's optimal stint
pit_cost           −2.0 flat (offset toward 0 if tire was already overdue)
sc_pit_bonus       +8.0 bonus for pitting under safety car (free pit window)
finish_reward      terminal only — large reward based on final position
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# Optimal stint length per compound (laps)
COMPOUND_OPTIMAL_LAPS: dict[str, int] = {
    "SOFT": 20,
    "MEDIUM": 30,
    "HARD": 45,
    "INTER": 25,
    "WET": 20,
}

POS_GAIN_REWARD = 5.0
POS_LOSS_PENALTY = 3.0
PIT_BASE_COST = 2.0
SC_PIT_BONUS = 8.0

# P1–P10 terminal rewards; any position worse than 10 = −2
_FINISH_REWARDS: dict[int, float] = {
    1: 50.0, 2: 30.0, 3: 20.0, 4: 12.0, 5: 8.0,
    6: 5.0,  7: 3.0,  8: 2.0,  9: 1.0, 10: 0.0,
}


@dataclass
class RewardComponents:
    position_gain: float = 0.0
    lap_time_bonus: float = 0.0
    tire_overstay: float = 0.0
    pit_cost: float = 0.0
    sc_pit_bonus: float = 0.0
    finish_reward: float = 0.0

    @property
    def total(self) -> float:
        return (
            self.position_gain
            + self.lap_time_bonus
            + self.tire_overstay
            + self.pit_cost
            + self.sc_pit_bonus
            + self.finish_reward
        )

    def __repr__(self) -> str:
        return (
            f"RewardComponents(total={self.total:.3f}, "
            f"pos={self.position_gain:.2f}, "
            f"lap_time={self.lap_time_bonus:.2f}, "
            f"overstay={self.tire_overstay:.2f}, "
            f"pit={self.pit_cost:.2f}, "
            f"sc_pit={self.sc_pit_bonus:.2f}, "
            f"finish={self.finish_reward:.2f})"
        )


class RewardFunction:
    """
    Computes per-step and terminal reward for one driver's episode.

    Call reset() at the start of each episode.
    Call step() each lap. Call terminal() at the final lap.
    """

    def __init__(self) -> None:
        self._lap_time_ema: Optional[float] = None

    def reset(self) -> None:
        self._lap_time_ema = None

    def step(
        self,
        prev_position: int,
        new_position: int,
        lap_time_ms: float,
        tire_compound: str,
        tire_age_laps: int,
        pitted: bool,
        safety_car_active: bool,
    ) -> RewardComponents:
        """Compute reward for one lap transition."""
        r = RewardComponents()

        # ── Position change ────────────────────────────────────────────────────
        pos_delta = prev_position - new_position  # positive = gained positions
        if pos_delta > 0:
            r.position_gain = POS_GAIN_REWARD * pos_delta
        elif pos_delta < 0:
            r.position_gain = -POS_LOSS_PENALTY * abs(pos_delta)

        # ── Lap time vs EMA baseline ───────────────────────────────────────────
        if lap_time_ms > 0:
            if self._lap_time_ema is None:
                self._lap_time_ema = lap_time_ms
            else:
                self._lap_time_ema = 0.9 * self._lap_time_ema + 0.1 * lap_time_ms
            delta_s = (lap_time_ms - self._lap_time_ema) / 1000.0
            r.lap_time_bonus = -0.5 * delta_s  # faster than baseline → positive

        # ── Tire overstay penalty ──────────────────────────────────────────────
        compound = tire_compound.upper() if tire_compound else "MEDIUM"
        optimal = COMPOUND_OPTIMAL_LAPS.get(compound, 30)
        threshold = optimal * 1.1
        if tire_age_laps > threshold:
            r.tire_overstay = -0.3 * (tire_age_laps - threshold)

        # ── Pit cost ──────────────────────────────────────────────────────────
        if pitted:
            if tire_age_laps >= optimal:
                r.pit_cost = -0.5   # tire was due — almost free
            else:
                r.pit_cost = -PIT_BASE_COST

        # ── Safety car pit bonus ──────────────────────────────────────────────
        if pitted and safety_car_active:
            r.sc_pit_bonus = SC_PIT_BONUS

        return r

    def terminal(self, final_position: int) -> RewardComponents:
        """Compute terminal reward at the end of the race."""
        r = RewardComponents()
        r.finish_reward = _FINISH_REWARDS.get(final_position, -2.0)
        return r