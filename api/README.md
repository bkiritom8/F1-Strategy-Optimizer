# API — F1 Strategy Serving

FastAPI service serving real-time race strategy recommendations.

## Endpoint

**Production**: `https://f1-strategy-api-dev-694267183904.us-central1.run.app`

```bash
curl https://f1-strategy-api-dev-694267183904.us-central1.run.app/health
curl https://f1-strategy-api-dev-694267183904.us-central1.run.app/docs
```

## Source

`src/api/main.py` — uvicorn on port 8000.

Loads promoted models from `gs://f1optimizer-models/` at startup.
Falls back to rule-based strategy logic if no models are present.

## Docker Image

Built from `docker/Dockerfile.api`, pushed to Artifact Registry:
`us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/api:latest`

Cloud Build pushes on every commit to `pipeline`.
Cloud Run picks up `:latest` automatically.

## Local Development

```bash
# Via docker-compose
docker-compose -f docker-compose.f1.yml up api
# → http://localhost:8000/docs

# Or directly
pip install -r docker/requirements-api.txt
uvicorn src.api.main:app --reload --port 8000
```

## Key Environment Variables

| Variable | Default | Description |
|---|---|---|
| `ENV` | `local` | Environment name |
| `LOG_LEVEL` | `INFO` | Log verbosity |
| `ENABLE_HTTPS` | `false` | Force HTTPS redirect |
| `ENABLE_IAM` | `true` | Require GCP IAM auth |
| `MODELS_BUCKET` | `gs://f1optimizer-models` | Where to load model artifacts |

## Target SLA

- P99 latency < 500ms
- Cost per prediction < $0.001
