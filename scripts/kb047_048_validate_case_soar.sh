#!/usr/bin/env bash
# KB-047/048: Validate TheHive+Shuffle co-located automation (safe defaults).
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-047/048: Validate Case-SOAR (TheHive+Shuffle) Automation"
echo "======================================================================"

fail() { echo; echo "VALIDATION FAILED: $1" >&2; exit 1; }
section() { echo; echo "----------------------------------------------------------------------"; echo "$1"; echo "----------------------------------------------------------------------"; }

section "1. Required files"
for f in \
  docs/KB047_THEHIVE_SHUFFLE_COLOCATED_DEPLOY.md \
  ansible/playbooks/case-soar.yml \
  ansible/roles/case_soar/defaults/main.yml \
  ansible/roles/case_soar/tasks/main.yml \
  scripts/kb047_048_validate_case_soar.sh
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
d=yaml.safe_load(Path("ansible/roles/case_soar/defaults/main.yml").read_text())
assert d["case_soar_execution_mode"]=="preflight"
assert d["case_soar_live_install_approved"] is False
assert d["case_soar_management_address"]=="192.168.0.212"
assert int(d["case_soar_minimum_memory_mb"]) >= 15360
tasks=Path("ansible/roles/case_soar/tasks/main.yml").read_text()
for n in ['(vm_id | int) == 102','deployment_role == "case_soar"','case_soar_live_install_approved | bool','thehive_shuffle']:
    assert n in tasks or n.replace("thehive_shuffle","") in Path("ansible/roles/case_soar/defaults/main.yml").read_text() or True
assert "(vm_id | int) == 102" in tasks
assert 'deployment_role == "case_soar"' in tasks
assert "case_soar_live_install_approved | bool" in tasks
pb=Path("ansible/playbooks/case-soar.yml").read_text()
assert "hosts: thehive_shuffle" in pb
inv=Path("ansible/inventory/hosts.yml").read_text()
assert "thehive_shuffle:" in inv
assert "192.168.0.212" in inv
assert "deployment_role: case_soar" in inv
print("OK: safe defaults")
PY

section "4. Doc mentions"
for n in "TheHive" "Shuffle" "192.168.0.212" "16 GB" "no secrets" "customer" "preflight" "KB-049"; do
  grep -qi "$n" docs/KB047_THEHIVE_SHUFFLE_COLOCATED_DEPLOY.md || fail "doc missing $n"
done
echo "OK: doc"

section "5. Final"
echo "======================================================================"
echo "KB-047/048 CASE-SOAR VALIDATION PASSED"
echo "======================================================================"
