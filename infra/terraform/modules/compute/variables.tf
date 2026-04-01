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

variable "service_name" {
  description = "Cloud Run service name"
  type        = string
}

variable "container_image" {
  description = "Container image URI"
  type        = string
}

variable "max_instances" {
  description = "Maximum number of Cloud Run instances"
  type        = number
  default     = 10
}

variable "min_instances" {
  description = "Minimum number of Cloud Run instances"
  type        = number
  default     = 1
}

variable "memory" {
  description = "Memory limit per instance"
  type        = string
  default     = "512Mi"
}

variable "cpu" {
  description = "CPU limit per instance"
  type        = string
  default     = "1"
}

variable "timeout_seconds" {
  description = "Request timeout in seconds"
  type        = number
  default     = 60
}

variable "max_concurrent_requests" {
  description = "Max concurrent requests per Cloud Run instance (max_instance_request_concurrency). Tune based on workload: lower for CPU-heavy LLM calls, higher for I/O-bound services."
  type        = number
  default     = 80
}

variable "cpu_target_utilization" {
  description = "Target CPU utilization percentage (1-100) that triggers autoscaling. Cloud Run adds instances when average CPU across active instances exceeds this value, and removes them when it drops below."
  type        = number
  default     = 85

  validation {
    condition     = var.cpu_target_utilization >= 1 && var.cpu_target_utilization <= 100
    error_message = "cpu_target_utilization must be between 1 and 100."
  }
}

variable "env_vars" {
  description = "Environment variables for the container"
  type        = map(string)
  default     = {}
}

variable "labels" {
  description = "Resource labels"
  type        = map(string)
  default     = {}
}
