# infra/terraform/monitoring.tf
# Minimal Cloud Monitoring alerts for production

# Alert: API error rate > 5% over 5 minutes
resource "google_monitoring_alert_policy" "api_error_rate" {
  display_name = "F1 API High Error Rate"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Error rate > 5%"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"f1-strategy-api\" AND metric.type=\"run.googleapis.com/request_count\" AND metric.labels.response_code_class!=\"2xx\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.05
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_RATE"
      }
    }
  }

  notification_channels = []

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [google_project_service.required_apis]
}

# Alert: Cloud Run instance count drops to 0 (service down)
resource "google_monitoring_alert_policy" "api_instance_count" {
  display_name = "F1 API No Active Instances"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Instance count = 0"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"f1-strategy-api\" AND metric.type=\"run.googleapis.com/container/instance_count\""
      duration        = "120s"
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MEAN"
      }
    }
  }

  notification_channels = []

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [google_project_service.required_apis]
}

# Alert: P99 latency > 500ms (violates target SLA)
resource "google_monitoring_alert_policy" "api_latency_p99" {
  display_name = "F1 API P99 Latency > 500ms"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "P99 latency exceeds 500ms"
    condition_threshold {
      filter          = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"f1-strategy-api\" AND metric.type=\"run.googleapis.com/request_latencies\""
      duration        = "300s"
      comparison      = "COMPARISON_GT"
      threshold_value = 500
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_PERCENTILE_99"
      }
    }
  }

  notification_channels = []

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [google_project_service.required_apis]
}
