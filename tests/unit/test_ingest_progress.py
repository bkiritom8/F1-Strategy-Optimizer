"""
Unit tests for ingest/progress.py — GCS-backed optimistic locking.

All GCS I/O is mocked; tests verify the read/modify/write logic,
idempotency, and conflict-retry behaviour.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from google.api_core import exceptions as gcp_exc


def _make_blob(data: dict, generation: int = 1):
    """Create a mock GCS blob that returns *data* on download."""
    blob = MagicMock()
    blob.generation = generation
    blob.download_as_text.return_value = json.dumps(data)
    blob.upload_from_string.return_value = None
    return blob


def _make_bucket(blob):
    bucket = MagicMock()
    bucket.blob.return_value = blob
    return bucket


class TestProgressIsDone:
    def test_returns_false_when_blob_not_found(self):
        from ingest.progress import Progress

        blob = MagicMock()
        blob.reload.side_effect = gcp_exc.NotFound("not found")
        bucket = _make_bucket(blob)

        p = Progress(bucket)
        assert p.is_done("task_0") is False

    def test_returns_false_when_key_absent(self):
        from ingest.progress import Progress

        blob = _make_blob({"other_key": "done"})
        p = Progress(_make_bucket(blob))
        assert p.is_done("task_0") is False

    def test_returns_true_when_key_is_done(self):
        from ingest.progress import Progress

        blob = _make_blob({"task_0": "done"})
        p = Progress(_make_bucket(blob))
        assert p.is_done("task_0") is True

    def test_returns_false_when_key_has_wrong_value(self):
        from ingest.progress import Progress

        blob = _make_blob({"task_0": "in_progress"})
        p = Progress(_make_bucket(blob))
        assert p.is_done("task_0") is False


class TestProgressMarkDone:
    def test_marks_key_done_on_success(self):
        from ingest.progress import Progress

        blob = _make_blob({}, generation=5)
        p = Progress(_make_bucket(blob))
        p.mark_done("task_3")

        uploaded = json.loads(blob.upload_from_string.call_args[0][0])
        assert uploaded["task_3"] == "done"
        assert blob.upload_from_string.call_args[1]["if_generation_match"] == 5

    def test_idempotent_when_already_done(self):
        from ingest.progress import Progress

        blob = _make_blob({"task_3": "done"})
        p = Progress(_make_bucket(blob))
        p.mark_done("task_3")

        blob.upload_from_string.assert_not_called()

    def test_retries_on_412_precondition_failed(self):
        from ingest.progress import Progress

        blob = MagicMock()
        blob.generation = 1
        blob.download_as_text.return_value = json.dumps({})
        # First write fails with 412; second write succeeds
        blob.upload_from_string.side_effect = [
            gcp_exc.PreconditionFailed("conflict"),
            None,
        ]

        with patch("ingest.progress.time.sleep"):
            p = Progress(_make_bucket(blob))
            p.mark_done("task_1")

        assert blob.upload_from_string.call_count == 2

    def test_preserves_existing_keys_when_marking_done(self):
        from ingest.progress import Progress

        blob = _make_blob({"task_0": "done", "task_1": "done"})
        p = Progress(_make_bucket(blob))
        p.mark_done("task_2")

        uploaded = json.loads(blob.upload_from_string.call_args[0][0])
        assert uploaded["task_0"] == "done"
        assert uploaded["task_1"] == "done"
        assert uploaded["task_2"] == "done"


class TestProgressWrite:
    def test_write_returns_true_on_success(self):
        from ingest.progress import Progress

        blob = MagicMock()
        blob.upload_from_string.return_value = None
        p = Progress(_make_bucket(blob))
        result = p._write({"key": "val"}, generation=3)
        assert result is True

    def test_write_returns_false_on_precondition_failed(self):
        from ingest.progress import Progress

        blob = MagicMock()
        blob.upload_from_string.side_effect = gcp_exc.PreconditionFailed("conflict")
        p = Progress(_make_bucket(blob))
        result = p._write({"key": "val"}, generation=3)
        assert result is False


class TestProgressRead:
    def test_read_returns_empty_dict_and_zero_generation_when_not_found(self):
        from ingest.progress import Progress

        blob = MagicMock()
        blob.reload.side_effect = gcp_exc.NotFound("not found")
        p = Progress(_make_bucket(blob))
        data, gen = p._read()
        assert data == {}
        assert gen == 0

    def test_read_returns_data_and_generation(self):
        from ingest.progress import Progress

        blob = _make_blob({"task_0": "done"}, generation=7)
        p = Progress(_make_bucket(blob))
        data, gen = p._read()
        assert data == {"task_0": "done"}
        assert gen == 7
