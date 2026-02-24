# Monitoring — F1 Strategy Optimizer

Observability for the API, training runs, and the data pipeline.

## Local Monitoring (Docker Compose)

Prometheus and Grafana run locally via `docker-compose.f1.yml`:

```bash
docker-compose -f docker-compose.f1.yml up prometheus grafana
```

| Service | URL | Credentials |
|---|---|---|
| Prometheus | http://localhost:9090 | — |
| Grafana | http://localhost:3000 | admin / admin |

Prometheus scrapes:
- `api:8000/metrics` — FastAPI request metrics
- `localhost:9090` — Prometheus self-monitoring

Config: `docker/prometheus.yml`

## GCP Monitoring

| Component | Status |
|---|---|
| Cloud Logging (structured JSON) | Active — all services |
| Cloud Monitoring dashboards | Provisioned via Terraform in `infra/terraform/` |
| Pub/Sub alert topics | `f1-alerts-dev`, `f1-predictions-dev` |
| Airflow task logs | `/opt/airflow/logs/` on GCE VM + Cloud Logging |

## Airflow Pipeline Monitoring

The Airflow UI shows task-level status and logs for all pipeline runs:

- **Local**: http://localhost:8080
- **GCP**: `http://$(terraform -chdir=infra/terraform output -raw airflow_vm_ip):8080`

Failed tasks trigger email alerts (configured via `SMTP` Airflow connection)
and optional Slack alerts (set `SLACK_WEBHOOK_URL` in `.env`).

## Planned

- Vertex AI Experiments integration (model training metrics per run)
- Grafana dashboard for API latency and error rates
- Alerting on Vertex AI training job failures via `f1-alerts-dev` Pub/Sub
- Data drift detection on processed Parquet files
