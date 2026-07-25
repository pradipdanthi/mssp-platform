#!/usr/bin/env bash
# KB-061: one-shot TheHive → control plane sync suitable for cron.
# Reads secrets from gitignored files when env vars are unset.
set -euo pipefail
cd /opt/mssp-control

if [[ -z "${THEHIVE_PASSWORD:-}" && -f .secrets/thehive_password ]]; then
  THEHIVE_PASSWORD="$(tr -d '\n' < .secrets/thehive_password)"
  export THEHIVE_PASSWORD
fi
if [[ -z "${SOC_SYNC_API_KEY:-}" && -f .secrets/soc_sync_api_key ]]; then
  SOC_SYNC_API_KEY="$(tr -d '\n' < .secrets/soc_sync_api_key)"
  export SOC_SYNC_API_KEY
fi

LOG_DIR=/opt/mssp-control/.secrets
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/kb061_sync.log"
{
  echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) kb061 sync start ===="
  ./scripts/kb061_sync_thehive_alerts.sh
  echo "==== $(date -u +%Y-%m-%dT%H:%M:%SZ) kb061 sync end ===="
} >>"$LOG_FILE" 2>&1
