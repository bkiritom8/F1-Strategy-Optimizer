# Distributed Training Pipeline Infrastructure

**Last Updated**: 2026-02-14

## Overview

The F1 Strategy Optimizer training pipeline executes ML model training as isolated, containerized stages within the DAG-based orchestration layer. Training jobs are horizontally scalable, fault-tolerant, and secured with least-privilege access controls.

**Key Principles**:
- Training is a DAG node, not a separate system
- Container-native execution (framework-agnostic)
- Reads from processed storage only
- Writes artifacts to dedicated storage
- Integrated with DAG orchestrator
- Hardware-agnostic (CPU/GPU abstracted)
- Centralized pipeline logging

---

## DAG Integration

### Training as DAG Nodes

Training jobs are defined as nodes in the pipeline DAG with explicit dependencies on data preparation stages. Each model training task is a separate DAG node, enabling parallel training of multiple models.

**Training DAG Structure**:
```
┌─────────────────────────────────────────────────────────┐
│ Training Pipeline DAG                                   │
│                                                         │
│  ┌──────────────┐                                      │
│  │ Data Splits  │  (Dependency from data pipeline)     │
│  │   Ready      │                                      │
│  └──────┬───────┘                                      │
│         │                                               │
│         ▼                                               │
│  ┌──────────────┐                                      │
│  │  Validate    │                                      │
│  │ Training Data│                                      │
│  └──────┬───────┘                                      │
│         │                                               │
│         └───────┬─────────┬─────────┬─────────┐        │
│                 ▼         ▼         ▼         ▼        │
│          ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐│
│          │  Train  │ │  Train  │ │  Train  │ │  Train  ││
│          │  Tire   │ │  Fuel   │ │  Brake  │ │ Driving ││
│          │  Deg    │ │  Cons   │ │  Bias   │ │  Style  ││
│          └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘│
│               │           │           │           │      │
│               └───────────┼───────────┼───────────┘      │
│                           ▼           ▼                  │
│                    ┌──────────┐ ┌──────────┐            │
│                    │ Evaluate │ │ Register │            │
│                    │  Models  │ │  Models  │            │
│                    └──────────┘ └──────────┘            │
└─────────────────────────────────────────────────────────┘
```

**Parallel Execution**: The 4 model training tasks (Tire Degradation, Fuel Consumption, Brake Bias, Driving Style) run in parallel since they have no inter-dependencies, maximizing throughput.

**Non-Blocking Design**: Training DAG runs independently and does not block:
- Real-time inference pipelines
- Streaming data ingestion (Dataflow)
- Dashboard queries
- Other pipeline stages

### Training DAG Definition

**File**: `pipeline/orchestrator/dag_definitions/training_pipeline.yaml`

```yaml
dag_id: f1_training_pipeline
description: Distributed training for F1 strategy models
schedule: "0 2 * * 1"  # Every Monday at 2:00 AM UTC (after data pipeline)
depends_on: [f1_data_pipeline]  # Wait for data pipeline completion

tasks:
  - task_id: validate_training_data
    container: gcr.io/f1-strategy/data-validator:latest
    command: ["python", "pipeline/training/validate.py", "--split=train"]
    dependencies: []
    timeout: 300
    retries: 1

  - task_id: train_tire_degradation
    container: gcr.io/f1-strategy/training-worker:latest
    command:
      - python
      - -m
      - training.worker
      - --model-type=tire_degradation
      - --num-workers=4
    dependencies: [validate_training_data]
    timeout: 14400  # 4 hours
    retries: 2
    resources:
      cpu: 16
      memory: 64Gi

  - task_id: train_fuel_consumption
    container: gcr.io/f1-strategy/training-worker:latest
    command:
      - python
      - -m
      - training.worker
      - --model-type=fuel_consumption
      - --num-workers=4
    dependencies: [validate_training_data]
    timeout: 14400  # 4 hours
    retries: 2
    resources:
      cpu: 16
      memory: 64Gi

  - task_id: train_brake_bias
    container: gcr.io/f1-strategy/training-worker:latest
    command:
      - python
      - -m
      - training.worker
      - --model-type=brake_bias
      - --num-workers=2
    dependencies: [validate_training_data]
    timeout: 7200  # 2 hours
    retries: 2
    resources:
      cpu: 8
      memory: 32Gi

  - task_id: train_driving_style
    container: gcr.io/f1-strategy/training-worker:latest
    command:
      - python
      - -m
      - training.worker
      - --model-type=driving_style
      - --num-workers=4
    dependencies: [validate_training_data]
    timeout: 10800  # 3 hours
    retries: 2
    resources:
      cpu: 16
      memory: 64Gi

  - task_id: evaluate_models
    container: gcr.io/f1-strategy/evaluator:latest
    command: ["python", "models/evaluate.py", "--split=test"]
    dependencies:
      - train_tire_degradation
      - train_fuel_consumption
      - train_brake_bias
      - train_driving_style
    timeout: 1800  # 30 minutes
    retries: 1

  - task_id: register_models
    container: gcr.io/f1-strategy/model-registry:latest
    command: ["python", "models/register.py"]
    dependencies: [evaluate_models]
    timeout: 600  # 10 minutes
    retries: 2

on_failure:
  action: notify
  channels: [slack, pagerduty]
  message: "Training pipeline failed"

on_success:
  action: log
  message: "Training pipeline completed successfully"
```

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────┐
│ DAG Orchestrator (Containerized)                       │
│                                                        │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐          │
│  │ Ingest   │──>│ Process  │──>│ Validate │          │
│  │  (DAG)   │   │  (DAG)   │   │  (DAG)   │          │
│  └──────────┘   └──────────┘   └──────────┘          │
│                                      │                 │
│                                      ▼                 │
│                            ┌──────────────────┐       │
│                            │ Training (DAG)   │       │
│                            │  (Distributed)   │       │
│                            └──────────────────┘       │
│                                      │                 │
│                                      ▼                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐          │
│  │ Evaluate │──>│ Register │──>│  Serve   │          │
│  │  (DAG)   │   │  (DAG)   │   │  (DAG)   │          │
│  └──────────┘   └──────────┘   └──────────┘          │
└────────────────────────────────────────────────────────┘
```

---

## Container-Native Execution

### Training Worker Container

**Base Image**:
```dockerfile
# Dockerfile.training-worker
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages (framework-agnostic base)
COPY requirements-training.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements-training.txt

# Copy training code
COPY pipeline/training/ /app/training/
COPY models/ /app/models/

WORKDIR /app

# Entrypoint
ENTRYPOINT ["python", "-m", "training.worker"]
```

**Container Registry**:
- **Location**: Google Container Registry (GCR)
- **Image**: `gcr.io/f1-strategy/training-worker:latest`
- **Versioning**: Semantic versioning (v1.0.0, v1.1.0, etc.)
- **Tagging**: Git commit SHA for traceability

**Container Configuration**:
```yaml
container:
  image: gcr.io/f1-strategy/training-worker:v1.0.0
  command: ["python", "-m", "training.worker"]
  args:
    - --model-type=tire_degradation
    - --data-split=train
    - --output-uri=gs://f1-strategy-artifacts/models/

  env:
    - name: GOOGLE_CLOUD_PROJECT
      value: f1-strategy
    - name: TRAINING_JOB_ID
      value: "${JOB_ID}"
    - name: WORKER_INDEX
      value: "${WORKER_INDEX}"
    - name: TOTAL_WORKERS
      value: "${TOTAL_WORKERS}"

  resources:
    requests:
      cpu: "4"
      memory: "16Gi"
    limits:
      cpu: "8"
      memory: "32Gi"
```

---

## Distributed Training Architecture

### Horizontal Scaling

**Worker Pool Configuration**:
- **Minimum Workers**: 1 (single-node training for small models)
- **Maximum Workers**: 10 (distributed training for large models)
- **Default Workers**: 4 (cost-effective for typical training)
- **Scaling Policy**: Manual specification per job (not auto-scaled during training)

**Worker Coordination**:
```
┌─────────────────────────────────────────────────┐
│ Distributed Training Job                       │
│                                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ Worker 0 │  │ Worker 1 │  │ Worker 2 │     │
│  │ (Chief)  │  │          │  │          │     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
│       │             │             │            │
│       └─────────────┼─────────────┘            │
│              HTTPS/TLS 1.3                     │
│             (Encrypted Transport)              │
│                                                 │
│  Data Sharding: Each worker processes subset   │
│  Model Sync: Parameter updates via secure RPC  │
│  Checkpoints: Coordinated write to GCS         │
└─────────────────────────────────────────────────┘
```

**Inter-Worker Communication**:
- **Protocol**: gRPC over HTTPS/TLS 1.3
- **Network**: Internal VPC only (no public internet)
- **Encryption**: All traffic encrypted end-to-end
- **Service Discovery**: Kubernetes DNS or Vertex AI internal service mesh

**Data Sharding Strategy**:
```python
# Example: Each worker processes a shard of the training data
def get_data_shard(worker_index: int, total_workers: int, dataset: str):
    """Shard data across workers for distributed training."""

    query = f"""
        SELECT *
        FROM f1_strategy.{dataset}
        WHERE MOD(ABS(FARM_FINGERPRINT(CAST(race_id AS STRING))), {total_workers}) = {worker_index}
    """

    # Each worker reads only its shard from BigQuery
    df = bq_client.query(query).to_dataframe()
    return df
```

**Fault Tolerance**:
- **Worker Failure**: Job continues if <50% workers fail
- **Chief Worker Failure**: Job restarts from last checkpoint
- **Network Partition**: Job paused, retried after 5 minutes
- **Checkpoint Frequency**: Every 10 minutes or 1000 iterations

---

## Infrastructure Provisioning (Terraform)

### Compute Resources

**File**: `infrastructure/terraform/training.tf`

```hcl
# Training compute resource pool
resource "google_compute_region_instance_group_manager" "training_workers" {
  name               = "f1-training-workers"
  base_instance_name = "training-worker"
  region             = var.region

  version {
    instance_template = google_compute_instance_template.training_worker.id
  }

  target_size = 0  # Scale to zero by default

  auto_healing_policies {
    health_check      = google_compute_health_check.training_worker.id
    initial_delay_sec = 300
  }
}

# Instance template for training workers
resource "google_compute_instance_template" "training_worker" {
  name         = "f1-training-worker-template-v1"
  machine_type = var.training_machine_type

  disk {
    source_image = "cos-cloud/cos-stable"
    auto_delete  = true
    boot         = true
    disk_size_gb = 100
  }

  # Additional disk for model checkpoints (optional)
  disk {
    auto_delete  = true
    boot         = false
    disk_size_gb = 200
    type         = "pd-ssd"
  }

  network_interface {
    network    = google_compute_network.training_vpc.id
    subnetwork = google_compute_subnetwork.training_subnet.id
    # No external IP - internal only
  }

  service_account {
    email  = google_service_account.training_worker.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    google-logging-enabled = "true"
    container-vm           = module.training_container.metadata
  }

  tags = ["training-worker", "no-internet"]
}

# Autoscaler (manual trigger, not auto-scaling during training)
resource "google_compute_region_autoscaler" "training_workers" {
  name   = "f1-training-autoscaler"
  region = var.region
  target = google_compute_region_instance_group_manager.training_workers.id

  autoscaling_policy {
    min_replicas = 0
    max_replicas = var.max_training_workers

    # Scale based on custom metric (jobs in queue)
    metric {
      name   = "custom.googleapis.com/training/jobs_queued"
      target = 1
      type   = "GAUGE"
    }

    scale_in_control {
      max_scaled_in_replicas {
        fixed = 2
      }
      time_window_sec = 600
    }
  }
}

# Health check
resource "google_compute_health_check" "training_worker" {
  name               = "training-worker-health"
  check_interval_sec = 60
  timeout_sec        = 30

  http_health_check {
    port         = 8080
    request_path = "/health"
  }
}
```

### Storage Resources

**File**: `infrastructure/terraform/storage.tf`

```hcl
# GCS bucket for training artifacts
resource "google_storage_bucket" "training_artifacts" {
  name          = "f1-strategy-artifacts"
  location      = var.region
  storage_class = "STANDARD"

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 90  # Delete artifacts older than 90 days
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      age = 30
      matches_storage_class = ["STANDARD"]
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  encryption {
    default_kms_key_name = google_kms_crypto_key.artifact_encryption.id
  }
}

# Separate buckets for different artifact types
resource "google_storage_bucket" "model_registry" {
  name          = "f1-strategy-models"
  location      = var.region
  storage_class = "STANDARD"

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket" "training_checkpoints" {
  name          = "f1-strategy-checkpoints"
  location      = var.region
  storage_class = "NEARLINE"  # Cheaper for infrequent access

  lifecycle_rule {
    condition {
      age = 7  # Delete checkpoints after 7 days
    }
    action {
      type = "Delete"
    }
  }
}
```

### IAM and Security

**File**: `infrastructure/terraform/iam.tf`

```hcl
# Training worker service account
resource "google_service_account" "training_worker" {
  account_id   = "training-worker"
  display_name = "F1 Strategy Training Worker"
  description  = "Service account for distributed training jobs"
}

# BigQuery read-only access
resource "google_project_iam_member" "training_bq_viewer" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.training_worker.email}"

  condition {
    title      = "training-data-only"
    expression = "resource.name.startsWith('projects/${var.project_id}/datasets/f1_strategy')"
  }
}

resource "google_project_iam_member" "training_bq_jobuser" {
  project = var.project_id
  role    = "roles/bigquery.jobUser"
  member  = "serviceAccount:${google_service_account.training_worker.email}"
}

# GCS write access to artifacts bucket
resource "google_storage_bucket_iam_member" "training_artifacts_writer" {
  bucket = google_storage_bucket.training_artifacts.name
  role   = "roles/storage.objectCreator"
  member = "serviceAccount:${google_service_account.training_worker.email}"
}

resource "google_storage_bucket_iam_member" "training_artifacts_reader" {
  bucket = google_storage_bucket.training_artifacts.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.training_worker.email}"
}

# Vertex AI access
resource "google_project_iam_member" "training_vertex_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.training_worker.email}"
}

# Explicitly deny dangerous permissions
resource "google_project_iam_member" "training_deny_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.training_worker.email}"

  # This is a deny policy (requires Organization Policy)
  condition {
    title      = "deny-data-modification"
    expression = "false"
  }
}
```

### Networking

**File**: `infrastructure/terraform/network.tf`

```hcl
# Dedicated VPC for training workloads
resource "google_compute_network" "training_vpc" {
  name                    = "f1-training-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "training_subnet" {
  name          = "f1-training-subnet"
  ip_cidr_range = "10.10.0.0/16"
  region        = var.region
  network       = google_compute_network.training_vpc.id

  private_ip_google_access = true  # Access GCP APIs without external IP
}

# Firewall: Allow internal traffic between workers
resource "google_compute_firewall" "training_internal" {
  name    = "training-internal-allow"
  network = google_compute_network.training_vpc.name

  allow {
    protocol = "tcp"
    ports    = ["0-65535"]
  }

  allow {
    protocol = "udp"
    ports    = ["0-65535"]
  }

  source_tags = ["training-worker"]
  target_tags = ["training-worker"]
}

# Firewall: Deny all external ingress
resource "google_compute_firewall" "training_deny_external" {
  name     = "training-deny-external"
  network  = google_compute_network.training_vpc.name
  priority = 1000

  deny {
    protocol = "all"
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["no-internet"]
}

# Cloud NAT (optional, for pulling container images)
resource "google_compute_router" "training_router" {
  name    = "f1-training-router"
  region  = var.region
  network = google_compute_network.training_vpc.id
}

resource "google_compute_router_nat" "training_nat" {
  name                               = "f1-training-nat"
  router                             = google_compute_router.training_router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}
```

---

## Orchestration Integration

### Pipeline Definition (Vertex AI Pipelines)

**File**: `pipeline/training/orchestrator.py`

```python
from kfp.v2 import dsl
from kfp.v2.dsl import component, Input, Output, Artifact, Model, Metrics

@component(
    base_image="gcr.io/f1-strategy/data-validator:latest",
    packages_to_install=["google-cloud-bigquery"]
)
def validate_data(split: str, min_completeness: float = 0.95) -> bool:
    """Validate training data quality before training."""
    from google.cloud import bigquery

    client = bigquery.Client()

    # Check data completeness
    query = f"""
        SELECT
            COUNT(*) as total_rows,
            COUNTIF(lap_time_ms IS NULL) as null_laps,
            COUNTIF(tire_age IS NULL) as null_tires
        FROM f1_strategy.{split}
    """

    result = list(client.query(query).result())[0]
    completeness = 1 - (result.null_laps + result.null_tires) / (result.total_rows * 2)

    if completeness < min_completeness:
        raise ValueError(f"Data completeness {completeness:.2%} < {min_completeness:.2%}")

    return True

@component(
    base_image="gcr.io/f1-strategy/training-worker:latest"
)
def train_model(
    model_type: str,
    data_split: str,
    num_workers: int,
    output_model: Output[Model],
    output_metrics: Output[Metrics]
):
    """Execute distributed training job."""
    import os
    from training.worker import DistributedTrainer

    # Initialize trainer
    trainer = DistributedTrainer(
        model_type=model_type,
        data_split=data_split,
        num_workers=num_workers,
        worker_index=int(os.getenv('WORKER_INDEX', '0')),
        job_id=os.getenv('TRAINING_JOB_ID')
    )

    # Train model
    model_uri, metrics = trainer.run()

    # Write outputs
    output_model.uri = model_uri
    output_metrics.log_metric("final_loss", metrics['loss'])
    output_metrics.log_metric("final_accuracy", metrics['accuracy'])

@component(
    base_image="gcr.io/f1-strategy/evaluator:latest"
)
def evaluate_model(
    model: Input[Model],
    test_split: str,
    output_metrics: Output[Metrics]
) -> dict:
    """Evaluate trained model on test set."""
    from evaluation.evaluator import ModelEvaluator

    evaluator = ModelEvaluator(model.uri)
    metrics = evaluator.evaluate(test_split)

    # Log metrics
    for key, value in metrics.items():
        output_metrics.log_metric(key, value)

    return metrics

@dsl.pipeline(
    name='f1-training-pipeline',
    description='Distributed training pipeline for F1 strategy models'
)
def training_pipeline(
    model_type: str,
    data_split: str = 'train',
    num_workers: int = 4,
    test_split: str = 'test'
):
    """Complete training pipeline with validation, training, and evaluation."""

    # Stage 1: Validate data quality
    validation_task = validate_data(
        split=data_split,
        min_completeness=0.95
    )

    # Stage 2: Distributed training
    training_task = train_model(
        model_type=model_type,
        data_split=data_split,
        num_workers=num_workers
    ).after(validation_task)

    # Stage 3: Evaluate on test set
    evaluation_task = evaluate_model(
        model=training_task.outputs['output_model'],
        test_split=test_split
    ).after(training_task)

    # Set resource requirements
    training_task.set_cpu_limit('16')
    training_task.set_memory_limit('64G')
    training_task.set_retry(3)
```

### Job Submission

```python
from google.cloud import aiplatform
from kfp.v2 import compiler

# Compile pipeline
compiler.Compiler().compile(
    pipeline_func=training_pipeline,
    package_path='training_pipeline.json'
)

# Submit to Vertex AI Pipelines
aiplatform.init(
    project='f1-strategy',
    location='us-central1'
)

job = aiplatform.PipelineJob(
    display_name='tire-degradation-training',
    template_path='training_pipeline.json',
    parameter_values={
        'model_type': 'tire_degradation',
        'data_split': 'train',
        'num_workers': 4,
        'test_split': 'test'
    },
    enable_caching=False  # Always retrain
)

job.submit(
    service_account='training-worker@f1-strategy.iam.gserviceaccount.com'
)
```

---

## Failure Handling and Retries

### Retry Policy

```yaml
Retry Configuration:
  max_retries: 3
  retry_on:
    - worker_failure
    - network_timeout
    - resource_exhaustion

  no_retry_on:
    - data_validation_failure
    - permission_denied
    - invalid_configuration

  backoff_policy:
    initial_delay: 60s
    max_delay: 600s
    multiplier: 2.0
```

### Failure Scenarios

**Worker Failure**:
```
Action: Restart failed worker from last checkpoint
Timeout: 5 minutes before retry
Max Retries: 3
Fallback: Reduce num_workers by 1, retry
```

**Chief Worker Failure**:
```
Action: Restart entire job from last checkpoint
Timeout: 10 minutes
Max Retries: 2
Fallback: Notify on-call engineer
```

**Data Validation Failure**:
```
Action: Fail immediately (no retry)
Notification: Alert data team
Logs: Full validation report to Cloud Logging
```

**Out of Memory**:
```
Action: Retry with larger instance type
Instance Upgrade: n1-standard-16 → n1-highmem-16
Max Retries: 1
Fallback: Fail, notify ML team
```

**Network Partition**:
```
Action: Pause job, wait for network recovery
Timeout: 15 minutes
Recovery: Resume from last checkpoint
```

### Checkpoint Management

```python
# Checkpoint every 10 minutes or 1000 iterations
class CheckpointManager:
    def __init__(self, checkpoint_dir: str, frequency_sec: int = 600):
        self.checkpoint_dir = checkpoint_dir
        self.frequency_sec = frequency_sec
        self.last_checkpoint_time = time.time()

    def should_checkpoint(self, iteration: int) -> bool:
        """Check if checkpoint should be saved."""
        elapsed = time.time() - self.last_checkpoint_time

        return (
            iteration % 1000 == 0 or
            elapsed >= self.frequency_sec
        )

    def save(self, model_state: dict, iteration: int):
        """Save checkpoint to GCS."""
        checkpoint_path = f"{self.checkpoint_dir}/checkpoint_{iteration}.ckpt"

        # Save to GCS
        with gcs_client.open(checkpoint_path, 'wb') as f:
            pickle.dump(model_state, f)

        self.last_checkpoint_time = time.time()

    def load_latest(self) -> dict:
        """Load latest checkpoint from GCS."""
        checkpoints = gcs_client.list_blobs(self.checkpoint_dir)
        latest = max(checkpoints, key=lambda x: x.updated)

        with gcs_client.open(latest.name, 'rb') as f:
            return pickle.load(f)
```

---

## Monitoring and Observability

### Cloud Monitoring Metrics

**Job-Level Metrics**:
```yaml
training.job.duration_seconds:
  type: gauge
  labels: [model_type, job_id]
  description: Total training job duration

training.job.status:
  type: gauge
  labels: [model_type, status]  # status: running, succeeded, failed
  description: Training job status

training.job.retry_count:
  type: counter
  labels: [model_type, failure_reason]
  description: Number of job retries
```

**Worker-Level Metrics**:
```yaml
training.worker.cpu_utilization:
  type: gauge
  labels: [job_id, worker_index]
  description: Worker CPU utilization (0-100%)

training.worker.memory_usage_bytes:
  type: gauge
  labels: [job_id, worker_index]
  description: Worker memory usage

training.worker.heartbeat:
  type: gauge
  labels: [job_id, worker_index]
  description: Worker heartbeat timestamp (for liveness check)
```

**Training Progress Metrics**:
```yaml
training.progress.iterations_completed:
  type: counter
  labels: [job_id, model_type]
  description: Training iterations completed

training.progress.records_processed:
  type: counter
  labels: [job_id, worker_index]
  description: Training records processed
```

### Alerting

**File**: `monitoring/alerts.yaml`

```yaml
alerts:
  - name: training-job-timeout
    condition: training.job.duration_seconds > 43200  # 12 hours
    severity: warning
    notification: slack

  - name: training-job-failure-rate
    condition: rate(training.job.status{status="failed"}[1h]) > 0.2
    severity: critical
    notification: pagerduty

  - name: worker-oom
    condition: training.worker.memory_usage_bytes / limits.memory > 0.95
    severity: warning
    action: auto-retry with larger instance

  - name: data-validation-failure
    condition: training.job.status{status="failed", reason="validation"}
    severity: critical
    notification: slack
    action: block future training jobs
```

### Logging

**Structured Logging**:
```python
import logging
from google.cloud import logging as cloud_logging

# Initialize Cloud Logging
logging_client = cloud_logging.Client()
logging_client.setup_logging()

# Structured log entry
logging.info(
    "Training started",
    extra={
        "job_id": os.getenv("TRAINING_JOB_ID"),
        "model_type": "tire_degradation",
        "num_workers": 4,
        "worker_index": 0,
        "data_split": "train"
    }
)
```

**Log Retention**:
- **Training Logs**: 30 days
- **Error Logs**: 90 days
- **Audit Logs**: 1 year

---

## Cost Management

### Budget Allocation

```yaml
Training Budget (Monthly):
  weekly_retraining: $80-120      # 4 models × $20-30 per week
  ad_hoc_experiments: $50         # Manual triggered jobs
  infrastructure: $30             # Storage, networking
  total: $160-200/month
```

### Cost Optimization Strategies

**1. Preemptible VMs**:
```hcl
resource "google_compute_instance_template" "training_worker_preemptible" {
  name         = "training-worker-preemptible"
  machine_type = var.training_machine_type

  scheduling {
    preemptible       = true
    automatic_restart = false
  }

  # 70% cost reduction vs standard VMs
}
```

**2. Scale to Zero**:
- Worker pool scales to 0 when no jobs running
- No cost during idle periods
- Cold start: ~2-3 minutes to provision workers

**3. Storage Lifecycle**:
- Checkpoints deleted after 7 days
- Artifacts moved to Nearline after 30 days
- Old models deleted after 90 days

**4. Resource Right-Sizing**:
```python
# Automatically adjust instance type based on model size
def select_instance_type(model_type: str) -> str:
    INSTANCE_TYPES = {
        'tire_degradation': 'n1-standard-8',   # Medium model
        'fuel_consumption': 'n1-highmem-16',   # Large LSTM model
        'brake_bias': 'n1-standard-4',         # Small linear model
        'driving_style': 'n1-standard-8'       # Medium tree model
    }
    return INSTANCE_TYPES.get(model_type, 'n1-standard-8')
```

### Cost Monitoring

```sql
-- BigQuery query for training costs
SELECT
  DATE(usage_start_time) as date,
  service.description as service,
  SUM(cost) as total_cost
FROM `f1-strategy.billing.gcp_billing_export_v1`
WHERE
  project.id = 'f1-strategy'
  AND (
    service.description LIKE '%Compute%'
    OR service.description LIKE '%Vertex AI%'
    OR service.description LIKE '%Storage%'
  )
  AND DATE(usage_start_time) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY date, service
ORDER BY date DESC;
```

---

## Security Hardening

### Principle of Least Privilege

**Training Service Account Permissions** (Minimal):
```
READ:
  [OK] BigQuery: f1_strategy.train, f1_strategy.validation
  [OK] GCS: gs://f1-strategy-models/* (read trained models)

WRITE:
  [OK] GCS: gs://f1-strategy-artifacts/* (write new artifacts)

DENIED:
  [FAIL] BigQuery: raw_*, processed_data (cannot modify source data)
  [FAIL] GCS: Delete operations on production buckets
  [FAIL] Compute: Create/delete infrastructure
  [FAIL] IAM: Modify service accounts or permissions
```

### Network Isolation

```
Training VPC:
  ├── No external IP addresses
  ├── Private Google Access enabled
  ├── Firewall: Block all ingress from internet
  ├── Firewall: Allow internal worker-to-worker traffic
  └── Cloud NAT: Only for pulling container images
```

### Secrets Management

```python
# Use Secret Manager for sensitive credentials
from google.cloud import secretmanager

def get_secret(secret_id: str) -> str:
    """Fetch secret from Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/f1-strategy/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(name=name)
    return response.payload.data.decode('UTF-8')

# Never hardcode credentials
api_key = get_secret('external-api-key')
```

### Audit Logging

```yaml
Audit Events:
  - data_access: Log all BigQuery queries from training workers
  - admin_activity: Log all GCS writes
  - system_event: Log worker start/stop events

Retention: 1 year
Storage: Cloud Logging + exported to BigQuery
```

---

## Training Pipeline Logging

### Centralized Logging Integration

All training tasks emit structured logs to the centralized pipeline logging system. Logs are indexed by DAG run ID and task ID, enabling easy correlation across distributed workers.

**Training-Specific Log Events**:

```yaml
training_start:
  level: INFO
  fields:
    - dag_run_id
    - task_id
    - model_type
    - num_workers
    - data_split
    - hyperparameters

training_progress:
  level: INFO
  fields:
    - dag_run_id
    - task_id
    - epoch
    - iteration
    - loss
    - accuracy
    - records_processed

training_checkpoint:
  level: INFO
  fields:
    - dag_run_id
    - task_id
    - checkpoint_uri
    - epoch
    - iteration

training_end:
  level: INFO
  fields:
    - dag_run_id
    - task_id
    - status
    - duration_seconds
    - final_loss
    - final_accuracy
    - model_uri

worker_start:
  level: INFO
  fields:
    - dag_run_id
    - task_id
    - worker_index
    - total_workers
    - node_name

worker_failure:
  level: ERROR
  fields:
    - dag_run_id
    - task_id
    - worker_index
    - error_type
    - error_message
    - stack_trace

model_evaluation:
  level: INFO
  fields:
    - dag_run_id
    - task_id
    - model_type
    - test_loss
    - test_accuracy
    - evaluation_metrics
```

### Logging Implementation in Training Workers

**File**: `pipeline/training/worker.py`

```python
from pipeline.logging.logger import PipelineLogger
import os
import time

class DistributedTrainer:
    """Distributed training worker with centralized logging."""

    def __init__(self, model_type: str, data_split: str, num_workers: int, worker_index: int, job_id: str):
        self.model_type = model_type
        self.data_split = data_split
        self.num_workers = num_workers
        self.worker_index = worker_index
        self.job_id = job_id

        # Initialize centralized logger
        dag_run_id = os.getenv('DAG_RUN_ID')
        task_id = os.getenv('TASK_ID')
        self.logger = PipelineLogger(dag_run_id, task_id)

    def run(self):
        """Execute training with comprehensive logging."""

        start_time = time.time()

        # Log training start
        self.logger.log_event(
            event_type='training_start',
            level='INFO',
            message=f'Starting training for {self.model_type}',
            model_type=self.model_type,
            num_workers=self.num_workers,
            data_split=self.data_split,
            worker_index=self.worker_index
        )

        try:
            # Load data
            data = self.load_data()

            # Train model
            for epoch in range(self.num_epochs):
                for iteration, batch in enumerate(data):
                    # Training step
                    loss, accuracy = self.train_step(batch)

                    # Log progress every 100 iterations
                    if iteration % 100 == 0:
                        self.logger.log_event(
                            event_type='training_progress',
                            level='INFO',
                            message=f'Epoch {epoch}, Iteration {iteration}',
                            epoch=epoch,
                            iteration=iteration,
                            loss=float(loss),
                            accuracy=float(accuracy)
                        )

                # Checkpoint after each epoch
                checkpoint_uri = self.save_checkpoint(epoch)
                self.logger.log_event(
                    event_type='training_checkpoint',
                    level='INFO',
                    message=f'Saved checkpoint at epoch {epoch}',
                    checkpoint_uri=checkpoint_uri,
                    epoch=epoch
                )

            # Save final model
            model_uri = self.save_model()

            # Log training end
            duration = time.time() - start_time
            self.logger.log_event(
                event_type='training_end',
                level='INFO',
                message=f'Training completed for {self.model_type}',
                status='success',
                duration_seconds=duration,
                model_uri=model_uri
            )

            return model_uri

        except Exception as e:
            # Log training failure
            self.logger.task_failure(
                error_type=type(e).__name__,
                error_message=str(e),
                stack_trace=traceback.format_exc()
            )
            raise

    def load_data(self):
        """Load training data with logging."""
        self.logger.log_event(
            event_type='data_loading',
            level='INFO',
            message=f'Loading data split: {self.data_split}',
            data_split=self.data_split
        )
        # ... data loading logic
```

### Log Querying for Training

**Query Training Progress**:
```sql
-- BigQuery query for training progress
SELECT
  timestamp,
  metadata.epoch,
  metadata.iteration,
  metadata.loss,
  metadata.accuracy
FROM f1_strategy.pipeline_logs
WHERE task_id = 'train_tire_degradation'
  AND event_type = 'training_progress'
  AND dag_run_id = 'f1_training_pipeline_20260214_020000'
ORDER BY timestamp ASC;
```

**Query Failed Workers**:
```sql
-- Find failed workers in training job
SELECT
  timestamp,
  metadata.worker_index,
  metadata.error_type,
  metadata.error_message
FROM f1_strategy.pipeline_logs
WHERE event_type = 'worker_failure'
  AND dag_run_id = 'f1_training_pipeline_20260214_020000'
ORDER BY timestamp DESC;
```

**Training Run Summary**:
```sql
-- Generate training run summary
SELECT
  task_id,
  MIN(CASE WHEN event_type = 'training_start' THEN timestamp END) as start_time,
  MAX(CASE WHEN event_type = 'training_end' THEN timestamp END) as end_time,
  MAX(CASE WHEN event_type = 'training_end' THEN metadata.duration_seconds END) as duration_seconds,
  MAX(CASE WHEN event_type = 'training_end' THEN metadata.final_loss END) as final_loss,
  MAX(CASE WHEN event_type = 'training_end' THEN metadata.final_accuracy END) as final_accuracy,
  MAX(CASE WHEN event_type = 'training_end' THEN metadata.model_uri END) as model_uri
FROM f1_strategy.pipeline_logs
WHERE dag_run_id = 'f1_training_pipeline_20260214_020000'
  AND task_id LIKE 'train_%'
GROUP BY task_id;
```

### Training Monitoring Dashboard

**Cloud Monitoring Metrics** (derived from training logs):
```yaml
training.model.loss:
  type: gauge
  labels: [model_type, epoch]
  description: Training loss per epoch

training.model.accuracy:
  type: gauge
  labels: [model_type, epoch]
  description: Training accuracy per epoch

training.worker.failure_count:
  type: counter
  labels: [model_type, worker_index, error_type]
  description: Worker failure count

training.checkpoint.count:
  type: counter
  labels: [model_type]
  description: Number of checkpoints saved

training.duration_seconds:
  type: gauge
  labels: [model_type, status]
  description: Total training duration
```

**Alerting Rules**:
```yaml
training_stalled:
  condition: no training_progress events in 30 minutes
  severity: warning
  action: notify_slack

worker_failure_rate_high:
  condition: worker_failure_count > 3 in 1 hour
  severity: critical
  action: notify_pagerduty

training_duration_exceeded:
  condition: training_duration_seconds > 14400  # 4 hours
  severity: warning
  action: notify_slack
```

---

## Operational Guarantees

### Observability

Training pipeline emits comprehensive metrics for full visibility into distributed training execution.

**Training-Specific Metrics** (per DAG run, per task, per worker):

```yaml
Training Job Metrics:
  training.job.duration_seconds:
    type: gauge
    labels: [model_type, dag_run_id, status]
    description: Total training job duration
    aggregations: [p50, p95, p99]
    slo:
      tire_degradation: <14400s  # 4 hours
      fuel_consumption: <14400s
      brake_bias: <7200s         # 2 hours
      driving_style: <10800s     # 3 hours

  training.job.success_count:
    type: counter
    labels: [model_type]
    description: Successful training job completions

  training.job.failure_count:
    type: counter
    labels: [model_type, failure_reason]
    description: Failed training jobs

  training.job.retry_count:
    type: counter
    labels: [model_type, attempt_number]
    description: Training job retries

  training.job.queue_delay_seconds:
    type: gauge
    labels: [model_type]
    description: Time between job submission and start
    slo: <300s  # 5 minutes

Worker-Level Metrics:
  training.worker.cpu_utilization:
    type: gauge
    labels: [job_id, worker_index, model_type]
    description: Worker CPU utilization (0-100%)
    alert_threshold: >95% for >30min

  training.worker.memory_usage_bytes:
    type: gauge
    labels: [job_id, worker_index]
    description: Worker memory usage
    alert_threshold: >90% of limit

  training.worker.gpu_utilization:
    type: gauge
    labels: [job_id, worker_index]
    description: GPU utilization (if applicable)
    alert_threshold: <20% for >1hr (underutilization)

  training.worker.heartbeat_timestamp:
    type: gauge
    labels: [job_id, worker_index]
    description: Last worker heartbeat (for liveness check)
    alert_threshold: no heartbeat in 2 minutes

Training Progress Metrics:
  training.progress.epoch:
    type: gauge
    labels: [job_id, model_type]
    description: Current training epoch

  training.progress.iteration:
    type: counter
    labels: [job_id, model_type]
    description: Training iterations completed

  training.progress.records_processed:
    type: counter
    labels: [job_id, worker_index]
    description: Training records processed

  training.model.loss:
    type: gauge
    labels: [model_type, epoch, split]
    description: Training/validation loss per epoch

  training.model.accuracy:
    type: gauge
    labels: [model_type, epoch, split]
    description: Training/validation accuracy per epoch

  training.checkpoint.count:
    type: counter
    labels: [job_id, model_type]
    description: Checkpoints saved

Data Quality Metrics:
  training.data.validation_errors:
    type: counter
    labels: [model_type, validation_rule]
    description: Pre-training data validation errors
```

**Training Alerting Rules**:

```yaml
Critical Alerts:
  - name: training_job_timeout
    condition: training.job.duration_seconds > 14400  # 4 hours
    severity: critical
    channels: [pagerduty, slack]
    action: Terminate job, investigate

  - name: repeated_training_failures
    condition: training.job.failure_count > 2 in 24 hours for same model_type
    severity: critical
    channels: [pagerduty]
    action: Block new training jobs, alert ML team

  - name: worker_oom
    condition: training.worker.memory_usage_bytes / limits.memory > 0.95
    severity: critical
    channels: [slack]
    action: Auto-retry with larger instance (n1-highmem)

  - name: worker_unresponsive
    condition: no training.worker.heartbeat in 2 minutes
    severity: critical
    channels: [slack]
    action: Restart worker, resume from checkpoint

  - name: data_validation_failure
    condition: training.data.validation_errors > 0
    severity: critical
    channels: [slack]
    action: Block training job, alert data team

Warning Alerts:
  - name: training_stalled
    condition: no training.progress.iteration increment in 30 minutes
    severity: warning
    channels: [slack]
    action: Check worker logs, may need restart

  - name: high_training_retry_rate
    condition: rate(training.job.retry_count[24h]) > 0.3
    severity: warning
    channels: [slack]
    action: Investigate infrastructure issues

  - name: gpu_underutilization
    condition: training.worker.gpu_utilization < 20% for >1 hour
    severity: warning
    channels: [slack]
    action: Review model architecture, may not need GPU

  - name: training_queue_backlog
    condition: training.job.queue_delay_seconds > 600s  # 10 minutes
    severity: warning
    channels: [slack]
    action: Increase worker pool max_replicas
```

**Observability Dashboards**:

```yaml
Training Dashboard Panels:
  1. Job Status Overview:
     - Active training jobs (by model type)
     - Job duration (current, p95, max)
     - Success/failure rate (last 7 days)
     - Queue depth and delay

  2. Worker Health:
     - Worker count (current, target, max)
     - CPU/Memory/GPU utilization per worker
     - Worker heartbeats (liveness map)
     - Failed worker count

  3. Training Progress:
     - Loss curves (training, validation)
     - Accuracy trends per epoch
     - Records processed per second
     - ETA to completion

  4. Cost & Resource Usage:
     - Current spend (hourly rate)
     - Projected cost to completion
     - Resource allocation vs limits
     - Cost per model (historical)

  5. Data Quality:
     - Validation error rate
     - Data completeness score
     - Feature drift detection
     - Training data freshness
```

### Cost Controls

Training pipeline enforces strict cost controls to prevent budget overruns on compute-intensive workloads.

**Training Job Resource Limits**:

```yaml
Per-Model Resource Limits:
  tire_degradation:
    cpu_limit: 16 cores
    memory_limit: 64Gi
    max_workers: 4
    timeout: 14400s  # 4 hours
    max_cost_per_run: $8.00
    estimated_cost: $5-7

  fuel_consumption:
    cpu_limit: 16 cores
    memory_limit: 64Gi
    max_workers: 4
    timeout: 14400s
    max_cost_per_run: $8.00
    estimated_cost: $5-7

  brake_bias:
    cpu_limit: 8 cores
    memory_limit: 32Gi
    max_workers: 2
    timeout: 7200s  # 2 hours
    max_cost_per_run: $3.00
    estimated_cost: $2-3

  driving_style:
    cpu_limit: 16 cores
    memory_limit: 64Gi
    max_workers: 4
    timeout: 10800s  # 3 hours
    max_cost_per_run: $6.00
    estimated_cost: $4-6

# Hard limits enforced at orchestrator level
# Jobs terminated if limits exceeded
```

**Max Runtime Enforcement**:

```yaml
Training Job Timeouts:
  per_model_timeout: defined above
  total_training_dag_timeout: 57600s  # 16 hours (all 4 models in sequence)

Timeout Actions:
  - Task terminated gracefully (SIGTERM)
  - 30-second grace period for cleanup
  - Force kill if not terminated (SIGKILL)
  - Checkpoint saved before termination (if possible)
  - Failure logged with reason: "timeout_exceeded"
  - No automatic retry on timeout (manual investigation required)
```

**Autoscaling Bounds (Training Compute)**:

```yaml
Training Worker Pool:
  min_replicas: 0  # Scale to zero when idle
  max_replicas: 20  # Hard cap to prevent runaway costs

  scale_up_policy:
    trigger: training_jobs_queued > 0
    increment: min(jobs_queued * avg_workers_per_job, max_replicas - current)
    cooldown: 60s

  scale_down_policy:
    trigger: idle_workers > 0 for >300s  # 5 minutes
    decrement: idle_workers
    cooldown: 300s
    grace_period: 60s  # Allow checkpointing before termination

  cost_guardrails:
    max_hourly_spend: $50
    action_on_exceed: pause_autoscaling, alert_devops
```

**Budget Thresholds & Throttling** (Training-Specific):

```yaml
Training Budget (Monthly):
  allocated: $120
  breakdown:
    weekly_retraining: $80  # 4 models × $20/week
    ad_hoc_experiments: $30
    infrastructure_overhead: $10

Budget Actions:
  $96 (80% of training budget):
    action: warning_alert
    channels: [slack]
    message: "Training budget 80% consumed"

  $108 (90% of training budget):
    action: throttle_training
    scope:
      - Pause weekly scheduled retraining
      - Allow only critical manual jobs
      - Reduce max_workers by 50%
      - Alert ML team

  $120 (100% of training budget):
    action: block_training
    scope:
      - Block all new training jobs
      - Allow running jobs to complete
      - Scale worker pool to zero after completion
      - Require manual approval for new jobs

  $150 (125% overage):
    action: emergency_stop
    scope:
      - Terminate all running training jobs
      - Save checkpoints before termination
      - Scale to zero immediately
      - Require director approval to restart
```

**Training Job Throttling**:

```yaml
Throttle Conditions:
  budget_threshold_exceeded:
    action: pause_scheduled_jobs
    scope: weekly retraining only (manual jobs still allowed)

  consecutive_failures:
    condition: 3+ failures for same model in 24 hours
    action: block_model_training
    duration: 24 hours or until manual review

  resource_exhaustion:
    condition: max_replicas reached and jobs queued
    action: queue_jobs
    max_queue_size: 10
    overflow_action: reject_new_jobs

Throttle Overrides:
  critical_training_job:
    label: "priority:critical"
    bypass: budget_throttle (but not emergency_stop)
    approval: ML team lead required
```

**Cost Visibility (Training Pipeline)**:

```yaml
Training Cost Metrics:
  cost.training.job_total:
    type: gauge
    labels: [model_type, dag_run_id]
    description: Total cost for training job

  cost.training.worker_hours:
    type: counter
    labels: [model_type, instance_type]
    description: Worker-hours consumed

  cost.training.storage_io:
    type: gauge
    labels: [model_type]
    description: Storage I/O cost (checkpoints, artifacts)

  cost.training.cumulative_week:
    type: counter
    labels: [model_type]
    description: Weekly training spend
    reset: Weekly on Monday 00:00 UTC

  cost.training.projected_month:
    type: gauge
    description: Projected monthly training cost based on current rate
    alert_threshold: >$120
```

**Cost Optimization (Training)**:
- [OK] Preemptible VMs (70% cost reduction, with checkpoint/retry logic)
- [OK] Scale to zero when no jobs running
- [OK] Right-sized instances per model (small models use smaller instances)
- [OK] Checkpoint cleanup (delete after 7 days)
- [OK] Cached preprocessed features (reduce BigQuery costs)
- [OK] Spot instances with aggressive bidding

### Failure Isolation & Blast Radius

Training failures are strictly isolated to prevent impact on data ingestion, inference, and other pipelines.

**Training Failure Scope**:

```yaml
Isolation Guarantees:
  Failed Training Job Impact:
    affected:
      - This training job only
      - Model artifacts NOT updated (previous version remains)

    NOT affected:
      [OK] Data ingestion pipeline (continues normally)
      [OK] Data processing pipeline (continues normally)
      [OK] Streaming inference (uses existing models)
      [OK] Real-time API (serves existing models)
      [OK] Dashboard (shows existing models)
      [OK] Other training jobs (parallel models continue)

  Failed Worker Impact:
    affected:
      - This worker only
      - Training job pauses/retries

    NOT affected:
      [OK] Other workers in same job
      [OK] Other training jobs
      [OK] Non-training pipelines

  Orchestrator Failure Impact:
    affected:
      - Training DAG runs paused

    NOT affected:
      [OK] Completed training artifacts
      [OK] Data pipeline (separate orchestrator)
      [OK] Inference pipeline
      [OK] Model registry

Recovery:
  - Orchestrator auto-restarts within 5 minutes
  - Training jobs resume from last checkpoint
```

**Training Non-Blocking Design**:

```
System Architecture (Failure Isolation):
┌─────────────────────────────────────────────────────┐
│                                                     │
│  ┌──────────────┐         ┌──────────────┐         │
│  │ Data         │    [OK]    │ Inference    │         │
│  │ Pipeline     │ Running │ API          │         │
│  │ (Running)    │         │ (Running)    │         │
│  └──────────────┘         └──────────────┘         │
│                                                     │
│  ┌──────────────┐                                  │
│  │ Training     │         X FAILED                 │
│  │ Pipeline     │           (Isolated)             │
│  │ (Failed)     │                                  │
│  └──────────────┘                                  │
│                                                     │
│  Training Failure Impact:                          │
│  [OK] Data ingestion: UNAFFECTED                     │
│  [OK] Inference API: UNAFFECTED (uses old models)    │
│  [OK] Dashboard: UNAFFECTED                          │
│  [OK] Monitoring: UNAFFECTED                         │
│  [FAIL] New models: NOT deployed (old models remain)   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Retry Scope (Training-Specific)**:

```yaml
Training Retry Policy:
  scope: task  # Per-model training task, NOT entire training DAG

  max_retries: 2  # Lower than data pipeline (training more expensive)
  retry_delay: 300s  # 5 minutes (allow resources to clean up)
  backoff_multiplier: 2.0

  retry_on:
    - worker_preempted  # Preemptible VM preempted
    - network_timeout   # Transient network issue
    - worker_crash      # Worker node failure

  no_retry_on:
    - data_validation_failure  # Data quality issue
    - out_of_memory            # Requires config change
    - timeout_exceeded         # Job taking too long
    - cost_limit_exceeded      # Budget issue

  retry_behavior:
    - Resume from last checkpoint (NOT from scratch)
    - Increment attempt_number in logs
    - Track retry reason in metadata
    - Alert on 2nd retry (may indicate systemic issue)

Retry Isolation:
  - Retries do NOT affect other model training tasks
  - Failed tire_degradation retries do NOT block fuel_consumption training
  - Retry count tracked per model, NOT per DAG
  - Max 2 retries → manual intervention required
```

**Cascading Failure Prevention (Training DAG)**:

```yaml
Training DAG Branch Independence:
  # 4 parallel training tasks (tire_deg, fuel_cons, brake_bias, driving_style)
  # Failure in one does NOT cascade to others

  ┌──────────────┐
  │  Validate    │
  │Training Data │
  └──────┬───────┘
         │
  ┌──────┼──────────────────┬──────────┬──────────┐
  │      │                  │          │          │
  ▼      ▼                  ▼          ▼          ▼
┌────┐ ┌────┐            ┌────┐    ┌────┐    ┌────┐
│Tire│ │Fuel│   (Failed)│Brake│    │Drive│    │...│
│Deg │ │Cons│      X     │Bias│    │Style│    │   │
└──┬─┘ └──┬─┘            └──┬─┘    └──┬─┘    └───┘
   │      │                 │         │
   │      X                 │         │
   │                        │         │
   └────────┬───────────────┴─────────┘
            ▼
     ┌──────────────┐
     │  Evaluate    │  ← Only evaluates successful models
     │  Models      │    (Fuel failure isolated)
     └──────┬───────┘
            ▼
     ┌──────────────┐
     │  Register    │  ← Only registers evaluated models
     │  Models      │    (Partial success allowed)
     └──────────────┘

Independence Rules:
  - Each model training task is independent
  - Evaluation stage evaluates ONLY successful models
  - Registration stage registers ONLY evaluated models
  - Partial success allowed (3/4 models trained → deploy 3)
  - Failed models keep previous version in production
```

**Blast Radius Containment (Training)**:

```yaml
Impact Boundaries:
  Training Task Failure:
    affected: 1 model training task
    unaffected: other 3 model training tasks, data pipeline, inference
    recovery: retry task (2x), fallback to previous model version

  Training DAG Failure:
    affected: all training tasks in this DAG run
    unaffected: data pipeline, inference, other DAG runs
    recovery: retry DAG from failed node, investigate root cause

  Worker Pool Exhaustion:
    affected: new training jobs (queued)
    unaffected: running jobs, data pipeline, inference
    recovery: autoscaling provisions workers (or jobs wait in queue)

  Training Data Corruption:
    affected: current training DAG (validation failure)
    unaffected: previous models, inference, data pipeline
    recovery: block training, fix data, re-run validation

Prohibited Cascades:
  [FAIL] Training failure NEVER stops data ingestion
  [FAIL] Training failure NEVER stops inference API
  [FAIL] Training failure NEVER deletes previous models
  [FAIL] One model failure NEVER blocks other model training
```

### Compliance & Auditability

All training executions are fully auditable with immutable records for reproducibility and compliance.

**Training Audit Trail**:

```yaml
Immutable Training Records:
  1. Training Job Metadata:
     - DAG run ID and task ID
     - Model type and version
     - Git commit SHA (training code)
     - Container image digest (training worker)
     - Hyperparameters (all config)
     - Data split versions (train/val checksums)
     - Resource allocation (CPU, memory, workers)
     - Start/end timestamps
     - Success/failure status
     - Cost per job

  2. Training Artifacts:
     - Model binary (versioned in GCS)
     - Model metadata (architecture, hyperparameters)
     - Training metrics (loss, accuracy per epoch)
     - Validation metrics (test set performance)
     - Feature importance (if applicable)
     - Checkpoints (retained 7 days)

  3. Data Lineage:
     - Input: f1_strategy.train (snapshot version)
     - Features: f1_features table (version)
     - Output: gs://f1-strategy-models/[model_type]/[version]/
     - Full provenance chain queryable

  4. IAM Access (Training-Specific):
     - BigQuery reads: which tables, when, by whom
     - GCS writes: which buckets, what artifacts
     - Vertex AI job submissions
     - Model registry updates
```

**Training Audit Schema**:

```sql
-- BigQuery table: f1_strategy.training_audit_log
CREATE TABLE f1_strategy.training_audit_log (
  audit_id STRING NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  dag_run_id STRING NOT NULL,
  task_id STRING NOT NULL,
  model_type STRING NOT NULL,
  event_type STRING NOT NULL,  -- training_start, training_end, checkpoint_saved, model_registered
  status STRING,  -- running, success, failure
  metadata JSON,

  -- Training-specific fields
  git_commit_sha STRING,
  container_image_digest STRING,
  hyperparameters JSON,
  num_workers INT64,
  worker_type STRING,

  -- Data lineage
  input_data_version STRING,
  input_data_checksum STRING,
  output_model_uri STRING,
  output_model_checksum STRING,

  -- Performance
  training_duration_seconds FLOAT64,
  final_loss FLOAT64,
  final_accuracy FLOAT64,

  -- Cost
  cost_usd FLOAT64,
  worker_hours FLOAT64
)
PARTITION BY DATE(timestamp)
CLUSTER BY model_type, dag_run_id
OPTIONS(
  description="Immutable audit log for all training executions"
);
```

**Training Audit Queries**:

```sql
-- Query: All training runs for a specific model in last 30 days
SELECT
  timestamp,
  dag_run_id,
  status,
  training_duration_seconds,
  final_loss,
  final_accuracy,
  cost_usd
FROM f1_strategy.training_audit_log
WHERE model_type = 'tire_degradation'
  AND event_type = 'training_end'
  AND DATE(timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
ORDER BY timestamp DESC;

-- Query: Reproduce training run (get exact configuration)
SELECT
  git_commit_sha,
  container_image_digest,
  hyperparameters,
  input_data_version,
  input_data_checksum,
  num_workers,
  worker_type
FROM f1_strategy.training_audit_log
WHERE dag_run_id = 'f1_training_pipeline_20260214_020000'
  AND task_id = 'train_tire_degradation'
  AND event_type = 'training_start'
LIMIT 1;

-- Query: Training cost trends
SELECT
  DATE(timestamp) as date,
  model_type,
  COUNT(*) as num_runs,
  AVG(training_duration_seconds) as avg_duration,
  SUM(cost_usd) as total_cost
FROM f1_strategy.training_audit_log
WHERE event_type = 'training_end'
  AND status = 'success'
  AND DATE(timestamp) >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
GROUP BY date, model_type
ORDER BY date DESC, model_type;
```

**Training Reproducibility**:

```yaml
Reproducibility Guarantees:
  deterministic_training:
    - Fixed random seeds (per DAG run)
    - Exact hyperparameters recorded
    - Data split checksums verified
    - Container image digest pinned
    - Training code version (git commit SHA)

  reproducible_artifacts:
    - Model binary checksums recorded
    - Training metrics reproducible (±1% tolerance for numerical precision)
    - Feature importance vectors match
    - Prediction outputs match on test set

  rollback_capability:
    - Restore any previous model version
    - Re-run training with historical config
    - Recreate exact training environment
    - Max rollback window: 90 days (then archived)

Reproduction Procedure:
  # Reproduce training run from 2024-01-15
  python pipeline/training/reproduce.py \
    --dag-run-id f1_training_pipeline_20240115_020000 \
    --task-id train_tire_degradation \
    --verify-checksums \
    --compare-metrics

  # Verifies:
  # [OK] Git commit SHA matches
  # [OK] Container image digest matches
  # [OK] Hyperparameters match
  # [OK] Input data checksums match
  # [OK] Output model checksum matches (bit-for-bit)
  # [OK] Training metrics match (within tolerance)
```

**Training Compliance Retention**:

```yaml
Training Artifact Retention:
  trained_models: 90 days (production), then archive 1 year
  training_metrics: 1 year
  checkpoints: 7 days (delete after)
  training_audit_logs: 1 year (regulatory)
  hyperparameters: 1 year
  training_code: permanent (Git)
  cost_data: 3 years (accounting)

Access Controls:
  training_audit_logs: read-only (NO deletion)
  model_artifacts: versioned (previous versions preserved)
  training_configs: immutable after job start

Compliance Export:
  - Monthly export of training audit logs to secure archive
  - Encrypted with CMEK (customer-managed encryption keys)
  - Retention: 3 years for model governance
  - Access: ML team leads, compliance officers only
```

**Training Audit Alerting**:

```yaml
Security Alerts:
  - name: unauthorized_model_access
    condition: model_registry access denied
    severity: critical
    channels: [security_team]

  - name: model_artifact_tampering
    condition: model checksum mismatch after registration
    severity: critical
    channels: [security_team, ml_team]
    action: Quarantine model, investigate

  - name: training_data_unauthorized_access
    condition: BigQuery access from non-training service account
    severity: warning
    channels: [security_team]

Compliance Alerts:
  - name: training_audit_gap
    condition: no training audit events for >1 day during scheduled training
    severity: warning
    channels: [compliance_team]

  - name: model_deployment_without_audit
    condition: model deployed without training_audit_log entry
    severity: critical
    channels: [compliance_team, ml_team]
    action: Block deployment, require audit trail
```

---

## Production Readiness Checklist

### Pre-Deployment

- [ ] Terraform infrastructure deployed and tested
- [ ] Service accounts created with least-privilege IAM
- [ ] Training container image built and pushed to GCR
- [ ] VPC and firewall rules configured
- [ ] Data validation pipeline tested on sample data
- [ ] Checkpoint/restore logic tested
- [ ] Monitoring dashboards configured
- [ ] Alerting rules deployed
- [ ] DAG definitions validated and tested
- [ ] Centralized logging integration verified

### Post-Deployment

- [ ] Execute dry-run training job (small dataset)
- [ ] Verify artifacts written to GCS
- [ ] Validate metrics exported to Cloud Monitoring
- [ ] Test failure scenarios (worker crash, OOM, etc.)
- [ ] Verify cost tracking and budgets
- [ ] Conduct security review (IAM, network, secrets)
- [ ] Test DAG retry and partial re-run logic
- [ ] Verify logs are queryable in BigQuery
- [ ] Document runbook for on-call engineers

---

**See Also**:
- CLAUDE.md: High-level project overview
- docs/data.md: DAG orchestration and pipeline logging
- docs/architecture.md: Overall DAG execution model
- docs/monitoring.md: Operational monitoring details
- infrastructure/terraform/: Infrastructure as code
- pipeline/orchestrator/dag_definitions/: DAG definitions
