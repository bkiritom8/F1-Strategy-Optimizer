"""
Smoke tests for ML model wrapper classes.
Loads real .pkl files from models/ and uses a real GCS data slice.
Only base_model GCP clients are mocked (Cloud Logging, Pub/Sub, Storage).
"""

from __future__ import annotations

import os
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
import pytest

MODELS_DIR = "models"
MODELS_BUCKET = "f1optimizer-models"
PROJECT_ID = "f1optimizer"
FEATURES_URI = "gs://f1optimizer-data-lake/ml_features/fastf1_features.parquet"
RACE_RESULTS_URI = "gs://f1optimizer-data-lake/ml_features/race_results_features.parquet"

def _load_bundle(name: str):
    local_path = os.path.join(MODELS_DIR, f"{name}.pkl")
    if os.path.exists(local_path):
        return joblib.load(local_path)
    
    # Fallback to GCS for CI
    from google.cloud import storage
    import io
    
    client = storage.Client(project=PROJECT_ID)
    bucket = client.bucket(MODELS_BUCKET)
    # Match model_bridge.py / strategy predictor paths
    if name == "strategy_predictor":
        blob_path = "strategy_predictor/latest/model.pkl"
    else:
        blob_path = f"{name}/model.pkl"
    
    blob = bucket.blob(blob_path)
    if not blob.exists():
        pytest.fail(f"Bundle {name} not found locally or at gs://{MODELS_BUCKET}/{blob_path}")
        
    buf = io.BytesIO()
    blob.download_to_file(buf)
    buf.seek(0)
    return joblib.load(buf)


@pytest.fixture(scope="module")
def real_laps():
    df = pd.read_parquet(FEATURES_URI)
    slice_df = df[(df["season"] == 2022) & (df["round"] == 1)].reset_index(drop=True)
    # driver_encoded is created by the training script but not saved to parquet
    # encode using the bundle's encoder
    bundle = _load_bundle("overtake_prob")
    le = bundle["driver_encoder"]
    known = set(le.classes_)
    slice_df["driver_encoded"] = slice_df["Driver"].apply(
        lambda v: le.transform([v])[0] if v in known else -1
    )
    return slice_df


@pytest.fixture(scope="module")
def real_race_results():
    df = pd.read_parquet(RACE_RESULTS_URI)
    slice_df = df[(df["season"] == 2022) & (df["round"] == 1)].reset_index(drop=True)
    # finish_tier is computed at training time from position
    slice_df["position"] = pd.to_numeric(slice_df["position"], errors="coerce")
    slice_df["finish_tier"] = pd.cut(
        slice_df["position"],
        bins=[0, 3, 10, 100],
        labels=["Podium", "Points", "Outside"],
    ).astype(str)
    return slice_df


class TestTireDegradationModel:
    @pytest.fixture(autouse=True)
    def _patch(self):
        with patch("ml.models.base_model.cloud_logging.Client"), patch(
            "ml.models.base_model.pubsub_v1.PublisherClient"
        ), patch("ml.models.base_model.storage.Client"):
            yield

    @pytest.fixture
    def model(self):
        from ml.models.tire_degradation_model import TireDegradationModel

        m = TireDegradationModel()
        m._bundle = _load_bundle("tire_degradation")
        return m

    def test_loads_without_error(self, model):
        assert model._bundle is not None

    def test_predict_returns_dataframe(self, model, real_laps):
        out = model.predict(real_laps)
        assert isinstance(out, pd.DataFrame)
        assert "prediction" in out.columns
        assert len(out) > 0

    def test_predict_values_are_numeric(self, model, real_laps):
        out = model.predict(real_laps)
        assert pd.to_numeric(out["prediction"], errors="coerce").notna().all()

    def test_evaluate_returns_mae_and_r2(self, model, real_laps):
        metrics = model.evaluate(real_laps)
        assert "mae" in metrics
        assert "r2" in metrics
        assert metrics["mae"] >= 0

    def test_train_raises_not_implemented(self, model, real_laps):
        with pytest.raises(NotImplementedError):
            model.train(real_laps)


class TestDrivingStyleModel:
    @pytest.fixture(autouse=True)
    def _patch(self):
        with patch("ml.models.base_model.cloud_logging.Client"), patch(
            "ml.models.base_model.pubsub_v1.PublisherClient"
        ), patch("ml.models.base_model.storage.Client"):
            yield

    @pytest.fixture
    def model(self):
        from ml.models.driving_style_model import DrivingStyleModel

        m = DrivingStyleModel()
        m._bundle = _load_bundle("driving_style")
        return m

    def test_loads_without_error(self, model):
        assert model._bundle is not None

    def test_predict_returns_valid_classes(self, model, real_laps):
        out = model.predict(real_laps)
        assert "prediction" in out.columns
        assert set(out["prediction"].unique()).issubset({"PUSH", "BALANCE", "NEUTRAL"})

    def test_evaluate_returns_f1(self, model, real_laps):
        df = real_laps.copy()
        # driving_style must be string labels to match string predictions
        df["driving_style"] = np.random.choice(
            ["PUSH", "BALANCE", "NEUTRAL"], size=len(df)
        )
        metrics = model.evaluate(df)
        assert "accuracy" in metrics
        assert "f1_macro" in metrics

    def test_train_raises_not_implemented(self, model, real_laps):
        with pytest.raises(NotImplementedError):
            model.train(real_laps)


class TestSafetyCarModel:
    @pytest.fixture(autouse=True)
    def _patch(self):
        with patch("ml.models.base_model.cloud_logging.Client"), patch(
            "ml.models.base_model.pubsub_v1.PublisherClient"
        ), patch("ml.models.base_model.storage.Client"):
            yield

    @pytest.fixture
    def model(self):
        from ml.models.safety_car_model import SafetyCarModel

        m = SafetyCarModel()
        m._bundle = _load_bundle("safety_car")
        return m

    def test_loads_without_error(self, model):
        assert model._bundle is not None

    def test_predict_returns_binary(self, model, real_laps):
        out = model.predict(real_laps)
        assert "prediction" in out.columns
        assert "probability" in out.columns
        assert out["prediction"].isin([0, 1]).all()

    def test_probability_in_range(self, model, real_laps):
        out = model.predict(real_laps)
        assert out["probability"].between(0, 1).all()

    def test_circuit_sc_prob_known(self, model):
        prob = model.predict_circuit_sc_prob("Monaco Grand Prix")
        assert prob >= 0.0

    def test_circuit_sc_prob_unknown_returns_default(self, model):
        prob = model.predict_circuit_sc_prob("Unknown Circuit XYZ")
        assert prob == 0.1

    def test_train_raises_not_implemented(self, model, real_laps):
        with pytest.raises(NotImplementedError):
            model.train(real_laps)


class TestPitWindowModel:
    @pytest.fixture(autouse=True)
    def _patch(self):
        with patch("ml.models.base_model.cloud_logging.Client"), patch(
            "ml.models.base_model.pubsub_v1.PublisherClient"
        ), patch("ml.models.base_model.storage.Client"):
            yield

    @pytest.fixture
    def model(self):
        from ml.models.pit_window_model import PitWindowModel

        m = PitWindowModel()
        m._bundle = _load_bundle("pit_window")
        return m

    def test_loads_without_error(self, model):
        assert model._bundle is not None

    def test_predict_returns_dataframe(self, model, real_laps):
        out = model.predict(real_laps)
        assert isinstance(out, pd.DataFrame)
        assert "prediction" in out.columns
        assert len(out) > 0

    def test_predict_values_are_numeric(self, model, real_laps):
        out = model.predict(real_laps)
        assert pd.to_numeric(out["prediction"], errors="coerce").notna().all()

    def test_train_raises_not_implemented(self, model, real_laps):
        with pytest.raises(NotImplementedError):
            model.train(real_laps)


class TestOvertakeProbModel:
    @pytest.fixture(autouse=True)
    def _patch(self):
        with patch("ml.models.base_model.cloud_logging.Client"), patch(
            "ml.models.base_model.pubsub_v1.PublisherClient"
        ), patch("ml.models.base_model.storage.Client"):
            yield

    @pytest.fixture
    def model(self):
        from ml.models.overtake_prob_model import OvertakeProbModel

        m = OvertakeProbModel()
        m._bundle = _load_bundle("overtake_prob")
        return m

    def test_loads_without_error(self, model):
        assert model._bundle is not None

    def test_predict_returns_binary(self, model, real_laps):
        out = model.predict(real_laps)
        assert "prediction" in out.columns
        assert "probability" in out.columns
        assert out["prediction"].isin([0, 1]).all()

    def test_probability_in_range(self, model, real_laps):
        out = model.predict(real_laps)
        assert out["probability"].between(0, 1).all()

    def test_evaluate_returns_f1(self, model, real_laps):
        metrics = model.evaluate(real_laps)
        assert "accuracy" in metrics
        assert "f1_macro" in metrics

    def test_train_raises_not_implemented(self, model, real_laps):
        with pytest.raises(NotImplementedError):
            model.train(real_laps)


class TestRaceOutcomeModel:
    @pytest.fixture(autouse=True)
    def _patch(self):
        with patch("ml.models.base_model.cloud_logging.Client"), patch(
            "ml.models.base_model.pubsub_v1.PublisherClient"
        ), patch("ml.models.base_model.storage.Client"):
            yield

    @pytest.fixture
    def model(self):
        from ml.models.race_outcome_model import RaceOutcomeModel

        m = RaceOutcomeModel()
        m._bundle = _load_bundle("race_outcome")
        return m

    def test_loads_without_error(self, model):
        assert model._bundle is not None

    def test_predict_returns_dataframe(self, model, real_race_results):
        out = model.predict(real_race_results)
        assert isinstance(out, pd.DataFrame)
        assert "prediction" in out.columns
        assert len(out) > 0

    def test_predict_classes_valid(self, model, real_race_results):
        out = model.predict(real_race_results)
        assert set(out["prediction"].unique()).issubset({"Podium", "Points", "Outside"})

    def test_evaluate_returns_f1(self, model, real_race_results):
        metrics = model.evaluate(real_race_results)
        assert "accuracy" in metrics
        assert "f1_macro" in metrics

    def test_train_raises_not_implemented(self, model, real_race_results):
        with pytest.raises(NotImplementedError):
            model.train(real_race_results)


class TestBaseModelInterface:
    def test_cannot_instantiate_base(self):
        from ml.models.base_model import BaseF1Model

        with pytest.raises(TypeError):
            BaseF1Model()

    def test_all_wrappers_have_required_methods(self):
        with patch("ml.models.base_model.cloud_logging.Client"), patch(
            "ml.models.base_model.pubsub_v1.PublisherClient"
        ), patch("ml.models.base_model.storage.Client"):
            from ml.models.tire_degradation_model import TireDegradationModel

            m = TireDegradationModel()
        for method in (
            "train",
            "predict",
            "evaluate",
            "save",
            "load",
            "_save_native",
            "_load_native",
        ):
            assert hasattr(m, method) and callable(getattr(m, method))
