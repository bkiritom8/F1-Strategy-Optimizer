"""
generate_gantt.py — Generate a Gantt chart for the F1 data pipeline.

Reads task timing from Data-Pipeline/logs/pipeline_runs.json when available.
Falls back to hardcoded realistic estimates based on known bottlenecks
(FastF1 telemetry download is the dominant cost at ~30 min for 3 seasons).

Outputs
-------
  Data-Pipeline/logs/gantt_chart.png   — matplotlib chart (requires matplotlib)
  stdout                               — ASCII chart (always printed)

pipeline_runs.json schema
-------------------------
Single run dict or array of run dicts (most recent entry is used):

  {
    "run_id": "scheduled__2024-01-15T00:00:00+00:00",
    "tasks": [
      {
        "task_id": "fetch_jolpica_data",
        "start_offset_min": 0.0,
        "duration_min": 5.2,
        "state": "success"
      },
      ...
    ]
  }

  start_time / end_time ISO-8601 strings are accepted in place of
  start_offset_min / duration_min.

Usage
-----
  python Data-Pipeline/scripts/generate_gantt.py
  python Data-Pipeline/scripts/generate_gantt.py --data-file Data-Pipeline/logs/pipeline_runs.json
  python Data-Pipeline/scripts/generate_gantt.py --output Data-Pipeline/logs/gantt_chart.png
  python Data-Pipeline/scripts/generate_gantt.py --ascii-only
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("generate_gantt")

_SCRIPT_DIR = Path(__file__).parent
_LOGS_DIR = _SCRIPT_DIR.parent / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_OUTPUT: Path = _LOGS_DIR / "gantt_chart.png"
DEFAULT_RUNS_FILE: Path = _LOGS_DIR / "pipeline_runs.json"

# ── Hardcoded estimates ──────────────────────────────────────────────────────
# fetch_jolpica and fetch_fastf1 both start at t=0 (parallel Airflow tasks).
# Every downstream task waits for the bottleneck (fetch_fastf1) to complete.

_DEFAULT_TASKS: List[Dict[str, Any]] = [
    {
        "task_id": "fetch_jolpica_data",
        "start_min": 0.0,
        "duration_min": 5.0,
        "state": "success",
        "bottleneck": False,
    },
    {
        "task_id": "fetch_fastf1_data",
        "start_min": 0.0,
        "duration_min": 30.0,
        "state": "success",
        "bottleneck": True,  # 10Hz telemetry for 3 seasons — dominant cost
    },
    {
        "task_id": "validate_raw_data",
        "start_min": 30.0,  # waits for both ingest tasks
        "duration_min": 2.0,
        "state": "success",
        "bottleneck": False,
    },
    {
        "task_id": "preprocess_data",
        "start_min": 32.0,
        "duration_min": 5.0,
        "state": "success",
        "bottleneck": False,
    },
    {
        "task_id": "detect_anomalies",
        "start_min": 37.0,
        "duration_min": 1.0,
        "state": "success",
        "bottleneck": False,
    },
    {
        "task_id": "build_features",
        "start_min": 38.0,
        "duration_min": 7.0,
        "state": "success",
        "bottleneck": False,
    },
    {
        "task_id": "bias_analysis",
        "start_min": 45.0,
        "duration_min": 2.0,
        "state": "success",
        "bottleneck": False,
    },
]

_STATE_COLORS: Dict[str, str] = {
    "success": "#2ecc71",  # green
    "failed": "#e74c3c",  # red
    "running": "#f39c12",  # yellow/amber
    "skipped": "#95a5a6",  # grey
    "bottleneck": "#e67e22",  # orange
}


# ── Data loading ─────────────────────────────────────────────────────────────


def _load_run_file(path: Path) -> Optional[List[Dict[str, Any]]]:
    """Parse pipeline_runs.json and return the task list for the most recent run."""
    try:
        raw: Any = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Cannot read %s — %s", path, exc)
        return None

    if isinstance(raw, dict):
        raw = [raw]
    if not raw:
        return None

    # Use the most recent run entry
    run = raw[-1]
    if isinstance(run, dict) and "tasks" in run:
        return run["tasks"]  # type: ignore[return-value]
    if isinstance(run, list):
        return run  # type: ignore[return-value]
    return None


def _parse_tasks(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Normalise raw task records to the internal format:
      {task_id, start_min, duration_min, state, bottleneck}

    Accepts either:
      • start_offset_min + duration_min  (preferred)
      • start_time + end_time            (ISO-8601 strings)
    """
    # First pass: locate the earliest start_time for relative-offset calculation
    pipeline_start: Optional[datetime] = None
    for rec in records:
        if "start_time" in rec:
            try:
                st = datetime.fromisoformat(rec["start_time"].replace("Z", "+00:00"))
                if pipeline_start is None or st < pipeline_start:
                    pipeline_start = st
            except ValueError:
                pass

    out: List[Dict[str, Any]] = []
    for rec in records:
        task_id = str(rec.get("task_id", "unknown"))
        state = str(rec.get("state", "success")).lower()
        bottleneck = bool(rec.get("bottleneck", False))

        if "start_offset_min" in rec and "duration_min" in rec:
            start_min = float(rec["start_offset_min"])
            duration_min = float(rec["duration_min"])
        elif "start_time" in rec and "end_time" in rec and pipeline_start is not None:
            try:
                st = datetime.fromisoformat(rec["start_time"].replace("Z", "+00:00"))
                et = datetime.fromisoformat(rec["end_time"].replace("Z", "+00:00"))
                start_min = (st - pipeline_start).total_seconds() / 60.0
                duration_min = (et - st).total_seconds() / 60.0
            except ValueError:
                logger.debug("Skipping task %r — unparseable timestamps", task_id)
                continue
        else:
            logger.debug("Skipping task %r — no timing fields found", task_id)
            continue

        out.append(
            {
                "task_id": task_id,
                "start_min": max(0.0, start_min),
                "duration_min": max(0.1, duration_min),
                "state": state,
                "bottleneck": bottleneck,
            }
        )
    return out


def _resolve_tasks(data_file: Optional[Path]) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Return (tasks, loaded_from_file).
    Falls back to _DEFAULT_TASKS when no valid file data is available.
    """
    if data_file and data_file.exists():
        records = _load_run_file(data_file)
        if records:
            tasks = _parse_tasks(records)
            if tasks:
                logger.info("Loaded %d tasks from %s", len(tasks), data_file)
                return tasks, True
            logger.warning(
                "No parseable task records in %s — using defaults", data_file
            )

    logger.info(
        "No run data found — using hardcoded estimates. "
        "Run the Airflow DAG and write results to %s to use real timings.",
        DEFAULT_RUNS_FILE,
    )
    return list(_DEFAULT_TASKS), False


# ── ASCII chart ───────────────────────────────────────────────────────────────


def _build_tick_header(total_min: int, step: int = 10) -> str:
    """
    Build a ruler string with tick labels at every `step` minutes.
    Example (total_min=60, step=10):
        '0         10        20        30        40        50        60'
    Each character position corresponds to one minute on the timeline.
    """
    chars = list(" " * (total_min + 1))
    for tick in range(0, total_min + 1, step):
        label = str(tick)
        for j, ch in enumerate(label):
            if tick + j <= total_min:
                chars[tick + j] = ch
    return "".join(chars)


def print_ascii_gantt(
    tasks: List[Dict[str, Any]],
    from_file: bool = False,
    total_min: int = 60,
) -> None:
    """Print an ASCII Gantt chart to stdout (1 character = 1 minute)."""
    label_w = max(len(t["task_id"]) for t in tasks) + 2
    tick_header = _build_tick_header(total_min)
    source = "pipeline_runs.json" if from_file else "hardcoded estimates"
    divider = "=" * (label_w + total_min + 8)

    print()
    print(divider)
    print("F1 Data Pipeline — Task Duration (Gantt)")
    print(f"Source  : {source}")
    print(divider)
    print(f"{'Task':<{label_w}}| {tick_header} min")
    print("-" * label_w + "|" + "-" * (total_min + 5))

    for task in tasks:
        label = task["task_id"]
        start = task["start_min"]
        dur = task["duration_min"]
        is_bottleneck = task.get("bottleneck", False)

        pre = " " * int(round(start))
        fill = "=" * max(1, int(round(dur)))
        bar = f"[{fill}]"
        suffix = " ← bottleneck" if is_bottleneck else ""
        print(f"{label:<{label_w}}| {pre}{bar}{suffix}")

    print("-" * label_w + "|" + "-" * (total_min + 5))

    total_wall = max(t["start_min"] + t["duration_min"] for t in tasks)
    seq_total = sum(t["duration_min"] for t in tasks)
    saved = seq_total - total_wall
    print(
        f"{'Wall-clock total':<{label_w}}| "
        f"{total_wall:.1f} min  "
        f"(parallel saved {saved:.1f} min vs sequential {seq_total:.1f} min)"
    )
    print(divider)
    print()


# ── Matplotlib chart ──────────────────────────────────────────────────────────


def generate_png_gantt(
    tasks: List[Dict[str, Any]],
    output_path: Path,
    from_file: bool = False,
) -> bool:
    """
    Render a PNG Gantt chart with matplotlib.
    Returns True on success, False if matplotlib is unavailable.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")  # non-interactive backend — safe in CI/containers
        import matplotlib.patches as mpatches
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
    except ImportError:
        logger.warning(
            "matplotlib not installed — PNG chart skipped. "
            "Install with: pip install 'matplotlib>=3.7.0'"
        )
        return False

    n = len(tasks)
    fig, ax = plt.subplots(figsize=(13, max(4.0, n * 0.65 + 1.8)))

    yticks: List[int] = []
    ylabels: List[str] = []

    for i, task in enumerate(tasks):
        start = task["start_min"]
        dur = task["duration_min"]
        state = task.get("state", "success")
        is_bottleneck = task.get("bottleneck", False)

        color = (
            _STATE_COLORS["bottleneck"]
            if is_bottleneck
            else _STATE_COLORS.get(state, _STATE_COLORS["success"])
        )

        ax.broken_barh(
            [(start, dur)],
            (i - 0.38, 0.76),
            facecolors=color,
            edgecolors="#2c3e50",
            linewidth=0.6,
        )

        # Duration label inside the bar (only when wide enough to fit)
        if dur >= 2.0:
            ax.text(
                start + dur / 2,
                i,
                f"{dur:.0f}m",
                ha="center",
                va="center",
                fontsize=8,
                color="white",
                fontweight="bold",
            )

        # Bottleneck annotation to the right of the bar
        if is_bottleneck:
            ax.annotate(
                "← bottleneck",
                xy=(start + dur, i),
                xytext=(start + dur + 1.5, i),
                fontsize=8.5,
                color=_STATE_COLORS["bottleneck"],
                va="center",
                fontweight="bold",
            )

        yticks.append(i)
        ylabels.append(task["task_id"])

    # ── Y axis ─────────────────────────────────────────────────────────────────
    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels, fontsize=9.5)
    ax.set_ylim(-0.7, n - 0.3)
    ax.invert_yaxis()  # first task at the top

    # Bracket marking the parallel ingest tasks (both start at t=0)
    parallel_idx = [i for i, t in enumerate(tasks) if t["start_min"] == 0.0]
    if len(parallel_idx) >= 2:
        y_top = min(parallel_idx) - 0.45
        y_bot = max(parallel_idx) + 0.45
        ax.annotate(
            "",
            xy=(-1.5, y_top),
            xytext=(-1.5, y_bot),
            xycoords="data",
            textcoords="data",
            arrowprops=dict(arrowstyle="-", color="#7f8c8d", lw=1.8),
        )
        ax.text(
            -2.8,
            (y_top + y_bot) / 2,
            "parallel",
            ha="right",
            va="center",
            fontsize=7.5,
            color="#7f8c8d",
            rotation=90,
        )

    # ── X axis ─────────────────────────────────────────────────────────────────
    total_wall = max(t["start_min"] + t["duration_min"] for t in tasks)
    x_max = max(62.0, total_wall * 1.18)
    ax.set_xlim(-4, x_max)
    ax.set_xlabel("Time (minutes from pipeline start)", fontsize=10)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(10))
    ax.xaxis.set_minor_locator(ticker.MultipleLocator(5))
    ax.grid(axis="x", which="major", linestyle="--", alpha=0.35, color="#95a5a6")
    ax.grid(axis="x", which="minor", linestyle=":", alpha=0.2, color="#bdc3c7")

    # Vertical dashed line at pipeline completion
    ax.axvline(total_wall, color="#2c3e50", linestyle="--", alpha=0.5, linewidth=1.2)
    ax.text(
        total_wall + 0.8,
        n - 0.65,
        f"{total_wall:.0f}m total",
        fontsize=8,
        color="#2c3e50",
        va="bottom",
    )

    # ── Legend ─────────────────────────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(
            facecolor=_STATE_COLORS["success"], edgecolor="#2c3e50", label="Success"
        ),
        mpatches.Patch(
            facecolor=_STATE_COLORS["bottleneck"],
            edgecolor="#2c3e50",
            label="Bottleneck",
        ),
        mpatches.Patch(
            facecolor=_STATE_COLORS["running"], edgecolor="#2c3e50", label="Running"
        ),
        mpatches.Patch(
            facecolor=_STATE_COLORS["failed"], edgecolor="#2c3e50", label="Failed"
        ),
    ]
    ax.legend(handles=legend_items, loc="lower right", fontsize=8.5, framealpha=0.85)

    # ── Title ──────────────────────────────────────────────────────────────────
    subtitle = (
        "sourced from pipeline_runs.json"
        if from_file
        else "estimated from known bottlenecks"
    )
    ax.set_title(
        f"F1 Data Pipeline — Task Duration (Gantt)\n({subtitle})",
        fontsize=12,
        fontweight="bold",
        pad=14,
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    logger.info("Gantt chart saved → %s", output_path)
    return True


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate a Gantt chart for the F1 data pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-file",
        default=str(DEFAULT_RUNS_FILE),
        help=f"Path to pipeline_runs.json (default: {DEFAULT_RUNS_FILE})",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"PNG output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--ascii-only",
        action="store_true",
        help="Print ASCII chart to terminal only; skip PNG generation",
    )
    args = parser.parse_args()

    tasks, from_file = _resolve_tasks(Path(args.data_file))

    # ASCII chart is always printed (works without matplotlib)
    print_ascii_gantt(tasks, from_file=from_file)

    if args.ascii_only:
        logger.info("--ascii-only flag set; skipping PNG generation")
        return 0

    ok = generate_png_gantt(tasks, Path(args.output), from_file=from_file)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
