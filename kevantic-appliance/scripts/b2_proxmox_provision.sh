#!/usr/bin/env bash
# Provision Kevantic appliance roles onto the Proxmox build VM.
# Ansible runs on VM 112 (automation controller).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO="$(cd "$ROOT/.." && pwd)"
VM_IP="${KEVANTIC_BUILD_VM_IP:-192.168.0.223}"
CI_USER="${KEVANTIC_BUILD_CI_USER:-kevantic}"
SSH_PRIV="${KEVANTIC_BUILD_SSH_PRIV:-$ROOT/.tools/build-ssh/kevantic_packer}"
CI_PASS="${KEVANTIC_BUILD_CI_PASS:-KevanticBuildOnlyChangeMe}"

AUTO_HOST="${KEVANTIC_ANSIBLE_HOST:-192.168.0.222}"
AUTO_USER="${KEVANTIC_ANSIBLE_USER:-secadmin}"
AUTO_KEY="${KEVANTIC_ANSIBLE_SSH_KEY:-$HOME/.ssh/id_ed25519_automation}"
REMOTE_ROOT="${MSSP_AUTOMATION_ROOT:-/home/secadmin/mssp-automation}"
REMOTE_JX="${REMOTE_ROOT}/kevantic-appliance"

if [[ ! -f "$SSH_PRIV" ]]; then
  echo "Missing build SSH private key: $SSH_PRIV" >&2
  exit 2
fi
if [[ ! -f "$AUTO_KEY" ]]; then
  echo "Missing automation SSH key: $AUTO_KEY" >&2
  exit 2
fi

AUTO_SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$AUTO_KEY" -o IdentitiesOnly=yes "${AUTO_USER}@${AUTO_HOST}")
RSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i ${AUTO_KEY} -o IdentitiesOnly=yes"

echo "Waiting for SSH ${CI_USER}@${VM_IP} (build VM)..."
ssh-keygen -R "${VM_IP}" >/dev/null 2>&1 || true
for i in $(seq 1 60); do
  if ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=5 \
      -i "$SSH_PRIV" -o IdentitiesOnly=yes \
      "${CI_USER}@${VM_IP}" 'true' 2>/dev/null; then
    break
  fi
  if [[ "$i" -eq 60 ]]; then
    echo "SSH not available on ${VM_IP} — create the Proxmox build VM first." >&2
    exit 3
  fi
  sleep 5
done

echo "Bootstrap python3 on build VM..."
ssh -i "$SSH_PRIV" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
  "${CI_USER}@${VM_IP}" \
  "echo '${CI_PASS}' | sudo -S DEBIAN_FRONTEND=noninteractive apt-get update -y && echo '${CI_PASS}' | sudo -S DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-apt sudo"

echo "Refreshing controller ansible inventory/keys (safe sync, no installs)..."
"$REPO/scripts/sync_ansible_controller.sh"

echo "Syncing kevantic-appliance roles to VM 112 (${REMOTE_JX})..."
"${AUTO_SSH[@]}" "mkdir -p '${REMOTE_JX}' && rm -rf '${REMOTE_JX:?}/'* '${REMOTE_JX}'/.[!.]* 2>/dev/null || true"
if command -v rsync >/dev/null 2>&1; then
  rsync -az --delete \
    -e "$RSH" \
    --exclude '.cache/' \
    --exclude '.tools/packer/' \
    --exclude '.tools/pydeps/' \
    "$ROOT/" "${AUTO_USER}@${AUTO_HOST}:${REMOTE_JX}/"
else
  tar -C "$ROOT" \
    --exclude='.cache' --exclude='.tools/packer' --exclude='.tools/pydeps' \
    -czf - . \
    | "${AUTO_SSH[@]}" "mkdir -p '${REMOTE_JX}' && tar -C '${REMOTE_JX}' -xzf -"
fi

# Ensure controller has kevantic build key at inventory path
scp -o BatchMode=yes -i "$AUTO_KEY" -o IdentitiesOnly=yes \
  "$SSH_PRIV" "${AUTO_USER}@${AUTO_HOST}:/home/secadmin/.ssh/id_ed25519_kevantic_build"
"${AUTO_SSH[@]}" 'chmod 600 /home/secadmin/.ssh/id_ed25519_kevantic_build'

echo "Running b2-smoke.yml on VM 112 → kevantic-appliance-build..."
"${AUTO_SSH[@]}" bash -s <<EOF
set -euo pipefail
cd '${REMOTE_JX}'
export ANSIBLE_HOST_KEY_CHECKING=False
export ANSIBLE_ROLES_PATH='${REMOTE_JX}/ansible/roles'
export ANSIBLE_CONFIG='${REMOTE_JX}/ansible/ansible.cfg'
# Prefer shared controller inventory (has kevantic_appliance_build group)
INV='${REMOTE_ROOT}/ansible/inventory/hosts.yml'
ansible-playbook -i "\$INV" --limit kevantic-appliance-build \\
  ansible/playbooks/b2-smoke.yml \\
  --become --become-user=root \\
  -e 'ansible_become_password=${CI_PASS}' \\
  -e 'firewall_nftables_mode=bootstrap' \\
  -e 'firewall_nftables_src_dir=${REMOTE_JX}/hardening/nftables'
echo ANSIBLE_PLAY_OK
EOF

echo "Guest smoke checks..."
ssh -i "$SSH_PRIV" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new \
  "${CI_USER}@${VM_IP}" \
  "echo '${CI_PASS}' | sudo -S bash -eux -c '
    kevantic-cli version || true
    test -f /var/lib/kevantic/network_mode
    grep -q bootstrap /var/lib/kevantic/network_mode
    command -v nft
    test -d /opt/kevantic/appliance-src/appliance/datalake
    export PYTHONPATH=/opt/kevantic/appliance-src
    python3 -c \"from appliance.datalake import DataLakeArchiver; print(DataLakeArchiver)\"
    ! dpkg -l | grep -qi thehive
    echo B2_SMOKE_GUEST_OK
  '"

echo B2_PROXMOX_PROVISION_OK
