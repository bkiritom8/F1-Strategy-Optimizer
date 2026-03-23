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
# Cloud Router + Auto NAT on the existing VPC (no static IP cost)
# ---------------------------------------------------------------------------

resource "google_compute_router" "ingest" {
  name    = "f1-ingest-router"
  network = local.gap_vpc
  region  = var.region
  project = var.project_id
}

resource "google_compute_router_nat" "ingest" {
  name    = "f1-ingest-nat"
  router  = google_compute_router.ingest.name
  region  = var.region
  project = var.project_id

  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"
}

# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

output "ingest_sa_email" {
  description = "Ingest service account email"
  value       = google_service_account.ingest.email
}
