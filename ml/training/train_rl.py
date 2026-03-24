"""
RL Training Script — F1 Race Strategy Agent (PPO)

Trains a PPO agent to optimise F1 race strategy across a range of circuits.

Data sources (in priority order):
  1. GCS feature cache  (gs://f1optimizer-training/cache/race_*.parquet)
  2. Local /tmp/f1_cache (written by FeatureStore after first GCS pull)
  3. CIRCUIT_REGISTRY   (built-in lap counts / base times — fully offline)

Usage — quick smoke-test (no GCS needed, ~5 min on CPU):
    python ml/training/train_rl.py --timesteps 50000 --n-envs 2 --smoke-test

Usage — full training run:
    python ml/training/train_rl.py --timesteps 1000000 --n-envs 4 \
        --save-dir /tmp/f1_rl_checkpoints \
        --gcs-save gs://f1optimizer-models/rl_strategy/v1

Usage — resume from checkpoint:
    python ml/training/train_rl.py --resume /tmp/f1_rl_checkpoints/best/best_model.zip

Flags:
  --timesteps     Total PPO env steps (default: 1_000_000)
  --n-envs        Parallel envs / CPU cores to use (default: 4)
  --driver-id     Driver the agent controls (default: lando_norris)
  --start-pos     Starting grid position 1-20 (default: 10)
  --save-dir      Local checkpoint directory (default: /tmp/f1_rl_checkpoints)
  --gcs-save      GCS URI to upload final model (optional)
  --smoke-test    50k steps, 2 envs, no GCS — fast correctness check
  --resume        Path to existing policy.zip to continue training
  --no-models     Skip loading pkl models (physics fallback only)
  --eval-freq     Eval callback frequency in steps (default: 10000)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# ── Ensure repo root is on path ───────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("train_rl")

# ── Race ID sets ──────────────────────────────────────────────────────────────
# Training: 2022-2024 (diverse circuits, varied lap counts)
# Eval:     2025 (held-out season)

TRAIN_RACE_IDS = [
    # 2024 — full season
    f"2024_{r}" for r in range(1, 25)
] + [
    # 2023 — full season
    f"2023_{r}" for r in range(1, 24)
] + [
    # 2022 — full season
    f"2022_{r}" for r in range(1, 22)
]

EVAL_RACE_IDS = [
    # 2025 — held-out
    f"2025_{r}" for r in range(1, 13)   # first half of 2025 season
]

# For smoke-test: small subset covering fast + slow circuits
SMOKE_TRAIN_IDS = [
    "2024_11",   # Austria  — 71 laps, fast
    "2024_8",    # Monaco   — 78 laps, slow/street
    "2024_13",   # Belgium  — 44 laps, long lap
    "2024_16",   # Monza    — 53 laps, power circuit
    "2024_18",   # Singapore — 62 laps, high SC chance
    "2024_2",    # Bahrain  — 57 laps, baseline
]
SMOKE_EVAL_IDS = ["2025_1", "2025_4", "2025_11"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train F1 RL strategy agent (PPO)")
    p.add_argument("--timesteps",  type=int,   default=1_000_000, help="Total PPO steps")
    p.add_argument("--n-envs",     type=int,   default=4,         help="Parallel envs")
    p.add_argument("--driver-id",  type=str,   default="lando_norris")
    p.add_argument("--start-pos",  type=int,   default=10,        help="Grid position 1-20")
    p.add_argument("--save-dir",   type=str,   default="/tmp/f1_rl_checkpoints")
    p.add_argument("--gcs-save",   type=str,   default=None,      help="gs://bucket/path to upload")
    p.add_argument("--smoke-test", action="store_true")
    p.add_argument("--resume",     type=str,   default=None,      help="Path to policy.zip")
    p.add_argument("--no-models",  action="store_true",           help="Physics fallback only")
    p.add_argument("--eval-freq",  type=int,   default=10_000)
    return p.parse_args()


def load_adapters(models_dir: str = "models", skip: bool = False) -> dict:
    """Load all local pkl adapters, with graceful fallback per model."""
    if skip:
        logger.info("--no-models: running with physics fallbacks only")
        return {}
    try:
        from ml.rl.model_adapters import load_local_adapters
        adapters = load_local_adapters(models_dir)
        loaded = [k for k, v in adapters.items() if v.loaded]
        missing = [k for k, v in adapters.items() if not v.loaded]
        logger.info("Adapters loaded: %s", loaded)
        if missing:
            logger.info("Adapters in fallback mode: %s", missing)
        return adapters
    except Exception as exc:
        logger.warning("Adapter load failed (%s) — physics fallback", exc)
        return {}


def maybe_prefetch_gcs(race_ids: list[str], project: str = "f1optimizer") -> None:
    """
    Attempt to pull race features from GCS into local cache.
    Silently skips any race_id that fails (missing data, no GCS access, etc.).
    """
    try:
        from ml.features.feature_store import FeatureStore
        fs = FeatureStore(project=project)
        pulled, skipped = 0, 0
        for rid in race_ids:
            try:
                df = fs.load_race_features(rid)
                if df is not None and not df.empty:
                    pulled += 1
                else:
                    skipped += 1
            except Exception:
                skipped += 1
        logger.info("GCS prefetch: %d cached, %d skipped (will use registry fallback)", pulled, skipped)
    except Exception as exc:
        logger.info("GCS prefetch unavailable (%s) — using circuit registry", exc)


def run_smoke_test(adapters: dict, driver_id: str, start_pos: int) -> None:
    """Single episode sanity check before training."""
    logger.info("Running smoke-test episode…")
    try:
        from ml.rl.environment import F1RaceEnv
        env = F1RaceEnv(
            race_ids      = ["2024_4"],   # Japan — known stable circuit
            driver_id     = driver_id,
            adapters      = adapters,
            start_position = start_pos,
        )
        obs, info = env.reset()
        assert obs.shape == (29,), f"Expected obs shape (29,), got {obs.shape}"

        total_reward, steps = 0.0, 0
        done = False
        while not done:
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            steps += 1
            done = terminated or truncated

        lap     = info.get("total_laps", "?")
        pos_end = info.get("position", "?")
        logger.info(
            "Smoke-test OK — %d laps, final P%s, total reward %.1f",
            steps, pos_end, total_reward,
        )
        env.close()
    except Exception as exc:
        logger.error("Smoke-test FAILED: %s", exc)
        raise


def main() -> None:
    args = parse_args()

    if args.smoke_test:
        # Respect explicit --timesteps / --n-envs; only apply smoke defaults otherwise
        if args.timesteps == 1_000_000:
            args.timesteps = 10_000
        if args.n_envs == 4:
            args.n_envs = 2
        train_ids = SMOKE_TRAIN_IDS
        eval_ids  = SMOKE_EVAL_IDS
        logger.info("=== SMOKE TEST MODE: %dk steps, %d envs ===", args.timesteps // 1000, args.n_envs)
    else:
        train_ids = TRAIN_RACE_IDS
        eval_ids  = EVAL_RACE_IDS

    logger.info("Train races : %d  |  Eval races: %d", len(train_ids), len(eval_ids))
    logger.info("Driver      : %s  (P%d start)", args.driver_id, args.start_pos)
    logger.info("Timesteps   : %d  |  Envs: %d", args.timesteps, args.n_envs)

    # ── Load adapters ─────────────────────────────────────────────────────────
    models_dir = str(_REPO_ROOT / "models")
    adapters = load_adapters(models_dir, skip=args.no_models)

    # ── Prefetch GCS data into local cache (best-effort) ──────────────────────
    all_ids = list(set(train_ids + eval_ids))
    logger.info("Prefetching circuit data for %d races…", len(all_ids))
    maybe_prefetch_gcs(all_ids)

    # ── Smoke-test before committing to full training ─────────────────────────
    run_smoke_test(adapters, args.driver_id, args.start_pos)

    # ── Build agent ───────────────────────────────────────────────────────────
    from ml.rl.agent import F1StrategyAgent
    from ml.rl.driver_profiles import get_profile

    profile = get_profile(args.driver_id)
    agent   = F1StrategyAgent(
        driver_profile = profile,
        adapters       = adapters,
    )

    # ── Resume from checkpoint if requested ───────────────────────────────────
    if args.resume:
        logger.info("Resuming from checkpoint: %s", args.resume)
        # Load policy weights directly into SB3 PPO
        from stable_baselines3 import PPO
        agent._ppo = PPO.load(args.resume)
        logger.info("Checkpoint loaded")

    # ── Train ─────────────────────────────────────────────────────────────────
    t0 = time.time()
    logger.info("Starting training…")

    meta = agent.train(
        race_ids        = train_ids,
        total_timesteps = args.timesteps,
        eval_race_ids   = eval_ids,
        checkpoint_dir  = args.save_dir,
        n_envs          = args.n_envs,
        driver_id       = args.driver_id,
        # Pass None when --no-models so subprocess workers use physics fallbacks
        models_dir      = None if args.no_models else models_dir,
    )

    elapsed = time.time() - t0
    logger.info("Training complete in %.1f min", elapsed / 60)
    logger.info("Meta: %s", meta)

    # ── Save locally ──────────────────────────────────────────────────────────
    local_policy = os.path.join(args.save_dir, "final_policy.zip")
    local_vn     = os.path.join(args.save_dir, "final_vec_normalize.pkl")
    if agent._ppo:
        agent._ppo.save(local_policy)
        logger.info("Policy saved → %s", local_policy)
    if agent._vec_normalize:
        agent._vec_normalize.save(local_vn)
        logger.info("VecNormalize saved → %s", local_vn)

    # ── Upload to GCS (optional) ──────────────────────────────────────────────
    if args.gcs_save:
        logger.info("Uploading to GCS: %s", args.gcs_save)
        try:
            agent.save(args.gcs_save)
            logger.info("GCS upload complete")
        except Exception as exc:
            logger.warning("GCS upload failed: %s", exc)

    # ── Quick eval: run 3 deterministic episodes and report ───────────────────
    logger.info("Post-training evaluation (3 episodes)…")
    try:
        from ml.rl.environment import F1RaceEnv
        import numpy as np

        eval_env = F1RaceEnv(
            race_ids      = eval_ids[:3],
            driver_id     = args.driver_id,
            adapters      = adapters,
            start_position = args.start_pos,
        )
        positions = []
        for ep in range(3):
            obs, info = eval_env.reset()
            done = False
            while not done:
                if agent._ppo and agent._vec_normalize:
                    norm_obs = agent._vec_normalize.normalize_obs(obs)
                    action, _ = agent._ppo.predict(norm_obs, deterministic=True)
                else:
                    action = eval_env.action_space.sample()
                obs, _, terminated, truncated, info = eval_env.step(int(action))
                done = terminated or truncated
            pos = info.get("position", "?")
            positions.append(pos)
            logger.info("  Episode %d — final P%s", ep + 1, pos)
        if positions and all(isinstance(p, int) for p in positions):
            logger.info("Avg finishing position: P%.1f", float(np.mean(positions)))
        eval_env.close()
    except Exception as exc:
        logger.warning("Post-training eval failed: %s", exc)

    logger.info("Done. Checkpoints at: %s", args.save_dir)


if __name__ == "__main__":
    main()
