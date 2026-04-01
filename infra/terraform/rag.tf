/**
 * rag.tf — Vertex AI Vector Search index + endpoint + RAG ingestion Cloud Run Job
 */

# ── Vertex AI Vector Search index (768-dim, streaming upserts) ────────────────

resource "google_vertex_ai_index" "rag" {
  display_name = "f1-rag-index"
  region       = var.region
  description  = "F1 Strategy Optimizer RAG vector index"

  metadata {
    contents_delta_uri = "gs://${google_storage_bucket.models.name}/rag/vectors/"

    config {
      dimensions                  = 768
      approximate_neighbors_count = 150
      distance_measure_type       = "DOT_PRODUCT_DISTANCE"

      algorithm_config {
        tree_ah_config {
          leaf_node_embedding_count    = 1000
          leaf_nodes_to_search_percent = 10
        }
      }
    }
  }

  index_update_method = "STREAM_UPDATE"
  labels              = local.common_labels

  depends_on = [google_project_service.required_apis]
}

# ── Public endpoint ────────────────────────────────────────────────────────────

resource "google_vertex_ai_index_endpoint" "rag" {
  display_name            = "f1-rag-endpoint"
  region                  = var.region
  description             = "F1 RAG Vector Search public endpoint"
  public_endpoint_enabled = true
  labels                  = local.common_labels

  depends_on = [google_project_service.required_apis]
}

# ── Deploy index to endpoint ───────────────────────────────────────────────────
# Initial deployment can take 20–40 minutes; subsequent updates are faster.

resource "google_vertex_ai_index_endpoint_deployed_index" "rag" {
  index_endpoint    = google_vertex_ai_index_endpoint.rag.id
  index             = google_vertex_ai_index.rag.id
  deployed_index_id = "f1_rag_deployed"
  display_name      = "F1 RAG Deployed Index"

  automatic_resources {
    min_replica_count = 1
    max_replica_count = 2
  }

  timeouts {
    create = "60m"
    update = "60m"
  }

  depends_on = [
    google_vertex_ai_index.rag,
    google_vertex_ai_index_endpoint.rag,
  ]
}

# ── IAM: ingest SA needs aiplatform.user to embed + query Vector Search ────────

resource "google_project_iam_member" "ingest_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.ingest.email}"
}

# ── Cloud Run Job: RAG ingestion ───────────────────────────────────────────────
# Triggered manually or on a schedule after new data lands in GCS.
# Run: gcloud run jobs execute f1-rag-ingestion --region=us-central1 --project=f1optimizer

resource "google_cloud_run_v2_job" "rag_ingestion" {
  name     = "f1-rag-ingestion"
  location = var.region

  template {
    template {
      service_account = google_service_account.ingest.email
      max_retries     = 1
      timeout         = "3600s"

      containers {
        image = "${var.region}-docker.pkg.dev/${var.project_id}/f1-optimizer/rag:latest"

        env {
          name  = "PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "VECTOR_SEARCH_INDEX_ID"
          value = google_vertex_ai_index.rag.id
        }
        env {
          name  = "VECTOR_SEARCH_ENDPOINT_ID"
          value = google_vertex_ai_index_endpoint.rag.id
        }
        env {
          name  = "VECTOR_SEARCH_DEPLOYED_INDEX_ID"
          value = google_vertex_ai_index_endpoint_deployed_index.rag.deployed_index_id
        }
        env {
          name  = "GCS_DATA_BUCKET"
          value = google_storage_bucket.data_lake.name
        }
        env {
          name  = "GCS_MODELS_BUCKET"
          value = google_storage_bucket.models.name
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

  labels = local.common_labels

  depends_on = [
    google_project_service.required_apis,
    google_vertex_ai_index_endpoint_deployed_index.rag,
  ]
}

# ── Outputs ────────────────────────────────────────────────────────────────────

output "rag_index_id" {
  description = "Vertex AI Vector Search index resource name"
  value       = google_vertex_ai_index.rag.id
}

output "rag_endpoint_id" {
  description = "Vertex AI Vector Search endpoint resource name"
  value       = google_vertex_ai_index_endpoint.rag.id
}

output "rag_deployed_index_id" {
  description = "Deployed index ID used in Vector Search queries"
  value       = google_vertex_ai_index_endpoint_deployed_index.rag.deployed_index_id
}
