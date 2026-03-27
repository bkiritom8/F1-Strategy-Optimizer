"""
generate_gantt.py — Gantt chart for the F1 Strategy Optimizer Cloud Build pipeline.

Reads step timing from pipeline/logs/build_run.json when available.
Falls back to hardcoded realistic estimates based on observed build durations
(train-models is the dominant cost at ~45 min for 6 Vertex AI Custom Jobs).

Outputs
-------
  pipeline/logs/gantt_chart.png   — matplotlib chart (requires matplotlib)
  stdout                          — ASCII chart (always printed)

build_run.json schema
---------------------
Written by the optional fetch step or by hand after a build completes.
Accepted shapes:

  Single build dict:
  {
    "build_id": "459a8a75-...",
    "steps": [
      {
        "step_id":        "build-api",
        "start_offset_min": 0.0,
        "duration_min":     6.2,
        "status":           "SUCCESS"
      },
      ...
    ]
  }

  start_time / finish_time ISO-8601 strings are also accepted in place of
  start_offset_min / duration_min (the script converts them automatically).

  You can generate this file from a real build with:
    python pipeline/scripts/generate_gantt.py --fetch-build <BUILD_ID>

Usage
-----
  python pipeline/scripts/generate_gantt.py
  python pipeline/scripts/generate_gantt.py --data-file pipeline/logs/build_run.json
  python pipeline/scripts/generate_gantt.py --fetch-build <BUILD_ID> --project f1optimizer
  python pipeline/scripts/generate_gantt.py --output pipeline/logs/gantt_chart.png
  python pipeline/scripts/generate_gantt.py --ascii-only
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("generate_gantt")

_SCRIPT_DIR = Path(__file__).parent
_LOGS_DIR = _SCRIPT_DIR.parent / "logs"
_LOGS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_OUTPUT: Path = _LOGS_DIR / "gantt_chart.png"
DEFAULT_RUNS_FILE: Path = _LOGS_DIR / "build_run.json"

# ── Cloud Build step definitions ─────────────────────────────────────────────
#
# Parallelism mirrors the actual waitFor graph in cloudbuild.yaml:
#
#   build-api  ─────────────────────────────────────────────► push-api ─┐
#   build-ml  ──────────────────────────────────────────────► push-ml ──┤
#                                                                         │
#                                                           train-models ◄┘
#                                                                │
#                                                        validate-models
#                                                                │
#                                              ┌─── check-bias ─┤
#                                              │     test-rag ──┘
#                                              │         │
#                                        push-models-registry
#                                                │
#                                         rollback-check
#
# Estimated durations are based on observed Cloud Build runs in us-central1.

_DEFAULT_STEPS: list[dict[str, Any]] = [
    {
        "step_id": "build-api",
        "start_min": 0.0,
        "duration_min": 6.0,
        "status": "SUCCESS",
        "bottleneck": False,
        "lane": 0,
    },
    {
        "step_id": "build-ml",
        "start_min": 0.0,
        "duration_min": 11.0,
        "status": "SUCCESS",
        "bottleneck": False,
        "lane": 1,
    },
    {
        "step_id": "push-api",
        "start_min": 6.0,      # waitFor: build-api
        "duration_min": 2.0,
        "status": "SUCCESS",
        "bottleneck": False,
        "lane": 0,
    },
    {
        "step_id": "push-ml",
        "start_min": 11.0,     # waitFor: build-ml
        "duration_min": 2.0,
        "status": "SUCCESS",
        "bottleneck": False,
        "lane": 1,
    },
    {
        "step_id": "train-models",
        "start_min": 13.0,     # waitFor: push-ml
        "duration_min": 46.0,  # 6 Vertex AI Custom Jobs polled sequentially
        "status": "SUCCESS",
        "bottleneck": True,    # dominant cost — Vertex AI n1-standard-8 jobs
        "lane": 0,
    },
    {
        "step_id": "validate-models",
        "start_min": 59.0,     # waitFor: train-models
        "duration_min": 2.0,
        "status": "SUCCESS",
        "bottleneck": False,
        "lane": 0,
    },
    {
        "step_id": "check-bias",
        "start_min": 61.0,     # waitFor: validate-models
        "duration_min": 2.0,
        "status": "SUCCESS",
        "bottleneck": False,
        "lane": 0,
    },
    {
        "step_id": "test-rag",
        "start_min": 61.0,     # runs in parallel with check-bias
        "duration_min": 3.0,   # pip install + 24 pytest tests
        "status": "SUCCESS",
        "bottleneck": False,
        "lane": 1,
    },
    {
        "step_id": "push-models-registry",
        "start_min": 64.0,     # waitFor: check-bias + test-rag
        "duration_min": 3.0,
        "status": "SUCCESS",
        "bottleneck": False,
        "lane": 0,
    },
    {
        "step_id": "rollback-check",
        "start_min": 67.0,     # waitFor: push-models-registry
        "duration_min": 2.0,
        "status": "SUCCESS",
        "bottleneck": False,
        "lane": 0,
    },
]

_STATUS_COLORS: dict[str, str] = {
    "SUCCESS": "#2ecc71",
    "FAILURE": "#e74c3c",
    "WORKING": "#f39c12",
    "QUEUED": "#95a5a6",
    "TIMEOUT": "#9b59b6",
    "CANCELLED": "#7f8c8d",
    "bottleneck": "#e67e22",
}


# ── Cloud Build data fetch ────────────────────────────────────────────────────


def fetch_build_data(build_id: str, project: str, region: str) -> dict[str, Any] | None:
    """
    Fetch step timings from a real Cloud Build run via gcloud and write
    build_run.json.  Returns the parsed dict or None on failure.
    """
    logger.info("Fetching build %s from project %s (%s)…", build_id, project, region)
    try:
        result = subprocess.run(
            [
                "gcloud", "builds", "describe", build_id,
                f"--project={project}",
                f"--region={region}",
                "--format=json",
            ],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.error("gcloud failed: %s", exc)
        return None

    try:
        raw: dict[str, Any] = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error("Cannot parse gcloud output: %s", exc)
        return None

    build_start_str: str = raw.get("startTime", "")
    try:
        build_start = datetime.fromisoformat(build_start_str.replace("Z", "+00:00"))
    except ValueError:
        build_start = None

    steps: list[dict[str, Any]] = []
    for raw_step in raw.get("steps", []):
        step_id = raw_step.get("id", raw_step.get("name", "unknown"))
        status = raw_step.get("status", "WORKING")

        timing = raw_step.get("timing", {})
        start_str = timing.get("startTime", "")
        end_str = timing.get("endTime", "")

        if build_start and start_str and end_str:
            try:
                st = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                et = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                start_offset = (st - build_start).total_seconds() / 60.0
                duration = (et - st).total_seconds() / 60.0
            except ValueError:
                start_offset = 0.0
                duration = 0.0
        else:
            start_offset = 0.0
            duration = 0.0

        steps.append({
            "step_id": step_id,
            "start_offset_min": round(start_offset, 2),
            "duration_min": round(max(0.1, duration), 2),
            "status": status,
        })

    out = {"build_id": build_id, "steps": steps}
    DEFAULT_RUNS_FILE.write_text(json.dumps(out, indent=2))
    logger.info("Saved build timing → %s", DEFAULT_RUNS_FILE)
    return out


# ── Data loading ─────────────────────────────────────────────────────────────


def _load_run_file(path: Path) -> list[dict[str, Any]] | None:
    """Parse build_run.json and return the step list."""
    try:
        raw: Any = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Cannot read %s — %s", path, exc)
        return None

    if isinstance(raw, dict) and "steps" in raw:
        return raw["steps"]
    return None


def _parse_steps(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Normalise raw step records to internal format:
      {step_id, start_min, duration_min, status, bottleneck, lane}

    Accepted input fields:
      • start_offset_min + duration_min   (preferred — written by fetch_build_data)
      • start_time + finish_time          (ISO-8601, relative to pipeline start)
    """
    pipeline_start: datetime | None = None
    for rec in records:
        for key in ("start_time", "startTime"):
            if key in rec:
                try:
                    ts = datetime.fromisoformat(rec[key].replace("Z", "+00:00"))
                    if pipeline_start is None or ts < pipeline_start:
                        pipeline_start = ts
                except ValueError:
                    pass

    out: list[dict[str, Any]] = []
    for rec in records:
        step_id = str(rec.get("step_id", rec.get("id", "unknown")))
        status = str(rec.get("status", "SUCCESS")).upper()

        if "start_offset_min" in rec and "duration_min" in rec:
            start_min = float(rec["start_offset_min"])
            duration_min = float(rec["duration_min"])
        elif all(k in rec for k in ("start_time", "finish_time")) and pipeline_start:
            try:
                st = datetime.fromisoformat(rec["start_time"].replace("Z", "+00:00"))
                et = datetime.fromisoformat(rec["finish_time"].replace("Z", "+00:00"))
                start_min = (st - pipeline_start).total_seconds() / 60.0
                duration_min = (et - st).total_seconds() / 60.0
            except ValueError:
                logger.debug("Skipping %r — unparseable timestamps", step_id)
                continue
        else:
            logger.debug("Skipping %r — no timing fields", step_id)
            continue

        out.append({
            "step_id": step_id,
            "start_min": max(0.0, start_min),
            "duration_min": max(0.1, duration_min),
            "status": status,
            "bottleneck": rec.get("bottleneck", False),
            "lane": rec.get("lane", 0),
        })
    return out


def _resolve_steps(data_file: Path | None) -> tuple[list[dict[str, Any]], bool]:
    """
    Return (steps, loaded_from_file).
    Falls back to _DEFAULT_STEPS when no valid file data is available.
    """
    if data_file and data_file.exists():
        records = _load_run_file(data_file)
        if records:
            steps = _parse_steps(records)
            if steps:
                logger.info("Loaded %d steps from %s", len(steps), data_file)
                return steps, True
            logger.warning("No parseable step records in %s — using defaults", data_file)

    logger.info(
        "No build data found — using hardcoded estimates based on observed durations. "
        "Fetch a real build with: --fetch-build <BUILD_ID>"
    )
    return list(_DEFAULT_STEPS), False


# ── ASCII chart ───────────────────────────────────────────────────────────────


def _tick_header(total_min: int, step: int = 10) -> str:
    chars = list(" " * (total_min + 1))
    for tick in range(0, total_min + 1, step):
        label = str(tick)
        for j, ch in enumerate(label):
            if tick + j <= total_min:
                chars[tick + j] = ch
    return "".join(chars)


def print_ascii_gantt(
    steps: list[dict[str, Any]],
    from_file: bool = False,
    total_min: int = 80,
) -> None:
    """Print an ASCII Gantt chart to stdout (1 char = 1 minute)."""
    label_w = max(len(s["step_id"]) for s in steps) + 2
    divider = "=" * (label_w + total_min + 10)
    source = "build_run.json" if from_file else "hardcoded estimates"

    print()
    print(divider)
    print("F1 Strategy Optimizer — Cloud Build Pipeline (Gantt)")
    print(f"Source: {source}")
    print(divider)
    print(f"{'Step':<{label_w}}| {_tick_header(total_min)} min")
    print("-" * label_w + "+" + "-" * (total_min + 6))

    for step in steps:
        label = step["step_id"]
        start = int(round(step["start_min"]))
        dur = max(1, int(round(step["duration_min"])))
        is_bottleneck = step.get("bottleneck", False)

        bar = " " * start + "[" + "=" * dur + "]"
        suffix = "  ← bottleneck" if is_bottleneck else ""
        print(f"{label:<{label_w}}| {bar}{suffix}")

    print("-" * label_w + "+" + "-" * (total_min + 6))
    wall = max(s["start_min"] + s["duration_min"] for s in steps)
    seq = sum(s["duration_min"] for s in steps)
    print(
        f"{'Wall-clock total':<{label_w}}| "
        f"{wall:.1f} min  "
        f"(parallelism saved {seq - wall:.1f} min vs {seq:.1f} min sequential)"
    )
    print(divider)
    print()


# ── Matplotlib PNG chart ──────────────────────────────────────────────────────


def generate_png_gantt(
    steps: list[dict[str, Any]],
    output_path: Path,
    from_file: bool = False,
) -> bool:
    """
    Render a colour-coded PNG Gantt chart.
    Returns True on success, False if matplotlib is not installed.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.patches as mpatches
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
    except ImportError:
        logger.warning(
            "matplotlib not installed — PNG skipped. "
            "pip install 'matplotlib>=3.7.0'"
        )
        return False

    n = len(steps)
    fig, ax = plt.subplots(figsize=(15, max(4.5, n * 0.7 + 2.0)))

    yticks: list[int] = []
    ylabels: list[str] = []

    for i, step in enumerate(steps):
        start = step["start_min"]
        dur = step["duration_min"]
        status = step.get("status", "SUCCESS")
        is_bottleneck = step.get("bottleneck", False)

        color = (
            _STATUS_COLORS["bottleneck"]
            if is_bottleneck
            else _STATUS_COLORS.get(status, _STATUS_COLORS["SUCCESS"])
        )

        ax.broken_barh(
            [(start, dur)],
            (i - 0.38, 0.76),
            facecolors=color,
            edgecolors="#2c3e50",
            linewidth=0.6,
        )

        if dur >= 1.5:
            ax.text(
                start + dur / 2, i,
                f"{dur:.0f}m",
                ha="center", va="center",
                fontsize=8.5, color="white", fontweight="bold",
            )

        if is_bottleneck:
            ax.annotate(
                "← bottleneck",
                xy=(start + dur, i),
                xytext=(start + dur + 1.0, i),
                fontsize=8.5, color=_STATUS_COLORS["bottleneck"],
                va="center", fontweight="bold",
            )

        yticks.append(i)
        ylabels.append(step["step_id"])

    # Bracket parallel groups (steps starting at the same time)
    from itertools import groupby
    sorted_by_start = sorted(enumerate(steps), key=lambda x: round(x[1]["start_min"], 1))
    for _, group in groupby(sorted_by_start, key=lambda x: round(x[1]["start_min"], 1)):
        group_list = list(group)
        if len(group_list) >= 2:
            idxs = [g[0] for g in group_list]
            y_top = min(idxs) - 0.5
            y_bot = max(idxs) + 0.5
            x_pos = group_list[0][1]["start_min"] - 1.8
            ax.annotate("", xy=(x_pos, y_top), xytext=(x_pos, y_bot),
                        arrowprops=dict(arrowstyle="-", color="#7f8c8d", lw=1.8))
            ax.text(x_pos - 1.2, (y_top + y_bot) / 2, "parallel",
                    ha="right", va="center", fontsize=7, color="#7f8c8d", rotation=90)

    # Axes
    wall = max(s["start_min"] + s["duration_min"] for s in steps)
    x_max = max(85.0, wall * 1.2)
    ax.set_xlim(-6, x_max)
    ax.set_ylim(-0.7, n - 0.3)
    ax.invert_yaxis()
    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels, fontsize=9.5)
    ax.set_xlabel("Time (minutes from build start)", fontsize=10)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(10))
    ax.xaxis.set_minor_locator(ticker.MultipleLocator(5))
    ax.grid(axis="x", which="major", linestyle="--", alpha=0.35, color="#95a5a6")
    ax.grid(axis="x", which="minor", linestyle=":", alpha=0.2, color="#bdc3c7")

    # Completion line
    ax.axvline(wall, color="#2c3e50", linestyle="--", alpha=0.5, linewidth=1.2)
    ax.text(wall + 0.8, n - 0.7, f"{wall:.0f}m total",
            fontsize=8, color="#2c3e50", va="bottom")

    # Legend
    legend_items = [
        mpatches.Patch(facecolor=_STATUS_COLORS["SUCCESS"],    edgecolor="#2c3e50", label="SUCCESS"),
        mpatches.Patch(facecolor=_STATUS_COLORS["bottleneck"], edgecolor="#2c3e50", label="Bottleneck"),
        mpatches.Patch(facecolor=_STATUS_COLORS["WORKING"],    edgecolor="#2c3e50", label="WORKING"),
        mpatches.Patch(facecolor=_STATUS_COLORS["FAILURE"],    edgecolor="#2c3e50", label="FAILURE"),
        mpatches.Patch(facecolor=_STATUS_COLORS["TIMEOUT"],    edgecolor="#2c3e50", label="TIMEOUT"),
    ]
    ax.legend(handles=legend_items, loc="lower right", fontsize=8.5, framealpha=0.85)

    subtitle = "sourced from build_run.json" if from_file else "estimated from observed durations"
    ax.set_title(
        f"F1 Strategy Optimizer — Cloud Build Pipeline (Gantt)\n({subtitle})",
        fontsize=12, fontweight="bold", pad=14,
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
        description="Gantt chart for the F1 Strategy Optimizer Cloud Build pipeline.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data-file",
        default=str(DEFAULT_RUNS_FILE),
        help=f"Path to build_run.json (default: {DEFAULT_RUNS_FILE})",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help=f"PNG output path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--ascii-only",
        action="store_true",
        help="Print ASCII chart only; skip PNG generation",
    )
    parser.add_argument(
        "--fetch-build",
        metavar="BUILD_ID",
        help="Fetch real step timings from a Cloud Build run and save to build_run.json",
    )
    parser.add_argument(
        "--project",
        default="f1optimizer",
        help="GCP project ID for --fetch-build (default: f1optimizer)",
    )
    parser.add_argument(
        "--region",
        default="us-central1",
        help="Cloud Build region for --fetch-build (default: us-central1)",
    )
    args = parser.parse_args()

    if args.fetch_build:
        data = fetch_build_data(args.fetch_build, args.project, args.region)
        if data is None:
            logger.error("Failed to fetch build data — falling back to defaults")
        else:
            logger.info("Build data written to %s", DEFAULT_RUNS_FILE)

    steps, from_file = _resolve_steps(Path(args.data_file))

    print_ascii_gantt(steps, from_file=from_file)

    if args.ascii_only:
        return 0

    ok = generate_png_gantt(steps, Path(args.output), from_file=from_file)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
