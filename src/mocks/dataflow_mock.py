"""
dataflow_mock.py — Local mock server for GCP Dataflow API.

LOCAL DEVELOPMENT ONLY. Not deployed to GCP.

Simulates the subset of Dataflow REST API endpoints used by this project:
  GET  /v1b3/projects/{project}/jobs          list jobs
  POST /v1b3/projects/{project}/jobs          create job
  GET  /v1b3/projects/{project}/jobs/{id}     get job status
  PUT  /v1b3/projects/{project}/jobs/{id}     update/cancel job

Runs on port 8088 by default (set PORT env var to override).

Usage:
  python src/mocks/dataflow_mock.py
  # or via docker-compose:
  docker-compose -f docker-compose.f1.yml up mock-dataflow
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("dataflow_mock")

app = FastAPI(
    title="Dataflow Mock API",
    description="Local mock for GCP Dataflow REST API (development only)",
    version="1.0.0",
)

# In-memory job store
_jobs: Dict[str, Dict[str, Any]] = {}

_JOB_STATES = ["JOB_STATE_QUEUED", "JOB_STATE_RUNNING", "JOB_STATE_DONE"]


def _make_job(project: str, request_body: Dict[str, Any]) -> Dict[str, Any]:
    job_id = str(uuid.uuid4())[:8]
    now = int(time.time())
    return {
        "id": job_id,
        "projectId": project,
        "name": request_body.get("name", f"mock-job-{job_id}"),
        "type": request_body.get("type", "JOB_TYPE_BATCH"),
        "currentState": "JOB_STATE_QUEUED",
        "currentStateTime": str(now),
        "createTime": str(now),
        "environment": request_body.get("environment", {}),
        "labels": request_body.get("labels", {}),
    }


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "dataflow-mock"}


@app.get("/v1b3/projects/{project}/jobs")
def list_jobs(project: str) -> Dict[str, Any]:
    jobs = [j for j in _jobs.values() if j["projectId"] == project]
    logger.info("list_jobs project=%s → %d jobs", project, len(jobs))
    return {"jobs": jobs}


@app.post("/v1b3/projects/{project}/jobs")
def create_job(project: str, body: Dict[str, Any]) -> Dict[str, Any]:
    job = _make_job(project, body)
    _jobs[job["id"]] = job
    logger.info(
        "create_job project=%s name=%s → id=%s", project, job["name"], job["id"]
    )
    return job


@app.get("/v1b3/projects/{project}/jobs/{job_id}")
def get_job(project: str, job_id: str) -> Dict[str, Any]:
    job = _jobs.get(job_id)
    if job is None or job["projectId"] != project:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    # Auto-advance state for realistic simulation
    state_idx = _JOB_STATES.index(job["currentState"])
    if state_idx < len(_JOB_STATES) - 1:
        job["currentState"] = _JOB_STATES[state_idx + 1]
    logger.info("get_job id=%s → state=%s", job_id, job["currentState"])
    return job


@app.put("/v1b3/projects/{project}/jobs/{job_id}")
def update_job(project: str, job_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    job = _jobs.get(job_id)
    if job is None or job["projectId"] != project:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    new_state = body.get("currentState")
    if new_state:
        job["currentState"] = new_state
    logger.info("update_job id=%s → state=%s", job_id, job["currentState"])
    return job


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8088"))
    logger.info("Starting Dataflow mock on port %d", port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
