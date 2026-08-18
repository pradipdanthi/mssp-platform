#!/usr/bin/env bash
# KB-044: Validate Suricata to Wazuh Integration (docs + safe-default automation).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-044: Validate Suricata to Wazuh Integration"
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
  "docs/KB044_SURICATA_WAZUH_INTEGRATION.md"
  "scripts/kb044_validate_suricata_wazuh_integration.sh"
  "docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md"
  "ansible/playbooks/suricata-wazuh.yml"
  "ansible/roles/suricata_wazuh/defaults/main.yml"
  "ansible/roles/suricata_wazuh/tasks/main.yml"
  "ansible/roles/suricata_wazuh/handlers/main.yml"
)

for f in "${REQUIRED[@]}"; do
  [ -f "$f" ] || fail "$f is missing"
  echo "found: $f"
done

section "2. Protected runtime paths must remain unmodified"

for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" 2>/dev/null || fail "$p has working-tree changes but KB-044 must not modify runtime/protected paths"
  git diff --cached --quiet -- "$p" 2>/dev/null || fail "$p has staged changes but KB-044 must not modify runtime/protected paths"
  echo "OK: $p unmodified"
done

if git status --porcelain -- .env 2>/dev/null | grep -q .; then
  fail ".env shows as changed/untracked"
fi
echo "OK: .env not changed/untracked."

section "3. KB044 doc required mentions"

file_mentions docs/KB044_SURICATA_WAZUH_INTEGRATION.md \
  "Suricata" \
  "Wazuh" \
  "VM 101" \
  "VM 106" \
  "eve.json" \
  "tenant_id" \
  "tenant isolation" \
  "source_platform" \
  "raw logs" \
  "never" \
  "customer portal" \
  "no secrets" \
  "KB-036" \
  "KB-037" \
  "KB-038" \
  "KB-043" \
  "KB-057" \
  "preflight" \
  "Option A"
echo "OK: KB044 doc mentions integration architecture and safety boundaries."

section "4. Suricata→Wazuh role safe defaults and identity guards"

python3 - <<'PY'
from pathlib import Path
import yaml

defaults = yaml.safe_load(Path("ansible/roles/suricata_wazuh/defaults/main.yml").read_text())
assert defaults["suricata_wazuh_execution_mode"] == "preflight"
assert defaults["suricata_wazuh_live_enroll_approved"] is False
assert defaults["wazuh_agent_version"] == "4.14.6"
assert defaults["wazuh_agent_package_version"] == "4.14.6-1"
assert "{{ wazuh_manager_ip }}" in str(defaults["wazuh_manager_address"])
assert defaults["wazuh_agent_name"] == "suricata-sensor"
assert defaults["wazuh_agent_authd_passwordless"] is True
assert defaults["suricata_eve_log_path"] == "/var/log/suricata/eve.json"
assert defaults["wazuh_agent_enrollment_password"].startswith("<SET_")

tasks = Path("ansible/roles/suricata_wazuh/tasks/main.yml").read_text()
for needle in (
    'suricata_wazuh_execution_mode == "preflight"',
    'suricata_wazuh_execution_mode == "enroll"',
    'deployment_role == "suricata_sensor"',
    "suricata_wazuh_live_enroll_approved | bool",
    "no_log: true",
    "check_mode: false",
    "wazuh-agent={{ wazuh_agent_package_version }}",
    "/var/ossec/bin/agent-auth",
    "Suricata eve.json",
    "log_format>json",
):
    assert needle in tasks, f"role tasks missing: {needle}"

pb = Path("ansible/playbooks/suricata-wazuh.yml").read_text()
assert "hosts: suricata-sensor" in pb
assert "role: suricata_wazuh" in pb
print("OK: Suricata→Wazuh role safe defaults verified.")
PY

section "5. No obvious secrets in KB-044 docs/automation"

DOC_SCAN_FILES=(
  docs/KB044_SURICATA_WAZUH_INTEGRATION.md
  ansible/roles/suricata_wazuh/defaults/main.yml
  ansible/roles/suricata_wazuh/tasks/main.yml
  ansible/playbooks/suricata-wazuh.yml
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
  fail "Possible secret material found in KB-044 files"
fi
echo "OK: no obvious secret assignments in KB-044 files."

section "6. Final verdict"

echo "======================================================================"
echo "KB-044 SURICATA WAZUH INTEGRATION VALIDATION PASSED"
echo "======================================================================"
