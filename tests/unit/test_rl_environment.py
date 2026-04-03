"""
Unit tests for the F1 RL environment and components.

All tests run offline with no GCS access, no ML models (physics fallbacks only).
Fast: < 5 seconds total.
"""

import sys
from pathlib import Path
import numpy as np
import pytest

# Ensure repo root is on path
_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


# ── Action space tests ─────────────────────────────────────────────────────────

class TestActions:
    def test_decode_all_actions(self):
        from ml.rl.actions import decode, N_ACTIONS
        for i in range(N_ACTIONS):
            a = decode(i)
            assert a.raw == i
            assert a.driving_mode in ("NEUTRAL", "BALANCED", "PUSH")
            assert a.driving_style_int in (0, 1, 2)

    def test_stay_actions_are_not_pits(self):
        from ml.rl.actions import decode
        for i in (0, 1, 2):   # STAY_NEUTRAL, STAY_BALANCED, STAY_PUSH
            a = decode(i)
            assert not a.is_pit
            assert a.new_compound is None

    def test_pit_actions_have_compound(self):
        from ml.rl.actions import decode
        expected = {3: "SOFT", 4: "MEDIUM", 5: "HARD", 6: "INTER"}
        for i, compound in expected.items():
            a = decode(i)
            assert a.is_pit
            assert a.new_compound == compound

    def test_invalid_action_raises(self):
        from ml.rl.actions import decode
        with pytest.raises(ValueError):
            decode(99)

    def test_wet_pit_validity(self):
        from ml.rl.actions import is_valid_pit
        assert is_valid_pit(6, "wet", "INTER")        # PIT_INTER on wet = valid
        assert not is_valid_pit(6, "dry", "MEDIUM")   # PIT_INTER on dry = invalid
        assert not is_valid_pit(3, "wet", "INTER")    # PIT_SOFT on wet = invalid
        assert is_valid_pit(3, "dry", "MEDIUM")       # PIT_SOFT on dry = valid
        assert is_valid_pit(0, "dry", "SOFT")         # stay out always valid


# ── StateEncoder tests ────────────────────────────────────────────────────────

class TestStateEncoder:
    @pytest.fixture
    def encoder(self):
        from ml.rl.state import StateEncoder
        return StateEncoder(driver_profile={
            "aggression": 0.8, "consistency": 0.7,
            "tire_management": 0.6, "pressure_response": 0.5,
        })

    def _basic_obs(self, encoder):
        return encoder.encode(
            lap_number=25, total_laps=57,
            tire_age_laps=12, fuel_remaining_kg=60.0,
            tire_compound="MEDIUM", position=8,
            gap_to_leader=15.0, gap_to_ahead=1.2,
            lap_time_ms=85_000.0, pit_stops_count=1,
        )

    def test_obs_shape(self, encoder):
        obs = self._basic_obs(encoder)
        from ml.rl.state import STATE_DIM
        assert obs.shape == (STATE_DIM,)

    def test_obs_dtype(self, encoder):
        obs = self._basic_obs(encoder)
        assert obs.dtype == np.float32

    def test_bounded_features(self, encoder):
        """Most features should be in [0, 1] — delta features allow [-1, 1]."""
        obs = self._basic_obs(encoder)
        # Features 0-25 and 26-28 (delta lags) are clipped
        assert np.all(obs[:26] >= -1.0) and np.all(obs[:26] <= 1.0)

    def test_compound_onehot(self, encoder):
        """Exactly one compound bit should be set."""
        for compound, expected_idx in [("SOFT", 4), ("MEDIUM", 5), ("HARD", 6), ("INTER", 7)]:
            encoder.reset()
            obs = encoder.encode(
                lap_number=1, total_laps=50,
                tire_age_laps=0, fuel_remaining_kg=100.0,
                tire_compound=compound, position=10,
                gap_to_leader=0.0, gap_to_ahead=0.0,
                lap_time_ms=85_000.0, pit_stops_count=0,
            )
            assert obs[expected_idx] == 1.0, f"Expected compound bit {expected_idx} set for {compound}"
            assert sum(obs[4:9]) == 1.0, f"Expected exactly one compound bit for {compound}"

    def test_driver_profile_in_obs(self, encoder):
        obs = self._basic_obs(encoder)
        assert obs[22] == pytest.approx(0.8)   # aggression
        assert obs[23] == pytest.approx(0.7)   # consistency
        assert obs[24] == pytest.approx(0.6)   # tire_management
        assert obs[25] == pytest.approx(0.5)   # pressure_response

    def test_lap_progress(self, encoder):
        obs = self._basic_obs(encoder)
        assert obs[0] == pytest.approx(25 / 57, abs=1e-4)
        assert obs[1] == pytest.approx((57 - 25) / 57, abs=1e-4)

    def test_reset_clears_history(self, encoder):
        # Build up some history
        for i in range(5):
            encoder.encode(
                lap_number=i, total_laps=50,
                tire_age_laps=i, fuel_remaining_kg=100.0 - i,
                tire_compound="SOFT", position=10,
                gap_to_leader=0.0, gap_to_ahead=0.0,
                lap_time_ms=85_000.0 + i * 100, pit_stops_count=0,
            )
        encoder.reset()
        obs = encoder.encode(
            lap_number=0, total_laps=50,
            tire_age_laps=0, fuel_remaining_kg=110.0,
            tire_compound="MEDIUM", position=1,
            gap_to_leader=0.0, gap_to_ahead=0.0,
            lap_time_ms=0.0, pit_stops_count=0,
        )
        assert obs[26] == 0.0 and obs[27] == 0.0 and obs[28] == 0.0


# ── RewardFunction tests ──────────────────────────────────────────────────────

class TestRewardFunction:
    @pytest.fixture
    def rf(self):
        from ml.rl.reward import RewardFunction
        r = RewardFunction()
        r.reset()
        return r

    def test_position_gain_reward(self, rf):
        r = rf.step(
            prev_position=10, new_position=8,
            lap_time_ms=85_000, tire_compound="MEDIUM",
            tire_age_laps=5, pitted=False, safety_car_active=False,
        )
        assert r.position_gain == pytest.approx(10.0)  # +5 per position × 2

    def test_position_loss_penalty(self, rf):
        r = rf.step(
            prev_position=5, new_position=8,
            lap_time_ms=85_000, tire_compound="MEDIUM",
            tire_age_laps=5, pitted=False, safety_car_active=False,
        )
        assert r.position_gain == pytest.approx(-9.0)  # -3 per position × 3

    def test_no_position_change(self, rf):
        r = rf.step(
            prev_position=5, new_position=5,
            lap_time_ms=85_000, tire_compound="MEDIUM",
            tire_age_laps=5, pitted=False, safety_car_active=False,
        )
        assert r.position_gain == 0.0

    def test_pit_cost_overdue_tire(self, rf):
        """Pitting with an overdue tire should have near-zero cost."""
        r = rf.step(
            prev_position=5, new_position=5,
            lap_time_ms=85_000, tire_compound="MEDIUM",
            tire_age_laps=35,   # > optimal 30
            pitted=True, safety_car_active=False,
        )
        assert r.pit_cost == pytest.approx(-0.5)

    def test_pit_cost_fresh_tire(self, rf):
        """Pitting with a fresh tire should have full base cost."""
        r = rf.step(
            prev_position=5, new_position=5,
            lap_time_ms=85_000, tire_compound="MEDIUM",
            tire_age_laps=10,   # well within optimal 30
            pitted=True, safety_car_active=False,
        )
        assert r.pit_cost == pytest.approx(-1.0)

    def test_sc_pit_bonus(self, rf):
        r = rf.step(
            prev_position=5, new_position=5,
            lap_time_ms=85_000, tire_compound="SOFT",
            tire_age_laps=15, pitted=True, safety_car_active=True,
        )
        assert r.sc_pit_bonus == pytest.approx(8.0)

    def test_no_sc_bonus_without_sc(self, rf):
        r = rf.step(
            prev_position=5, new_position=5,
            lap_time_ms=85_000, tire_compound="SOFT",
            tire_age_laps=15, pitted=True, safety_car_active=False,
        )
        assert r.sc_pit_bonus == 0.0

    def test_tire_overstay_penalty(self, rf):
        # MEDIUM optimal = 30, threshold = 33. At tire_age=38, should penalise 5 laps over
        r = rf.step(
            prev_position=5, new_position=5,
            lap_time_ms=85_000, tire_compound="MEDIUM",
            tire_age_laps=38, pitted=False, safety_car_active=False,
        )
        assert r.tire_overstay < 0.0

    def test_terminal_podium(self, rf):
        r = rf.terminal(final_position=1)
        assert r.finish_reward == pytest.approx(50.0)

    def test_terminal_outside_points(self, rf):
        r = rf.terminal(final_position=15)
        assert r.finish_reward == pytest.approx(-5.0)

    def test_reward_components_total(self, rf):
        from ml.rl.reward import RewardComponents
        r = RewardComponents(position_gain=5.0, lap_time_bonus=0.2,
                             tire_overstay=-1.0, pit_cost=0.0,
                             sc_pit_bonus=0.0, finish_reward=0.0)
        assert r.total == pytest.approx(4.2)


# ── Circuit registry tests ────────────────────────────────────────────────────

class TestCircuitRegistry:
    def test_registry_not_empty(self):
        from ml.rl.race_runner import CIRCUIT_REGISTRY
        assert len(CIRCUIT_REGISTRY) > 50

    def test_known_circuits_present(self):
        from ml.rl.race_runner import CIRCUIT_REGISTRY
        for race_id in ["2024_1", "2024_8", "2024_16", "2025_1"]:
            assert race_id in CIRCUIT_REGISTRY, f"{race_id} missing from registry"

    def test_circuit_entry_fields(self):
        from ml.rl.race_runner import CIRCUIT_REGISTRY
        for race_id, meta in list(CIRCUIT_REGISTRY.items())[:5]:
            assert "total_laps" in meta, f"{race_id} missing total_laps"
            assert "base_lap_time_ms" in meta, f"{race_id} missing base_lap_time_ms"
            assert "race_name" in meta, f"{race_id} missing race_name"
            assert "circuit_id" in meta, f"{race_id} missing circuit_id"
            assert meta["total_laps"] > 0
            assert 50_000 < meta["base_lap_time_ms"] < 200_000   # 50s – 200s sanity

    def test_registry_lookup(self):
        from ml.rl.race_runner import _registry_lookup
        meta = _registry_lookup("2024_1")
        assert meta is not None
        assert isinstance(meta["circuit_id"], str) and len(meta["circuit_id"]) > 0

    def test_missing_key_returns_none(self):
        from ml.rl.race_runner import _registry_lookup
        assert _registry_lookup("9999_99") is None


# ── F1RaceEnv integration tests ──────────────────────────────────────────────

class TestF1RaceEnv:
    """Full environment tests — no ML models, uses circuit registry."""

    @pytest.fixture
    def env(self):
        from ml.rl.environment import F1RaceEnv
        e = F1RaceEnv(
            race_ids  = ["2024_16"],  # Monza — 53 laps, fast
            driver_id = "lando_norris",
            adapters  = {},
        )
        yield e
        e.close()

    def test_reset_returns_correct_shape(self, env):
        from ml.rl.state import STATE_DIM
        obs, info = env.reset()
        assert obs.shape == (STATE_DIM,)
        assert obs.dtype == np.float32

    def test_action_space(self, env):
        import gymnasium as gym
        assert isinstance(env.action_space, gym.spaces.Discrete)
        assert env.action_space.n == 7

    def test_observation_space(self, env):
        from ml.rl.state import STATE_DIM
        import gymnasium as gym
        assert isinstance(env.observation_space, gym.spaces.Box)
        assert env.observation_space.shape == (STATE_DIM,)

    def test_step_returns_correct_types(self, env):
        env.reset()
        obs, reward, terminated, truncated, info = env.step(0)
        from ml.rl.state import STATE_DIM
        assert obs.shape == (STATE_DIM,)
        assert isinstance(reward, float)
        assert isinstance(terminated, bool)
        assert isinstance(truncated, bool)
        assert isinstance(info, dict)

    def test_episode_terminates(self, env):
        """A full episode should terminate (not run forever)."""
        env.reset()
        done, steps = False, 0
        while not done:
            _, _, terminated, truncated, _ = env.step(env.action_space.sample())
            done = terminated or truncated
            steps += 1
            assert steps < 500, "Episode exceeded 500 steps — infinite loop?"
        assert steps > 0

    def test_info_contains_position(self, env):
        env.reset()
        done = False
        info = {}
        while not done:
            _, _, terminated, truncated, info = env.step(1)
            done = terminated or truncated
        assert "position" in info
        assert 1 <= info["position"] <= 20

    def test_obs_in_valid_range(self, env):
        """Most features should stay within [-1, 1] throughout an episode.
        Exceptions: obs[0] (lap_progress) can slightly exceed 1.0 on the terminal step."""
        env.reset()
        done = False
        while not done:
            obs, _, terminated, truncated, _ = env.step(env.action_space.sample())
            # Compound one-hot and binary flags must be exactly {0, 1}
            assert np.all(obs[4:9] >= 0.0) and np.all(obs[4:9] <= 1.0)
            assert obs[18] in (0.0, 1.0)  # safety_car
            assert obs[19] in (0.0, 1.0)  # vsc
            assert obs[20] in (0.0, 1.0)  # is_wet
            # All features except lap_progress (obs[0]) must stay in [0, 1] or [-1, 1]
            assert np.all(obs[1:] >= -1.0) and np.all(obs[1:] <= 1.0 + 1e-4), \
                f"Obs[1:] out of bounds: min={obs[1:].min():.3f} max={obs[1:].max():.3f}"
            done = terminated or truncated

    def test_gym_check_env(self, env):
        """Validate Gymnasium API compliance."""
        from gymnasium.utils.env_checker import check_env
        env.reset()
        check_env(env, warn=True, skip_render_check=True)


# ── Model adapter fallback tests ──────────────────────────────────────────────

class TestModelAdapterFallbacks:
    """Verify adapters return valid physics values when models are not loaded."""

    def _make_adapter(self, cls):
        """Instantiate an adapter with a non-existent path so it stays in fallback mode."""
        return cls("/tmp/_nonexistent_model.pkl")

    def test_tire_deg_fallback(self):
        from ml.rl.model_adapters import TireDegradationAdapter
        adapter = self._make_adapter(TireDegradationAdapter)
        assert not adapter.loaded
        state = {
            "tire_compound": "SOFT", "tire_age_laps": 10,
            "lap_number": 20, "total_laps": 57,
        }
        val = adapter.predict(state)
        assert isinstance(val, float)
        assert val >= 0.0   # degradation adds time, never negative

    def test_fuel_fallback(self):
        from ml.rl.model_adapters import FuelConsumptionAdapter
        adapter = self._make_adapter(FuelConsumptionAdapter)
        assert not adapter.loaded
        state = {"driving_mode": "PUSH", "lap_number": 1, "total_laps": 57}
        val = adapter.predict(state)
        assert isinstance(val, float)
        assert 0.5 < val < 5.0   # realistic kg/lap range

    def test_sc_fallback(self):
        from ml.rl.model_adapters import SafetyCarAdapter
        adapter = self._make_adapter(SafetyCarAdapter)
        assert not adapter.loaded
        state = {"lap_number": 30, "total_laps": 57, "tire_age_laps": 20}
        prob = adapter.predict_pit(state)
        assert 0.0 <= prob <= 1.0

    def test_pit_window_fallback(self):
        from ml.rl.model_adapters import PitWindowAdapter
        adapter = self._make_adapter(PitWindowAdapter)
        assert not adapter.loaded
        state = {
            "tire_age_laps": 25, "tire_compound": "MEDIUM",
            "lap_number": 30, "total_laps": 57,
        }
        val = adapter.predict(state)
        assert isinstance(val, float)
        assert val >= 0.0

    def test_tire_deg_batch_fallback(self):
        from ml.rl.model_adapters import TireDegradationAdapter
        adapter = self._make_adapter(TireDegradationAdapter)
        states = [
            {"tire_compound": c, "tire_age_laps": 10, "lap_number": 20, "total_laps": 57}
            for c in ["SOFT", "MEDIUM", "HARD", "MEDIUM", "SOFT"]
        ]
        results = adapter.predict_batch(states)
        assert len(results) == 5
        assert all(isinstance(v, float) and v >= 0.0 for v in results)
