"""
F1RaceEnv — Gymnasium environment for F1 race strategy optimization.

Each episode is a full F1 race where:
  - The agent controls one driver against 19 AI rivals
  - AI rivals run autonomous profile-aware strategies (see race_runner.py)
  - ML adapters power tire degradation, fuel consumption, and safety car models
  - Physics fallbacks are used for any unloaded model

Observation:  Box(−2, 2, shape=(STATE_DIM=29,), float32)  — see state.py
Action:       Discrete(7)                                  — see actions.py
Reward:       per-lap + terminal from RewardFunction       — see reward.py

Usage (physics-only):
    env = F1RaceEnv(race_ids=["2024_1"], driver_id="max_verstappen")

Usage (with all 4 trained models):
    from ml.rl.model_adapters import load_local_adapters
    from ml.rl.driver_profiles import build_race_lineup

    adapters = load_local_adapters("models/")
    lineup   = build_race_lineup("max_verstappen", start_position=1)
    env      = F1RaceEnv(race_ids=["2024_1"], driver_id="max_verstappen",
                         adapters=adapters, lineup=lineup)
"""

from __future__ import annotations

import logging
import random
from typing import Any, Optional

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from ml.rl.actions import N_ACTIONS
from ml.rl.driver_profiles import build_race_lineup, get_profile, DriverEntry
from ml.rl.race_runner import RaceRunner
from ml.rl.reward import RewardFunction
from ml.rl.state import STATE_DIM

logger = logging.getLogger(__name__)


class F1RaceEnv(gym.Env):
    """
    Gymnasium environment for single-driver F1 race strategy.

    The agent competes against 19 AI rivals whose strategies are driven by
    their driver profiles (aggression, consistency, tire_management,
    pressure_response). All lap physics use ML adapters when loaded.

    Args:
        race_ids:         List of race_ids to sample from on reset().
                          Pass None/[] to use a synthetic mock race.
        driver_id:        Ergast driverRef the agent controls
                          (e.g. "max_verstappen").
        driver_profile:   Dict with float [0,1] keys: aggression, consistency,
                          tire_management, pressure_response.
                          If None, loaded from DRIVER_PROFILES or generic.
        adapters:         Dict of model adapters from
                          model_adapters.load_local_adapters().
        lineup:           Pre-built list[DriverEntry] for the race. If None,
                          build_race_lineup() is called automatically each reset.
        start_position:   Grid slot for user's driver (1-20).
        start_compound:   Starting tire (SOFT/MEDIUM/HARD).
        rivals:           Explicit list of rival driver IDs. None = DEFAULT_GRID.
        project:          GCP project ID.
        seed:             Random seed.
    """

    metadata = {"render_modes": ["human"]}

    def __init__(
        self,
        race_ids: Optional[list[str]] = None,
        driver_id: Optional[str] = None,
        driver_profile: Optional[dict] = None,
        adapters: Optional[dict] = None,
        lineup: Optional[list[DriverEntry]] = None,
        start_position: int = 10,
        start_compound: str = "MEDIUM",
        rivals: Optional[list[str]] = None,
        project: str = "f1optimizer",
        seed: Optional[int] = None,
        # Legacy params (ignored — kept for backward compat)
        tire_deg_model=None,
        fuel_model=None,
        overtake_model=None,
        sc_model=None,
    ) -> None:
        super().__init__()

        self._race_ids = race_ids or []
        self._driver_id = driver_id or "agent_driver"
        self._driver_profile = driver_profile or get_profile(self._driver_id)
        self._adapters = adapters or {}
        self._fixed_lineup = lineup
        self._start_position = start_position
        self._start_compound = start_compound
        self._rivals = rivals
        self._project = project
        self._rng_seed = seed

        self.observation_space = spaces.Box(
            low=np.full(STATE_DIM, -2.0, dtype=np.float32),
            high=np.full(STATE_DIM, 2.0, dtype=np.float32),
            dtype=np.float32,
        )
        self.action_space = spaces.Discrete(N_ACTIONS)

        self._runner: Optional[RaceRunner] = None
        self._reward_fn = RewardFunction()
        self._prev_position: int = start_position

    # ── Gymnasium interface ────────────────────────────────────────────────────

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[dict] = None,
    ) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)

        race_id = random.choice(self._race_ids) if self._race_ids else "mock"

        if self._fixed_lineup is not None:
            lineup = self._fixed_lineup
        else:
            lineup = build_race_lineup(
                user_driver_id=self._driver_id,
                user_profile=self._driver_profile,
                user_start_position=self._start_position,
                user_start_compound=self._start_compound,
                rivals=self._rivals,
            )

        self._runner = RaceRunner(
            race_id=race_id,
            drivers=lineup,
            adapters=self._adapters,
            project=self._project,
            seed=seed or self._rng_seed,
        )
        self._reward_fn.reset()

        obs, info = self._runner.reset()
        self._prev_position = info.get("position", self._start_position)
        return obs, info

    def step(self, action: int) -> tuple[np.ndarray, float, bool, bool, dict]:
        if self._runner is None:
            raise RuntimeError("Call reset() before step().")

        lap_records, obs, info = self._runner.step_lap(action)

        pitted = (
            lap_records[self._driver_id].pit_stop
            if self._driver_id in lap_records
            else False
        )
        new_position = info.get("position", self._prev_position)

        r = self._reward_fn.step(
            prev_position=self._prev_position,
            new_position=new_position,
            lap_time_ms=info.get("lap_time_ms", 95_000.0),
            tire_compound=info.get("tire_compound", "MEDIUM"),
            tire_age_laps=info.get("tire_age_laps", 0),
            pitted=pitted,
            safety_car_active=info.get("safety_car", False),
        )
        self._prev_position = new_position
        reward = float(r.total)
        terminated = self._runner.finished

        if terminated:
            reward += float(self._reward_fn.terminal(new_position).total)

        info["reward_components"] = r
        info["all_lap_records"] = lap_records
        return obs, reward, terminated, False, info

    def render(self) -> None:
        if self._runner is None:
            return
        info = self._runner._user_info()
        print(
            f"Lap {info.get('lap_number')}/{info.get('total_laps')} | "
            f"P{info.get('position')} | "
            f"{info.get('tire_compound')} age={info.get('tire_age_laps')} | "
            f"Fuel={info.get('fuel_remaining_kg'):.1f} kg | "
            f"Mode={info.get('driving_mode')} | SC={info.get('safety_car')} | "
            f"Lap={info.get('lap_time_ms', 0)/1000:.3f} s"
        )

    def get_race_result(self):
        """Return full RaceResult after episode ends. Call after terminated=True."""
        if self._runner is None:
            return None
        return self._runner.result()
