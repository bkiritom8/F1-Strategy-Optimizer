"""
generate_gantt.py — Gantt chart for the F1 Strategy Optimizer pipelines.

Shows two sections in one chart:
  1. INGEST PIPELINE  — Cloud Run Job (9 parallel tasks, run on demand)
  2. CLOUD BUILD      — Cloud Build pipeline (triggered on push to pipeline branch)

Reads step timing from pipeline/logs/build_run.json when available.
Falls back to hardcoded realistic estimates based on observed run durations.

Outputs
-------
  pipeline/logs/gantt_chart.png   — matplotlib chart
  stdout                          — ASCII chart (always printed)

build_run.json schema
---------------------
  {
    "build_id": "4616b688-...",
    "ingest": [
      {"step_id": "fastf1_2018", "start_offset_min": 0.0, "duration_min": 38.0, "status": "SUCCESS"},
      ...
    ],
    "steps": [
      {"step_id": "build-api",  "start_offset_min": 0.0,  "duration_min": 14.2, "status": "SUCCESS"},
      ...
    ]
  }

  Ingest timing can also be written manually after a Cloud Run Job completes.
  Cloud Build timing can be fetched automatically with --fetch-build <BUILD_ID>.

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
from datetime import datetime
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

# ── Section colours ───────────────────────────────────────────────────────────
_SECTION_BG = {
    "ingest": "#f0f8ff",   # light blue tint
    "build":  "#f9f9f9",   # near-white
}
_SECTION_HEADER = {
    "ingest": "#2980b9",
    "build":  "#2c3e50",
}

# ── Status colours ────────────────────────────────────────────────────────────
_STATUS_COLORS: dict[str, str] = {
    "SUCCESS":    "#2ecc71",
    "FAILURE":    "#e74c3c",
    "WORKING":    "#f39c12",
    "QUEUED":     "#95a5a6",
    "TIMEOUT":    "#9b59b6",
    "CANCELLED":  "#7f8c8d",
    "bottleneck": "#e67e22",
}

# ── Hardcoded ingest estimates ────────────────────────────────────────────────
# All 9 Cloud Run tasks start at t=0 (parallel execution).
# FastF1 download time scales with season length and telemetry volume.
# Historical Jolpica is rate-limited to ~450 req/hr.

_DEFAULT_INGEST: list[dict[str, Any]] = [
    {"step_id": "fastf1_2018 (Task 0)", "start_min": 0.0, "duration_min": 38.0, "status": "SUCCESS", "bottleneck": True,  "section": "ingest"},
    {"step_id": "fastf1_2019 (Task 1)", "start_min": 0.0, "duration_min": 35.0, "status": "SUCCESS", "bottleneck": False, "section": "ingest"},
    {"step_id": "fastf1_2020 (Task 2)", "start_min": 0.0, "duration_min": 30.0, "status": "SUCCESS", "bottleneck": False, "section": "ingest"},
    {"step_id": "fastf1_2021 (Task 3)", "start_min": 0.0, "duration_min": 36.0, "status": "SUCCESS", "bottleneck": False, "section": "ingest"},
    {"step_id": "fastf1_2022 (Task 4)", "start_min": 0.0, "duration_min": 34.0, "status": "SUCCESS", "bottleneck": False, "section": "ingest"},
    {"step_id": "fastf1_2023 (Task 5)", "start_min": 0.0, "duration_min": 32.0, "status": "SUCCESS", "bottleneck": False, "section": "ingest"},
    {"step_id": "fastf1_2024 (Task 6)", "start_min": 0.0, "duration_min": 28.0, "status": "SUCCESS", "bottleneck": False, "section": "ingest"},
    {"step_id": "fastf1_2025 (Task 7)", "start_min": 0.0, "duration_min": 10.0, "status": "SUCCESS", "bottleneck": False, "section": "ingest"},
    {"step_id": "historical  (Task 8)", "start_min": 0.0, "duration_min": 18.0, "status": "SUCCESS", "bottleneck": False, "section": "ingest"},
]

# ── Hardcoded Cloud Build estimates ──────────────────────────────────────────
# Based on observed build 4616b688 (SUCCESS, 2026-03-27).
# push-models-registry is a secondary bottleneck due to Vertex AI LRO waits.

_DEFAULT_BUILD: list[dict[str, Any]] = [
    {"step_id": "build-api",             "start_min": 0.0,  "duration_min": 14.0, "status": "SUCCESS", "bottleneck": False, "section": "build"},
    {"step_id": "build-ml",              "start_min": 14.0, "duration_min": 6.0,  "status": "SUCCESS", "bottleneck": False, "section": "build"},
    {"step_id": "push-api",              "start_min": 14.0, "duration_min": 1.0,  "status": "SUCCESS", "bottleneck": False, "section": "build"},
    {"step_id": "push-ml",               "start_min": 20.0, "duration_min": 6.0,  "status": "SUCCESS", "bottleneck": False, "section": "build"},
    {"step_id": "train-models",          "start_min": 26.0, "duration_min": 33.0, "status": "SUCCESS", "bottleneck": True,  "section": "build"},
    {"step_id": "validate-models",       "start_min": 59.0, "duration_min": 1.0,  "status": "SUCCESS", "bottleneck": False, "section": "build"},
    {"step_id": "check-bias",            "start_min": 60.0, "duration_min": 1.0,  "status": "SUCCESS", "bottleneck": False, "section": "build"},
    {"step_id": "test-rag",              "start_min": 60.0, "duration_min": 2.0,  "status": "SUCCESS", "bottleneck": False, "section": "build"},
    {"step_id": "push-models-registry",  "start_min": 62.0, "duration_min": 19.0, "status": "SUCCESS", "bottleneck": True,  "section": "build"},
    {"step_id": "rollback-check",        "start_min": 81.0, "duration_min": 1.0,  "status": "SUCCESS", "bottleneck": False, "section": "build"},
]


# ── Cloud Build fetch ─────────────────────────────────────────────────────────


def fetch_build_data(build_id: str, project: str, region: str) -> dict[str, Any] | None:
    """Fetch real step timings from gcloud and merge into build_run.json."""
    logger.info("Fetching build %s…", build_id)
    try:
        result = subprocess.run(
            ["gcloud", "builds", "describe", build_id,
             f"--project={project}", f"--region={region}", "--format=json"],
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
        status  = raw_step.get("status", "WORKING")
        timing  = raw_step.get("timing", {})
        start_str = timing.get("startTime", "")
        end_str   = timing.get("endTime", "")

        if build_start and start_str and end_str:
            try:
                st = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                et = datetime.fromisoformat(end_str.replace("Z", "+00:00"))
                start_offset = (st - build_start).total_seconds() / 60.0
                duration     = (et - st).total_seconds() / 60.0
            except ValueError:
                start_offset = duration = 0.0
        else:
            start_offset = duration = 0.0

        steps.append({
            "step_id":          step_id,
            "start_offset_min": round(start_offset, 2),
            "duration_min":     round(max(0.1, duration), 2),
            "status":           status,
        })

    # Preserve existing ingest data if present
    existing: dict[str, Any] = {}
    if DEFAULT_RUNS_FILE.exists():
        try:
            existing = json.loads(DEFAULT_RUNS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    out = {"build_id": build_id, "steps": steps, "ingest": existing.get("ingest", [])}
    DEFAULT_RUNS_FILE.write_text(json.dumps(out, indent=2))
    logger.info("Saved → %s", DEFAULT_RUNS_FILE)
    return out


# ── Parsing helpers ───────────────────────────────────────────────────────────


def _parse_records(
    records: list[dict[str, Any]],
    section: str,
) -> list[dict[str, Any]]:
    """Normalise raw records to internal step format."""
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
        step_id   = str(rec.get("step_id", rec.get("id", "unknown")))
        status    = str(rec.get("status", "SUCCESS")).upper()
        is_bottle = bool(rec.get("bottleneck", False))

        if "start_offset_min" in rec and "duration_min" in rec:
            start_min    = float(rec["start_offset_min"])
            duration_min = float(rec["duration_min"])
        elif all(k in rec for k in ("start_time", "finish_time")) and pipeline_start:
            try:
                st = datetime.fromisoformat(rec["start_time"].replace("Z", "+00:00"))
                et = datetime.fromisoformat(rec["finish_time"].replace("Z", "+00:00"))
                start_min    = (st - pipeline_start).total_seconds() / 60.0
                duration_min = (et - st).total_seconds() / 60.0
            except ValueError:
                continue
        else:
            continue

        out.append({
            "step_id":    step_id,
            "start_min":  max(0.0, start_min),
            "duration_min": max(0.1, duration_min),
            "status":     status,
            "bottleneck": is_bottle,
            "section":    rec.get("section", section),
        })
    return out


def _resolve_steps(data_file: Path | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    """
    Return (ingest_steps, build_steps, loaded_from_file).
    Falls back to defaults when no valid file data is found.
    """
    if data_file and data_file.exists():
        try:
            raw: dict[str, Any] = json.loads(data_file.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Cannot read %s — %s", data_file, exc)
            raw = {}

        ingest_records = raw.get("ingest", [])
        build_records  = raw.get("steps", [])

        ingest = _parse_records(ingest_records, "ingest") if ingest_records else []
        build  = _parse_records(build_records,  "build")  if build_records  else []

        if ingest or build:
            logger.info(
                "Loaded %d ingest + %d build steps from %s",
                len(ingest), len(build), data_file,
            )
            return (
                ingest or list(_DEFAULT_INGEST),
                build  or list(_DEFAULT_BUILD),
                True,
            )

    logger.info("No run data — using hardcoded estimates.")
    return list(_DEFAULT_INGEST), list(_DEFAULT_BUILD), False


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
    ingest_steps: list[dict[str, Any]],
    build_steps: list[dict[str, Any]],
    from_file: bool = False,
    total_min: int = 90,
) -> None:
    all_steps = ingest_steps + build_steps
    label_w   = max(len(s["step_id"]) for s in all_steps) + 2
    divider   = "=" * (label_w + total_min + 10)
    source    = "build_run.json" if from_file else "hardcoded estimates"

    def _row(step: dict[str, Any]) -> str:
        start  = int(round(step["start_min"]))
        dur    = max(1, int(round(step["duration_min"])))
        suffix = "  ← bottleneck" if step.get("bottleneck") else ""
        bar    = " " * start + "[" + "=" * dur + "]"
        return f"{step['step_id']:<{label_w}}| {bar}{suffix}"

    def _wall(steps: list[dict[str, Any]]) -> float:
        return max(s["start_min"] + s["duration_min"] for s in steps)

    print()
    print(divider)
    print("F1 Strategy Optimizer — Full Pipeline (Gantt)")
    print(f"Source: {source}")
    print(divider)
    print(f"{'Step':<{label_w}}| {_tick_header(total_min)} min")

    sep = "-" * label_w + "+" + "-" * (total_min + 6)
    print(sep)
    print(f"{'── INGEST PIPELINE (Cloud Run Job)':<{label_w}}|")
    print(sep)
    for s in ingest_steps:
        print(_row(s))
    iwall = _wall(ingest_steps)
    print(sep)
    print(f"{'Wall-clock (ingest)':<{label_w}}| {iwall:.1f} min  (9 tasks parallel)")

    print(sep)
    print(f"{'── CLOUD BUILD PIPELINE':<{label_w}}|")
    print(sep)
    for s in build_steps:
        print(_row(s))
    bwall = _wall(build_steps)
    bseq  = sum(s["duration_min"] for s in build_steps)
    print(sep)
    print(f"{'Wall-clock (build)':<{label_w}}| {bwall:.1f} min  (saved {bseq - bwall:.1f} min vs {bseq:.1f} sequential)")
    print(divider)
    print()


# ── Matplotlib PNG ────────────────────────────────────────────────────────────


def generate_png_gantt(
    ingest_steps: list[dict[str, Any]],
    build_steps: list[dict[str, Any]],
    output_path: Path,
    from_file: bool = False,
) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.patches as mpatches
        import matplotlib.pyplot as plt
        import matplotlib.ticker as ticker
    except ImportError:
        logger.warning("matplotlib not installed — pip install 'matplotlib>=3.7.0'")
        return False

    all_steps = ingest_steps + build_steps
    n_ingest  = len(ingest_steps)
    n_build   = len(build_steps)
    n_total   = n_ingest + n_build + 1  # +1 for the divider row

    fig, ax = plt.subplots(figsize=(16, max(6.0, n_total * 0.62 + 2.5)))

    yticks:  list[int] = []
    ylabels: list[str] = []

    def _render_steps(steps: list[dict[str, Any]], y_offset: int) -> None:
        for i, step in enumerate(steps):
            y         = y_offset + i
            start     = step["start_min"]
            dur       = step["duration_min"]
            status    = step.get("status", "SUCCESS")
            is_bottle = step.get("bottleneck", False)

            color = (
                _STATUS_COLORS["bottleneck"]
                if is_bottle
                else _STATUS_COLORS.get(status, _STATUS_COLORS["SUCCESS"])
            )

            ax.broken_barh(
                [(start, dur)], (y - 0.38, 0.76),
                facecolors=color, edgecolors="#2c3e50", linewidth=0.6,
            )
            if dur >= 1.5:
                ax.text(
                    start + dur / 2, y, f"{dur:.0f}m",
                    ha="center", va="center",
                    fontsize=8, color="white", fontweight="bold",
                )
            if is_bottle:
                ax.annotate(
                    "← bottleneck",
                    xy=(start + dur, y), xytext=(start + dur + 0.8, y),
                    fontsize=8, color=_STATUS_COLORS["bottleneck"],
                    va="center", fontweight="bold",
                )
            yticks.append(y)
            ylabels.append(step["step_id"])

    # Section background spans
    def _bg(y_start: float, y_end: float, color: str) -> None:
        ax.axhspan(y_start, y_end, facecolor=color, alpha=0.25, zorder=0)

    # ── Ingest section ────────────────────────────────────────────────────────
    _bg(-0.6, n_ingest - 0.4, _SECTION_BG["ingest"])
    _render_steps(ingest_steps, y_offset=0)

    # Section label (left margin)
    ax.text(
        -7, (n_ingest - 1) / 2,
        "INGEST\nPIPELINE",
        ha="center", va="center", fontsize=8, fontweight="bold",
        color=_SECTION_HEADER["ingest"], rotation=90,
    )

    # Bracket for parallel ingest tasks (all start at 0)
    ax.annotate("", xy=(-2.5, -0.45), xytext=(-2.5, n_ingest - 0.55),
                arrowprops=dict(arrowstyle="-", color=_SECTION_HEADER["ingest"], lw=2.0))
    ax.text(-3.5, (n_ingest - 1) / 2, "parallel",
            ha="right", va="center", fontsize=7.5,
            color=_SECTION_HEADER["ingest"], rotation=90)

    # Divider line
    div_y = n_ingest + 0.1
    ax.axhline(div_y, color="#7f8c8d", linewidth=1.5, linestyle="--", zorder=3)
    ax.text(0, div_y + 0.05, "  CLOUD BUILD PIPELINE",
            fontsize=8.5, fontweight="bold", color=_SECTION_HEADER["build"],
            va="bottom", zorder=4)

    # ── Build section ─────────────────────────────────────────────────────────
    build_y0 = n_ingest + 1
    _bg(n_ingest + 0.6, n_ingest + 1 + n_build - 0.4, _SECTION_BG["build"])
    _render_steps(build_steps, y_offset=build_y0)

    ax.text(
        -7, build_y0 + (n_build - 1) / 2,
        "CLOUD\nBUILD",
        ha="center", va="center", fontsize=8, fontweight="bold",
        color=_SECTION_HEADER["build"], rotation=90,
    )

    # ── Axes ──────────────────────────────────────────────────────────────────
    wall = max(s["start_min"] + s["duration_min"] for s in all_steps)
    x_max = max(95.0, wall * 1.18)
    ax.set_xlim(-9, x_max)
    ax.set_ylim(-0.8, n_total + 0.4)
    ax.invert_yaxis()
    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels, fontsize=9)
    ax.set_xlabel("Time (minutes from pipeline start)", fontsize=10)
    ax.xaxis.set_major_locator(ticker.MultipleLocator(10))
    ax.xaxis.set_minor_locator(ticker.MultipleLocator(5))
    ax.grid(axis="x", which="major", linestyle="--", alpha=0.35, color="#95a5a6")
    ax.grid(axis="x", which="minor", linestyle=":",  alpha=0.20, color="#bdc3c7")

    # Wall-clock lines per section
    i_wall = max(s["start_min"] + s["duration_min"] for s in ingest_steps)
    b_wall = max(s["start_min"] + s["duration_min"] for s in build_steps)
    ax.axvline(i_wall, color=_SECTION_HEADER["ingest"], linestyle=":", alpha=0.6, lw=1.2)
    ax.text(i_wall + 0.4, n_ingest - 1 + 0.3, f"{i_wall:.0f}m",
            fontsize=7.5, color=_SECTION_HEADER["ingest"])
    ax.axvline(b_wall, color=_SECTION_HEADER["build"], linestyle=":", alpha=0.6, lw=1.2)
    ax.text(b_wall + 0.4, build_y0 + n_build - 1 + 0.3, f"{b_wall:.0f}m",
            fontsize=7.5, color=_SECTION_HEADER["build"])

    # ── Legend ────────────────────────────────────────────────────────────────
    legend_items = [
        mpatches.Patch(facecolor=_STATUS_COLORS["SUCCESS"],    edgecolor="#2c3e50", label="SUCCESS"),
        mpatches.Patch(facecolor=_STATUS_COLORS["bottleneck"], edgecolor="#2c3e50", label="Bottleneck"),
        mpatches.Patch(facecolor=_STATUS_COLORS["FAILURE"],    edgecolor="#2c3e50", label="FAILURE"),
        mpatches.Patch(facecolor=_STATUS_COLORS["TIMEOUT"],    edgecolor="#2c3e50", label="TIMEOUT"),
        mpatches.Patch(facecolor=_SECTION_BG["ingest"], edgecolor=_SECTION_HEADER["ingest"],
                       alpha=0.6, label="Ingest section"),
        mpatches.Patch(facecolor=_SECTION_BG["build"],  edgecolor=_SECTION_HEADER["build"],
                       alpha=0.6, label="Cloud Build section"),
    ]
    ax.legend(handles=legend_items, loc="lower right", fontsize=8.5, framealpha=0.9)

    subtitle = "sourced from build_run.json" if from_file else "estimated from observed durations"
    ax.set_title(
        f"F1 Strategy Optimizer — Full Pipeline (Gantt)\n({subtitle})",
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
        description="Gantt chart for the F1 Strategy Optimizer pipelines.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--data-file", default=str(DEFAULT_RUNS_FILE),
                        help=f"Path to build_run.json (default: {DEFAULT_RUNS_FILE})")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT),
                        help=f"PNG output path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--ascii-only", action="store_true",
                        help="Print ASCII chart only; skip PNG")
    parser.add_argument("--fetch-build", metavar="BUILD_ID",
                        help="Fetch real Cloud Build step timings from gcloud")
    parser.add_argument("--project", default="f1optimizer")
    parser.add_argument("--region",  default="us-central1")
    args = parser.parse_args()

    if args.fetch_build:
        data = fetch_build_data(args.fetch_build, args.project, args.region)
        if data is None:
            logger.error("Failed to fetch build — falling back to defaults")

    ingest_steps, build_steps, from_file = _resolve_steps(Path(args.data_file))

    print_ascii_gantt(ingest_steps, build_steps, from_file=from_file)

    if args.ascii_only:
        return 0

    ok = generate_png_gantt(ingest_steps, build_steps, Path(args.output), from_file=from_file)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
