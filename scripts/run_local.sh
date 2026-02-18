#!/usr/bin/env bash
# run_local.sh — mirrors the full GitHub Actions CI pipeline locally
# Usage: ./scripts/run_local.sh [--skip-terraform] [--skip-security] [--fast]

set -euo pipefail

# ─── colours ────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

# ─── flags ───────────────────────────────────────────────────────────────────
SKIP_TERRAFORM=false
SKIP_SECURITY=false
FAST=false          # --fast: skip slow tests and security

for arg in "$@"; do
  case $arg in
    --skip-terraform) SKIP_TERRAFORM=true ;;
    --skip-security)  SKIP_SECURITY=true  ;;
    --fast)           FAST=true; SKIP_SECURITY=true ;;
  esac
done

# ─── helpers ─────────────────────────────────────────────────────────────────
PASS=0; FAIL=0
declare -a RESULTS=()

step()    { echo -e "\n${BLUE}${BOLD}> $*${RESET}"; }
ok()      { echo -e "${GREEN}[OK] $*${RESET}"; }
warn()    { echo -e "${YELLOW}[WARNING] $*${RESET}"; }
fail()    { echo -e "${RED}[FAIL] $*${RESET}"; }

record() {
  local label="$1" status="$2"
  if [[ "$status" == "ok" ]]; then
    RESULTS+=("${GREEN}  [OK] ${label}${RESET}")
    (( PASS++ )) || true
  else
    RESULTS+=("${RED}  [FAIL] ${label}${RESET}")
    (( FAIL++ )) || true
  fi
}

run_check() {
  # run_check <label> <command...>
  local label="$1"; shift
  if "$@"; then
    ok "$label passed"
    record "$label" ok
  else
    fail "$label failed"
    record "$label" fail
  fi
}

# ─── repo root ───────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
echo -e "${BOLD}F1 Strategy Optimizer — Local CI${RESET}"
echo -e "Repo: ${REPO_ROOT}"
echo -e "Date: $(date)"

# ─── 1. Virtual environment ───────────────────────────────────────────────────
VENV_DIR="${REPO_ROOT}/.venv"
step "Setting up virtual environment (.venv)"

if [[ ! -d "$VENV_DIR" ]]; then
  python3 -m venv "$VENV_DIR"
  ok "Created new venv at .venv"
else
  ok "Reusing existing venv at .venv"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

step "Installing dependencies"
pip install --quiet --upgrade pip
# requirements-test.txt is a slim, conflict-free subset used for linting and
# testing.  The full requirements-f1.txt is for deployment containers only
# (it pulls in Airflow which conflicts with SQLAlchemy 2.x).
pip install --quiet -r requirements-test.txt
ok "Dependencies installed"

# ─── 2. Lint ─────────────────────────────────────────────────────────────────
step "Lint — Ruff"
run_check "ruff" ruff check src/ tests/

step "Lint — Black (format check)"
run_check "black" black --check src/ tests/

step "Lint — MyPy (type check)"
mypy src/ --ignore-missing-imports 2>&1 || true   # non-blocking, matches CI
record "mypy" ok
warn "mypy runs with continue-on-error (matching CI)"

# ─── 3. Security ─────────────────────────────────────────────────────────────
if [[ "$SKIP_SECURITY" == "false" ]]; then
  step "Security — Bandit"
  bandit -r src/ -f txt 2>&1 || true
  record "bandit" ok
  warn "bandit runs with continue-on-error (matching CI)"

  step "Security — Safety"
  safety check 2>&1 || true
  record "safety" ok
  warn "safety runs with continue-on-error (matching CI)"
else
  warn "Skipping security checks (--skip-security / --fast)"
fi

# ─── 4. Unit tests ───────────────────────────────────────────────────────────
step "Tests — Unit (pytest)"
PYTEST_FLAGS="-v --cov=src --cov-report=term-missing --cov-report=html"
if [[ "$FAST" == "true" ]]; then
  PYTEST_FLAGS="-v -x"   # stop on first failure, no coverage
fi

if pytest tests/unit/ $PYTEST_FLAGS; then
  ok "Unit tests passed"
  record "unit tests" ok
  if [[ "$FAST" == "false" ]]; then
    echo -e "${BLUE}  Coverage report: file://${REPO_ROOT}/htmlcov/index.html${RESET}"
  fi
else
  fail "Unit tests failed"
  record "unit tests" fail
fi

# ─── 5. Terraform validate ───────────────────────────────────────────────────
if [[ "$SKIP_TERRAFORM" == "false" ]]; then
  if command -v terraform &>/dev/null; then
    step "Terraform — Format check"
    if terraform -chdir=terraform fmt -check -recursive; then
      ok "terraform fmt OK"
      record "terraform fmt" ok
    else
      fail "terraform fmt would reformat files — run: terraform -chdir=terraform fmt -recursive"
      record "terraform fmt" fail
    fi

    step "Terraform — Init (no backend)"
    if terraform -chdir=terraform init -backend=false -input=false -no-color; then
      ok "terraform init OK"
      record "terraform init" ok

      step "Terraform — Validate"
      if terraform -chdir=terraform validate -no-color; then
        ok "terraform validate OK"
        record "terraform validate" ok
      else
        fail "terraform validate failed"
        record "terraform validate" fail
      fi
    else
      fail "terraform init failed"
      record "terraform init" fail
      record "terraform validate" fail
    fi
  else
    warn "terraform not found — skipping (install from https://developer.hashicorp.com/terraform/downloads)"
    warn "CI uses terraform 1.5.0"
  fi
else
  warn "Skipping terraform (--skip-terraform)"
fi

# ─── 6. Summary ──────────────────────────────────────────────────────────────
echo -e "\n${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}CI Summary${RESET}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
for r in "${RESULTS[@]}"; do echo -e "$r"; done
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "  Passed: ${GREEN}${PASS}${RESET}  Failed: ${RED}${FAIL}${RESET}"
echo ""

if [[ $FAIL -gt 0 ]]; then
  fail "Some checks failed — fix them before pushing"
  exit 1
else
  ok "All checks passed — safe to push"
  exit 0
fi
