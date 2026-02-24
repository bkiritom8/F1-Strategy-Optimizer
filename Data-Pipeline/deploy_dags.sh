#!/bin/bash
# deploy_dags.sh — Upload DAGs to GCS and print the Airflow URL.
#
# Usage:
#   bash Data-Pipeline/scripts/deploy_dags.sh
#
# Reads the Airflow VM IP from Terraform output (infra/terraform).
# Requires: gcloud auth application-default login, terraform applied.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
DAGS_DIR="${REPO_ROOT}/Data-Pipeline/dags"
TF_DIR="${REPO_ROOT}/infra/terraform"

GCS_DAGS_BUCKET="${GCS_DAGS_BUCKET:-gs://f1optimizer-training/dags}"

echo "=== F1 Pipeline — Deploy DAGs ==="
echo "Source : ${DAGS_DIR}"
echo "Target : ${GCS_DAGS_BUCKET}"
echo ""

# ── Upload DAGs to GCS ────────────────────────────────────────────────────────
echo "[1/3] Uploading DAGs to GCS..."
gsutil -m rsync -r -d "${DAGS_DIR}/" "${GCS_DAGS_BUCKET}/"
echo "[OK]  DAGs uploaded: $(gsutil ls "${GCS_DAGS_BUCKET}/" | wc -l | tr -d ' ') files"

# ── Read VM IP from Terraform output ─────────────────────────────────────────
echo ""
echo "[2/3] Reading Airflow VM IP from Terraform..."
VM_IP=""
if terraform -chdir="${TF_DIR}" output airflow_vm_ip &>/dev/null; then
    VM_IP=$(terraform -chdir="${TF_DIR}" output -raw airflow_vm_ip 2>/dev/null || "")
fi

if [[ -z "$VM_IP" ]]; then
    echo "[WARN] Could not read airflow_vm_ip from Terraform output."
    echo "       Run: terraform -chdir=infra/terraform apply -var-file=dev.tfvars"
    AIRFLOW_URL="http://<VM_IP>:8080"
else
    AIRFLOW_URL="http://${VM_IP}:8080"
fi

# ── Print result ───────────────────────────────────────────────────────────────
echo ""
echo "[3/3] Deployment complete."
echo ""
echo "  DAGs synced to : ${GCS_DAGS_BUCKET}"
echo "  Airflow URL    : ${AIRFLOW_URL}"
echo ""
echo "The GCE VM syncs DAGs from GCS every 5 minutes."
echo "To trigger a DAG immediately, open the Airflow UI or run:"
echo "  gcloud compute ssh f1-airflow-vm --zone=us-central1-a -- \\"
echo "    'docker-compose -f /opt/airflow/docker-compose.yml exec airflow-scheduler \\"
echo "     airflow dags trigger f1_data_pipeline'"
