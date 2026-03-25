from google.cloud import aiplatform

aiplatform.init(project='f1optimizer', location='us-central1', experiment='f1-strategy-models')

BIAS_TOLERANCE = {
    'tire_degradation': 0.10, 'driving_style': 0.12,
    'safety_car': 0.15,       'pit_window': 2.0,
    'overtake_prob': 0.10,    'race_outcome': 0.20,
}
RUN_MAP = {
    'tire_degradation': 'tire-degradation-v1', 'driving_style': 'driving-style-v1',
    'safety_car': 'safety-car-v1',             'pit_window': 'pit-window-v1',
    'overtake_prob': 'overtake-prob-v1',        'race_outcome': 'race-outcome-v1',
}
METRIC_KEY = {
    'tire_degradation': 'mae', 'pit_window': 'mae',
    'driving_style': 'f1',     'safety_car': 'f1',
    'overtake_prob': 'f1',     'race_outcome': 'f1',
}

for model, run_name in RUN_MAP.items():
    try:
        run = aiplatform.ExperimentRun(run_name=run_name, experiment='f1-strategy-models',
                                       project='f1optimizer', location='us-central1')
        metrics = run.get_metrics()
        mk = METRIC_KEY[model]
        slices = {k: v for k, v in metrics.items() if k.startswith('bias_') and k.endswith(f'_{mk}')}
        if not slices:
            print(f'{model}: no bias metrics found')
            continue
        best  = min(slices.values()) if mk == 'mae' else max(slices.values())
        worst = max(slices.values()) if mk == 'mae' else min(slices.values())
        gap = abs(best - worst)
        tol = BIAS_TOLERANCE[model]
        print(f'{"OK" if gap <= tol else "WARN"} {model}: disparity={gap:.3f} (tol={tol})')
    except Exception as e:
        print(f'{model}: error — {e}')
