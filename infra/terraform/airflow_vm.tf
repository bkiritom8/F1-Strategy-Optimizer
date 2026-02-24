/**
 * F1 Strategy Optimizer - GCE VM for Airflow
 *
 * Provisions a Container-Optimized OS VM running Airflow via Docker Compose.
 * DAGs are synced from gs://f1optimizer-training/dags/ every 5 minutes.
 *
 * Deploy:
 *   terraform -chdir=infra/terraform apply -var-file=dev.tfvars
 *
 * After apply, deploy DAGs:
 *   bash Data-Pipeline/scripts/deploy_dags.sh
 */

# ── IAM: grant Airflow SA access to pull image + read/write GCS ───────────────

resource "google_project_iam_member" "airflow_artifact_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.airflow_sa.email}"
}

resource "google_project_iam_member" "airflow_gcs_viewer" {
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.airflow_sa.email}"
}

resource "google_project_iam_member" "airflow_training_writer" {
  project = var.project_id
  role    = "roles/storage.objectAdmin"
  member  = "serviceAccount:${google_service_account.airflow_sa.email}"
}

# ── GCE VM: f1-airflow-vm ─────────────────────────────────────────────────────

resource "google_compute_instance" "f1_airflow_vm" {
  name         = "f1-airflow-vm"
  machine_type = "e2-standard-2"
  zone         = "us-central1-a"

  tags = ["airflow", "http-server"]

  boot_disk {
    initialize_params {
      image = "cos-cloud/cos-stable"
      size  = 50
      type  = "pd-standard"
    }
  }

  network_interface {
    network = "default"
    access_config {}
  }

  metadata = {
    startup-script  = file("${path.module}/scripts/airflow_startup.sh")
    gcs-dags-bucket = "gs://${var.project_id}-training/dags"
    airflow-image   = "us-central1-docker.pkg.dev/${var.project_id}/f1-optimizer/airflow:latest"
  }

  service_account {
    email  = google_service_account.airflow_sa.email
    scopes = ["cloud-platform"]
  }

  labels = merge(local.common_labels, {
    component   = "airflow"
    environment = var.environment
    managed_by  = "terraform"
    project     = "f1-strategy-optimizer"
  })

  depends_on = [
    google_project_service.required_apis,
    google_project_iam_member.airflow_artifact_reader,
    google_project_iam_member.airflow_gcs_viewer,
  ]
}

# ── Firewall: allow Airflow UI on port 8080 ───────────────────────────────────

resource "google_compute_firewall" "allow_airflow_ui" {
  name    = "allow-airflow-ui-${var.environment}"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["8080"]
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["airflow"]
  description   = "Allow inbound HTTP traffic to Airflow webserver (port 8080)"
}

# ── Outputs ───────────────────────────────────────────────────────────────────

output "airflow_vm_ip" {
  description = "Public IP address of the Airflow VM"
  value       = google_compute_instance.f1_airflow_vm.network_interface[0].access_config[0].nat_ip
}

output "airflow_url" {
  description = "Airflow UI URL"
  value       = "http://${google_compute_instance.f1_airflow_vm.network_interface[0].access_config[0].nat_ip}:8080"
}
