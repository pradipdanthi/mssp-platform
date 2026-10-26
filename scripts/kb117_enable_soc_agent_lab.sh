#!/usr/bin/env bash
# Enable KB-117 SOC agent wiring on lab VM 100 + sync/restart VM 117.
# Reads token from soc-agent/data/OPERATOR_TOKEN.txt — never prints it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOKEN_FILE="$ROOT/soc-agent/data/OPERATOR_TOKEN.txt"
ENVF="$ROOT/.env"
KEY_SSH="${SOC_AGENT_SSH_KEY:-$HOME/.ssh/id_ed25519_soc_agent}"
IP="${SOC_AGENT_IP:-192.168.0.228}"

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Missing $TOKEN_FILE" >&2
  exit 1
fi
TOKEN="$(grep '^TOKEN=' "$TOKEN_FILE" | cut -d= -f2-)"
if [[ -z "$TOKEN" ]]; then
  echo "TOKEN= missing in OPERATOR_TOKEN.txt" >&2
  exit 1
fi

umask 077
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

if [[ -f "$ENVF" ]]; then
  grep -vE '^(SOC_AGENT_ENABLED|SOC_AGENT_URL|SOC_AGENT_TOKEN|SOC_AGENT_CALLBACK_TOKEN|SOC_AGENT_TIMEOUT_SECONDS|SOC_AGENT_MIN_SEVERITY)=' "$ENVF" >"$tmp" || true
else
  : >"$tmp"
fi
{
  echo "SOC_AGENT_ENABLED=true"
  echo "SOC_AGENT_URL=http://${IP}:8443"
  echo "SOC_AGENT_TOKEN=${TOKEN}"
  echo "SOC_AGENT_TIMEOUT_SECONDS=90"
  echo "SOC_AGENT_MIN_SEVERITY=medium"
} >>"$tmp"

if ! grep -q '^AI_DEEP_TRIAGE_ENABLED=' "$tmp"; then
  echo 'AI_DEEP_TRIAGE_ENABLED=true' >>"$tmp"
fi
mv "$tmp" "$ENVF"
chmod 600 "$ENVF"
echo "Updated control-plane .env with SOC_AGENT_* (values not shown)"

tar -C "$ROOT/soc-agent" -czf - app data/OPERATOR_TOKEN.txt \
  | ssh -i "$KEY_SSH" -o BatchMode=yes "secadmin@${IP}" 'tar -C /opt/soc-agent -xzf -'

ssh -i "$KEY_SSH" -o BatchMode=yes "secadmin@${IP}" 'bash -s' <<'REMOTE'
set -euo pipefail
ENV=/opt/soc-agent/.env
TF=/opt/soc-agent/data/OPERATOR_TOKEN.txt
TOKEN=$(grep '^TOKEN=' "$TF" | cut -d= -f2-)
test -n "$TOKEN"
touch "$ENV"
chmod 600 "$ENV"
grep -vE '^(MSSP_CALLBACK_URL|MSSP_CALLBACK_TOKEN|SOC_AGENT_INGEST_TOKEN)=' "$ENV" >"$ENV.tmp" || true
mv "$ENV.tmp" "$ENV"
printf '%s\n' \
  'MSSP_CALLBACK_URL=http://192.168.0.201:8000' \
  "MSSP_CALLBACK_TOKEN=${TOKEN}" \
  "SOC_AGENT_INGEST_TOKEN=${TOKEN}" >>"$ENV"
sudo systemctl restart mssp-soc-agent
sleep 2
curl -fsS http://127.0.0.1:8443/health | python3 -c 'import sys,json; d=json.load(sys.stdin); print("agent", d["status"], d["llm"]["cursor"])'
REMOTE

echo "DONE — restart control plane (production_deploy_control_plane.sh) to load SOC_AGENT_*"
