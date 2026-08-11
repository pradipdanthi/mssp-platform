#!/usr/bin/env bash
# First boot after autoinstall: provision Kevantic runtime + idle engines, then exit.
set -euo pipefail

LOG=/var/log/kevantic/firstboot.log
mkdir -p /var/log/kevantic /var/lib/kevantic /opt/kevantic
exec > >(tee -a "$LOG") 2>&1

MARKER=/var/lib/kevantic/firstboot.done
if [[ -f "$MARKER" ]]; then
  echo "firstboot already completed"
  exit 0
fi

echo "=== Kevantic firstboot $(date -Is) ==="
PAYLOAD="${KEVANTIC_PAYLOAD:-/opt/kevantic/payload}"
if [[ ! -d "$PAYLOAD/ansible" ]]; then
  echo "ERROR: missing payload at $PAYLOAD" >&2
  exit 2
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -y || true

# Local inventory for ansible against localhost
INV=$(mktemp)
cat >"$INV" <<'EOF'
[all]
localhost ansible_connection=local ansible_python_interpreter=/usr/bin/python3
EOF

PLAYBOOK="$PAYLOAD/ansible/playbooks/install-provision.yml"
if [[ ! -f "$PLAYBOOK" ]]; then
  PLAYBOOK="$PAYLOAD/ansible/playbooks/site.yml"
fi
if [[ ! -f "$PLAYBOOK" ]]; then
  echo "ERROR: install playbook missing" >&2
  exit 3
fi

# Roles live in $PAYLOAD/ansible/roles — not under playbooks/roles.
export ANSIBLE_CONFIG="${PAYLOAD}/ansible/ansible.cfg"
export ANSIBLE_ROLES_PATH="${PAYLOAD}/ansible/roles${ANSIBLE_ROLES_PATH:+:$ANSIBLE_ROLES_PATH}"
cd "${PAYLOAD}/ansible"

OFFLINE_POOL="$PAYLOAD/offline-packages"
if compgen -G "$OFFLINE_POOL/*.deb" >/dev/null; then
  echo "Offline engine pool: $(find "$OFFLINE_POOL" -maxdepth 1 -name '*.deb' | wc -l) deb(s)"
else
  echo "WARN: no offline .deb pool at $OFFLINE_POOL — engines need bootstrap Internet APT"
fi

ansible-playbook -i "$INV" "$PLAYBOOK" \
  -e "@${PAYLOAD}/ansible/group_vars/all.yml" \
  -e "kevantic_payload_root=$PAYLOAD" \
  -e "firewall_nftables_mode=bootstrap" \
  -e "kevantic_install_idle_engines=true" \
  -e "firewall_nftables_src_dir=$PAYLOAD/hardening/nftables" \
  -e "wazuh_local_offline_packages_dir=$OFFLINE_POOL" \
  -e "channel_agent_src_dir=$PAYLOAD/channel" \
  -e "ota_src_dir=$PAYLOAD/ota"

touch "$MARKER"
systemctl disable kevantic-firstboot.service || true
echo "=== Kevantic firstboot OK $(date -Is) ==="
echo "Next: kevantic-cli setup --token … && kevantic-cli bootstrap update && kevantic-cli network lock --yes"
