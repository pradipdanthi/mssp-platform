#!/usr/bin/env bash
# Sync /opt/mssp-control/ansible → VM 112 mssp-automation (safe refresh).
# Does NOT run install playbooks. Does NOT touch Docker/control-plane runtime.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO/ansible"
AUTO_HOST="${JUNEXIS_ANSIBLE_HOST:-192.168.0.222}"
AUTO_USER="${JUNEXIS_ANSIBLE_USER:-secadmin}"
AUTO_KEY="${JUNEXIS_ANSIBLE_SSH_KEY:-$HOME/.ssh/id_ed25519_automation}"
REMOTE_ROOT="${MSSP_AUTOMATION_ROOT:-/home/secadmin/mssp-automation}"
REMOTE_ANSIBLE="$REMOTE_ROOT/ansible"

if [[ ! -d "$SRC" ]]; then
  echo "Missing $SRC" >&2
  exit 2
fi
if [[ ! -f "$AUTO_KEY" ]]; then
  echo "Missing automation SSH key: $AUTO_KEY" >&2
  exit 2
fi

AUTO_SSH=(ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i "$AUTO_KEY" -o IdentitiesOnly=yes "${AUTO_USER}@${AUTO_HOST}")
RSH="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new -i ${AUTO_KEY} -o IdentitiesOnly=yes"

echo "=== Preflight: controller Ansible ==="
"${AUTO_SSH[@]}" 'ansible --version | head -1'

echo "=== Sync ansible tree (roles/playbooks/inventory/group_vars/cfg) ==="
"${AUTO_SSH[@]}" "mkdir -p '$REMOTE_ANSIBLE'"
if command -v rsync >/dev/null 2>&1; then
  rsync -az --delete \
    -e "$RSH" \
    --exclude '.git/' \
    --exclude '*.retry' \
    "$SRC/" "${AUTO_USER}@${AUTO_HOST}:${REMOTE_ANSIBLE}/"
else
  # VM 100 may not have rsync — tar over SSH is enough
  tar -C "$SRC" --exclude='.git' --exclude='*.retry' -czf - . \
    | "${AUTO_SSH[@]}" "mkdir -p '$REMOTE_ANSIBLE' && tar -C '$REMOTE_ANSIBLE' -xzf -"
fi

echo "=== Align SSH private keys on controller (non-destructive) ==="
# Copy keys that inventory expects and that exist on VM 100 (management keys only).
for key in id_ed25519_misp id_ed25519_velociraptor id_ed25519_linux_endpoint id_ed25519_junexis_build; do
  if [[ -f "$HOME/.ssh/$key" ]]; then
    scp -o BatchMode=yes -i "$AUTO_KEY" -o IdentitiesOnly=yes \
      "$HOME/.ssh/$key" "$HOME/.ssh/${key}.pub" \
      "${AUTO_USER}@${AUTO_HOST}:/home/secadmin/.ssh/" 2>/dev/null || \
    scp -o BatchMode=yes -i "$AUTO_KEY" -o IdentitiesOnly=yes \
      "$HOME/.ssh/$key" \
      "${AUTO_USER}@${AUTO_HOST}:/home/secadmin/.ssh/"
  fi
done

# Also copy junexis build key from appliance tree if dedicated name missing
BUILD_KEY="$REPO/junexis-appliance/.tools/build-ssh/junexis_packer"
if [[ -f "$BUILD_KEY" ]]; then
  scp -o BatchMode=yes -i "$AUTO_KEY" -o IdentitiesOnly=yes \
    "$BUILD_KEY" "${AUTO_USER}@${AUTO_HOST}:/home/secadmin/.ssh/id_ed25519_junexis_build"
  [[ -f "${BUILD_KEY}.pub" ]] && scp -o BatchMode=yes -i "$AUTO_KEY" -o IdentitiesOnly=yes \
    "${BUILD_KEY}.pub" "${AUTO_USER}@${AUTO_HOST}:/home/secadmin/.ssh/id_ed25519_junexis_build.pub" || true
fi

"${AUTO_SSH[@]}" bash -s <<'EOF'
set -euo pipefail
cd ~/.ssh
chmod 700 .
# Inventory (from control plane) expects these names; map to working controller keys.
[[ -f id_ed25519_ansible_greenbone && ! -e id_ed25519_greenbone ]] && ln -s id_ed25519_ansible_greenbone id_ed25519_greenbone
[[ -f id_ed25519_ansible_endpoint && ! -e id_ed25519_linux_endpoint ]] && ln -s id_ed25519_ansible_endpoint id_ed25519_linux_endpoint
# If both exist as real files, leave alone (do not overwrite working keys).
chmod 600 id_ed25519_* 2>/dev/null || true
chmod 644 id_ed25519_*.pub 2>/dev/null || true
# Stale host keys for rebuilt endpoint labs (safe hygiene)
ssh-keygen -R 192.168.0.215 >/dev/null 2>&1 || true
ssh-keygen -R 192.168.0.214 >/dev/null 2>&1 || true
EOF

COMMIT="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo unknown)"
NOW_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"${AUTO_SSH[@]}" "printf 'source_commit=%s\nsync_time_utc=%s\nsync_from=%s\n' '$COMMIT' '$NOW_UTC' 'vm100:/opt/mssp-control/ansible' > '$REMOTE_ROOT/SOURCE_STATE'"

echo "=== Syntax-check playbooks on VM 112 ==="
"${AUTO_SSH[@]}" bash -s <<EOF
set -euo pipefail
cd '$REMOTE_ANSIBLE'
export ANSIBLE_CONFIG='$REMOTE_ANSIBLE/ansible.cfg'
fail=0
for pb in playbooks/*.yml; do
  echo "-- syntax \$pb"
  if ! ansible-playbook --syntax-check "\$pb" >/tmp/ansible-syntax.out 2>&1; then
    echo "SYNTAX_FAIL \$pb" >&2
    cat /tmp/ansible-syntax.out >&2
    fail=1
  fi
done
exit \$fail
EOF

echo "=== Connectivity pings (read-only) ==="
"${AUTO_SSH[@]}" bash -s <<EOF
set -euo pipefail
cd '$REMOTE_ANSIBLE'
export ANSIBLE_CONFIG='$REMOTE_ANSIBLE/ansible.cfg'
# Only groups expected to be live with keys on controller
for limit in wazuh-stack thehive_shuffle suricata-sensor greenbone; do
  echo "-- ping \$limit"
  ansible all -m ping --limit "\$limit" || echo "PING_WARN \$limit"
done
# Optional: junexis build VM may not exist yet
if ansible all -m ping --limit junexis-appliance-build >/tmp/jx-ping.out 2>&1; then
  echo "-- ping junexis-appliance-build OK"
else
  echo "-- ping junexis-appliance-build skipped/unavailable (OK if VM 113 not created yet)"
fi
EOF

echo "ANSIBLE_CONTROLLER_SYNC_OK"
echo "Controller tree: ${AUTO_USER}@${AUTO_HOST}:${REMOTE_ANSIBLE}"
echo "Remember: sync ≠ redeploy. Install/upgrade playbooks still need explicit approval."
