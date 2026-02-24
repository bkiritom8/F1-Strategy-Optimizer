"""
Unit tests for preprocessing pipeline
"""

import pytest
import pandas as pd
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from ml.preprocessing.preprocess_data import (
    load_fastf1_data,
    load_race_results,
    preprocess_fastf1,
    preprocess_race_results,
)


class TestLoadData:

    def test_load_fastf1_data_returns_dataframe(self):
        df = load_fastf1_data()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

    def test_load_fastf1_data_has_required_columns(self):
        df = load_fastf1_data()
        required = ["season", "round", "Driver", "LapNumber", "LapTime"]
        for col in required:
            assert col in df.columns, f"Missing column: {col}"

    def test_load_race_results_returns_dataframe(self):
        df = load_race_results()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0


class TestPreprocessFastF1:

    @pytest.fixture
    def raw_data(self):
        return load_fastf1_data()

    def test_removes_invalid_laptimes(self, raw_data):
        df = preprocess_fastf1(raw_data.copy())
        assert df["LapTime"].min() > 60
        assert df["LapTime"].max() < 200

    def test_creates_compound_columns(self, raw_data):
        df = preprocess_fastf1(raw_data.copy())
        compound_cols = ["compound_SOFT", "compound_MEDIUM", "compound_HARD"]
        for col in compound_cols:
            assert col in df.columns, f"Missing column: {col}"

    def test_creates_lap_time_delta(self, raw_data):
        df = preprocess_fastf1(raw_data.copy())
        assert "lap_time_delta" in df.columns
        assert df["lap_time_delta"].between(-5, 5).all()

    def test_creates_fuel_load(self, raw_data):
        df = preprocess_fastf1(raw_data.copy())
        assert "fuel_load_pct" in df.columns
        assert df["fuel_load_pct"].between(0, 1).all()

    def test_creates_laps_to_pit(self, raw_data):
        df = preprocess_fastf1(raw_data.copy())
        assert "laps_to_pit" in df.columns

    def test_creates_driving_style(self, raw_data):
        df = preprocess_fastf1(raw_data.copy())
        assert "driving_style" in df.columns
        assert df["driving_style"].isin([0, 1, 2]).all()

    def test_creates_position(self, raw_data):
        df = preprocess_fastf1(raw_data.copy())
        assert "position" in df.columns

    def test_creates_safety_car_detection(self, raw_data):
        df = preprocess_fastf1(raw_data.copy())
        assert "is_sc_lap" in df.columns
        assert df["is_sc_lap"].isin([0, 1]).all()

    def test_creates_overtake_success(self, raw_data):
        df = preprocess_fastf1(raw_data.copy())
        assert "overtake_success" in df.columns
        assert df["overtake_success"].isin([0, 1]).all()


class TestPreprocessRaceResults:

    @pytest.fixture
    def raw_data(self):
        return load_race_results()

    def test_removes_invalid_positions(self, raw_data):
        df = preprocess_race_results(raw_data.copy())
        assert df["position"].min() >= 1
        assert df["position"].max() <= 20

    def test_removes_invalid_grid(self, raw_data):
        df = preprocess_race_results(raw_data.copy())
        assert df["grid"].min() >= 1

    def test_creates_encoded_columns(self, raw_data):
        df = preprocess_race_results(raw_data.copy())
        encoded_cols = [c for c in df.columns if "_encoded" in c]
        assert len(encoded_cols) > 0

    def test_creates_driver_avg_finish(self, raw_data):
        df = preprocess_race_results(raw_data.copy())
        has_avg = (
            "driver_avg_finish" in df.columns or "constructor_avg_finish" in df.columns
        )
        assert has_avg


class TestDataIntegrity:

    def test_seasons_in_expected_range(self):
        df = load_fastf1_data()
        df = preprocess_fastf1(df)
        assert df["season"].min() >= 2018
        assert df["season"].max() <= 2025

    def test_no_duplicate_laps(self):
        df = load_fastf1_data()
        df = preprocess_fastf1(df)
        duplicates = df.duplicated(subset=["season", "round", "Driver", "LapNumber"])
        assert duplicates.sum() == 0, f"Found {duplicates.sum()} duplicate laps"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
