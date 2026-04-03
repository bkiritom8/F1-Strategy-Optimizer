# Infrastructure as Code (IaC)

Terraform and Cloud Build configurations for the F1 Strategy Optimizer on Google Cloud Platform.

## Contents

- **terraform/**: Modules and configurations for:
  - **GCS Buckets**: Data lake for raw and processed F1 telemetry.
  - **Cloud Run**: Serverless deployment for the FastAPI backend and ingestion workers.
  - **Firestore**: User authentication and configuration database.
  - **Vertex AI Search**: Vector indexes for the RAG intelligence system.
  - **IAM**: Access control and service accounts.

## Usage

1. Initialize Terraform:
   ```bash
   cd terraform
   terraform init
   ```
2. Plan changes:
   ```bash
   terraform plan -var-file="prod.tfvars"
   ```
3. Apply to production:
   ```bash
   terraform apply -var-file="prod.tfvars"
   ```

> [!CAUTION]
> Always verify the `terraform plan` output for any destructive operations on production buckets.
