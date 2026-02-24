"""
Pipeline runner — compiles and submits the F1 strategy pipeline to Vertex AI.

Usage:
    # Compile only (produces pipeline JSON, no submission)
    python ml/dag/pipeline_runner.py --compile-only

    # Submit to Vertex AI Pipelines
    python ml/dag/pipeline_runner.py

    # Submit with a custom run ID
    python ml/dag/pipeline_runner.py --run-id 20260218-manual

The compiled pipeline JSON is saved to:
    gs://f1optimizer-models/pipelines/f1_strategy_pipeline.json

Can also be triggered via:
    gcloud run jobs execute f1-pipeline-trigger --region=us-central1 --project=f1optimizer
"""

from __future__ import annotations

import argparse
import logging
import os
import tempfile
from datetime import datetime, timezone

from google.cloud import aiplatform, storage
from kfp import compiler

from ml.dag.f1_pipeline import f1_strategy_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("f1.pipeline.runner")

# ── Config ────────────────────────────────────────────────────────────────────

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
REGION = os.environ.get("REGION", "us-central1")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "gs://f1optimizer-models")
PIPELINE_JSON_GCS = f"{MODELS_BUCKET}/pipelines/f1_strategy_pipeline.json"
SERVICE_ACCOUNT = f"f1-training-dev@{PROJECT_ID}.iam.gserviceaccount.com"


def compile_pipeline(output_path: str) -> None:
    """Compile the KFP pipeline to a JSON file."""
    logger.info("Compiling pipeline to %s", output_path)
    compiler.Compiler().compile(
        pipeline_func=f1_strategy_pipeline,
        package_path=output_path,
    )
    logger.info("Pipeline compiled OK")


def upload_pipeline_json(local_path: str) -> str:
    """Upload compiled JSON to GCS. Returns GCS URI."""
    bucket_name, blob_path = PIPELINE_JSON_GCS.lstrip("gs://").split("/", 1)
    client = storage.Client(project=PROJECT_ID)
    blob = client.bucket(bucket_name).blob(blob_path)
    blob.upload_from_filename(local_path, content_type="application/json")
    logger.info("Pipeline JSON uploaded to %s", PIPELINE_JSON_GCS)
    return PIPELINE_JSON_GCS


def submit_pipeline(
    compiled_path: str,
    run_id: str,
    enable_caching: bool = True,
) -> aiplatform.PipelineJob:
    """Submit pipeline to Vertex AI Pipelines and return the job object."""
    aiplatform.init(
        project=PROJECT_ID,
        location=REGION,
        staging_bucket="gs://f1optimizer-training",
    )

    job = aiplatform.PipelineJob(
        display_name=f"f1-strategy-pipeline-{run_id}",
        template_path=compiled_path,
        pipeline_root=f"{MODELS_BUCKET}/pipeline-runs/{run_id}/",
        parameter_values={
            "project_id": PROJECT_ID,
            "region": REGION,
            "run_id": run_id,
        },
        enable_caching=enable_caching,
    )

    logger.info("Submitting pipeline job %s", job.display_name)
    job.submit(service_account=SERVICE_ACCOUNT)
    logger.info(
        "Pipeline job submitted. Monitor at:\n"
        "  https://console.cloud.google.com/vertex-ai/pipelines/runs"
        "?project=%s",
        PROJECT_ID,
    )
    return job


def monitor_pipeline(job: aiplatform.PipelineJob) -> str:
    """Block until the pipeline finishes. Returns final state string."""
    logger.info("Monitoring pipeline job (this will block until completion)...")
    job.wait()
    state = job.state.name
    logger.info("Pipeline finished with state: %s", state)
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="F1 Strategy Pipeline Runner")
    parser.add_argument(
        "--compile-only",
        action="store_true",
        help="Compile pipeline to JSON and upload to GCS, but do not submit.",
    )
    parser.add_argument(
        "--run-id",
        default=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        help="Unique run identifier (default: current UTC timestamp).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable Vertex AI Pipelines caching.",
    )
    parser.add_argument(
        "--no-monitor",
        action="store_true",
        help="Submit pipeline but do not wait for completion.",
    )
    args = parser.parse_args()

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        local_json = tmp.name

    try:
        compile_pipeline(local_json)
        gcs_uri = upload_pipeline_json(local_json)
        logger.info("Compiled pipeline available at: %s", gcs_uri)

        if args.compile_only:
            logger.info("--compile-only: skipping submission.")
            return

        job = submit_pipeline(
            compiled_path=local_json,
            run_id=args.run_id,
            enable_caching=not args.no_cache,
        )

        if not args.no_monitor:
            final_state = monitor_pipeline(job)
            if final_state != "PIPELINE_STATE_SUCCEEDED":
                raise SystemExit(
                    f"Pipeline ended in state {final_state}. "
                    f"Check logs at https://console.cloud.google.com/vertex-ai/pipelines"
                    f"/runs?project={PROJECT_ID}"
                )
    finally:
        os.unlink(local_json)


if __name__ == "__main__":
    main()
