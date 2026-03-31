###############################################################################
# Firestore — user store for F1 Strategy Optimizer
#
# Collections:
#   users/              — user profiles (no credentials)
#   user_credentials/   — password hashes (separate, restricted)
#   audit_log/          — GDPR append-only audit entries
#
# Mode: NATIVE (required for real-time + transactions)
# Location: nam5 (US multi-region, same as Cloud Run us-central1)
###############################################################################

resource "google_project_service" "firestore" {
  project            = var.project_id
  service            = "firestore.googleapis.com"
  disable_on_destroy = false
}

resource "google_firestore_database" "default" {
  project                     = var.project_id
  name                        = "(default)"
  location_id                 = "nam5"
  type                        = "FIRESTORE_NATIVE"
  concurrency_mode            = "OPTIMISTIC"
  app_engine_integration_mode = "DISABLED"

  depends_on = [google_project_service.firestore]
}

# Composite index: users collection — query by role, order by created_at
resource "google_firestore_index" "users_by_role" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "users"

  fields {
    field_path = "role"
    order      = "ASCENDING"
  }
  fields {
    field_path = "created_at"
    order      = "DESCENDING"
  }

  depends_on = [google_firestore_database.default]
}

# Composite index: audit_log — query by username, order by timestamp
resource "google_firestore_index" "audit_by_user" {
  project    = var.project_id
  database   = google_firestore_database.default.name
  collection = "audit_log"

  fields {
    field_path = "username"
    order      = "ASCENDING"
  }
  fields {
    field_path = "timestamp"
    order      = "DESCENDING"
  }

  depends_on = [google_firestore_database.default]
}

# IAM: Cloud Run service account can read/write Firestore
resource "google_project_iam_member" "cloudrun_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.api_sa.email}"
}
