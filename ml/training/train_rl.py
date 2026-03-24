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
  --run-name      Vertex AI experiment run name (default: rl-strategy-vN)
  --skip-registry Skip Vertex AI model registry push
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

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

# ── Vertex AI — graceful fallback when GCP credentials not available ──────────
try:
    from google.cloud import aiplatform, storage
    aiplatform.init(
        project='f1optimizer',
        location='us-central1',
        experiment='f1-strategy-models',
    )
    _VERTEX_AVAILABLE = True
    logger.info("Vertex AI experiment tracking enabled")
except Exception as _va_exc:
    _VERTEX_AVAILABLE = False
    logger.info("Vertex AI unavailable (%s) — tracking skipped", _va_exc)

PLOTS_DIR = '/tmp/plots'
os.makedirs(PLOTS_DIR, exist_ok=True)

# ── Race ID sets ──────────────────────────────────────────────────────────────
TRAIN_RACE_IDS = [
    f"2024_{r}" for r in range(1, 25)
] + [
    f"2023_{r}" for r in range(1, 24)
] + [
    f"2022_{r}" for r in range(1, 22)
]

EVAL_RACE_IDS = [
    f"2025_{r}" for r in range(1, 13)
]

SMOKE_TRAIN_IDS = [
    "2024_11",   # Austria  — 71 laps, fast
    "2024_8",    # Monaco   — 78 laps, slow/street
    "2024_13",   # Belgium  — 44 laps, long lap
    "2024_16",   # Monza    — 53 laps, power circuit
    "2024_18",   # Singapore — 62 laps, high SC chance
    "2024_2",    # Bahrain  — 57 laps, baseline
]
SMOKE_EVAL_IDS = ["2025_1", "2025_4", "2025_11"]

# ── Circuit slices for bias detection ─────────────────────────────────────────
# Street circuits: narrow, low-overtake, high SC probability
STREET_RACE_IDS = ["2024_8", "2024_18", "2024_4", "2024_22", "2024_6", "2024_2"]
# Power circuits: high-speed, strategy-driven
POWER_RACE_IDS  = ["2024_16", "2024_13", "2024_11", "2024_1"]
# Mixed (remaining eval)
MIXED_RACE_IDS  = ["2025_1", "2025_4", "2025_7", "2025_10"]

# Season slices for bias detection
SEASON_SLICES = {
    "2022": [f"2022_{r}" for r in range(1, 6)],
    "2023": [f"2023_{r}" for r in range(1, 6)],
    "2024": [f"2024_{r}" for r in range(1, 6)],
}

# State feature names (matches state.py order)
OBS_FEATURE_NAMES = [
    "lap_progress", "laps_remaining_frac",
    "tire_age_norm", "fuel_norm",
    "compound_soft", "compound_medium", "compound_hard", "compound_inter", "compound_wet",
    "position_norm", "gap_leader_norm", "gap_ahead_norm",
    "lap_time_norm", "lap_time_delta_norm",
    "sector1_norm", "sector2_norm", "sector3_norm",
    "pit_stops_norm", "safety_car", "vsc", "is_wet", "track_temp_norm",
    "aggression", "consistency", "tire_management", "pressure_response",
    "delta_lag1", "delta_lag2", "delta_lag3",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train F1 RL strategy agent (PPO)")
    p.add_argument("--timesteps",      type=int,   default=1_000_000, help="Total PPO steps")
    p.add_argument("--n-envs",         type=int,   default=4,         help="Parallel envs")
    p.add_argument("--driver-id",      type=str,   default="lando_norris")
    p.add_argument("--start-pos",      type=int,   default=10,        help="Grid position 1-20")
    p.add_argument("--save-dir",       type=str,   default="/tmp/f1_rl_checkpoints")
    p.add_argument("--gcs-save",       type=str,   default=None,      help="gs://bucket/path to upload")
    p.add_argument("--smoke-test",     action="store_true")
    p.add_argument("--resume",         type=str,   default=None,      help="Path to policy.zip")
    p.add_argument("--no-models",      action="store_true",           help="Physics fallback only")
    p.add_argument("--eval-freq",      type=int,   default=10_000)
    p.add_argument("--run-name",       type=str,   default=None,      help="Vertex AI run name")
    p.add_argument("--skip-registry",  action="store_true",           help="Skip model registry push")
    return p.parse_args()


# ── Adapter loading ────────────────────────────────────────────────────────────

def load_adapters(models_dir: str = "models", skip: bool = False) -> dict:
    """Load all local pkl adapters, with graceful fallback per model."""
    if skip:
        logger.info("--no-models: running with physics fallbacks only")
        return {}
    try:
        from ml.rl.model_adapters import load_local_adapters
        adapters = load_local_adapters(models_dir)
        loaded  = [k for k, v in adapters.items() if v.loaded]
        missing = [k for k, v in adapters.items() if not v.loaded]
        logger.info("Adapters loaded: %s", loaded)
        if missing:
            logger.info("Adapters in fallback mode: %s", missing)
        return adapters
    except Exception as exc:
        logger.warning("Adapter load failed (%s) — physics fallback", exc)
        return {}


def maybe_prefetch_gcs(race_ids: list[str], project: str = "f1optimizer") -> None:
    try:
        from ml.features.feature_store import FeatureStore
        fs = FeatureStore(project=project)
        pulled, skipped = 0, 0
        for rid in race_ids:
            try:
                df = fs.load_race_features(rid)
                pulled += 1 if (df is not None and not df.empty) else 0
                skipped += 1 if (df is None or df.empty) else 0
            except Exception:
                skipped += 1
        logger.info("GCS prefetch: %d cached, %d skipped", pulled, skipped)
    except Exception as exc:
        logger.info("GCS prefetch unavailable (%s) — using circuit registry", exc)


# ── Smoke test ────────────────────────────────────────────────────────────────

def run_smoke_test(adapters: dict, driver_id: str, start_pos: int) -> None:
    logger.info("Running smoke-test episode…")
    try:
        from ml.rl.environment import F1RaceEnv
        env = F1RaceEnv(
            race_ids       = ["2024_4"],
            driver_id      = driver_id,
            adapters       = adapters,
            start_position = start_pos,
        )
        obs, info = env.reset()
        assert obs.shape == (29,), f"Expected obs shape (29,), got {obs.shape}"
        total_reward, steps, done = 0.0, 0, False
        while not done:
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            total_reward += reward
            steps += 1
            done = terminated or truncated
        logger.info("Smoke-test OK — %d laps, final P%s, total reward %.1f",
                    steps, info.get("position", "?"), total_reward)
        env.close()
    except Exception as exc:
        logger.error("Smoke-test FAILED: %s", exc)
        raise


# ── Evaluation helper ─────────────────────────────────────────────────────────

def _eval_episodes(
    agent,
    race_ids: list[str],
    adapters: dict,
    driver_id: str,
    start_pos: int,
    n_episodes: int = 5,
) -> dict:
    """
    Run N deterministic episodes and return summary statistics.
    Returns dict with keys: avg_position, avg_reward, avg_pit_stops, positions, rewards.
    """
    from ml.rl.environment import F1RaceEnv
    env = F1RaceEnv(
        race_ids       = race_ids,
        driver_id      = driver_id,
        adapters       = adapters,
        start_position = start_pos,
    )
    positions, rewards, pit_stops = [], [], []
    for _ in range(n_episodes):
        obs, info = env.reset()
        done, ep_reward = False, 0.0
        while not done:
            if agent._ppo and agent._vec_normalize:
                norm_obs        = agent._vec_normalize.normalize_obs(obs)
                action, _       = agent._ppo.predict(norm_obs, deterministic=True)
            else:
                action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(int(action))
            ep_reward += reward
            done = terminated or truncated
        positions.append(info.get("position", 20))
        rewards.append(ep_reward)
        pit_stops.append(info.get("pit_stops", 0))
    env.close()
    return {
        "avg_position":  float(np.mean(positions)),
        "avg_reward":    float(np.mean(rewards)),
        "avg_pit_stops": float(np.mean(pit_stops)),
        "positions":     positions,
        "rewards":       rewards,
    }


# ── Bias detection ────────────────────────────────────────────────────────────

def evaluate_bias_slices(
    agent,
    adapters: dict,
    driver_id: str,
    start_pos: int,
    smoke: bool = False,
) -> dict[str, float]:
    """
    Evaluate the trained policy across meaningful data slices to detect bias.

    Slices:
      - Circuit type: street vs power vs mixed
      - Starting position: front (P1-5), mid (P6-12), back (P13-20)
      - Season: 2022 / 2023 / 2024

    Returns a flat dict of metric_name → value, suitable for aiplatform.log_metrics().
    Flags bias if any circuit-type slice deviates > 3 positions from the overall mean.
    """
    logger.info("Running bias detection across data slices…")
    n_eps = 2 if smoke else 5
    metrics: dict[str, float] = {}

    # ── Circuit type slices ───────────────────────────────────────────────────
    circuit_results: dict[str, float] = {}
    for label, race_ids in [
        ("street",    STREET_RACE_IDS[:3]),
        ("power",     POWER_RACE_IDS[:3]),
        ("mixed",     MIXED_RACE_IDS[:3]),
    ]:
        try:
            res = _eval_episodes(agent, race_ids, adapters, driver_id, start_pos, n_eps)
            avg_pos = res["avg_position"]
            circuit_results[label] = avg_pos
            metrics[f"bias_circuit_{label}_avg_position"] = avg_pos
            metrics[f"bias_circuit_{label}_avg_reward"]   = res["avg_reward"]
            logger.info("  Circuit slice %-8s → avg P%.1f  reward=%.1f",
                        label, avg_pos, res["avg_reward"])
        except Exception as exc:
            logger.warning("  Circuit slice %s failed: %s", label, exc)

    # Flag bias: if any slice deviates > 3 positions from mean
    if circuit_results:
        vals     = list(circuit_results.values())
        mean_pos = float(np.mean(vals))
        max_dev  = float(max(abs(v - mean_pos) for v in vals))
        metrics["bias_circuit_position_mean"]    = mean_pos
        metrics["bias_circuit_max_deviation"]    = max_dev
        metrics["bias_circuit_flag"]             = float(max_dev > 3.0)
        if max_dev > 3.0:
            worst = max(circuit_results, key=lambda k: abs(circuit_results[k] - mean_pos))
            logger.warning(
                "  BIAS FLAG: circuit slice '%s' deviates %.1f positions from mean (%.1f)",
                worst, max_dev, mean_pos,
            )
        else:
            logger.info("  No circuit bias detected (max deviation=%.1f positions)", max_dev)

    # ── Starting position slices ──────────────────────────────────────────────
    eval_ids = SMOKE_EVAL_IDS if smoke else EVAL_RACE_IDS[:6]
    for label, spos in [("front_p1", 1), ("mid_p10", 10), ("back_p18", 18)]:
        try:
            res = _eval_episodes(agent, eval_ids, adapters, driver_id, spos, n_eps)
            gain = spos - res["avg_position"]   # positive = gained positions
            metrics[f"bias_startpos_{label}_avg_position"] = res["avg_position"]
            metrics[f"bias_startpos_{label}_position_gain"] = gain
            logger.info("  Start pos %-10s → avg P%.1f  gain=%.1f",
                        label, res["avg_position"], gain)
        except Exception as exc:
            logger.warning("  Start pos slice %s failed: %s", label, exc)

    # ── Season slices ─────────────────────────────────────────────────────────
    if not smoke:
        season_results: dict[str, float] = {}
        for season, race_ids in SEASON_SLICES.items():
            try:
                res = _eval_episodes(agent, race_ids, adapters, driver_id, start_pos, 3)
                season_results[season] = res["avg_position"]
                metrics[f"bias_season_{season}_avg_position"] = res["avg_position"]
                logger.info("  Season slice %s → avg P%.1f", season, res["avg_position"])
            except Exception as exc:
                logger.warning("  Season slice %s failed: %s", season, exc)

        if len(season_results) >= 2:
            season_vals = list(season_results.values())
            metrics["bias_season_max_deviation"] = float(
                max(season_vals) - min(season_vals)
            )

    return metrics


# ── Sensitivity analysis ──────────────────────────────────────────────────────

def analyze_policy_sensitivity(
    agent,
    adapters: dict,
    driver_id: str,
    start_pos: int,
    smoke: bool = False,
) -> dict[str, float]:
    """
    Feature perturbation sensitivity analysis for the RL policy.

    For each of the 29 observation features:
      1. Collect a set of reference observations from an eval episode
      2. Zero out (ablate) that feature across all observations
      3. Measure the mean KL divergence between original and perturbed action distributions
      4. Higher KL divergence = feature has greater influence on policy decisions

    Returns a flat dict: 'sensitivity_{feature_name}' → mean_kl_divergence.
    """
    logger.info("Running policy sensitivity analysis (feature perturbation)…")
    metrics: dict[str, float] = {}

    if agent._ppo is None or agent._vec_normalize is None:
        logger.warning("  Sensitivity skipped: policy not trained")
        return metrics

    try:
        from ml.rl.environment import F1RaceEnv
        env = F1RaceEnv(
            race_ids       = SMOKE_EVAL_IDS if smoke else EVAL_RACE_IDS[:4],
            driver_id      = driver_id,
            adapters       = adapters,
            start_position = start_pos,
        )

        # Collect reference observations from one eval episode
        obs_list: list[np.ndarray] = []
        obs, _ = env.reset()
        done = False
        while not done and len(obs_list) < 100:
            obs_list.append(obs.copy())
            norm_obs       = agent._vec_normalize.normalize_obs(obs)
            action, _      = agent._ppo.predict(norm_obs, deterministic=True)
            obs, _, terminated, truncated, _ = env.step(int(action))
            done = terminated or truncated
        env.close()

        if not obs_list:
            logger.warning("  Sensitivity skipped: no observations collected")
            return metrics

        obs_matrix = np.stack(obs_list)  # (N, 29)
        n_obs      = len(obs_matrix)

        # Compute baseline action probabilities for all observations
        def _get_action_probs(obs_batch: np.ndarray) -> np.ndarray:
            """Return (N, n_actions) softmax probabilities."""
            import torch
            from stable_baselines3.common.utils import obs_as_tensor
            device     = agent._ppo.policy.device
            norm_batch = agent._vec_normalize.normalize_obs(obs_batch)
            obs_tensor = obs_as_tensor(norm_batch, device)
            with torch.no_grad():
                dist = agent._ppo.policy.get_distribution(obs_tensor)
                return dist.distribution.probs.cpu().numpy()  # (N, n_actions)

        baseline_probs = _get_action_probs(obs_matrix)  # (N, 7)

        def _kl_divergence(p: np.ndarray, q: np.ndarray) -> float:
            """Mean KL(p‖q) across N samples."""
            eps = 1e-8
            kl  = np.sum(p * np.log((p + eps) / (q + eps)), axis=1)
            return float(np.mean(kl))

        # Perturb each feature and measure impact
        feature_impacts: list[tuple[str, float]] = []
        for i, feat_name in enumerate(OBS_FEATURE_NAMES):
            perturbed = obs_matrix.copy()
            perturbed[:, i] = 0.0  # ablate feature
            perturbed_probs  = _get_action_probs(perturbed)
            kl               = _kl_divergence(baseline_probs, perturbed_probs)
            feature_impacts.append((feat_name, kl))
            metrics[f"sensitivity_{feat_name}"] = kl

        # Log top 10 most influential features
        feature_impacts.sort(key=lambda x: x[1], reverse=True)
        logger.info("  Top 10 features by policy sensitivity (KL divergence):")
        for rank, (name, kl) in enumerate(feature_impacts[:10], 1):
            logger.info("    %2d. %-25s  KL=%.4f", rank, name, kl)

        # Save sensitivity bar chart
        top_n    = min(15, len(feature_impacts))
        names    = [x[0] for x in feature_impacts[:top_n]]
        kl_vals  = [x[1] for x in feature_impacts[:top_n]]

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.barh(names[::-1], kl_vals[::-1], color='#4C72B0')
        ax.set_xlabel('Mean KL Divergence (higher = more influential)')
        ax.set_title(f'RL Policy Sensitivity — Feature Perturbation Analysis\n'
                     f'(n={n_obs} observations, 29 features ablated)')
        plt.tight_layout()
        p = os.path.join(PLOTS_DIR, 'rl_sensitivity.png')
        plt.savefig(p, dpi=150, bbox_inches='tight')
        plt.close()
        logger.info("  Sensitivity plot saved → %s", p)
        _try_upload_plot(p, 'plots/rl_sensitivity.png')

    except Exception as exc:
        logger.warning("  Sensitivity analysis failed: %s", exc)

    return metrics


# ── Bias detection plots ──────────────────────────────────────────────────────

def _plot_bias_results(bias_metrics: dict[str, float]) -> None:
    """Save a bar chart of avg finishing position across circuit type slices."""
    try:
        labels = ["street", "power", "mixed"]
        values = [
            bias_metrics.get(f"bias_circuit_{l}_avg_position", None)
            for l in labels
        ]
        if all(v is None for v in values):
            return

        fig, axes = plt.subplots(1, 2, figsize=(12, 4))

        # Circuit type bar chart
        valid_labels = [l for l, v in zip(labels, values) if v is not None]
        valid_values = [v for v in values if v is not None]
        axes[0].bar(valid_labels, valid_values, color=['#4C72B0', '#DD8452', '#55A868'])
        axes[0].axhline(
            y=bias_metrics.get("bias_circuit_position_mean", 10),
            color='red', linestyle='--', linewidth=1, label='mean'
        )
        axes[0].set_title('RL Policy Bias — Avg Position by Circuit Type\n(lower = better)')
        axes[0].set_ylabel('Average Finishing Position')
        axes[0].set_ylim(0, 21)
        axes[0].legend()
        for i, v in enumerate(valid_values):
            axes[0].text(i, v + 0.3, f'P{v:.1f}', ha='center', fontsize=10)

        # Starting position gain chart
        spos_labels = ["front_p1", "mid_p10", "back_p18"]
        spos_values = [
            bias_metrics.get(f"bias_startpos_{l}_position_gain", None)
            for l in spos_labels
        ]
        valid_sp = [(l, v) for l, v in zip(spos_labels, spos_values) if v is not None]
        if valid_sp:
            sp_l, sp_v = zip(*valid_sp)
            colors = ['green' if v > 0 else 'red' for v in sp_v]
            axes[1].bar(sp_l, sp_v, color=colors)
            axes[1].axhline(y=0, color='black', linewidth=0.8)
            axes[1].set_title('RL Policy — Position Gain by Starting Position\n(positive = improved)')
            axes[1].set_ylabel('Positions Gained (start − finish)')
            for i, v in enumerate(sp_v):
                axes[1].text(i, v + (0.2 if v >= 0 else -0.5), f'{v:+.1f}', ha='center', fontsize=10)

        plt.tight_layout()
        p = os.path.join(PLOTS_DIR, 'rl_bias_detection.png')
        plt.savefig(p, dpi=150, bbox_inches='tight')
        plt.close()
        logger.info("Bias detection plot saved → %s", p)
        _try_upload_plot(p, 'plots/rl_bias_detection.png')
    except Exception as exc:
        logger.warning("Bias plot failed: %s", exc)


def _plot_position_distribution(positions: list[int], title: str, filename: str) -> None:
    """Histogram of finishing positions across eval episodes."""
    try:
        fig, ax = plt.subplots(figsize=(8, 4))
        bins = list(range(1, 22))
        ax.hist(positions, bins=bins, align='left', color='#4C72B0', edgecolor='white', rwidth=0.8)
        ax.axvline(x=np.mean(positions), color='red', linestyle='--', label=f'mean P{np.mean(positions):.1f}')
        ax.set_xlabel('Finishing Position')
        ax.set_ylabel('Count')
        ax.set_title(title)
        ax.set_xticks(range(1, 21))
        ax.legend()
        plt.tight_layout()
        p = os.path.join(PLOTS_DIR, filename)
        plt.savefig(p, dpi=150, bbox_inches='tight')
        plt.close()
        _try_upload_plot(p, f'plots/{filename}')
    except Exception as exc:
        logger.warning("Position distribution plot failed: %s", exc)


# ── Model registry ────────────────────────────────────────────────────────────

def push_to_model_registry(
    gcs_uri: str,
    display_name: str = "f1-rl-strategy",
    description: str  = "PPO race strategy agent trained on 2022-2024 F1 seasons",
) -> Optional[str]:
    """
    Register the trained model in Vertex AI Model Registry.
    Returns the resource name of the uploaded model, or None on failure.
    """
    if not _VERTEX_AVAILABLE:
        logger.info("Vertex AI unavailable — skipping model registry push")
        return None
    try:
        logger.info("Pushing to Vertex AI Model Registry: %s", display_name)
        model = aiplatform.Model.upload(
            display_name               = display_name,
            description                = description,
            artifact_uri               = gcs_uri,
            # Lightweight serving container — the model is loaded by the API, not Vertex serving
            serving_container_image_uri = (
                "us-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-0:latest"
            ),
            labels = {
                "framework": "stable-baselines3",
                "algorithm": "ppo",
                "task":      "race-strategy",
            },
        )
        logger.info("Model registered: %s", model.resource_name)
        return model.resource_name
    except Exception as exc:
        logger.warning("Model registry push failed: %s", exc)
        return None


# ── Rollback mechanism ────────────────────────────────────────────────────────

def compare_with_baseline(
    new_avg_position: float,
    baseline_path: str,
    adapters: dict,
    driver_id: str,
    start_pos: int,
) -> bool:
    """
    Compare the newly trained model against the saved baseline.
    Returns True if new model is better (lower avg position = better finishing).
    Implements rollback by keeping baseline if new model is worse.
    """
    if not os.path.exists(baseline_path):
        logger.info("No baseline model found at %s — accepting new model", baseline_path)
        return True

    logger.info("Comparing new model (avg P%.1f) against baseline…", new_avg_position)
    try:
        from ml.rl.agent import F1StrategyAgent
        from ml.rl.driver_profiles import get_profile

        baseline_agent = F1StrategyAgent(
            driver_profile = get_profile(driver_id),
            adapters       = adapters,
        )
        from stable_baselines3 import PPO
        from stable_baselines3.common.vec_env import VecNormalize, DummyVecEnv
        from ml.rl.model_adapters import load_local_adapters

        baseline_agent._ppo = PPO.load(baseline_path)

        # Load VecNormalize if present alongside the policy
        vn_path = baseline_path.replace("final_policy.zip", "final_vec_normalize.pkl")
        if os.path.exists(vn_path):
            from ml.rl.environment import F1RaceEnv
            dummy_env = DummyVecEnv([lambda: F1RaceEnv(
                race_ids=EVAL_RACE_IDS[:3], driver_id=driver_id, adapters=adapters
            )])
            baseline_agent._vec_normalize = VecNormalize.load(vn_path, dummy_env)
            baseline_agent._vec_normalize.training = False

        res = _eval_episodes(baseline_agent, EVAL_RACE_IDS[:4], adapters,
                             driver_id, start_pos, n_episodes=5)
        baseline_avg = res["avg_position"]
        improvement  = baseline_avg - new_avg_position   # positive = new is better
        logger.info("  Baseline avg P%.1f  |  New model avg P%.1f  |  Δ=%.1f positions",
                    baseline_avg, new_avg_position, improvement)

        if new_avg_position <= baseline_avg:
            logger.info("  New model is better (or equal) — proceeding with deployment")
            return True
        else:
            logger.warning(
                "  ROLLBACK: new model (P%.1f) is worse than baseline (P%.1f) by %.1f positions",
                new_avg_position, baseline_avg, -improvement,
            )
            return False
    except Exception as exc:
        logger.warning("Baseline comparison failed (%s) — accepting new model", exc)
        return True


# ── GCS plot uploader ─────────────────────────────────────────────────────────

def _try_upload_plot(local_path: str, gcs_path: str) -> None:
    """Upload a plot to GCS if credentials are available."""
    if not _VERTEX_AVAILABLE:
        return
    try:
        storage.Client(project='f1optimizer').bucket('f1optimizer-models') \
               .blob(gcs_path).upload_from_filename(local_path)
        logger.info("Uploaded plot → gs://f1optimizer-models/%s", gcs_path)
    except Exception:
        pass   # silently skip if no GCS access


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    if args.smoke_test:
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

    # Vertex AI experiment run name
    run_name = args.run_name or (
        f"rl-strategy-smoke" if args.smoke_test else "rl-strategy-v1"
    )

    # ── PPO hyperparameters (from agent.py _PPO_KWARGS) ───────────────────────
    ppo_hparams = {
        "algorithm":       "PPO",
        "policy":          "MlpPolicy",
        "net_arch":        "256x256",
        "learning_rate":   3e-4,
        "n_steps":         2048,
        "batch_size":      64,
        "n_epochs":        10,
        "gamma":           0.99,
        "gae_lambda":      0.95,
        "clip_range":      0.2,
        "ent_coef":        0.01,
        "vf_coef":         0.5,
        "max_grad_norm":   0.5,
        "total_timesteps": args.timesteps,
        "n_envs":          args.n_envs,
        "driver_id":       args.driver_id,
        "start_position":  args.start_pos,
        "n_train_races":   len(train_ids),
        "n_eval_races":    len(eval_ids),
        "physics_only":    int(args.no_models),
        "smoke_test":      int(args.smoke_test),
    }

    # ── Start Vertex AI experiment run ────────────────────────────────────────
    _run_ctx = None
    if _VERTEX_AVAILABLE and not args.smoke_test:
        try:
            _run_ctx = aiplatform.start_run(run=run_name)
            aiplatform.log_params(ppo_hparams)
            logger.info("Vertex AI run started: %s", run_name)
        except Exception as exc:
            logger.warning("Vertex AI run start failed: %s", exc)
            _run_ctx = None

    # ── Load adapters ─────────────────────────────────────────────────────────
    models_dir = str(_REPO_ROOT / "models")
    adapters   = load_adapters(models_dir, skip=args.no_models)

    # ── Prefetch GCS data ─────────────────────────────────────────────────────
    all_ids = list(set(train_ids + eval_ids))
    logger.info("Prefetching circuit data for %d races…", len(all_ids))
    maybe_prefetch_gcs(all_ids)

    # ── Smoke test ────────────────────────────────────────────────────────────
    run_smoke_test(adapters, args.driver_id, args.start_pos)

    # ── Build agent ───────────────────────────────────────────────────────────
    from ml.rl.agent import F1StrategyAgent
    from ml.rl.driver_profiles import get_profile

    profile = get_profile(args.driver_id)
    agent   = F1StrategyAgent(driver_profile=profile, adapters=adapters)

    if args.resume:
        logger.info("Resuming from checkpoint: %s", args.resume)
        from stable_baselines3 import PPO
        agent._ppo = PPO.load(args.resume)

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
        models_dir      = None if args.no_models else models_dir,
    )

    elapsed = time.time() - t0
    training_fps = int(args.timesteps / max(elapsed, 1))
    logger.info("Training complete in %.1f min  (~%d fps)", elapsed / 60, training_fps)

    # ── Save locally ──────────────────────────────────────────────────────────
    os.makedirs(args.save_dir, exist_ok=True)
    local_policy = os.path.join(args.save_dir, "final_policy.zip")
    local_vn     = os.path.join(args.save_dir, "final_vec_normalize.pkl")
    if agent._ppo:
        agent._ppo.save(local_policy)
        logger.info("Policy saved → %s", local_policy)
    if agent._vec_normalize:
        agent._vec_normalize.save(local_vn)
        logger.info("VecNormalize saved → %s", local_vn)

    # ── Upload to GCS ─────────────────────────────────────────────────────────
    gcs_model_uri = None
    if args.gcs_save:
        logger.info("Uploading to GCS: %s", args.gcs_save)
        try:
            agent.save(args.gcs_save)
            gcs_model_uri = args.gcs_save
            logger.info("GCS upload complete")
        except Exception as exc:
            logger.warning("GCS upload failed: %s", exc)

    # ── Post-training evaluation (main eval set) ──────────────────────────────
    logger.info("Post-training evaluation (%d episodes)…", 5 if not args.smoke_test else 3)
    try:
        n_eps = 3 if args.smoke_test else 5
        eval_res = _eval_episodes(
            agent, eval_ids[:3] if args.smoke_test else eval_ids,
            adapters, args.driver_id, args.start_pos, n_eps
        )
        avg_pos = eval_res["avg_position"]
        logger.info("Post-training eval — avg P%.1f  reward=%.1f  pit_stops=%.1f",
                    avg_pos, eval_res["avg_reward"], eval_res["avg_pit_stops"])
        for i, (pos, rew) in enumerate(zip(eval_res["positions"], eval_res["rewards"]), 1):
            logger.info("  Episode %d — P%d  reward=%.1f", i, pos, rew)

        # Save position distribution plot
        _plot_position_distribution(
            eval_res["positions"],
            title=f'RL Agent — Finishing Position Distribution\n(n={n_eps} eval episodes, {args.driver_id})',
            filename='rl_eval_positions.png',
        )
    except Exception as exc:
        logger.warning("Post-training eval failed: %s", exc)
        avg_pos = 20.0
        eval_res = {"avg_position": avg_pos, "avg_reward": 0.0, "avg_pit_stops": 0.0,
                    "positions": [], "rewards": []}

    # ── Rollback check ────────────────────────────────────────────────────────
    baseline_policy = str(_REPO_ROOT / "models" / "rl" / "final_policy.zip")
    deploy_model = compare_with_baseline(
        new_avg_position = avg_pos,
        baseline_path    = baseline_policy,
        adapters         = adapters,
        driver_id        = args.driver_id,
        start_pos        = args.start_pos,
    )

    if deploy_model:
        # Copy to permanent models/rl/ directory
        import shutil
        dest_dir = _REPO_ROOT / "models" / "rl"
        dest_dir.mkdir(parents=True, exist_ok=True)
        if os.path.exists(local_policy):
            shutil.copy2(local_policy, dest_dir / "final_policy.zip")
        if os.path.exists(local_vn):
            shutil.copy2(local_vn, dest_dir / "final_vec_normalize.pkl")
        logger.info("Model deployed → %s", dest_dir)
    else:
        logger.warning("Rollback: keeping existing baseline model at %s", baseline_policy)

    # ── Bias detection ────────────────────────────────────────────────────────
    bias_metrics: dict[str, float] = {}
    if not args.smoke_test:
        bias_metrics = evaluate_bias_slices(
            agent, adapters, args.driver_id, args.start_pos, smoke=False
        )
        _plot_bias_results(bias_metrics)
    else:
        logger.info("Smoke test: skipping full bias detection")

    # ── Sensitivity analysis ──────────────────────────────────────────────────
    sensitivity_metrics: dict[str, float] = {}
    if not args.smoke_test:
        sensitivity_metrics = analyze_policy_sensitivity(
            agent, adapters, args.driver_id, args.start_pos, smoke=False
        )
    else:
        logger.info("Smoke test: skipping sensitivity analysis")

    # ── Log all metrics to Vertex AI ──────────────────────────────────────────
    all_metrics = {
        "eval_avg_position":  avg_pos,
        "eval_avg_reward":    eval_res["avg_reward"],
        "eval_avg_pit_stops": eval_res["avg_pit_stops"],
        "training_fps":       float(training_fps),
        "training_time_min":  round(elapsed / 60, 2),
        "model_deployed":     float(deploy_model),
        **bias_metrics,
        **sensitivity_metrics,
    }
    if _VERTEX_AVAILABLE and _run_ctx is not None:
        try:
            # Vertex AI log_metrics takes flat float dict; filter to reasonable size
            loggable = {k: v for k, v in all_metrics.items()
                        if isinstance(v, (int, float)) and not k.startswith("sensitivity_")}
            aiplatform.log_metrics(loggable)
            # Log sensitivity separately if present
            sens_subset = {k: v for k, v in sensitivity_metrics.items()
                           if isinstance(v, float)}
            if sens_subset:
                aiplatform.log_metrics(sens_subset)
            logger.info("Metrics logged to Vertex AI experiment run: %s", run_name)
        except Exception as exc:
            logger.warning("Vertex AI metric logging failed: %s", exc)

    # ── Push to Vertex AI Model Registry ─────────────────────────────────────
    if not args.skip_registry and deploy_model and gcs_model_uri and not args.smoke_test:
        push_to_model_registry(
            gcs_uri      = gcs_model_uri,
            display_name = f"f1-rl-strategy-{run_name}",
            description  = (
                f"PPO race strategy agent — {args.timesteps:,} steps, "
                f"driver={args.driver_id}, avg_position=P{avg_pos:.1f}"
            ),
        )

    # ── Summary ───────────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("Training summary")
    logger.info("  Timesteps    : %d  (%.1f min, %d fps)", args.timesteps, elapsed / 60, training_fps)
    logger.info("  Eval avg pos : P%.1f", avg_pos)
    logger.info("  Eval avg rew : %.1f", eval_res["avg_reward"])
    logger.info("  Model deployed: %s", deploy_model)
    logger.info("  Checkpoints  : %s", args.save_dir)
    if bias_metrics:
        circuit_flag = bias_metrics.get("bias_circuit_flag", 0.0)
        logger.info("  Bias flag    : %s (circuit deviation=%.1f positions)",
                    "YES" if circuit_flag else "NO",
                    bias_metrics.get("bias_circuit_max_deviation", 0.0))
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
