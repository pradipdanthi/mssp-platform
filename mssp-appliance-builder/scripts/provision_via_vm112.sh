#!/usr/bin/env bash
# provision_via_vm112.sh — Sync Kevantic-appliance + run golden_provision.yml from VM 112.
set -euo pipefail

log() { printf '[provision_via_vm112] %s\n' "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

TARGET_HOST="${MSSP_TARGET_HOST:?MSSP_TARGET_HOST required}"
TARGET_USER="${MSSP_TARGET_USER:-packer}"
TARGET_PASSWORD="${MSSP_TARGET_PASSWORD:?MSSP_TARGET_PASSWORD required — never use a hardcoded build password}"
CTRL_HOST="${MSSP_ANSIBLE_CONTROLLER:-192.168.0.222}"
CTRL_USER="${MSSP_ANSIBLE_CONTROLLER_USER:-secadmin}"
CTRL_KEY="${MSSP_ANSIBLE_CONTROLLER_KEY:-$HOME/.ssh/id_ed25519_automation}"
CTRL_KEY="${CTRL_KEY/#\~/$HOME}"
BUILDER_ROOT="${MSSP_BUILDER_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
JX_ROOT="${MSSP_KEVANTIC_ROOT:-$(cd "$BUILDER_ROOT/../kevantic-appliance" && pwd)}"
REMOTE_JX="${MSSP_REMOTE_KEVANTIC:-/home/secadmin/mssp-automation/kevantic-appliance}"
REMOTE_BUILDER="${MSSP_REMOTE_BUILDER:-/home/secadmin/mssp-automation/mssp-appliance-builder}"
BUILD_KEY_REMOTE="/home/secadmin/.ssh/id_ed25519_kevantic_build"
BUILD_KEY_LOCAL="${MSSP_BUILD_SSH_KEY:-$JX_ROOT/.tools/build-ssh/kevantic_packer}"

[[ -f "$CTRL_KEY" ]] || die "missing automation SSH key: $CTRL_KEY"
[[ -f "$BUILD_KEY_LOCAL" ]] || die "missing build SSH key: $BUILD_KEY_LOCAL"
[[ -f "$JX_ROOT/ansible/playbooks/install-provision.yml" ]] || die "kevantic-appliance tree missing at $JX_ROOT"
[[ -d "$JX_ROOT/iso/offline-packages" ]] || die "offline-packages missing — run b2_fetch_offline_packages.sh first"

SSH_CTRL=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes -i "$CTRL_KEY" "${CTRL_USER}@${CTRL_HOST}")
RSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes -i ${CTRL_KEY}"

log "Controller ${CTRL_USER}@${CTRL_HOST} → target ${TARGET_USER}@${TARGET_HOST}"
log "Syncing kevantic-appliance (incl. offline-packages) to VM 112 — this can take several minutes"

"${SSH_CTRL[@]}" "mkdir -p '${REMOTE_JX}' '${REMOTE_BUILDER}'"
if command -v rsync >/dev/null 2>&1; then
  rsync -az --delete \
    -e "$RSH" \
    --exclude '.cache/' \
    --exclude '.tools/packer/' \
    --exclude '.tools/pydeps/' \
    --exclude 'mkosi/mkosi.output/' \
    "$JX_ROOT/" "${CTRL_USER}@${CTRL_HOST}:${REMOTE_JX}/"
  rsync -az --delete \
    -e "$RSH" \
    --exclude 'output-mssp-appliance/' \
    --exclude '.cache/' \
    "$BUILDER_ROOT/" "${CTRL_USER}@${CTRL_HOST}:${REMOTE_BUILDER}/"
else
  log "rsync not found locally — using tar over SSH (slower but reliable)"
  tar -C "$JX_ROOT" \
    --exclude='.cache' --exclude='.tools/packer' --exclude='.tools/pydeps' --exclude='mkosi/mkosi.output' \
    -czf - . | "${SSH_CTRL[@]}" "tar -C '${REMOTE_JX}' -xzf -"
  tar -C "$BUILDER_ROOT" \
    --exclude='output-mssp-appliance' --exclude='.cache' \
    -czf - . | "${SSH_CTRL[@]}" "tar -C '${REMOTE_BUILDER}' -xzf -"
fi

scp -o BatchMode=yes -i "$CTRL_KEY" -o IdentitiesOnly=yes \
  "$BUILD_KEY_LOCAL" "${CTRL_USER}@${CTRL_HOST}:${BUILD_KEY_REMOTE}"
"${SSH_CTRL[@]}" "chmod 600 '${BUILD_KEY_REMOTE}'"

INV_REMOTE="${REMOTE_BUILDER}/.inventory-ephemeral.ini"
log "Writing key-based inventory on controller"
"${SSH_CTRL[@]}" bash -s <<EOF
set -euo pipefail
umask 077
cat > '${INV_REMOTE}' <<INV
[mssp_appliance]
${TARGET_HOST} ansible_user=${TARGET_USER} ansible_ssh_private_key_file=${BUILD_KEY_REMOTE} ansible_become=true ansible_become_method=sudo ansible_become_password=${TARGET_PASSWORD} ansible_python_interpreter=/usr/bin/python3 ansible_ssh_common_args='-o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes'

[mssp_appliance:vars]
ansible_connection=ssh
INV
chmod 600 '${INV_REMOTE}'
EOF

log "Waiting for key-based SSH from VM 112 → guest"
"${SSH_CTRL[@]}" bash -s <<EOF
set -euo pipefail
for i in \$(seq 1 90); do
  if ssh -i '${BUILD_KEY_REMOTE}' -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 \\
      ${TARGET_USER}@${TARGET_HOST} 'true' 2>/dev/null; then
    echo TARGET_SSH_KEY_OK
    break
  fi
  if [[ "\$i" -eq 90 ]]; then
    echo "Key SSH / passwordless sudo not ready on ${TARGET_HOST}" >&2
    exit 3
  fi
  sleep 5
done
command -v ansible-playbook >/dev/null
command -v rsync >/dev/null
EOF

log "Running golden_provision.yml (splash + idle engines) from VM 112"
"${SSH_CTRL[@]}" bash -s <<EOF
set -euo pipefail
export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_STDOUT_CALLBACK=yaml
export ANSIBLE_ROLES_PATH='${REMOTE_JX}/ansible/roles'
export KEVANTIC_APPLIANCE_ROOT='${REMOTE_JX}'
ansible-playbook -i '${INV_REMOTE}' \\
  '${REMOTE_BUILDER}/ansible/golden_provision.yml' \\
  -e "kevantic_controller_root=${REMOTE_JX}" \\
  -e "kevantic_install_idle_engines=true" \\
  -e "mssp_build_user=${TARGET_USER}"
PLAY_RC=\$?
rm -f '${INV_REMOTE}'
exit \$PLAY_RC
EOF

log "SUCCESS — golden provision via VM 112 complete"
exit 0
