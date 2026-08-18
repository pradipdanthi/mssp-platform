#!/usr/bin/env bash
# KB-094 — validate production portability pack (templates + deploy scripts + docs).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*"; exit 1; }

need() {
  [[ -f "$1" ]] || fail "missing $1"
}

echo "=== KB-094 production portability validation ==="

need docs/KB094_PRODUCTION_PORTABILITY_PACK.md
need deploy/RELEASE_CHECKLIST.md
need deploy/environments/README.md
need deploy/environments/control-plane.lab.example.env
need deploy/environments/control-plane.production.example.env
need deploy/environments/engines.lab.example.env
need deploy/environments/engines.production.example.env
need ansible/inventory/production.example.yml
need scripts/production_deploy_control_plane.sh
need scripts/production_deploy_engines.sh
pass "required files present"

[[ -x scripts/production_deploy_control_plane.sh ]] || fail "production_deploy_control_plane.sh not executable"
[[ -x scripts/production_deploy_engines.sh ]] || fail "production_deploy_engines.sh not executable"
pass "deploy scripts executable"

for key in POSTGRES_PASSWORD REDIS_PASSWORD JWT_SECRET APP_ENV API_PORT; do
  grep -q "^${key}=" deploy/environments/control-plane.lab.example.env \
    || fail "lab example missing ${key}"
  grep -q "^${key}=" deploy/environments/control-plane.production.example.env \
    || fail "production example missing ${key}"
done
pass "env templates include required keys"

grep -q 'APP_ENV=production' deploy/environments/control-plane.production.example.env \
  || fail "production template must set APP_ENV=production"
grep -q 'admin.kevantic.com' deploy/environments/control-plane.production.example.env \
  || fail "production template must document portal URLs"
pass "production template posture"

grep -q 'MSSP_ENGINE_DEPLOY_APPROVED' scripts/production_deploy_engines.sh \
  || fail "engine deploy must require explicit approval flag"
grep -q 'DRY RUN' scripts/production_deploy_engines.sh \
  || fail "engine deploy must default to dry-run"
pass "engine deploy safety gate"

grep -q 'frontend-admin frontend-customer' scripts/production_deploy_control_plane.sh \
  || fail "control plane deploy must recreate both frontends with backend"
grep -q '401' scripts/production_deploy_control_plane.sh \
  || fail "control plane deploy must smoke-test login proxy"
pass "control plane deploy smoke hooks"

grep -q 'VM 199' docs/KB094_PRODUCTION_PORTABILITY_PACK.md \
  || fail "KB-094 doc must reference golden VM 199"
grep -q 'production.example' docs/KB094_PRODUCTION_PORTABILITY_PACK.md \
  || fail "KB-094 doc must reference production inventory example"
pass "KB-094 documentation coverage"

grep -q 'KB-094' DOCS/CURSOR_REDEPLOYMENT_PLAYBOOK.md \
  || fail "redeployment playbook must reference KB-094"
pass "DR playbook cross-link"

need scripts/cache_sysmon_offline.sh
need scripts/verify_e2e_midlayer_edr.py
need deploy/wazuh-manager/mssp_linux_exec_rules.xml
need ansible/playbooks/mssp-linux-midlayer-manager.yml
[[ -x scripts/cache_sysmon_offline.sh ]] || fail "cache_sysmon_offline.sh not executable"
[[ -x scripts/verify_e2e_midlayer_edr.py ]] || fail "verify_e2e_midlayer_edr.py not executable"
pass "mid-layer EDR cloud portability files present"

grep -q 'cache_sysmon_offline' scripts/production_deploy_control_plane.sh \
  || fail "control plane deploy must cache Sysmon64.exe before image build"
grep -q 'mssp-linux-midlayer-manager' scripts/production_deploy_engines.sh \
  || fail "engine deploy order must include Linux mid-layer Manager rules"
grep -q 'verify_e2e_midlayer_edr' deploy/RELEASE_CHECKLIST.md \
  || fail "release checklist must run mid-layer EDR verifier"
pass "mid-layer EDR wired into cloud deploy path"

grep -q 'vm_id: 101' ansible/inventory/production.example.yml \
  || fail "production inventory example must set wazuh vm_id 101 (KB-041 lock)"
pass "production inventory documents engine vm_id locks"

echo "RESULT: PASSED"
echo "KB-094 PRODUCTION PORTABILITY PACK VALIDATION PASSED"
