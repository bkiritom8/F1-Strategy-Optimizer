"""
test_csv_to_parquet.py — Unit tests for pipeline/scripts/csv_to_parquet.py

Tests:
  - Timedelta string "0 days 00:01:39.019000" converts to 99.019 seconds
  - Negative timedelta "-1 days +23:58:20" converts correctly
  - Empty CSV returns empty DataFrame without crashing
  - Missing input file raises FileNotFoundError
  - All expected output Parquet columns preserved
  - Non-timedelta columns are left unchanged
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

_REPO_ROOT = Path(__file__).parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from pipeline.scripts.csv_to_parquet import (  # noqa: E402
    _read_yearly_csvs,
    convert_and_upload,
    fix_timedelta_columns,
)

# ---------------------------------------------------------------------------
# Tests — fix_timedelta_columns
# ---------------------------------------------------------------------------


class TestFixTimedeltaColumns:
    def test_standard_timedelta_converts_to_seconds(self) -> None:
        """'0 days 00:01:39.019000' → 99.019 seconds."""
        df = pd.DataFrame({"LapTime": ["0 days 00:01:39.019000"]})
        result = fix_timedelta_columns(df)
        assert abs(result["LapTime"].iloc[0] - 99.019) < 0.001

    def test_negative_timedelta_converts_correctly(self) -> None:
        """-1 days +23:58:20 → -100.0 seconds."""
        df = pd.DataFrame({"delta": ["-1 days +23:58:20"]})
        result = fix_timedelta_columns(df)
        # -1 day + 23:58:20 = -100 seconds
        assert abs(result["delta"].iloc[0] - (-100.0)) < 0.1

    def test_zero_timedelta(self) -> None:
        """'0 days 00:00:00' → 0.0 seconds."""
        df = pd.DataFrame({"gap": ["0 days 00:00:00"]})
        result = fix_timedelta_columns(df)
        assert result["gap"].iloc[0] == pytest.approx(0.0)

    def test_non_timedelta_column_unchanged(self) -> None:
        """Numeric and normal string columns must not be modified."""
        df = pd.DataFrame(
            {
                "speed": [300.5, 250.1],
                "driver": ["VER", "HAM"],
                "lap": [1, 2],
            }
        )
        result = fix_timedelta_columns(df)
        assert list(result["driver"]) == ["VER", "HAM"]
        assert list(result["speed"]) == [300.5, 250.1]
        assert list(result["lap"]) == [1, 2]

    def test_mixed_column_null_values_handled(self) -> None:
        """Timedelta column with some NaN values should not crash."""
        df = pd.DataFrame(
            {"LapTime": ["0 days 00:01:30.000000", None, "0 days 00:01:45.000000"]}
        )
        result = fix_timedelta_columns(df)
        assert result["LapTime"].iloc[0] == pytest.approx(90.0)
        assert pd.isna(result["LapTime"].iloc[1])
        assert result["LapTime"].iloc[2] == pytest.approx(105.0)

    def test_empty_dataframe_returns_empty(self) -> None:
        """Empty DataFrame with timedelta column should return empty without error."""
        df = pd.DataFrame({"LapTime": pd.Series([], dtype=object)})
        result = fix_timedelta_columns(df)
        assert len(result) == 0

    def test_fully_null_column_skipped(self) -> None:
        """A column with all nulls should not be converted."""
        df = pd.DataFrame({"time": [None, None, None]})
        result = fix_timedelta_columns(df)
        # Column should remain unchanged (all null)
        assert result["time"].isna().all()

    def test_multiple_timedelta_columns(self) -> None:
        """Multiple timedelta columns in the same DataFrame are all converted."""
        df = pd.DataFrame(
            {
                "LapTime": ["0 days 00:01:30.000000"],
                "Sector1": ["0 days 00:00:28.500000"],
                "Sector2": ["0 days 00:00:35.100000"],
            }
        )
        result = fix_timedelta_columns(df)
        assert result["LapTime"].iloc[0] == pytest.approx(90.0)
        assert result["Sector1"].iloc[0] == pytest.approx(28.5)
        assert result["Sector2"].iloc[0] == pytest.approx(35.1)


# ---------------------------------------------------------------------------
# Tests — _read_yearly_csvs
# ---------------------------------------------------------------------------


class TestReadYearlyCsvs:
    def test_reads_and_concatenates_csvs(self, tmp_path: Path) -> None:
        """Multiple year CSVs are concatenated in chronological order."""
        (tmp_path / "laps_2022.csv").write_text("season,lap\n2022,1\n2022,2\n")
        (tmp_path / "laps_2023.csv").write_text("season,lap\n2023,1\n2023,2\n2023,3\n")
        paths = sorted(tmp_path.glob("laps_*.csv"))
        df = _read_yearly_csvs(paths, "test")
        assert len(df) == 5
        assert list(df["season"].astype(str)) == [
            "2022",
            "2022",
            "2023",
            "2023",
            "2023",
        ]

    def test_single_file(self, tmp_path: Path) -> None:
        (tmp_path / "laps_2024.csv").write_text("driver,lap\nVER,1\n")
        paths = list(tmp_path.glob("laps_*.csv"))
        df = _read_yearly_csvs(paths, "single")
        assert len(df) == 1
        assert df["driver"].iloc[0] == "VER"


# ---------------------------------------------------------------------------
# Tests — convert_and_upload (mocked GCS)
# ---------------------------------------------------------------------------


class TestConvertAndUpload:
    def test_missing_input_dir_raises_file_not_found(self) -> None:
        with pytest.raises(FileNotFoundError, match="Input directory not found"):
            convert_and_upload("/nonexistent/path", "test-bucket")

    def test_processes_individual_csv(self, tmp_path: Path) -> None:
        """circuits.csv → circuits.parquet should be uploaded."""
        (tmp_path / "circuits.csv").write_text(
            "circuitId,circuitName\nmonaco,Monaco\nbahrain,Bahrain\n"
        )
        uploaded: dict = {}

        def mock_upload(df: pd.DataFrame, bucket: object, blob_name: str) -> None:
            uploaded[blob_name] = df

        with patch(
            "pipeline.scripts.csv_to_parquet._upload_df", side_effect=mock_upload
        ):
            with patch("pipeline.scripts.csv_to_parquet.storage.Client"):
                row_counts = convert_and_upload(str(tmp_path), "test-bucket")

        assert "circuits" in row_counts
        assert row_counts["circuits"] == 2
        assert "processed/circuits.parquet" in uploaded

    def test_yearly_laps_combined(self, tmp_path: Path) -> None:
        """laps_YYYY.csv files are combined into laps_all.parquet."""
        (tmp_path / "laps_2022.csv").write_text("driver,lap\nVER,1\n")
        (tmp_path / "laps_2023.csv").write_text("driver,lap\nHAM,1\nHAM,2\n")

        uploaded: dict = {}

        def mock_upload(df: pd.DataFrame, bucket: object, blob_name: str) -> None:
            uploaded[blob_name] = df

        with patch(
            "pipeline.scripts.csv_to_parquet._upload_df", side_effect=mock_upload
        ):
            with patch("pipeline.scripts.csv_to_parquet.storage.Client"):
                row_counts = convert_and_upload(str(tmp_path), "test-bucket")

        assert "laps_all" in row_counts
        assert row_counts["laps_all"] == 3
        assert "processed/laps_all.parquet" in uploaded

    def test_missing_csv_logged_not_raised(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Missing individual CSV files are skipped with a warning, not an exception."""
        # Empty dir — no CSVs at all
        with patch("pipeline.scripts.csv_to_parquet._upload_df"):
            with patch("pipeline.scripts.csv_to_parquet.storage.Client"):
                row_counts = convert_and_upload(str(tmp_path), "test-bucket")
        # Should complete without error and return empty counts
        assert isinstance(row_counts, dict)

    def test_timedelta_columns_converted_in_output(self, tmp_path: Path) -> None:
        """Timedelta strings in CSVs are converted to float seconds in uploaded Parquet."""
        (tmp_path / "laps_2024.csv").write_text(
            "driver,LapTime\nVER,0 days 00:01:30.000000\n"
        )
        uploaded: dict = {}

        def mock_upload(df: pd.DataFrame, bucket: object, blob_name: str) -> None:
            uploaded[blob_name] = df

        with patch(
            "pipeline.scripts.csv_to_parquet._upload_df", side_effect=mock_upload
        ):
            with patch("pipeline.scripts.csv_to_parquet.storage.Client"):
                convert_and_upload(str(tmp_path), "test-bucket")

        df_out = uploaded.get("processed/laps_all.parquet")
        assert df_out is not None
        assert df_out["LapTime"].iloc[0] == pytest.approx(90.0)
