"""
Smoke tests for ML models.

Tests:
  - StrategyPredictor: train on dummy data, predict, evaluate, save/load (GCS mocked)
  - PitStopOptimizer:  train on dummy data, predict, evaluate, save/load (GCS mocked)
  - BaseF1Model:       abstract interface is enforced

All tests run on Vertex AI (n1-standard-4, no GPU).
GCS calls are intercepted via unittest.mock — no actual GCS uploads.
"""

import os
import tempfile
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

# ── Dummy data ────────────────────────────────────────────────────────────────


def _make_lap_df(n_drivers: int = 3, laps_per_driver: int = 60) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for driver_id in range(n_drivers):
        for lap in range(1, laps_per_driver + 1):
            compound = rng.choice(["SOFT", "MEDIUM", "HARD"])
            rows.append(
                {
                    "race_id": 1,
                    "driver_id": driver_id,
                    "lap_number": lap,
                    "lap_time_ms": 85000 + rng.integers(-3000, 3000),
                    "tire_compound": compound,
                    "tire_age_laps": lap % 20 + 1,
                    "gap_to_car_ahead_ms": int(rng.integers(0, 20000)),
                    "gap_to_leader_ms": int(rng.integers(0, 100000)),
                    "position": int(rng.integers(1, 20)),
                    "pit_stop_flag": int(lap % 20 == 0),
                    "year": 2023,
                    "circuit_id": "monza",
                    "round": 1,
                    "driver_ref": f"driver_{driver_id}",
                }
            )
    return pd.DataFrame(rows)


# ── StrategyPredictor tests ───────────────────────────────────────────────────


class TestStrategyPredictor:

    @pytest.fixture(autouse=True)
    def _patch_gcp(self):
        """Suppress all GCP calls (Cloud Logging, Pub/Sub, GCS)."""
        with patch("ml.models.base_model.cloud_logging.Client"), patch(
            "ml.models.base_model.pubsub_v1.PublisherClient"
        ), patch("ml.models.base_model.storage.Client"):
            yield

    @pytest.fixture
    def model(self):
        from ml.models.strategy_predictor import StrategyPredictor

        # Use CPU-friendly params for fast smoke test
        return StrategyPredictor(
            xgb_params={
                "n_estimators": 10,
                "max_depth": 3,
                "learning_rate": 0.1,
                "tree_method": "hist",  # CPU (not gpu_hist)
                "random_state": 0,
            },
            lgb_params={
                "n_estimators": 10,
                "max_depth": 3,
                "learning_rate": 0.1,
                "device": "cpu",
                "verbose": -1,
                "random_state": 0,
            },
        )

    @pytest.fixture
    def trained_model(self, model):
        df = _make_lap_df()
        model.train(df)
        return model, df

    def test_train_returns_metrics(self, model):
        df = _make_lap_df()
        metrics = model.train(df)
        assert "val_mae" in metrics
        assert "val_loss" in metrics
        assert metrics["val_mae"] >= 0

    def test_predict_adds_column(self, trained_model):
        model, df = trained_model
        out = model.predict(df)
        assert "strategy_score_pred" in out.columns
        assert len(out) == len(df)

    def test_evaluate_returns_metrics(self, trained_model):
        model, df = trained_model
        metrics = model.evaluate(df)
        assert "val_mae" in metrics
        assert "val_loss" in metrics
        assert "n_samples" in metrics

    def test_predict_before_train_raises(self, model):
        with pytest.raises(RuntimeError, match="not trained"):
            model.predict(_make_lap_df())

    def test_feature_importance_shape(self, trained_model):
        model, _ = trained_model
        fi = model.feature_importance()
        assert "feature" in fi.columns
        assert "importance" in fi.columns
        assert len(fi) > 0

    def test_save_load_roundtrip(self, trained_model):
        model, df = trained_model
        with tempfile.TemporaryDirectory() as tmp:
            # Patch GCS save to write to a local dir
            with patch.object(model, "_storage_client") as mock_client:
                mock_bucket = MagicMock()
                mock_blob = MagicMock()
                mock_client.bucket.return_value = mock_bucket
                mock_bucket.blob.return_value = mock_blob
                mock_bucket.list_blobs.return_value = []

                # Save natively to temp dir
                native_dir = os.path.join(tmp, "native")
                os.makedirs(native_dir)
                model._save_native(native_dir)

                # Load from same temp dir
                from ml.models.strategy_predictor import StrategyPredictor

                new_model = StrategyPredictor()
                new_model._load_native(native_dir)

            assert new_model._trained
            preds = new_model.predict(df)
            assert "strategy_score_pred" in preds.columns


# ── PitStopOptimizer tests ────────────────────────────────────────────────────


class TestPitStopOptimizer:

    @pytest.fixture(autouse=True)
    def _patch_gcp(self):
        with patch("ml.models.base_model.cloud_logging.Client"), patch(
            "ml.models.base_model.pubsub_v1.PublisherClient"
        ), patch("ml.models.base_model.storage.Client"):
            yield

    @pytest.fixture
    def model(self):
        from ml.models.pit_stop_optimizer import PitStopOptimizer

        return PitStopOptimizer(
            sequence_len=5,
            lstm_units=[16],
            dense_units=[8],
            dropout_rate=0.0,
            learning_rate=1e-3,
            batch_size=32,
            epochs=2,
        )

    @pytest.fixture
    def trained_model(self, model):
        # Need enough laps to form sequences: sequence_len + 1 per driver
        df = _make_lap_df(n_drivers=3, laps_per_driver=30)
        model.train(df)
        return model, df

    def test_train_returns_metrics(self, model):
        df = _make_lap_df(n_drivers=3, laps_per_driver=30)
        metrics = model.train(df)
        assert "val_loss" in metrics
        assert "val_auc" in metrics

    def test_predict_adds_urgency(self, trained_model):
        model, df = trained_model
        out = model.predict(df)
        assert "pit_urgency" in out.columns
        assert "recommend_pit" in out.columns
        assert out["pit_urgency"].between(0, 1).all()

    def test_evaluate_returns_metrics(self, trained_model):
        model, df = trained_model
        metrics = model.evaluate(df)
        assert "val_roc_auc" in metrics
        assert "n_samples" in metrics

    def test_predict_before_train_raises(self, model):
        with pytest.raises(RuntimeError, match="not trained"):
            model.predict(_make_lap_df())

    def test_save_load_native(self, trained_model):
        model, df = trained_model
        with tempfile.TemporaryDirectory() as tmp:
            model._save_native(tmp)
            assert os.path.exists(os.path.join(tmp, "config.json"))

            from ml.models.pit_stop_optimizer import PitStopOptimizer

            new_model = PitStopOptimizer()
            new_model._load_native(tmp)
            assert new_model._trained


# ── BaseF1Model interface enforcement ─────────────────────────────────────────


class TestBaseModelInterface:

    def test_cannot_instantiate_base(self):
        from ml.models.base_model import BaseF1Model

        with pytest.raises(TypeError):
            BaseF1Model()

    def test_concrete_model_has_all_methods(self):
        from ml.models.strategy_predictor import StrategyPredictor

        with patch("ml.models.base_model.cloud_logging.Client"), patch(
            "ml.models.base_model.pubsub_v1.PublisherClient"
        ), patch("ml.models.base_model.storage.Client"):
            m = StrategyPredictor()
        for method in ("train", "predict", "evaluate", "save", "load"):
            assert hasattr(m, method) and callable(
                getattr(m, method)
            ), f"StrategyPredictor missing method: {method}"
