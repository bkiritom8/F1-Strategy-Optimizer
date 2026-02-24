"""
KFP component: deploy
Promotes the best models to gs://f1optimizer-models/*/latest/
and triggers a Cloud Run revision update for the serving API.
"""

from kfp import dsl
from kfp.dsl import Input, Dataset

ML_IMAGE = "us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest"


@dsl.component(
    base_image=ML_IMAGE,
    packages_to_install=[],
)
def deploy_op(
    project_id: str,
    region: str,
    models_bucket: str,
    cloud_run_service: str,
    strategy_eval_report: Input[Dataset],
    pit_stop_eval_report: Input[Dataset],
) -> None:
    """
    1. Reads eval reports for both models.
    2. Uses Aggregator to promote each model checkpoint to GCS latest/.
    3. Updates the Cloud Run service env var MODEL_VERSION to trigger
       a new revision that picks up the promoted models.
    4. Publishes deployment event to f1-predictions-dev.
    """
    import json
    import logging
    import subprocess
    from datetime import datetime, timezone

    from google.cloud import logging as cloud_logging, pubsub_v1

    from ml.distributed.aggregator import Aggregator

    cloud_logging.Client(project=project_id).setup_logging()
    logger = logging.getLogger("f1.pipeline.deploy")

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, "f1-predictions-dev")

    def publish(event: str, status: str, detail: str = "") -> None:
        payload = json.dumps(
            {
                "event": event,
                "component": "deploy",
                "status": status,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ).encode()
        publisher.publish(topic_path, data=payload)

    publish("component_start", "running")

    with open(strategy_eval_report.path) as f:
        strategy_report = json.load(f)
    with open(pit_stop_eval_report.path) as f:
        pit_report = json.load(f)

    run_id = strategy_report["run_id"]
    deployed_uris: dict[str, str] = {}

    for report in (strategy_report, pit_report):
        model_name = report["model_name"]
        logger.info("deploy: promoting %s (run_id=%s)", model_name, run_id)

        agg = Aggregator(model_name=model_name, run_id=run_id)
        # Aggregator.list_checkpoints reads from training bucket shards.
        # We pass the checkpoint_uri directly via a synthetic checkpoint.
        from ml.distributed.aggregator import CheckpointMeta

        best = CheckpointMeta(
            gcs_uri=report["checkpoint_uri"],
            worker_index=0,
            val_loss=report["metrics"].get("val_loss", 0.0),
            epoch=0,
            metrics=report["metrics"],
        )
        model_uri = agg.save_final_model(best)
        agg.publish_completion(best, model_uri=model_uri)
        deployed_uris[model_name] = model_uri
        logger.info("deploy: %s promoted to %s", model_name, model_uri)

    # ── Update Cloud Run to pick up new model versions ────────────────────────
    cmd = [
        "gcloud",
        "run",
        "services",
        "update",
        cloud_run_service,
        "--region",
        region,
        "--project",
        project_id,
        "--update-env-vars",
        f"MODEL_VERSION={run_id}",
        "--quiet",
    ]
    logger.info("deploy: updating Cloud Run service %s", cloud_run_service)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("deploy: Cloud Run update returned non-zero: %s", result.stderr)
    else:
        logger.info("deploy: Cloud Run updated OK")

    publish(
        "component_complete",
        "success",
        f"deployed={list(deployed_uris.keys())} run_id={run_id}",
    )
    logger.info("deploy: DONE %s", deployed_uris)
