/**
 * Compute Module - Cloud Run
 * Deploys the F1 Strategy API as a serverless Cloud Run service
 */

resource "google_cloud_run_v2_service" "api" {
  name     = "${var.service_name}-${var.environment}"
  location = var.region
  project  = var.project_id

  template {
    annotations = {
      # Scale out when average CPU across active instances exceeds this threshold.
      # New instances are added until utilization drops back below the target.
      "autoscaling.knative.dev/cpuTargetUtilizationPercentage" = tostring(var.cpu_target_utilization)
    }

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    max_instance_request_concurrency = var.max_concurrent_requests

    containers {
      image = var.container_image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          memory = var.memory
          cpu    = var.cpu
        }
      }

      dynamic "env" {
        for_each = var.env_vars
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.secret_env_vars
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }
    }

    timeout = "${var.timeout_seconds}s"
  }

  labels = var.labels
}

output "service_url" {
  description = "Cloud Run service URL"
  value       = google_cloud_run_v2_service.api.uri
}
