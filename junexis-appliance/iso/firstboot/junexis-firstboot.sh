#!/usr/bin/env bash
# First boot after autoinstall: provision Junexis runtime + idle engines, then exit.
set -euo pipefail

LOG=/var/log/junexis/firstboot.log
mkdir -p /var/log/junexis /var/lib/junexis /opt/junexis
exec > >(tee -a "$LOG") 2>&1

MARKER=/var/lib/junexis/firstboot.done
if [[ -f "$MARKER" ]]; then
  echo "firstboot already completed"
  exit 0
fi

echo "=== Junexis firstboot $(date -Is) ==="
PAYLOAD="${JUNEXIS_PAYLOAD:-/opt/junexis/payload}"
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

OFFLINE_POOL="$PAYLOAD/offline-packages"
if compgen -G "$OFFLINE_POOL/*.deb" >/dev/null; then
  echo "Offline engine pool: $(find "$OFFLINE_POOL" -maxdepth 1 -name '*.deb' | wc -l) deb(s)"
else
  echo "WARN: no offline .deb pool at $OFFLINE_POOL — engines need bootstrap Internet APT"
fi

ansible-playbook -i "$INV" "$PLAYBOOK" \
  -e "junexis_payload_root=$PAYLOAD" \
  -e "firewall_nftables_mode=bootstrap" \
  -e "junexis_install_idle_engines=true" \
  -e "firewall_nftables_src_dir=$PAYLOAD/hardening/nftables" \
  -e "wazuh_local_offline_packages_dir=$OFFLINE_POOL"

touch "$MARKER"
systemctl disable junexis-firstboot.service || true
echo "=== Junexis firstboot OK $(date -Is) ==="
echo "Next: junexis-cli setup --token … && junexis-cli bootstrap update && junexis-cli network lock --yes"
