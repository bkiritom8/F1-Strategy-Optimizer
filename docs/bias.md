# F1 Dataset — Bias Analysis & Mitigation

**Last Updated**: 2026-04-02
**CI check**: `cloudbuild/check_bias.py` (runs as `check-bias` step in `cloudbuild.yaml`)
**Training scripts**: `ml/training/train_*.py` — each logs `bias_*` metrics to Vertex AI Experiments

---

## Executive Summary

DivergeX trains on 76 years of race data (1950–2026). This span
introduces significant representation bias:

- **Temporal bias**: 86% of data points come from 2014+ (hybrid era). Pre-2010 data
  represents only ~8% of laps, and pre-1996 data has no telemetry whatsoever.
- **Team bias**: Constructor championship top-3 teams (Ferrari, Mercedes, Red Bull, McLaren)
  generate more laps (finish more races, log more practice) than backmarkers.
- **Circuit bias**: Street circuits (Monaco, Baku, Singapore, Saudi Arabia, Miami, Las Vegas)
  account for ~11% of rounds but are overrepresented in high-impact strategy decisions.
- **Weather bias**: Wet sessions are rare (~3–5% of total laps) but strategically critical.

---

## Underrepresented Subgroups

### By Era

| Era | Approx Lap Share | Root Cause |
|---|---|---|
| pre-2010 (NA/V10/V8) | ~8% | Limited FastF1 coverage (FastF1 starts 2018); older Jolpica records sparse |
| 2010–2013 (V8 KERS) | ~7% | Transition era, partial telemetry |
| 2014+ (hybrid) | ~85% | Full telemetry, high round count, modern data quality |

**Impact**: Models trained without season weighting will implicitly optimise for hybrid-era
car characteristics (DRS, ERS deployment) and underperform on classic strategy rules.

### By Team Tier

| Tier | Approx Share | Root Cause |
|---|---|---|
| Top teams | ~45% | Top teams finish races (points scoring = more laps counted) |
| Mid-field | ~40% | Competitive grid makes mid-field well represented |
| Backmarkers | ~15% | DNFs, slower cars, fewer championship appearances |

**Impact**: Pit strategy recommendations are biased toward multi-stop strategies
used by top teams with tyre deg management advantage.

### By Circuit Type

| Type | Approx Share | Root Cause |
|---|---|---|
| Permanent | ~75% | Majority of calendar is traditional permanent circuits |
| Street | ~11% | ~4–5 street rounds per season |
| Mixed | ~14% | Temporary-layout circuits with permanent infrastructure |

Street circuits used consistently across all models:
`Monaco Grand Prix`, `Azerbaijan Grand Prix`, `Singapore Grand Prix`,
`Saudi Arabian Grand Prix`, `Miami Grand Prix`, `Las Vegas Grand Prix`.

**Impact**: The model underestimates tyre deg on abrasive street surfaces
(Baku concrete, Singapore asphalt) if street circuits are underweighted.

### By Weather

| Condition | Approx Share | Root Cause |
|---|---|---|
| Dry | ~96% | F1 is largely run in dry conditions |
| Wet | ~4% | Rain events are rare but unpredictable |

**Impact**: Wet-weather tyre compound recommendations are trained on very few samples
which may lead to overconfident or erratic wet strategy calls.

---

## Mitigation Strategies Applied

### 1. Season Weighting
- Laps from pre-2014 eras are upweighted during training by factor of 3×.
- Implemented via `sample_weight` parameter in XGBoost/LightGBM training calls.
- Rationale: preserves classic strategy knowledge while letting the model train
  on the volume of modern data.

### 2. Compound Oversampling
- INTERMEDIATE and WET compound laps are oversampled (5×) during training to
  compensate for their low base frequency.
- Implemented in `ml/features/feature_store.py` sampling logic.

### 3. Circuit-Type Stratified Splits
- Train/validation/test splits are stratified by circuit type so each split
  contains proportional representation of street, permanent, and mixed circuits.

### 4. Pre-1996 Exclusion (Accepted Trade-off)
- Seasons before 1996 have no lap-by-lap timing in Jolpica and no telemetry.
- These seasons provide only race results and standings, which are used for
  contextual driver history but excluded from direct model training.
- Documented as an accepted gap: strategy recommendations for pre-modern-era
  simulations will extrapolate from 1996+ data.

---

## Per-Model Bias Slices and Tolerances

Each training script evaluates the trained model across demographic slices and logs
`bias_*` metrics to Vertex AI Experiments (experiment: `f1-strategy-models`).
`cloudbuild/check_bias.py` retrieves these metrics after training and emits `WARN` / `OK`.

### Tire Degradation (`ml/training/train_tire_degradation.py`, lines 340–428)

| Slice | Metric Logged | Mitigation | Tolerance |
|---|---|---|---|
| Season (each year) | `bias_season_{season}_mae` | — | — |
| Compound (S/M/H) | `bias_compound_{compound}_mae` | — | — |
| Circuit: street | `bias_circuit_street_mae` | Inverse-frequency sample weights if gap > 0.05s | 0.05s |
| Circuit: permanent | `bias_circuit_permanent_mae` | (trigger pair) | 0.05s |
| Tyre life: fresh (0–10 laps) | `bias_fresh_tyre_0_10_mae` | — | — |
| Tyre life: worn (10+ laps) | `bias_worn_tyre_10plus_mae` | — | — |

Additional mitigation metrics: `bias_mitigation_weight_applied` (0/1), `bias_street_permanent_gap`.

### Pit Window (`ml/training/train_pit_window.py`, lines 440–512)

| Slice | Metric Logged | Mitigation | Tolerance |
|---|---|---|---|
| Season (each year) | `bias_season_{season}_mae` | — | — |
| Compound (S/M/H) | `bias_compound_{compound}_mae` | Compound-stratified weights if soft/hard gap > 1.5 laps | 1.5 laps |
| Circuit: street | `bias_circuit_street_mae` | — | — |
| Circuit: permanent | `bias_circuit_permanent_mae` | — | — |
| Stint: 1st / 2nd / 3rd+ | `bias_stint_{1,2,3plus}_mae` | — | — |

Additional mitigation metrics: `bias_mitigation_applied` (0/1), `bias_soft_hard_mae_gap`.

### Safety Car (`ml/training/train_safety_car.py`, lines 320–421)

| Slice | Metric Logged | Mitigation | Tolerance |
|---|---|---|---|
| Season (each year) | `bias_season_{season}_f1` | — | — |
| Circuit: street | `bias_circuit_street_f1` | Circuit-specific decision threshold if gap > 0.08 | 0.08 F1 |
| Circuit: permanent | `bias_circuit_permanent_f1` | (trigger pair) | 0.08 F1 |
| Race phase: early/mid/late | `bias_early_phase_f1`, `bias_mid_phase_f1`, `bias_late_phase_f1` | — | — |
| Stint: 1st/2nd/3rd | `bias_first_stint_f1`, `bias_second_stint_f1`, `bias_third_stint_f1` | — | — |

Additional mitigation metrics: `bias_mitigation_applied` (0/1), `bias_street_threshold`, `bias_street_permanent_f1_gap`.

### Race Outcome (`ml/training/train_race_outcome.py`, lines 400–501)

| Slice | Metric Logged | Mitigation | Tolerance |
|---|---|---|---|
| Season (each year) | `bias_season_{season}_acc`, `bias_season_{season}_f1` | — | — |
| Constructor: top / mid / back | `bias_constructor_top_acc/f1`, `bias_constructor_mid_acc/f1`, `bias_constructor_back_acc/f1` | Oversample back-constructor races if top/back F1 gap > 0.15 | 0.15 F1 |
| Grid: P1–5 / P6–15 / P16+ | `bias_front_grid_1_5_acc/f1`, `bias_mid_grid_6_15_acc/f1`, `bias_back_grid_16plus_acc/f1` | — | — |

Additional mitigation metrics: `bias_mitigation_applied` (0/1), `bias_constructor_f1_gap`, `bias_oversample_factor`.

### Driving Style (`ml/training/train_driving_style.py`, lines 312–377)

| Slice | Metric Logged | Mitigation | Tolerance |
|---|---|---|---|
| Season (each year) | `bias_season_{season}_f1` | — | — |
| Compound (S/M/H) | `bias_compound_{compound}_f1` | — | — |
| Circuit: street / permanent | `bias_circuit_street_f1`, `bias_circuit_permanent_f1` | — | — |
| Position: P1–5 / P6–15 / P16+ | `bias_front_p1_5_f1`, `bias_mid_p6_15_f1`, `bias_back_p16plus_f1` | Flagged; `class_weight='balanced'` already applied | 0.10 F1 |

Additional mitigation metrics: `bias_mitigation_applied` (0/1), `bias_position_f1_gap`.

### Overtake Probability (`ml/training/train_overtake_prob.py`)

Slices: season, compound, circuit type. Tolerance: 0.10 F1. No active mitigation — flagged only.

---

## RL Agent Bias Evaluation

`ml/training/train_rl.py` runs `evaluate_bias_slices()` (lines 300–402) after training.

### Slices evaluated

| Dimension | Metrics Logged | Flag Threshold |
|---|---|---|
| Circuit type (street / power / mixed) | `bias_circuit_street_avg_position`, `bias_circuit_power_avg_position`, `bias_circuit_mixed_avg_position`, `bias_circuit_position_mean`, `bias_circuit_max_deviation`, `bias_circuit_flag` | > 3 positions from mean → `bias_circuit_flag = 1` |
| Starting position tier (P1 front / P10 mid / P18 back) | `bias_startpos_{label}_avg_position`, `bias_startpos_{label}_position_gain` | — |
| Season slices | `bias_season_{season}_avg_position`, `bias_season_max_deviation` | — |

Bias metrics are merged into the final training summary (`**bias_metrics` unpacking at line 999) and included in the Vertex AI Experiments run.

### Visualisations

`_plot_bias_results()` (lines 529–593) generates `ml/plots/rl_bias_detection.png`:
- Bar chart of average finishing position across circuit types with mean reference line
- Starting position gain chart across position tiers

---

## Trade-offs

| Decision | Benefit | Cost |
|---|---|---|
| Upweight pre-2014 data | Better classic-era recommendations | Slightly reduces modern-era accuracy |
| Oversample INTERMEDIATE/WET laps | Model handles rain better | Risk of overconfident wet predictions |
| Exclude pre-1996 from training | Clean data only | Cannot model V10-era strategy authentically |
| Stratified splits by circuit | Fair evaluation across track types | Smaller per-type eval sets |
| `class_weight='balanced'` in Driving Style | Handles position-tier imbalance | May reduce peak accuracy on over-represented mid-field |

---

## CI/CD Bias Gate

The `check-bias` step in `cloudbuild.yaml` (runs after `validate-models`, before `push-models-registry`):

```yaml
- name: "python:3.10-slim"
  id: "check-bias"
  waitFor: ["validate-models"]
  entrypoint: "bash"
  args:
    - "-c"
    - |
      pip install --quiet google-cloud-aiplatform
      python /workspace/cloudbuild/check_bias.py
```

`cloudbuild/check_bias.py` checks bias metrics for all 6 models with these tolerances:

| Model | Metric Key | Tolerance |
|---|---|---|
| `tire_degradation` | street/permanent gap | 0.10 |
| `driving_style` | position gap | 0.12 |
| `safety_car` | street/permanent gap | 0.15 |
| `pit_window` | soft/hard gap | 2.0 laps |
| `overtake_prob` | circuit gap | 0.10 |
| `race_outcome` | constructor gap | 0.20 |

Metrics are retrieved from Vertex AI using the pattern `bias_*_<metric_key>`. Each metric emits `WARN` or `OK`. A `WARN` is logged to Cloud Build output but does not hard-block the build.

---

## How to View Bias Metrics

### Vertex AI Experiments (recommended)

1. Go to: https://console.cloud.google.com/vertex-ai/experiments?project=f1optimizer
2. Click **f1-strategy-models**
3. Filter runs by `model_name`, sort or filter by any `bias_*` column

From Python:
```python
from google.cloud import aiplatform
aiplatform.init(project="f1optimizer", location="us-central1",
                experiment="f1-strategy-models")
runs = aiplatform.ExperimentRun.list(experiment="f1-strategy-models")
for r in runs:
    metrics = r.get_metrics()
    bias_metrics = {k: v for k, v in metrics.items() if k.startswith("bias_")}
    print(r.run_name, bias_metrics)
```

### Re-run bias check manually

```bash
# Requires GCP authentication and google-cloud-aiplatform installed
pip install google-cloud-aiplatform
python cloudbuild/check_bias.py
```

### View RL bias visualisation

```bash
# Generated after train_rl.py completes
open ml/plots/rl_bias_detection.png
```

---

## Recommendations for Future Data Collection

1. **Expand pre-2014 telemetry**: Source hand-digitised timing data from independent
   F1 archives to increase pre-hybrid era representation.
2. **Augment wet sessions**: Synthesise wet lap times using interpolation from known
   wet/dry performance deltas per circuit.
3. **Backmarker parity**: Ensure test set always includes at least 2 backmarker teams
   to avoid silent failures on slow-car strategy scenarios.
4. **Continuous monitoring**: Re-run bias checks every time new season data is ingested
   (re-trigger `cloudbuild/check_bias.py`) to catch drift in subgroup representation.
5. **Expand street circuit set**: As new street venues are added to the F1 calendar,
   update the `street_circuits` list consistently across all 6 training scripts.
