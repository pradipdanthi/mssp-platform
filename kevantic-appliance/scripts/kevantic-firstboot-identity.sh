#!/usr/bin/env bash
# kevantic-firstboot-identity — one-shot clone/factory identity reset.
#
# Runs when /etc/kevantic/GOLDEN_TEMPLATE exists (left on golden images / clones).
# Before Wazuh manager/agent enrolls:
#   * regenerate /etc/machine-id (unique host identity)
#   * clear Wazuh client.keys so the node cannot reuse a prior agent identity
#   * never plant mssp-callback.key (callback secret comes from manager shared groups)
# Subsequent boots: marker removed → this unit is a no-op (ConditionPathExists).
set -euo pipefail

MARKER=/etc/kevantic/GOLDEN_TEMPLATE
DONE=/var/lib/kevantic/identity-initialized
LOG=/var/log/kevantic/firstboot-identity.log
mkdir -p /var/lib/kevantic /var/log/kevantic /etc/kevantic

exec >>"$LOG" 2>&1
echo "=== kevantic-firstboot-identity $(date -Is) ==="

if [[ ! -e "$MARKER" ]]; then
  echo "no GOLDEN_TEMPLATE marker; nothing to do"
  exit 0
fi

OLD_ID="$(tr -d '[:space:]' </etc/machine-id 2>/dev/null || true)"
echo "old_machine_id=${OLD_ID:-empty}"

# Drop stale machine-id so systemd regenerates a unique value.
rm -f /etc/machine-id /var/lib/dbus/machine-id
systemd-machine-id-setup
NEW_ID="$(tr -d '[:space:]' </etc/machine-id)"
echo "new_machine_id=${NEW_ID}"

if [[ -n "$OLD_ID" && "$OLD_ID" == "$NEW_ID" ]]; then
  echo "ERROR: machine-id did not change" >&2
  exit 1
fi

# Fresh Wazuh agent identity (manager enroll creates keys later).
if [[ -d /var/ossec/etc ]]; then
  : >/var/ossec/etc/client.keys
  chown root:wazuh /var/ossec/etc/client.keys 2>/dev/null || chown root:root /var/ossec/etc/client.keys
  chmod 640 /var/ossec/etc/client.keys
  # Ensure no privileged callback secret is baked into the image tree.
  find /var/ossec/etc/shared -name 'mssp-callback.key' -type f -delete 2>/dev/null || true
  echo "wazuh client.keys cleared; shared mssp-callback.key removed if present"
fi

# Clones get a new NIC MAC; golden netplan often pins the bake MAC and then
# has no usable address. Rewrite match MAC in /etc/netplan/*.yaml when present.
LIVE_MAC=""
for nic_addr in /sys/class/net/*/address; do
  nic="$(basename "$(dirname "$nic_addr")")"
  case "$nic" in lo|docker*|veth*|br*|virbr*) continue ;; esac
  LIVE_MAC="$(tr '[:upper:]' '[:lower:]' <"$nic_addr" | tr -d '[:space:]')"
  [[ -n "$LIVE_MAC" ]] && break
done
if [[ -n "${LIVE_MAC:-}" && -d /etc/netplan ]]; then
  for f in /etc/netplan/*.yaml /etc/netplan/*.yml; do
    [[ -f "$f" ]] || continue
    if grep -q 'macaddress:' "$f"; then
      sed -i -E "s/(macaddress:[[:space:]]*[\"']?)([0-9A-Fa-f:]+)([\"']?)/\\1${LIVE_MAC}\\3/" "$f"
      echo "netplan_mac_updated file=$f mac=$LIVE_MAC"
    fi
  done
else
  echo "netplan_mac_skip live_mac=${LIVE_MAC:-empty}"
fi

rm -f "$MARKER"
date -Is >"$DONE"
echo "identity initialized; GOLDEN_TEMPLATE removed"
echo "=== done $(date -Is) ==="
