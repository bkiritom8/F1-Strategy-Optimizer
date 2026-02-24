"""
KFP component: train_strategy_model
Launches a Vertex AI CustomJob to train the strategy predictor
using multi-node data-parallel distribution.
"""

from kfp import dsl
from kfp.dsl import Input, Output, Dataset, Model

ML_IMAGE = "us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest"


@dsl.component(
    base_image=ML_IMAGE,
    packages_to_install=[],
)
def train_strategy_op(
    project_id: str,
    region: str,
    training_bucket: str,
    models_bucket: str,
    run_id: str,
    feature_manifest: Input[Dataset],
    strategy_model: Output[Model],
) -> None:
    """
    Submits a Vertex AI CustomJob to train the XGBoost+LightGBM strategy predictor.
    Cluster: MULTI_NODE_DATA_PARALLEL (4 x n1-standard-8, 1 T4 each).
    Waits for job completion, then writes model artifact URI to strategy_model.
    """
    import json
    import logging
    from datetime import datetime, timezone

    from google.cloud import aiplatform, logging as cloud_logging, pubsub_v1

    from ml.distributed.cluster_config import MULTI_NODE_DATA_PARALLEL

    cloud_logging.Client(project=project_id).setup_logging()
    logger = logging.getLogger("f1.pipeline.train_strategy")

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, "f1-predictions-dev")

    def publish(event: str, status: str, detail: str = "") -> None:
        payload = json.dumps(
            {
                "event": event,
                "component": "train_strategy",
                "status": status,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ).encode()
        publisher.publish(topic_path, data=payload)

    with open(feature_manifest.path) as f:
        features = json.load(f)

    publish("component_start", "running")
    logger.info("train_strategy: submitting CustomJob, run_id=%s", run_id)

    aiplatform.init(project=project_id, location=region, staging_bucket=training_bucket)

    checkpoint_uri = f"{training_bucket.rstrip('/')}/checkpoints/{run_id}/strategy/"

    job = aiplatform.CustomJob(
        display_name=f"f1-strategy-train-{run_id}",
        worker_pool_specs=MULTI_NODE_DATA_PARALLEL.worker_pool_specs(
            args=[
                "python",
                "-m",
                "ml.models.strategy_predictor",
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
        sync=True,  # block until job finishes
    )

    logger.info("train_strategy: CustomJob finished, job_name=%s", job.display_name)

    model_meta = {
        "model_name": "strategy_predictor",
        "run_id": run_id,
        "checkpoint_uri": checkpoint_uri,
        "cluster_config": MULTI_NODE_DATA_PARALLEL.name,
        "feature_uri": features["feature_uris"]["laps_features"],
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "job_name": job.display_name,
    }

    strategy_model.metadata.update(model_meta)
    with open(strategy_model.path, "w") as f:
        json.dump(model_meta, f, indent=2)

    publish("component_complete", "success", f"checkpoint_uri={checkpoint_uri}")
    logger.info("train_strategy: DONE %s", model_meta)
