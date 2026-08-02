#!/usr/bin/env bash
# Human-readable MSSP DR backup status for operators and Cursor.
# Exit codes: 0=idle/success, 1=failed last run, 2=currently RUNNING, 3=unknown
set -euo pipefail

LOCAL_ROOT="${MSSP_DR_LOCAL_ROOT:-$HOME/MSSP_Backups}"
STATUS_FILE="${MSSP_DR_STATUS_FILE:-$LOCAL_ROOT/STATUS.json}"
LOCK_FILE="${MSSP_DR_LOCK_FILE:-$LOCAL_ROOT/BACKUP_RUNNING.lock}"
TIMER_UNIT="${MSSP_DR_TIMER_UNIT:-mssp-dr-backup.timer}"
SERVICE_UNIT="${MSSP_DR_SERVICE_UNIT:-mssp-dr-backup.service}"

echo "=== MSSP DR Backup Status ==="
echo "Checked at (local): $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "Checked at (UTC):   $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo

# systemd timer / service
if systemctl --user show "$TIMER_UNIT" >/dev/null 2>&1; then
  NEXT="$(systemctl --user show "$TIMER_UNIT" -p NextElapseUSecRealtime --value 2>/dev/null || true)"
  LAST="$(systemctl --user show "$TIMER_UNIT" -p LastTriggerUSec --value 2>/dev/null || true)"
  ACTIVE="$(systemctl --user is-active "$TIMER_UNIT" 2>/dev/null || echo unknown)"
  SVC="$(systemctl --user is-active "$SERVICE_UNIT" 2>/dev/null || echo inactive)"
  echo "Timer:   $TIMER_UNIT ($ACTIVE)"
  echo "Service: $SERVICE_UNIT ($SVC)"
  echo "Next:    ${NEXT:-unknown}"
  echo "Last:    ${LAST:-never}"
else
  echo "Timer:   not installed (run scripts/dr_install_backup_cron.sh)"
fi
echo

RUNNING=0
if [[ -f "$LOCK_FILE" ]]; then
  pid="$(awk '{print $1}' "$LOCK_FILE" 2>/dev/null || true)"
  if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
    RUNNING=1
  fi
fi
if [[ $RUNNING -eq 0 ]]; then
  svc_state="$(systemctl --user is-active "$SERVICE_UNIT" 2>/dev/null || true)"
  if [[ "$svc_state" == "activating" || "$svc_state" == "active" ]]; then
    RUNNING=1
  elif pgrep -f 'dr_scheduled_backup\.sh' >/dev/null 2>&1; then
    RUNNING=1
  elif pgrep -f 'rclone copy .*/MSSP_Backups/.*\.tar\.gz gdrive:MSSP/MSSP_Backups' >/dev/null 2>&1; then
    RUNNING=1
  fi
fi

if [[ $RUNNING -eq 1 ]]; then
  echo "STATE: RUNNING"
  echo "A full backup is currently in progress."
else
  echo "STATE: IDLE (not running right now)"
fi
echo

if [[ -f "$STATUS_FILE" ]]; then
  echo "Last status file: $STATUS_FILE"
  python3 - <<PY
import json
from pathlib import Path
p = Path("$STATUS_FILE")
try:
    d = json.loads(p.read_text())
except Exception as e:
    print(f"  (unreadable: {e})")
    raise SystemExit(0)
for k in ("state", "message", "started_at_utc", "finished_at_utc", "timestamp_utc",
          "local_path", "gdrive_path", "log_file", "pid", "host"):
    if k in d and d[k] not in (None, ""):
        print(f"  {k}: {d[k]}")
PY
else
  echo "No STATUS.json yet (no scheduled run recorded)."
fi

echo
if [[ -L "$LOCAL_ROOT/LATEST" || -d "$LOCAL_ROOT/LATEST" ]]; then
  echo "Local LATEST → $(readlink -f "$LOCAL_ROOT/LATEST" 2>/dev/null || echo "$LOCAL_ROOT/LATEST")"
fi

# Exit code for automation
if [[ $RUNNING -eq 1 ]]; then
  exit 2
fi
if [[ -f "$STATUS_FILE" ]]; then
  st="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("state",""))' "$STATUS_FILE" 2>/dev/null || true)"
  if [[ "$st" == "failed" ]]; then
    exit 1
  fi
fi
exit 0
