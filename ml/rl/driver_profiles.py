"""
Driver profiles for the F1 race simulation.

Profile dimensions (all float [0, 1]):
  aggression        — throttle intensity, willing to risk tires/collisions
  consistency       — lap-to-lap variance (1 = very consistent)
  tire_management   — ability to extend tire stints beyond optimal
  pressure_response — pace when being chased or chasing within 1 s

Performance offsets represent car-level pace differences vs the midfield
baseline (negative = faster, positive = slower, in ms per lap).

Usage:
    profile = get_profile("max_verstappen")
    lineup  = build_race_lineup("user_driver", user_profile, n_rivals=19)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ── Driver profiles ───────────────────────────────────────────────────────────

DRIVER_PROFILES: dict[str, dict[str, float]] = {
    # Red Bull
    "max_verstappen": {
        "aggression": 0.88,
        "consistency": 0.96,
        "tire_management": 0.82,
        "pressure_response": 0.93,
    },
    "liam_lawson": {
        "aggression": 0.74,
        "consistency": 0.76,
        "tire_management": 0.72,
        "pressure_response": 0.70,
    },
    # McLaren
    "lando_norris": {
        "aggression": 0.79,
        "consistency": 0.84,
        "tire_management": 0.76,
        "pressure_response": 0.76,
    },
    "oscar_piastri": {
        "aggression": 0.77,
        "consistency": 0.85,
        "tire_management": 0.79,
        "pressure_response": 0.74,
    },
    # Ferrari
    "charles_leclerc": {
        "aggression": 0.83,
        "consistency": 0.84,
        "tire_management": 0.72,
        "pressure_response": 0.81,
    },
    "lewis_hamilton": {
        "aggression": 0.76,
        "consistency": 0.92,
        "tire_management": 0.91,
        "pressure_response": 0.88,
    },
    # Mercedes
    "george_russell": {
        "aggression": 0.74,
        "consistency": 0.88,
        "tire_management": 0.81,
        "pressure_response": 0.77,
    },
    "kimi_antonelli": {
        "aggression": 0.75,
        "consistency": 0.76,
        "tire_management": 0.72,
        "pressure_response": 0.70,
    },
    # Aston Martin
    "fernando_alonso": {
        "aggression": 0.77,
        "consistency": 0.90,
        "tire_management": 0.88,
        "pressure_response": 0.87,
    },
    "lance_stroll": {
        "aggression": 0.65,
        "consistency": 0.73,
        "tire_management": 0.75,
        "pressure_response": 0.62,
    },
    # Alpine
    "pierre_gasly": {
        "aggression": 0.72,
        "consistency": 0.78,
        "tire_management": 0.74,
        "pressure_response": 0.71,
    },
    "jack_doohan": {
        "aggression": 0.71,
        "consistency": 0.72,
        "tire_management": 0.70,
        "pressure_response": 0.66,
    },
    # Haas
    "oliver_bearman": {
        "aggression": 0.74,
        "consistency": 0.75,
        "tire_management": 0.71,
        "pressure_response": 0.68,
    },
    "esteban_ocon": {
        "aggression": 0.69,
        "consistency": 0.77,
        "tire_management": 0.76,
        "pressure_response": 0.68,
    },
    # RB (Racing Bulls)
    "yuki_tsunoda": {
        "aggression": 0.76,
        "consistency": 0.73,
        "tire_management": 0.70,
        "pressure_response": 0.71,
    },
    "isack_hadjar": {
        "aggression": 0.73,
        "consistency": 0.74,
        "tire_management": 0.71,
        "pressure_response": 0.68,
    },
    # Sauber
    "nico_hulkenberg": {
        "aggression": 0.70,
        "consistency": 0.80,
        "tire_management": 0.78,
        "pressure_response": 0.72,
    },
    "gabriel_bortoleto": {
        "aggression": 0.72,
        "consistency": 0.73,
        "tire_management": 0.70,
        "pressure_response": 0.67,
    },
    # Williams
    "alex_albon": {
        "aggression": 0.71,
        "consistency": 0.79,
        "tire_management": 0.77,
        "pressure_response": 0.72,
    },
    "carlos_sainz": {
        "aggression": 0.73,
        "consistency": 0.86,
        "tire_management": 0.84,
        "pressure_response": 0.78,
    },
    # Legends (available for custom races)
    "michael_schumacher": {
        "aggression": 0.87,
        "consistency": 0.95,
        "tire_management": 0.86,
        "pressure_response": 0.92,
    },
    "ayrton_senna": {
        "aggression": 0.93,
        "consistency": 0.88,
        "tire_management": 0.74,
        "pressure_response": 0.95,
    },
    "alain_prost": {
        "aggression": 0.65,
        "consistency": 0.94,
        "tire_management": 0.95,
        "pressure_response": 0.84,
    },
    "sebastian_vettel": {
        "aggression": 0.80,
        "consistency": 0.93,
        "tire_management": 0.85,
        "pressure_response": 0.85,
    },
    "valtteri_bottas": {
        "aggression": 0.71,
        "consistency": 0.85,
        "tire_management": 0.82,
        "pressure_response": 0.65,
    },
}

# Human-readable display names
DRIVER_DISPLAY_NAMES: dict[str, str] = {
    "max_verstappen": "Max Verstappen",
    "liam_lawson": "Liam Lawson",
    "lando_norris": "Lando Norris",
    "oscar_piastri": "Oscar Piastri",
    "charles_leclerc": "Charles Leclerc",
    "lewis_hamilton": "Lewis Hamilton",
    "george_russell": "George Russell",
    "kimi_antonelli": "Kimi Antonelli",
    "fernando_alonso": "Fernando Alonso",
    "lance_stroll": "Lance Stroll",
    "pierre_gasly": "Pierre Gasly",
    "jack_doohan": "Jack Doohan",
    "oliver_bearman": "Oliver Bearman",
    "esteban_ocon": "Esteban Ocon",
    "yuki_tsunoda": "Yuki Tsunoda",
    "isack_hadjar": "Isack Hadjar",
    "nico_hulkenberg": "Nico Hülkenberg",
    "gabriel_bortoleto": "Gabriel Bortoleto",
    "alex_albon": "Alex Albon",
    "carlos_sainz": "Carlos Sainz",
    "michael_schumacher": "Michael Schumacher",
    "ayrton_senna": "Ayrton Senna",
    "alain_prost": "Alain Prost",
    "sebastian_vettel": "Sebastian Vettel",
    "valtteri_bottas": "Valtteri Bottas",
}

# Per-driver car performance offset (ms/lap vs a median field car).
# Negative = faster. Reflects 2025 constructor competitiveness.
CAR_PERFORMANCE_OFFSET_MS: dict[str, float] = {
    # Red Bull
    "max_verstappen": -600.0,
    "liam_lawson": -480.0,
    # McLaren
    "lando_norris": -550.0,
    "oscar_piastri": -540.0,
    # Ferrari
    "charles_leclerc": -480.0,
    "lewis_hamilton": -470.0,
    # Mercedes
    "george_russell": -380.0,
    "kimi_antonelli": -360.0,
    # Aston Martin
    "fernando_alonso": -320.0,
    "lance_stroll": -280.0,
    # Williams
    "alex_albon": -160.0,
    "carlos_sainz": -170.0,
    # RB (Racing Bulls)
    "yuki_tsunoda": -140.0,
    "isack_hadjar": -110.0,
    # Alpine
    "pierre_gasly": -100.0,
    "jack_doohan": -80.0,
    # Haas
    "esteban_ocon": -60.0,
    "oliver_bearman": -50.0,
    # Sauber
    "nico_hulkenberg": -80.0,
    "gabriel_bortoleto": -60.0,
}

# Default grid order (starting positions for a typical race)
DEFAULT_GRID: list[str] = [
    "max_verstappen",
    "lando_norris",
    "charles_leclerc",
    "oscar_piastri",
    "lewis_hamilton",
    "george_russell",
    "carlos_sainz",
    "fernando_alonso",
    "liam_lawson",
    "kimi_antonelli",
    "yuki_tsunoda",
    "isack_hadjar",
    "alex_albon",
    "nico_hulkenberg",
    "gabriel_bortoleto",
    "esteban_ocon",
    "oliver_bearman",
    "pierre_gasly",
    "lance_stroll",
    "jack_doohan",
]

# Default starting compounds per grid position
DEFAULT_START_COMPOUNDS: dict[int, str] = {
    **{p: "MEDIUM" for p in range(1, 11)},
    **{p: "HARD" for p in range(11, 21)},
}

_GENERIC_PROFILE: dict[str, float] = {
    "aggression": 0.70,
    "consistency": 0.78,
    "tire_management": 0.75,
    "pressure_response": 0.70,
}


@dataclass
class DriverEntry:
    """One driver's configuration entering the race."""

    driver_id: str
    display_name: str
    profile: dict  # aggression, consistency, tire_management, pressure_response
    start_position: int
    start_compound: str  # SOFT / MEDIUM / HARD
    car_offset_ms: float = 0.0  # lap time offset vs baseline (negative = faster)
    is_user: bool = False  # True = RL agent / user controls this driver


def get_profile(driver_id: str) -> dict[str, float]:
    """Return driver profile, falling back to a generic midfield profile."""
    return dict(DRIVER_PROFILES.get(driver_id, _GENERIC_PROFILE))


def get_display_name(driver_id: str) -> str:
    return DRIVER_DISPLAY_NAMES.get(driver_id, driver_id.replace("_", " ").title())


def build_race_lineup(
    user_driver_id: str,
    user_profile: Optional[dict] = None,
    user_start_position: int = 10,
    user_start_compound: str = "MEDIUM",
    rivals: Optional[list[str]] = None,
    n_rivals: int = 19,
) -> list[DriverEntry]:
    """
    Build a 20-driver race lineup with the user in their slot.

    Args:
        user_driver_id:      Driver ID for the user (can be any string).
        user_profile:        Profile dict; if None, uses known profile or generic.
        user_start_position: Grid slot (1-20).
        user_start_compound: Starting tire.
        rivals:              Explicit list of rival driver IDs. If None, selects
                             from DEFAULT_GRID excluding user_driver_id.
        n_rivals:            Number of rivals to include (max 19).

    Returns:
        List of DriverEntry sorted by starting position.
    """
    if rivals is None:
        pool = [d for d in DEFAULT_GRID if d != user_driver_id]
        rivals = pool[:n_rivals]

    entries: list[DriverEntry] = []

    # Place rivals in grid positions, skipping user's slot
    rival_positions = [p for p in range(1, 21) if p != user_start_position]
    for i, rival_id in enumerate(rivals[:n_rivals]):
        pos = rival_positions[i] if i < len(rival_positions) else i + 2
        entries.append(
            DriverEntry(
                driver_id=rival_id,
                display_name=get_display_name(rival_id),
                profile=get_profile(rival_id),
                start_position=pos,
                start_compound=DEFAULT_START_COMPOUNDS.get(pos, "MEDIUM"),
                car_offset_ms=CAR_PERFORMANCE_OFFSET_MS.get(rival_id, 0.0),
                is_user=False,
            )
        )

    # User driver
    resolved_profile = user_profile or get_profile(user_driver_id)
    entries.append(
        DriverEntry(
            driver_id=user_driver_id,
            display_name=get_display_name(user_driver_id),
            profile={
                k: float(max(0.0, min(1.0, resolved_profile.get(k, 0.5))))
                for k in (
                    "aggression",
                    "consistency",
                    "tire_management",
                    "pressure_response",
                )
            },
            start_position=user_start_position,
            start_compound=user_start_compound,
            car_offset_ms=CAR_PERFORMANCE_OFFSET_MS.get(user_driver_id, 0.0),
            is_user=True,
        )
    )

    return sorted(entries, key=lambda e: e.start_position)
