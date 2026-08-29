#!/usr/bin/env bash
# Install sovereign multihost cluster modules on a live appliance.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${1:-}"
USER="${2:-}"
SSH_KEY="${APPLIANCE_SSH_KEY:-$ROOT/.tools/build-ssh/kevantic_packer}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cp "$ROOT/appliance/sovereign/cluster.py" "$TMP/cluster.py"
cp "$ROOT/appliance/sovereign/node_agent.py" "$TMP/node_agent.py"
cp "$ROOT/scripts/sovereign_multihost_cluster.sh" "$TMP/sovereign_multihost_cluster.sh"

cat > "$TMP/install_remote.sh" <<'INSTALL'
#!/usr/bin/env bash
set -euo pipefail
for base in /opt/kevantic/appliance-src /opt/junexis/appliance-src; do
  if [[ -d "$base/appliance/sovereign" ]]; then
    install -m 0644 /tmp/cluster.py "$base/appliance/sovereign/cluster.py"
    install -m 0644 /tmp/node_agent.py "$base/appliance/sovereign/node_agent.py"
  fi
done
install -m 0755 /tmp/sovereign_multihost_cluster.sh /usr/local/sbin/sovereign-multihost-cluster
install -d -m 0755 /var/lib/sovereign-cluster /run/sovereign-multihost
INSTALL
chmod +x "$TMP/install_remote.sh"

if [[ -n "$HOST" ]]; then
  scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "$TMP/cluster.py" "$TMP/node_agent.py" "$TMP/sovereign_multihost_cluster.sh" "$TMP/install_remote.sh" \
    "${USER}@${HOST}:/tmp/"
  ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o BatchMode=yes \
    "${USER}@${HOST}" "sudo -n bash /tmp/install_remote.sh"
else
  sudo -n bash "$TMP/install_remote.sh"
fi

echo "[sovereign-multihost] installed on ${HOST:-localhost}"
