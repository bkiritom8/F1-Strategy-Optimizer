/**
 * Pub/Sub Module
 * Creates Pub/Sub topics and subscriptions for F1 event streaming
 */

resource "google_pubsub_topic" "topics" {
  for_each = toset(var.topics)

  name    = "${each.value}-${var.environment}"
  project = var.project_id

  labels = var.labels
}

output "topic_names" {
  description = "Pub/Sub topic names"
  value       = { for k, v in google_pubsub_topic.topics : k => v.name }
}
