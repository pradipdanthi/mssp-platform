#!/usr/bin/env bash
# Create CrowdSec firewall bouncer API key if still placeholder
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BOUNCE="$ROOT/crowdsec/bouncer.yaml"
if ! docker ps --format '{{.Names}}' | grep -qx niktiar-se-crowdsec; then
  echo "crowdsec not running"; exit 0
fi
if grep -q 'changeme-lab-bouncer-key' "$BOUNCE" 2>/dev/null || [[ ! -f "$BOUNCE" ]]; then
  NAME="firewall-$(date +%s)"
  KEY="$(docker exec niktiar-se-crowdsec cscli bouncers add "$NAME" -o raw | tr -d '\r\n')"
  cat > "$BOUNCE" <<EOF
mode: iptables
update_frequency: 10s
log_mode: stdout
log_level: info
api_url: http://127.0.0.1:7422/
api_key: ${KEY}
iptables_chains:
  - INPUT
  - FORWARD
deny_action: DROP
EOF
  echo "BOUNCER_KEY_OK name=$NAME"
  cd "$ROOT/docker"
  docker compose --env-file .env up -d --force-recreate crowdsec-firewall-bouncer || true
else
  echo "BOUNCER_ALREADY_CONFIGURED"
  cd "$ROOT/docker"
  docker compose --env-file .env up -d crowdsec-firewall-bouncer || true
fi
