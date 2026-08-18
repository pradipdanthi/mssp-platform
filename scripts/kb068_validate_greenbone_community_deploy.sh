#!/usr/bin/env bash
# KB-068: Validate Greenbone Community deploy automation (safe defaults).
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-068: Validate Greenbone Community Deploy Automation"
echo "======================================================================"

fail() { echo; echo "VALIDATION FAILED: $1" >&2; exit 1; }
section() { echo; echo "----------------------------------------------------------------------"; echo "$1"; echo "----------------------------------------------------------------------"; }

section "1. Required files"
for f in \
  docs/KB068_GREENBONE_COMMUNITY_DEPLOY.md \
  docs/KB052_GREENBONE_VULNERABILITY_MANAGEMENT_PLAN.md \
  ansible/playbooks/greenbone.yml \
  ansible/roles/greenbone/defaults/main.yml \
  ansible/roles/greenbone/tasks/main.yml \
  ansible/roles/greenbone/handlers/main.yml \
  scripts/kb068_validate_greenbone_community_deploy.sh
do
  [ -f "$f" ] || fail "$f missing"
  echo "found: $f"
done

section "2. Protected paths unmodified"
for p in backend-api/ frontend-customer/ frontend-admin/ postgres/init/ docker-compose.yml; do
  git diff --quiet -- "$p" || fail "$p modified"
  git diff --cached --quiet -- "$p" || fail "$p staged"
  echo "OK: $p"
done
git status --porcelain -- .env 2>/dev/null | grep -q . && fail ".env changed" || echo "OK: .env"

section "3. Safe defaults"
python3 - <<'PY'
from pathlib import Path
import yaml
d = yaml.safe_load(Path("ansible/roles/greenbone/defaults/main.yml").read_text())
assert d["greenbone_execution_mode"] == "preflight"
assert d["greenbone_live_install_approved"] is False
assert "{{ ansible_host }}" in str(d["greenbone_management_address"])
assert int(d["greenbone_minimum_memory_mb"]) >= 7800
assert int(d["greenbone_gsa_https_port"]) == 443
tasks = Path("ansible/roles/greenbone/tasks/main.yml").read_text()
assert "ansible_host is defined" in tasks
assert 'deployment_role == "greenbone"' in tasks
assert "greenbone_live_install_approved | bool" in tasks
assert "compose.yaml" in tasks
pb = Path("ansible/playbooks/greenbone.yml").read_text()
assert "hosts: greenbone" in pb
inv = Path("ansible/inventory/hosts.yml").read_text()
assert "greenbone:" in inv
assert "192.168.0.219" in inv
assert "deployment_role: greenbone" in inv
assert "id_ed25519_greenbone" in inv
print("OK: safe defaults")
PY

section "4. Doc mentions"
for n in "Greenbone" "192.168.0.219" "8 GB" "no secrets" "customer" "preflight" "KB-052" "443"; do
  grep -qi "$n" docs/KB068_GREENBONE_COMMUNITY_DEPLOY.md || fail "doc missing $n"
done
echo "OK: doc"

section "5. Final"
echo "======================================================================"
echo "KB-068 GREENBONE COMMUNITY DEPLOY VALIDATION PASSED"
echo "======================================================================"
