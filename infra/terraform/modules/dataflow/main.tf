/**
 * Dataflow Module
 * Configures Dataflow resources for F1 streaming pipeline
 */

# Dataflow jobs are launched dynamically via Airflow DAGs.
# This module provisions supporting GCS buckets for Dataflow temp/staging.

resource "google_storage_bucket" "dataflow_temp" {
  name     = "${var.project_id}-dataflow-temp-${var.environment}"
  project  = var.project_id
  location = var.region

  force_destroy = var.environment != "prod"

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = 7
    }
  }

  labels = var.labels
}

resource "google_storage_bucket" "dataflow_staging" {
  name     = "${var.project_id}-dataflow-staging-${var.environment}"
  project  = var.project_id
  location = var.region

  force_destroy = var.environment != "prod"

  labels = var.labels
}
