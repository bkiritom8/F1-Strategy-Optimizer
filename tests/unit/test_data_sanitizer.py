"""Tests for src/preprocessing/data_sanitizer.py"""
import numpy as np
import pandas as pd
import pytest

from src.preprocessing.data_sanitizer import sanitize_data


class TestSanitizeData:
    def test_removes_all_null_rows(self):
        df = pd.DataFrame({"a": [1, None, 3], "b": [4, None, 6]})
        result = sanitize_data(df)
        assert len(result) == 2
        assert result["a"].tolist() == [1.0, 3.0]

    def test_strips_whitespace_from_string_columns(self):
        df = pd.DataFrame({"name": ["  Alice  ", " Bob", "Carol "]})
        result = sanitize_data(df)
        assert result["name"].tolist() == ["Alice", "Bob", "Carol"]

    def test_replaces_blank_strings_with_nan(self):
        df = pd.DataFrame({"x": ["a", "   ", "b", "c"]})
        result = sanitize_data(df)
        # "   " is stripped to "" then replaced with NaN
        assert result["x"].isna().sum() == 1
        assert result["x"].dropna().tolist() == ["a", "b", "c"]

    def test_removes_duplicate_rows(self):
        df = pd.DataFrame({"a": [1, 2, 1], "b": [3, 4, 3]})
        result = sanitize_data(df)
        assert len(result) == 2

    def test_does_not_modify_original_dataframe(self):
        df = pd.DataFrame({"a": [1, None], "b": ["  x", "y"]})
        original_len = len(df)
        sanitize_data(df)
        assert len(df) == original_len

    def test_non_string_columns_unaffected_by_strip(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": [1.1, 2.2, 3.3]})
        result = sanitize_data(df)
        assert result["a"].tolist() == [1, 2, 3]

    def test_empty_dataframe_returns_empty(self):
        df = pd.DataFrame({"a": [], "b": []})
        result = sanitize_data(df)
        assert len(result) == 0

    def test_all_null_row_removed_partial_nulls_kept(self):
        df = pd.DataFrame({"a": [1, None, 3], "b": [None, None, 6]})
        result = sanitize_data(df)
        # Row 1 is all-null → removed; rows 0 and 2 kept
        assert len(result) == 2
