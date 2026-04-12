# Test Suites

Integration, unit, and E2E tests for the DivergeX backend, ML pipeline, and frontend.

## Structure

```
tests/
├── unit/
│   ├── preprocessing/      # Tyre wear, fuel load, and degradation calculation tests
│   ├── llm/                # Prompt structure and structured output schema validation
│   ├── simulation/         # Monte Carlo coordinator + SSE streamer tests
│   └── api/                # Endpoint input validation and error handling
├── integration/            # End-to-end flows: data ingestion → ML prediction → recommendations
└── e2e/                    # Playwright/Puppeteer UI tests for Race Command Center
```

## ML Tests (`ml/tests/`)

87 model and feature validation tests covering all 6 supervised models and the feature store. Run on Vertex AI Custom Jobs for GPU access:

```bash
python ml/tests/run_tests_on_vertex.py
```

## Running Tests

### Backend (Python)

```bash
# Unit tests
pytest tests/unit -v

# Integration tests (requires GCP ADC credentials)
pytest tests/integration -v

# Simulation tests (requires Redis)
REDIS_HOST=localhost pytest tests/unit/simulation/ -v
```

### Frontend (TypeScript)

```bash
cd frontend
npm test                 # Vitest unit tests
npm run test:coverage    # With coverage report
```

### E2E

```bash
cd tests/e2e
npx playwright test
```

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every push:

- Lint: flake8
- Type-check: mypy
- Unit tests: pytest
- Security: Bandit
- Terraform: `terraform validate`
- RL smoke test: single-episode PPO rollout
- Frontend: ESLint + Vitest
