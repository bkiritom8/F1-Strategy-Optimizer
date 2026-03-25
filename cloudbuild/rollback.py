import sys
import json
import subprocess
from google.cloud import aiplatform

aiplatform.init(project='f1optimizer', location='us-central1', experiment='f1-strategy-models')

ROLLBACK_METRIC = {
    'tire-degradation-v1': ('test_mae',      'lower'),
    'driving-style-v1':    ('test_f1_macro', 'higher'),
    'safety-car-v1':       ('test_f1_macro', 'higher'),
    'pit-window-v1':       ('test_mae',      'lower'),
    'overtake-prob-v1':    ('test_f1',       'higher'),
    'race-outcome-v1':     ('test_f1_macro', 'higher'),
}

try:
    result = subprocess.run(['gsutil', 'cat', 'gs://f1optimizer-models/champion_metrics.json'],
                            capture_output=True, text=True)
    champion = json.loads(result.stdout) if result.returncode == 0 else {}
except Exception:
    champion = {}

rollback = False
new_metrics = {}

for run_name, (metric, direction) in ROLLBACK_METRIC.items():
    try:
        run = aiplatform.ExperimentRun(run_name=run_name, experiment='f1-strategy-models',
                                       project='f1optimizer', location='us-central1')
        cur = run.get_metrics().get(metric)
        if cur is None:
            continue
        new_metrics[run_name] = {metric: cur}
        prev = champion.get(run_name, {}).get(metric)
        if prev is None:
            print(f'{run_name}: no previous — accepting ({cur:.4f})')
            continue
        ok = cur <= prev * 1.05 if direction == 'lower' else cur >= prev * 0.95
        print(f'{"OK" if ok else "ROLLBACK"} {run_name}: {prev:.4f} -> {cur:.4f}')
        if not ok:
            rollback = True
    except Exception as e:
        print(f'{run_name}: error — {e}')

if rollback:
    print('Regression detected — keeping champion models')
    sys.exit(1)

champion.update(new_metrics)
with open('/workspace/champion_metrics.json', 'w') as f:
    json.dump(champion, f)
subprocess.run(['gsutil', 'cp', '/workspace/champion_metrics.json',
                'gs://f1optimizer-models/champion_metrics.json'])
print('All models promoted to champion')
