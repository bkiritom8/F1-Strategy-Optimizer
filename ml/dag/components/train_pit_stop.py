"""
KFP component: train_pit_stop_model
Launches a Vertex AI CustomJob to train the pit stop optimizer
using single-node multi-GPU distribution (4 x T4).
"""

from kfp import dsl
from kfp.dsl import Input, Output, Dataset, Model

ML_IMAGE = "us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest"


@dsl.component(
    base_image=ML_IMAGE,
    packages_to_install=[],
)
def train_pit_stop_op(
    project_id: str,
    region: str,
    training_bucket: str,
    models_bucket: str,
    run_id: str,
    feature_manifest: Input[Dataset],
    pit_stop_model: Output[Model],
) -> None:
    """
    Submits a Vertex AI CustomJob to train the LSTM pit stop optimizer.
    Cluster: SINGLE_NODE_MULTI_GPU (n1-standard-16, 4 x T4, MirroredStrategy).
    Waits for job completion, then writes model artifact URI to pit_stop_model.
    """
    import json
    import logging
    from datetime import datetime, timezone

    from google.cloud import aiplatform, logging as cloud_logging, pubsub_v1

    from ml.distributed.cluster_config import SINGLE_NODE_MULTI_GPU

    cloud_logging.Client(project=project_id).setup_logging()
    logger = logging.getLogger("f1.pipeline.train_pit_stop")

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, "f1-predictions-dev")

    def publish(event: str, status: str, detail: str = "") -> None:
        payload = json.dumps(
            {
                "event": event,
                "component": "train_pit_stop",
                "status": status,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ).encode()
        publisher.publish(topic_path, data=payload)

    with open(feature_manifest.path) as f:
        features = json.load(f)

    publish("component_start", "running")
    logger.info("train_pit_stop: submitting CustomJob, run_id=%s", run_id)

    aiplatform.init(project=project_id, location=region, staging_bucket=training_bucket)

    checkpoint_uri = f"{training_bucket.rstrip('/')}/checkpoints/{run_id}/pit_stop/"

    job = aiplatform.CustomJob(
        display_name=f"f1-pit-stop-train-{run_id}",
        worker_pool_specs=SINGLE_NODE_MULTI_GPU.worker_pool_specs(
            args=[
                "python",
                "-m",
                "ml.models.pit_stop_optimizer",
                "--mode",
                "train",
                "--feature-uri",
                features["feature_uris"]["laps_features"],
                "--checkpoint-uri",
                checkpoint_uri,
                "--run-id",
                run_id,
            ],
            env_vars={
                "PROJECT_ID": project_id,
                "REGION": region,
                "TRAINING_BUCKET": training_bucket,
                "MODELS_BUCKET": models_bucket,
                "TF_FORCE_GPU_ALLOW_GROWTH": "true",
            },
        ),
    )

    job.run(
        service_account=f"f1-training-dev@{project_id}.iam.gserviceaccount.com",
        restart_job_on_worker_restart=False,
        sync=True,
    )

    logger.info("train_pit_stop: CustomJob finished, job_name=%s", job.display_name)

    model_meta = {
        "model_name": "pit_stop_optimizer",
        "run_id": run_id,
        "checkpoint_uri": checkpoint_uri,
        "cluster_config": SINGLE_NODE_MULTI_GPU.name,
        "feature_uri": features["feature_uris"]["laps_features"],
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "job_name": job.display_name,
    }

    pit_stop_model.metadata.update(model_meta)
    with open(pit_stop_model.path, "w") as f:
        json.dump(model_meta, f, indent=2)

    publish("component_complete", "success", f"checkpoint_uri={checkpoint_uri}")
    logger.info("train_pit_stop: DONE %s", model_meta)
