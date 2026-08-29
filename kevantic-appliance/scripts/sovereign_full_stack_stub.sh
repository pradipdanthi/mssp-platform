#!/usr/bin/env bash
# Lightweight loopback stubs for TheHive (:9000) and Shuffle (:3001) on small lab appliances.
set -euo pipefail

ACTION="${1:-status}"
THEHIVE_PORT="${SOVEREIGN_THEHIVE_PORT:-9000}"
SHUFFLE_PORT="${SOVEREIGN_SHUFFLE_PORT:-3001}"
RUN_DIR="${SOVEREIGN_STUB_RUN_DIR:-/run/sovereign-full-stack}"

pid_file() { echo "${RUN_DIR}/stub-${1}.pid"; }

start_stub() {
  local name="$1" port="$2" service="$3"
  install -d -m 0755 "$RUN_DIR"
  local pf
  pf="$(pid_file "$name")"
  if [[ -f "$pf" ]] && kill -0 "$(cat "$pf")" 2>/dev/null; then
    echo "stub ${name} already running"
    return 0
  fi
  nohup python3 -c "
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
port, service = ${port}, '${service}'
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): return
    def do_GET(self):
        body = json.dumps({'ok': True, 'service': service, 'stub': True}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
HTTPServer(('127.0.0.1', port), H).serve_forever()
" >/var/log/sovereign-stub-${name}.log 2>&1 &
  echo $! >"$pf"
  sleep 0.3
  echo "started stub ${name} on 127.0.0.1:${port}"
}

stop_stub() {
  local name="$1"
  local pf
  pf="$(pid_file "$name")"
  if [[ -f "$pf" ]]; then
    kill "$(cat "$pf")" 2>/dev/null || true
    rm -f "$pf"
  fi
}

case "$ACTION" in
  start)
    start_stub thehive "$THEHIVE_PORT" "thehive"
    start_stub shuffle "$SHUFFLE_PORT" "shuffle"
    ;;
  stop)
    stop_stub thehive
    stop_stub shuffle
    ;;
  status)
    for n in thehive shuffle; do
      pf="$(pid_file "$n")"
      if [[ -f "$pf" ]] && kill -0 "$(cat "$pf")" 2>/dev/null; then
        echo "${n}: running (pid $(cat "$pf"))"
      else
        echo "${n}: stopped"
      fi
    done
    ;;
  *)
    echo "usage: $0 {start|stop|status}" >&2
    exit 2
    ;;
esac
