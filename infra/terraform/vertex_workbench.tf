/**
 * F1 Strategy Optimizer - Vertex AI Workbench
 * Managed notebook instance for the ML team.
 * Apply with: terraform -chdir=infra/terraform apply -var-file=dev.tfvars
 */

# ── Workbench instance ────────────────────────────────────────────────────────

resource "google_project_service" "notebooks_api" {
  service            = "notebooks.googleapis.com"
  disable_on_destroy = false
}

resource "google_workbench_instance" "f1_ml_workbench" {
  name     = "f1-ml-workbench"
  location = "us-central1-a" # hardcoded to avoid GPU capacity race conditions

  gce_setup {
    machine_type = "n1-standard-4"

    service_accounts {
      email = google_service_account.training_sa.email
    }

    # Pull startup script from GCS on every boot
    metadata = {
      startup-script-url   = "gs://f1optimizer-training/startup/workbench_startup.sh"
      idle-timeout-seconds = "3600" # 60-minute auto-shutdown
    }

    boot_disk {
      disk_size_gb = 150
      disk_type    = "PD_SSD"
    }

    data_disks {
      disk_size_gb = 200
      disk_type    = "PD_STANDARD"
    }
  }

  labels = {
    project     = "f1-strategy-optimizer"
    environment = var.environment
    managed_by  = "terraform"
    team        = "ml"
  }
}

# ── IAM grants for f1-training-dev SA ────────────────────────────────────────

locals {
  training_sa_roles = [
    "roles/cloudsql.client",
    "roles/storage.admin",
    "roles/aiplatform.user",
    "roles/secretmanager.secretAccessor",
    "roles/pubsub.editor",
    "roles/logging.logWriter",
    "roles/artifactregistry.writer",
    "roles/aiplatform.customCodeServiceAgent",
  ]
}

resource "google_project_iam_member" "f1_training_roles" {
  for_each = toset(local.training_sa_roles)

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.training_sa.email}"
}

# ── Outputs ───────────────────────────────────────────────────────────────────

output "workbench_instance_name" {
  description = "Vertex AI Workbench instance name"
  value       = google_workbench_instance.f1_ml_workbench.name
}

output "workbench_console_url" {
  description = "GCP console link for the Workbench instance"
  value       = "https://console.cloud.google.com/vertex-ai/workbench/instances?project=${var.project_id}"
}
