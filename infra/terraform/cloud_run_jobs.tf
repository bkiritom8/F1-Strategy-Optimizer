/**
 * cloud_run_jobs.tf — ingest infrastructure (service account + Cloud Run Jobs).
 *
 * 10 parallel tasks:
 *   Tasks 0-8: FastF1 10Hz telemetry, one year per task (2018-2026)
 *   Task 9:    Jolpica historical data (1950-2017)
 *
 * Containers are ephemeral — Cloud Run tears them down automatically when
 * each task completes. No manual cleanup required.
 *
 * Run:
 *   gcloud run jobs execute f1-ingest --region=us-central1 --project=f1optimizer
 */

# ---------------------------------------------------------------------------
# Service account (reuse if already exists, else create)
# ---------------------------------------------------------------------------

resource "google_service_account" "ingest" {
  account_id   = "f1-ingest-sa"
  display_name = "F1 Ingest Job Service Account"
}

resource "google_project_iam_member" "ingest_storage" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.ingest.email}"
}

resource "google_project_iam_member" "ingest_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.ingest.email}"
}

resource "google_project_iam_member" "ingest_registry_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.ingest.email}"
}


# ---------------------------------------------------------------------------
# Cloud Run Job — parallel ingest (10 tasks)
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_job" "ingest" {
  name     = "f1-ingest"
  location = var.region
  labels   = local.common_labels

  template {
    task_count  = 10
    parallelism = 10

    template {
      max_retries     = 2
      timeout         = "86400s"
      service_account = google_service_account.ingest.email

      containers {
        # Placeholder until Cloud Build pushes ingest:latest on first pipeline push.
        image = "us-docker.pkg.dev/cloudrun/container/placeholder:latest"

        env {
          name  = "GCS_BUCKET"
          value = "f1optimizer-data-lake"
        }

        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.required_apis,
    google_service_account.ingest,
    google_project_iam_member.ingest_storage,
  ]
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "ingest_sa_email" {
  description = "Ingest service account email"
  value       = google_service_account.ingest.email
}

output "ingest_job_name" {
  description = "Cloud Run Job name for manual execution"
  value       = google_cloud_run_v2_job.ingest.name
}
