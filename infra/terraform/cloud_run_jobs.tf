/**
 * cloud_run_jobs.tf — shared ingest infrastructure (service account + NAT).
 *
 * Gap-fill Cloud Run Jobs have been replaced by e2-micro spot VMs
 * defined in lap_times_vms.tf.
 */

locals {
  gap_vpc    = "f1-optimizer-network-dev"
  gap_subnet = "f1-optimizer-network-dev-primary"
}

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
# Outputs
# ---------------------------------------------------------------------------

output "ingest_sa_email" {
  description = "Ingest service account email"
  value       = google_service_account.ingest.email
}
