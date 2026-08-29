#!/usr/bin/env bash
# KB-115 Step 7: Validate ephemeral 2-VM sovereign HA sign-off.
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"

NODE_A_IP="${SOVEREIGN_HA_NODE_A_IP:-192.168.0.231}"
NODE_B_IP="${SOVEREIGN_HA_NODE_B_IP:-192.168.0.232}"
APPLIANCE_USER="${APPLIANCE_SSH_USER:-junexis}"
APPLIANCE_KEY="${APPLIANCE_SSH_KEY:-$ROOT/kevantic-appliance/.tools/build-ssh/kevantic_packer}"
API_PORT="${SOVEREIGN_NODE_PORT:-8443}"

pass=0
fail=0
section() { echo; echo "=== $1 ==="; }
ok() { echo "PASS: $1"; pass=$((pass + 1)); }
bad() { echo "FAIL: $1"; fail=$((fail + 1)); }

remote_a() {
  ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes \
    "${APPLIANCE_USER}@${NODE_A_IP}" "$@"
}
remote_b() {
  ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes \
    "${APPLIANCE_USER}@${NODE_B_IP}" "$@"
}

section "0. Both nodes reachable"
remote_a 'echo ok' >/dev/null 2>&1 && ok "node A ${NODE_A_IP}" || bad "node A unreachable"
remote_b 'echo ok' >/dev/null 2>&1 && ok "node B ${NODE_B_IP}" || bad "node B unreachable"

section "1. Multihost cluster paired"
STATUS_A="$(remote_a 'sudo -n env SOVEREIGN_NODE_ID=a sovereign-multihost-cluster status')"
echo "$STATUS_A" | jq -e '.topology == "multihost" and .paired == true' >/dev/null 2>&1 \
  && ok "multihost topology on A" || bad "multihost topology missing on A"

section "2. Cross-VM health endpoints"
A_HEALTH="$(remote_a "curl -s --connect-timeout 3 http://${NODE_A_IP}:${API_PORT}/health")"
B_HEALTH="$(remote_b "curl -s --connect-timeout 3 http://${NODE_B_IP}:${API_PORT}/health")"
echo "$A_HEALTH" | jq -e '.ok == true and .node_id == "a"' >/dev/null 2>&1 && ok "node A /health" || bad "node A /health"
echo "$B_HEALTH" | jq -e '.ok == true and .node_id == "b"' >/dev/null 2>&1 && ok "node B /health" || bad "node B /health"

section "3. Write on A → replicated to B"
MARKER="kb115-$(date +%s)"
remote_a "sudo -n env SOVEREIGN_NODE_ID=a sovereign-multihost-cluster write-marker a '${MARKER}'"
remote_a 'sudo -n env SOVEREIGN_NODE_ID=a sovereign-multihost-cluster publish a'
sleep 2
READ_MARKER="$(remote_b "sudo -n python3 -c \"import json; print(json.load(open('/var/lib/junexis/entitlements.json')).get('cluster_write_marker',''))\"")"
READ_MARKER="${READ_MARKER//$'\r'/}"
[[ "$READ_MARKER" == "$MARKER" ]] && ok "marker replicated A→B (${MARKER})" || bad "marker on B is '${READ_MARKER}'"

section "4. VIP follows leader"
VIP_EP="$(remote_a 'sudo -n env SOVEREIGN_NODE_ID=a sovereign-multihost-cluster vip')"
VIP_EP="${VIP_EP//$'\r'/}"
[[ "$VIP_EP" == http://* ]] && ok "active endpoint ${VIP_EP}" || bad "invalid VIP ${VIP_EP}"

section "5. Failover: stop node A agent"
remote_a 'sudo -n env SOVEREIGN_NODE_ID=a sovereign-multihost-cluster stop'
sleep 4
B_HEALTH2="$(remote_b "curl -s --connect-timeout 3 http://${NODE_B_IP}:${API_PORT}/health")"
echo "$B_HEALTH2" | jq -e '.ok == true' >/dev/null 2>&1 && ok "node B healthy after A stop" || bad "node B unhealthy"
LEADER="$(remote_b 'sudo -n env SOVEREIGN_NODE_ID=b sovereign-multihost-cluster status' | jq -r '.leader // empty')"
[[ "$LEADER" == "b" ]] && ok "leader moved to B" || bad "leader is '${LEADER}'"
remote_a 'sudo -n env SOVEREIGN_NODE_ID=a sovereign-multihost-cluster start'
sleep 2

section "6. Split-brain guard on node A"
remote_a 'sudo -n env SOVEREIGN_NODE_ID=a sovereign-multihost-cluster stop'
remote_a 'sudo -n env SOVEREIGN_NODE_ID=a sovereign-multihost-cluster partition-stale a'
PUB_A="$(remote_a 'sudo -n env SOVEREIGN_NODE_ID=a sovereign-multihost-cluster publish a 2>/dev/null || true')"
echo "$PUB_A" | jq -e '.ok == false' >/dev/null 2>&1 && echo "$PUB_A" | grep -qi 'split-brain' \
  && ok "stale A publish blocked" || bad "stale A not blocked"
PUB_B="$(remote_b 'sudo -n env SOVEREIGN_NODE_ID=b sovereign-multihost-cluster publish b 2>/dev/null || true')"
echo "$PUB_B" | jq -e '.ok == true' >/dev/null 2>&1 && ok "B publish as leader" || bad "B publish failed"
remote_a 'sudo -n env SOVEREIGN_NODE_ID=a sovereign-multihost-cluster start'
sleep 2

section "7. Unit tests"
if (cd backend-api && python3 -m unittest tests.test_sovereign_multihost_cluster -q 2>/dev/null); then
  ok "test_sovereign_multihost_cluster"
else
  bad "test_sovereign_multihost_cluster"
fi

echo
if [[ "$fail" -eq 0 ]]; then
  echo "KB-115 EPHEMERAL 2-VM HA SIGN-OFF PASSED ($pass checks)"
  exit 0
fi
echo "KB-115 EPHEMERAL 2-VM HA SIGN-OFF FAILED ($fail failed / $pass passed)"
exit 1
