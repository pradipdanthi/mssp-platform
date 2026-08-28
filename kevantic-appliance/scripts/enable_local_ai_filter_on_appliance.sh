#!/usr/bin/env bash
# Enable appliance-local AI filter on a live box (lab appliance 210 or field).
# Installs Ollama (if missing), pulls model, copies filter module + updates
# forwarder unit env, restarts forwarder. Default: filter ENABLED, fail-open.
#
# Usage:
#   ./enable_local_ai_filter_on_appliance.sh [user@]host
# Example:
#   ./enable_local_ai_filter_on_appliance.sh junexis@192.168.0.226
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:?usage: $0 user@host}"
SSH_KEY="${MSSP_BUILD_SSH_KEY:-$ROOT/.tools/build-ssh/kevantic_packer}"
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=accept-new)
[[ -f "$SSH_KEY" ]] && SSH_OPTS+=(-i "$SSH_KEY" -o IdentitiesOnly=yes)

log() { printf '[enable-local-ai] %s\n' "$*"; }

FILTER="$ROOT/appliance/telemetry/local_ai_filter.py"
WATCHER="$ROOT/appliance/telemetry/critical_alert_watcher.py"
PRIVACY="$ROOT/appliance/common/privacy.py"
UNIT="$ROOT/configs/systemd/kevantic-critical-alert-forwarder.service"
JUNIT="$ROOT/configs/systemd/niktiar-critical-alert-forwarder.service"
INSTALL_OLLAMA="$ROOT/scripts/install_appliance_ollama.sh"
PULL="$ROOT/scripts/pull_local_ai_model.sh"
OLLAMA_UNIT="$ROOT/configs/systemd/ollama.service"
OLLAMA_DROPIN="$ROOT/configs/systemd/ollama.service.d/override.conf"
OLLAMA_WRAPPER="$ROOT/configs/systemd/ollama-serve-pinned.sh"
OLLAMA_ENV_EX="$ROOT/configs/kevantic/ollama.env.example"

for f in "$FILTER" "$WATCHER" "$PRIVACY" "$UNIT" "$INSTALL_OLLAMA" "$PULL" "$OLLAMA_UNIT" "$OLLAMA_DROPIN" "$OLLAMA_WRAPPER" "$OLLAMA_ENV_EX"; do
  [[ -f "$f" ]] || { log "missing $f"; exit 2; }
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
cp "$FILTER" "$WATCHER" "$PRIVACY" "$UNIT" "$JUNIT" "$INSTALL_OLLAMA" "$PULL" "$OLLAMA_UNIT" "$TMP/"
mkdir -p "$TMP/ollama.service.d"
cp "$OLLAMA_DROPIN" "$TMP/ollama.service.d/override.conf"
cp "$OLLAMA_WRAPPER" "$TMP/ollama-serve-pinned.sh"
cp "$OLLAMA_ENV_EX" "$TMP/ollama.env.example"

log "Copying artifacts to ${TARGET}"
scp "${SSH_OPTS[@]}" -r \
  "$TMP/local_ai_filter.py" \
  "$TMP/critical_alert_watcher.py" \
  "$TMP/privacy.py" \
  "$TMP/kevantic-critical-alert-forwarder.service" \
  "$TMP/niktiar-critical-alert-forwarder.service" \
  "$TMP/install_appliance_ollama.sh" \
  "$TMP/pull_local_ai_model.sh" \
  "$TMP/ollama.service" \
  "$TMP/ollama.service.d" \
  "$TMP/ollama-serve-pinned.sh" \
  "$TMP/ollama.env.example" \
  "${TARGET}:/tmp/"

ssh "${SSH_OPTS[@]}" "$TARGET" 'bash -s' <<'REMOTE'
set -euo pipefail
SRC_APP="/opt/kevantic/appliance-src/appliance"
if [[ ! -d "$SRC_APP" ]]; then
  SRC_APP="/opt/niktiar/appliance-src/appliance"
fi
[[ -d "$SRC_APP" ]] || { echo "appliance-src missing" >&2; exit 2; }

sudo install -m 0644 /tmp/local_ai_filter.py "$SRC_APP/telemetry/local_ai_filter.py"
sudo install -m 0644 /tmp/critical_alert_watcher.py "$SRC_APP/telemetry/critical_alert_watcher.py"
sudo install -m 0644 /tmp/privacy.py "$SRC_APP/common/privacy.py"
sudo install -m 0644 /tmp/kevantic-critical-alert-forwarder.service /etc/systemd/system/kevantic-critical-alert-forwarder.service
sudo install -m 0644 /tmp/niktiar-critical-alert-forwarder.service /etc/systemd/system/niktiar-critical-alert-forwarder.service
sudo install -m 0755 /tmp/ollama-serve-pinned.sh /usr/local/sbin/ollama-serve-pinned.sh
sudo install -d -m 0755 /etc/kevantic /etc/niktiar
if [[ ! -f /etc/kevantic/ollama.env ]]; then
  sudo install -m 0644 /tmp/ollama.env.example /etc/kevantic/ollama.env
fi
if [[ ! -f /etc/niktiar/ollama.env ]]; then
  sudo install -m 0644 /tmp/ollama.env.example /etc/niktiar/ollama.env
fi
sudo install -d -m 0755 /etc/systemd/system/ollama.service.d
sudo install -m 0644 /tmp/ollama.service /etc/systemd/system/ollama.service
sudo install -m 0644 /tmp/ollama.service.d/override.conf /etc/systemd/system/ollama.service.d/override.conf
sudo install -m 0755 /tmp/install_appliance_ollama.sh /usr/local/sbin/install_appliance_ollama.sh
sudo install -m 0755 /tmp/pull_local_ai_model.sh /usr/local/sbin/pull_local_ai_model.sh

# Ensure filter env present in appliance.env (idempotent).
for ENVF in /etc/kevantic/appliance.env /etc/niktiar/appliance.env; do
  sudo mkdir -p "$(dirname "$ENVF")"
  sudo touch "$ENVF"
  for kv in \
    'ENABLE_LOCAL_AI_FILTER=true' \
    'LOCAL_AI_FAIL_OPEN=true' \
    'OLLAMA_URL=http://127.0.0.1:11434' \
    'LOCAL_AI_MODEL=qwen2.5:7b' \
    'LOCAL_AI_TIMEOUT_SECONDS=60' \
    'LOCAL_AI_NUM_THREAD=4' \
    'LOCAL_AI_CACHE_ENABLED=true' \
    'LOCAL_AI_CACHE_TTL_SECONDS=86400' \
    'OLLAMA_CPU_THREADS=4' \
    'OLLAMA_CORE_PINNING=0-5' \
    'OLLAMA_KEEP_ALIVE=-1'
  do
    key="${kv%%=*}"
    if sudo grep -q "^${key}=" "$ENVF" 2>/dev/null; then
      sudo sed -i "s|^${key}=.*|${kv}|" "$ENVF"
    else
      echo "$kv" | sudo tee -a "$ENVF" >/dev/null
    fi
  done
done

sudo bash /usr/local/sbin/install_appliance_ollama.sh
sudo bash /usr/local/sbin/pull_local_ai_model.sh qwen2.5:7b
sudo systemctl daemon-reload
sudo systemctl restart kevantic-critical-alert-forwarder.service || true
sudo systemctl restart niktiar-critical-alert-forwarder.service || true
sudo systemctl is-active ollama.service
echo LOCAL_AI_FILTER_ENABLED_OK
REMOTE

log "OK — local AI filter enabled on ${TARGET}"
