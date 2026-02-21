# Monitoring

Observability for training runs and the serving API.

## Current state

- Cloud Logging: all components log structured JSON
- Cloud Monitoring dashboards: provisioned via Terraform in `infra/terraform/`
- Pub/Sub alerts: topics `f1-alerts-dev`, `f1-predictions-dev`

## Planned

- Vertex AI Experiments integration (model metrics)
- Latency / error-rate dashboards for `f1-strategy-api-dev`
- Alerting on training job failures via `f1-alerts-dev` Pub/Sub
