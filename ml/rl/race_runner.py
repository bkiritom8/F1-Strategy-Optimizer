"""
RaceRunner — modular multi-driver F1 race simulation engine.

Simulates a full F1 race where:
  - One driver is controlled by the RL agent / user (is_user=True)
  - All other drivers run autonomous profile-aware strategies
  - Lap times evolve from tire degradation, fuel load, driving mode,
    safety car, and each driver's profile characteristics
  - ML model adapters are used when loaded; physics fallbacks otherwise

Core loop (each lap):
  1. RL agent provides action for user's driver
  2. Each AI driver decides action via _ai_action() (profile + race state)
  3. _simulate_driver_lap() computes lap time + fuel for every driver
  4. Positions updated from cumulative race times
  5. Safety car checked stochastically (circuit-calibrated)

Usage:
    from ml.rl.driver_profiles import build_race_lineup
    from ml.rl.model_adapters import load_local_adapters

    lineup   = build_race_lineup("user_driver", user_profile, user_start_position=5)
    adapters = load_local_adapters("models/")
    runner   = RaceRunner(race_id="2024_1", drivers=lineup, adapters=adapters)

    obs, info = runner.reset()
    while not runner.finished:
        action = agent.predict(obs)
        lap_records, obs, info = runner.step_lap(action)

    result = runner.result()
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, cast

import numpy as np

from ml.rl.actions import Action, N_ACTIONS, decode
from ml.rl.driver_profiles import DriverEntry
from ml.rl.reward import COMPOUND_OPTIMAL_LAPS, RewardFunction
from ml.rl.state import StateEncoder

logger = logging.getLogger(__name__)

# ── Circuit registry — offline fallback for total_laps / base lap time ────────
# Covers 2018-2025. race_id format: "{season}_{round}".
# base_lap_time_ms is median dry-weather lap time (ms) from fastf1 data.

CIRCUIT_REGISTRY: dict[str, dict] = {
    # ── 2025 ──────────────────────────────────────────────────────────────────
    "2025_1": {
        "total_laps": 58,
        "base_lap_time_ms": 81_000,
        "race_name": "Australian Grand Prix",
        "circuit_id": "albert_park",
    },
    "2025_2": {
        "total_laps": 56,
        "base_lap_time_ms": 96_500,
        "race_name": "Chinese Grand Prix",
        "circuit_id": "shanghai",
    },
    "2025_3": {
        "total_laps": 53,
        "base_lap_time_ms": 93_500,
        "race_name": "Japanese Grand Prix",
        "circuit_id": "suzuka",
    },
    "2025_4": {
        "total_laps": 57,
        "base_lap_time_ms": 95_800,
        "race_name": "Bahrain Grand Prix",
        "circuit_id": "bahrain",
    },
    "2025_5": {
        "total_laps": 50,
        "base_lap_time_ms": 90_800,
        "race_name": "Saudi Arabian Grand Prix",
        "circuit_id": "jeddah",
    },
    "2025_6": {
        "total_laps": 57,
        "base_lap_time_ms": 91_500,
        "race_name": "Miami Grand Prix",
        "circuit_id": "miami",
    },
    "2025_7": {
        "total_laps": 63,
        "base_lap_time_ms": 79_500,
        "race_name": "Emilia Romagna Grand Prix",
        "circuit_id": "imola",
    },
    "2025_8": {
        "total_laps": 78,
        "base_lap_time_ms": 75_000,
        "race_name": "Monaco Grand Prix",
        "circuit_id": "monaco",
    },
    "2025_9": {
        "total_laps": 66,
        "base_lap_time_ms": 83_500,
        "race_name": "Spanish Grand Prix",
        "circuit_id": "catalunya",
    },
    "2025_10": {
        "total_laps": 70,
        "base_lap_time_ms": 76_000,
        "race_name": "Canadian Grand Prix",
        "circuit_id": "villeneuve",
    },
    "2025_11": {
        "total_laps": 71,
        "base_lap_time_ms": 68_500,
        "race_name": "Austrian Grand Prix",
        "circuit_id": "red_bull_ring",
    },
    "2025_12": {
        "total_laps": 52,
        "base_lap_time_ms": 92_500,
        "race_name": "British Grand Prix",
        "circuit_id": "silverstone",
    },
    "2025_13": {
        "total_laps": 44,
        "base_lap_time_ms": 108_000,
        "race_name": "Belgian Grand Prix",
        "circuit_id": "spa",
    },
    "2025_14": {
        "total_laps": 70,
        "base_lap_time_ms": 80_500,
        "race_name": "Hungarian Grand Prix",
        "circuit_id": "hungaroring",
    },
    "2025_15": {
        "total_laps": 72,
        "base_lap_time_ms": 74_000,
        "race_name": "Dutch Grand Prix",
        "circuit_id": "zandvoort",
    },
    "2025_16": {
        "total_laps": 53,
        "base_lap_time_ms": 83_000,
        "race_name": "Italian Grand Prix",
        "circuit_id": "monza",
    },
    "2025_17": {
        "total_laps": 51,
        "base_lap_time_ms": 106_000,
        "race_name": "Azerbaijan Grand Prix",
        "circuit_id": "baku",
    },
    "2025_18": {
        "total_laps": 62,
        "base_lap_time_ms": 102_000,
        "race_name": "Singapore Grand Prix",
        "circuit_id": "marina_bay",
    },
    "2025_19": {
        "total_laps": 56,
        "base_lap_time_ms": 100_500,
        "race_name": "United States Grand Prix",
        "circuit_id": "americas",
    },
    "2025_20": {
        "total_laps": 71,
        "base_lap_time_ms": 80_000,
        "race_name": "Mexico City Grand Prix",
        "circuit_id": "rodriguez",
    },
    "2025_21": {
        "total_laps": 71,
        "base_lap_time_ms": 74_000,
        "race_name": "São Paulo Grand Prix",
        "circuit_id": "interlagos",
    },
    "2025_22": {
        "total_laps": 50,
        "base_lap_time_ms": 100_000,
        "race_name": "Las Vegas Grand Prix",
        "circuit_id": "las_vegas",
    },
    "2025_23": {
        "total_laps": 57,
        "base_lap_time_ms": 88_500,
        "race_name": "Qatar Grand Prix",
        "circuit_id": "losail",
    },
    "2025_24": {
        "total_laps": 55,
        "base_lap_time_ms": 95_500,
        "race_name": "Abu Dhabi Grand Prix",
        "circuit_id": "yas_marina",
    },
    # ── 2024 ──────────────────────────────────────────────────────────────────
    "2024_1": {
        "total_laps": 58,
        "base_lap_time_ms": 81_200,
        "race_name": "Australian Grand Prix",
        "circuit_id": "albert_park",
    },
    "2024_2": {
        "total_laps": 57,
        "base_lap_time_ms": 96_000,
        "race_name": "Bahrain Grand Prix",
        "circuit_id": "bahrain",
    },
    "2024_3": {
        "total_laps": 50,
        "base_lap_time_ms": 91_000,
        "race_name": "Saudi Arabian Grand Prix",
        "circuit_id": "jeddah",
    },
    "2024_4": {
        "total_laps": 53,
        "base_lap_time_ms": 93_800,
        "race_name": "Japanese Grand Prix",
        "circuit_id": "suzuka",
    },
    "2024_5": {
        "total_laps": 56,
        "base_lap_time_ms": 97_000,
        "race_name": "Chinese Grand Prix",
        "circuit_id": "shanghai",
    },
    "2024_6": {
        "total_laps": 57,
        "base_lap_time_ms": 91_800,
        "race_name": "Miami Grand Prix",
        "circuit_id": "miami",
    },
    "2024_7": {
        "total_laps": 63,
        "base_lap_time_ms": 79_800,
        "race_name": "Emilia Romagna Grand Prix",
        "circuit_id": "imola",
    },
    "2024_8": {
        "total_laps": 78,
        "base_lap_time_ms": 75_200,
        "race_name": "Monaco Grand Prix",
        "circuit_id": "monaco",
    },
    "2024_9": {
        "total_laps": 66,
        "base_lap_time_ms": 83_800,
        "race_name": "Spanish Grand Prix",
        "circuit_id": "catalunya",
    },
    "2024_10": {
        "total_laps": 70,
        "base_lap_time_ms": 76_200,
        "race_name": "Canadian Grand Prix",
        "circuit_id": "villeneuve",
    },
    "2024_11": {
        "total_laps": 71,
        "base_lap_time_ms": 68_800,
        "race_name": "Austrian Grand Prix",
        "circuit_id": "red_bull_ring",
    },
    "2024_12": {
        "total_laps": 52,
        "base_lap_time_ms": 92_800,
        "race_name": "British Grand Prix",
        "circuit_id": "silverstone",
    },
    "2024_13": {
        "total_laps": 44,
        "base_lap_time_ms": 108_500,
        "race_name": "Belgian Grand Prix",
        "circuit_id": "spa",
    },
    "2024_14": {
        "total_laps": 70,
        "base_lap_time_ms": 80_800,
        "race_name": "Hungarian Grand Prix",
        "circuit_id": "hungaroring",
    },
    "2024_15": {
        "total_laps": 72,
        "base_lap_time_ms": 74_200,
        "race_name": "Dutch Grand Prix",
        "circuit_id": "zandvoort",
    },
    "2024_16": {
        "total_laps": 53,
        "base_lap_time_ms": 83_500,
        "race_name": "Italian Grand Prix",
        "circuit_id": "monza",
    },
    "2024_17": {
        "total_laps": 51,
        "base_lap_time_ms": 106_500,
        "race_name": "Azerbaijan Grand Prix",
        "circuit_id": "baku",
    },
    "2024_18": {
        "total_laps": 62,
        "base_lap_time_ms": 102_500,
        "race_name": "Singapore Grand Prix",
        "circuit_id": "marina_bay",
    },
    "2024_19": {
        "total_laps": 56,
        "base_lap_time_ms": 101_000,
        "race_name": "United States Grand Prix",
        "circuit_id": "americas",
    },
    "2024_20": {
        "total_laps": 71,
        "base_lap_time_ms": 80_500,
        "race_name": "Mexico City Grand Prix",
        "circuit_id": "rodriguez",
    },
    "2024_21": {
        "total_laps": 71,
        "base_lap_time_ms": 74_500,
        "race_name": "São Paulo Grand Prix",
        "circuit_id": "interlagos",
    },
    "2024_22": {
        "total_laps": 50,
        "base_lap_time_ms": 100_500,
        "race_name": "Las Vegas Grand Prix",
        "circuit_id": "las_vegas",
    },
    "2024_23": {
        "total_laps": 57,
        "base_lap_time_ms": 89_000,
        "race_name": "Qatar Grand Prix",
        "circuit_id": "losail",
    },
    "2024_24": {
        "total_laps": 55,
        "base_lap_time_ms": 95_800,
        "race_name": "Abu Dhabi Grand Prix",
        "circuit_id": "yas_marina",
    },
    # ── 2023 ──────────────────────────────────────────────────────────────────
    "2023_1": {
        "total_laps": 57,
        "base_lap_time_ms": 96_200,
        "race_name": "Bahrain Grand Prix",
        "circuit_id": "bahrain",
    },
    "2023_2": {
        "total_laps": 50,
        "base_lap_time_ms": 91_200,
        "race_name": "Saudi Arabian Grand Prix",
        "circuit_id": "jeddah",
    },
    "2023_3": {
        "total_laps": 58,
        "base_lap_time_ms": 81_500,
        "race_name": "Australian Grand Prix",
        "circuit_id": "albert_park",
    },
    "2023_4": {
        "total_laps": 53,
        "base_lap_time_ms": 94_000,
        "race_name": "Japanese Grand Prix",
        "circuit_id": "suzuka",
    },
    "2023_5": {
        "total_laps": 57,
        "base_lap_time_ms": 92_000,
        "race_name": "Miami Grand Prix",
        "circuit_id": "miami",
    },
    "2023_6": {
        "total_laps": 66,
        "base_lap_time_ms": 84_000,
        "race_name": "Spanish Grand Prix",
        "circuit_id": "catalunya",
    },
    "2023_7": {
        "total_laps": 78,
        "base_lap_time_ms": 75_500,
        "race_name": "Monaco Grand Prix",
        "circuit_id": "monaco",
    },
    "2023_8": {
        "total_laps": 70,
        "base_lap_time_ms": 76_500,
        "race_name": "Canadian Grand Prix",
        "circuit_id": "villeneuve",
    },
    "2023_9": {
        "total_laps": 63,
        "base_lap_time_ms": 80_000,
        "race_name": "Emilia Romagna Grand Prix",
        "circuit_id": "imola",
    },
    "2023_10": {
        "total_laps": 51,
        "base_lap_time_ms": 107_000,
        "race_name": "Azerbaijan Grand Prix",
        "circuit_id": "baku",
    },
    "2023_11": {
        "total_laps": 52,
        "base_lap_time_ms": 93_000,
        "race_name": "British Grand Prix",
        "circuit_id": "silverstone",
    },
    "2023_12": {
        "total_laps": 71,
        "base_lap_time_ms": 69_000,
        "race_name": "Austrian Grand Prix",
        "circuit_id": "red_bull_ring",
    },
    "2023_13": {
        "total_laps": 44,
        "base_lap_time_ms": 109_000,
        "race_name": "Belgian Grand Prix",
        "circuit_id": "spa",
    },
    "2023_14": {
        "total_laps": 70,
        "base_lap_time_ms": 81_000,
        "race_name": "Hungarian Grand Prix",
        "circuit_id": "hungaroring",
    },
    "2023_15": {
        "total_laps": 72,
        "base_lap_time_ms": 74_500,
        "race_name": "Dutch Grand Prix",
        "circuit_id": "zandvoort",
    },
    "2023_16": {
        "total_laps": 53,
        "base_lap_time_ms": 84_000,
        "race_name": "Italian Grand Prix",
        "circuit_id": "monza",
    },
    "2023_17": {
        "total_laps": 62,
        "base_lap_time_ms": 103_000,
        "race_name": "Singapore Grand Prix",
        "circuit_id": "marina_bay",
    },
    "2023_18": {
        "total_laps": 56,
        "base_lap_time_ms": 101_500,
        "race_name": "United States Grand Prix",
        "circuit_id": "americas",
    },
    "2023_19": {
        "total_laps": 71,
        "base_lap_time_ms": 81_000,
        "race_name": "Mexico City Grand Prix",
        "circuit_id": "rodriguez",
    },
    "2023_20": {
        "total_laps": 71,
        "base_lap_time_ms": 75_000,
        "race_name": "São Paulo Grand Prix",
        "circuit_id": "interlagos",
    },
    "2023_21": {
        "total_laps": 50,
        "base_lap_time_ms": 100_800,
        "race_name": "Las Vegas Grand Prix",
        "circuit_id": "las_vegas",
    },
    "2023_22": {
        "total_laps": 57,
        "base_lap_time_ms": 89_500,
        "race_name": "Qatar Grand Prix",
        "circuit_id": "losail",
    },
    "2023_23": {
        "total_laps": 55,
        "base_lap_time_ms": 96_000,
        "race_name": "Abu Dhabi Grand Prix",
        "circuit_id": "yas_marina",
    },
    # ── 2022 ──────────────────────────────────────────────────────────────────
    "2022_1": {
        "total_laps": 57,
        "base_lap_time_ms": 97_000,
        "race_name": "Bahrain Grand Prix",
        "circuit_id": "bahrain",
    },
    "2022_2": {
        "total_laps": 50,
        "base_lap_time_ms": 92_000,
        "race_name": "Saudi Arabian Grand Prix",
        "circuit_id": "jeddah",
    },
    "2022_3": {
        "total_laps": 58,
        "base_lap_time_ms": 82_000,
        "race_name": "Australian Grand Prix",
        "circuit_id": "albert_park",
    },
    "2022_4": {
        "total_laps": 63,
        "base_lap_time_ms": 80_500,
        "race_name": "Emilia Romagna Grand Prix",
        "circuit_id": "imola",
    },
    "2022_5": {
        "total_laps": 57,
        "base_lap_time_ms": 92_500,
        "race_name": "Miami Grand Prix",
        "circuit_id": "miami",
    },
    "2022_6": {
        "total_laps": 66,
        "base_lap_time_ms": 84_500,
        "race_name": "Spanish Grand Prix",
        "circuit_id": "catalunya",
    },
    "2022_7": {
        "total_laps": 78,
        "base_lap_time_ms": 76_000,
        "race_name": "Monaco Grand Prix",
        "circuit_id": "monaco",
    },
    "2022_8": {
        "total_laps": 70,
        "base_lap_time_ms": 77_000,
        "race_name": "Canadian Grand Prix",
        "circuit_id": "villeneuve",
    },
    "2022_9": {
        "total_laps": 51,
        "base_lap_time_ms": 108_000,
        "race_name": "Azerbaijan Grand Prix",
        "circuit_id": "baku",
    },
    "2022_10": {
        "total_laps": 52,
        "base_lap_time_ms": 93_500,
        "race_name": "British Grand Prix",
        "circuit_id": "silverstone",
    },
    "2022_11": {
        "total_laps": 71,
        "base_lap_time_ms": 69_500,
        "race_name": "Austrian Grand Prix",
        "circuit_id": "red_bull_ring",
    },
    "2022_12": {
        "total_laps": 53,
        "base_lap_time_ms": 94_500,
        "race_name": "Japanese Grand Prix",
        "circuit_id": "suzuka",
    },
    "2022_13": {
        "total_laps": 44,
        "base_lap_time_ms": 110_000,
        "race_name": "Belgian Grand Prix",
        "circuit_id": "spa",
    },
    "2022_14": {
        "total_laps": 70,
        "base_lap_time_ms": 81_500,
        "race_name": "Hungarian Grand Prix",
        "circuit_id": "hungaroring",
    },
    "2022_15": {
        "total_laps": 72,
        "base_lap_time_ms": 75_000,
        "race_name": "Dutch Grand Prix",
        "circuit_id": "zandvoort",
    },
    "2022_16": {
        "total_laps": 53,
        "base_lap_time_ms": 84_500,
        "race_name": "Italian Grand Prix",
        "circuit_id": "monza",
    },
    "2022_17": {
        "total_laps": 62,
        "base_lap_time_ms": 103_500,
        "race_name": "Singapore Grand Prix",
        "circuit_id": "marina_bay",
    },
    "2022_18": {
        "total_laps": 56,
        "base_lap_time_ms": 102_000,
        "race_name": "United States Grand Prix",
        "circuit_id": "americas",
    },
    "2022_19": {
        "total_laps": 71,
        "base_lap_time_ms": 81_500,
        "race_name": "Mexico City Grand Prix",
        "circuit_id": "rodriguez",
    },
    "2022_20": {
        "total_laps": 71,
        "base_lap_time_ms": 75_500,
        "race_name": "São Paulo Grand Prix",
        "circuit_id": "interlagos",
    },
    "2022_21": {
        "total_laps": 55,
        "base_lap_time_ms": 96_500,
        "race_name": "Abu Dhabi Grand Prix",
        "circuit_id": "yas_marina",
    },
}

# Reverse map: race_name → circuit metadata (for SC probability lookup)
_RACE_NAME_TO_META: dict[str, dict] = {
    v["race_name"]: v for v in CIRCUIT_REGISTRY.values()
}


def _registry_lookup(race_id: str) -> dict | None:
    """Return circuit metadata for a race_id, or None if not in registry."""
    return CIRCUIT_REGISTRY.get(race_id)


# ── Physics constants ─────────────────────────────────────────────────────────

FUEL_START_KG = 110.0
PIT_STOP_LOSS_MS = 25_000.0
SC_LAP_DELTA_MS = 15_000.0  # SC adds ~15 s per lap (field bunched, no racing)
SC_END_PROB = 0.40  # P(SC ends this lap); expected duration ≈ 2.5 laps
SC_MIN_LAPS = 2  # minimum laps SC/VSC must be active before it can clear
SC_DEFAULT_PROB = 0.04

VSC_LAP_DELTA_MS = 6_000.0  # VSC adds ~6 s per lap (delta-time enforced, no bunching)
VSC_END_PROB = 0.40  # same clearance probability as SC
VSC_DEFAULT_PROB = 0.06  # VSC triggered slightly more often than full SC

COMPOUND_DELTA_MS: dict[str, float] = {
    "SOFT": 0.0,
    "MEDIUM": 400.0,
    "HARD": 800.0,
    "INTER": 1_500.0,
    "WET": 2_500.0,
}
DEG_RATE_MS: dict[str, float] = {
    "SOFT": 80.0,
    "MEDIUM": 50.0,
    "HARD": 30.0,
    "INTER": 60.0,
    "WET": 40.0,
}
FUEL_BURN_KG: dict[str, float] = {"PUSH": 2.1, "BALANCED": 1.8, "NEUTRAL": 1.5}
MODE_DELTA_MS: dict[str, float] = {"PUSH": -200.0, "BALANCED": 0.0, "NEUTRAL": 150.0}

# Lap-to-lap noise std (ms) for a perfectly consistent driver; scaled by (1 - consistency)
BASE_NOISE_MS = 400.0

# How much gap (s) below which "pressure" effect kicks in
PRESSURE_GAP_S = 1.2


# ── Data structures ───────────────────────────────────────────────────────────


@dataclass
class DriverRaceState:
    """Mutable per-driver state throughout the race."""

    entry: DriverEntry
    position: int
    tire_compound: str
    tire_age_laps: int
    pit_stops: int
    fuel_remaining_kg: float
    cumulative_time_ms: float
    last_lap_time_ms: float
    driving_mode: str
    driving_style_int: int  # 0=NEUTRAL, 1=BALANCED, 2=PUSH
    gap_to_leader: float  # seconds
    gap_to_ahead: float  # seconds
    safety_car: bool = False
    vsc: bool = False
    retired: bool = False
    # Rolling features for ML models (maintained over race)
    _tyre_delta_hist: deque = field(default_factory=lambda: deque([0.0] * 5, maxlen=5))
    _lap_delta_hist: deque = field(default_factory=lambda: deque([0.0] * 3, maxlen=3))
    _prev_style_int: int = 1


@dataclass
class LapRecord:
    """One driver's data for one lap — the output record."""

    driver_id: str
    display_name: str
    lap_number: int
    position: int
    lap_time_ms: float
    tire_compound: str
    tire_age_laps: int
    fuel_remaining_kg: float
    pit_stop: bool
    new_compound: Optional[str]
    driving_mode: str
    gap_to_leader: float
    gap_to_ahead: float
    safety_car: bool
    vsc: bool
    cumulative_time_ms: float


@dataclass
class RaceResult:
    """Full output after a completed race."""

    race_id: str
    circuit_id: str
    total_laps: int
    user_driver_id: str
    # driver_id → list of LapRecord (one per lap)
    lap_data: dict[str, list[LapRecord]]
    # Final race standings: [{position, driver_id, display_name, total_time_s, pit_stops}]
    final_standings: list[dict]
    # user's final position
    user_final_position: int
    # strategy summary per driver: [{driver_id, stints: [{compound, laps}]}]
    strategy_summary: list[dict]


# Physics-only adapter singletons — unloaded adapters use pure physics formulas.
# Shared across all RaceRunner instances so there's no per-lap object creation.
def _get_physics_adapters():
    from ml.rl.model_adapters import TireDegradationAdapter, FuelConsumptionAdapter

    return TireDegradationAdapter(None), FuelConsumptionAdapter(None)


_PHYSICS_TIRE, _PHYSICS_FUEL = _get_physics_adapters()

# ── Race Runner ───────────────────────────────────────────────────────────────


class RaceRunner:
    """
    Simulates a full F1 race with one RL-controlled driver and N AI rivals.

    Args:
        race_id:    Race identifier (e.g. "2024_1") for loading circuit data.
        drivers:    List of DriverEntry from driver_profiles.build_race_lineup().
        adapters:   Dict of model adapters from model_adapters.load_local_adapters().
        total_laps: Override total laps (loaded from data if None).
        base_lap_time_ms: Override circuit base lap time (loaded from data if None).
        circuit_id: Circuit identifier for SC probability lookup.
        race_name:  Race name for SC probability lookup (e.g. "Bahrain Grand Prix").
        project:    GCP project ID.
        seed:       Random seed for stochastic elements.
    """

    def __init__(
        self,
        race_id: str,
        drivers: list[DriverEntry],
        adapters: Optional[dict] = None,
        total_laps: Optional[int] = None,
        base_lap_time_ms: Optional[float] = None,
        circuit_id: str = "",
        race_name: str = "",
        project: str = "f1optimizer",
        seed: Optional[int] = None,
        ml_user_only: bool = True,
    ) -> None:
        self._race_id = race_id
        self._drivers = drivers
        self._adapters = adapters or {}
        self._project = project
        self._ml_user_only = ml_user_only
        self._rng = np.random.default_rng(seed)

        # Resolve circuit metadata: explicit args → registry → GCS → defaults
        _reg = _registry_lookup(race_id)
        self._circuit_id = circuit_id or (_reg["circuit_id"] if _reg else "")
        self._race_name = race_name or (_reg["race_name"] if _reg else "")

        self._total_laps = total_laps or (
            _reg["total_laps"] if _reg else self._load_total_laps()
        )
        self._base_lap_time_ms = base_lap_time_ms or (
            _reg["base_lap_time_ms"] if _reg else self._load_base_lap_time()
        )
        self._sc_deploy_prob = self._load_sc_prob()

        # Initialised on reset()
        self._current_lap: int = 1
        self._safety_car: bool = False
        self._vsc: bool = False
        self._sc_laps_active: int = 0
        self._vsc_laps_active: int = 0
        self._states: dict[str, DriverRaceState] = {}
        self._lap_data: dict[str, list[LapRecord]] = {}
        self._user_id: str = next((d.driver_id for d in drivers if d.is_user), "")
        self._reward_fn = RewardFunction()
        self._encoder = StateEncoder()

        # Init user driver's encoder profile
        user_entry = next((d for d in drivers if d.is_user), None)
        if user_entry:
            self._encoder = StateEncoder(user_entry.profile)

    # ── Public interface ──────────────────────────────────────────────────────

    def reset(self) -> tuple[np.ndarray, dict]:
        """Initialise race state. Returns (obs, info) for the user's driver."""
        self._current_lap = 1
        self._safety_car = False
        self._vsc = False
        self._sc_laps_active = 0
        self._vsc_laps_active = 0
        self._lap_data = {d.driver_id: [] for d in self._drivers}
        self._reward_fn.reset()
        self._encoder.reset()

        self._states = {
            d.driver_id: DriverRaceState(
                entry=d,
                position=d.start_position,
                tire_compound=d.start_compound,
                tire_age_laps=0,
                pit_stops=0,
                fuel_remaining_kg=FUEL_START_KG,
                cumulative_time_ms=0.0,
                last_lap_time_ms=self._base_lap_time_ms,
                driving_mode="BALANCED",
                driving_style_int=1,
                gap_to_leader=0.0,
                gap_to_ahead=0.0,
            )
            for d in self._drivers
        }
        return self._user_obs(), self._user_info()

    def step_lap(
        self, user_action: int
    ) -> tuple[dict[str, LapRecord], np.ndarray, dict]:
        """
        Advance one lap.

        Args:
            user_action: RL action int for the user's driver (see actions.py).

        Returns:
            (lap_records, obs, info)
              lap_records: dict[driver_id → LapRecord] for all drivers this lap
              obs:         new observation for user's driver
              info:        info dict for user's driver
        """
        lap_records: dict[str, LapRecord] = {}

        prev_user_pos = self._states[self._user_id].position

        # ── Phase 1: apply actions, resolve pits ──────────────────────────────
        active = [d for d in self._drivers if not self._states[d.driver_id].retired]
        pit_flags: dict[str, bool] = {}
        new_compounds: dict[str, Optional[str]] = {}

        for d in active:
            state = self._states[d.driver_id]
            action = user_action if d.is_user else self._ai_action(state)
            decoded = decode(action)

            pitted = False
            new_compound = None
            if decoded.is_pit and decoded.new_compound:
                state._prev_style_int = state.driving_style_int
                new_compound = decoded.new_compound
                state.tire_compound = new_compound
                state.tire_age_laps = 0
                state.pit_stops += 1
                pitted = True

            state._prev_style_int = state.driving_style_int
            state.driving_mode = decoded.driving_mode
            state.driving_style_int = decoded.driving_style_int
            pit_flags[d.driver_id] = pitted
            new_compounds[d.driver_id] = new_compound

        # ── Phase 2: ML predictions for lap times ─────────────────────────────
        # ml_user_only=True (default for RL training): run ML only for the
        # user's driver; rivals use physics. This gives ~15x speedup since
        # model inference dominates step time with 20 drivers.
        td_adapter = self._tire_deg_adapter()
        fuel_adapter = self._fuel_adapter()

        if self._ml_user_only and self._user_id:
            # Only build the full state dict for the user driver — rivals use
            # physics directly via a 3-key minimal dict, avoiding 19 wasted
            # _model_state_dict() calls (each does list copies + np.mean) per step.
            tire_deltas = {}
            fuel_burns = {}
            for d in active:
                state = self._states[d.driver_id]
                if d.driver_id == self._user_id:
                    ms = self._model_state_dict(state)
                    tire_deltas[d.driver_id] = (
                        td_adapter.predict(ms)
                        if td_adapter.loaded
                        else _PHYSICS_TIRE.predict(ms)
                    )
                    fuel_burns[d.driver_id] = (
                        fuel_adapter.predict(ms)
                        if fuel_adapter.loaded
                        else _PHYSICS_FUEL.predict(ms)
                    )
                else:
                    phys = {
                        "tire_compound": state.tire_compound,
                        "tire_age_laps": state.tire_age_laps,
                        "driving_mode": state.driving_mode,
                    }
                    tire_deltas[d.driver_id] = _PHYSICS_TIRE.predict(phys)
                    fuel_burns[d.driver_id] = _PHYSICS_FUEL.predict(phys)
        else:
            # Full ML for all drivers (eval / non-training use)
            id_list = [d.driver_id for d in active]
            ms_list = [
                self._model_state_dict(self._states[d.driver_id]) for d in active
            ]
            if hasattr(td_adapter, "predict_batch") and td_adapter.loaded:
                tire_deltas = dict(zip(id_list, td_adapter.predict_batch(ms_list)))
            else:
                tire_deltas = {
                    did: td_adapter.predict(ms) for did, ms in zip(id_list, ms_list)
                }
            if hasattr(fuel_adapter, "predict_batch") and fuel_adapter.loaded:
                fuel_burns = dict(zip(id_list, fuel_adapter.predict_batch(ms_list)))
            else:
                fuel_burns = {
                    did: fuel_adapter.predict(ms) for did, ms in zip(id_list, ms_list)
                }

        # ── Phase 3: compute lap times and update state ───────────────────────
        for d in active:
            state = self._states[d.driver_id]
            pitted = pit_flags[d.driver_id]
            new_compound = new_compounds[d.driver_id]
            tire_delta_s = tire_deltas[d.driver_id]
            fuel_burn = fuel_burns[d.driver_id]

            lap_time_ms = self._compute_lap_time(state, pitted, tire_delta_s)

            prev_lap_time_ms = state.last_lap_time_ms
            state.last_lap_time_ms = lap_time_ms
            state.cumulative_time_ms += lap_time_ms
            state.fuel_remaining_kg = max(0.0, state.fuel_remaining_kg - fuel_burn)
            state.tire_age_laps += 1

            # Update rolling trackers
            lap_delta_s = (lap_time_ms - prev_lap_time_ms) / 1000.0
            state._tyre_delta_hist.append(tire_delta_s)
            state._lap_delta_hist.append(lap_delta_s)

            rec = LapRecord(
                driver_id=d.driver_id,
                display_name=d.display_name,
                lap_number=self._current_lap,
                position=state.position,  # updated below
                lap_time_ms=round(lap_time_ms, 1),
                tire_compound=state.tire_compound,
                tire_age_laps=state.tire_age_laps,
                fuel_remaining_kg=round(state.fuel_remaining_kg, 2),
                pit_stop=pitted,
                new_compound=new_compound,
                driving_mode=state.driving_mode,
                gap_to_leader=0.0,  # filled after position update
                gap_to_ahead=0.0,
                safety_car=self._safety_car,
                vsc=self._vsc,
                cumulative_time_ms=round(state.cumulative_time_ms, 1),
            )
            lap_records[d.driver_id] = rec
            self._lap_data[d.driver_id].append(rec)

        # Update positions + gaps from cumulative times
        self._update_positions(lap_records)
        self._update_safety_car()

        # Sync safety car / VSC flag into states and records
        for d in self._drivers:
            self._states[d.driver_id].safety_car = self._safety_car
            self._states[d.driver_id].vsc = self._vsc
            if d.driver_id in lap_records:
                lap_records[d.driver_id].safety_car = self._safety_car
                lap_records[d.driver_id].vsc = self._vsc

        self._current_lap += 1

        obs = self._user_obs()
        info = self._user_info()
        info["prev_position"] = prev_user_pos
        return lap_records, obs, info

    @property
    def finished(self) -> bool:
        return self._current_lap > self._total_laps

    def result(self) -> RaceResult:
        """Build and return the final RaceResult after the race is complete."""
        standings = sorted(
            [
                {
                    "position": s.position,
                    "driver_id": s.entry.driver_id,
                    "display_name": s.entry.display_name,
                    "total_time_s": round(s.cumulative_time_ms / 1000.0, 3),
                    "pit_stops": s.pit_stops,
                    "gap_to_winner_s": round(
                        (
                            s.cumulative_time_ms
                            - min(x.cumulative_time_ms for x in self._states.values())
                        )
                        / 1000.0,
                        3,
                    ),
                }
                for s in self._states.values()
            ],
            key=lambda x: cast(int, x["position"]),
        )

        strategy_summary = [
            {
                "driver_id": d.driver_id,
                "display_name": d.display_name,
                "stints": _extract_stints(self._lap_data.get(d.driver_id, [])),
            }
            for d in self._drivers
        ]

        return RaceResult(
            race_id=self._race_id,
            circuit_id=self._circuit_id,
            total_laps=self._total_laps,
            user_driver_id=self._user_id,
            lap_data=self._lap_data,
            final_standings=standings,
            user_final_position=next((s["position"] for s in standings if s["driver_id"] == self._user_id), 20),
            strategy_summary=strategy_summary,
        )

    def run_full_race(
        self,
        user_action_fn: Callable[[np.ndarray, dict], int],
    ) -> RaceResult:
        """
        Run the entire race from start to finish.

        Args:
            user_action_fn: Callable(obs, info) → action int for the user's driver.
                            Typically agent.predict or a heuristic.
        Returns:
            RaceResult with full lap-by-lap data.
        """
        obs, info = self.reset()
        while not self.finished:
            action = user_action_fn(obs, info)
            _, obs, info = self.step_lap(action)
        return self.result()

    # ── AI strategy ───────────────────────────────────────────────────────────

    def _ai_action(self, state: DriverRaceState) -> int:
        """
        Determine action for an AI-controlled driver.
        Strategy is shaped by the driver's profile: aggressive drivers push
        harder, good tire managers extend stints, etc.
        """
        profile = state.entry.profile
        aggression = profile.get("aggression", 0.70)
        tire_mgmt = profile.get("tire_management", 0.75)
        lap = self._current_lap
        total = self._total_laps
        tire_age = state.tire_age_laps
        compound = state.tire_compound.upper()
        laps_rem = total - lap
        gap_ahead = state.gap_to_ahead
        fuel = state.fuel_remaining_kg

        # ── Pit decision ─────────────────────────────────────────────────────

        # Safety car opportunity — query SC model or use tire age heuristic
        # VSC requires more tire wear than SC to justify a pit (smaller time saving)
        if (state.safety_car and tire_age > 8) or (state.vsc and tire_age > 15):
            model_state = self._model_state_dict(state)
            pit_prob = (
                self._sc_adapter().predict_pit(model_state)
                if self._sc_adapter().loaded
                else 0.0
            )
            threshold = (
                0.45 - 0.1 * tire_mgmt
            )  # conservative managers need higher confidence
            if (
                pit_prob > threshold
                or tire_age > COMPOUND_OPTIMAL_LAPS.get(compound, 30) * 0.8
            ):
                return _choose_compound_action(laps_rem, aggression)

        # Tire degradation threshold: better tire managers can stretch further
        optimal = COMPOUND_OPTIMAL_LAPS.get(compound, 30)
        max_age = int(optimal * (1.0 + 0.30 * tire_mgmt))
        if tire_age >= max_age:
            return _choose_compound_action(laps_rem, aggression)

        # Undercut / anti-undercut window (lap 0.35-0.65 race)
        laps_pct = lap / max(total, 1)
        if (
            state.pit_stops == 0
            and 0.35 <= laps_pct <= 0.52
            and tire_age >= int(optimal * 0.75)
        ):
            # Small stochastic chance to pit in strategic window
            if self._rng.random() < 0.06 + 0.04 * aggression:
                return _choose_compound_action(laps_rem, aggression)

        if (
            state.pit_stops == 1
            and 0.65 <= laps_pct <= 0.80
            and tire_age >= int(optimal * 0.70)
        ):
            if self._rng.random() < 0.07 + 0.03 * aggression:
                return _choose_compound_action(laps_rem, aggression)

        # ── Driving mode ─────────────────────────────────────────────────────

        # Conserve when low on fuel or over-extended tires
        if fuel < 12.0 or tire_age > int(optimal * 0.95):
            return int(Action.STAY_NEUTRAL)

        # Push when close to the car ahead
        if gap_ahead < PRESSURE_GAP_S and aggression > 0.65:
            return int(Action.STAY_PUSH)

        # Profile-based default mode
        if aggression >= 0.80:
            return int(Action.STAY_PUSH)
        if aggression >= 0.65:
            return int(Action.STAY_BALANCED)
        return int(Action.STAY_NEUTRAL)

    # ── Lap simulation ────────────────────────────────────────────────────────

    def _compute_lap_time(
        self, state: DriverRaceState, just_pitted: bool, tire_delta_s: float
    ) -> float:
        """
        Compute lap_time_ms for this driver this lap.
        tire_delta_s is pre-computed (from batch ML call or physics fallback).
        """
        base_ms = self._base_lap_time_ms + state.entry.car_offset_ms
        deg_ms = tire_delta_s * 1000.0
        compound_delta = COMPOUND_DELTA_MS.get(state.tire_compound.upper(), 0.0)
        mode_delta = MODE_DELTA_MS.get(state.driving_mode, 0.0)
        if self._safety_car:
            sc_delta = SC_LAP_DELTA_MS
        elif self._vsc:
            sc_delta = VSC_LAP_DELTA_MS
        else:
            sc_delta = 0.0
        pit_loss = PIT_STOP_LOSS_MS if just_pitted else 0.0

        pressure_delta = 0.0
        if state.gap_to_ahead < PRESSURE_GAP_S:
            pressure_delta = -state.entry.profile.get("pressure_response", 0.5) * 150.0

        noise_std = BASE_NOISE_MS * (1.0 - state.entry.profile.get("consistency", 0.8))
        noise_ms = float(self._rng.normal(0.0, noise_std))

        lap_time_ms = (
            base_ms
            + compound_delta
            + deg_ms
            + mode_delta
            + sc_delta
            + pit_loss
            + pressure_delta
            + noise_ms
        )
        return max(lap_time_ms, base_ms * 0.85)

    # ── Position + gap updates ────────────────────────────────────────────────

    def _update_positions(self, lap_records: dict[str, LapRecord]) -> None:
        """Rank drivers by cumulative race time and update gaps."""
        sorted_states = sorted(
            [s for s in self._states.values() if not s.retired],
            key=lambda s: s.cumulative_time_ms,
        )
        times = [s.cumulative_time_ms for s in sorted_states]
        leader_time = times[0] if times else 0.0

        for rank, s in enumerate(sorted_states, start=1):
            s.position = rank
            s.gap_to_leader = max(0.0, (s.cumulative_time_ms - leader_time) / 1000.0)
            s.gap_to_ahead = (
                max(0.0, (s.cumulative_time_ms - times[rank - 2]) / 1000.0)
                if rank > 1
                else 0.0
            )

            # Write back to lap record
            if s.entry.driver_id in lap_records:
                rec = lap_records[s.entry.driver_id]
                rec.position = rank
                rec.gap_to_leader = round(s.gap_to_leader, 3)
                rec.gap_to_ahead = round(s.gap_to_ahead, 3)

    def _update_safety_car(self) -> None:
        """Stochastically deploy or clear the safety car / virtual safety car.

        Minimum duration (SC_MIN_LAPS / VSC_MIN_LAPS) prevents the flag from
        clearing on the same lap it deployed, matching real-F1 behaviour where
        SC/VSC lasts at least 2 laps before the pit lane is closed and the
        field is released.
        """
        if self._safety_car:
            self._sc_laps_active += 1
            if self._sc_laps_active >= SC_MIN_LAPS and self._rng.random() < SC_END_PROB:
                self._safety_car = False
                self._sc_laps_active = 0
        elif self._vsc:
            self._vsc_laps_active += 1
            if (
                self._vsc_laps_active >= SC_MIN_LAPS
                and self._rng.random() < VSC_END_PROB
            ):
                self._vsc = False
                self._vsc_laps_active = 0
        else:
            if self._rng.random() < self._sc_deploy_prob:
                self._safety_car = True
                self._sc_laps_active = 0
            elif self._rng.random() < VSC_DEFAULT_PROB:
                self._vsc = True
                self._vsc_laps_active = 0

    # ── Model state dict ──────────────────────────────────────────────────────

    def _model_state_dict(self, state: DriverRaceState) -> dict[str, Any]:
        """Build the state dict that model adapters expect."""
        lap = self._current_lap
        total = max(self._total_laps, 1)
        t_hist = list(state._tyre_delta_hist)
        l_hist = list(state._lap_delta_hist)

        return {
            "lap_number": lap,
            "total_laps": total,
            "tire_age_laps": state.tire_age_laps,
            "pit_stops_count": state.pit_stops,
            "tire_compound": state.tire_compound,
            "position": state.position,
            "gap_to_ahead": state.gap_to_ahead,
            "gap_to_leader": state.gap_to_leader,
            "lap_time_ms": state.last_lap_time_ms,
            "lap_time_delta_ms": (l_hist[-1] * 1000) if l_hist else 0.0,
            "driving_mode": state.driving_mode,
            "driving_style_int": state.driving_style_int,
            "prev_style_int": state._prev_style_int,
            "safety_car": self._safety_car,
            "vsc": self._vsc,
            "race_name": self._race_name,
            "delta_roll3": float(np.mean(t_hist[-3:])) if t_hist else 0.0,
            "delta_roll5": float(np.mean(t_hist)) if t_hist else 0.0,
            "deg_rate_roll3": float(np.mean(l_hist)) if l_hist else 0.0,
            "tyre_delta_roll3": float(np.mean(t_hist[-3:])) if t_hist else 0.0,
            "tyre_delta": t_hist[-1] if t_hist else 0.0,
            "tyre_delta_trend": float(np.mean(t_hist)) if t_hist else 0.0,
        }

    # ── Adapter accessors ─────────────────────────────────────────────────────

    def _tire_deg_adapter(self):
        from ml.rl.model_adapters import TireDegradationAdapter

        return self._adapters.get("tire_deg") or TireDegradationAdapter(None)

    def _fuel_adapter(self):
        from ml.rl.model_adapters import FuelConsumptionAdapter

        return self._adapters.get("fuel") or FuelConsumptionAdapter(None)

    def _sc_adapter(self):
        from ml.rl.model_adapters import SafetyCarAdapter

        return self._adapters.get("sc") or SafetyCarAdapter(None)

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_total_laps(self) -> int:
        try:
            from ml.features.feature_store import FeatureStore

            df = FeatureStore(project=self._project).load_race_features(self._race_id)
            if df is not None and not df.empty:
                return int(df["lap_number"].max())
        except Exception:
            pass
        return 58

    def _load_base_lap_time(self) -> float:
        try:
            from ml.features.feature_store import FeatureStore

            df = FeatureStore(project=self._project).load_race_features(self._race_id)
            if df is not None and not df.empty and "last_lap_time_ms" in df.columns:
                return float(df["last_lap_time_ms"].median())
        except Exception:
            pass
        return 95_000.0

    def _load_sc_prob(self) -> float:
        sc = self._adapters.get("sc")
        if sc and sc.loaded and self._race_name:
            return sc.sc_deploy_prob(self._race_name)
        return SC_DEFAULT_PROB

    # ── Observation / info for user driver ────────────────────────────────────

    def _user_obs(self) -> np.ndarray:
        if not self._user_id or self._user_id not in self._states:
            return np.zeros(29, dtype=np.float32)
        s = self._states[self._user_id]
        return self._encoder.encode(
            lap_number=self._current_lap,
            total_laps=self._total_laps,
            tire_age_laps=s.tire_age_laps,
            fuel_remaining_kg=s.fuel_remaining_kg,
            tire_compound=s.tire_compound,
            position=s.position,
            gap_to_leader=s.gap_to_leader,
            gap_to_ahead=s.gap_to_ahead,
            lap_time_ms=s.last_lap_time_ms,
            pit_stops_count=s.pit_stops,
            safety_car=self._safety_car,
        )

    def _user_info(self) -> dict[str, Any]:
        if not self._user_id or self._user_id not in self._states:
            return {}
        s = self._states[self._user_id]
        return {
            "race_id": self._race_id,
            "race_name": self._race_name,
            "lap_number": self._current_lap,
            "total_laps": self._total_laps,
            "position": s.position,
            "tire_compound": s.tire_compound,
            "tire_age_laps": s.tire_age_laps,
            "pit_stops_count": s.pit_stops,
            "fuel_remaining_kg": round(s.fuel_remaining_kg, 2),
            "driving_mode": s.driving_mode,
            "safety_car": self._safety_car,
            "vsc": self._vsc,
            "gap_to_leader": round(s.gap_to_leader, 3),
            "gap_to_ahead": round(s.gap_to_ahead, 3),
            "lap_time_ms": round(s.last_lap_time_ms, 1),
            "cumulative_time_ms": round(s.cumulative_time_ms, 1),
        }


# ── Module-level helpers ──────────────────────────────────────────────────────


def _choose_compound_action(laps_remaining: int, aggression: float) -> int:
    """Pick a pit action based on remaining laps and driver aggression."""
    if laps_remaining <= 15:
        return int(Action.PIT_SOFT)
    if laps_remaining <= 28:
        return int(Action.PIT_MEDIUM) if aggression < 0.75 else int(Action.PIT_SOFT)
    return int(Action.PIT_HARD) if aggression < 0.70 else int(Action.PIT_MEDIUM)


def _extract_stints(lap_records: list[LapRecord]) -> list[dict]:
    """Summarise a driver's stints from their lap record list."""
    if not lap_records:
        return []
    stints: list[dict] = []
    current_compound = lap_records[0].tire_compound
    stint_start = 1
    for rec in lap_records:
        if rec.pit_stop and rec.new_compound:
            stints.append(
                {"compound": current_compound, "laps": rec.lap_number - stint_start}
            )
            current_compound = rec.new_compound
            stint_start = rec.lap_number
    # Final stint
    last_lap = lap_records[-1].lap_number
    stints.append({"compound": current_compound, "laps": last_lap - stint_start + 1})
    return stints

