"""
KFP component: feature_engineering
Computes derived features from raw DB tables and writes feature sets to GCS.
"""

from kfp import dsl
from kfp.dsl import Input, Output, Dataset

ML_IMAGE = "us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest"


@dsl.component(
    base_image=ML_IMAGE,
    packages_to_install=[],
)
def feature_engineering_op(
    project_id: str,
    instance_connection_name: str,
    db_name: str,
    training_bucket: str,
    validated_manifest: Input[Dataset],
    feature_manifest: Output[Dataset],
) -> None:
    """
    Derives features from raw DB tables:
      - Tire degradation curves (lap time delta vs tire age)
      - Gap evolution (gap_to_car_ahead per lap)
      - Undercut/overcut windows (position delta after pit stop)
      - Weather impact factors (lap time delta vs track condition)
    Writes Parquet feature files to GCS and outputs a manifest.
    """
    import json
    import logging
    import os
    from datetime import datetime, timezone

    import pandas as pd
    from google.cloud import logging as cloud_logging, pubsub_v1, storage
    from google.cloud.sql.connector import Connector

    cloud_logging.Client(project=project_id).setup_logging()
    logger = logging.getLogger("f1.pipeline.feature_engineering")

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, "f1-predictions-dev")

    def publish(event: str, status: str, detail: str = "") -> None:
        payload = json.dumps(
            {
                "event": event,
                "component": "feature_engineering",
                "status": status,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ).encode()
        publisher.publish(topic_path, data=payload)

    with open(validated_manifest.path) as f:
        manifest = json.load(f)

    publish("component_start", "running")
    logger.info(
        "feature_engineering: starting, telemetry_available=%s",
        manifest.get("telemetry_available"),
    )

    db_user = os.environ.get("DB_USER", "f1_app")
    db_password = os.environ.get("DB_PASSWORD", "")
    connector = Connector()

    def get_conn():
        return connector.connect(
            instance_connection_name,
            "pg8000",
            user=db_user,
            password=db_password,
            db=db_name,
        )

    # ── Load raw data ─────────────────────────────────────────────────────────
    try:
        conn = get_conn()
        laps = pd.read_sql_query(
            """
            SELECT lf.*, r.year, r.circuit_id, r.race_name
            FROM lap_features lf
            JOIN races r USING (race_id)
            ORDER BY lf.race_id, lf.driver_id, lf.lap_number
            """,
            conn,
        )
        logger.info("feature_engineering: loaded %d lap rows", len(laps))
        conn.close()
    finally:
        connector.close()

    # ── Tire degradation curves ───────────────────────────────────────────────
    laps = laps.sort_values(["race_id", "driver_id", "lap_number"])
    laps["lap_time_delta"] = laps.groupby(["race_id", "driver_id"])[
        "lap_time_ms"
    ].diff()
    deg_curve = (
        laps.groupby(["tire_compound", "tire_age_laps"])["lap_time_delta"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .rename(
            columns={
                "mean": "deg_mean_ms",
                "std": "deg_std_ms",
                "count": "sample_count",
            }
        )
    )

    # ── Gap evolution ─────────────────────────────────────────────────────────
    laps["gap_delta"] = laps.groupby(["race_id", "driver_id"])[
        "gap_to_car_ahead_ms"
    ].diff()

    # ── Undercut / overcut windows ────────────────────────────────────────────
    pit_laps = laps[laps["pit_stop_flag"] == 1].copy()
    if not pit_laps.empty:
        pit_laps["position_after"] = laps.groupby(["race_id", "driver_id"])[
            "position"
        ].shift(-2)
        pit_laps["position_gain"] = pit_laps["position"] - pit_laps["position_after"]
        undercut_windows = pit_laps[
            [
                "race_id",
                "driver_id",
                "lap_number",
                "position",
                "position_after",
                "position_gain",
            ]
        ]
    else:
        undercut_windows = pd.DataFrame(
            columns=[
                "race_id",
                "driver_id",
                "lap_number",
                "position",
                "position_after",
                "position_gain",
            ]
        )

    # ── Compound one-hot encoding ─────────────────────────────────────────────
    compound_dummies = pd.get_dummies(laps["tire_compound"], prefix="compound")
    laps = pd.concat([laps, compound_dummies], axis=1)

    # ── Write to GCS ──────────────────────────────────────────────────────────
    bucket_name = training_bucket.lstrip("gs://")
    gcs_client = storage.Client(project=project_id)
    bucket = gcs_client.bucket(bucket_name)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    base_prefix = f"features/{timestamp}"

    def upload_df(df: pd.DataFrame, name: str) -> str:
        uri = f"gs://{bucket_name}/{base_prefix}/{name}.parquet"
        bucket.blob(f"{base_prefix}/{name}.parquet").upload_from_string(
            df.to_parquet(index=False), content_type="application/octet-stream"
        )
        logger.info("feature_engineering: wrote %s (%d rows) to %s", name, len(df), uri)
        return uri

    uris = {
        "laps_features": upload_df(laps, "laps_features"),
        "deg_curves": upload_df(deg_curve, "deg_curves"),
        "undercut_windows": upload_df(undercut_windows, "undercut_windows"),
    }

    out_manifest = {
        "created_at": timestamp,
        "base_prefix": f"gs://{bucket_name}/{base_prefix}",
        "feature_uris": uris,
        "row_counts": {k: len(laps) for k in uris},
        "telemetry_available": manifest.get("telemetry_available", False),
    }

    with open(feature_manifest.path, "w") as f:
        json.dump(out_manifest, f, indent=2)

    # Write manifest to GCS too so other jobs can find it
    bucket.blob(f"{base_prefix}/manifest.json").upload_from_string(
        json.dumps(out_manifest, indent=2), content_type="application/json"
    )

    publish(
        "component_complete",
        "success",
        f"features written to gs://{bucket_name}/{base_prefix}",
    )
    logger.info("feature_engineering: DONE %s", out_manifest)
