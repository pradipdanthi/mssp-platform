#!/usr/bin/env bash
# Sovereign Edge full stack — TheHive, Shuffle, unified portal.
# Usage: sovereign-full-stack <enable|status|start-portal|stop-portal|stub-start|stub-stop>
set -euo pipefail

ACTION="${1:-status}"
shift || true
MODE="${SOVEREIGN_FULL_STACK_MODE:-}"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

find_appliance_src() {
  for base in /opt/junexis/appliance-src /opt/kevantic/appliance-src /opt/mssp-control/kevantic-appliance; do
    if [[ -f "$base/appliance/sovereign/full_stack.py" ]]; then
      echo "$base"
      return 0
    fi
  done
  return 1
}

APPLIANCE_SRC="$(find_appliance_src || true)"
[[ -n "$APPLIANCE_SRC" ]] || { echo "sovereign full_stack module not found" >&2; exit 2; }
export PYTHONPATH="${APPLIANCE_SRC}:${PYTHONPATH:-}"

run_py() {
  python3 - "$@" <<'PY'
import json, os, sys
sys.path.insert(0, os.environ.get("PYTHONPATH", "").split(":")[0])
from appliance.sovereign import full_stack

action = sys.argv[1]
mode = os.environ.get("SOVEREIGN_FULL_STACK_MODE") or None
dry = os.environ.get("DRY_RUN") == "1"

if action == "enable":
    out = full_stack.enable_profile(mode=mode, dry_run=dry)
elif action == "status":
    out = full_stack.show_status()
elif action == "stub-start":
    out = full_stack.start_stub_services()
elif action == "stub-stop":
    out = full_stack.stop_stub_services()
elif action == "docker-start":
    out = full_stack.start_docker_stacks()
elif action == "docker-stop":
    out = full_stack.stop_docker_stacks()
else:
    raise SystemExit(f"unknown action {action}")
print(json.dumps(out, indent=2))
PY
}

PORTAL_PID="/run/sovereign-full-stack/unified-portal.pid"

start_portal() {
  install -d -m 0755 /run/sovereign-full-stack
  if [[ -f "$PORTAL_PID" ]] && kill -0 "$(cat "$PORTAL_PID")" 2>/dev/null; then
    echo "unified portal already running (pid $(cat "$PORTAL_PID"))"
    return 0
  fi
  nohup python3 -m appliance.sovereign.unified_portal >/var/log/sovereign-unified-portal.log 2>&1 &
  echo $! >"$PORTAL_PID"
  sleep 1
  echo "unified portal started (pid $(cat "$PORTAL_PID"))"
}

stop_portal() {
  if [[ -f "$PORTAL_PID" ]]; then
    kill "$(cat "$PORTAL_PID")" 2>/dev/null || true
    rm -f "$PORTAL_PID"
  fi
  pkill -f "appliance.sovereign.unified_portal" 2>/dev/null || true
  echo "unified portal stopped"
}

export DRY_RUN
export SOVEREIGN_FULL_STACK_MODE="$MODE"

case "$ACTION" in
  enable)
    run_py enable
    start_portal
    ;;
  status)
    run_py status
    ;;
  stub-start) run_py stub-start ;;
  stub-stop) run_py stub-stop ;;
  docker-start) run_py docker-start ;;
  docker-stop) run_py docker-stop ;;
  start-portal) start_portal ;;
  stop-portal) stop_portal ;;
  *)
    echo "usage: $0 {enable|status|start-portal|stop-portal|stub-start|stub-stop|docker-start|docker-stop} [--mode stub|docker|preflight]" >&2
    exit 2
    ;;
esac
