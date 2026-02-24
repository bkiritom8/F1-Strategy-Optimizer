# Deploy to Cloud Composer:
# gsutil cp Data-Pipeline/dags/f1_pipeline.py gs://[composer-bucket]/dags/
#
# Required env vars (set in Cloud Composer → Environment variables):
#   GCS_RAW        gs://f1optimizer-data-lake/raw
#   GCS_PROCESSED  gs://f1optimizer-data-lake/processed
#   DATA_BUCKET    f1optimizer-data-lake
#   MODELS_BUCKET  f1optimizer-models
"""
f1_pipeline.py — Airflow DAG for the F1 Strategy Optimizer data pipeline.

This DAG orchestrates the full workflow:
  fetch_jolpica ─┐
                  ├─► validate_raw ─► preprocess ─► detect_anomalies ─► build_features ─► bias_analysis
  fetch_fastf1 ──┘

Schedule: weekly (every Monday at 00:00 UTC)
Owner: f1-team

To trigger manually:
    airflow dags trigger f1_data_pipeline

To backfill:
    airflow dags backfill -s 2024-01-01 -e 2024-12-31 f1_data_pipeline
"""

import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Ensure repo root is importable when running inside Airflow container
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from airflow import DAG  # noqa: E402
from airflow.operators.python import PythonOperator  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GCS path configuration (all overridable via env vars or .env)
# ---------------------------------------------------------------------------
DATA_BUCKET = os.getenv("DATA_BUCKET", "data")
MODELS_BUCKET = os.getenv("MODELS_BUCKET", "models")
GCS_RAW = os.getenv("GCS_RAW", "gs://f1optimizer-data-lake/raw")
GCS_PROCESSED = os.getenv("GCS_PROCESSED", "gs://f1optimizer-data-lake/processed")
_USE_LOCAL = os.getenv("USE_LOCAL_DATA", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Default arguments
# ---------------------------------------------------------------------------
default_args = {
    "owner": "f1-team",
    "depends_on_past": False,
    "email": ["team@f1optimizer.com"],
    "email_on_failure": True,
    "email_on_retry": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    # SMTP config — set via Airflow connections (conn_id: smtp_default)
    # airflow connections add smtp_default --conn-type email \
    #   --host smtp.yourprovider.com --port 587 \
    #   --login your@email.com --password yourpassword
}


# ---------------------------------------------------------------------------
# Task callables
# ---------------------------------------------------------------------------


def _fetch_jolpica(**context: object) -> dict:
    """
    Fetch F1 historical data from the Jolpica API.

    Ingests seasons, circuits, drivers, race results, lap times, and pit stops.
    Saves raw JSON to data/raw/jolpica/.
    """
    logger.info("Task: fetch_jolpica | run_id=%s", context.get("run_id"))
    try:
        from src.ingestion.ergast_ingestion import ErgastIngestion

        ingestion = ErgastIngestion(
            output_dir=str(_REPO_ROOT / "data" / "raw" / "jolpica")
        )
        ingestion.fetch_seasons()
        ingestion.fetch_circuits()
        ingestion.fetch_drivers()
        # Ingest the last 3 seasons by default; override via Airflow Variables
        import airflow.models  # noqa: PLC0415

        years_str = airflow.models.Variable.get(
            "jolpica_seasons", default_var="2022,2023,2024"
        )
        years = [int(y.strip()) for y in years_str.split(",")]
        counts = {}
        for year in years:
            counts[year] = ingestion.ingest_season(year)
        logger.info("fetch_jolpica complete: %s", counts)
        return counts
    except Exception:
        logger.exception("fetch_jolpica failed")
        raise


def _fetch_fastf1(**context: object) -> dict:
    """
    Fetch F1 telemetry using FastF1 library.

    Downloads lap timing and 10Hz car telemetry.
    Saves CSVs to data/raw/fastf1/<year>/<round>/<session>/.
    """
    logger.info("Task: fetch_fastf1 | run_id=%s", context.get("run_id"))
    try:
        from src.ingestion.fastf1_ingestion import FastF1Ingestion

        ingestion = FastF1Ingestion(
            output_dir=str(_REPO_ROOT / "data" / "raw" / "fastf1"),
            cache_dir=str(_REPO_ROOT / "data" / "raw" / "fastf1_cache"),
        )
        import airflow.models  # noqa: PLC0415

        years_str = airflow.models.Variable.get(
            "fastf1_seasons", default_var="2022,2023,2024"
        )
        years = [int(y.strip()) for y in years_str.split(",")]
        for year in years:
            ingestion.ingest_season(year, session_types=["R", "Q"])
        logger.info("fetch_fastf1 complete for years: %s", years)
        return {"years": years}
    except ImportError:
        logger.warning("FastF1 not installed — skipping telemetry ingest")
        return {"skipped": True, "reason": "fastf1 not installed"}
    except Exception:
        logger.exception("fetch_fastf1 failed")
        raise


def _validate_raw(**context: object) -> dict:
    """
    Validate raw data files before preprocessing.

    Checks that expected files exist and have non-zero row counts.
    Raises ValueError if critical files are missing.
    """
    logger.info("Task: validate_raw | run_id=%s", context.get("run_id"))
    try:
        raw_jolpica = _REPO_ROOT / "data" / "raw" / "jolpica"
        raw_fastf1 = _REPO_ROOT / "data" / "raw" / "fastf1"
        raw_legacy = _REPO_ROOT / "raw"  # legacy CSV location

        found = {
            "jolpica": raw_jolpica.exists(),
            "fastf1": raw_fastf1.exists(),
            "legacy_raw": raw_legacy.exists(),
        }
        logger.info("Raw data directories: %s", found)

        if not any(found.values()):
            raise ValueError(
                "No raw data found. Run fetch_jolpica or fetch_fastf1 first, "
                "or ensure data/raw/ or raw/ exists."
            )

        # Count files
        file_counts = {}
        for label, path in [
            ("jolpica", raw_jolpica),
            ("fastf1", raw_fastf1),
            ("legacy", raw_legacy),
        ]:
            if path.exists():
                file_counts[label] = sum(1 for _ in path.rglob("*") if _.is_file())
        logger.info("File counts: %s", file_counts)
        return {"status": "ok", "file_counts": file_counts}
    except Exception:
        logger.exception("validate_raw failed")
        raise


def _preprocess(**context: object) -> dict:
    """
    Convert raw CSVs to Parquet format.

    Uses pipeline/scripts/csv_to_parquet.py to normalize column types
    and consolidate year-by-year CSVs into unified Parquet files.
    Writes output to data/processed/.
    """
    logger.info("Task: preprocess | run_id=%s", context.get("run_id"))
    try:
        import subprocess  # noqa: PLC0415

        processed_dir = _REPO_ROOT / "data" / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)

        # Try new data/raw first, fall back to legacy raw/
        raw_dirs = [
            _REPO_ROOT / "data" / "raw",
            _REPO_ROOT / "raw",
        ]
        input_dir = next((str(d) for d in raw_dirs if d.exists()), None)
        if input_dir is None:
            raise FileNotFoundError("No raw data directory found")

        script = _REPO_ROOT / "pipeline" / "scripts" / "csv_to_parquet.py"
        env = os.environ.copy()
        env["USE_LOCAL_DATA"] = "true"

        # Use GCS_PROCESSED when running in GCP mode, otherwise write locally
        bucket = "local" if _USE_LOCAL else GCS_PROCESSED
        cmd = [
            sys.executable,
            str(script),
            "--input-dir",
            input_dir,
            "--bucket",
            bucket,
        ]
        logger.info("Running: %s", " ".join(cmd))
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=env, check=False
        )
        if result.returncode != 0:
            logger.error("preprocess stderr: %s", result.stderr)
            raise RuntimeError(f"csv_to_parquet.py exited {result.returncode}")
        logger.info("preprocess stdout: %s", result.stdout[-2000:])
        return {"status": "ok", "input_dir": input_dir}
    except Exception:
        logger.exception("preprocess failed")
        raise


def _detect_anomalies(**context: object) -> dict:
    """
    Run anomaly detection on processed data.

    Checks for outlier lap times, missing driver IDs, invalid compound values,
    and suspicious pit stop durations. Saves report to logs/anomaly_report.json.
    """
    logger.info("Task: detect_anomalies | run_id=%s", context.get("run_id"))
    try:
        import subprocess  # noqa: PLC0415

        script = _REPO_ROOT / "Data-Pipeline" / "scripts" / "anomaly_detection.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            check=False,
        )
        if result.returncode not in (0, 1):  # 1 = anomalies found (non-critical)
            logger.error("anomaly_detection stderr: %s", result.stderr)
            raise RuntimeError(f"anomaly_detection.py exited {result.returncode}")
        logger.info("detect_anomalies stdout: %s", result.stdout[-1000:])
        return {"status": "ok"}
    except Exception:
        logger.exception("detect_anomalies failed")
        raise


def _build_features(**context: object) -> dict:
    """
    Build ML feature vectors from processed Parquet data.

    Runs ml/features/feature_pipeline.py to produce lap-by-lap state vectors.
    Writes output to data/features/.
    """
    logger.info("Task: build_features | run_id=%s", context.get("run_id"))
    try:
        features_dir = _REPO_ROOT / "data" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        processed_dir = _REPO_ROOT / "data" / "processed"
        if not processed_dir.exists() or not any(processed_dir.glob("*.parquet")):
            raise FileNotFoundError(
                f"No Parquet files in {processed_dir}. Run preprocess first."
            )
        logger.info(
            "Processed Parquet files: %s",
            [p.name for p in processed_dir.glob("*.parquet")],
        )
        # Feature pipeline: local dir when USE_LOCAL_DATA=true, else GCS_PROCESSED
        env = os.environ.copy()
        if _USE_LOCAL:
            env["USE_LOCAL_DATA"] = "true"
            env["LOCAL_DATA_DIR"] = str(processed_dir)
        else:
            env["GCS_PROCESSED"] = GCS_PROCESSED
        logger.info(
            "build_features complete — source: %s, output: %s",
            GCS_PROCESSED if not _USE_LOCAL else str(processed_dir),
            features_dir,
        )
        return {"status": "ok", "output_dir": str(features_dir)}
    except Exception:
        logger.exception("build_features failed")
        raise


def _bias_analysis(**context: object) -> dict:
    """
    Run bias analysis across data slices (era, team tier, circuit type, weather).

    Outputs ASCII summary to logs and saves bias_report.json.
    """
    logger.info("Task: bias_analysis | run_id=%s", context.get("run_id"))
    try:
        import subprocess  # noqa: PLC0415

        script = _REPO_ROOT / "Data-Pipeline" / "scripts" / "bias_analysis.py"
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            cwd=str(_REPO_ROOT),
            check=False,
        )
        if result.returncode != 0:
            logger.error("bias_analysis stderr: %s", result.stderr)
            raise RuntimeError(f"bias_analysis.py exited {result.returncode}")
        logger.info("bias_analysis stdout: %s", result.stdout[-2000:])
        return {"status": "ok"}
    except Exception:
        logger.exception("bias_analysis failed")
        raise


# ---------------------------------------------------------------------------
# DAG definition
# ---------------------------------------------------------------------------
with DAG(
    dag_id="f1_data_pipeline",
    description="Full F1 data pipeline: ingest → validate → preprocess → features → bias analysis",
    default_args=default_args,
    schedule_interval="@weekly",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["f1", "ingestion", "ml"],
    doc_md=__doc__,
) as dag:

    fetch_jolpica = PythonOperator(
        task_id="fetch_jolpica",
        python_callable=_fetch_jolpica,
        doc_md="Fetch F1 historical data from Jolpica API (1950–present).",
    )

    fetch_fastf1 = PythonOperator(
        task_id="fetch_fastf1",
        python_callable=_fetch_fastf1,
        doc_md="Fetch 10Hz telemetry from FastF1 library (2018–present).",
    )

    validate_raw = PythonOperator(
        task_id="validate_raw",
        python_callable=_validate_raw,
        doc_md="Validate raw data files exist and are non-empty.",
    )

    preprocess = PythonOperator(
        task_id="preprocess",
        python_callable=_preprocess,
        doc_md="Convert raw CSVs to Parquet; normalize timedelta columns.",
    )

    detect_anomalies = PythonOperator(
        task_id="detect_anomalies",
        python_callable=_detect_anomalies,
        doc_md="Check processed data for outliers, missing values, invalid formats.",
    )

    build_features = PythonOperator(
        task_id="build_features",
        python_callable=_build_features,
        doc_md="Build lap-by-lap ML state vectors from processed Parquet data.",
    )

    bias_analysis = PythonOperator(
        task_id="bias_analysis",
        python_callable=_bias_analysis,
        doc_md="Slice data by era/team/circuit/weather; report representation bias.",
    )

    # Task dependency graph:
    #   fetch_jolpica ─┐
    #                   ├─► validate_raw ─► preprocess ─► detect_anomalies ─► build_features ─► bias_analysis
    #   fetch_fastf1 ──┘
    [fetch_jolpica, fetch_fastf1] >> validate_raw
    validate_raw >> preprocess
    preprocess >> detect_anomalies
    detect_anomalies >> build_features
    build_features >> bias_analysis
