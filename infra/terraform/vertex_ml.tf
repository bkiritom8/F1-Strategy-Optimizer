/**
 * F1 Strategy Optimizer - Vertex AI ML Resources
 * Extends main.tf with Pipeline, Experiments, and Vizier IAM/API support.
 * No Vertex AI Experiments or Vizier resources are created here — those are
 * managed via the Python SDK (pipeline_runner.py, base_model.py).
 * This file provisions the IAM roles and APIs they depend on.
 */

# ── Additional APIs ───────────────────────────────────────────────────────────

resource "google_project_service" "ml_apis" {
  for_each = toset([
    "ml.googleapis.com", # Vertex AI (legacy ML Engine alias)
  ])

  service            = each.value
  disable_on_destroy = false
  depends_on         = [google_project_service.required_apis]
}

# ── GCS bucket: f1optimizer-models (pipeline run roots + promoted models) ─────
# Already defined in main.tf as google_storage_bucket.models.
# This resource adds versioning config for pipeline run artefacts.
resource "google_storage_bucket" "pipeline_runs" {
  name          = "${var.project_id}-pipeline-runs"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type          = "SetStorageClass"
      storage_class = "NEARLINE"
    }
  }

  labels     = local.common_labels
  depends_on = [google_project_service.required_apis]
}

# ── IAM: training_sa additional roles for Vertex AI Pipelines + Vizier ────────

locals {
  pipeline_sa_extra_roles = [
    "roles/aiplatform.user",
    "roles/aiplatform.viewer",
    "roles/ml.developer",           # Vertex AI custom training
    "roles/iam.serviceAccountUser", # impersonate self when launching jobs
    "roles/run.invoker",            # trigger Cloud Run jobs from pipeline
  ]
}

resource "google_project_iam_member" "training_sa_pipeline_roles" {
  for_each = toset(local.pipeline_sa_extra_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.training_sa.email}"

  depends_on = [google_service_account.training_sa]
}

# ── Cloud Run Job: pipeline trigger ──────────────────────────────────────────
# Allows the ML team to trigger the full Vertex AI Pipeline via:
#   gcloud run jobs execute f1-pipeline-trigger --region=us-central1 --project=f1optimizer

resource "google_cloud_run_v2_job" "f1_pipeline_trigger" {
  name     = "f1-pipeline-trigger"
  location = var.region
  labels   = local.common_labels

  template {
    template {
      timeout         = "900s" # compile + submit only; pipeline runs async
      service_account = google_service_account.training_sa.email

      containers {
        image   = "${var.region}-docker.pkg.dev/${var.project_id}/f1-optimizer/ml:latest"
        command = ["python"]
        args    = ["ml/dag/pipeline_runner.py"]

        resources {
          limits = {
            memory = "2Gi"
            cpu    = "2"
          }
        }

        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "REGION"
          value = var.region
        }
        env {
          name  = "MODELS_BUCKET"
          value = "gs://${google_storage_bucket.models.name}"
        }
        env {
          name  = "TRAINING_BUCKET"
          value = "gs://${google_storage_bucket.training.name}"
        }
      }
    }
  }

  depends_on = [
    google_project_service.ml_apis,
    google_project_iam_member.training_sa_pipeline_roles,
    google_storage_bucket.pipeline_runs,
  ]
}

# ── Outputs ───────────────────────────────────────────────────────────────────

output "pipeline_trigger_job" {
  description = "Cloud Run Job that compiles and submits the Vertex AI Pipeline"
  value       = google_cloud_run_v2_job.f1_pipeline_trigger.name
}

output "pipeline_runs_bucket" {
  description = "GCS bucket for Vertex AI Pipeline run artefacts"
  value       = "gs://${google_storage_bucket.pipeline_runs.name}"
}

output "vertex_console_urls" {
  description = "GCP console links for Vertex AI resources"
  value = {
    pipelines   = "https://console.cloud.google.com/vertex-ai/pipelines?project=${var.project_id}"
    training    = "https://console.cloud.google.com/vertex-ai/training/custom-jobs?project=${var.project_id}"
    experiments = "https://console.cloud.google.com/vertex-ai/experiments?project=${var.project_id}"
  }
}
