"""
Run all ML tests as a Vertex AI Custom Job.

Machine: n1-standard-4 (no GPU needed — tests use real GCS data and CPU-only params).
Reports results to Cloud Logging.
Exits with code 1 if any test fails (fails the Vertex AI job).

Usage:
    # From Vertex AI Workbench terminal or Cloud Run Job:
    python ml/tests/run_tests_on_vertex.py

    # With specific test file:
    python ml/tests/run_tests_on_vertex.py --test-path ml/tests/test_models.py

    # As a Cloud Run Job:
    gcloud run jobs execute f1-test-runner --region=us-central1 --project=f1optimizer
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone

from google.cloud import aiplatform, logging as cloud_logging

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
REGION = os.environ.get("REGION", "us-central1")
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "gs://f1optimizer-training")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "gs://f1optimizer-models")
ML_IMAGE = "us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest"
SERVICE_ACCOUNT = f"f1-training-dev@{PROJECT_ID}.iam.gserviceaccount.com"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("f1.tests.runner")


def download_models(local_dir: str = "/app/models") -> None:
    """
    Download trained model .pkl files from GCS to local_dir so
    test_models.py can load them with joblib.
    """
    os.makedirs(local_dir, exist_ok=True)
    logger.info("Downloading models from %s to %s", MODELS_BUCKET, local_dir)
    result = subprocess.run(
        ["gsutil", "-m", "cp", f"{MODELS_BUCKET}/*.pkl", local_dir],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        logger.warning(
            "gsutil cp returned non-zero: %s — tests may fail if models are missing",
            result.stderr.strip(),
        )
    else:
        logger.info("Models downloaded OK to %s", local_dir)


def run_tests_locally(test_path: str) -> tuple[int, str]:
    """
    Run pytest in-process (used when already inside a Vertex AI container).
    Downloads model artifacts from GCS before running.
    Returns (exit_code, output_text).
    """
    download_models("/app/models")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            test_path,
            "-v",
            "--tb=short",
            "--no-header",
            "--junitxml=/tmp/test_results.xml",
        ],
        capture_output=True,
        text=True,
        cwd="/app",
    )
    output = result.stdout + result.stderr
    return result.returncode, output


def submit_test_job(test_path: str, run_id: str) -> aiplatform.CustomJob:
    """Submit the test suite as a Vertex AI Custom Job and return the job."""
    aiplatform.init(
        project=PROJECT_ID,
        location=REGION,
        staging_bucket=TRAINING_BUCKET,
    )

    job = aiplatform.CustomJob(
        display_name=f"f1-ml-tests-{run_id}",
        worker_pool_specs=[
            {
                "machine_spec": {
                    "machine_type": "n1-standard-4",
                },
                "replica_count": 1,
                "container_spec": {
                    "image_uri": ML_IMAGE,
                    "args": [
                        "python",
                        "ml/tests/run_tests_on_vertex.py",
                        "--run-in-container",
                        "--test-path",
                        test_path,
                        "--run-id",
                        run_id,
                    ],
                    "env": [
                        {"name": "PROJECT_ID", "value": PROJECT_ID},
                        {"name": "REGION", "value": REGION},
                        {"name": "TRAINING_BUCKET", "value": TRAINING_BUCKET},
                        {"name": "MODELS_BUCKET", "value": MODELS_BUCKET},
                    ],
                },
            }
        ],
    )

    logger.info("Submitting test job: %s", job.display_name)
    job.run(
        service_account=SERVICE_ACCOUNT,
        sync=True,
    )
    return job


def log_results_to_cloud(
    run_id: str,
    exit_code: int,
    output: str,
    test_path: str,
) -> None:
    """Write structured test results to Cloud Logging."""
    try:
        cloud_logging.Client(project=PROJECT_ID).setup_logging()
        result_log = logging.getLogger("f1.tests.results")
        result_log.info(
            json.dumps(
                {
                    "run_id": run_id,
                    "test_path": test_path,
                    "exit_code": exit_code,
                    "passed": exit_code == 0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "output_preview": output[-2000:],
                }
            )
        )
    except Exception as exc:
        logger.warning("Could not write to Cloud Logging: %s", exc)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run F1 ML tests on Vertex AI")
    p.add_argument(
        "--test-path",
        default="ml/tests/",
        help="Path to test file or directory (default: ml/tests/)",
    )
    p.add_argument(
        "--run-id",
        default=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        help="Unique run ID for logging",
    )
    p.add_argument(
        "--run-in-container",
        action="store_true",
        help="Run tests locally inside the container (set by the Vertex AI job itself)",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.run_in_container:
        logger.info(
            "Running tests in container: test_path=%s run_id=%s",
            args.test_path,
            args.run_id,
        )
        exit_code, output = run_tests_locally(args.test_path)
        log_results_to_cloud(args.run_id, exit_code, output, args.test_path)

        print(output)
        if exit_code != 0:
            logger.error(
                "Tests FAILED (exit_code=%d). Check Cloud Logging run_id=%s",
                exit_code,
                args.run_id,
            )
            sys.exit(exit_code)
        else:
            logger.info("All tests PASSED. run_id=%s", args.run_id)

    else:
        logger.info(
            "Submitting test job to Vertex AI: test_path=%s run_id=%s",
            args.test_path,
            args.run_id,
        )
        try:
            submit_test_job(args.test_path, args.run_id)
            logger.info(
                "Test job completed. Check results at:\n"
                "  https://console.cloud.google.com/vertex-ai/training/custom-jobs"
                "?project=%s",
                PROJECT_ID,
            )
        except Exception as exc:
            logger.error("Test job FAILED: %s", exc)
            sys.exit(1)


if __name__ == "__main__":
    main()
