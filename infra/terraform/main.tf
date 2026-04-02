/**
 * F1 Strategy Optimizer - Main Terraform Configuration
 * Provisions GCP infrastructure for production deployment
 */

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }

  backend "gcs" {
    bucket = "f1-optimizer-terraform-state"
    prefix = "terraform/state"
  }
}

# Configure GCP provider
provider "google" {
  project = var.project_id
  region  = var.region
}

# Local variables
locals {
  common_labels = {
    project     = "f1-strategy-optimizer"
    environment = var.environment
    managed_by  = "terraform"
  }
}

# Enable required APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "compute.googleapis.com",
    "pubsub.googleapis.com",
    "dataflow.googleapis.com",
    "run.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com"
  ])

  service            = each.value
  disable_on_destroy = false
}

# Pub/Sub Topics and Subscriptions
module "pubsub" {
  source = "./modules/pubsub"

  project_id  = var.project_id
  environment = var.environment

  topics = [
    "f1-race-events",
    "f1-telemetry-stream",
    "f1-predictions",
    "f1-alerts"
  ]

  labels = local.common_labels

  depends_on = [google_project_service.required_apis]
}

# Dataflow Jobs
module "dataflow" {
  source = "./modules/dataflow"

  project_id  = var.project_id
  region      = var.region
  environment = var.environment

  temp_location    = "gs://${var.project_id}-dataflow-temp"
  staging_location = "gs://${var.project_id}-dataflow-staging"

  labels = local.common_labels

  depends_on = [google_project_service.required_apis]
}

# Cloud Run Services
module "cloud_run" {
  source = "./modules/compute"

  project_id  = var.project_id
  region      = var.region
  environment = var.environment

  service_name            = "f1-strategy-api"
  container_image         = "${var.region}-docker.pkg.dev/${var.project_id}/f1-optimizer/api:latest"
  max_instances           = var.api_max_instances
  min_instances           = var.api_min_instances
  max_concurrent_requests = var.api_max_concurrent_requests
  cpu_target_utilization  = var.api_cpu_target_utilization
  memory                  = "1Gi"
  cpu                     = "2"
  timeout_seconds         = 120

  env_vars = {
    ENV                             = var.environment
    PUBSUB_PROJECT_ID               = var.project_id
    MODELS_BUCKET                   = "gs://${google_storage_bucket.models.name}"
    ENABLE_HTTPS                    = "true"
    ENABLE_IAM                      = "true"
    LOG_LEVEL                       = "INFO"
    LLM_PRIMARY_MODEL               = "gemini-2.5-flash"
    LLM_FALLBACK_MODEL              = "gemini-1.5-flash"
    LLM_BATCH_MAX_SIZE              = "50"
    LLM_BATCH_MAX_WAIT_MS           = "100"
    LLM_BATCH_MAX_CONCURRENT        = "20"
    LLM_RATE_LIMIT_RPM              = "10"
    LLM_CB_FAILURE_THRESHOLD        = "5"
    LLM_CB_RECOVERY_TIMEOUT_S       = "30"
    VECTOR_SEARCH_INDEX_ID          = google_vertex_ai_index.rag.id
    VECTOR_SEARCH_ENDPOINT_ID       = google_vertex_ai_index_endpoint.rag.id
    VECTOR_SEARCH_DEPLOYED_INDEX_ID = google_vertex_ai_index_endpoint_deployed_index.rag.deployed_index_id
  }

  labels = local.common_labels

  depends_on = [google_project_service.required_apis]
}

# IAM Service Accounts
resource "google_service_account" "airflow_sa" {
  account_id   = "f1-airflow-${var.environment}"
  display_name = "F1 Airflow Service Account (${var.environment})"
  description  = "Service account for Airflow DAG execution"
}

resource "google_service_account" "dataflow_sa" {
  account_id   = "f1-dataflow-${var.environment}"
  display_name = "F1 Dataflow Service Account (${var.environment})"
  description  = "Service account for Dataflow job execution"
}

resource "google_service_account" "api_sa" {
  account_id   = "f1-api-${var.environment}"
  display_name = "F1 API Service Account (${var.environment})"
  description  = "Service account for Cloud Run API service"
}

# IAM Bindings
resource "google_project_iam_member" "airflow_pubsub_admin" {
  project = var.project_id
  role    = "roles/pubsub.admin"
  member  = "serviceAccount:${google_service_account.airflow_sa.email}"
}

resource "google_project_iam_member" "dataflow_worker" {
  project = var.project_id
  role    = "roles/dataflow.worker"
  member  = "serviceAccount:${google_service_account.dataflow_sa.email}"
}

# Cloud Storage Buckets
# Data lake — raw/ holds source CSVs from Jolpica/FastF1,
# processed/ holds Parquet files ready for ML training
resource "google_storage_bucket" "data_lake" {
  name          = "${var.project_id}-data-lake"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  lifecycle_rule {
    condition {
      age = 365
    }
    action {
      type          = "SetStorageClass"
      storage_class = "COLDLINE"
    }
  }

  labels = local.common_labels
}

resource "google_storage_bucket" "models" {
  name          = "${var.project_id}-models"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }

  # Delete noncurrent (superseded) model versions after 30 days
  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 30
    }
    action {
      type = "Delete"
    }
  }

  labels = local.common_labels
}

# Artifact Registry — Docker image repository
resource "google_artifact_registry_repository" "docker_repo" {
  repository_id = "f1-optimizer"
  format        = "DOCKER"
  location      = "us-central1"
  description   = "F1 Strategy Optimizer Docker images"

  # Keep the 5 most recent tagged images per image name; delete untagged digests
  # after 7 days. This prevents $COMMIT_SHA images from accumulating across builds.
  cleanup_policies {
    id     = "keep-5-most-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = 5
    }
  }

  cleanup_policies {
    id     = "delete-untagged-after-7d"
    action = "DELETE"
    condition {
      tag_state  = "UNTAGGED"
      older_than = "604800s" # 7 days
    }
  }

  depends_on = [google_project_service.required_apis]
}

# Lookup project metadata (used for Cloud Build service account)
data "google_project" "project" {}


# Grant Cloud Build SA permission to push images to Artifact Registry
resource "google_project_iam_member" "cloudbuild_ar_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${data.google_project.project.number}@cloudbuild.gserviceaccount.com"

  depends_on = [google_project_service.required_apis]
}

resource "google_cloud_run_service_iam_member" "api_sa_run_invoker" {
  project  = var.project_id
  location = var.region
  service  = "f1-strategy-api-dev"
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.api_sa.email}"
}

# Monitoring and Logging
# One notification channel per alert email — add team members in *.tfvars
resource "google_monitoring_notification_channel" "email" {
  for_each     = toset(var.alert_emails)
  display_name = "F1 Optimizer Alerts — ${each.value}"
  type         = "email"

  labels = {
    email_address = each.value
  }
}

locals {
  all_notification_channels = [for ch in google_monitoring_notification_channel.email : ch.id]
}

resource "google_monitoring_alert_policy" "api_error_rate" {
  display_name = "F1 API High Error Rate"
  combiner     = "OR"

  conditions {
    display_name = "API Error Rate > 5%"

    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class=\"5xx\""
      duration        = "60s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = local.all_notification_channels

  alert_strategy {
    auto_close = "1800s"
  }
}


# Vertex AI Training Infrastructure
resource "google_storage_bucket" "training" {
  name          = "${var.project_id}-training"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true
  versioning {
    enabled = true
  }

  # Delete training checkpoints and pipeline run artifacts after 45 days.
  # Cloud Build log objects also land here — this prevents unbounded growth.
  lifecycle_rule {
    condition {
      age = 45
    }
    action {
      type = "Delete"
    }
  }

  # Purge noncurrent (overwritten) versions after 7 days.
  lifecycle_rule {
    condition {
      days_since_noncurrent_time = 7
    }
    action {
      type = "Delete"
    }
  }

  labels = local.common_labels

  depends_on = [google_project_service.required_apis]
}

resource "google_service_account" "training_sa" {
  account_id   = "f1-training-dev"
  display_name = "F1 Training Service Account (dev)"
  description  = "Service account for running Vertex AI custom training jobs"
}


resource "google_project_iam_member" "api_sa_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.api_sa.email}"
}

resource "google_project_iam_member" "training_sa_custom_code" {
  project = var.project_id
  role    = "roles/aiplatform.customCodeServiceAgent"
  member  = "serviceAccount:${google_service_account.training_sa.email}"
}

resource "google_project_iam_member" "training_sa_storage_admin" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.training_sa.email}"
}

# ── Cloud Build trigger — pipeline branch ──────────────────────────────────
# Requires the Cloud Build GitHub App to be connected first (OAuth step in
# the GCP Console — one-time). Until then this resource stays commented out.
#
# SETUP STEPS:
#   1. Cloud Build → Triggers → Connect Repository
#   2. Select "GitHub (Cloud Build GitHub App)" → authenticate
#   3. Select bkiritom8/F1-Strategy-Optimizer → Done
#   4. Then uncomment the resource block below and run:
#        terraform -chdir=infra/terraform apply -var-file=dev.tfvars
#
# resource "google_cloudbuild_trigger" "pipeline_branch" {
#   project     = var.project_id
#   name        = "pipeline-branch-trigger"
#   description = "Build, train, validate, deploy — backend changes on pipeline branch only"
#   location    = "global"
#
#   github {
#     owner = "bkiritom8"
#     name  = "F1-Strategy-Optimizer"
#     push {
#       branch = "^pipeline$"
#     }
#   }
#
#   included_files = [
#     "src/**", "ml/**", "docker/**",
#     "cloudbuild/**", "cloudbuild.yaml", "requirements*.txt",
#   ]
#
#   ignored_files = [
#     "frontend/**", "docs/**", "**/*.md", ".github/**", "infra/**",
#   ]
#
#   filename   = "cloudbuild.yaml"
#   depends_on = [google_project_service.required_apis]
# }

# Outputs
output "api_service_url" {
  description = "Cloud Run API service URL"
  value       = module.cloud_run.service_url
}

output "pubsub_topics" {
  description = "Pub/Sub topic names"
  value       = module.pubsub.topic_names
}

output "service_accounts" {
  description = "Service account emails"
  value = {
    airflow  = google_service_account.airflow_sa.email
    dataflow = google_service_account.dataflow_sa.email
    api      = google_service_account.api_sa.email
    training = google_service_account.training_sa.email
  }
}

# ── IAM: api_sa needs to publish to Pub/Sub (race events, predictions)

resource "google_project_iam_member" "api_sa_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.api_sa.email}"
}
