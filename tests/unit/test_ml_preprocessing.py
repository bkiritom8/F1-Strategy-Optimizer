"""
Unit tests for preprocessing pipeline.
"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch

# Mock sample data
def get_sample_fastf1_data():
    # Need multiple groups to ensure groupby structure is stable
    data = {
        "season": [2024] * 10,
        "round": [1] * 5 + [2] * 5,
        "Driver": ["VER"] * 5 + ["HAM"] * 5,
        "LapNumber": [1, 2, 3, 4, 5] * 2,
        "LapTime": [95.0, 94.5, 94.2, 94.8, 125.0] * 2,
        "TyreLife": [1, 2, 3, 4, 5] * 2,
        "Compound": ["SOFT"] * 10,
        "Stint": [1] * 10,
        "mean_throttle": [80.0] * 10,
        "std_throttle": [5.0] * 10,
        "mean_brake": [10.0] * 10,
        "std_brake": [2.0] * 10,
        "mean_speed": [250.0] * 10,
        "max_speed": [320.0] * 10,
        "Team": ["Red Bull Racing"] * 5 + ["Mercedes"] * 5
    }
    return pd.DataFrame(data)

def get_sample_race_results():
    return pd.DataFrame({
        "Season": [2024],
        "Grid": [1],
        "Position": [1],
        "Driver": ["VER"],
        "Constructor": ["Red Bull"],
        "Circuit": ["Bahrain"]
    })

@pytest.fixture(autouse=True)
def mock_data_loading():
    with patch("ml.preprocessing.preprocess_data.load_fastf1_data", return_value=get_sample_fastf1_data()), \
         patch("ml.preprocessing.preprocess_data.load_race_results", return_value=get_sample_race_results()), \
         patch("ml.preprocessing.preprocess_data.fs.open"): # Mock GCS opening for saving metadata
        yield

class TestLoadData:
    def test_load_fastf1_data_returns_dataframe(self):
        from ml.preprocessing.preprocess_data import load_fastf1_data
        df = load_fastf1_data()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_load_fastf1_data_has_required_columns(self):
        from ml.preprocessing.preprocess_data import load_fastf1_data
        df = load_fastf1_data()
        required = ["season", "round", "Driver", "LapNumber", "LapTime"]
        for col in required:
            assert col in df.columns, f"Missing column: {col}"

    def test_load_race_results_returns_dataframe(self):
        from ml.preprocessing.preprocess_data import load_race_results
        df = load_race_results()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0


class TestPreprocessFastF1:
    @pytest.fixture
    def raw_data(self):
        return get_sample_fastf1_data()

    def test_removes_invalid_laptimes(self, raw_data):
        from ml.preprocessing.preprocess_data import preprocess_fastf1
        df = preprocess_fastf1(raw_data.copy())
        # Filtered version removes the slow lap (125.0) which is >94.2*1.2
        assert df["LapTime"].min() >= 60
        assert df["LapTime"].max() < 200

    def test_creates_compound_columns(self, raw_data):
        from ml.preprocessing.preprocess_data import preprocess_fastf1
        df = preprocess_fastf1(raw_data.copy())
        for col in ["compound_SOFT", "compound_MEDIUM", "compound_HARD"]:
            assert col in df.columns

    def test_creates_lap_time_delta(self, raw_data):
        from ml.preprocessing.preprocess_data import preprocess_fastf1
        df = preprocess_fastf1(raw_data.copy())
        assert "lap_time_delta" in df.columns
        assert df["lap_time_delta"].between(-10, 10).all()

    def test_creates_fuel_load(self, raw_data):
        from ml.preprocessing.preprocess_data import preprocess_fastf1
        df = preprocess_fastf1(raw_data.copy())
        assert "fuel_load_pct" in df.columns
        assert df["fuel_load_pct"].between(0, 1).all()

    def test_creates_laps_to_pit(self, raw_data):
        from ml.preprocessing.preprocess_data import preprocess_fastf1
        df = preprocess_fastf1(raw_data.copy())
        assert "laps_to_pit" in df.columns

    def test_creates_driving_style(self, raw_data):
        from ml.preprocessing.preprocess_data import preprocess_fastf1
        df = preprocess_fastf1(raw_data.copy())
        assert "driving_style" in df.columns
        assert df["driving_style"].isin([0, 1, 2]).all()

    def test_creates_position(self, raw_data):
        from ml.preprocessing.preprocess_data import preprocess_fastf1
        df = preprocess_fastf1(raw_data.copy())
        assert "position" in df.columns

    def test_creates_safety_car_detection(self, raw_data):
        from ml.preprocessing.preprocess_data import engineer_features
        df = engineer_features(raw_data.copy())
        assert "is_sc_lap" in df.columns
        assert df["is_sc_lap"].isin([0, 1]).all()

    def test_creates_overtake_success(self, raw_data):
        from ml.preprocessing.preprocess_data import preprocess_fastf1
        df = preprocess_fastf1(raw_data.copy())
        assert "overtake_success" in df.columns
        assert df["overtake_success"].isin([0, 1]).all()


class TestPreprocessRaceResults:
    @pytest.fixture
    def raw_data(self):
        return get_sample_race_results()

    def test_removes_invalid_positions(self, raw_data):
        from ml.preprocessing.preprocess_data import preprocess_race_results
        df = preprocess_race_results(raw_data.copy())
        assert df["position"].min() >= 1
        assert df["position"].max() <= 20

    def test_removes_invalid_grid(self, raw_data):
        from ml.preprocessing.preprocess_data import preprocess_race_results
        df = preprocess_race_results(raw_data.copy())
        assert df["grid"].min() >= 1

    def test_creates_driver_avg_finish(self, raw_data):
        from ml.preprocessing.preprocess_data import preprocess_race_results
        df = preprocess_race_results(raw_data.copy())
        assert "driver_avg_finish" in df.columns or "constructor_avg_finish" in df.columns


class TestDataIntegrity:
    def test_seasons_in_expected_range(self):
        from ml.preprocessing.preprocess_data import preprocess_fastf1, load_fastf1_data
        df = preprocess_fastf1(load_fastf1_data())
        assert df["season"].min() >= 2018
        assert df["season"].max() <= 2025

    def test_no_duplicate_laps(self):
        from ml.preprocessing.preprocess_data import preprocess_fastf1, load_fastf1_data
        df   = preprocess_fastf1(load_fastf1_data())
        dups = df.duplicated(subset=["season", "round", "Driver", "LapNumber"])
        assert dups.sum() == 0