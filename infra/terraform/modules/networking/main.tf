/**
 * Networking Module
 * Creates VPC network and subnets for F1 Strategy Optimizer
 */

resource "google_compute_network" "vpc" {
  name                    = "${var.network_name}-${var.environment}"
  project                 = var.project_id
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "primary" {
  name          = "${var.network_name}-${var.environment}-primary"
  project       = var.project_id
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.0.0.0/20"
}

output "network_id" {
  description = "VPC network ID (self_link)"
  value       = google_compute_network.vpc.id
}
