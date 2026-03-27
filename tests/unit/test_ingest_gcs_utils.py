"""
Unit tests for ingest/gcs_utils.py — GCS upload helpers.

All GCS I/O is mocked; tests verify serialisation, blob path construction,
content-type headers, and the exists() delegation.
"""

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))


def _make_bucket(blob=None):
    bucket = MagicMock()
    bucket.name = "test-bucket"
    if blob is not None:
        bucket.blob.return_value = blob
    else:
        bucket.blob.return_value = MagicMock()
    return bucket


class TestUploadParquet:
    def test_uploads_parquet_bytes_to_correct_path(self):
        from ingest.gcs_utils import upload_parquet

        blob = MagicMock()
        bucket = _make_bucket(blob)
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

        upload_parquet(df, bucket, "raw/laps.parquet")

        bucket.blob.assert_called_once_with("raw/laps.parquet")
        blob.upload_from_file.assert_called_once()
        _, kwargs = blob.upload_from_file.call_args
        assert kwargs["content_type"] == "application/octet-stream"

    def test_uploaded_bytes_are_valid_parquet(self):
        from ingest.gcs_utils import upload_parquet

        captured = {}

        def fake_upload(buf, content_type):
            captured["data"] = buf.read()

        blob = MagicMock()
        blob.upload_from_file.side_effect = fake_upload
        bucket = _make_bucket(blob)

        df = pd.DataFrame({"x": [10, 20, 30]})
        upload_parquet(df, bucket, "any/path.parquet")

        result = pd.read_parquet(io.BytesIO(captured["data"]))
        pd.testing.assert_frame_equal(result, df)

    def test_upload_empty_dataframe(self):
        from ingest.gcs_utils import upload_parquet

        blob = MagicMock()
        bucket = _make_bucket(blob)
        df = pd.DataFrame({"col": pd.Series([], dtype="int64")})

        upload_parquet(df, bucket, "empty.parquet")

        blob.upload_from_file.assert_called_once()


class TestUploadDoneMarker:
    def test_writes_to_correct_blob_path(self):
        from ingest.gcs_utils import upload_done_marker

        blob = MagicMock()
        bucket = _make_bucket(blob)

        upload_done_marker(bucket, 3)

        bucket.blob.assert_called_once_with("status/task_3.done")

    def test_uploads_empty_string(self):
        from ingest.gcs_utils import upload_done_marker

        blob = MagicMock()
        bucket = _make_bucket(blob)

        upload_done_marker(bucket, 0)

        blob.upload_from_string.assert_called_once_with(
            "", content_type="text/plain"
        )

    def test_task_id_appears_in_blob_name(self):
        from ingest.gcs_utils import upload_done_marker

        blob = MagicMock()
        bucket = _make_bucket(blob)

        upload_done_marker(bucket, 7)

        path = bucket.blob.call_args[0][0]
        assert "7" in path


class TestBlobExists:
    def test_returns_true_when_blob_exists(self):
        from ingest.gcs_utils import blob_exists

        blob = MagicMock()
        blob.exists.return_value = True
        bucket = _make_bucket(blob)

        assert blob_exists(bucket, "some/path.parquet") is True

    def test_returns_false_when_blob_absent(self):
        from ingest.gcs_utils import blob_exists

        blob = MagicMock()
        blob.exists.return_value = False
        bucket = _make_bucket(blob)

        assert blob_exists(bucket, "missing/file.parquet") is False

    def test_checks_correct_path(self):
        from ingest.gcs_utils import blob_exists

        blob = MagicMock()
        blob.exists.return_value = False
        bucket = _make_bucket(blob)

        blob_exists(bucket, "data/2023/laps.parquet")

        bucket.blob.assert_called_once_with("data/2023/laps.parquet")
