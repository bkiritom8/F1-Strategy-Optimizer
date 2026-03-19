/**
 * lap_times_vms.tf — 8 e2-micro spot VMs that re-fetch all F1 lap times
 *                    from Jolpica (1996–2025) with correct pagination.
 *
 * Each VM gets its own ephemeral external IP (free while running) so each
 * worker hits Jolpica from a distinct IP, staying under the 500 req/hr cap.
 *
 * Year splits (designed for ≤3 h wall-clock at 1 req/8 s):
 *   W1: 1996-1999  ~65 races   ~1.73 h
 *   W2: 2000-2003  ~67 races   ~1.79 h
 *   W3: 2004-2007  ~72 races   ~1.92 h
 *   W4: 2008-2011  ~73 races   ~1.95 h
 *   W5: 2012-2015  ~77 races   ~2.05 h
 *   W6: 2016-2017  ~41 races   ~1.10 h
 *
 * 2018+ data comes from FastF1 (richer telemetry: sector times, tyre compounds, speeds)
 *
 * Estimated cost: 8 × $0.0025/hr × 3 h ≈ $0.06  (well under $10 budget)
 *
 * Output GCS path: raw/lap_times_v2/{year}/round_{round:02d}.parquet
 */

locals {
  lt_bucket = "f1optimizer-data-lake"
  lt_sa     = google_service_account.ingest.email  # reuse existing SA

  # Workers with ephemeral external IPs (unique Jolpica source IP each)
  # Jolpica only for pre-2018; FastF1 handles 2018+ with richer telemetry
  lt_workers_ext = {
    "1" = { year_start = 1996, year_end = 1999 }
    "2" = { year_start = 2000, year_end = 2003 }
    "4" = { year_start = 2008, year_end = 2011 }
    "5" = { year_start = 2012, year_end = 2015 }
    "6" = { year_start = 2016, year_end = 2017 }
  }

  # Worker 3 uses Cloud NAT egress (no external IP, avoids IN_USE_ADDRESSES quota)
  lt_workers_nat = {
    "3" = { year_start = 2004, year_end = 2007 }
  }
}

# ---------------------------------------------------------------------------
# IAM: let the SA stop itself (needed for self-termination)
# ---------------------------------------------------------------------------

resource "google_project_iam_member" "ingest_instance_admin" {
  project = var.project_id
  role    = "roles/compute.instanceAdmin.v1"
  member  = "serviceAccount:${local.lt_sa}"
}

# ---------------------------------------------------------------------------
# 8 spot VMs
# ---------------------------------------------------------------------------

# Workers 1,2,4-8: ephemeral external IP (unique Jolpica source IP)
resource "google_compute_instance" "lap_times_worker" {
  for_each = local.lt_workers_ext

  name         = "f1-lt-worker-${each.key}"
  machine_type = "e2-micro"
  zone         = "${var.region}-a"
  project      = var.project_id

  labels = merge(local.common_labels, {
    role       = "lap-times-worker"
    worker_id  = each.key
    year_start = tostring(each.value.year_start)
    year_end   = tostring(each.value.year_end)
  })

  scheduling {
    preemptible         = true
    automatic_restart   = false
    on_host_maintenance = "TERMINATE"
  }

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
      type  = "pd-standard"
    }
  }

  network_interface {
    network    = "f1-optimizer-network-dev"
    subnetwork = "f1-optimizer-network-dev-primary"
    access_config {}
  }

  service_account {
    email  = local.lt_sa
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script = templatefile(
      "${path.module}/startup_lap_times.sh.tftpl",
      {
        worker_id  = each.key
        year_start = tostring(each.value.year_start)
        year_end   = tostring(each.value.year_end)
        bucket     = local.lt_bucket
      }
    )
  }

  depends_on = [
    google_service_account.ingest,
    google_project_iam_member.ingest_storage,
    google_project_iam_member.ingest_logging,
    google_project_iam_member.ingest_instance_admin,
  ]
}

# Worker 3: Cloud NAT egress only (saves the IN_USE_ADDRESSES quota slot)
resource "google_compute_instance" "lap_times_worker_nat" {
  for_each = local.lt_workers_nat

  name         = "f1-lt-worker-${each.key}"
  machine_type = "e2-micro"
  zone         = "${var.region}-a"
  project      = var.project_id

  labels = merge(local.common_labels, {
    role       = "lap-times-worker"
    worker_id  = each.key
    year_start = tostring(each.value.year_start)
    year_end   = tostring(each.value.year_end)
  })

  scheduling {
    preemptible         = true
    automatic_restart   = false
    on_host_maintenance = "TERMINATE"
  }

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 10
      type  = "pd-standard"
    }
  }

  network_interface {
    network    = "f1-optimizer-network-dev"
    subnetwork = "f1-optimizer-network-dev-primary"
    # No access_config — uses Cloud NAT for egress
  }

  service_account {
    email  = local.lt_sa
    scopes = ["cloud-platform"]
  }

  metadata = {
    startup-script = templatefile(
      "${path.module}/startup_lap_times.sh.tftpl",
      {
        worker_id  = each.key
        year_start = tostring(each.value.year_start)
        year_end   = tostring(each.value.year_end)
        bucket     = local.lt_bucket
      }
    )
  }

  depends_on = [
    google_service_account.ingest,
    google_project_iam_member.ingest_storage,
    google_project_iam_member.ingest_logging,
    google_project_iam_member.ingest_instance_admin,
    google_compute_router_nat.ingest,
  ]
}

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

output "lt_worker_names" {
  description = "Lap-times worker VM names"
  value = merge(
    { for k, v in google_compute_instance.lap_times_worker     : k => v.name },
    { for k, v in google_compute_instance.lap_times_worker_nat : k => v.name },
  )
}
