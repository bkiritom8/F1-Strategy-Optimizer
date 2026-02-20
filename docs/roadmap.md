# Project Roadmap and Timeline

**Last Updated**: 2026-02-18
**Project Duration**: 13 weeks
**Target Completion**: Week 13

## Overview

The F1 Strategy Optimizer follows a phased development approach across 13 weeks, organized into 5 major phases: Setup & Data (Weeks 1-4), Model Development (Weeks 5-7), Integration & Simulation (Weeks 8-9), Deployment (Weeks 10-11), and Testing & Launch (Weeks 12-13).

## Timeline Visualization

```
Week 1-2   Week 3-4   Week 5-6   Week 7     Week 8-9   Week 10-11  Week 12-13
├──────────┼──────────┼──────────┼──────────┼──────────┼───────────┼──────────┤
│  Data    │ Profiles │  ML      │  ML      │ Monte    │  API &    │  Testing │
│ Ingestion│ Extract  │ Models   │ Models   │  Carlo   │ Dashboard │  Launch  │
│          │          │  (1-2)   │  (3-4)   │  Sim     │           │          │
└──────────┴──────────┴──────────┴──────────┴──────────┴───────────┴──────────┘

Phase 1      Phase 2    Phase 3              Phase 4     Phase 5
Setup & Data            Model Dev            Integration Deployment  Test & Launch
```

## Phase 1: Setup & Data (Weeks 1-4)

### Week 1-2: Infrastructure Setup & Data Ingestion

**Owner**: Data Engineer + DevOps

**Objectives**:
- Set up GCP project and services
- Download historical data (Jolpica + FastF1)
- Create Cloud SQL tables (lap_features, telemetry_features, driver_profiles)
- Establish data quality checks

**Deliverables**:

[OK] **Infrastructure**:
- [x] GCP project created (`f1optimizer`)
- [x] IAM roles configured (3 service accounts: airflow, dataflow, api)
- [x] Cloud SQL (PostgreSQL 15) provisioned with VPC private IP
- [x] Cloud Run, Dataflow, Pub/Sub, Artifact Registry enabled via Terraform
- [x] Cloud Build trigger configured (pipeline branch)
- [x] Terraform configuration applied (`dev.tfvars`)

[OK] **Data Ingestion**:
- [ ] Jolpica API data downloaded (1950-2026, 1,300+ races)
- [ ] FastF1 telemetry downloaded (2018-2024, 200+ races)
- [ ] Data inserted into Cloud SQL (`lap_features`, `telemetry_features`)
- [ ] Data completeness validated (≥95%)

[OK] **Documentation**:
- [x] `src/database/schema.sql` defined (lap_features, telemetry_features, driver_profiles)
- [x] README updated with quick start
- [x] mkdocs.yml created for CI documentation build

**Success Metrics**:
- Cloud SQL `lap_features` populated with ~1M+ records from Jolpica
- `telemetry_features` populated from FastF1 (2018-2024)
- Data completeness >95%
- All team members have GCP access

**Risks & Mitigations**:
- **Risk**: Jolpica API slow/unreliable → **Mitigation**: Implement retry logic, cache intermediate results
- **Risk**: FastF1 download takes >1 week → **Mitigation**: Parallelize downloads, prioritize recent seasons

---

### Week 2-3: Data Cleaning & Preprocessing

**Owner**: Data Architect

**Objectives**:
- Clean raw data (remove outliers, handle NULLs)
- Implement feature engineering pipeline
- Create temporal train/val/test splits

**Deliverables**:

[OK] **Preprocessing Pipeline**:
- [ ] Outlier removal (lap times, fuel values)
- [ ] Missing data imputation (telemetry gaps)
- [ ] Tire compound standardization (historical mapping)
- [ ] Race alignment (results + pit stops)

[OK] **Feature Engineering**:
- [ ] Tire age calculation
- [ ] Fuel remaining estimation
- [ ] Telemetry aggregation (mean throttle, max speed, brake count)
- [ ] Race context features (gap to leader, position delta)
- [ ] Temporal features (lap number, stint age, laps remaining)

[OK] **Data Splits**:
- [ ] SQL VIEW `train` (1950-2022, ~140GB)
- [ ] SQL VIEW `validation` (2023 Q1-Q2, ~5GB)
- [ ] SQL VIEW `test` (2023 Q3-Q4 + 2024, ~10GB)

[OK] **Feature Store**:
- [ ] `lap_features` and `telemetry_features` tables populated
- [x] Schema documented in `src/database/schema.sql`

**Success Metrics**:
- Cloud SQL contains 1M+ feature rows
- All features validated (no NULLs, correct ranges)
- EDA notebook completed with insights

**Dependencies**: Week 1-2 data ingestion complete

---

### Week 3-4: Driver Profile Extraction

**Owner**: Data Scientist

**Objectives**:
- Extract behavioral profiles for 200+ drivers
- Validate profiles against telemetry
- Create driver profile visualization

**Deliverables**:

[OK] **Profile Extraction**:
- [ ] Aggression score (mean throttle, overtake frequency)
- [ ] Consistency (std_dev of lap times)
- [ ] Pressure response (lap time delta under competition)
- [ ] Tire management (degradation vs teammates)

[OK] **Validation**:
- [ ] Aggression correlation: r > 0.7 [OK]
- [ ] Consistency accuracy: <5% error [OK]
- [ ] Pressure response MAE: <50ms [OK]

[OK] **Outputs**:
- [ ] `drivers/profiles.json` (200+ profiles)
- [ ] Visualization: Scatter plot (aggression vs consistency)
- [ ] Dashboard component: Driver profile viewer

**Success Metrics**:
- 200+ driver profiles generated
- Validation metrics meet targets
- Profiles stored in `driver_profiles` Cloud SQL table

**Dependencies**: Week 2-3 feature engineering complete

---

## Phase 2: Model Development (Weeks 5-7)

### Week 5-6: Train Models 1-2 (Tire Degradation, Fuel Consumption)

**Owner**: ML Engineer

**Objectives**:
- Train XGBoost tire degradation model
- Train LSTM fuel consumption model
- Validate both models on test set

**Deliverables**:

[OK] **Tire Degradation Model (XGBoost)**:
- [ ] Model trained on 1950-2022 data
- [ ] Hyperparameter tuning (max_depth, learning_rate, n_estimators)
- [ ] Validation: MAE < 50ms [OK]
- [ ] Feature importance analysis
- [ ] Model saved to `models/artifacts/tire_degradation_v1.json`

[OK] **Fuel Consumption Model (LSTM)**:
- [ ] Sequence preparation (10 laps lookback)
- [ ] Model trained with early stopping
- [ ] Validation: RMSE < 0.5 kg/lap [OK]
- [ ] Loss curves plotted
- [ ] Model saved to `models/artifacts/fuel_consumption_v1.h5`

[OK] **Model Registry**:
- [ ] Both models registered in Vertex AI
- [ ] Metadata tracked (training date, metrics, hyperparameters)

**Success Metrics**:
- Tire degradation MAE <50ms on test set
- Fuel consumption RMSE <0.5 kg/lap on test set
- Both models meet accuracy targets

**Dependencies**: Week 3-4 feature store ready

---

### Week 7: Train Models 3-4 (Brake Bias, Driving Style)

**Owner**: ML Engineer

**Objectives**:
- Train linear regression brake bias model
- Train decision tree driving style classifier
- Complete model ensemble validation

**Deliverables**:

[OK] **Brake Bias Model (Linear Regression)**:
- [ ] Model trained on telemetry data
- [ ] Feature standardization (StandardScaler)
- [ ] Validation: ±1% accuracy [OK]
- [ ] Model saved to `models/artifacts/brake_bias_v1.pkl`

[OK] **Driving Style Classifier (Decision Tree)**:
- [ ] Labels created from aggressive_score
- [ ] Model trained with class weighting
- [ ] Validation: ≥75% accuracy [OK]
- [ ] Confusion matrix analyzed
- [ ] Model saved to `models/artifacts/driving_style_v1.pkl`

[OK] **Unified Training Pipeline**:
- [ ] `models/train.py` script (train all 4 models)
- [ ] Automated validation reporting
- [ ] Model versioning implemented

**Success Metrics**:
- All 4 models meet accuracy targets
- Unified training pipeline functional
- Models registered in Vertex AI

**Dependencies**: Week 5-6 models 1-2 complete

---

## Phase 3: Integration & Simulation (Weeks 8-9)

### Week 8-9: Monte Carlo Simulator & Optimization Engine

**Owner**: ML Engineer + Data Scientist

**Objectives**:
- Implement race simulator using trained models
- Build Monte Carlo optimization (10K scenarios)
- Validate simulated race outcomes vs actual results

**Deliverables**:

[OK] **Race Simulator**:
- [ ] `simulation/race_simulator.py` implemented
- [ ] Integrates all 4 models + driver profiles
- [ ] Simulates lap-by-lap (tire deg, fuel burn, pit stops)
- [ ] Returns finishing position, total time, fuel remaining

[OK] **Monte Carlo Optimization**:
- [ ] Generate pit strategy candidates (500-1000)
- [ ] Simulate each strategy 20 times (with noise)
- [ ] Rank by win probability
- [ ] Return top 3 strategies

[OK] **Validation**:
- [ ] Podium accuracy: ≥70% [OK]
- [ ] Winner accuracy: ≥65% [OK]
- [ ] Finishing order correlation: Spearman >0.75 [OK]
- [ ] Pit timing accuracy: ±2 laps (70%+ races) [OK]

[OK] **Optimization**:
- [ ] GPU acceleration for Monte Carlo
- [ ] Reduce to 5K scenarios for live inference
- [ ] Caching for common race scenarios

**Success Metrics**:
- Simulator predicts podium ≥70% on test set
- Monte Carlo completes in <200ms (5K scenarios)
- All race prediction metrics meet targets

**Dependencies**: Week 7 all models trained

---

## Phase 4: Deployment (Weeks 10-11)

### Week 10-11: FastAPI Server & Dashboard

**Owner**: Backend Engineer + Frontend Engineer

**Objectives**:
- Deploy FastAPI on Cloud Run
- Build React dashboard with 4 components
- Implement real-time streaming pipeline

**Deliverables**:

[OK] **FastAPI Server**:
- [ ] `serving/api.py` implemented
- [ ] `/recommend` endpoint (pit strategy, driving mode, brake bias)
- [ ] `/simulate` endpoint (full race simulation)
- [ ] `/driver-profile/{id}` endpoint
- [ ] Health check endpoint (`/health`)
- [ ] Deployed to Cloud Run (<500ms P99 latency [OK])

[OK] **React Dashboard**:
- [ ] Component 1: Driver Profile Viewer (scatter plot)
- [ ] Component 2: Lap-by-Lap Guidance Panel
- [ ] Component 3: Race Simulation Visualizer
- [ ] Component 4: Historical Analysis Comparison
- [ ] Deployed to Vercel/Cloud Run

[OK] **Streaming Pipeline (Optional for Live Races)**:
- [ ] Pub/Sub topic created (`telemetry-topic`)
- [ ] Dataflow job deployed (`pipeline/dataflow_job.py`)
- [ ] Real-time feature extraction
- [ ] End-to-end latency <5s [OK]

[OK] **Load Testing**:
- [ ] API tested at 2x expected traffic
- [ ] P99 latency <500ms confirmed
- [ ] Auto-scaling validated (1-20 instances)

**Success Metrics**:
- API deployed and accessible
- P99 latency <500ms
- Dashboard functional and responsive
- Streaming pipeline (if implemented) <5s latency

**Dependencies**: Week 8-9 simulator ready

---

## Phase 5: Testing & Launch (Weeks 12-13)

### Week 12-13: Testing, Monitoring, Documentation

**Owner**: QA + DevOps + Documentation Lead

**Objectives**:
- Comprehensive testing (unit, integration, load)
- Production monitoring setup
- Final documentation and demo preparation

**Deliverables**:

[OK] **Testing**:
- [ ] Unit tests: 80%+ coverage [OK]
- [ ] Integration tests: End-to-end pipeline
- [ ] Load tests: 2x traffic, no degradation
- [ ] Validation tests: All metrics on test set
- [ ] Test report generated

[OK] **Monitoring**:
- [ ] Cloud Monitoring dashboards (4 dashboards)
- [ ] Alert policies configured (6 alerts)
- [ ] Slack webhook integration
- [ ] Cost tracking enabled
- [ ] Drift detection scheduled (weekly)

[OK] **Documentation**:
- [ ] README.md finalized
- [ ] API documentation (auto-generated from FastAPI)
- [ ] ARCHITECTURE.md complete
- [ ] DATA_DICTIONARY.md complete
- [ ] DEPLOYMENT.md runbook

[OK] **Demonstrations**:
- [ ] Demo 1: Driver profiles scatter plot
- [ ] Demo 2: Live race simulation (Monaco 2024)
- [ ] Demo 3: Validation results (podium accuracy)
- [ ] Demo 4: API call (<500ms response time)

[OK] **Launch Readiness**:
- [ ] All acceptance criteria met
- [ ] Stakeholder presentation prepared
- [ ] Code review completed
- [ ] GitHub repository organized

**Success Metrics**:
- All tests passing
- All monitoring configured
- All documentation complete
- Demos successful
- Stakeholder approval [OK]

**Dependencies**: Week 10-11 deployment complete

---

## Milestone Summary

| Week | Milestone | Status | Deliverable |
|------|-----------|--------|-------------|
| 1-2 | Infrastructure Complete | [Complete] Done | Cloud SQL, IAM, VPC, Cloud Build, Terraform applied |
| 2 | Data Ingestion Complete | [Pending] Pending | Cloud SQL `lap_features` populated (150GB) |
| 3 | Feature Store Ready | [Pending] Pending | `lap_features` + `telemetry_features` (1M+ rows) |
| 4 | Driver Profiles Extracted | [Pending] Pending | `driver_profiles` table (200+ drivers) |
| 6 | Models 1-2 Trained | [Pending] Pending | Tire degradation + Fuel consumption |
| 7 | All 4 Models Trained | [Pending] Pending | All models meet accuracy targets |
| 9 | Simulator Validated | [Pending] Pending | Podium accuracy ≥70% |
| 11 | API Deployed | [Pending] Pending | Cloud Run, <500ms P99 |
| 13 | Project Complete | [Pending] Pending | All acceptance criteria met |

## Critical Path

```
Data Ingestion → Feature Engineering → Driver Profiles → Model Training →
Monte Carlo Simulator → API Deployment → Testing → Launch
```

**Bottleneck Analysis**:
- **Week 5-7**: Model training (computationally intensive) → Use Vertex AI distributed training
- **Week 8-9**: Monte Carlo simulation (10K scenarios slow) → GPU acceleration required
- **Week 10-11**: API latency optimization → Critical for <500ms P99 target

## Risk Register

| Risk | Probability | Impact | Mitigation | Owner |
|------|-------------|--------|------------|-------|
| Data download exceeds 1 week | Medium | High | Parallelize, prioritize recent seasons | Data Engineer |
| Model accuracy below target | Medium | High | Increase training data, tune hyperparameters | ML Engineer |
| Monte Carlo too slow | High | High | GPU acceleration, reduce scenarios to 5K | ML Engineer |
| API latency >500ms | Medium | Critical | Model caching, quantization, load testing | Backend Engineer |
| Budget overrun >$70/month | Medium | High | Cost monitoring, optimize Dataflow, budget alerts at $60 | DevOps |
| Test coverage <80% | Low | Medium | Enforce test writing, CI/CD checks | QA |

## Resource Allocation

| Role | Weeks 1-4 | Weeks 5-7 | Weeks 8-9 | Weeks 10-11 | Weeks 12-13 |
|------|-----------|-----------|-----------|-------------|-------------|
| Data Engineer | 100% | 20% | 20% | 10% | 10% |
| Data Scientist | 30% | 100% | 100% | 20% | 20% |
| ML Engineer | 20% | 100% | 100% | 50% | 30% |
| Backend Engineer | 10% | 10% | 20% | 100% | 50% |
| Frontend Engineer | 0% | 0% | 10% | 100% | 30% |
| DevOps | 50% | 10% | 10% | 50% | 100% |
| QA | 10% | 10% | 20% | 30% | 100% |

## Weekly Cadence

**Mondays**: Sprint planning, task assignment
**Wednesdays**: Mid-week sync, blocker resolution
**Fridays**: Demo, retrospective, progress update

**Slack Channels**:
- `#f1-strategy-general`: General discussion
- `#f1-strategy-dev`: Development updates
- `#f1-strategy-alerts`: Automated alerts

## Future Roadmap (Post-Week 13)

**Phase 6: Enhancements (Weeks 14-20)**
- Real-time telemetry integration (live races)
- Multi-series support (Formula E, IndyCar)
- Advanced tire temperature modeling
- Video analysis (onboard cameras)
- Mobile app development

**Phase 7: Scale & Commercialize (Weeks 21-30)**
- Multi-region deployment (US, EU, Asia)
- SaaS subscription model
- Team-specific customizations
- API rate limiting and billing
- Enterprise security features

---

**See Also**:
- CLAUDE.md: Project objectives
- docs/metrics.md: Success criteria
- docs/monitoring.md: Operational readiness
