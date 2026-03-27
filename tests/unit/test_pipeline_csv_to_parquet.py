"""
Unit tests for pipeline/scripts/csv_to_parquet.py.

Tests the pure-logic helpers (fix_timedelta_columns, _read_yearly_csvs) and
the convert_and_upload orchestrator with all GCS I/O mocked.
"""

import io
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from pipeline.scripts.csv_to_parquet import (
    fix_timedelta_columns,
    _read_yearly_csvs,
    convert_and_upload,
)


class TestFixTimedeltaColumns:
    def test_converts_days_string_column_to_float(self):
        df = pd.DataFrame({"time": ["0 days 00:01:30", "0 days 00:02:00"]})
        result = fix_timedelta_columns(df)
        assert pd.api.types.is_float_dtype(result["time"])
        assert result["time"].iloc[0] == pytest.approx(90.0)

    def test_ignores_numeric_columns(self):
        df = pd.DataFrame({"laps": [1, 2, 3], "lap_time": [90.1, 91.2, 89.5]})
        result = fix_timedelta_columns(df)
        assert list(result["laps"]) == [1, 2, 3]
        assert list(result["lap_time"]) == pytest.approx([90.1, 91.2, 89.5])

    def test_ignores_non_timedelta_string_columns(self):
        df = pd.DataFrame({"compound": ["SOFT", "MEDIUM", "HARD"]})
        result = fix_timedelta_columns(df)
        assert list(result["compound"]) == ["SOFT", "MEDIUM", "HARD"]

    def test_handles_empty_column_gracefully(self):
        df = pd.DataFrame({"time": pd.Series([], dtype="object")})
        result = fix_timedelta_columns(df)
        assert "time" in result.columns

    def test_mixed_timedelta_and_normal_columns(self):
        df = pd.DataFrame(
            {
                "lap_time": ["0 days 00:01:30", "0 days 00:01:35"],
                "driver": ["VER", "HAM"],
            }
        )
        result = fix_timedelta_columns(df)
        assert pd.api.types.is_float_dtype(result["lap_time"])
        assert list(result["driver"]) == ["VER", "HAM"]


class TestReadYearlyCsvs:
    def test_reads_and_concatenates_in_order(self, tmp_path):
        p2020 = tmp_path / "laps_2020.csv"
        p2021 = tmp_path / "laps_2021.csv"
        pd.DataFrame({"season": [2020], "lap": [1]}).to_csv(p2020, index=False)
        pd.DataFrame({"season": [2021], "lap": [1]}).to_csv(p2021, index=False)

        result = _read_yearly_csvs([p2021, p2020], "test")

        assert len(result) == 2
        # Should be sorted chronologically
        assert list(result["season"]) == [2020, 2021]

    def test_single_file_returns_correct_data(self, tmp_path):
        p = tmp_path / "laps_2022.csv"
        pd.DataFrame({"x": [10, 20]}).to_csv(p, index=False)

        result = _read_yearly_csvs([p], "laps")
        assert len(result) == 2

    def test_reset_index_on_concatenated_result(self, tmp_path):
        files = []
        for year in [2018, 2019]:
            p = tmp_path / f"laps_{year}.csv"
            pd.DataFrame({"season": [year] * 3}).to_csv(p, index=False)
            files.append(p)

        result = _read_yearly_csvs(files, "test")
        assert list(result.index) == list(range(len(result)))


class TestConvertAndUpload:
    def _make_input_dir(self, tmp_path):
        """Create a minimal raw/ directory with one laps CSV and one individual CSV."""
        raw = tmp_path / "raw"
        raw.mkdir()
        pd.DataFrame({"season": [2023], "time": [90.0]}).to_csv(
            raw / "laps_2023.csv", index=False
        )
        pd.DataFrame({"circuitId": ["bahrain"], "country": ["Bahrain"]}).to_csv(
            raw / "circuits.csv", index=False
        )
        return raw

    def _make_mock_bucket(self):
        blob = MagicMock()
        blob.upload_from_file.return_value = None
        bucket = MagicMock()
        bucket.name = "test-bucket"
        bucket.blob.return_value = blob
        return bucket, blob

    def test_raises_when_input_dir_missing(self, tmp_path):
        with patch("pipeline.scripts.csv_to_parquet.storage.Client"):
            with pytest.raises(FileNotFoundError):
                convert_and_upload(str(tmp_path / "nonexistent"), "bucket")

    def test_uploads_laps_all_parquet(self, tmp_path):
        raw = self._make_input_dir(tmp_path)
        bucket, blob = self._make_mock_bucket()
        mock_client = MagicMock()
        mock_client.bucket.return_value = bucket

        with patch(
            "pipeline.scripts.csv_to_parquet.storage.Client",
            return_value=mock_client,
        ):
            counts = convert_and_upload(str(raw), "test-bucket")

        assert "laps_all" in counts
        assert counts["laps_all"] == 1

    def test_uploads_individual_csv_if_present(self, tmp_path):
        raw = self._make_input_dir(tmp_path)
        bucket, blob = self._make_mock_bucket()
        mock_client = MagicMock()
        mock_client.bucket.return_value = bucket

        with patch(
            "pipeline.scripts.csv_to_parquet.storage.Client",
            return_value=mock_client,
        ):
            counts = convert_and_upload(str(raw), "test-bucket")

        assert "circuits" in counts
        assert counts["circuits"] == 1

    def test_skips_missing_individual_csvs(self, tmp_path):
        raw = tmp_path / "raw"
        raw.mkdir()
        pd.DataFrame({"season": [2023]}).to_csv(raw / "laps_2023.csv", index=False)
        bucket, _ = self._make_mock_bucket()
        mock_client = MagicMock()
        mock_client.bucket.return_value = bucket

        with patch(
            "pipeline.scripts.csv_to_parquet.storage.Client",
            return_value=mock_client,
        ):
            counts = convert_and_upload(str(raw), "test-bucket")

        # circuits.csv was not in raw/, so it should not appear in counts
        assert "circuits" not in counts

    def test_no_laps_csvs_does_not_crash(self, tmp_path):
        raw = tmp_path / "raw"
        raw.mkdir()
        bucket, _ = self._make_mock_bucket()
        mock_client = MagicMock()
        mock_client.bucket.return_value = bucket

        with patch(
            "pipeline.scripts.csv_to_parquet.storage.Client",
            return_value=mock_client,
        ):
            counts = convert_and_upload(str(raw), "test-bucket")

        assert "laps_all" not in counts
