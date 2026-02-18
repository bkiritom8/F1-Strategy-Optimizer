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
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.0"
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
    "sqladmin.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
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

  service_name    = "f1-strategy-api"
  container_image = "${var.region}-docker.pkg.dev/${var.project_id}/f1-optimizer/api:latest"
  max_instances   = var.api_max_instances
  min_instances   = var.api_min_instances
  memory          = "512Mi"
  cpu             = "1"
  timeout_seconds = 60

  env_vars = {
    ENV               = var.environment
    DB_HOST           = google_sql_database_instance.f1_db.private_ip_address
    DB_NAME           = google_sql_database.f1_data.name
    DB_PORT           = "5432"
    PUBSUB_PROJECT_ID = var.project_id
    ENABLE_HTTPS      = "true"
    ENABLE_IAM        = "true"
    LOG_LEVEL         = "INFO"
  }

  labels = local.common_labels

  depends_on = [google_project_service.required_apis]
}

# VPC Network
module "networking" {
  source = "./modules/networking"

  project_id  = var.project_id
  region      = var.region
  environment = var.environment

  network_name = "f1-optimizer-network"

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

  labels = local.common_labels
}

# Private IP range for Cloud SQL VPC peering
resource "google_compute_global_address" "private_ip_range" {
  name          = "f1-optimizer-private-ip-${var.environment}"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = module.networking.network_id

  depends_on = [module.networking]
}

resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = module.networking.network_id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_ip_range.name]

  depends_on = [google_project_service.required_apis]
}

# Generate random password for Cloud SQL user
resource "random_password" "db_password" {
  length  = 32
  special = true
}

# Cloud SQL (PostgreSQL) — operational data store replacing BigQuery
resource "google_sql_database_instance" "f1_db" {
  name                = "f1-optimizer-${var.environment}"
  database_version    = "POSTGRES_15"
  region              = var.region
  deletion_protection = true

  settings {
    tier = "db-f1-micro"

    backup_configuration {
      enabled = true
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = module.networking.network_id
      ssl_mode        = "ENCRYPTED_ONLY"
    }

    user_labels = local.common_labels
  }

  depends_on = [
    google_project_service.required_apis,
    google_service_networking_connection.private_vpc_connection,
  ]
}

resource "google_sql_database" "f1_data" {
  name     = "f1_data"
  instance = google_sql_database_instance.f1_db.name
  project  = var.project_id
}

resource "google_sql_user" "api_user" {
  name     = "f1_api"
  instance = google_sql_database_instance.f1_db.name
  project  = var.project_id
  password = random_password.db_password.result
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "f1-db-password-${var.environment}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_secret_manager_secret_version" "db_password" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = random_password.db_password.result
}

resource "google_project_iam_member" "api_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api_sa.email}"
}

resource "google_cloud_run_service_iam_member" "api_sa_run_invoker" {
  project  = var.project_id
  location = var.region
  service  = "f1-strategy-api-dev"
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.api_sa.email}"
}
resource "google_project_iam_member" "compute_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:694267183904-compute@developer.gserviceaccount.com"
}

# Artifact Registry — Docker image repository
resource "google_artifact_registry_repository" "docker_repo" {
  repository_id = "f1-optimizer"
  format        = "DOCKER"
  location      = "us-central1"
  description   = "F1 Strategy Optimizer Docker images"

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

# Monitoring and Logging
resource "google_monitoring_notification_channel" "email" {
  display_name = "F1 Optimizer Email Alerts"
  type         = "email"

  labels = {
    email_address = var.alert_email
  }
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

  notification_channels = [google_monitoring_notification_channel.email.id]

  alert_strategy {
    auto_close = "1800s"
  }
}

# Cloud Run v2 Job — data ingestion (Ergast + FastF1)
resource "google_cloud_run_v2_job" "f1_data_ingestion" {
  name     = "f1-data-ingestion"
  location = var.region
  labels   = local.common_labels

  template {
    template {
      timeout = "3600s"

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/f1-optimizer/api:latest"

        resources {
          limits = {
            memory = "4Gi"
            cpu    = "2"
          }
        }

        env {
          name  = "DB_HOST"
          value = google_sql_database_instance.f1_db.private_ip_address
        }
        env {
          name  = "DB_NAME"
          value = var.db_name
        }
        env {
          name  = "DB_PORT"
          value = "5432"
        }
        env {
          name  = "DB_USER"
          value = "f1_api"
        }
        env {
          name = "DB_PASSWORD"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.db_password.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_sql_database_instance.f1_db,
    google_secret_manager_secret_version.db_password,
  ]
}

# Trigger data ingestion job once after infrastructure is ready.
# Re-runs only when the Cloud SQL instance name changes, not on every apply.
resource "null_resource" "trigger_data_ingestion" {
  triggers = {
    db_instance_name = google_sql_database_instance.f1_db.name
  }

  provisioner "local-exec" {
    command = "gcloud run jobs execute f1-data-ingestion --region=${var.region} --project=${var.project_id}"
  }

  depends_on = [
    google_cloud_run_v2_job.f1_data_ingestion,
    google_sql_database_instance.f1_db,
  ]
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

# Outputs
output "cloud_sql_instance_connection_name" {
  description = "Cloud SQL instance connection name"
  value       = google_sql_database_instance.f1_db.connection_name
}

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
