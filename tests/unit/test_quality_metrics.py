"""Tests for src/preprocessing/quality_metrics.py"""
import pandas as pd
import pytest

from src.preprocessing.quality_metrics import DataQualityLevel, check_data_quality


class TestDataQualityLevel:
    def test_enum_values(self):
        assert DataQualityLevel.HIGH == "high"
        assert DataQualityLevel.MEDIUM == "medium"
        assert DataQualityLevel.LOW == "low"
        assert DataQualityLevel.INVALID == "invalid"


class TestCheckDataQuality:
    def _clean_df(self):
        return pd.DataFrame({
            "a": [1, 2, 3, 4, 5],
            "b": [10, 20, 30, 40, 50],
        })

    def test_high_quality_clean_data(self):
        df = self._clean_df()
        level, report = check_data_quality(df)
        assert level == DataQualityLevel.HIGH
        assert report["overall_score"] >= 90

    def test_report_contains_required_keys(self):
        df = self._clean_df()
        _, report = check_data_quality(df)
        assert "overall_score" in report
        assert "quality_level" in report
        assert "metrics" in report
        assert "scores" in report

    def test_scores_keys(self):
        df = self._clean_df()
        _, report = check_data_quality(df)
        assert "completeness" in report["scores"]
        assert "validity" in report["scores"]
        assert "consistency" in report["scores"]

    def test_null_values_reduce_completeness(self):
        df = pd.DataFrame({"a": [1, None, None, None, None], "b": [1, 2, 3, 4, 5]})
        level, report = check_data_quality(df)
        assert report["scores"]["completeness"] < 100

    def test_duplicates_reduce_consistency(self):
        df = pd.DataFrame({"a": [1, 1, 1, 1, 1], "b": [2, 2, 2, 2, 2]})
        _, report = check_data_quality(df)
        assert report["scores"]["consistency"] < 100
        assert report["metrics"]["consistency"]["duplicates"]["count"] > 0

    def test_completeness_metrics_per_column(self):
        df = pd.DataFrame({"x": [1, None, 3], "y": [4, 5, 6]})
        _, report = check_data_quality(df)
        assert "x" in report["metrics"]["completeness"]
        assert "y" in report["metrics"]["completeness"]
        assert report["metrics"]["completeness"]["x"]["null_count"] == 1
        assert report["metrics"]["completeness"]["y"]["null_count"] == 0

    def test_validity_rules_applied(self):
        df = pd.DataFrame({"speed": [100, 200, 500, 150, 80]})
        rules = {"speed": {"valid_range": (0, 400)}}
        _, report = check_data_quality(df, column_rules=rules)
        assert "speed" in report["metrics"]["validity"]
        assert report["metrics"]["validity"]["speed"]["out_of_range_count"] == 1

    def test_validity_rule_missing_column_skipped(self):
        df = pd.DataFrame({"a": [1, 2, 3]})
        rules = {"nonexistent": {"valid_range": (0, 10)}}
        level, report = check_data_quality(df, column_rules=rules)
        assert "nonexistent" not in report["metrics"]["validity"]

    def test_low_quality_heavily_null_data(self):
        df = pd.DataFrame({
            "a": [None] * 8 + [1, 2],
            "b": [None] * 8 + [1, 2],
            "c": [None] * 8 + [1, 2],
        })
        level, _ = check_data_quality(df)
        assert level in (DataQualityLevel.LOW, DataQualityLevel.INVALID, DataQualityLevel.MEDIUM)

    def test_quality_level_in_report_matches_returned_level(self):
        df = self._clean_df()
        level, report = check_data_quality(df)
        assert report["quality_level"] == level.value

    def test_no_column_rules_returns_empty_validity(self):
        df = self._clean_df()
        _, report = check_data_quality(df)
        assert report["metrics"]["validity"] == {}
