"""Unit tests for tests/adversarial/reporter.py."""

import json
from unittest.mock import MagicMock


def _sample_results(n_pass: int, n_fail: int) -> list[dict]:
    results = []
    for _ in range(n_pass):
        results.append(
            {
                "verdict": "PASS",
                "category": "prompt_injection",
                "prompt": "p",
                "response_snippet": "r",
                "scorer": "keyword",
                "keyword_reason": "clean",
                "judge_reason": "SAFE",
            }
        )
    for _ in range(n_fail):
        results.append(
            {
                "verdict": "FAIL",
                "category": "scope_escape",
                "prompt": "p",
                "response_snippet": "r",
                "scorer": "judge",
                "keyword_reason": "clean",
                "judge_reason": "UNSAFE",
            }
        )
    return results


def test_build_report_schema():
    from tests.adversarial.reporter import build_report

    report = build_report(_sample_results(8, 2), "gemini-2.5-flash", "20260407-120000")
    for key in (
        "run_id",
        "timestamp",
        "model",
        "total",
        "passed",
        "failed",
        "robustness_score",
        "results",
    ):
        assert key in report, f"Missing key: {key}"


def test_build_report_counts():
    from tests.adversarial.reporter import build_report

    report = build_report(_sample_results(23, 7), "gemini-2.5-flash", "20260407-120000")
    assert report["total"] == 30
    assert report["passed"] == 23
    assert report["failed"] == 7


def test_build_report_robustness_score():
    from tests.adversarial.reporter import build_report

    report = build_report(_sample_results(25, 5), "gemini-2.5-flash", "20260407-120000")
    assert report["robustness_score"] == 0.833  # round(25/30, 3)


def test_build_report_empty_results():
    from tests.adversarial.reporter import build_report

    report = build_report([], "gemini-2.5-flash", "20260407-120000")
    assert report["total"] == 0
    assert report["robustness_score"] == 0.0


def test_build_report_run_id_and_model():
    from tests.adversarial.reporter import build_report

    report = build_report([], "gemini-2.5-flash", "MY-RUN-ID")
    assert report["run_id"] == "MY-RUN-ID"
    assert report["model"] == "gemini-2.5-flash"


def test_upload_to_gcs_calls_blob_upload():
    from tests.adversarial.reporter import upload_to_gcs

    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_gcs = MagicMock()
    mock_gcs.bucket.return_value = mock_bucket

    report = {"run_id": "20260407-120000", "total": 0, "passed": 0}
    uri = upload_to_gcs(report, mock_gcs)

    mock_gcs.bucket.assert_called_once_with("f1optimizer-training")
    mock_bucket.blob.assert_called_once_with("adversarial-reports/20260407-120000.json")
    mock_blob.upload_from_string.assert_called_once()
    args, kwargs = mock_blob.upload_from_string.call_args
    assert json.loads(args[0])["run_id"] == "20260407-120000"
    assert kwargs["content_type"] == "application/json"
    assert uri == "gs://f1optimizer-training/adversarial-reports/20260407-120000.json"


def test_build_report_timestamp_format():
    from datetime import datetime, timezone
    from tests.adversarial.reporter import build_report

    fixed_ts = datetime(2026, 4, 7, 14, 30, 22, tzinfo=timezone.utc)
    report = build_report([], "gemini-2.5-flash", "run-id", timestamp=fixed_ts)
    assert report["timestamp"] == "2026-04-07T14:30:22Z"


def test_build_report_results_are_copied():
    from tests.adversarial.reporter import build_report

    original = [{"verdict": "PASS"}]
    report = build_report(original, "gemini-2.5-flash", "run-id")
    original.append({"verdict": "FAIL"})  # mutate after build
    assert len(report["results"]) == 1  # report should be unaffected
