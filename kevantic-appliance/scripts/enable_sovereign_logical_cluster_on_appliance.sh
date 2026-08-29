#!/usr/bin/env bash
# KB-113 Step 5: Install sovereign logical cluster modules on a live appliance.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${1:-}"
USER="${2:-}"
SSH_KEY="${APPLIANCE_SSH_KEY:-$ROOT/.tools/build-ssh/kevantic_packer}"

log() { echo "[sovereign-cluster] $*"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cp "$ROOT/appliance/sovereign/cluster.py" "$TMP/cluster.py"
cp "$ROOT/appliance/sovereign/node_agent.py" "$TMP/node_agent.py"
cp "$ROOT/scripts/sovereign_logical_cluster.sh" "$TMP/sovereign_logical_cluster.sh"

cat > "$TMP/install_cluster_remote.sh" <<'INSTALL'
#!/usr/bin/env bash
set -euo pipefail
for base in /opt/kevantic/appliance-src /opt/junexis/appliance-src; do
  if [[ -d "$base/appliance" ]]; then
    install -d -m 0755 "$base/appliance/sovereign"
    install -m 0644 /tmp/cluster.py "$base/appliance/sovereign/cluster.py"
    install -m 0644 /tmp/node_agent.py "$base/appliance/sovereign/node_agent.py"
    touch "$base/appliance/sovereign/__init__.py" 2>/dev/null || true
  fi
done
install -m 0755 /tmp/sovereign_logical_cluster.sh /usr/local/sbin/sovereign-logical-cluster
install -d -m 0755 /var/lib/sovereign-cluster /var/lib/niktiar-a /var/lib/niktiar-b /run/sovereign-cluster
INSTALL
chmod +x "$TMP/install_cluster_remote.sh"

if [[ -n "$HOST" ]]; then
  scp -i "$SSH_KEY" -o StrictHostKeyChecking=no \
    "$TMP/cluster.py" "$TMP/node_agent.py" "$TMP/sovereign_logical_cluster.sh" "$TMP/install_cluster_remote.sh" \
    "${USER}@${HOST}:/tmp/"
  ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o BatchMode=yes \
    "${USER}@${HOST}" "sudo -n bash /tmp/install_cluster_remote.sh"
else
  cp "$TMP/cluster.py" "$TMP/node_agent.py" "$TMP/sovereign_logical_cluster.sh" /tmp/
  sudo -n bash "$TMP/install_cluster_remote.sh"
fi

log "Sovereign logical cluster installed on ${HOST:-localhost}"
