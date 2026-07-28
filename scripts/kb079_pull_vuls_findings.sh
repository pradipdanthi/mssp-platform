#!/usr/bin/env bash
# KB-079: Pull latest Vuls JSON report from VM 109 → normalize → vuln sync.
# Requires a completed Vuls scan on VM 109 (config.toml + SSH keys host-local).
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:8000}"
GREENBONE_SSH_HOST="${GREENBONE_SSH_HOST:-greenbone}"
MAP_FILE="${VULN_SCAN_TARGETS_FILE:-$PROJECT_DIR/config/vuln_scan_targets.yml}"
KEY_FILE="${VULN_SYNC_API_KEY_FILE:-$PROJECT_DIR/.secrets/vuln_sync_api_key}"
VULS_ROOT="${VULS_ROOT:-/opt/mssp-vuln-free}"
REPORT_PATH="${VULS_REPORT_PATH:-$VULS_ROOT/vuls/results/latest.json}"
DRY_RUN="${DRY_RUN:-0}"

cd "$PROJECT_DIR"
fail() { echo "ERROR: $*" >&2; exit 1; }

[ -f "$MAP_FILE" ] || fail "targets file missing: $MAP_FILE"
[ -f "$KEY_FILE" ] || fail "vuln sync key missing: $KEY_FILE"
SYNC_KEY="$(tr -d '[:space:]' <"$KEY_FILE")"

TMP_REPORT="$(mktemp)"
TMP_BATCHES="$(mktemp)"
trap 'rm -f "$TMP_REPORT" "$TMP_BATCHES"' EXIT

if ! ssh -o BatchMode=yes -o ConnectTimeout=20 "$GREENBONE_SSH_HOST" \
  "sudo test -f '$REPORT_PATH'" 2>/dev/null; then
  echo "KB-079: no Vuls report at $REPORT_PATH — run a Vuls scan on VM 109 first."
  exit 0
fi

ssh -o BatchMode=yes -o ConnectTimeout=60 "$GREENBONE_SSH_HOST" \
  "sudo cat '$REPORT_PATH'" >"$TMP_REPORT"

export PYTHONPATH="$PROJECT_DIR/scripts${PYTHONPATH:+:$PYTHONPATH}"
python3 "$PROJECT_DIR/scripts/kb079_normalize_vuls_report.py" \
  "$TMP_REPORT" "$MAP_FILE" "$TMP_BATCHES"

if [[ "$DRY_RUN" == "1" ]]; then
  python3 -m json.tool <"$TMP_BATCHES" | head -80
  echo "DRY_RUN=1 — not posting."
  exit 0
fi

python3 "$PROJECT_DIR/scripts/kb079_post_vuln_sync.py" \
  "$TMP_BATCHES" "$CONTROL_PLANE_URL" "$SYNC_KEY"
echo "KB-079 Vuls pull complete."
