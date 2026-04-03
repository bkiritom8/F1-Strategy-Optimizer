"""
SSE frame builder and async generator for simulation streaming.

Reads lap frames from Redis list and yields SSE-formatted strings.
Polls until status == 'complete' and all frames are consumed.
"""

import asyncio
import json
import logging
from typing import AsyncGenerator

from src.simulation.coordinator import SimulationCoordinator

logger = logging.getLogger(__name__)

POLL_INTERVAL_S = 0.2  # seconds between Redis polls


def build_sse_line(event: str, frame: dict) -> str:
    """Return a single SSE data line with event type merged into payload."""
    payload = {"event": event, **frame}
    return f"data: {json.dumps(payload)}\n\n"


async def frames_to_sse(
    job_id: str,
    coordinator: SimulationCoordinator,
    timeout_s: float = 120.0,
) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE strings for each lap frame.

    Polls Redis list sim:frames:{job_id} until sim:status:{job_id} == 'complete'
    and all frames have been consumed.
    """
    offset = 0
    elapsed = 0.0

    while elapsed < timeout_s:
        frames = coordinator.get_frames_from(job_id, offset)

        for frame in frames:
            frame_type = frame.get("type", "lap")
            event = "sim_complete" if frame_type == "complete" else "sim_lap"
            yield build_sse_line(event, frame)
            offset += 1

        status = coordinator.get_status(job_id)
        if status == "complete" and not frames:
            # All frames consumed and simulation done
            yield build_sse_line("done", {"event": "done"})
            return

        if status == "error":
            yield build_sse_line(
                "error", {"event": "error", "message": "Simulation failed"}
            )
            return

        await asyncio.sleep(POLL_INTERVAL_S)
        elapsed += POLL_INTERVAL_S

    yield build_sse_line("error", {"event": "error", "message": "Simulation timed out"})
