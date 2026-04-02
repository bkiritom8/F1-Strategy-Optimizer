/**
 * lap_times_vms.tf — Lap-times ingest workers (DECOMMISSIONED)
 *
 * The 6 spot VMs that fetched Jolpica lap times (1996-2017) are no longer
 * needed — all historical data is already in GCS. VMs removed to save cost.
 * IAM binding kept: ingest SA still runs the RAG ingestion Cloud Run job.
 */

resource "google_project_iam_member" "ingest_instance_admin" {
  project = var.project_id
  role    = "roles/compute.instanceAdmin.v1"
  member  = "serviceAccount:${google_service_account.ingest.email}"
}
