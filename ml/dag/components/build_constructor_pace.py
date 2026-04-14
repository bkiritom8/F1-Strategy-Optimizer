"""
KFP component: build_constructor_pace
Fits a mixed-effects model (1996–2026) to isolate constructor car pace from
driver skill, writes constructor_pace.json to GCS.
Runs in parallel with train_strategy and train_pit_stop after feature_engineering.
"""

from kfp import dsl
from kfp.dsl import Input, Output, Dataset

ML_IMAGE = "us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest"


@dsl.component(
    base_image=ML_IMAGE,
    packages_to_install=[],
)
def build_constructor_pace_op(
    project_id: str,
    data_bucket: str,
    run_id: str,
    feature_manifest: Input[Dataset],
    constructor_pace_artifact: Output[Dataset],
) -> None:
    """
    Fits a statsmodels MixedLM across three data tiers:
      - Tier 1 (2018–2026): FastF1 qualifying lap times
      - Tier 2 (2003–2017): Ergast qualifying times
      - Tier 3 (1996–2002): Ergast race finish times
    Driver skill is absorbed by the random effect; constructor fixed-effect
    coefficients become the per-season car pace delta (seconds/lap vs field median).
    Writes constructor_pace.json to gs://<data_bucket>/processed/constructor_pace.json.
    """
    import json
    import logging
    from datetime import datetime, timezone

    from google.cloud import logging as cloud_logging, pubsub_v1
    from pipeline.scripts.build_constructor_pace import main as build_constructor_pace

    cloud_logging.Client(project=project_id).setup_logging()
    logger = logging.getLogger("f1.pipeline.build_constructor_pace")

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, "f1-predictions-dev")

    def publish(event: str, status: str, detail: str = "") -> None:
        payload = json.dumps(
            {
                "event": event,
                "component": "build_constructor_pace",
                "status": status,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ).encode()
        publisher.publish(topic_path, data=payload)

    output_uri = f"gs://{data_bucket}/processed/constructor_pace.json"

    publish("component_start", "running")
    logger.info("build_constructor_pace: starting, output=%s", output_uri)

    result = build_constructor_pace(
        data_bucket=data_bucket,
        gcs_output=output_uri,
        local_output=None,
    )

    n_constructors = len(result.get("constructors", {}))
    logger.info(
        "build_constructor_pace: wrote %d constructors to %s",
        n_constructors,
        output_uri,
    )

    meta = {
        "artifact_uri": output_uri,
        "n_constructors": n_constructors,
        "version": result.get("version"),
        "run_id": run_id,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }

    constructor_pace_artifact.metadata.update(meta)
    with open(constructor_pace_artifact.path, "w") as f:
        json.dump(meta, f, indent=2)

    publish("component_complete", "success", f"artifact_uri={output_uri}")
    logger.info("build_constructor_pace: DONE %s", meta)
