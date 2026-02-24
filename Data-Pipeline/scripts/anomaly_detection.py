"""
anomaly_detection.py — Detect data anomalies in processed F1 Parquet files.

Checks:
  - Lap times > 3 std deviations from circuit mean → WARNING
  - Missing Driver IDs → ERROR
  - Invalid Compound values → WARNING
  - Pit stop duration < 1.5s or > 60s → WARNING
  - Sessions with 0 telemetry rows → WARNING

Sends Slack alert if SLACK_WEBHOOK_URL env var is set.

Saves full report to Data-Pipeline/logs/anomaly_report.json.

Exit codes:
  0 — no anomalies
  1 — anomalies found (non-critical)
  2 — critical errors found

Usage:
    python Data-Pipeline/scripts/anomaly_detection.py
    python Data-Pipeline/scripts/anomaly_detection.py --data-dir data/processed
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("anomaly_detection")

_SCRIPT_DIR = Path(__file__).parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]
_LOGS_DIR = _SCRIPT_DIR.parent / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Local fallback: Data-Pipeline/data/ when USE_LOCAL_DATA=true
_USE_LOCAL = os.getenv("USE_LOCAL_DATA", "false").lower() == "true"
_LOCAL_DATA_DIR = _SCRIPT_DIR.parent / "data"

VALID_COMPOUNDS = {"SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET", "UNKNOWN"}
LAP_TIME_Z_THRESHOLD = 3.0
PIT_STOP_MIN_S = 1.5
PIT_STOP_MAX_S = 60.0


# ---------------------------------------------------------------------------
# Anomaly entry builders
# ---------------------------------------------------------------------------


def _anomaly(
    severity: str,
    dataset: str,
    check: str,
    count: int,
    detail: str,
    sample: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    return {
        "severity": severity,  # "ERROR" | "WARNING"
        "dataset": dataset,
        "check": check,
        "count": count,
        "detail": detail,
        "sample": sample or [],
    }


# ---------------------------------------------------------------------------
# Per-dataset checks
# ---------------------------------------------------------------------------


def check_laps(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Detect anomalies in laps data."""
    anomalies: List[Dict[str, Any]] = []
    driver_col = "Driver" if "Driver" in df.columns else "driverId"
    lap_time_col = "LapTime" if "LapTime" in df.columns else "time"
    circuit_col = "CircuitId" if "CircuitId" in df.columns else "raceName"
    compound_col = "Compound" if "Compound" in df.columns else None

    # Missing Driver IDs
    if driver_col in df.columns:
        null_drivers = int(df[driver_col].isna().sum())
        if null_drivers > 0:
            anomalies.append(
                _anomaly(
                    "ERROR",
                    "laps",
                    "missing_driver_id",
                    null_drivers,
                    f"{null_drivers} laps have null {driver_col}",
                )
            )
            logger.error("Missing driver IDs: %d", null_drivers)

    # Lap time outliers (z-score per circuit)
    if lap_time_col in df.columns and circuit_col in df.columns:
        lt = pd.to_numeric(df[lap_time_col], errors="coerce")
        circ = df[circuit_col]
        outlier_rows = []
        for circuit, grp_idx in df.groupby(circ).groups.items():
            grp_lt = lt.loc[grp_idx].dropna()
            if len(grp_lt) < 5:
                continue
            mean, std = grp_lt.mean(), grp_lt.std()
            if std == 0:
                continue
            z = (grp_lt - mean) / std
            outliers = grp_idx[z.abs() > LAP_TIME_Z_THRESHOLD]
            outlier_rows.extend(outliers.tolist())
        if outlier_rows:
            anomalies.append(
                _anomaly(
                    "WARNING",
                    "laps",
                    "lap_time_outlier",
                    len(outlier_rows),
                    f"{len(outlier_rows)} laps exceed {LAP_TIME_Z_THRESHOLD}σ from circuit mean",
                    sample=outlier_rows[:5],
                )
            )
            logger.warning("Lap time outliers: %d rows", len(outlier_rows))

    # Invalid compound values
    if compound_col and compound_col in df.columns:
        invalid = df[compound_col].dropna()[
            ~df[compound_col].dropna().isin(VALID_COMPOUNDS)
        ]
        if len(invalid) > 0:
            unexpected = list(invalid.unique()[:10])
            anomalies.append(
                _anomaly(
                    "WARNING",
                    "laps",
                    "invalid_compound",
                    len(invalid),
                    f"{len(invalid)} invalid compound values: {unexpected}",
                    sample=unexpected,
                )
            )
            logger.warning("Invalid compounds: %d — %s", len(invalid), unexpected)

    return anomalies


def check_telemetry(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Detect anomalies in telemetry data."""
    anomalies: List[Dict[str, Any]] = []

    checks = [
        ("Speed", 0, 400),
        ("Throttle", 0, 100),
        ("nGear", 0, 8),
        ("RPM", 0, 20000),
    ]
    for col, lo, hi in checks:
        if col not in df.columns:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce").dropna()
        bad = numeric[(numeric < lo) | (numeric > hi)]
        if len(bad) > 0:
            anomalies.append(
                _anomaly(
                    "WARNING",
                    "telemetry",
                    f"out_of_range_{col}",
                    len(bad),
                    f"{len(bad)} values outside [{lo}, {hi}]: min={numeric.min():.1f}, max={numeric.max():.1f}",
                )
            )
            logger.warning("Telemetry %s out of range: %d rows", col, len(bad))

    # Sessions with 0 telemetry rows
    if "season" in df.columns and "round" in df.columns:
        session_counts = df.groupby(["season", "round"]).size()
        empty = session_counts[session_counts == 0]
        if len(empty) > 0:
            anomalies.append(
                _anomaly(
                    "WARNING",
                    "telemetry",
                    "empty_session_telemetry",
                    len(empty),
                    f"{len(empty)} sessions have 0 telemetry rows",
                    sample=empty.index.tolist()[:5],
                )
            )

    return anomalies


def check_pit_stops(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Detect anomalies in pit stop data."""
    anomalies: List[Dict[str, Any]] = []

    if "duration" in df.columns:
        dur = pd.to_numeric(df["duration"], errors="coerce").dropna()
        too_short = dur[dur < PIT_STOP_MIN_S]
        too_long = dur[dur > PIT_STOP_MAX_S]
        if len(too_short) > 0:
            anomalies.append(
                _anomaly(
                    "WARNING",
                    "pit_stops",
                    "pit_stop_too_short",
                    len(too_short),
                    f"{len(too_short)} pit stops < {PIT_STOP_MIN_S}s (min={dur.min():.2f}s)",
                )
            )
            logger.warning("Pit stops too short: %d", len(too_short))
        if len(too_long) > 0:
            anomalies.append(
                _anomaly(
                    "WARNING",
                    "pit_stops",
                    "pit_stop_too_long",
                    len(too_long),
                    f"{len(too_long)} pit stops > {PIT_STOP_MAX_S}s (max={dur.max():.2f}s)",
                )
            )
            logger.warning("Pit stops too long: %d", len(too_long))

    return anomalies


# ---------------------------------------------------------------------------
# Slack alert (optional)
# ---------------------------------------------------------------------------


def _send_slack_alert(message: str, webhook_url: str) -> None:
    """Send alert to Slack webhook if configured."""
    try:
        import urllib.request  # noqa: PLC0415

        payload = json.dumps({"text": message}).encode()
        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                logger.warning("Slack alert returned HTTP %d", resp.status)
    except Exception:
        logger.warning("Failed to send Slack alert", exc_info=True)


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_anomaly_detection(data_dir: Optional[str] = None) -> int:
    """Run all anomaly checks. Returns exit code."""
    if data_dir is None:
        if _USE_LOCAL:
            data_path = _LOCAL_DATA_DIR
            data_path.mkdir(parents=True, exist_ok=True)
            logger.info("USE_LOCAL_DATA=true — reading from %s", data_path)
        else:
            data_path = _REPO_ROOT / "data" / "processed"
    else:
        data_path = Path(data_dir)

    if not data_path.exists():
        logger.error("Data directory not found: %s", data_path)
        return 2

    logger.info("Running anomaly detection on: %s", data_path)
    all_anomalies: List[Dict[str, Any]] = []
    critical_count = 0

    dataset_checks = [
        ("laps_all.parquet", check_laps),
        ("telemetry_all.parquet", check_telemetry),
        ("pit_stops.parquet", check_pit_stops),
    ]

    for filename, check_fn in dataset_checks:
        path = data_path / filename
        if not path.exists():
            logger.warning("Skipping %s — not found", filename)
            continue
        logger.info("Checking %s...", filename)
        try:
            df = pd.read_parquet(path)
            anomalies = check_fn(df)
            all_anomalies.extend(anomalies)
        except Exception:
            logger.exception("Error reading %s", path)

    # Count by severity
    critical_count = sum(1 for a in all_anomalies if a["severity"] == "ERROR")
    warning_count = sum(1 for a in all_anomalies if a["severity"] == "WARNING")
    total = len(all_anomalies)

    # Print summary
    print("\n" + "=" * 70)
    print("F1 Data Pipeline — Anomaly Detection Report")
    print(f"Timestamp : {datetime.now(timezone.utc).isoformat()}")
    print(f"Data dir  : {data_path}")
    print("=" * 70)
    for a in all_anomalies:
        icon = "ERROR" if a["severity"] == "ERROR" else "WARN "
        print(f"  [{icon}] {a['dataset']}.{a['check']}: {a['detail']}")
    print(
        f"\nTotal: {total} anomalies | {critical_count} errors | {warning_count} warnings"
    )
    print("=" * 70 + "\n")

    # Save report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_dir": str(data_path),
        "total_anomalies": total,
        "critical": critical_count,
        "warnings": warning_count,
        "anomalies": all_anomalies,
    }
    report_path = _LOGS_DIR / "anomaly_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    logger.info("Anomaly report saved: %s", report_path)

    # Optional Slack alert
    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if webhook and total > 0:
        msg = (
            f":warning: *F1 Pipeline Anomaly Alert*\n"
            f"Found {total} anomalies ({critical_count} errors, {warning_count} warnings)\n"
            f"Run `python Data-Pipeline/scripts/anomaly_detection.py` for details."
        )
        _send_slack_alert(msg, webhook)

    if critical_count > 0:
        return 2
    if warning_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Detect anomalies in F1 processed data"
    )
    parser.add_argument(
        "--data-dir", default=None, help="Path to processed Parquet directory"
    )
    args = parser.parse_args()
    sys.exit(run_anomaly_detection(args.data_dir))
