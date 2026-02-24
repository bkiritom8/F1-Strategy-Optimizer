"""
KFP component: validate_data
Checks that Cloud SQL has sufficient data before training starts.
Publishes status to f1-predictions-dev.
"""

from kfp import dsl
from kfp.dsl import Output, Dataset

ML_IMAGE = "us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest"


@dsl.component(
    base_image=ML_IMAGE,
    packages_to_install=[],
)
def validate_data_op(
    project_id: str,
    instance_connection_name: str,
    db_name: str,
    min_races: int,
    validated_manifest: Output[Dataset],
) -> None:
    """
    Connects to Cloud SQL, verifies:
      - races table has >= min_races rows
      - lap_features table is populated
      - telemetry_features table is populated
    Writes a JSON manifest to validated_manifest for downstream components.
    Publishes status to Pub/Sub f1-predictions-dev.
    """
    import json
    import logging
    import os
    from datetime import datetime, timezone

    from google.cloud import logging as cloud_logging, pubsub_v1
    from google.cloud.sql.connector import Connector

    # ── Cloud Logging ─────────────────────────────────────────────────────────
    cloud_logging.Client(project=project_id).setup_logging()
    logger = logging.getLogger("f1.pipeline.validate_data")

    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(project_id, "f1-predictions-dev")

    def publish(event: str, status: str, detail: str = "") -> None:
        import json as _json

        payload = _json.dumps(
            {
                "event": event,
                "component": "validate_data",
                "status": status,
                "detail": detail,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ).encode()
        publisher.publish(topic_path, data=payload)

    publish("component_start", "running")
    logger.info("validate_data: connecting to Cloud SQL %s", instance_connection_name)

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

    checks: dict[str, int] = {}
    try:
        conn = get_conn()
        cur = conn.cursor()
        for table in ("races", "lap_features", "telemetry_features", "drivers"):
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            checks[table] = count
            logger.info("validate_data: %s → %d rows", table, count)
        conn.close()
    finally:
        connector.close()

    races_ok = checks.get("races", 0) >= min_races
    laps_ok = checks.get("lap_features", 0) > 0
    telemetry_ok = checks.get("telemetry_features", 0) > 0

    if not (races_ok and laps_ok):
        msg = (
            f"Data validation failed: races={checks.get('races',0)} "
            f"(need {min_races}), lap_features={checks.get('lap_features',0)}"
        )
        publish("component_failed", "failed", msg)
        raise RuntimeError(msg)

    manifest = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "row_counts": checks,
        "min_races": min_races,
        "telemetry_available": telemetry_ok,
    }

    with open(validated_manifest.path, "w") as f:
        json.dump(manifest, f, indent=2)

    publish("component_complete", "success", f"races={checks['races']}")
    logger.info("validate_data: PASSED %s", manifest)
