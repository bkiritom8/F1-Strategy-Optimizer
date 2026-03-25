"""
StateEncoder — converts per-lap race state into a fixed-size numpy observation.

Vector layout (STATE_DIM = 29):

  Lap progress
  [0]  lap_progress          lap_number / total_laps
  [1]  laps_remaining_frac   laps_remaining / total_laps

  Tire & fuel
  [2]  tire_age_norm         tire_age_laps / 50
  [3]  fuel_norm             fuel_remaining_kg / 110

  Compound one-hot (SOFT / MEDIUM / HARD / INTER / WET)
  [4]  compound_soft
  [5]  compound_medium
  [6]  compound_hard
  [7]  compound_inter
  [8]  compound_wet

  Race position
  [9]  position_norm         position / 20
  [10] gap_leader_norm       gap_to_leader / 120   (seconds, capped)
  [11] gap_ahead_norm        gap_to_ahead / 30

  Lap time signals
  [12] lap_time_norm         lap_time_ms / 120_000
  [13] lap_time_delta_norm   Δlap_time_ms / 5_000  (clipped [-1, 1])

  Sector times
  [14] sector1_norm          sector1_time_ms / 40_000
  [15] sector2_norm          sector2_time_ms / 40_000
  [16] sector3_norm          sector3_time_ms / 40_000

  Race context
  [17] pit_stops_norm        pit_stops_count / 4
  [18] safety_car            0 / 1
  [19] vsc                   0 / 1
  [20] is_wet                0 / 1
  [21] track_temp_norm       track_temp / 60

  Driver profile embedding (all [0, 1])
  [22] aggression
  [23] consistency
  [24] tire_management
  [25] pressure_response

  Recent lap time deltas (last 3 laps, clipped [-1, 1])
  [26] delta_lag1
  [27] delta_lag2
  [28] delta_lag3
"""

from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

STATE_DIM = 29

_COMPOUND_IDX: dict[str, int] = {
    "SOFT": 4,
    "MEDIUM": 5,
    "HARD": 6,
    "INTER": 7,
    "INTERMEDIATE": 7,
    "WET": 8,
}

_PROFILE_KEYS = ("aggression", "consistency", "tire_management", "pressure_response")


class StateEncoder:
    """
    Encodes the current lap state for one driver into a (STATE_DIM,) float32 vector.

    Call reset() at the start of each episode to clear rolling history.
    Call encode() each lap to produce the observation passed to the agent.
    """

    def __init__(self, driver_profile: Optional[dict] = None) -> None:
        self._profile = _normalize_profile(driver_profile or {})
        self._delta_history: deque[float] = deque([0.0, 0.0, 0.0], maxlen=3)
        self._last_lap_time_ms: float = 0.0

    def reset(self, driver_profile: Optional[dict] = None) -> None:
        """Reset history buffers. Optionally update driver profile."""
        if driver_profile is not None:
            self._profile = _normalize_profile(driver_profile)
        self._delta_history = deque([0.0, 0.0, 0.0], maxlen=3)
        self._last_lap_time_ms = 0.0

    def encode(
        self,
        lap_number: int,
        total_laps: int,
        tire_age_laps: int,
        fuel_remaining_kg: float,
        tire_compound: str,
        position: int,
        gap_to_leader: float,
        gap_to_ahead: float,
        lap_time_ms: float,
        pit_stops_count: int,
        safety_car: bool = False,
        vsc: bool = False,
        weather: str = "dry",
        track_temp: float = 35.0,
        sector1_time_ms: float = 0.0,
        sector2_time_ms: float = 0.0,
        sector3_time_ms: float = 0.0,
    ) -> np.ndarray:
        """Return a (STATE_DIM,) float32 observation vector."""
        obs = np.zeros(STATE_DIM, dtype=np.float32)
        total = max(total_laps, 1)

        # Lap progress
        obs[0] = lap_number / total
        obs[1] = max(0.0, total - lap_number) / total

        # Tire & fuel
        obs[2] = float(np.clip(tire_age_laps / 50.0, 0.0, 1.0))
        obs[3] = float(np.clip(fuel_remaining_kg / 110.0, 0.0, 1.0))

        # Compound one-hot
        key = tire_compound.upper() if tire_compound else "MEDIUM"
        obs[_COMPOUND_IDX.get(key, 5)] = 1.0

        # Race position
        obs[9] = float(np.clip(position / 20.0, 0.0, 1.0))
        obs[10] = float(np.clip(gap_to_leader / 120.0, 0.0, 1.0))
        obs[11] = float(np.clip(gap_to_ahead / 30.0, 0.0, 1.0))

        # Lap time
        obs[12] = float(np.clip(lap_time_ms / 120_000.0, 0.0, 1.0))

        # Lap time delta vs previous lap
        if self._last_lap_time_ms > 0 and lap_time_ms > 0:
            delta_ms = lap_time_ms - self._last_lap_time_ms
        else:
            delta_ms = 0.0
        self._delta_history.append(delta_ms)
        if lap_time_ms > 0:
            self._last_lap_time_ms = lap_time_ms
        obs[13] = float(np.clip(delta_ms / 5_000.0, -1.0, 1.0))

        # Sector times
        if sector1_time_ms > 0:
            obs[14] = float(np.clip(sector1_time_ms / 40_000.0, 0.0, 1.0))
        if sector2_time_ms > 0:
            obs[15] = float(np.clip(sector2_time_ms / 40_000.0, 0.0, 1.0))
        if sector3_time_ms > 0:
            obs[16] = float(np.clip(sector3_time_ms / 40_000.0, 0.0, 1.0))

        # Race context
        obs[17] = float(np.clip(pit_stops_count / 4.0, 0.0, 1.0))
        obs[18] = float(safety_car)
        obs[19] = float(vsc)
        obs[20] = 1.0 if weather in ("wet", "intermediate") else 0.0
        obs[21] = float(np.clip(track_temp / 60.0, 0.0, 1.0))

        # Driver profile
        obs[22] = self._profile["aggression"]
        obs[23] = self._profile["consistency"]
        obs[24] = self._profile["tire_management"]
        obs[25] = self._profile["pressure_response"]

        # Rolling lap time deltas (oldest → newest in [26, 27, 28])
        history = list(self._delta_history)
        obs[26] = float(np.clip(history[0] / 5_000.0, -1.0, 1.0))
        obs[27] = float(np.clip(history[1] / 5_000.0, -1.0, 1.0))
        obs[28] = float(np.clip(history[2] / 5_000.0, -1.0, 1.0))

        return obs


def _normalize_profile(profile: dict) -> dict:
    """Ensure all driver profile keys are present and clamped to [0, 1]."""
    out: dict[str, float] = {}
    for key in _PROFILE_KEYS:
        out[key] = float(np.clip(profile.get(key, 0.5), 0.0, 1.0))
    return out
