# Machine Learning Models

This directory contains the end-to-step ML lifecycle codebase for F1 Strategy predictions.

## Structure

- **training/**: Contains the supervised training scripts for the 6 primary models, plus the Reinforcement Learning agent.
- **models/**: Python classes wrapping the models, handling loading/saving mechanisms (e.g. GCS serialization and Pub/Sub).
- **rl/**: Custom OpenAI Gymnasium environments and agents modeling the complexity of an F1 race.
- **preprocessing/**: Feeds the feature store by converting raw ingested FastF1 data into usable features.
- **features/**: The feature store system connected to GCS.
- **distributed/**: Training configurations using Vertex AI distributed training profiles.
- **dag/**: Kubeflow Pipelines (KFP v2) definitions building the 5-step Directed Acyclic Graph.
- **tests/**: Specific validation integration tests for models and features.

## Workflows

The main supervised models predict:
- Tire Degradation
- Driving Style
- Safety Car deployments
- Pit Windows
- Overtake Probabilities
- Overall Race Outcomes

The pipeline is triggered manually or continuously via Cloud Build.