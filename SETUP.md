# F1 Strategy Optimizer - Setup Guide

Complete setup guide for local development and production deployment.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Local Development Setup](#local-development-setup)
3. [Running the System](#running-the-system)
4. [Testing](#testing)
5. [Production Deployment](#production-deployment)
6. [Troubleshooting](#troubleshooting)

## Prerequisites

### Required Software

- **Docker Desktop** (Windows/macOS) or **Docker Engine + Docker Compose** (Linux)
  - Minimum version: Docker 20.10+, Docker Compose 2.0+
- **Python 3.10+**
- **Git**
- **8GB RAM minimum** (16GB recommended)

### Optional (for development)

- `make` (for Makefile commands)
- `pre-commit` (for git hooks)
- GCP CLI (`gcloud`) for production deployment

## Local Development Setup

### 1. Clone Repository

```bash
git clone <repository-url>
cd test
git checkout claude/f1-optimizer-pipeline-KC0J8
```

### 2. Create Python Virtual Environment

**Linux/macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-f1.txt
```

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-f1.txt
```

**Windows (CMD):**
```cmd
python -m venv venv
.\venv\Scripts\activate.bat
pip install -r requirements-f1.txt
```

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and configure your settings
# For local development, defaults should work fine
```

### 4. Initialize Database

```bash
python scripts/init_db.py
```

This will:
- Create necessary directories
- Initialize mock BigQuery database
- Create sample data
- Verify environment

## Running the System

### Start All Services

```bash
docker-compose -f docker-compose.f1.yml up -d
```

This starts:
- **Airflow** (webserver + scheduler)
- **PostgreSQL** (Airflow metadata)
- **Redis** (Celery backend)
- **Mock BigQuery** (local data warehouse)
- **Mock Pub/Sub** (message broker)
- **Mock Dataflow** (pipeline executor)
- **FastAPI** (strategy API)
- **Prometheus** (metrics)
- **Grafana** (dashboards)
- **Ray** (distributed ML)

### Verify Services

```bash
# Check all containers are running
docker-compose -f docker-compose.f1.yml ps

# Check service health
curl http://localhost:8080/health  # Airflow
curl http://localhost:8000/health  # API
curl http://localhost:9050/health  # Mock BigQuery
curl http://localhost:9051/health  # Mock Dataflow
```

### Access Web Interfaces

| Service | URL | Credentials |
|---------|-----|-------------|
| Airflow UI | http://localhost:8080 | admin / admin |
| API Docs | http://localhost:8000/docs | See authentication below |
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | None |
| Ray Dashboard | http://localhost:8265 | None |

### API Authentication

Get an access token:

```bash
curl -X POST http://localhost:8000/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=admin"
```

Use the token:

```bash
curl http://localhost:8000/users/me \
  -H "Authorization: Bearer <your-token>"
```

### Run Airflow DAG

```bash
# Trigger manually via CLI
docker-compose -f docker-compose.f1.yml exec airflow-scheduler \
  airflow dags trigger f1_data_ingestion

# Or via UI: http://localhost:8080
# Navigate to DAGs → f1_data_ingestion → Trigger DAG
```

### View Logs

```bash
# All services
docker-compose -f docker-compose.f1.yml logs -f

# Specific service
docker-compose -f docker-compose.f1.yml logs -f api
docker-compose -f docker-compose.f1.yml logs -f airflow-scheduler

# Airflow task logs
docker-compose -f docker-compose.f1.yml exec airflow-scheduler \
  airflow tasks logs f1_data_ingestion initialize_metrics <execution-date>
```

## Testing

### Run All Tests

```bash
pytest tests/ -v
```

### Unit Tests Only

```bash
pytest tests/unit/ -v
```

### Integration Tests (requires Docker)

```bash
pytest tests/integration/ -v --docker
```

### Test with Coverage

```bash
pytest tests/ -v --cov=src --cov-report=html
# View coverage report: open htmlcov/index.html
```

### Load Testing

```bash
locust -f tests/load/locustfile.py --host=http://localhost:8000
# Open http://localhost:8089
```

## Production Deployment

### 1. GCP Project Setup

```bash
# Install gcloud CLI
# https://cloud.google.com/sdk/docs/install

# Authenticate
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Enable billing
gcloud billing accounts list
gcloud billing projects link YOUR_PROJECT_ID --billing-account=BILLING_ACCOUNT_ID
```

### 2. Terraform Deployment

```bash
cd terraform

# Create backend bucket
gsutil mb gs://YOUR_PROJECT_ID-terraform-state

# Initialize Terraform
terraform init

# Review plan
terraform plan \
  -var="project_id=YOUR_PROJECT_ID" \
  -var="alert_email=your-email@example.com"

# Apply infrastructure
terraform apply \
  -var="project_id=YOUR_PROJECT_ID" \
  -var="alert_email=your-email@example.com"
```

### 3. Deploy Application

```bash
# Build and push Docker images
docker build -t gcr.io/YOUR_PROJECT_ID/f1-api:latest -f docker/Dockerfile.api .
docker push gcr.io/YOUR_PROJECT_ID/f1-api:latest

# Deploy to Cloud Run (automated by Terraform)
# Or manually:
gcloud run deploy f1-strategy-api \
  --image gcr.io/YOUR_PROJECT_ID/f1-api:latest \
  --region us-central1 \
  --platform managed \
  --allow-unauthenticated
```

### 4. Configure Secrets

```bash
# Create secrets in Secret Manager
echo -n "your-ergast-api-key" | \
  gcloud secrets create ergast-api-key --data-file=-

echo -n "your-jwt-secret" | \
  gcloud secrets create jwt-secret --data-file=-
```

### 5. Deploy Airflow DAGs

```bash
# Copy DAGs to Cloud Composer (if using)
gsutil cp airflow/dags/* gs://YOUR_COMPOSER_BUCKET/dags/

# Or deploy to Cloud Run Airflow instance
./scripts/deploy_dags.sh
```

## Troubleshooting

### Docker Containers Won't Start

```bash
# Check Docker daemon
docker info

# Reset Docker environment
docker-compose -f docker-compose.f1.yml down -v
docker system prune -a
docker-compose -f docker-compose.f1.yml up -d
```

### Port Already in Use

```bash
# Find process using port (e.g., 8080)
# Linux/macOS:
lsof -i :8080

# Windows:
netstat -ano | findstr :8080

# Kill the process or change port in docker-compose.f1.yml
```

### Airflow DAGs Not Appearing

```bash
# Check DAG folder permissions
chmod -R 755 airflow/dags/

# Restart scheduler
docker-compose -f docker-compose.f1.yml restart airflow-scheduler

# Check for syntax errors
docker-compose -f docker-compose.f1.yml exec airflow-scheduler \
  python /opt/airflow/dags/f1_data_ingestion.py
```

### Database Connection Errors

```bash
# Verify PostgreSQL is running
docker-compose -f docker-compose.f1.yml ps postgres

# Check connection
docker-compose -f docker-compose.f1.yml exec postgres \
  psql -U airflow -d airflow -c "SELECT 1;"

# Reinitialize database
docker-compose -f docker-compose.f1.yml down -v
python scripts/init_db.py
docker-compose -f docker-compose.f1.yml up -d
```

### Mock Service Connection Issues

```bash
# Check service is running
docker-compose -f docker-compose.f1.yml ps mock-bigquery

# Check logs
docker-compose -f docker-compose.f1.yml logs mock-bigquery

# Restart service
docker-compose -f docker-compose.f1.yml restart mock-bigquery
```

### Python Import Errors

```bash
# Verify Python path
python -c "import sys; print('\n'.join(sys.path))"

# Reinstall dependencies
pip install -r requirements-f1.txt --force-reinstall

# Check module installation
pip list | grep fastf1
```

### Windows-Specific Issues

**Path too long errors:**
```powershell
# Enable long paths
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

**WSL2 recommended:**
```powershell
# Install WSL2 for better Docker performance
wsl --install
wsl --set-default-version 2
```

### Memory Issues

```bash
# Increase Docker memory limit
# Docker Desktop → Settings → Resources → Memory → 8GB+

# Reduce service count for development
# Comment out non-essential services in docker-compose.f1.yml
```

### Permission Denied Errors (Linux)

```bash
# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker

# Fix file permissions
sudo chown -R $USER:$USER .
```

## Performance Optimization

### Local Development

- **Reduce workers**: Set `NUM_WORKERS=1` in `.env`
- **Disable GPU**: Set `USE_GPU=false`
- **Use smaller datasets**: Configure `LIMIT_DATA_SIZE=true`
- **Cache aggressively**: Enable FastF1 cache

### Production

- **Autoscaling**: Configured in Terraform
- **Database indexing**: Automatically applied
- **CDN caching**: Configure Cloud CDN
- **Monitoring**: Check Grafana dashboards

## Next Steps

1. **Read the documentation**: `docs/` directory
2. **Explore sample DAGs**: `airflow/dags/`
3. **Run tests**: `pytest tests/ -v`
4. **Check API endpoints**: http://localhost:8000/docs
5. **Monitor metrics**: http://localhost:3000

## Support

- **Issues**: Create a GitHub issue
- **Documentation**: See `docs/` directory
- **API Reference**: http://localhost:8000/docs

---

**Last Updated**: 2026-02-14
**Version**: 1.0.0
