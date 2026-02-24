"""
KFP component: evaluate
Loads a trained model checkpoint, runs evaluation on held-out data,
and writes metrics to Vertex AI Experiments.
"""

from kfp import dsl
from kfp.dsl import Input, Output, Model, Metrics, Dataset

ML_IMAGE = "us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest"


@dsl.component(
    base_image=ML_IMAGE,
    packages_to_install=[],
)
def evaluate_op(
    project_id: str,
    region: str,
    training_bucket: str,
    experiment_name: str,
    model_artifact: Input[Model],
    feature_manifest: Input[Dataset],
    eval_metrics: Output[Metrics],
    eval_report: Output[Dataset],
) -> None:
    """
    Evaluates the trained model on a held-out season (most recent season not
    used in training). Writes metrics to:
      - Vertex AI Experiments (for comparison across runs)
      - eval_metrics output artifact (for the deploy component)
      - GCS eval report JSON
    """
    import json
    import logging
    from datetime import datetime, timezone

    import pandas as pd
    from google.cloud import aiplatform, logging as cloud_logging, pubsub_v1, storage

    cloud_logging.Client(project=project_id).setup_logging()
    logger = logging.getLogger("f1.pipeline.evaluate")

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, "f1-predictions-dev")

    def publish(event: str, status: str, detail: str = "") -> None:
        payload = json.dumps(
            {
                "event": event,
                "component": "evaluate",
                "status": status,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ).encode()
        publisher.publish(topic_path, data=payload)

    with open(model_artifact.path) as f:
        model_meta = json.load(f)
    with open(feature_manifest.path) as f:
        features = json.load(f)

    model_name = model_meta["model_name"]
    run_id = model_meta["run_id"]
    checkpoint_uri = model_meta["checkpoint_uri"]

    publish("component_start", "running", f"model={model_name}")
    logger.info("evaluate: model=%s run_id=%s", model_name, run_id)

    # ── Load held-out data (most recent season) ───────────────────────────────
    feature_uri = features["feature_uris"]["laps_features"]
    df = pd.read_parquet(feature_uri)

    max_year = df["year"].max()
    eval_df = df[df["year"] == max_year].copy()
    train_df = df[df["year"] < max_year].copy()
    logger.info(
        "evaluate: eval_year=%d, eval_rows=%d, train_rows=%d",
        max_year,
        len(eval_df),
        len(train_df),
    )

    # ── Load model from GCS checkpoint and score ──────────────────────────────
    # Model-specific scoring is delegated to the model module itself.
    # We import dynamically based on model_name.
    if model_name == "strategy_predictor":
        from ml.models.strategy_predictor import StrategyPredictor

        model = StrategyPredictor()
    elif model_name == "pit_stop_optimizer":
        from ml.models.pit_stop_optimizer import PitStopOptimizer

        model = PitStopOptimizer()  # type: ignore[assignment]
    else:
        raise ValueError(f"Unknown model_name: {model_name}")

    model.load(checkpoint_uri)
    metrics = model.evaluate(eval_df)

    # ── Log to Vertex AI Experiments ──────────────────────────────────────────
    aiplatform.init(project=project_id, location=region, experiment=experiment_name)

    with aiplatform.start_run(run=f"{model_name}-{run_id}"):
        aiplatform.log_params(
            {
                "model_name": model_name,
                "run_id": run_id,
                "eval_year": int(max_year),
                "cluster_config": model_meta.get("cluster_config", "unknown"),
            }
        )
        aiplatform.log_metrics(metrics)

    # ── Write outputs ─────────────────────────────────────────────────────────
    for k, v in metrics.items():
        eval_metrics.log_metric(k, float(v))

    report = {
        "model_name": model_name,
        "run_id": run_id,
        "eval_year": int(max_year),
        "eval_rows": len(eval_df),
        "metrics": metrics,
        "checkpoint_uri": checkpoint_uri,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }

    with open(eval_report.path, "w") as f:
        json.dump(report, f, indent=2)

    # Mirror report to GCS
    bucket_name = training_bucket.lstrip("gs://")
    gcs_client = storage.Client(project=project_id)
    gcs_client.bucket(bucket_name).blob(
        f"eval_reports/{run_id}/{model_name}.json"
    ).upload_from_string(json.dumps(report, indent=2), content_type="application/json")

    publish("component_complete", "success", f"model={model_name} metrics={metrics}")
    logger.info("evaluate: DONE %s", report)
