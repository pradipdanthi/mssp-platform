#!/usr/bin/env bash
# KB-043: Validate Suricata Sensor Deployment Plan + safe-default automation.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-043: Validate Suricata Sensor Deployment Plan"
echo "Target: $PROJECT_DIR"
echo "======================================================================"

fail() {
  echo
  echo "VALIDATION FAILED: $1" >&2
  exit 1
}

section() {
  echo
  echo "----------------------------------------------------------------------"
  echo "$1"
  echo "----------------------------------------------------------------------"
}

file_mentions() {
  local file="$1"
  shift
  local needle
  for needle in "$@"; do
    grep -qi "$needle" "$file" || fail "$file missing required mention: $needle"
  done
}

section "1. Required documentation and automation files exist"

REQUIRED=(
  "docs/KB043_SURICATA_SENSOR_DEPLOYMENT_PLAN.md"
  "scripts/kb043_validate_suricata_sensor_deployment_plan.sh"
  "docs/KB039_DEPLOYMENT_AUTOMATION_FOUNDATION.md"
  "ansible/playbooks/suricata-sensor.yml"
  "ansible/roles/suricata_sensor/defaults/main.yml"
  "ansible/roles/suricata_sensor/tasks/main.yml"
  "ansible/roles/suricata_sensor/handlers/main.yml"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p has working-tree changes but KB-043 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" || fail "$p has staged changes but KB-043 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB043 planning doc required mentions"

file_mentions docs/KB043_SURICATA_SENSOR_DEPLOYMENT_PLAN.md \
  "Purpose" \
  "VM 106" \
  "suricata-sensor" \
  "Suricata" \
  "IDS" \
  "KB-036" \
  "KB-037" \
  "KB-038" \
  "KB-039" \
  "KB-044" \
  "no secrets" \
  "customer portal" \
  "raw" \
  "never" \
  "passive" \
  "preflight" \
  "192.168.0.216"
echo "OK: KB043 doc mentions VM 106 plan, links, and safety boundaries."

section "4. Suricata role safe defaults and identity guards"

python3 - <<'PY'
from pathlib import Path
import yaml

defaults = yaml.safe_load(Path("ansible/roles/suricata_sensor/defaults/main.yml").read_text())
assert defaults["suricata_execution_mode"] == "preflight"
assert defaults["suricata_live_install_approved"] is False
assert "{{ ansible_host }}" in str(defaults["suricata_management_address"])
assert defaults["suricata_capture_interface"]
assert defaults["suricata_package_name"] == "suricata"

tasks = Path("ansible/roles/suricata_sensor/tasks/main.yml").read_text()
for needle in (
    'suricata_execution_mode == "preflight"',
    'suricata_execution_mode == "install"',
    'deployment_role == "suricata_sensor"',
    "suricata_live_install_approved | bool",
    "check_mode: false",
    "must have no IPv4",
    "suricata-update",
):
    assert needle in tasks, f"role tasks missing: {needle}"

pb = Path("ansible/playbooks/suricata-sensor.yml").read_text()
assert "hosts: suricata-sensor" in pb
assert "role: suricata_sensor" in pb

inv = Path("ansible/inventory/hosts.yml").read_text()
assert "suricata-sensor:" in inv
assert "192.168.0.216" in inv
assert "vm_id: 106" in inv
print("OK: Suricata role safe defaults and inventory placeholders verified.")
PY

section "5. No obvious secrets in KB-043 docs/automation"

DOC_SCAN_FILES=(
  docs/KB043_SURICATA_SENSOR_DEPLOYMENT_PLAN.md
  ansible/roles/suricata_sensor/defaults/main.yml
  ansible/roles/suricata_sensor/tasks/main.yml
  ansible/playbooks/suricata-sensor.yml
)

SECRET_HIT="$(grep -REn \
  -e 'password[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{6,}' \
  -e 'api_key[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{6,}' \
  -e 'token[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]{8,}' \
  -e 'JWT_SECRET[[:space:]]*=[[:space:]]*['\''\"][^'\''\"]+' \
  -e 'Bearer[[:space:]]+[A-Za-z0-9_-]{20,}' \
  "${DOC_SCAN_FILES[@]}" 2>/dev/null || true)"

if [ -n "$SECRET_HIT" ]; then
  echo "$SECRET_HIT" >&2
  fail "Possible secret material found in KB-043 files"
fi
echo "OK: no obvious secret assignments in KB-043 files."

section "6. Final verdict"

echo "======================================================================"
echo "KB-043 SURICATA SENSOR DEPLOYMENT PLAN VALIDATION PASSED"
echo "======================================================================"
