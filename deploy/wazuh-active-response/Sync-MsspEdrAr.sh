#!/usr/bin/env bash
# MSSP: keep Linux Active Response scripts + mssp-ar.env current from Manager shared/.
# Appliance-local and direct/cloud agents both use the same applicator:
#   Manager IP from ossec.conf <address>; callback defaults to public API.
set -euo pipefail

DEFAULT_CALLBACK_URL="https://api.kevantic.com/v1/edr/actions/callback"
DEFAULT_CONTROL_PLANE_IP="192.168.0.201"
ROOT="/var/ossec"
SHARED="$ROOT/etc/shared"
BIN="$ROOT/active-response/bin"
ETC="$ROOT/etc"
STATE_DIR="/var/lib/mssp-edr-ar"

mkdir -p "$BIN" "$STATE_DIR" 2>/dev/null || true

copy_if_present() {
  local name="$1"
  if [[ -f "$SHARED/$name" ]]; then
    install -o root -g wazuh -m 0750 "$SHARED/$name" "$BIN/$name" 2>/dev/null \
      || cp -f "$SHARED/$name" "$BIN/$name"
  fi
}

for f in mssp-isolate-host mssp-kill-process mssp-block-hash Sync-MsspEdrAr.sh; do
  copy_if_present "$f"
done

# Keep a durable copy for cron when shared/ is refreshed asynchronously.
if [[ -f "$SHARED/Sync-MsspEdrAr.sh" ]]; then
  install -o root -g root -m 0750 "$SHARED/Sync-MsspEdrAr.sh" "$STATE_DIR/Sync-MsspEdrAr.sh" 2>/dev/null \
    || cp -f "$SHARED/Sync-MsspEdrAr.sh" "$STATE_DIR/Sync-MsspEdrAr.sh"
elif [[ -f "$BIN/Sync-MsspEdrAr.sh" ]]; then
  cp -f "$BIN/Sync-MsspEdrAr.sh" "$STATE_DIR/Sync-MsspEdrAr.sh" 2>/dev/null || true
fi

manager_from_conf() {
  local conf="$ETC/ossec.conf"
  [[ -f "$conf" ]] || { echo ""; return 0; }
  python3 - <<'PY' "$conf" 2>/dev/null || true
import re, sys
text = open(sys.argv[1], encoding="utf-8", errors="ignore").read()
m = re.search(r"<address>\s*([^<]+)\s*</address>", text, re.I)
print(m.group(1).strip() if m else "")
PY
}

get_kv() {
  local file="$1" key="$2"
  [[ -f "$file" ]] || { echo ""; return 0; }
  awk -F= -v k="$key" '$1==k { sub(/^[^=]*=/,""); gsub(/\r/,""); gsub(/^["'\'']|["'\'']$/,""); print; exit }' "$file"
}

DEFAULTS_FILE="$SHARED/mssp-ar.env.defaults"
PRIOR_FILE=""
for cand in "$ETC/mssp-ar.env" "$BIN/mssp-ar.env"; do
  if [[ -f "$cand" ]]; then PRIOR_FILE="$cand"; break; fi
done

MANAGER="$(manager_from_conf)"
[[ -n "$MANAGER" ]] || MANAGER="$(get_kv "$DEFAULTS_FILE" WAZUH_MANAGER_IP)"
[[ -n "$MANAGER" ]] || MANAGER="$(get_kv "$PRIOR_FILE" WAZUH_MANAGER_IP)"
[[ -n "$MANAGER" ]] || MANAGER="192.168.0.211"

CALLBACK_URL="$(get_kv "$DEFAULTS_FILE" MSSP_CALLBACK_URL)"
[[ -n "$CALLBACK_URL" ]] || CALLBACK_URL="$(get_kv "$PRIOR_FILE" MSSP_CALLBACK_URL)"
[[ -n "$CALLBACK_URL" ]] || CALLBACK_URL="$DEFAULT_CALLBACK_URL"

CONTROL_PLANE="$(get_kv "$DEFAULTS_FILE" MSSP_CONTROL_PLANE_IP)"
[[ -n "$CONTROL_PLANE" ]] || CONTROL_PLANE="$(get_kv "$PRIOR_FILE" MSSP_CONTROL_PLANE_IP)"
[[ -n "$CONTROL_PLANE" ]] || CONTROL_PLANE="$DEFAULT_CONTROL_PLANE_IP"

CALLBACK_KEY="$(get_kv "$DEFAULTS_FILE" MSSP_CALLBACK_KEY)"
[[ -n "$CALLBACK_KEY" ]] || CALLBACK_KEY="$(get_kv "$DEFAULTS_FILE" EDR_CALLBACK_API_KEY)"
if [[ -z "$CALLBACK_KEY" && -f "$SHARED/mssp-callback.key" ]]; then
  CALLBACK_KEY="$(tr -d '\r\n' < "$SHARED/mssp-callback.key")"
fi
if [[ -z "$CALLBACK_KEY" && -f "$STATE_DIR/mssp-callback.key" ]]; then
  CALLBACK_KEY="$(tr -d '\r\n' < "$STATE_DIR/mssp-callback.key")"
fi
[[ -n "$CALLBACK_KEY" ]] || CALLBACK_KEY="$(get_kv "$PRIOR_FILE" MSSP_CALLBACK_KEY)"
[[ -n "$CALLBACK_KEY" ]] || CALLBACK_KEY="$(get_kv "$PRIOR_FILE" EDR_CALLBACK_API_KEY)"

umask 077
{
  echo "WAZUH_MANAGER_IP=$MANAGER"
  echo "MSSP_CONTROL_PLANE_IP=$CONTROL_PLANE"
  echo "MSSP_CALLBACK_URL=$CALLBACK_URL"
  if [[ -n "$CALLBACK_KEY" ]]; then
    echo "MSSP_CALLBACK_KEY=$CALLBACK_KEY"
    printf '%s\n' "$CALLBACK_KEY" > "$STATE_DIR/mssp-callback.key"
    chmod 600 "$STATE_DIR/mssp-callback.key" 2>/dev/null || true
  fi
} > "$ETC/mssp-ar.env"
cp -f "$ETC/mssp-ar.env" "$BIN/mssp-ar.env" 2>/dev/null || true
chown root:wazuh "$ETC/mssp-ar.env" "$BIN/mssp-ar.env" 2>/dev/null || true
chmod 640 "$ETC/mssp-ar.env" "$BIN/mssp-ar.env" 2>/dev/null || true

# Idempotent cron (every minute) when cron.d is available.
CRON_LINE="* * * * * root /bin/bash $STATE_DIR/Sync-MsspEdrAr.sh >/dev/null 2>&1"
if [[ -d /etc/cron.d && -f "$STATE_DIR/Sync-MsspEdrAr.sh" ]]; then
  echo "$CRON_LINE" > /etc/cron.d/mssp-edr-ar-sync
  chmod 644 /etc/cron.d/mssp-edr-ar-sync 2>/dev/null || true
fi

exit 0
