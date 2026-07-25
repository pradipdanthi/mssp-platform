#!/usr/bin/env bash
# KB-070: Validate Greenbone → control-plane live puller wiring.
set -euo pipefail
PROJECT_DIR="/opt/mssp-control"
cd "$PROJECT_DIR"

echo "======================================================================"
echo "KB-070: Validate Greenbone Live Puller"
echo "======================================================================"

fail() { echo; echo "VALIDATION FAILED: $1" >&2; exit 1; }
section() { echo; echo "----------------------------------------------------------------------"; echo "$1"; echo "----------------------------------------------------------------------"; }

section "1. Required files"
for f in \
  docs/KB070_GREENBONE_LIVE_PULLER.md \
  config/greenbone_host_tenant_map.yml \
  scripts/kb070_pull_greenbone_findings.sh \
  scripts/kb070_greenbone_hook_agent.py \
  scripts/kb070_greenbone_start_lab_scan.sh \
  scripts/kb070_validate_greenbone_live_puller.sh \
  docs/KB069_GREENBONE_CONTROL_PLANE_ADAPTER.md
do
  [ -f "$f" ] || fail "$f missing"
  echo "found: $f"
done

section "2. Safety"
grep -q "X-Vuln-Sync-Key" scripts/kb070_pull_greenbone_findings.sh || fail "missing sync header"
grep -q "admin.secret.env" scripts/kb070_pull_greenbone_findings.sh || fail "must read password only on scanner host"
grep -q "admin.password" scripts/kb070_greenbone_hook_agent.py || fail "hook must use password file"
if grep -q -- "--gmp-password" scripts/kb070_pull_greenbone_findings.sh; then fail "puller must not pass --gmp-password on argv"; fi
grep -q "Instant path\|instant" docs/KB070_GREENBONE_LIVE_PULLER.md || fail "doc must describe instant path"
grep -q "never commit\|Never commit\|never printed" docs/KB070_GREENBONE_LIVE_PULLER.md || fail "doc secrets rule"
grep -q "default_tenant_short_code" config/greenbone_host_tenant_map.yml || fail "map missing default"
grep -q "192.168.0.215" config/greenbone_host_tenant_map.yml || fail "map missing lab endpoint"
# Mapping file must not embed credential-looking assignments
if grep -vE '^\s*#' config/greenbone_host_tenant_map.yml | grep -qiE '(^|[^a-z])(password|api_key)\s*:'; then
  fail "secrets in map file"
fi
echo "OK: safety"

section "3. Instant hook health (VM 109)"
ssh -o BatchMode=yes -o ConnectTimeout=15 greenbone \
  'systemctl is-active mssp-greenbone-hook.service >/dev/null \
   && curl -fsS http://127.0.0.1:9271/health' \
  | grep -q 'ok' || fail "instant hook not healthy"
echo "OK: instant hook active"

section "4. Live GMP connectivity (get_version via file mount)"
ssh -o BatchMode=yes -o ConnectTimeout=15 greenbone 'bash -s' <<'REMOTE' | grep -q 'get_version_response' \
  || fail "GMP get_version failed"
set -euo pipefail
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
sudo awk -F= "/^GREENBONE_ADMIN_PASSWORD=/{print substr(\$0,index(\$0,\"=\")+1); exit}" \
  /opt/mssp-greenbone/admin.secret.env > "$W/admin.password"
printf "admin\n" > "$W/admin.user"
cat > "$W/q.py" <<'PY'
from pathlib import Path
from gvm.connections import UnixSocketConnection
from gvm.protocols.gmp import Gmp
from gvm.transforms import EtreeCheckCommandTransform
from lxml import etree
u=Path("/run/mssp/admin.user").read_text().strip(); p=Path("/run/mssp/admin.password").read_text().strip()
with Gmp(connection=UnixSocketConnection(path="/run/gvmd/gvmd.sock", timeout=60),
         transform=EtreeCheckCommandTransform()) as gmp:
    gmp.authenticate(u,p); print(etree.tostring(gmp.get_version(), encoding="unicode"))
PY
chmod 644 "$W"/*
sudo docker compose -f /opt/mssp-greenbone/community/compose.yaml -p greenbone-community-edition \
  run --rm --no-deps --user 1001 \
  -v "$W/admin.password:/run/mssp/admin.password:ro" \
  -v "$W/admin.user:/run/mssp/admin.user:ro" \
  -v "$W/q.py:/run/mssp/q.py:ro" \
  --entrypoint python3 gvm-tools /run/mssp/q.py 2>/dev/null
REMOTE
echo "OK: GMP reachable"

section "5. Dry-run puller parse"
DRY_RUN=1 ./scripts/kb070_pull_greenbone_findings.sh >/tmp/kb070-dryrun.out
grep -Eq 'Parsed findings=|No findings|DRY_RUN' /tmp/kb070-dryrun.out || fail "dry-run unexpected"
echo "OK: dry-run"
cat /tmp/kb070-dryrun.out | tail -5

section "6. Final"
echo "======================================================================"
echo "KB-070 GREENBONE LIVE PULLER VALIDATION PASSED"
echo "======================================================================"
