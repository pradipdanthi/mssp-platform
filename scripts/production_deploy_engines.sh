#!/usr/bin/env bash
# production_deploy_engines.sh — KB-094 engine deploy orchestrator (dry-run by default).
# Does NOT install engines unless MSSP_ENGINE_DEPLOY_APPROVED=1 is set.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

log() { printf '[production_deploy_engines] %s\n' "$*"; }
die() { log "ERROR: $*"; exit 1; }

INVENTORY="${MSSP_ANSIBLE_INVENTORY:-$ROOT/ansible/inventory/hosts.yml}"
CTRL_HOST="${MSSP_ANSIBLE_CONTROLLER:-192.168.0.222}"
CTRL_USER="${MSSP_ANSIBLE_CONTROLLER_USER:-secadmin}"
CTRL_KEY="${MSSP_ANSIBLE_CONTROLLER_KEY:-$HOME/.ssh/id_ed25519_automation}"
CTRL_KEY="${CTRL_KEY/#\~/$HOME}"
REMOTE_ANSIBLE="${MSSP_REMOTE_ANSIBLE:-/home/secadmin/mssp-automation/ansible}"

[[ -f "$INVENTORY" ]] || die "inventory missing: $INVENTORY (copy production.example.yml for cloud)"

# Recommended dependency order for full SOC stack
PLAYBOOK_ORDER=(
  "playbooks/wazuh-stack-install.yml"
  "playbooks/mssp-linux-midlayer-manager.yml"
  "playbooks/case-soar.yml"
  "playbooks/suricata-sensor.yml"
  "playbooks/suricata-wazuh.yml"
  "playbooks/zeek-on-suricata-sensor.yml"
  "playbooks/greenbone.yml"
  "playbooks/vuln-free-stack.yml"
  "playbooks/velociraptor.yml"
)

log "Inventory: $INVENTORY"
log "Controller: ${CTRL_USER}@${CTRL_HOST}"
log "Recommended playbook order:"
for pb in "${PLAYBOOK_ORDER[@]}"; do
  echo "  - $pb"
done

if [[ "${MSSP_ENGINE_DEPLOY_APPROVED:-}" != "1" ]]; then
  log "DRY RUN — set MSSP_ENGINE_DEPLOY_APPROVED=1 to sync controller and run bootstrap ping"
  log "Full engine install still requires per-playbook approval (Wazuh live install flags, snapshots)"
  exit 0
fi

[[ -f "$CTRL_KEY" ]] || die "controller SSH key missing: $CTRL_KEY"

log "Syncing ansible tree to controller"
"$ROOT/scripts/sync_ansible_controller.sh"

SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$CTRL_KEY" "${CTRL_USER}@${CTRL_HOST}")

log "Bootstrap connectivity check"
"${SSH[@]}" "cd '${REMOTE_ANSIBLE}' && ansible-playbook -i inventory/hosts.yml playbooks/bootstrap.yml"

log "Engine orchestrator complete (bootstrap only)."
log "Run individual playbooks from ${REMOTE_ANSIBLE} when approved — see ansible/README.md"
