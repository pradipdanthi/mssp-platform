#!/usr/bin/env bash
# KB-113 Step 5: Validate sovereign logical HA failover on Beta (single host).
set -euo pipefail
ROOT="/opt/mssp-control"
cd "$ROOT"

APPLIANCE_HOST="${APPLIANCE_SSH_HOST:-192.168.0.226}"
APPLIANCE_USER="${APPLIANCE_SSH_USER:-junexis}"
APPLIANCE_KEY="${APPLIANCE_SSH_KEY:-$ROOT/kevantic-appliance/.tools/build-ssh/kevantic_packer}"

pass=0
fail=0
section() { echo; echo "=== $1 ==="; }
ok() { echo "PASS: $1"; pass=$((pass + 1)); }
bad() { echo "FAIL: $1"; fail=$((fail + 1)); }

remote() {
  ssh -i "$APPLIANCE_KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes \
    "${APPLIANCE_USER}@${APPLIANCE_HOST}" "$@"
}

section "0. Appliance reachability"
if ! remote 'echo ok' >/dev/null 2>&1; then
  echo "FAIL: appliance ${APPLIANCE_HOST} unreachable"
  exit 1
fi
ok "appliance ${APPLIANCE_HOST} reachable"

section "0.5 Preflight — logical topology and node agents"
remote 'for nid in a b; do sudo env SOVEREIGN_NODE_ID="$nid" sovereign-multihost-cluster stop 2>/dev/null || true; done'
TOPOLOGY="$(remote 'sudo -n sovereign-logical-cluster status 2>/dev/null' | jq -r '.topology // empty' || true)"
if [[ "$TOPOLOGY" != "logical_single_host" ]]; then
  remote 'sudo -n sovereign-logical-cluster stop-all 2>/dev/null || true'
  remote 'pkill -f "appliance.sovereign.node_agent" 2>/dev/null || true'
  sleep 1
  if ! remote 'sudo -n sovereign-logical-cluster pair >/dev/null 2>&1'; then
    echo "FAIL: preflight logical pair failed (topology was ${TOPOLOGY:-unset})"
    exit 1
  fi
  echo "preflight: re-paired logical cluster (was topology=${TOPOLOGY:-unset})"
else
  echo "preflight: logical_single_host topology present"
fi
remote 'sudo -n sovereign-logical-cluster start-all'
sleep 2
A_PREFLIGHT="$(remote 'curl -s --connect-timeout 3 http://127.0.0.1:8443/health || true')"
B_PREFLIGHT="$(remote 'curl -s --connect-timeout 3 http://127.0.0.1:8444/health || true')"
if ! echo "$A_PREFLIGHT" | jq -e '.ok == true and .node_id == "a"' >/dev/null 2>&1; then
  echo "FAIL: preflight node-a /health"
  exit 1
fi
if ! echo "$B_PREFLIGHT" | jq -e '.ok == true and .node_id == "b"' >/dev/null 2>&1; then
  echo "FAIL: preflight node-b /health"
  exit 1
fi
echo "preflight: node agents healthy on 8443/8444"

section "1. Cluster paired"
PAIR_JSON="$(remote 'sudo -n sovereign-logical-cluster status')"
if echo "$PAIR_JSON" | jq -e '.paired == true and .cluster_id != null' >/dev/null 2>&1; then
  ok "cluster paired (${PAIR_JSON%%$'\n'*}...)"
else
  bad "cluster not paired"
fi

section "2. Node health endpoints"
A_HEALTH="$(remote 'curl -s --connect-timeout 3 http://127.0.0.1:8443/health || true')"
B_HEALTH="$(remote 'curl -s --connect-timeout 3 http://127.0.0.1:8444/health || true')"
echo "$A_HEALTH" | jq -e '.ok == true and .node_id == "a"' >/dev/null 2>&1 && ok "node-a /health" || bad "node-a /health"
echo "$B_HEALTH" | jq -e '.ok == true and .node_id == "b"' >/dev/null 2>&1 && ok "node-b /health" || bad "node-b /health"

section "3. Write on A → readable on B"
MARKER="kb113-$(date +%s)"
remote 'sudo -n sovereign-logical-cluster stop-b'
sleep 1
remote "sudo -n sovereign-logical-cluster write-marker a '${MARKER}'"
remote 'sudo -n sovereign-logical-cluster publish a'
remote 'sudo -n sovereign-logical-cluster sync b'
remote 'sudo -n sovereign-logical-cluster start-b'
sleep 2
READ_MARKER="$(remote "python3 -c \"import json; print(json.load(open('/var/lib/niktiar-b/entitlements.json')).get('cluster_write_marker',''))\"")"
READ_MARKER="${READ_MARKER//$'\r'/}"
[[ "$READ_MARKER" == "$MARKER" ]] && ok "replicated marker on node-b (${MARKER})" || bad "marker not on node-b (got '${READ_MARKER}')"

section "4. VIP / active endpoint"
VIP_EP="$(remote 'sudo -n sovereign-logical-cluster vip')"
VIP_EP="${VIP_EP//$'\r'/}"
if [[ "$VIP_EP" == http://127.0.0.1:8443 ]] || [[ "$VIP_EP" == http://127.0.0.1:8444 ]]; then
  ok "active endpoint resolves (${VIP_EP})"
else
  bad "active endpoint invalid (${VIP_EP})"
fi

section "5. Failover: stop node-a"
remote 'sudo -n sovereign-logical-cluster stop-a'
sleep 3
B_HEALTH2="$(remote 'curl -s --connect-timeout 3 http://127.0.0.1:8444/health || true')"
echo "$B_HEALTH2" | jq -e '.ok == true' >/dev/null 2>&1 && ok "node-b healthy after node-a stop" || bad "node-b unhealthy after failover"
LEADER="$(remote 'sudo -n sovereign-logical-cluster status' | jq -r '.leader // empty')"
[[ "$LEADER" == "b" ]] && ok "leader moved to node-b" || bad "leader is '${LEADER}' (expected b)"
remote 'sudo -n sovereign-logical-cluster start-a'
sleep 2

section "6. Split-brain guard (stale node-a)"
remote 'sudo -n sovereign-logical-cluster stop-a'
remote 'sudo -n sovereign-logical-cluster partition-stale a'
PUB_A_JSON="$(remote 'sudo -n sovereign-logical-cluster publish a 2>/dev/null || true')"
if echo "$PUB_A_JSON" | jq -e '.ok == false' >/dev/null 2>&1 && echo "$PUB_A_JSON" | grep -qi 'split-brain'; then
  ok "stale node-a publish blocked"
else
  bad "stale node-a publish was not blocked"
fi
PUB_B="$(remote 'sudo -n sovereign-logical-cluster publish b 2>&1' || true)"
echo "$PUB_B" | jq -e '.ok == true' >/dev/null 2>&1 && ok "node-b publish allowed as leader" || bad "node-b publish failed"
remote 'sudo -n sovereign-logical-cluster start-all'
sleep 2

echo
if [[ "$fail" -eq 0 ]]; then
  echo "KB-113 SOVEREIGN HA FAILOVER VALIDATION PASSED ($pass checks)"
  exit 0
fi
echo "KB-113 SOVEREIGN HA FAILOVER VALIDATION FAILED ($fail failed / $pass passed)"
exit 1
