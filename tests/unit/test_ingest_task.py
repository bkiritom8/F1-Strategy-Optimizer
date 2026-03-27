"""
Unit tests for ingest/task.py — dispatcher routing logic.

All GCS / Cloud Logging dependencies are mocked.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

# Stub heavy transitive dependencies before importing ingest.task so that
# patch("ingest.task.*") can resolve the module at collection time.
from unittest.mock import MagicMock as _MM

_stubs = {
    "google.cloud.logging": _MM(),
    "google.cloud.logging_v2": _MM(),
    "google.cloud.logging.handlers": _MM(),
    "fastf1": _MM(),
}
for _name, _mock in _stubs.items():
    sys.modules.setdefault(_name, _mock)

# Stub the worker submodules so ingest.task's top-level imports resolve
# without pulling in fastf1 / other heavy deps.
_fastf1_worker_stub = _MM()
_fastf1_worker_stub.run = _MM()
_historical_worker_stub = _MM()
_historical_worker_stub.run = _MM()
sys.modules["ingest.fastf1_worker"] = _fastf1_worker_stub
sys.modules["ingest.historical_worker"] = _historical_worker_stub

import ingest.task  # noqa: E402


def _make_mocks():
    """Return a consistent set of mock objects for task.main()."""
    mock_bucket = MagicMock()
    mock_gcs_client = MagicMock()
    mock_gcs_client.bucket.return_value = mock_bucket
    mock_progress = MagicMock()
    return mock_gcs_client, mock_bucket, mock_progress


class TestTaskDispatcher:
    """Tests for ingest.task.main() routing logic."""

    @pytest.mark.parametrize("index,expected_year", [
        (0, 2018),
        (1, 2019),
        (3, 2021),
        (7, 2025),
    ])
    def test_fastf1_tasks_route_to_correct_year(self, index, expected_year, monkeypatch):
        monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", str(index))
        monkeypatch.setenv("GCS_BUCKET", "test-bucket")

        mock_gcs_client, mock_bucket, mock_progress = _make_mocks()

        with patch("ingest.task.storage.Client", return_value=mock_gcs_client), \
             patch("ingest.task.Progress", return_value=mock_progress), \
             patch("ingest.task.run_fastf1") as mock_fastf1, \
             patch("ingest.task.run_historical") as mock_historical, \
             patch("ingest.task.cloud_logging.Client"):
            from ingest.task import main
            main()

        mock_fastf1.assert_called_once_with(expected_year, index, mock_bucket, mock_progress)
        mock_historical.assert_not_called()

    def test_historical_task_routes_to_historical_worker(self, monkeypatch):
        monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "8")
        monkeypatch.setenv("GCS_BUCKET", "test-bucket")

        mock_gcs_client, mock_bucket, mock_progress = _make_mocks()

        with patch("ingest.task.storage.Client", return_value=mock_gcs_client), \
             patch("ingest.task.Progress", return_value=mock_progress), \
             patch("ingest.task.run_fastf1") as mock_fastf1, \
             patch("ingest.task.run_historical") as mock_historical, \
             patch("ingest.task.cloud_logging.Client"):
            from ingest.task import main
            main()

        mock_historical.assert_called_once_with(8, mock_bucket, mock_progress)
        mock_fastf1.assert_not_called()

    def test_invalid_task_index_exits_with_error(self, monkeypatch):
        monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "99")
        monkeypatch.setenv("GCS_BUCKET", "test-bucket")

        mock_gcs_client, mock_bucket, _ = _make_mocks()

        with patch("ingest.task.storage.Client", return_value=mock_gcs_client), \
             patch("ingest.task.Progress"), \
             patch("ingest.task.run_fastf1"), \
             patch("ingest.task.run_historical"), \
             patch("ingest.task.cloud_logging.Client"), \
             pytest.raises(SystemExit) as exc_info:
            from ingest.task import main
            main()

        assert exc_info.value.code == 1

    def test_default_task_index_is_zero(self, monkeypatch):
        """When CLOUD_RUN_TASK_INDEX is not set, defaults to 0 (year 2018)."""
        monkeypatch.delenv("CLOUD_RUN_TASK_INDEX", raising=False)
        monkeypatch.setenv("GCS_BUCKET", "test-bucket")

        mock_gcs_client, mock_bucket, mock_progress = _make_mocks()

        with patch("ingest.task.storage.Client", return_value=mock_gcs_client), \
             patch("ingest.task.Progress", return_value=mock_progress), \
             patch("ingest.task.run_fastf1") as mock_fastf1, \
             patch("ingest.task.run_historical"), \
             patch("ingest.task.cloud_logging.Client"):
            from ingest.task import main
            main()

        mock_fastf1.assert_called_once_with(2018, 0, mock_bucket, mock_progress)

    def test_gcs_bucket_passed_to_workers(self, monkeypatch):
        monkeypatch.setenv("CLOUD_RUN_TASK_INDEX", "0")
        monkeypatch.setenv("GCS_BUCKET", "my-custom-bucket")

        mock_gcs_client = MagicMock()
        mock_bucket = MagicMock()
        mock_gcs_client.bucket.return_value = mock_bucket

        with patch("ingest.task.storage.Client", return_value=mock_gcs_client), \
             patch("ingest.task.Progress"), \
             patch("ingest.task.run_fastf1"), \
             patch("ingest.task.run_historical"), \
             patch("ingest.task.cloud_logging.Client"):
            from ingest.task import main
            main()

        mock_gcs_client.bucket.assert_called_once_with("my-custom-bucket")
