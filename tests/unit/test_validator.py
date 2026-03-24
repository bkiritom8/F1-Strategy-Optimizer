"""Tests for src/preprocessing/validator.py"""
import pandas as pd
import pytest

from src.preprocessing.validator import DataValidator
from src.preprocessing.schema_validator import RaceDataSchema, ValidationError


def _race_df(**overrides):
    row = {
        "race_id": 1,
        "year": 2024,
        "round": 1,
        "circuit_id": "bahrain",
        "name": "Bahrain Grand Prix",
        "date": "2024-03-02",
    }
    row.update(overrides)
    return pd.DataFrame([row])


class TestDataValidatorInit:
    def test_initial_stats_are_zero(self):
        v = DataValidator()
        stats = v.get_validation_summary()
        assert stats["total_records"] == 0
        assert stats["valid_records"] == 0
        assert stats["invalid_records"] == 0
        assert stats["validation_rate"] == 0

    def test_warnings_initially_empty(self):
        v = DataValidator()
        assert v.validation_stats["warnings"] == []


class TestDataValidatorValidate:
    def test_valid_df_updates_stats(self):
        v = DataValidator()
        df = _race_df()
        v.validate_dataframe(df, RaceDataSchema)
        stats = v.get_validation_summary()
        assert stats["total_records"] == 1
        assert stats["valid_records"] == 1
        assert stats["invalid_records"] == 0

    def test_invalid_df_updates_invalid_count(self):
        v = DataValidator()
        df = _race_df(race_id=0)
        v.validate_dataframe(df, RaceDataSchema)
        stats = v.get_validation_summary()
        assert stats["invalid_records"] == 1
        assert stats["valid_records"] == 0

    def test_cumulative_stats_across_calls(self):
        v = DataValidator()
        v.validate_dataframe(_race_df(), RaceDataSchema)
        v.validate_dataframe(_race_df(race_id=2, round=2), RaceDataSchema)
        stats = v.get_validation_summary()
        assert stats["total_records"] == 2
        assert stats["valid_records"] == 2

    def test_missing_required_column_raises(self):
        v = DataValidator()
        df = pd.DataFrame([{"race_id": 1}])
        with pytest.raises(ValidationError):
            v.validate_dataframe(df, RaceDataSchema, required_columns=["circuit_id"])


class TestDataValidatorQuality:
    def test_returns_level_and_report(self):
        v = DataValidator()
        df = _race_df()
        level, report = v.check_data_quality(df)
        assert hasattr(level, "value")
        assert "overall_score" in report

    def test_with_column_rules(self):
        v = DataValidator()
        df = pd.DataFrame({"year": [2024, 2025, 1900]})
        rules = {"year": {"valid_range": (1950, 2025)}}
        _, report = v.check_data_quality(df, column_rules=rules)
        assert report["metrics"]["validity"]["year"]["out_of_range_count"] == 1


class TestDataValidatorSanitize:
    def test_removes_duplicates(self):
        v = DataValidator()
        df = pd.DataFrame({"a": [1, 1, 2], "b": [3, 3, 4]})
        result = v.sanitize_data(df)
        assert len(result) == 2

    def test_strips_whitespace(self):
        v = DataValidator()
        df = pd.DataFrame({"name": ["  Alice  ", "Bob"]})
        result = v.sanitize_data(df)
        assert result["name"].iloc[0] == "Alice"


class TestValidationRate:
    def test_rate_is_one_when_all_valid(self):
        v = DataValidator()
        v.validate_dataframe(_race_df(), RaceDataSchema)
        assert v.get_validation_summary()["validation_rate"] == 1.0

    def test_rate_is_zero_when_all_invalid(self):
        v = DataValidator()
        v.validate_dataframe(_race_df(race_id=0), RaceDataSchema)
        assert v.get_validation_summary()["validation_rate"] == 0.0

    def test_rate_with_no_records_is_zero(self):
        v = DataValidator()
        assert v.get_validation_summary()["validation_rate"] == 0
