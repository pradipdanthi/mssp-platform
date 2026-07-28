#!/usr/bin/env bash
# KB-079: Run Nuclei on VM 109 for tenant-scoped targets → normalize → POST /integrations/vuln/sync.
set -euo pipefail

PROJECT_DIR="/opt/mssp-control"
CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:8000}"
GREENBONE_SSH_HOST="${GREENBONE_SSH_HOST:-greenbone}"
MAP_FILE="${VULN_SCAN_TARGETS_FILE:-$PROJECT_DIR/config/vuln_scan_targets.yml}"
KEY_FILE="${VULN_SYNC_API_KEY_FILE:-$PROJECT_DIR/.secrets/vuln_sync_api_key}"
NUCLEI_BIN="${NUCLEI_BIN:-/opt/mssp-vuln-free/bin/nuclei}"
NUCLEI_TEMPLATES="${NUCLEI_TEMPLATES:-/opt/mssp-vuln-free/nuclei-templates}"
SEVERITIES="${NUCLEI_SEVERITIES:-critical,high,medium}"
DRY_RUN="${DRY_RUN:-0}"

cd "$PROJECT_DIR"
fail() { echo "ERROR: $*" >&2; exit 1; }

[ -f "$MAP_FILE" ] || fail "targets file missing: $MAP_FILE"
[ -f "$KEY_FILE" ] || fail "vuln sync key missing: $KEY_FILE (never commit)"
SYNC_KEY="$(tr -d '[:space:]' <"$KEY_FILE")"
[ -n "$SYNC_KEY" ] || fail "empty vuln sync key"

TMP_TARGETS="$(mktemp)"
TMP_JSONL="$(mktemp)"
TMP_BATCHES="$(mktemp)"
trap 'rm -f "$TMP_TARGETS" "$TMP_JSONL" "$TMP_BATCHES"' EXIT

python3 "$PROJECT_DIR/scripts/kb079_vuln_scan_map.py" "$MAP_FILE" | python3 - <<'PY' >"$TMP_TARGETS"
import json, sys
data = json.load(sys.stdin)
lines = []
for tenant, cfg in sorted(data.items()):
    for t in cfg.get("nuclei_targets") or []:
        lines.append(str(t).strip())
print("\n".join(dict.fromkeys(lines)))
PY

if [ ! -s "$TMP_TARGETS" ]; then
  echo "KB-079: no nuclei_targets configured — nothing to scan."
  exit 0
fi

echo "KB-079: Nuclei scan on $GREENBONE_SSH_HOST (severity=$SEVERITIES)..."
TARGETS_B64="$(base64 -w0 <"$TMP_TARGETS")"

ssh -o BatchMode=yes -o ConnectTimeout=30 "$GREENBONE_SSH_HOST" \
  "NUCLEI_BIN='$NUCLEI_BIN' NUCLEI_TEMPLATES='$NUCLEI_TEMPLATES' SEVERITIES='$SEVERITIES' TARGETS_B64='$TARGETS_B64' bash -s" \
  >"$TMP_JSONL" <<'REMOTE'
set -euo pipefail
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
echo "$TARGETS_B64" | base64 -d >"$WORKDIR/targets.txt"
if [ ! -s "$WORKDIR/targets.txt" ]; then
  exit 0
fi
sudo "$NUCLEI_BIN" \
  -ud "$NUCLEI_TEMPLATES" \
  -l "$WORKDIR/targets.txt" \
  -severity "$SEVERITIES" \
  -jsonl -silent -no-color \
  2>/dev/null || true
REMOTE

export PYTHONPATH="$PROJECT_DIR/scripts${PYTHONPATH:+:$PYTHONPATH}"
python3 "$PROJECT_DIR/scripts/kb079_normalize_nuclei_jsonl.py" \
  "$TMP_JSONL" "$MAP_FILE" "$TMP_BATCHES"

if [[ "$DRY_RUN" == "1" ]]; then
  python3 -m json.tool <"$TMP_BATCHES" | head -80
  echo "DRY_RUN=1 — not posting to control plane."
  exit 0
fi

python3 "$PROJECT_DIR/scripts/kb079_post_vuln_sync.py" \
  "$TMP_BATCHES" "$CONTROL_PLANE_URL" "$SYNC_KEY"

echo "KB-079 Nuclei pull complete."
