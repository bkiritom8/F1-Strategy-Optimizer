/**
 * F1 Strategy Optimizer - Terraform Variables
 */

variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "GCP region for resources"
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod"
  }
}

variable "api_max_instances" {
  description = "Maximum number of Cloud Run API instances"
  type        = number
  default     = 10
}

variable "api_min_instances" {
  description = "Minimum number of Cloud Run API instances"
  type        = number
  default     = 1
}

variable "alert_email" {
  description = "Email for monitoring alerts"
  type        = string
}

variable "enable_apis" {
  description = "Enable required GCP APIs"
  type        = bool
  default     = true
}

variable "budget_amount" {
  description = "Monthly budget amount in USD"
  type        = number
  default     = 200
}

variable "db_tier" {
  description = "Cloud SQL instance tier"
  type        = string
  default     = "db-f1-micro"
}

variable "db_name" {
  description = "PostgreSQL database name for the ingestion job"
  type        = string
  default     = "f1_strategy"
}
