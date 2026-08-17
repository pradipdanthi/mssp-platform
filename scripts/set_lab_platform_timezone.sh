#!/usr/bin/env bash
# Set Asia/Kolkata on MSSP lab hosts (VM 100 already expected; engines + appliances via SSH).
set -euo pipefail

TZ_NAME="${MSSP_PLATFORM_TZ:-Asia/Kolkata}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

log() { printf '[platform_tz] %s\n' "$*"; }

set_local() {
  if command -v timedatectl >/dev/null 2>&1; then
    sudo timedatectl set-timezone "$TZ_NAME"
    timedatectl | grep -E 'Time zone|Local time'
  else
    log "timedatectl missing — skip local host"
  fi
}

set_remote() {
  local name="$1" target="$2" key="$3"
  log "Setting $name ($target) → $TZ_NAME"
  if ssh -i "$key" -o BatchMode=yes -o ConnectTimeout=6 -o StrictHostKeyChecking=accept-new \
    "$target" "sudo timedatectl set-timezone '$TZ_NAME' && timedatectl | grep -E 'Time zone|Local time'"; then
    log "OK $name"
  else
    log "WARN failed $name (SSH or sudo — VM 112 needs one interactive sudo: timedatectl set-timezone $TZ_NAME)"
  fi
}

log "Local control plane host (VM 100)"
set_local

declare -A VMS=(
  [wazuh101]="secadmin@192.168.0.211|${HOME}/.ssh/id_ed25519_wazuh_stack"
  [thehive102]="secadmin@192.168.0.212|${HOME}/.ssh/id_ed25519_case_soar"
  [linux-endpoint105]="secadmin@192.168.0.215|${HOME}/.ssh/id_ed25519_linux_endpoint"
  [suricata106]="secadmin@192.168.0.216|${HOME}/.ssh/id_ed25519_suricata"
  [misp108]="secadmin@192.168.0.218|${HOME}/.ssh/id_ed25519_misp"
  [greenbone109]="secadmin@192.168.0.219|${HOME}/.ssh/id_ed25519_greenbone"
  [velociraptor110]="secadmin@192.168.0.220|${HOME}/.ssh/id_ed25519_velociraptor"
  [automation112]="secadmin@192.168.0.222|${HOME}/.ssh/id_ed25519_automation"
  [appliance-mgmt114]="junexis@192.168.0.224|${ROOT}/kevantic-appliance/.tools/build-ssh/kevantic_packer"
  [beta-appliance226]="junexis@192.168.0.226|${ROOT}/kevantic-appliance/.tools/build-ssh/kevantic_packer"
)

for name in "${!VMS[@]}"; do
  IFS='|' read -r target key <<< "${VMS[$name]}"
  [[ -f "$key" ]] || { log "SKIP $name — missing key $key"; continue; }
  set_remote "$name" "$target" "$key"
done

log "Normalize tenant timezone aliases in Postgres (Asia/Calcutta → Asia/Kolkata)"
cd "$ROOT"
docker compose exec -T postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -c \"UPDATE tenants SET timezone = 'Asia/Kolkata' WHERE timezone IN ('Asia/Calcutta'); SELECT name, timezone FROM tenants ORDER BY name;\""

log "Recreate redis + frontends with TZ from .env (if changed)"
docker compose up -d --force-recreate redis frontend-admin frontend-customer

log "Done — platform timezone pass complete"
