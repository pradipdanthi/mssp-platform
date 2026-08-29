#!/usr/bin/env bash
# Install Sovereign Edge full stack modules on a live appliance.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${1:-}"
USER="${2:-}"
SSH_KEY="${APPLIANCE_SSH_KEY:-$ROOT/.tools/build-ssh/kevantic_packer}"
MODE="${SOVEREIGN_FULL_STACK_MODE:-stub}"

log() { echo "[sovereign-full-stack] $*"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cp "$ROOT/appliance/sovereign/full_stack.py" "$TMP/full_stack.py"
cp "$ROOT/appliance/sovereign/unified_portal.py" "$TMP/unified_portal.py"
cp "$ROOT/appliance/sovereign/rbac.py" "$TMP/rbac.py"
cp -r "$ROOT/appliance/sovereign/compose" "$TMP/compose"
cp "$ROOT/scripts/sovereign_full_stack.sh" "$TMP/sovereign_full_stack.sh"
cp "$ROOT/scripts/sovereign_full_stack_stub.sh" "$TMP/sovereign_full_stack_stub.sh"

cat > "$TMP/install_full_stack_remote.sh" <<INSTALL
#!/usr/bin/env bash
set -euo pipefail
for base in /opt/kevantic/appliance-src /opt/junexis/appliance-src; do
  if [[ -d "\$base/appliance" ]]; then
    install -d -m 0755 "\$base/appliance/sovereign/compose"
    install -m 0644 /tmp/full_stack.py "\$base/appliance/sovereign/full_stack.py"
    install -m 0644 /tmp/unified_portal.py "\$base/appliance/sovereign/unified_portal.py"
    install -m 0644 /tmp/rbac.py "\$base/appliance/sovereign/rbac.py"
    install -m 0644 /tmp/compose/*.yml "\$base/appliance/sovereign/compose/"
    touch "\$base/appliance/sovereign/__init__.py" 2>/dev/null || true
  fi
done
for root in /opt/kevantic/sovereign-full-stack /opt/junexis/sovereign-full-stack; do
  install -d -m 0750 "\$root"
  install -m 0640 /tmp/compose/thehive-docker-compose.yml "\$root/thehive-docker-compose.yml"
  install -m 0640 /tmp/compose/shuffle-docker-compose.yml "\$root/shuffle-docker-compose.yml"
done
install -m 0755 /tmp/sovereign_full_stack.sh /usr/local/sbin/sovereign-full-stack
install -m 0755 /tmp/sovereign_full_stack_stub.sh /usr/local/sbin/sovereign-full-stack-stub
install -d -m 0755 /var/lib/junexis/sovereign-full-stack /var/lib/kevantic/sovereign-full-stack /run/sovereign-full-stack
INSTALL
chmod +x "$TMP/install_full_stack_remote.sh"

if [[ -n "$HOST" ]]; then
  scp -i "$SSH_KEY" -o StrictHostKeyChecking=no -r \
    "$TMP/full_stack.py" "$TMP/unified_portal.py" "$TMP/rbac.py" "$TMP/compose" \
    "$TMP/sovereign_full_stack.sh" "$TMP/sovereign_full_stack_stub.sh" "$TMP/install_full_stack_remote.sh" \
    "${USER}@${HOST}:/tmp/"
  ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o BatchMode=yes \
    "${USER}@${HOST}" "sudo -n bash /tmp/install_full_stack_remote.sh"
  ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no -o BatchMode=yes \
    "${USER}@${HOST}" "sudo -n env SOVEREIGN_FULL_STACK_MODE=${MODE} sovereign-full-stack enable"
else
  sudo -n bash "$TMP/install_full_stack_remote.sh"
  sudo -n env SOVEREIGN_FULL_STACK_MODE="${MODE}" sovereign-full-stack enable
fi

log "Sovereign full stack installed on ${HOST:-localhost} (mode=${MODE})"
