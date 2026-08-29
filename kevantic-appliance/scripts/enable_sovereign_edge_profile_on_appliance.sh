#!/usr/bin/env bash
# Install / refresh NikTiar Sovereign Edge profile on a live appliance (single node).
# Usage:
#   ./enable_sovereign_edge_profile_on_appliance.sh [ssh-host] [ssh-user]
#   ./enable_sovereign_edge_profile_on_appliance.sh            # local (on appliance)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${1:-}"
USER="${2:-}"
SSH_KEY="${APPLIANCE_SSH_KEY:-$ROOT/.tools/build-ssh/kevantic_packer}"
CONTROL_PLANE_IP="${MSSP_CONTROL_PLANE_IP:-192.168.0.201}"
APPLIANCE_MGMT_IP="${MSSP_APPLIANCE_MGMT_IP:-192.168.0.224}"

log() { echo "[sovereign-edge] $*"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cp "$ROOT/appliance/sovereign/profile.py" "$TMP/profile.py"
cp "$ROOT/scripts/sovereign_edge_posture.sh" "$TMP/sovereign_edge_posture.sh"
cat > "$TMP/install_sovereign_remote.sh" <<INSTALL
#!/usr/bin/env bash
set -euo pipefail
install -d -m 0755 /opt/kevantic/appliance-src/appliance/sovereign /opt/junexis/appliance-src/appliance/sovereign 2>/dev/null || true
for base in /opt/kevantic/appliance-src /opt/junexis/appliance-src; do
  if [[ -d "\$base/appliance" ]]; then
    install -m 0644 /tmp/profile.py "\$base/appliance/sovereign/profile.py"
    touch "\$base/appliance/sovereign/__init__.py" 2>/dev/null || true
  fi
done
install -m 0755 /tmp/sovereign_edge_posture.sh /usr/local/sbin/sovereign-edge-posture
export KEVANTIC_CONFIG_DIR=/etc/kevantic
export NIKTIAR_CONFIG_DIR=/etc/niktiar
export JUNEXIS_CONFIG_DIR=/etc/junexis
export JUNEXIS_STATE_DIR=/var/lib/junexis
export KEVANTIC_STATE_DIR=/var/lib/kevantic
/usr/local/sbin/sovereign-edge-posture enable \\
  --control-plane-ip ${CONTROL_PLANE_IP} \\
  --appliance-mgmt-ip ${APPLIANCE_MGMT_IP}
INSTALL
chmod +x "$TMP/install_sovereign_remote.sh"

if [[ -n "$HOST" ]]; then
  scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "$TMP/profile.py" "$TMP/sovereign_edge_posture.sh" "$TMP/install_sovereign_remote.sh" \
    "${USER}@${HOST}:/tmp/"
  ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o BatchMode=yes \
    "${USER}@${HOST}" "sudo -n bash /tmp/install_sovereign_remote.sh"
else
  cp "$TMP/profile.py" "$TMP/sovereign_edge_posture.sh" /tmp/
  cp "$TMP/install_sovereign_remote.sh" /tmp/
  sudo bash /tmp/install_sovereign_remote.sh
fi

log "Sovereign Edge profile enabled on ${HOST:-localhost}"
