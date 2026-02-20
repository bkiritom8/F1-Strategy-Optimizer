variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "temp_location" {
  description = "GCS temp location for Dataflow"
  type        = string
}

variable "staging_location" {
  description = "GCS staging location for Dataflow"
  type        = string
}

variable "labels" {
  description = "Resource labels"
  type        = map(string)
  default     = {}
}
