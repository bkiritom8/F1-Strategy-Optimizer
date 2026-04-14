"""
Driver profiles for the F1 race simulation.

Profile dimensions (all float [0, 1]):
  aggression        — throttle intensity, willing to risk tires/collisions
  consistency       — lap-to-lap variance (1 = very consistent)
  tire_management   — ability to extend tire stints beyond optimal
  pressure_response — pace when being chased or chasing within 1 s

Car performance is now separated from driver skill.  Each driver maps to a
constructor via DRIVER_CONSTRUCTOR_MAP, and constructor-level pace/degradation
data is loaded from GCS (gs://f1optimizer-data-lake/processed/car_performance.json).
Users can override the car for any driver — e.g. run Verstappen in a Mercedes.

Usage:
    profile = get_profile("max_verstappen")
    lineup  = build_race_lineup("lando_norris", car_id_overrides={"lando_norris": "mercedes"})
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

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

# Maps each driver to their current/primary constructor.
# Used as the default car when no override is specified.
DRIVER_CONSTRUCTOR_MAP: dict[str, str] = {
    "max_verstappen": "red_bull",
    "liam_lawson": "red_bull",
    "lando_norris": "mclaren",
    "oscar_piastri": "mclaren",
    "charles_leclerc": "ferrari",
    "lewis_hamilton": "ferrari",  # 2025 move
    "george_russell": "mercedes",
    "kimi_antonelli": "mercedes",
    "fernando_alonso": "aston_martin",
    "lance_stroll": "aston_martin",
    "pierre_gasly": "alpine",
    "jack_doohan": "alpine",
    "oliver_bearman": "haas",
    "esteban_ocon": "haas",
    "yuki_tsunoda": "rb",
    "isack_hadjar": "rb",
    "nico_hulkenberg": "sauber",
    "gabriel_bortoleto": "sauber",
    "alex_albon": "williams",
    "carlos_sainz": "williams",
    # Legends — map to their iconic constructors
    "michael_schumacher": "ferrari",
    "ayrton_senna": "mclaren",
    "alain_prost": "ferrari",
    "sebastian_vettel": "red_bull",
    "valtteri_bottas": "mercedes",
}

# Hardcoded fallback car pace offsets (ms/lap vs field median, negative = faster).
# Used when GCS is unavailable.  Reflects approximate 2024/2025 competitiveness.
CAR_PERFORMANCE_OFFSET_MS: dict[str, float] = {
    "max_verstappen": -594.0,
    "liam_lawson": -480.0,
    "lando_norris": -550.0,
    "oscar_piastri": -540.0,
    "charles_leclerc": -480.0,
    "lewis_hamilton": -470.0,
    "george_russell": -380.0,
    "kimi_antonelli": -360.0,
    "fernando_alonso": -320.0,
    "lance_stroll": -280.0,
    "alex_albon": -160.0,
    "carlos_sainz": -170.0,
    "yuki_tsunoda": -140.0,
    "isack_hadjar": -110.0,
    "pierre_gasly": -100.0,
    "jack_doohan": -80.0,
    "esteban_ocon": -60.0,
    "oliver_bearman": -50.0,
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

# ── Car performance data structures ──────────────────────────────────────────


@dataclass
class CarDegParams:
    """Tire degradation parameters for one compound on one constructor/season."""

    deg_slope_per_lap: float = 0.040  # additional degradation per lap (s/lap)
    base_deg_s: float = 0.100  # degradation at tire age 0 (s)

    def deg_at_age(self, tire_age: int) -> float:
        """Return degradation in seconds at the given tire age (clamped to ≥ 0)."""
        return max(0.0, self.base_deg_s + self.deg_slope_per_lap * tire_age)


# Sensible defaults per compound when constructor-specific data is unavailable
_DEFAULT_COMPOUND_DEG: dict[str, CarDegParams] = {
    "SOFT": CarDegParams(deg_slope_per_lap=0.070, base_deg_s=0.050),
    "MEDIUM": CarDegParams(deg_slope_per_lap=0.045, base_deg_s=0.100),
    "HARD": CarDegParams(deg_slope_per_lap=0.025, base_deg_s=0.150),
    "INTER": CarDegParams(deg_slope_per_lap=0.055, base_deg_s=0.200),
    "WET": CarDegParams(deg_slope_per_lap=0.040, base_deg_s=0.250),
}


@dataclass
class CarProfile:
    """Performance characteristics for a constructor in a given season."""

    constructor_id: str
    display_name: str = ""
    # Pace delta vs field median in ms/lap (negative = faster than median)
    pace_delta_ms: float = 0.0
    compound_params: dict = field(default_factory=lambda: dict(_DEFAULT_COMPOUND_DEG))

    def deg_params(self, compound: str) -> CarDegParams:
        """Return degradation parameters for the given compound."""
        key = compound.upper()
        return self.compound_params.get(
            key, self.compound_params.get("MEDIUM", CarDegParams())
        )


# ── GCS car performance loader ────────────────────────────────────────────────

_car_performance_cache: Optional[dict[str, CarProfile]] = None


def load_car_performance(season: str = "2024") -> dict[str, CarProfile]:
    """
    Load constructor car-performance data from GCS and return a mapping of
    constructor_id → CarProfile.

    Results are cached in-process.  Falls back to hardcoded profiles if GCS
    is unavailable (e.g. in unit tests / offline environments).
    """
    global _car_performance_cache
    if _car_performance_cache is not None:
        return _car_performance_cache

    profiles = _load_car_performance_gcs(season)
    if not profiles:
        profiles = _hardcoded_car_profiles()

    _car_performance_cache = profiles
    return _car_performance_cache


def _load_car_performance_gcs(season: str) -> dict[str, CarProfile]:
    try:
        from google.cloud import storage

        client = storage.Client(project="f1optimizer")
        bucket = client.bucket("f1optimizer-data-lake")
        blob = bucket.blob("processed/car_performance.json")
        data = json.loads(blob.download_as_text())
        return _parse_car_performance(data, season)
    except Exception as exc:
        logger.debug(
            "Car performance GCS load failed (%s) — using hardcoded fallback", exc
        )
        return {}


def _parse_car_performance(data: dict, target_season: str) -> dict[str, CarProfile]:
    result: dict[str, CarProfile] = {}
    for cid, cdata in data.get("constructors", {}).items():
        seasons = cdata.get("seasons", {})
        # Find the most recent season ≤ target_season
        available = sorted(
            [s for s in seasons if int(s) <= int(target_season)], reverse=True
        )
        if not available:
            continue
        sdata = seasons[available[0]]

        # pace_delta_s: negative = faster than field median
        pace_ms = sdata.get("pace_delta_s", 0.0) * 1000.0

        compound_params: dict[str, CarDegParams] = {}
        for comp, comp_data in sdata.get("compounds", {}).items():
            compound_params[comp.upper()] = CarDegParams(
                deg_slope_per_lap=float(comp_data.get("deg_slope_per_lap", 0.040)),
                # Clamp base to ≥ 0 — negative values mean "faster than field at
                # fresh age" but we model that through pace_delta_ms instead.
                base_deg_s=max(0.0, float(comp_data.get("base_deg_s", 0.100))),
            )
        # Fill missing compounds with defaults
        for comp, default_params in _DEFAULT_COMPOUND_DEG.items():
            compound_params.setdefault(comp, default_params)

        result[cid] = CarProfile(
            constructor_id=cid,
            display_name=cdata.get("display_name", cid),
            pace_delta_ms=pace_ms,
            compound_params=compound_params,
        )
    return result


def _hardcoded_car_profiles() -> dict[str, CarProfile]:
    """Fallback profiles mirroring CAR_PERFORMANCE_OFFSET_MS for the 2024/2025 season."""
    _constructors = {
        "red_bull": (-594.0, "Red Bull Racing"),
        "ferrari": (-795.0, "Ferrari"),
        "mclaren": (-376.0, "McLaren"),
        "mercedes": (-611.0, "Mercedes"),
        "aston_martin": (-199.0, "Aston Martin"),
        "williams": (-116.0, "Williams"),
        "haas": (-263.0, "Haas"),
        "alpine": (+56.0, "Alpine"),
        "rb": (+110.0, "RB"),
        "sauber": (+516.0, "Sauber"),
    }
    return {
        cid: CarProfile(
            constructor_id=cid,
            display_name=name,
            pace_delta_ms=pace_ms,
        )
        for cid, (pace_ms, name) in _constructors.items()
    }


# ── Driver entry ──────────────────────────────────────────────────────────────


@dataclass
class DriverEntry:
    """One driver's configuration entering the race."""

    driver_id: str
    display_name: str
    profile: dict  # aggression, consistency, tire_management, pressure_response
    start_position: int
    start_compound: str  # SOFT / MEDIUM / HARD
    car_offset_ms: float = 0.0  # lap time offset vs baseline (negative = faster)
    car_id: str = ""  # constructor ID (e.g. "red_bull", "mclaren")
    car_profile: Optional[CarProfile] = None  # loaded from GCS if available
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
    car_id_overrides: Optional[dict[str, str]] = None,
    season: str = "2024",
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
        car_id_overrides:    Optional mapping of driver_id → constructor_id to
                             override the default car assignment.  Allows putting
                             any driver in any car (e.g. Verstappen in a Mercedes).
        season:              Season year for GCS car data lookup (default "2024").

    Returns:
        List of DriverEntry sorted by starting position.
    """
    overrides = car_id_overrides or {}

    # Load car performance data (cached after first call)
    car_profiles = load_car_performance(season)

    def _resolve_car(driver_id: str) -> tuple[str, float, Optional[CarProfile]]:
        """Return (car_id, car_offset_ms, car_profile) for a driver."""
        constructor_id = overrides.get(driver_id) or DRIVER_CONSTRUCTOR_MAP.get(
            driver_id, ""
        )
        profile = car_profiles.get(constructor_id)
        if profile:
            return constructor_id, profile.pace_delta_ms, profile
        # GCS unavailable — fall back to hardcoded per-driver offset
        offset = CAR_PERFORMANCE_OFFSET_MS.get(driver_id, 0.0)
        return constructor_id, offset, None

    if rivals is None:
        pool = [d for d in DEFAULT_GRID if d != user_driver_id]
        rivals = pool[:n_rivals]

    entries: list[DriverEntry] = []

    # Place rivals in grid positions, skipping user's slot
    rival_positions = [p for p in range(1, 21) if p != user_start_position]
    for i, rival_id in enumerate(rivals[:n_rivals]):
        pos = rival_positions[i] if i < len(rival_positions) else i + 2
        car_id, offset_ms, car_prof = _resolve_car(rival_id)
        entries.append(
            DriverEntry(
                driver_id=rival_id,
                display_name=get_display_name(rival_id),
                profile=get_profile(rival_id),
                start_position=pos,
                start_compound=DEFAULT_START_COMPOUNDS.get(pos, "MEDIUM"),
                car_offset_ms=offset_ms,
                car_id=car_id,
                car_profile=car_prof,
                is_user=False,
            )
        )

    # User driver
    resolved_profile = user_profile or get_profile(user_driver_id)
    car_id, offset_ms, car_prof = _resolve_car(user_driver_id)
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
            car_offset_ms=offset_ms,
            car_id=car_id,
            car_profile=car_prof,
            is_user=True,
        )
    )

    return sorted(entries, key=lambda e: e.start_position)
