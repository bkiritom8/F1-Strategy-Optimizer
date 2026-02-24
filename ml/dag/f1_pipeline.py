"""
F1 Strategy Pipeline — Vertex AI Pipelines (KFP v2)

DAG:
    validate_data
        └── feature_engineering
                ├── train_strategy  (parallel)
                └── train_pit_stop  (parallel)
                        ├── evaluate (strategy)  (parallel)
                        └── evaluate (pit_stop)  (parallel)
                                └── deploy

Compile:
    python ml/dag/pipeline_runner.py --compile-only

Submit:
    python ml/dag/pipeline_runner.py
"""

from __future__ import annotations

import os

from kfp import dsl

from ml.dag.components import (
    validate_data_op,
    feature_engineering_op,
    train_strategy_op,
    train_pit_stop_op,
    evaluate_op,
    deploy_op,
)

# ── Pipeline constants ────────────────────────────────────────────────────────

PROJECT_ID = os.environ.get("PROJECT_ID", "f1optimizer")
REGION = os.environ.get("REGION", "us-central1")
TRAINING_BUCKET = os.environ.get("TRAINING_BUCKET", "gs://f1optimizer-training")
MODELS_BUCKET = os.environ.get("MODELS_BUCKET", "gs://f1optimizer-models")
PIPELINE_ROOT = f"{MODELS_BUCKET}/pipeline-runs/"
EXPERIMENT_NAME = "f1-strategy-training"
CLOUD_RUN_SERVICE = "f1-strategy-api-dev"
MIN_RACES = 500


# ── Pipeline definition ───────────────────────────────────────────────────────


@dsl.pipeline(
    name="f1-strategy-pipeline",
    description="End-to-end F1 race strategy training pipeline: "
    "validate → features → train (parallel) → eval (parallel) → deploy",
    pipeline_root=PIPELINE_ROOT,
)
def f1_strategy_pipeline(
    project_id: str = PROJECT_ID,
    region: str = REGION,
    training_bucket: str = TRAINING_BUCKET,
    models_bucket: str = MODELS_BUCKET,
    instance_connection_name: str = "f1optimizer:us-central1:f1-optimizer-dev",
    db_name: str = "f1_strategy",
    min_races: int = MIN_RACES,
    run_id: str = "{{$.pipeline_run_id}}",
    experiment_name: str = EXPERIMENT_NAME,
    cloud_run_service: str = CLOUD_RUN_SERVICE,
) -> None:

    # ── Step 1: Data validation ───────────────────────────────────────────────
    validate = (
        validate_data_op(
            project_id=project_id,
            instance_connection_name=instance_connection_name,
            db_name=db_name,
            min_races=min_races,
        )
        .set_display_name("Validate Data")
        .set_retry(num_retries=2, backoff_duration="60s")
    )

    # ── Step 2: Feature engineering ───────────────────────────────────────────
    features = (
        feature_engineering_op(
            project_id=project_id,
            instance_connection_name=instance_connection_name,
            db_name=db_name,
            training_bucket=training_bucket,
            validated_manifest=validate.outputs["validated_manifest"],
        )
        .after(validate)
        .set_display_name("Feature Engineering")
        .set_retry(num_retries=2, backoff_duration="60s")
    )

    # ── Step 3a: Train strategy model (parallel with 3b) ─────────────────────
    train_strategy = (
        train_strategy_op(
            project_id=project_id,
            region=region,
            training_bucket=training_bucket,
            models_bucket=models_bucket,
            run_id=run_id,
            feature_manifest=features.outputs["feature_manifest"],
        )
        .after(features)
        .set_display_name("Train Strategy Model")
        .set_retry(num_retries=2, backoff_duration="120s")
        .set_cpu_limit("4")
        .set_memory_limit("16G")
    )

    # ── Step 3b: Train pit stop model (parallel with 3a) ─────────────────────
    train_pit = (
        train_pit_stop_op(
            project_id=project_id,
            region=region,
            training_bucket=training_bucket,
            models_bucket=models_bucket,
            run_id=run_id,
            feature_manifest=features.outputs["feature_manifest"],
        )
        .after(features)
        .set_display_name("Train Pit Stop Model")
        .set_retry(num_retries=2, backoff_duration="120s")
        .set_cpu_limit("4")
        .set_memory_limit("16G")
    )

    # ── Step 4a: Evaluate strategy model (parallel with 4b) ──────────────────
    eval_strategy = (
        evaluate_op(
            project_id=project_id,
            region=region,
            training_bucket=training_bucket,
            experiment_name=experiment_name,
            model_artifact=train_strategy.outputs["strategy_model"],
            feature_manifest=features.outputs["feature_manifest"],
        )
        .after(train_strategy)
        .set_display_name("Evaluate Strategy Model")
        .set_retry(num_retries=2, backoff_duration="60s")
    )

    # ── Step 4b: Evaluate pit stop model (parallel with 4a) ──────────────────
    eval_pit = (
        evaluate_op(
            project_id=project_id,
            region=region,
            training_bucket=training_bucket,
            experiment_name=experiment_name,
            model_artifact=train_pit.outputs["pit_stop_model"],
            feature_manifest=features.outputs["feature_manifest"],
        )
        .after(train_pit)
        .set_display_name("Evaluate Pit Stop Model")
        .set_retry(num_retries=2, backoff_duration="60s")
    )

    # ── Step 5: Deploy (after both evaluations) ───────────────────────────────
    deploy_op(
        project_id=project_id,
        region=region,
        models_bucket=models_bucket,
        cloud_run_service=cloud_run_service,
        strategy_eval_report=eval_strategy.outputs["eval_report"],
        pit_stop_eval_report=eval_pit.outputs["eval_report"],
    ).after(eval_strategy, eval_pit).set_display_name("Deploy Models").set_retry(
        num_retries=2, backoff_duration="60s"
    )
