"""
F1StrategyAgent — PPO-based race strategy agent.

Wraps stable-baselines3 PPO with F1-specific training utilities:
  - Multi-race parallel environment sampling
  - VecNormalize for observation/reward normalisation
  - GCS checkpointing (policy.zip + vec_normalize.pkl)
  - Evaluation callback on held-out races

Training flow:
  1. Build N parallel F1RaceEnv instances (one per CPU core)
  2. Wrap with VecNormalize (running mean/std for obs and rewards)
  3. Train PPO for total_timesteps
  4. Periodically evaluate on held-out races and checkpoint best policy

Usage:
    agent = F1StrategyAgent(driver_profile={...})
    agent.train(
        race_ids=train_race_ids,
        eval_race_ids=eval_race_ids,
        total_timesteps=500_000,
    )
    agent.save("gs://f1optimizer-models/rl_strategy/v1")

    # Inference (single obs vector)
    action = agent.predict(obs)
"""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Any, Optional

import numpy as np
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import (
    CallbackList,
    CheckpointCallback,
    EvalCallback,
)
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import SubprocVecEnv, VecNormalize

from ml.rl.environment import F1RaceEnv

logger = logging.getLogger(__name__)


class _EnvFactory:
    """
    Top-level picklable env factory for SubprocVecEnv / DummyVecEnv.

    Accepts either pre-loaded adapters (for DummyVecEnv — same process) or a
    models_dir path (for SubprocVecEnv — each worker loads its own copy so
    the large pkl files are not pickled across process boundaries).
    """

    def __init__(
        self,
        race_ids,
        driver_id,
        driver_profile,
        project,
        adapters=None,        # used by DummyVecEnv (same process)
        models_dir=None,      # used by SubprocVecEnv (loaded inside worker)
    ):
        self.race_ids       = race_ids
        self.driver_id      = driver_id
        self.driver_profile = driver_profile
        self.project        = project
        self.adapters       = adapters   # may be None for subprocess mode
        self.models_dir     = models_dir # path to local models/ dir

    def __call__(self):
        from stable_baselines3.common.monitor import Monitor

        # If running in a subprocess, load adapters locally (avoids pickling ~100 MB)
        adapters = self.adapters
        if adapters is None and self.models_dir:
            try:
                from ml.rl.model_adapters import load_local_adapters
                adapters = load_local_adapters(self.models_dir)
            except Exception:
                adapters = {}

        env = F1RaceEnv(
            race_ids       = self.race_ids,
            driver_id      = self.driver_id,
            driver_profile = self.driver_profile,
            adapters       = adapters or {},
            project        = self.project,
        )
        return Monitor(env)

PROJECT_ID    = os.environ.get("PROJECT_ID", "f1optimizer")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "gs://f1optimizer-models")

# PPO hyperparameters — tuned for F1 discrete strategy (58-lap episodes)
# Note: CPU is faster than GPU here — MLP with 29-dim obs is too small for
# CUDA launch overhead to be worthwhile; env stepping is the bottleneck.
_PPO_KWARGS: dict[str, Any] = {
    "policy":         "MlpPolicy",
    "learning_rate":  3e-4,
    "n_steps":        2048,       # rollout length per env before each update
    "batch_size":     64,
    "n_epochs":       10,
    "gamma":          0.99,       # discount: 1 lap ≈ 1 step → long horizon matters
    "gae_lambda":     0.95,
    "clip_range":     0.2,
    "ent_coef":       0.01,       # entropy bonus encourages exploration of compounds
    "vf_coef":        0.5,
    "max_grad_norm":  0.5,
    "verbose":        1,
    "device":         "cpu",      # MLP policy trains faster on CPU than GPU
    "policy_kwargs":  {"net_arch": [256, 256]},
}


class F1StrategyAgent:
    """
    PPO agent for F1 race strategy optimisation.

    Args:
        driver_profile:  Dict with keys aggression, consistency,
                         tire_management, pressure_response — all float [0, 1].
        tire_deg_model:  Trained TireDegradationModel (optional).
        fuel_model:      Trained FuelConsumptionModel (optional).
        overtake_model:  Trained OvertakeProbabilityModel (optional).
        sc_model:        Trained SafetyCarModel (optional).
        project:         GCP project ID.
    """

    def __init__(
        self,
        driver_profile: Optional[dict] = None,
        adapters: Optional[dict] = None,
        project: str = PROJECT_ID,
    ) -> None:
        self._driver_profile = driver_profile or {}
        self._adapters       = adapters or {}
        self._project        = project
        self._ppo:           Optional[PPO]          = None
        self._vec_normalize: Optional[VecNormalize] = None

    # ── Training ──────────────────────────────────────────────────────────────

    def train(
        self,
        race_ids: list[str],
        total_timesteps: int = 500_000,
        eval_race_ids: Optional[list[str]] = None,
        checkpoint_dir: str = "/tmp/f1_rl_checkpoints",
        n_envs: int = 4,
        driver_id: Optional[str] = None,
        models_dir: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Train the PPO agent over historical F1 races.

        Args:
            race_ids:         Training race IDs sampled each episode reset.
            total_timesteps:  Total environment steps to train for.
            eval_race_ids:    Held-out races for periodic evaluation.
            checkpoint_dir:   Local directory for intermediate checkpoints.
            n_envs:           Parallel environments (recommend = CPU cores).
            driver_id:        Driver to control (None → first driver per race).
            models_dir:       Path to local models/ dir. When n_envs > 1, each
                              subprocess loads its own adapters from this path
                              instead of pickling the parent's loaded objects.

        Returns:
            dict with training metadata.
        """
        from stable_baselines3.common.vec_env import DummyVecEnv

        os.makedirs(checkpoint_dir, exist_ok=True)

        # DummyVecEnv (same process) → pass loaded adapters directly (fast).
        # SubprocVecEnv (separate processes) → pass models_dir so each worker
        # loads its own copy, avoiding pickling ~100 MB of model objects.
        if n_envs == 1:
            vec_cls      = DummyVecEnv
            factory_kw   = {"adapters": self._adapters}
        else:
            vec_cls      = SubprocVecEnv
            if models_dir is not None:
                # Normal mode: each worker loads its own adapters from disk
                factory_kw = {"models_dir": models_dir}
            else:
                # --no-models mode: pass empty adapters dict (picklable, no disk load)
                factory_kw = {"adapters": {}}

        train_factory = _EnvFactory(
            race_ids       = race_ids,
            driver_id      = driver_id,
            driver_profile = self._driver_profile,
            project        = self._project,
            **factory_kw,
        )

        logger.info("Building %d %s training environments", n_envs, vec_cls.__name__)
        vec_env = make_vec_env(train_factory, n_envs=n_envs, vec_env_cls=vec_cls)
        self._vec_normalize = VecNormalize(vec_env, norm_obs=True, norm_reward=True)

        self._ppo = PPO(env=self._vec_normalize, **_PPO_KWARGS)

        callbacks = [
            CheckpointCallback(
                save_freq=max(50_000 // n_envs, 1),
                save_path=checkpoint_dir,
                name_prefix="f1_ppo",
                save_vecnormalize=True,
            ),
        ]

        if eval_race_ids:
            # Eval always uses DummyVecEnv (n_envs=1) with loaded adapters
            eval_factory = _EnvFactory(
                race_ids       = eval_race_ids,
                driver_id      = driver_id,
                driver_profile = self._driver_profile,
                project        = self._project,
                adapters       = self._adapters,
            )
            eval_vec = make_vec_env(eval_factory, n_envs=1, vec_env_cls=DummyVecEnv)
            # Share obs running stats from training env so evaluation is comparable
            eval_env = VecNormalize(
                eval_vec,
                norm_obs=True,
                norm_reward=False,   # don't normalise eval rewards
                training=False,
            )
            eval_env.obs_rms  = self._vec_normalize.obs_rms
            eval_env.ret_rms  = self._vec_normalize.ret_rms
            callbacks.append(
                EvalCallback(
                    eval_env,
                    best_model_save_path=os.path.join(checkpoint_dir, "best"),
                    log_path=checkpoint_dir,
                    eval_freq=max(10_000 // n_envs, 1),
                    n_eval_episodes=max(len(eval_race_ids), 5),
                    deterministic=True,
                    render=False,
                )
            )

        logger.info("Starting PPO training for %d timesteps", total_timesteps)
        self._ppo.learn(
            total_timesteps=total_timesteps,
            callback=CallbackList(callbacks),
            progress_bar=True,
        )
        logger.info("Training complete")

        return {
            "total_timesteps": total_timesteps,
            "n_train_races":   len(race_ids),
            "n_eval_races":    len(eval_race_ids) if eval_race_ids else 0,
            "checkpoint_dir":  checkpoint_dir,
        }

    # ── Inference ─────────────────────────────────────────────────────────────

    def predict(self, obs: np.ndarray, deterministic: bool = True) -> int:
        """
        Return the best action for the given observation.

        Args:
            obs:           (STATE_DIM,) float32 vector from F1RaceEnv.
            deterministic: Greedy if True; sample from policy if False.

        Returns:
            Integer action index (see actions.py).
        """
        if self._ppo is None:
            raise RuntimeError("Agent not trained. Call train() or load() first.")
        action, _ = self._ppo.predict(obs, deterministic=deterministic)
        return int(action)

    def action_probabilities(self, obs: np.ndarray) -> np.ndarray:
        """
        Return action probability distribution for the given observation.
        Shape: (N_ACTIONS,) float32.

        Useful for computing risk scores or displaying agent confidence.
        """
        if self._ppo is None:
            raise RuntimeError("Agent not trained.")
        import torch

        obs_tensor = self._ppo.policy.obs_to_tensor(obs)[0]
        with torch.no_grad():
            dist = self._ppo.policy.get_distribution(obs_tensor)
            probs = dist.distribution.probs.cpu().numpy().flatten()
        return probs

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self, gcs_uri: str) -> None:
        """
        Save trained policy and normalisation stats to GCS.

        Writes:
          <gcs_uri>/policy.zip         — PPO policy network weights
          <gcs_uri>/vec_normalize.pkl  — obs/reward normalisation statistics
        """
        if self._ppo is None:
            raise RuntimeError("Nothing to save — agent is not trained.")

        from google.cloud import storage

        client = storage.Client(project=self._project)
        bucket_name, prefix = gcs_uri.lstrip("gs://").split("/", 1)
        bucket = client.bucket(bucket_name)

        with tempfile.TemporaryDirectory() as tmp:
            policy_path = os.path.join(tmp, "policy.zip")
            self._ppo.save(policy_path)
            bucket.blob(f"{prefix}/policy.zip").upload_from_filename(policy_path)
            logger.info("Saved policy to %s/policy.zip", gcs_uri)

            if self._vec_normalize is not None:
                vn_path = os.path.join(tmp, "vec_normalize.pkl")
                self._vec_normalize.save(vn_path)
                bucket.blob(f"{prefix}/vec_normalize.pkl").upload_from_filename(vn_path)
                logger.info("Saved VecNormalize stats to %s/vec_normalize.pkl", gcs_uri)

    def load(self, gcs_uri: str, env: Optional[F1RaceEnv] = None) -> None:
        """
        Load policy (and optionally normalisation stats) from GCS.

        Args:
            gcs_uri: GCS URI prefix matching the one used in save().
            env:     Optional env to attach (required for continued training).
        """
        from google.cloud import storage

        client = storage.Client(project=self._project)
        bucket_name, prefix = gcs_uri.lstrip("gs://").split("/", 1)
        bucket = client.bucket(bucket_name)

        with tempfile.TemporaryDirectory() as tmp:
            policy_path = os.path.join(tmp, "policy.zip")
            bucket.blob(f"{prefix}/policy.zip").download_to_filename(policy_path)
            self._ppo = PPO.load(policy_path, env=env)
            logger.info("Loaded policy from %s", gcs_uri)

            vn_blob = bucket.blob(f"{prefix}/vec_normalize.pkl")
            if vn_blob.exists():
                vn_path = os.path.join(tmp, "vec_normalize.pkl")
                vn_blob.download_to_filename(vn_path)
                if env is not None:
                    self._vec_normalize = VecNormalize.load(vn_path, env)
                    logger.info("Loaded VecNormalize stats from %s", gcs_uri)
