#!/usr/bin/env bash
# KB-093L — Appliance Management plane (VM 114) smoke checks
set -euo pipefail
MGMT_IP="${JUNEXIS_MGMT_VM_IP:-192.168.0.224}"
pass() { echo "PASS: $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== KB-093L Appliance Management plane =="

curl -fsS "http://${MGMT_IP}:8000/health" | grep -q '"service":"junexis-appliance-mgmt"' \
  || fail "health service name"
curl -fsS "http://${MGMT_IP}:8000/health" | grep -q '"api":"ok"' \
  || fail "health api ok"
curl -fsS "http://${MGMT_IP}:8000/health" | grep -q '"database":"ok"' \
  || fail "health database"
curl -fsS "http://${MGMT_IP}:8000/health" | grep -q '"redis":"ok"' \
  || fail "health redis"
pass "VM114 /health ok"

code=$(curl -sS -o /dev/null -w '%{http_code}' "http://${MGMT_IP}:8000/appliance/channel/poll" || true)
[[ "$code" == "401" ]] || fail "channel poll expected 401 got $code"
pass "channel poll 401 (auth required)"

curl -fsS "http://127.0.0.1:8000/health" | grep -q '"api":"ok"' || fail "control-plane health"
pass "VM100 control-plane still healthy"

# Proxmox: 114 present, 113 absent
if [[ -f "$HOME/.ssh/id_ed25519_proxmox" ]]; then
  list=$(ssh -o BatchMode=yes -i "$HOME/.ssh/id_ed25519_proxmox" root@192.168.0.191 'qm list' 2>/dev/null || true)
  echo "$list" | grep -q 'junexis-appliance-mgmt' || fail "VM114 missing on Proxmox"
  if echo "$list" | grep -qE '^\s*113\s'; then
    fail "VM113 still present (expected destroyed)"
  fi
  pass "Proxmox: 114 present, 113 absent"
else
  echo "SKIP: Proxmox SSH key not found"
fi

test -f /opt/mssp-control/docs/KB093L_APPLIANCE_MANAGEMENT_PLANE_VM114.md || fail "missing KB093L doc"
pass "KB093L doc present"

# Lab defaults must point new appliances at VM 114 (not VM 100)
grep -q '192.168.0.224:8000' /opt/mssp-control/junexis-appliance/ansible/group_vars/all.yml \
  || fail "group_vars missing VM114 control plane"
grep -q '192.168.0.224:8000' /opt/mssp-control/junexis-appliance/configs/control_plane_defaults.env \
  || fail "control_plane_defaults.env missing VM114"
grep -q 'default_control_plane' /opt/mssp-control/junexis-appliance/cli/junexis-cli/junexis_cli/state.py \
  || fail "CLI missing default_control_plane helper"
grep -q 'applianceRegisterCommand' /opt/mssp-control/frontend-admin/src/pages/AppliancesPage.tsx \
  || fail "Admin missing register command helper"
pass "new-appliance gateway defaults baked in"

echo "KB093L_VALIDATE_PASS"
