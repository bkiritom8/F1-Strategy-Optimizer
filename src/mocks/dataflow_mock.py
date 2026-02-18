"""
Mock Dataflow service for local development and testing.
Provides synchronous Apache Beam pipeline execution.
"""

import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from prometheus_client import Counter, Gauge, Histogram, generate_latest
from prometheus_client import CONTENT_TYPE_LATEST

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Prometheus metrics
JOB_COUNTER = Counter(
    "dataflow_mock_jobs_total", "Total number of Dataflow jobs", ["status"]
)
JOB_DURATION = Histogram(
    "dataflow_mock_job_duration_seconds", "Job execution duration", ["job_type"]
)
ACTIVE_JOBS = Gauge("dataflow_mock_active_jobs", "Number of currently active jobs")
ELEMENTS_PROCESSED = Counter(
    "dataflow_mock_elements_processed_total",
    "Total number of elements processed",
    ["pipeline"],
)

# Initialize FastAPI app
app = FastAPI(
    title="Mock Dataflow Service",
    description="Local Apache Beam pipeline executor for F1 Strategy Optimizer",
    version="1.0.0",
)


class JobState(str, Enum):
    """Dataflow job states"""

    PENDING = "JOB_STATE_PENDING"
    RUNNING = "JOB_STATE_RUNNING"
    DONE = "JOB_STATE_DONE"
    FAILED = "JOB_STATE_FAILED"
    CANCELLED = "JOB_STATE_CANCELLED"


class PipelineOptions(BaseModel):
    """Pipeline execution options"""

    project: str
    region: str = "us-central1"
    runner: str = "DirectRunner"
    temp_location: Optional[str] = None
    staging_location: Optional[str] = None
    max_num_workers: int = 1
    machine_type: str = "n1-standard-1"


class LaunchTemplateRequest(BaseModel):
    """Request to launch a Dataflow template"""

    job_name: str
    template_path: str
    parameters: Dict[str, Any]
    environment: Optional[Dict[str, Any]] = None


class JobMetrics(BaseModel):
    """Job execution metrics"""

    elements_read: int = 0
    elements_written: int = 0
    total_vcpu_time: float = 0.0
    total_memory_usage: float = 0.0
    data_watermark: Optional[str] = None


class DataflowJob(BaseModel):
    """Dataflow job representation"""

    id: str
    name: str
    project_id: str
    type: str
    current_state: JobState
    create_time: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    location: str
    metrics: Optional[JobMetrics] = None
    error: Optional[str] = None


class MockDataflowService:
    """Mock Dataflow service implementation"""

    def __init__(self):
        self.jobs: Dict[str, DataflowJob] = {}
        logger.info("Mock Dataflow service initialized")

    def create_job(
        self, name: str, project_id: str, location: str, pipeline_type: str
    ) -> DataflowJob:
        """Create a new Dataflow job"""
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        create_time = datetime.utcnow().isoformat() + "Z"

        job = DataflowJob(
            id=job_id,
            name=name,
            project_id=project_id,
            type=pipeline_type,
            current_state=JobState.PENDING,
            create_time=create_time,
            location=location,
            metrics=JobMetrics(),
        )

        self.jobs[job_id] = job
        ACTIVE_JOBS.inc()
        JOB_COUNTER.labels(status="created").inc()

        logger.info(f"Created job {job_id}: {name}")
        return job

    def run_job(self, job_id: str, pipeline_func: Callable[[], Any]) -> DataflowJob:
        """Execute a Dataflow job"""
        if job_id not in self.jobs:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        job = self.jobs[job_id]
        job.current_state = JobState.RUNNING
        job.start_time = datetime.utcnow().isoformat() + "Z"

        try:
            with JOB_DURATION.labels(job_type=job.type).time():
                # Execute pipeline function (synchronous for mock)
                result = pipeline_func()

                # Update metrics
                if isinstance(result, dict) and job.metrics is not None:
                    job.metrics.elements_read = result.get("elements_read", 0)
                    job.metrics.elements_written = result.get("elements_written", 0)

                    ELEMENTS_PROCESSED.labels(pipeline=job.name).inc(
                        job.metrics.elements_written
                    )

            job.current_state = JobState.DONE
            job.end_time = datetime.utcnow().isoformat() + "Z"
            JOB_COUNTER.labels(status="success").inc()

            logger.info(f"Job {job_id} completed successfully")

        except Exception as e:
            job.current_state = JobState.FAILED
            job.end_time = datetime.utcnow().isoformat() + "Z"
            job.error = str(e)
            JOB_COUNTER.labels(status="failed").inc()

            logger.error(f"Job {job_id} failed: {e}")

        finally:
            ACTIVE_JOBS.dec()

        return job

    def get_job(self, job_id: str) -> DataflowJob:
        """Get job by ID"""
        if job_id not in self.jobs:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
        return self.jobs[job_id]

    def list_jobs(
        self,
        project_id: str,
        location: str = "us-central1",
        filter_state: Optional[JobState] = None,
    ) -> List[DataflowJob]:
        """List all jobs"""
        jobs = [
            job
            for job in self.jobs.values()
            if job.project_id == project_id and job.location == location
        ]

        if filter_state:
            jobs = [job for job in jobs if job.current_state == filter_state]

        return jobs

    def cancel_job(self, job_id: str) -> DataflowJob:
        """Cancel a running job"""
        job = self.get_job(job_id)

        if job.current_state == JobState.RUNNING:
            job.current_state = JobState.CANCELLED
            job.end_time = datetime.utcnow().isoformat() + "Z"
            ACTIVE_JOBS.dec()
            JOB_COUNTER.labels(status="cancelled").inc()

            logger.info(f"Job {job_id} cancelled")

        return job


# Simulated pipeline functions
def validation_pipeline(data: List[Dict[str, Any]]) -> Dict[str, int]:
    """Simulate data validation pipeline"""
    valid_count = 0
    invalid_count = 0

    for record in data:
        # Simple validation logic
        if all(key in record for key in ["race_id", "driver_id"]):
            valid_count += 1
        else:
            invalid_count += 1

    logger.info(f"Validation complete: {valid_count} valid, {invalid_count} invalid")

    return {"elements_read": len(data), "elements_written": valid_count}


def enrichment_pipeline(data: List[Dict[str, Any]]) -> Dict[str, int]:
    """Simulate data enrichment pipeline"""
    enriched = []

    for record in data:
        # Add computed features
        enriched_record = record.copy()
        enriched_record["enriched_at"] = datetime.utcnow().isoformat()
        enriched_record["version"] = "1.0"
        enriched.append(enriched_record)

    logger.info(f"Enrichment complete: {len(enriched)} records")

    return {"elements_read": len(data), "elements_written": len(enriched)}


# Initialize service
mock_service = MockDataflowService()


@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("Mock Dataflow service started successfully")


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "mock-dataflow",
        "active_jobs": len(
            [
                j
                for j in mock_service.jobs.values()
                if j.current_state == JobState.RUNNING
            ]
        ),
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/jobs", response_model=DataflowJob)
async def create_job(request: LaunchTemplateRequest):
    """Create and launch a Dataflow job"""
    try:
        # Extract parameters
        project_id = request.parameters.get("project", "local-dev")
        location = request.parameters.get("region", "us-central1")
        pipeline_type = request.parameters.get("pipeline_type", "batch")

        # Create job
        job = mock_service.create_job(
            name=request.job_name,
            project_id=project_id,
            location=location,
            pipeline_type=pipeline_type,
        )

        # Determine pipeline function based on template
        if "validation" in request.template_path.lower():

            def pipeline_func():
                return validation_pipeline(request.parameters.get("input_data", []))

        elif "enrichment" in request.template_path.lower():

            def pipeline_func():
                return enrichment_pipeline(request.parameters.get("input_data", []))

        else:

            def pipeline_func():
                return {"elements_read": 0, "elements_written": 0}

        # Run job (synchronous for mock)
        job = mock_service.run_job(job.id, pipeline_func)

        return job

    except Exception as e:
        logger.error(f"Job creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}", response_model=DataflowJob)
async def get_job(job_id: str):
    """Get job status"""
    return mock_service.get_job(job_id)


@app.get("/jobs", response_model=List[DataflowJob])
async def list_jobs(
    project_id: str = "local-dev",
    location: str = "us-central1",
    filter_state: Optional[JobState] = None,
):
    """List all jobs"""
    return mock_service.list_jobs(project_id, location, filter_state)


@app.post("/jobs/{job_id}/cancel", response_model=DataflowJob)
async def cancel_job(job_id: str):
    """Cancel a running job"""
    return mock_service.cancel_job(job_id)


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return JSONResponse(
        content=generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST
    )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Mock Dataflow",
        "version": "1.0.0",
        "status": "running",
        "active_jobs": len(
            [
                j
                for j in mock_service.jobs.values()
                if j.current_state == JobState.RUNNING
            ]
        ),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=9051)
