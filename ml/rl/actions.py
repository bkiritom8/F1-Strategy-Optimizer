"""
Action space for the F1 RL environment.

7 discrete actions combining pit/stay decision with driving mode:

  0  STAY_NEUTRAL   — stay out, neutral throttle (conserve tires/fuel)
  1  STAY_BALANCED  — stay out, balanced pace
  2  STAY_PUSH      — stay out, push hard (fastest lap times, more tire wear)
  3  PIT_SOFT       — pit stop → SOFT compound
  4  PIT_MEDIUM     — pit stop → MEDIUM compound
  5  PIT_HARD       — pit stop → HARD compound
  6  PIT_INTER      — pit stop → INTERMEDIATE (wet conditions only)

Driving mode aligns with preprocessing driving_style encoding:
  NEUTRAL = 0, BALANCED = 1, PUSH = 2
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Optional


class Action(IntEnum):
    STAY_NEUTRAL = 0
    STAY_BALANCED = 1
    STAY_PUSH = 2
    PIT_SOFT = 3
    PIT_MEDIUM = 4
    PIT_HARD = 5
    PIT_INTER = 6


N_ACTIONS = len(Action)

# Driving mode label per action
DRIVING_MODES: dict[Action, str] = {
    Action.STAY_NEUTRAL: "NEUTRAL",
    Action.STAY_BALANCED: "BALANCED",
    Action.STAY_PUSH: "PUSH",
    Action.PIT_SOFT: "BALANCED",   # default mode after pitting onto soft
    Action.PIT_MEDIUM: "BALANCED",
    Action.PIT_HARD: "NEUTRAL",    # conserve on hard tires
    Action.PIT_INTER: "NEUTRAL",
}

# Integer encoding (matches preprocess_data.py driving_style column)
DRIVING_STYLE_INT: dict[str, int] = {
    "NEUTRAL": 0,
    "BALANCED": 1,
    "PUSH": 2,
}

# Compound selected when pitting (None = stay out)
PIT_COMPOUND: dict[Action, Optional[str]] = {
    Action.STAY_NEUTRAL: None,
    Action.STAY_BALANCED: None,
    Action.STAY_PUSH: None,
    Action.PIT_SOFT: "SOFT",
    Action.PIT_MEDIUM: "MEDIUM",
    Action.PIT_HARD: "HARD",
    Action.PIT_INTER: "INTER",
}


@dataclass
class DecodedAction:
    """Human-readable action with all semantic fields."""

    raw: int
    is_pit: bool
    new_compound: Optional[str]  # None if staying out
    driving_mode: str            # NEUTRAL / BALANCED / PUSH
    driving_style_int: int       # 0 / 1 / 2


def decode(action: int) -> DecodedAction:
    """Convert integer action to a DecodedAction."""
    a = Action(action)
    compound = PIT_COMPOUND[a]
    mode = DRIVING_MODES[a]
    return DecodedAction(
        raw=action,
        is_pit=compound is not None,
        new_compound=compound,
        driving_mode=mode,
        driving_style_int=DRIVING_STYLE_INT[mode],
    )


def is_valid_pit(action: int, weather: str, current_compound: str) -> bool:
    """
    Returns False for contextually invalid actions:
      - PIT_INTER when weather is dry
      - Slick compounds when weather is wet
    """
    a = Action(action)
    compound = PIT_COMPOUND[a]
    if compound is None:
        return True  # stay-out always valid
    if compound == "INTER" and weather == "dry":
        return False
    if compound in ("SOFT", "MEDIUM", "HARD") and weather in ("wet", "intermediate"):
        return False
    return True