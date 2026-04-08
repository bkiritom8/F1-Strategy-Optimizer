"""Shared fixtures and session hook for adversarial tests."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

logger = logging.getLogger(__name__)

# Module-level state shared between fixtures and the sessionfinish hook.
# NOTE: Not safe for pytest-xdist parallel workers — each worker has its own process.
_session_results: list[dict] = []
_run_id: str = ""


def pytest_configure(config: pytest.Config) -> None:
    """Set the run_id once at session start."""
    global _run_id
    _session_results.clear()
    _run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


@pytest.fixture(scope="session")
def run_id() -> str:
    """UTC timestamp run ID, e.g. '20260407-143022'."""
    return _run_id


@pytest.fixture(scope="session")
def results_collector() -> list[dict]:
    """Mutable list that each test appends its result dict to."""
    return _session_results


@pytest.fixture(scope="session")
def gemini_client():
    """Real GeminiClient using ambient GCP credentials (ADC)."""
    from rag.config import RagConfig
    from src.llm.gemini_client import GeminiClient

    return GeminiClient(RagConfig())


@pytest.fixture(scope="session")
def gcs_client():
    """GCS client using ambient GCP credentials."""
    from google.cloud import storage

    return storage.Client()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Upload the JSON report to GCS after all tests finish."""
    if not _session_results:
        logger.warning("No adversarial results collected — skipping GCS upload.")
        return

    try:
        from google.cloud import storage as _storage
        from rag.config import RagConfig
        from tests.adversarial.reporter import build_report, upload_to_gcs

        config = RagConfig()
        report = build_report(_session_results, config.LLM_MODEL, _run_id)
        gcs = _storage.Client()
        uri = upload_to_gcs(report, gcs)
        print(f"\nAdversarial report → {uri}")
        print(
            f"Robustness score: {report['passed']}/{report['total']} "
            f"({report['robustness_score']:.1%})"
        )
    except Exception as exc:
        logger.error("Failed to upload adversarial report to GCS: %s", exc)
        print(f"\nWarning: GCS upload failed — {exc}")
