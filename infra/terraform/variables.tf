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

variable "api_max_concurrent_requests" {
  description = "Max concurrent requests per Cloud Run instance. 40 is tuned for LLM-heavy workloads (2-5s Gemini latency). Increase for lighter I/O-bound routes."
  type        = number
  default     = 40
}

variable "api_cpu_target_utilization" {
  description = "CPU utilization percentage that triggers autoscaling. New instances spin up when average CPU exceeds this; instances are removed when it drops back below."
  type        = number
  default     = 85
}

variable "alert_emails" {
  description = "List of email addresses to receive monitoring alerts. Add all GCP project members here — one notification channel is created per address."
  type        = list(string)
  default     = ["ajithsri3103@gmail.com"]
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

variable "email_from" {
  description = "Sender address used for verification emails (must match the Gmail account in smtp-user secret)"
  type        = string
}

variable "app_base_url" {
  description = "Frontend root URL used to build email verification links"
  type        = string
  default     = "https://f1optimizer.app"
}

variable "allowed_origins" {
  description = "Comma-separated list of allowed CORS origins"
  type        = string
  default     = "https://f1optimizer.web.app,https://f1optimizer.firebaseapp.com"
}
