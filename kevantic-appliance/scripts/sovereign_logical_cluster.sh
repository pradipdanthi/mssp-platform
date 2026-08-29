#!/usr/bin/env bash
# Sovereign Edge logical HA cluster (single-host lab).
# Usage: sovereign-logical-cluster <pair|status|start-a|start-b|stop-a|stop-b|stop-all|publish|sync|vip|partition-stale>
set -euo pipefail

ACTION="${1:-status}"
shift || true

CLUSTER_DIR="${SOVEREIGN_CLUSTER_DIR:-/var/lib/sovereign-cluster}"
RUN_DIR="${SOVEREIGN_CLUSTER_RUN_DIR:-/run/sovereign-cluster}"
NODE_ID="${SOVEREIGN_NODE_ID:-}"
ARTIFACT="${SOVEREIGN_ARTIFACT:-entitlements.json}"

find_appliance_src() {
  for base in /opt/junexis/appliance-src /opt/kevantic/appliance-src /opt/mssp-control/kevantic-appliance; do
    if [[ -f "$base/appliance/sovereign/cluster.py" ]]; then
      echo "$base"
      return 0
    fi
  done
  return 1
}

APPLIANCE_SRC="$(find_appliance_src || true)"
if [[ -z "$APPLIANCE_SRC" ]]; then
  echo "sovereign cluster module not found" >&2
  exit 2
fi
export PYTHONPATH="${APPLIANCE_SRC}:${PYTHONPATH:-}"

run_cluster_py() {
  python3 - "$@" <<'PY'
import json
import os
import sys

sys.path.insert(0, os.environ.get("PYTHONPATH", "").split(":")[0])
from appliance.sovereign import cluster

action = sys.argv[1]
args = sys.argv[2:]

if action == "pair":
    out = cluster.bootstrap_pair()
elif action == "status":
    out = cluster.cluster_status(os.environ.get("SOVEREIGN_NODE_ID") or None)
elif action == "heartbeat":
    out = cluster.record_heartbeat(args[0])
elif action == "publish":
    try:
        out = cluster.publish_artifacts(args[0])
    except ValueError as exc:
        out = {"ok": False, "error": str(exc)}
elif action == "sync":
    out = cluster.sync_from_shared(args[0])
elif action == "partition-stale":
    out = cluster.simulate_stale_node(args[0])
elif action == "write-marker":
    node_id, marker = args[0], args[1]
    root = cluster.node_state_dir(node_id)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "entitlements.json"
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data["cluster_write_marker"] = marker
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    out = {"ok": True, "node_id": node_id, "marker": marker, "path": str(path)}
else:
    raise SystemExit(f"unknown cluster action {action}")
print(json.dumps(out, indent=2))
PY
}

pid_file() {
  echo "${RUN_DIR}/node-${1}.pid"
}

start_node() {
  local node="$1"
  local port="$2"
  install -d -m 0755 "$RUN_DIR"
  local pf
  pf="$(pid_file "$node")"
  if [[ -f "$pf" ]] && kill -0 "$(cat "$pf")" 2>/dev/null; then
    echo "node ${node} already running (pid $(cat "$pf"))"
    return 0
  fi
  nohup python3 -m appliance.sovereign.node_agent --node-id "$node" --port "$port" \
    >/var/log/sovereign-cluster-node-${node}.log 2>&1 &
  echo $! >"$pf"
  sleep 1
  echo "started node ${node} on 127.0.0.1:${port} (pid $(cat "$pf"))"
}

stop_node() {
  local node="$1"
  local pf
  pf="$(pid_file "$node")"
  if [[ -f "$pf" ]]; then
    kill "$(cat "$pf")" 2>/dev/null || true
    rm -f "$pf"
  fi
  pkill -f "appliance.sovereign.node_agent --node-id ${node}" 2>/dev/null || true
  run_cluster_py partition-stale "$node" >/dev/null 2>&1 || true
  echo "stopped node ${node}"
}

case "$ACTION" in
  pair)
    install -d -m 0755 "$CLUSTER_DIR" /var/lib/niktiar-a /var/lib/niktiar-b
  for src in /var/lib/junexis/entitlements.json /var/lib/junexis/renewal-reminder.json /var/lib/junexis/license.jws; do
    [[ -f "$src" ]] || continue
    for nid in a b; do
      install -D -m 0644 "$src" "/var/lib/niktiar-${nid}/$(basename "$src")"
    done
  done
    run_cluster_py pair
    ;;
  status)
    run_cluster_py status
    ;;
  start-a)
    start_node a 8443
    ;;
  start-b)
    start_node b 8444
    ;;
  start-all)
    start_node a 8443
    start_node b 8444
    ;;
  stop-a)
    stop_node a
    ;;
  stop-b)
    stop_node b
    ;;
  stop-all)
    stop_node a
    stop_node b
    ;;
  publish)
    NODE="${1:-a}"
    run_cluster_py publish "$NODE"
    ;;
  sync)
    NODE="${1:-b}"
    run_cluster_py sync "$NODE"
    ;;
  write-marker)
    NODE="${1:-a}"
    MARKER="${2:-kb113-$(date +%s)}"
    run_cluster_py write-marker "$NODE" "$MARKER"
    ;;
  partition-stale)
    NODE="${1:-a}"
    run_cluster_py partition-stale "$NODE"
    ;;
  vip)
    run_cluster_py status | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("active_endpoint",""))'
    ;;
  *)
    echo "usage: $0 {pair|status|start-a|start-b|start-all|stop-a|stop-b|stop-all|publish|sync|write-marker|partition-stale|vip}" >&2
    exit 2
    ;;
esac
