import os
from google.cloud import aiplatform

aiplatform.init(project='f1optimizer', location='us-central1')

commit = os.environ.get('SHORT_SHA', 'unknown')

MODELS = {
    'tire-degradation':  'gs://f1optimizer-models/tire_degradation/',
    'driving-style':     'gs://f1optimizer-models/driving_style/',
    'safety-car':        'gs://f1optimizer-models/safety_car/',
    'pit-window':        'gs://f1optimizer-models/pit_window/',
    'overtake-prob':     'gs://f1optimizer-models/overtake_prob/',
    'race-outcome':      'gs://f1optimizer-models/race_outcome/',
}

for display_name, artifact_uri in MODELS.items():
    model = aiplatform.Model.upload(
        display_name=display_name,
        artifact_uri=artifact_uri,
        serving_container_image_uri='us-central1-docker.pkg.dev/f1optimizer/f1-optimizer/ml:latest',
        labels={'commit': commit},
    )
    print(f'Registered: {model.resource_name}')
