# API — F1 Strategy Serving

FastAPI service deployed on Cloud Run.

## Endpoint

`https://f1-strategy-api-dev-694267183904.us-central1.run.app`

## Source

`src/api/main.py` — uvicorn on port 8000.

## Docker image

Built from `docker/Dockerfile.api`, pushed to
`us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api:latest`.

## Deployment

Cloud Build pushes on every commit to the `pipeline` branch.
Cloud Run picks up `:latest` automatically.

## Target SLA

< 500ms P99 latency.
