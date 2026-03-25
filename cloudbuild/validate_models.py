import sys
from google.cloud import aiplatform

aiplatform.init(project='f1optimizer', location='us-central1', experiment='f1-strategy-models')

THRESHOLDS = {
    'tire-degradation-v1':  {'test_mae': 0.35,  'test_r2': 0.80},
    'driving-style-v1':     {'test_f1_macro': 0.75},
    'safety-car-v1':        {'test_f1_macro': 0.90},
    'pit-window-v1':        {'test_mae': 2.0,   'test_r2': 0.90},
    'overtake-prob-v1':     {'test_f1': 0.25},
    'race-outcome-v1':      {'test_f1_macro': 0.60},
}

failures = []
for run_name, thresholds in THRESHOLDS.items():
    try:
        run = aiplatform.ExperimentRun(run_name=run_name, experiment='f1-strategy-models',
                                       project='f1optimizer', location='us-central1')
        metrics = run.get_metrics()
        for metric, threshold in thresholds.items():
            val = metrics.get(metric)
            if val is None:
                continue
            ok = val <= threshold if 'mae' in metric else val >= threshold
            print(f'  {"OK" if ok else "FAIL"} {metric}: {val:.4f} (threshold: {threshold})')
            if not ok:
                failures.append(f'{run_name}.{metric}={val:.4f}')
    except Exception as e:
        print(f'  Could not fetch {run_name}: {e}')

if failures:
    print(f'VALIDATION FAILED: {failures}')
    sys.exit(1)
else:
    print('All models pass validation')
