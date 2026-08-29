#!/usr/bin/env bash
# Sovereign Edge multihost HA cluster (two physical appliances).
set -euo pipefail

ACTION="${1:-status}"
shift || true

NODE_ID="${SOVEREIGN_NODE_ID:-a}"
LOCAL_HOST="${SOVEREIGN_LOCAL_HOST:-}"
PEER_HOST="${SOVEREIGN_PEER_HOST:-}"
PEER_NODE_ID="${SOVEREIGN_PEER_NODE_ID:-b}"
API_PORT="${SOVEREIGN_NODE_PORT:-8443}"
PEER_PORT="${SOVEREIGN_PEER_PORT:-8443}"
CLUSTER_ID="${SOVEREIGN_CLUSTER_ID:-}"
JOIN_TOKEN="${SOVEREIGN_JOIN_TOKEN:-}"
RUN_DIR="${SOVEREIGN_CLUSTER_RUN_DIR:-/run/sovereign-multihost}"

find_appliance_src() {
  for base in /opt/junexis/appliance-src /opt/kevantic/appliance-src /opt/mssp-control/kevantic-appliance; do
    [[ -f "$base/appliance/sovereign/cluster.py" ]] && { echo "$base"; return 0; }
  done
  return 1
}

APPLIANCE_SRC="$(find_appliance_src || true)"
[[ -n "$APPLIANCE_SRC" ]] || { echo "cluster module not found" >&2; exit 2; }
export PYTHONPATH="${APPLIANCE_SRC}:${PYTHONPATH:-}"
export SOVEREIGN_CLUSTER_TOPOLOGY=multihost

run_cluster_py() {
  python3 - "$@" <<'PY'
import json, os, sys
sys.path.insert(0, os.environ.get("PYTHONPATH", "").split(":")[0])
from appliance.sovereign import cluster

action = sys.argv[1]
args = sys.argv[2:]

if action == "pair":
    out = cluster.bootstrap_multihost(
        node_id=args[0],
        local_host=args[1],
        peer_node_id=args[2],
        peer_host=args[3],
        api_port=int(args[4]),
        peer_port=int(args[5]),
        cluster_id=os.environ.get("SOVEREIGN_CLUSTER_ID") or None,
        join_token=os.environ.get("SOVEREIGN_JOIN_TOKEN") or None,
    )
elif action == "status":
    out = cluster.cluster_status(os.environ.get("SOVEREIGN_NODE_ID") or None)
elif action == "publish":
    try:
        out = cluster.publish_artifacts(args[0])
    except ValueError as exc:
        out = {"ok": False, "error": str(exc)}
elif action == "pull":
    out = cluster.pull_from_peer(args[0])
elif action == "partition-stale":
    out = cluster.simulate_stale_node(args[0])
elif action == "write-marker":
    node_id, marker = args[0], args[1]
    root = cluster.node_state_dir(node_id)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "entitlements.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    if not isinstance(data, dict):
        data = {}
    data["cluster_write_marker"] = marker
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    out = {"ok": True, "node_id": node_id, "marker": marker}
else:
    raise SystemExit(f"unknown action {action}")
print(json.dumps(out, indent=2))
PY
}

pid_file() { echo "${RUN_DIR}/node-${NODE_ID}.pid"; }

start_node() {
  install -d -m 0755 "$RUN_DIR"
  local pf bind_ip
  bind_ip="${SOVEREIGN_NODE_BIND:-0.0.0.0}"
  pf="$(pid_file)"
  if [[ -f "$pf" ]] && kill -0 "$(cat "$pf")" 2>/dev/null; then
    echo "node agent already running (pid $(cat "$pf"))"
    return 0
  fi
  nohup env SOVEREIGN_CLUSTER_TOPOLOGY=multihost SOVEREIGN_NODE_BIND="${bind_ip}" \
    PYTHONPATH="/opt/junexis/appliance-src:/opt/kevantic/appliance-src:${PYTHONPATH:-}" \
    python3 -m appliance.sovereign.node_agent --node-id "$NODE_ID" --port "$API_PORT" --bind "${bind_ip}" \
    >/var/log/sovereign-multihost-node.log 2>&1 &
  echo $! >"$pf"
  sleep 1
  echo "started multihost node ${NODE_ID} on ${bind_ip}:${API_PORT}"
}

stop_node() {
  local pf
  pf="$(pid_file)"
  [[ -f "$pf" ]] && kill "$(cat "$pf")" 2>/dev/null || true
  rm -f "$pf"
  pkill -f "appliance.sovereign.node_agent --node-id ${NODE_ID}" 2>/dev/null || true
  run_cluster_py partition-stale "$NODE_ID" >/dev/null 2>&1 || true
  echo "stopped multihost node ${NODE_ID}"
}

case "$ACTION" in
  pair)
    [[ -n "$LOCAL_HOST" && -n "$PEER_HOST" ]] || { echo "set SOVEREIGN_LOCAL_HOST and SOVEREIGN_PEER_HOST" >&2; exit 2; }
    run_cluster_py pair "$NODE_ID" "$LOCAL_HOST" "$PEER_NODE_ID" "$PEER_HOST" "$API_PORT" "$PEER_PORT"
    ;;
  status) run_cluster_py status ;;
  start) start_node ;;
  stop) stop_node ;;
  publish) run_cluster_py publish "${1:-$NODE_ID}" ;;
  pull) run_cluster_py pull "${1:-$NODE_ID}" ;;
  write-marker)
    MARKER="${2:-kb115-$(date +%s)}"
    run_cluster_py write-marker "${1:-$NODE_ID}" "$MARKER"
    ;;
  partition-stale) run_cluster_py partition-stale "${1:-$NODE_ID}" ;;
  vip)
    run_cluster_py status | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("active_endpoint",""))'
    ;;
  *)
    echo "usage: $0 {pair|status|start|stop|publish|pull|write-marker|partition-stale|vip}" >&2
    exit 2
    ;;
esac
