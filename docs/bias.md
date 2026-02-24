# F1 Dataset — Bias Analysis & Mitigation

**Last Updated**: 2026-02-23
**Script**: `Data-Pipeline/scripts/bias_analysis.py`
**Report**: `Data-Pipeline/logs/bias_report.json`

---

## Executive Summary

The F1 Strategy Optimizer trains on 76 years of race data (1950–2026). This span
introduces significant representation bias:

- **Temporal bias**: 86% of data points come from 2014+ (hybrid era). Pre-2010 data
  represents only ~8% of laps, and pre-1996 data has no telemetry whatsoever.
- **Team bias**: Constructor championship top-3 teams (Ferrari, Mercedes, Red Bull, McLaren)
  generate more laps (finish more races, log more practice) than backmarkers.
- **Circuit bias**: Street circuits (Monaco, Baku, Singapore) account for ~11% of rounds
  but are overrepresented in high-impact strategy decisions.
- **Weather bias**: Wet sessions are rare (~3-5% of total laps) but strategically critical.

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
| Street | ~11% | ~4-5 street rounds per season |
| Mixed | ~14% | Temporary-layout circuits with permanent infrastructure |

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
- Implemented via `sample_weight` parameter in XGBoost/LightGBM training.
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

## Trade-offs

| Decision | Benefit | Cost |
|---|---|---|
| Upweight pre-2014 data | Better classic-era recommendations | Slightly reduces modern-era accuracy |
| Oversample wet laps | Model handles rain better | Risk of overconfident wet predictions |
| Exclude pre-1996 from training | Clean data only | Cannot model V10-era strategy authentically |
| Stratified splits by circuit | Fair evaluation across track types | Smaller per-type eval sets |

---

## How to Re-Run Bias Analysis

```bash
# From repo root
python Data-Pipeline/scripts/bias_analysis.py

# Specify a custom data directory
python Data-Pipeline/scripts/bias_analysis.py --data-dir data/processed

# Via DVC
dvc repro bias_analysis

# View report
cat Data-Pipeline/logs/bias_report.json
```

---

## Recommendations for Future Data Collection

1. **Expand pre-2014 telemetry**: Source hand-digitised timing data from independent
   F1 archives (e.g., `statsf1.com`) to increase pre-hybrid era representation.
2. **Augment wet sessions**: Synthesise wet lap times using interpolation from known
   wet/dry performance deltas per circuit.
3. **Backmarker parity**: Ensure test set always includes at least 2 backmarker teams
   to avoid silent failures on slow-car strategy scenarios.
4. **Continuous monitoring**: Re-run `bias_analysis.py` every time new season data
   is ingested to catch drift in subgroup representation.
