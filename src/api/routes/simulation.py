"""
Interactive Race Simulation WebSocket Endpoint.

Drives F1RaceEnv (via RaceRunner) lap-by-lap and pauses at strategic key moments
to ask the user for pit/driving decisions. Uses the trained PPO agent for
recommendations, with a heuristic fallback when GCS is unreachable.

WebSocket protocol
──────────────────
Client → Server:
  {"type": "start", "race_id": "2025_4", "driver_id": "max_verstappen",
   "start_position": 5, "start_compound": "MEDIUM", "driver_profile": {...}}
  {"type": "accept"}                          # accept RL recommendation
  {"type": "override", "action": 5}          # user picks different action

Server → Client:
  {"type": "setup_ack", "circuit_name": ..., "total_laps": ..., "drivers": [...]}
  {"type": "laps", "data": [{lap, user, standings, rl_action, rl_action_name}, ...]}
  {"type": "prompt", "lap": ..., "reason": ..., "rl_action": ..., "action_probs": ..., ...}
  {"type": "finished", "final_standings": ..., "decision_history": ..., ...}
  {"type": "error", "message": "..."}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, Optional, cast

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ml.rl.driver_profiles import (
    DRIVER_PROFILES,
    build_race_lineup,
    get_display_name,
    get_profile,
)
from ml.rl.race_runner import CIRCUIT_REGISTRY, RaceRunner
from ml.rl.reward import COMPOUND_OPTIMAL_LAPS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation"])

# ── Constants ─────────────────────────────────────────────────────────────────

ACTION_NAMES = [
    "STAY_NEUTRAL",
    "STAY_BALANCED",
    "STAY_PUSH",
    "PIT_SOFT",
    "PIT_MEDIUM",
    "PIT_HARD",
    "PIT_INTER",
]

# Year-keyed team affiliations. The outer key is driver_id; inner key is the
# first season that entry applies. team_for_driver() picks the latest entry
# whose year is ≤ the requested season, so gaps are filled automatically.
DRIVER_TEAM_BY_YEAR: dict[str, dict[int, str]] = {
    "max_verstappen": {2022: "Red Bull Racing"},
    "liam_lawson": {2023: "AlphaTauri", 2025: "Red Bull Racing"},
    "lando_norris": {2022: "McLaren"},
    "oscar_piastri": {2023: "McLaren"},
    "charles_leclerc": {2022: "Ferrari"},
    "lewis_hamilton": {2022: "Mercedes", 2025: "Ferrari"},
    "george_russell": {2022: "Mercedes"},
    "kimi_antonelli": {2025: "Mercedes"},
    "fernando_alonso": {2022: "Alpine", 2023: "Aston Martin"},
    "lance_stroll": {2022: "Aston Martin"},
    "pierre_gasly": {2022: "AlphaTauri", 2023: "Alpine"},
    "jack_doohan": {2025: "Alpine"},
    "oliver_bearman": {2025: "Haas F1 Team"},
    "esteban_ocon": {2022: "Alpine", 2025: "Haas F1 Team"},
    "yuki_tsunoda": {2022: "AlphaTauri", 2024: "Visa Cash App RB"},
    "isack_hadjar": {2025: "Visa Cash App RB"},
    "nico_hulkenberg": {2023: "Haas F1 Team", 2025: "Audi"},
    "gabriel_bortoleto": {2025: "Audi"},
    "alex_albon": {2022: "Williams"},
    "carlos_sainz": {2022: "Ferrari", 2025: "Williams"},
    # Legendary drivers — single iconic entry used for any year
    "michael_schumacher": {2000: "Ferrari"},
    "ayrton_senna": {1988: "McLaren"},
    "alain_prost": {1988: "McLaren"},
    "sebastian_vettel": {2010: "Red Bull Racing"},
    "valtteri_bottas": {2022: "Alfa Romeo", 2024: "Sauber"},
}


def team_for_driver(driver_id: str, year: int) -> str:
    """Return the correct constructor name for a driver in a given season year."""
    entries = DRIVER_TEAM_BY_YEAR.get(driver_id)
    if not entries:
        return "Unknown"
    valid = {y: t for y, t in entries.items() if y <= year}
    if valid:
        return entries[max(valid)]
    # Requested year is before the earliest known entry — use earliest
    return entries[min(entries)]


DRIVER_CODE: dict[str, str] = {
    "max_verstappen": "VER",
    "liam_lawson": "LAW",
    "lando_norris": "NOR",
    "oscar_piastri": "PIA",
    "charles_leclerc": "LEC",
    "lewis_hamilton": "HAM",
    "george_russell": "RUS",
    "kimi_antonelli": "ANT",
    "fernando_alonso": "ALO",
    "lance_stroll": "STR",
    "pierre_gasly": "GAS",
    "jack_doohan": "DOO",
    "oliver_bearman": "BEA",
    "esteban_ocon": "OCO",
    "yuki_tsunoda": "TSU",
    "isack_hadjar": "HAD",
    "nico_hulkenberg": "HUL",
    "gabriel_bortoleto": "BOR",
    "alex_albon": "ALB",
    "carlos_sainz": "SAI",
    "michael_schumacher": "MSC",
    "ayrton_senna": "SEN",
    "alain_prost": "PRO",
    "sebastian_vettel": "VET",
    "valtteri_bottas": "BOT",
}

# ── RL Agent cache ─────────────────────────────────────────────────────────────

_rl_agent: Any = None
_rl_load_attempted = False

PAUSED_SESSION_TTL_SECONDS = 15 * 60
_paused_sim_sessions: dict[str, dict[str, Any]] = {}


def _cleanup_paused_sessions() -> None:
    now = time.time()
    expired = [
        sid
        for sid, sess in _paused_sim_sessions.items()
        if now - float(sess.get("paused_at", now)) > PAUSED_SESSION_TTL_SECONDS
    ]
    for sid in expired:
        _paused_sim_sessions.pop(sid, None)


def _try_load_rl_agent() -> Any:
    global _rl_agent, _rl_load_attempted
    if _rl_load_attempted:
        return _rl_agent
    _rl_load_attempted = True
    try:
        from ml.rl.agent import F1StrategyAgent

        agent = F1StrategyAgent()
        local_dir = os.environ.get("RL_MODEL_DIR", "models/rl_strategy/v3")
        if os.path.exists(os.path.join(local_dir, "policy.zip")):
            agent.load_local(local_dir)
            logger.info("RL agent loaded from local dir: %s", local_dir)
        else:
            agent.load("gs://f1optimizer-models/rl_strategy/latest")
            logger.info("RL agent loaded from GCS for simulation")
        _rl_agent = agent
    except Exception as exc:
        logger.warning("RL agent unavailable (%s) — using heuristic fallback", exc)
    return _rl_agent


# ── Heuristic action probabilities (fallback) ─────────────────────────────────


def _heuristic_probs(info: dict) -> np.ndarray:
    """Rule-based pit strategy probabilities when RL agent is not available."""
    compound = info.get("tire_compound", "MEDIUM").upper()
    tire_age = int(info.get("tire_age_laps", 0))
    safety_car = bool(info.get("safety_car", False))
    vsc = bool(info.get("vsc", False))
    total_laps = int(info.get("total_laps", 57))
    lap_num = int(info.get("lap_number", 1))
    remaining = total_laps - lap_num

    optimal = COMPOUND_OPTIMAL_LAPS.get(compound, 30)
    wear = tire_age / max(optimal, 1)

    # Base: stay balanced
    probs = np.array([0.10, 0.55, 0.25, 0.03, 0.04, 0.03, 0.0], dtype=np.float64)

    if safety_car:
        # SC: soft is the go-to under SC (free pit); medium for long stints; hard rare
        probs = np.array([0.00, 0.44, 0.01, 0.07, 0.25, 0.20, 0.03])
    elif vsc:
        # VSC: pit is advantageous but less so than SC (only ~6 s saved vs ~15 s).
        # Only recommend pitting if tires are meaningfully worn.
        if wear >= 0.70:
            probs = np.array([0.02, 0.10, 0.02, 0.12, 0.38, 0.28, 0.08])
        else:
            probs = np.array([0.08, 0.45, 0.30, 0.06, 0.07, 0.03, 0.01])
    elif wear >= 1.1:
        probs = np.array([0.00, 0.02, 0.00, 0.10, 0.48, 0.38, 0.02])
    elif wear >= 0.85:
        urgency = min(1.0, (wear - 0.85) / 0.25)
        pit_mass = urgency * 0.65
        probs = np.array(
            [
                max(0.0, 0.08 - pit_mass * 0.08),
                max(0.0, 0.20 - pit_mass * 0.15),
                max(0.0, 0.05 - pit_mass * 0.05),
                pit_mass * 0.15 + 0.03,
                pit_mass * 0.50 + 0.08,
                pit_mass * 0.32 + 0.06,
                0.01,
            ]
        )
    elif remaining <= 5:
        probs = np.array([0.05, 0.20, 0.70, 0.01, 0.02, 0.02, 0.0])

    probs = np.abs(probs)
    total = probs.sum()
    if total < 1e-9:
        probs = np.full(7, 1.0 / 7)
    else:
        probs /= total
    return probs


def _get_action_probs(obs: np.ndarray, info: dict) -> np.ndarray:
    agent = _try_load_rl_agent()
    if agent is not None:
        try:
            return agent.action_probabilities(obs)
        except Exception as exc:
            logger.debug("RL agent inference failed: %s", exc)
    return _heuristic_probs(info)


# ── Key-moment detection ──────────────────────────────────────────────────────


def _is_key_moment(
    info: dict,
    prev_info: dict,
    probs: np.ndarray,
    lap_records: dict,
    user_id: str,
    prompt_count: int,
    max_prompts: int = 7,
) -> tuple[bool, str]:
    """Return (True, reason) when the user should be asked for a strategy decision."""
    if prompt_count >= max_prompts:
        return False, ""

    lap = int(info.get("lap_number", 1))
    total = int(info.get("total_laps", 57))
    compound = info.get("tire_compound", "MEDIUM").upper()
    tire_age = int(info.get("tire_age_laps", 0))
    sc = bool(info.get("safety_car", False))
    prev_sc = bool(prev_info.get("safety_car", False))
    vsc = bool(info.get("vsc", False))
    prev_vsc = bool(prev_info.get("vsc", False))
    optimal = COMPOUND_OPTIMAL_LAPS.get(compound, 30)
    remaining = total - lap

    # 1. Safety Car just deployed — prime pit window
    if sc and not prev_sc:
        return True, f"Safety Car deployed on lap {lap} — free pit window!"

    # 1b. VSC deployed — partial pit window (weaker than SC; only prompt if tires are worn)
    if vsc and not prev_vsc and tire_age >= 15:
        return (
            True,
            f"Virtual Safety Car on lap {lap} — evaluate pit window (tires: {tire_age}L)",
        )

    # 2. RL recommends pitting — fire prompt when argmax is a pit action, tires
    #    are not fresh (tire_age >= 5), and SC/VSC is NOT active.
    #    • tire_age >= 5 prevents re-prompting immediately after a pit on fresh
    #      tires (e.g. consecutive SC laps where argmax stays PIT_MEDIUM even
    #      though the car pitted one lap ago).
    #    • not sc/vsc keeps SC/VSC-period pit advice exclusively in trigger 1/1b
    #      (just deployed), avoiding a second prompt if SC/VSC outlasts 5 laps.
    pit_prob = float(probs[3:].sum())
    best_action = int(probs.argmax())
    if (
        best_action >= 3
        and not sc
        and not vsc
        and tire_age >= 5
        and lap > 4
        and remaining > 8
    ):
        compound_name = {3: "SOFT", 4: "MEDIUM", 5: "HARD", 6: "INTER"}.get(
            best_action, "MEDIUM"
        )
        return (
            True,
            f"RL recommends pit for {compound_name} ({pit_prob:.0%} confidence)",
        )

    # 3. Tires past optimal stint — degradation critical
    if tire_age >= int(optimal * 1.05) and remaining > 5:
        pct = int(tire_age / optimal * 100)
        return (
            True,
            f"{compound} tires at {tire_age} laps ({pct}% of optimal) — degradation critical",
        )

    # 4. Undercut opportunity: car just ahead pitted
    gap_ahead = float(info.get("gap_to_ahead", 99.0))
    if 0 < gap_ahead < 2.5:
        for did, rec in lap_records.items():
            if did != user_id and rec.pit_stop:
                rec_pos = getattr(rec, "position", 99)
                user_pos = int(info.get("position", 20))
                if abs(rec_pos - user_pos) <= 2:
                    return (
                        True,
                        f"Undercut opportunity! Car ahead pitted. Gap = {gap_ahead:.1f}s",
                    )

    # 5. Late-race final strategy review
    if remaining == 13 and prompt_count < 4:
        return True, f"Final stint check — {remaining} laps to go. Review strategy?"

    return False, ""


# ── WebSocket endpoint ────────────────────────────────────────────────────────


@router.websocket("/ws")
async def race_simulation_ws(websocket: WebSocket) -> None:
    """
    Interactive race simulation over WebSocket.

    The simulation runs in lock-step:
      1. Client sends "start" with race config.
      2. Server batches laps between key moments, sending "laps" messages.
      3. At each key moment, server sends "prompt" and waits for "accept" / "override".
      4. After the final lap, server sends "finished" with full race stats.
    """
    await websocket.accept()
    _cleanup_paused_sessions()

    runner: Optional[RaceRunner] = None
    session_id = ""
    race_id = "2025_4"
    driver_id = "max_verstappen"
    circuit_id = "bahrain"
    race_name = "Grand Prix"
    total_laps = 57
    year = 2025
    obs = np.array([])
    info: dict[str, Any] = {}
    prev_info: dict[str, Any] = {}
    prompt_count = 0
    decision_history: list[dict[str, Any]] = []
    batch: list[dict[str, Any]] = []
    drivers_payload: list[dict[str, Any]] = []
    pending_prompt_payload: Optional[dict[str, Any]] = None

    async def _wait_for_decision() -> dict[str, Any]:
        decision_raw = None
        deadline = asyncio.get_event_loop().time() + 90.0
        while True:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                decision_raw = await asyncio.wait_for(
                    websocket.receive_text(), timeout=min(25.0, remaining)
                )
                break
            except asyncio.TimeoutError:
                if asyncio.get_event_loop().time() >= deadline:
                    break
                await websocket.send_json({"type": "keepalive"})
        return json.loads(decision_raw) if decision_raw else {"type": "accept"}

    try:
        raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
        msg: dict[str, Any] = json.loads(raw)
        msg_type = str(msg.get("type", ""))

        if msg_type == "resume":
            requested_session_id = str(msg.get("session_id", ""))
            saved = _paused_sim_sessions.pop(requested_session_id, None)
            if not saved:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": "Simulation session expired or not found. Start a new run.",
                    }
                )
                return

            session_id = requested_session_id
            runner = cast(RaceRunner, saved["runner"])
            race_id = cast(str, saved["race_id"])
            driver_id = cast(str, saved["driver_id"])
            circuit_id = cast(str, saved["circuit_id"])
            race_name = cast(str, saved["race_name"])
            total_laps = int(saved["total_laps"])
            year = int(saved["year"])
            obs = cast(np.ndarray, saved["obs"])
            info = cast(dict[str, Any], saved["info"])
            prev_info = cast(dict[str, Any], saved["prev_info"])
            prompt_count = int(saved["prompt_count"])
            decision_history = cast(list[dict[str, Any]], saved["decision_history"])
            batch = cast(list[dict[str, Any]], saved["batch"])
            drivers_payload = cast(list[dict[str, Any]], saved["drivers_payload"])
            pending_prompt_payload = cast(
                Optional[dict[str, Any]], saved.get("pending_prompt_payload")
            )

            await websocket.send_json(
                {
                    "type": "resumed",
                    "session_id": session_id,
                    "race_id": race_id,
                    "circuit_name": race_name,
                    "circuit_id": circuit_id,
                    "total_laps": total_laps,
                    "user_driver_id": driver_id,
                    "user_display_name": get_display_name(driver_id),
                    "drivers": drivers_payload,
                }
            )

        elif msg_type == "start":
            session_id = uuid.uuid4().hex
            race_id = str(msg.get("race_id", "2025_4"))
            driver_id = str(msg.get("driver_id", "max_verstappen"))
            start_position: int = max(1, min(20, int(msg.get("start_position", 10))))
            start_compound: str = str(msg.get("start_compound", "MEDIUM")).upper()
            driver_profile: Optional[dict] = msg.get("driver_profile") or None
            car_id: Optional[str] = msg.get("car_id") or None

            circuit_info = CIRCUIT_REGISTRY.get(race_id) or {}
            if not circuit_info:
                circuit_info = CIRCUIT_REGISTRY.get(
                    "2025_4",
                    {
                        "total_laps": 57,
                        "base_lap_time_ms": 95_800,
                        "race_name": "Grand Prix",
                        "circuit_id": "bahrain",
                    },
                )

            circuit_id = str(circuit_info.get("circuit_id", "bahrain"))
            race_name = str(circuit_info.get("race_name", "Grand Prix"))
            total_laps = int(circuit_info.get("total_laps", 57))
            base_lap_ms = float(circuit_info.get("base_lap_time_ms", 90_000))
            try:
                year = int(race_id.split("_")[0])
            except (ValueError, IndexError):
                year = 2025

            resolved_profile = driver_profile or get_profile(driver_id)
            car_id_overrides = {driver_id: car_id} if car_id else None
            lineup = build_race_lineup(
                user_driver_id=driver_id,
                user_profile=resolved_profile,
                user_start_position=start_position,
                user_start_compound=start_compound,
                car_id_overrides=car_id_overrides,
            )

            drivers_payload = [
                {
                    "driver_id": d.driver_id,
                    "display_name": d.display_name,
                    "code": DRIVER_CODE.get(d.driver_id, d.driver_id[:3].upper()),
                    "start_position": d.start_position,
                    "start_compound": d.start_compound,
                    "is_user": d.is_user,
                    "team": team_for_driver(d.driver_id, year),
                }
                for d in lineup
            ]

            await websocket.send_json(
                {
                    "type": "setup_ack",
                    "session_id": session_id,
                    "race_id": race_id,
                    "circuit_name": race_name,
                    "circuit_id": circuit_id,
                    "total_laps": total_laps,
                    "base_lap_time_ms": base_lap_ms,
                    "user_driver_id": driver_id,
                    "user_display_name": get_display_name(driver_id),
                    "drivers": drivers_payload,
                }
            )

            runner = RaceRunner(
                race_id=race_id,
                drivers=lineup,
                adapters={},
                circuit_id=circuit_id,
                race_name=race_name,
            )
            obs, info = runner.reset()
            prev_info = dict(info)
        else:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": 'First message must be type="start" or type="resume"',
                }
            )
            return

        if runner is None:
            raise RuntimeError("Simulation runner is not initialized")

        while not runner.finished:
            if pending_prompt_payload is not None:
                if batch:
                    await websocket.send_json({"type": "laps", "data": batch})
                    batch = []

                await websocket.send_json(pending_prompt_payload)
                decision = await _wait_for_decision()

                rl_action = int(pending_prompt_payload["rl_action"])
                reason = str(pending_prompt_payload["reason"])
                d_type = decision.get("type", "accept")
                if d_type == "override" and "action" in decision:
                    action = max(0, min(6, int(decision["action"])))
                    accepted = False
                else:
                    action = rl_action
                    accepted = True

                decision_history.append(
                    {
                        "lap": int(info.get("lap_number", 1)),
                        "reason": reason,
                        "rl_action": rl_action,
                        "rl_action_name": ACTION_NAMES[rl_action],
                        "user_action": action,
                        "user_action_name": ACTION_NAMES[action],
                        "accepted": accepted,
                    }
                )
                prompt_count += 1
                pending_prompt_payload = None
            else:
                probs = _get_action_probs(obs, info)
                rl_action = int(probs.argmax())
                is_key, reason = _is_key_moment(
                    info, prev_info, probs, {}, driver_id, prompt_count
                )

                if is_key:
                    alternatives = sorted(
                        [
                            {
                                "action": i,
                                "name": ACTION_NAMES[i],
                                "prob": round(float(probs[i]), 4),
                            }
                            for i in range(7)
                            if i != rl_action
                        ],
                        key=lambda x: -cast(float, x["prob"]),
                    )[:3]

                    pit_prob = float(probs[3:].sum())
                    confidence = float(probs[rl_action]) if rl_action < 3 else pit_prob
                    pending_prompt_payload = {
                        "type": "prompt",
                        "lap": int(info.get("lap_number", 1)),
                        "reason": reason,
                        "rl_action": rl_action,
                        "rl_action_name": ACTION_NAMES[rl_action],
                        "action_probs": [round(float(p), 4) for p in probs],
                        "confidence": round(confidence, 4),
                        "alternatives": alternatives,
                        "current_state": {
                            "position": info.get("position"),
                            "compound": info.get("tire_compound"),
                            "tire_age": info.get("tire_age_laps"),
                            "fuel_kg": round(
                                float(info.get("fuel_remaining_kg", 0)), 1
                            ),
                            "gap_to_leader": round(
                                float(info.get("gap_to_leader", 0)), 2
                            ),
                            "gap_to_ahead": round(
                                float(info.get("gap_to_ahead", 99)), 2
                            ),
                            "safety_car": bool(info.get("safety_car", False)),
                            "vsc": bool(info.get("vsc", False)),
                            "total_laps": total_laps,
                        },
                    }
                    continue

                action = rl_action if rl_action < 3 else 1

            lap_records, new_obs, new_info = runner.step_lap(action)

            standings = sorted(
                [
                    {
                        "driver_id": rec.driver_id,
                        "display_name": rec.display_name,
                        "code": DRIVER_CODE.get(
                            rec.driver_id, rec.driver_id[:3].upper()
                        ),
                        "position": rec.position,
                        "compound": rec.tire_compound,
                        "tire_age": rec.tire_age_laps,
                        "gap_to_leader": round(float(rec.gap_to_leader), 2),
                        "lap_time_ms": int(rec.lap_time_ms),
                        "pit_stop": rec.pit_stop,
                        "new_compound": rec.new_compound,
                        "team": team_for_driver(rec.driver_id, year),
                        "is_user": rec.driver_id == driver_id,
                    }
                    for rec in lap_records.values()
                ],
                key=lambda x: int(x["position"]),  # type: ignore[arg-type]
            )

            lap_snap = {
                "lap": int(info.get("lap_number", 1)),
                "safety_car": bool(new_info.get("safety_car", False)),
                "vsc": bool(new_info.get("vsc", False)),
                "standings": standings,
                "user": {
                    "position": new_info.get("position"),
                    "compound": new_info.get("tire_compound"),
                    "tire_age": new_info.get("tire_age_laps"),
                    "fuel_kg": round(float(new_info.get("fuel_remaining_kg", 0)), 1),
                    "lap_time_ms": int(new_info.get("lap_time_ms", 0)),
                    "gap_to_leader": round(float(new_info.get("gap_to_leader", 0)), 2),
                    "gap_to_ahead": round(float(new_info.get("gap_to_ahead", 99)), 2),
                    "safety_car": bool(new_info.get("safety_car", False)),
                    "vsc": bool(new_info.get("vsc", False)),
                    "action_taken": action,
                    "action_name": ACTION_NAMES[action],
                },
                "rl_action": rl_action,
                "rl_action_name": ACTION_NAMES[rl_action],
            }
            batch.append(lap_snap)

            prev_info = dict(info)
            obs = new_obs
            info = new_info

            if len(batch) >= 5:
                await websocket.send_json({"type": "laps", "data": batch})
                batch = []

        if batch:
            await websocket.send_json({"type": "laps", "data": batch})

        result = runner.result()
        await websocket.send_json(
            {
                "type": "finished",
                "final_standings": result.final_standings,
                "strategy_summary": result.strategy_summary,
                "user_final_position": result.user_final_position,
                "total_laps": result.total_laps,
                "circuit_name": race_name,
                "decision_history": decision_history,
            }
        )
        if session_id:
            _paused_sim_sessions.pop(session_id, None)

    except WebSocketDisconnect:
        if runner is not None and not runner.finished and session_id:
            _paused_sim_sessions[session_id] = {
                "runner": runner,
                "race_id": race_id,
                "driver_id": driver_id,
                "circuit_id": circuit_id,
                "race_name": race_name,
                "total_laps": total_laps,
                "year": year,
                "obs": obs,
                "info": info,
                "prev_info": prev_info,
                "prompt_count": prompt_count,
                "decision_history": decision_history,
                "batch": batch,
                "drivers_payload": drivers_payload,
                "pending_prompt_payload": pending_prompt_payload,
                "paused_at": time.time(),
            }
            logger.info("Race simulation paused (session_id=%s)", session_id)
        else:
            logger.info("Race simulation WebSocket disconnected by client")
    except asyncio.TimeoutError:
        logger.warning("Race simulation WebSocket timed out")
        try:
            await websocket.send_json(
                {"type": "error", "message": "Connection timed out"}
            )
        except Exception:  # nosec B110
            pass  # WebSocket already closed; ignore send failure
    except Exception as exc:
        logger.error("Race simulation error: %s", exc, exc_info=True)
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:  # nosec B110
            pass  # WebSocket already closed; ignore send failure


# ── Available races endpoint (for frontend circuit selector) ──────────────────


@router.get("/races")
async def list_available_races() -> list[dict]:
    """Return the list of simul-able race IDs with circuit metadata."""
    races = []
    for race_id, info in CIRCUIT_REGISTRY.items():
        if race_id.startswith("2025_"):
            races.append(
                {
                    "race_id": race_id,
                    "circuit_id": info.get("circuit_id", ""),
                    "race_name": info.get("race_name", ""),
                    "total_laps": info.get("total_laps", 57),
                    "base_lap_time_ms": info.get("base_lap_time_ms", 90_000),
                }
            )
    return sorted(races, key=lambda r: r["race_id"])


@router.get("/drivers")
async def list_drivers() -> list[dict]:
    """Return available driver IDs with team and display info."""
    from ml.rl.driver_profiles import DEFAULT_GRID

    result = []
    for driver_id in DEFAULT_GRID:
        result.append(
            {
                "driver_id": driver_id,
                "display_name": get_display_name(driver_id),
                "code": DRIVER_CODE.get(driver_id, driver_id[:3].upper()),
                "team": team_for_driver(driver_id, 2025),
            }
        )
    return result
