# DivergeX

**Real-time F1 race strategy intelligence — built on 76 years of data and seven AI models.**

[Live Demo](https://f1optimizer.web.app) · [Docs](./docs/README.md)

---

## The Problem

A single pit stop decision made one lap too late can cost a driver three positions. In Formula 1, strategy is decided in seconds — by engineers sifting through live telemetry, tyre degradation models, competitor pace data, and safety car windows simultaneously. The margins are razor-thin and the consequences are immediate.

This problem has historically required a full strategy team and decades of institutional knowledge. Most of that knowledge is never shared outside a team's garage.

## What DivergeX Does

DivergeX is a real-time race strategy platform that surfaces pit stop timing, driving mode recommendations, tyre compound analysis, and competitor threat assessments — for any driver, at any circuit — through a live web dashboard.

Under the hood, seven AI models work in concert. Six supervised ensembles predict tyre degradation, safety car probability, optimal pit windows, overtake likelihood, driver style, and final race outcome. A reinforcement learning agent — trained on over a million race simulations — recommends the globally optimal strategy sequence for the remainder of the race. The system also includes a Monte Carlo race simulator, a Gemini-backed strategy chatbot, and a 76-year F1 knowledge base queryable in plain English.

Everything runs in under 500ms.

## What Makes It Different

**The data advantage.** DivergeX ingests from two sources no commercial product fully combines: structured race records from 1950 to 2026 (results, pit stops, constructor standings, qualifying) and lap-by-lap 10Hz telemetry from 2018 onward (throttle, brake, speed trace, tyre compound, DRS, sector splits). Together they form the most comprehensive F1 dataset outside of a team's own data warehouse.

**Driver awareness.** Recommendations are not circuit-generic. The system models each driver's tyre management behaviour, throttle application patterns, and response under pressure as individual fingerprints. A strategy optimal for one driver will not be recommended for another if the data says otherwise.

**Realistic tyre physics.** The degradation model follows an exponential curve calibrated to real Pirelli performance data — soft compounds cliff sharply around lap 15, mediums around lap 28, hards around lap 50. Tires running past their rated life incur compounding penalties; severe overuse introduces the kind of unpredictable per-lap variance real teams are forced to manage on the radio.

**The full intelligence stack.** Most F1 strategy tools are calculators. DivergeX combines supervised prediction, reinforcement learning policy, probabilistic simulation, retrieval-augmented generation, and natural language interaction in a single platform.

---

## Core Capabilities

| Capability | Description |
|---|---|
| **Tyre Strategy** | Compound recommendations, pit window timing, degradation curve projection |
| **Safety Car Prediction** | Lap-by-lap deployment probability — revalues open pit windows in real time |
| **RL Strategy Agent** | PPO-trained policy recommends the globally optimal remaining race strategy |
| **Monte Carlo Simulator** | Runs hundreds of race scenarios, streams results live as an animated 2D track map |
| **AI Strategy Chat** | Gemini-backed chatbot answers natural-language strategy questions grounded in race state |
| **76-Year F1 Knowledge Base** | Historical race context retrieved by similarity — comparable situations, circuit patterns, precedent decisions |
| **Driver Style Modelling** | Per-driver tyre behaviour, pressure response, and throttle fingerprints |
| **Overtake Probability** | Circuit-specific pass likelihood given pace delta and track position |
| **Race Outcome Forecast** | Probability distribution over final positions updated each lap |

---

## The Models

| Model | What It Predicts | Accuracy |
|---|---|---|
| Tyre Degradation | Per-lap pace loss rate by compound, driver, circuit | MAE 0.285s · R² 0.850 |
| Safety Car | Deployment probability in the next N laps | F1 0.920 |
| Pit Window | Optimal pit lap range given current race context | MAE 1.1 laps · R² 0.968 |
| Race Outcome | Final position distribution — win, podium, points, DNF | Accuracy 79% · F1 0.778 |
| Driving Style | Driver class (aggressive / balanced / conservative) from telemetry | F1 0.800 |
| Overtake Probability | On-track pass likelihood by position and pace delta | F1 0.326 |
| RL Race Strategy | Globally optimal strategy sequence for the rest of the race | PPO · 1M+ simulations |

Training data: 2018–2021. Validation: 2022–2023. Test: 2024.

---

## The Stack

DivergeX is a production system — containerized, cloud-deployed, continuously trained, and monitored through a full CI/CD pipeline.

| Layer | Technology |
|---|---|
| Frontend | React 19 · TypeScript · Vite · Tailwind · Firebase Hosting |
| Backend | FastAPI · Cloud Run · Redis |
| ML Training | Vertex AI Custom Training · KFP v2 Pipelines · T4 GPU |
| Models | XGBoost · LightGBM · CatBoost · Random Forest · Stable-Baselines3 PPO |
| LLM & RAG | Gemini Pro · Vertex AI Vector Search · LangChain · 768-dim embeddings |
| Simulation | Monte Carlo · SSE streaming · Redis frame cache |
| Data | Google Cloud Storage · Jolpica API · FastF1 · Parquet |
| Infrastructure | Terraform · GCP · Artifact Registry · GitHub Actions · Cloud Build |

---

## The Data

**76 years of Formula 1.** Every race result, pit stop record, qualifying session, and constructor standing from 1950 to 2026 — plus lap-by-lap 10Hz telemetry from 2018 onward covering speed, throttle, brake, DRS, tyre compound, and sector splits for every driver in every session.

This depth of historical context is what makes driver-aware, circuit-specific recommendations possible. It is also what grounds the RAG knowledge base — when a user asks a comparative or historical question, the system retrieves the most relevant race records from the entire dataset before generating an answer.

---

## Roadmap

- **Monitoring & alerting** — real-time model drift detection, Cloud Monitoring dashboards
- **Live telemetry integration** — streaming race state from live F1 data feeds during active grands prix  
- **Team strategy view** — multi-car strategy coordination for two-car team management
- **Mobile app** — native iOS/Android dashboard for use in the paddock
- **B2B API** — strategy intelligence as a service for teams, broadcasters, and fantasy platforms

---

**Live**: [f1optimizer.web.app](https://f1optimizer.web.app) · **Docs**: [docs/](./docs/README.md) · **Last Updated**: 2026-04-14
