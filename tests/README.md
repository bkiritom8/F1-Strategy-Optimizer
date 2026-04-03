# Test Suites

Integration and unit tests for the F1 Strategy Optimizer.

## Structure

- **`unit/`**: Isolated tests for:
  - `preprocessing`: Logic for tyre wear/fuel calculations.
  - `llm`: Prompt structure and output schema validation.
  - `api`: Endpoint input validation.
- **`integration/`**: End-to-end flows:
  - Data ingestion -> ML Prediction -> Recommendations.
- **`e2e/`**: Playwright/Puppeteer UI tests for the Race Command Center.

## Running Tests

### Python (Backend/ML)
```bash
pytest tests/unit
pytest tests/integration
```

### Frontend
```bash
cd frontend
npm test
```
