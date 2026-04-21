# infra/terraform/monitoring.tf
# Minimal Cloud Monitoring alerts for production

# Custom metric descriptors must exist before alert policies that reference them.

resource "google_monitoring_metric_descriptor" "drift_psi" {
  project      = var.project_id
  type         = "custom.googleapis.com/f1/drift_psi"
  metric_kind  = "GAUGE"
  value_type   = "DOUBLE"
  unit         = "1"
  display_name = "ML Feature Drift PSI"
  description  = "Population Stability Index for ML feature drift detection"

  labels {
    key         = "model_name"
    value_type  = "STRING"
    description = "Name of the ML model being monitored"
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_monitoring_metric_descriptor" "accuracy_degradation_pct" {
  project      = var.project_id
  type         = "custom.googleapis.com/f1/accuracy_degradation_pct"
  metric_kind  = "GAUGE"
  value_type   = "DOUBLE"
  unit         = "%"
  display_name = "ML Model Accuracy Degradation"
  description  = "Percentage accuracy degradation from baseline for a given ML model"

  labels {
    key         = "model_name"
    value_type  = "STRING"
    description = "Name of the ML model being monitored"
  }

  depends_on = [google_project_service.required_apis]
}

resource "google_monitoring_metric_descriptor" "retraining_triggered" {
  project      = var.project_id
  type         = "custom.googleapis.com/f1/retraining_triggered"
  metric_kind  = "GAUGE"
  value_type   = "INT64"
  unit         = "1"
  display_name = "ML Retraining Triggered"
  description  = "Counter incremented each time an ML retraining job is triggered"

  depends_on = [google_project_service.required_apis]
}

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

  notification_channels = local.all_notification_channels

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

  notification_channels = local.all_notification_channels

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [google_project_service.required_apis]
}

# Alert: ML model critical drift detected (PSI >= 0.25)
resource "google_monitoring_alert_policy" "ml_drift_critical" {
  display_name = "F1 ML Critical Feature Drift"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Drift PSI >= 0.25 (critical threshold)"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/f1/drift_psi\" AND resource.type=\"global\""
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0.25
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MAX"
        group_by_fields    = ["metric.labels.model_name"]
      }
    }
  }

  notification_channels = local.all_notification_channels

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [google_monitoring_metric_descriptor.drift_psi]
}

# Alert: ML model accuracy degraded beyond threshold
resource "google_monitoring_alert_policy" "ml_accuracy_degraded" {
  display_name = "F1 ML Model Accuracy Degraded"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Accuracy degradation > 20%"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/f1/accuracy_degradation_pct\" AND resource.type=\"global\""
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 20
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_MAX"
        group_by_fields    = ["metric.labels.model_name"]
      }
    }
  }

  notification_channels = local.all_notification_channels

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [google_monitoring_metric_descriptor.accuracy_degradation_pct]
}

# Alert: Retraining was triggered (informational - notify stakeholders)
resource "google_monitoring_alert_policy" "ml_retraining_triggered" {
  display_name = "F1 ML Retraining Triggered"
  project      = var.project_id
  combiner     = "OR"

  conditions {
    display_name = "Retraining event fired"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/f1/retraining_triggered\" AND resource.type=\"global\""
      duration        = "0s"
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      aggregations {
        alignment_period   = "300s"
        per_series_aligner = "ALIGN_SUM"
      }
    }
  }

  notification_channels = local.all_notification_channels

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [google_monitoring_metric_descriptor.retraining_triggered]
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
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_PERCENTILE_99"
      }
    }
  }

  notification_channels = local.all_notification_channels

  alert_strategy {
    auto_close = "1800s"
  }

  depends_on = [google_project_service.required_apis]
}
