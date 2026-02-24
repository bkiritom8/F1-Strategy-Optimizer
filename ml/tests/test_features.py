"""
Tests for feature engineering and feature store.

Uses in-memory dummy DataFrames — no Cloud SQL calls.
Verifies that feature computations produce correct column shapes and values.

All tests run on Vertex AI (n1-standard-4, no GPU).
"""

import numpy as np
import pandas as pd
import pytest

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def dummy_laps() -> pd.DataFrame:
    """Minimal lap features DataFrame resembling Cloud SQL output."""
    rng = np.random.default_rng(42)

    drivers = [1, 2, 3]
    laps_per_driver = 100
    races = [1001]

    rows = []
    for race_id in races:
        for driver_id in drivers:
            for lap in range(1, laps_per_driver + 1):
                rows.append(
                    {
                        "race_id": race_id,
                        "driver_id": driver_id,
                        "lap_number": lap,
                        "lap_time_ms": 85000 + rng.integers(-2000, 2000),
                        "tire_compound": rng.choice(["SOFT", "MEDIUM", "HARD"]),
                        "tire_age_laps": lap % 25 + 1,
                        "gap_to_car_ahead_ms": rng.integers(0, 30000),
                        "gap_to_leader_ms": rng.integers(0, 120000),
                        "position": rng.integers(1, 20),
                        "pit_stop_flag": int(lap % 25 == 0),
                        "year": 2023,
                        "circuit_id": "bahrain",
                        "race_name": "Bahrain Grand Prix",
                        "round": 1,
                        "driver_ref": f"driver_{driver_id}",
                    }
                )
    return pd.DataFrame(rows)


# ── FeaturePipeline unit tests ────────────────────────────────────────────────


class TestFeaturePipeline:

    @pytest.fixture
    def pipeline(self):
        from unittest.mock import MagicMock, patch

        # Patch FeatureStore so no Cloud SQL connection is made
        with patch("ml.features.feature_pipeline.FeatureStore") as MockFS:
            mock_fs = MagicMock()
            MockFS.return_value = mock_fs
            from ml.features.feature_pipeline import FeaturePipeline

            p = FeaturePipeline()
            p._feature_store = mock_fs
            return p

    def test_encode_compounds(self, pipeline, dummy_laps):
        df = pipeline._encode_compounds(dummy_laps)
        for compound in ["SOFT", "MEDIUM", "HARD"]:
            assert (
                f"compound_{compound}" in df.columns
            ), f"compound_{compound} column missing after encoding"

    def test_tire_degradation_creates_delta(self, pipeline, dummy_laps):
        df = pipeline._sort(dummy_laps)
        df = pipeline._tire_degradation(df)
        assert "lap_time_delta" in df.columns
        assert "deg_rate" in df.columns
        assert "deg_rate_roll3" in df.columns

    def test_tire_degradation_first_lap_is_nan(self, pipeline, dummy_laps):
        df = pipeline._sort(dummy_laps)
        df = pipeline._tire_degradation(df)
        # First lap of each driver/race should have NaN delta
        first_laps = df[df["lap_number"] == 1]
        assert first_laps["lap_time_delta"].isna().all()

    def test_gap_evolution(self, pipeline, dummy_laps):
        df = pipeline._sort(dummy_laps)
        df = pipeline._gap_evolution(df)
        assert "gap_delta" in df.columns
        assert "gap_trend" in df.columns

    def test_undercut_windows(self, pipeline, dummy_laps):
        df = pipeline._sort(dummy_laps)
        df = pipeline._undercut_windows(df)
        assert "position_gain" in df.columns
        assert "undercut_success" in df.columns

    def test_fuel_load_estimate_range(self, pipeline, dummy_laps):
        df = pipeline._sort(dummy_laps)
        df = pipeline._fuel_load_estimate(df)
        assert "fuel_load_pct" in df.columns
        assert (
            df["fuel_load_pct"].between(0, 1).all()
        ), "fuel_load_pct must be in [0, 1]"

    def test_safety_car_probability_range(self, pipeline, dummy_laps):
        df = pipeline._sort(dummy_laps)
        df = pipeline._safety_car_probability(df)
        assert "sc_prob" in df.columns
        assert df["sc_prob"].between(0, 1).all()

    def test_weather_impact(self, pipeline, dummy_laps):
        df = pipeline._sort(dummy_laps)
        df = pipeline._weather_impact(df)
        assert "weather_delta_ms" in df.columns
        assert "circuit_baseline_ms" in df.columns

    def test_clean_fills_nan(self, pipeline, dummy_laps):
        df = pipeline._sort(dummy_laps)
        df = pipeline._tire_degradation(df)
        df = pipeline._clean(df)
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        assert (
            not df[numeric_cols].isna().any().any()
        ), "clean() should fill all numeric NaNs"

    def test_full_run_shape(self, pipeline, dummy_laps):
        """run() on mock data produces more columns than raw input."""
        from unittest.mock import patch

        with patch.object(
            pipeline._feature_store,
            "load_multi_season_features",
            return_value=dummy_laps,
        ):
            df = pipeline.run(years=[2023])
        assert len(df) == len(dummy_laps)
        assert len(df.columns) > len(
            dummy_laps.columns
        ), "run() should add derived feature columns"


# ── FeatureStore unit tests (no Cloud SQL) ────────────────────────────────────


class TestFeatureStore:

    def test_import_cleanly(self):
        from ml.features.feature_store import FeatureStore

        assert FeatureStore is not None

    def test_env_vars_defaulted(self):
        from ml.features import feature_store as fs_module

        assert fs_module.PROJECT_ID == "f1optimizer"
        assert fs_module.DB_NAME == "f1_strategy"

    def test_write_to_gcs_path_construction(self, dummy_laps):
        """write_to_gcs constructs the correct URI without actually uploading."""
        from unittest.mock import MagicMock, patch

        with patch("ml.features.feature_store.Connector"), patch(
            "ml.features.feature_store.storage.Client"
        ) as MockClient:

            mock_bucket = MagicMock()
            mock_blob = MagicMock()
            MockClient.return_value.bucket.return_value = mock_bucket
            mock_bucket.blob.return_value = mock_blob

            from ml.features.feature_store import FeatureStore

            fs = FeatureStore()
            uri = fs.write_to_gcs(dummy_laps, "features/test/data.parquet")

        assert uri.startswith("gs://")
        assert "features/test/data.parquet" in uri
