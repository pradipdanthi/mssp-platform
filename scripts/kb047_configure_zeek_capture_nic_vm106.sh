#!/usr/bin/env bash
# KB-047: Run on VM 106 (suricata-sensor) as secadmin with sudo.
# Configures the Zeek-dedicated capture NIC (no IP, promiscuous).
set -euo pipefail

MGMT_IF="${MGMT_IF:-eth0}"
# After Proxmox net2 hot-plug, Zeek NIC is usually the 3rd interface (not eth0, not enp6s19).
ZEEK_IF="${ZEEK_IF:-}"

detect_zeek_if() {
  if [[ -n "$ZEEK_IF" ]] && ip link show "$ZEEK_IF" &>/dev/null; then
    echo "$ZEEK_IF"
    return
  fi
  mapfile -t ifs < <(ip -o link show | awk -F': ' '{print $2}' | grep -v '^lo$' | grep -v "^${MGMT_IF}$" | grep -v '^enp6s19$' || true)
  if [[ ${#ifs[@]} -eq 1 ]]; then
    echo "${ifs[0]}"
    return
  fi
  echo "Could not auto-detect Zeek capture NIC. Set ZEEK_IF= and re-run." >&2
  exit 1
}

IFACE="$(detect_zeek_if)"
echo "Using Zeek capture interface: $IFACE"

sudo tee /etc/netplan/61-zeek-capture.yaml >/dev/null <<EOF
network:
  version: 2
  ethernets:
    ${IFACE}:
      dhcp4: false
      dhcp6: false
      optional: true
EOF
sudo chmod 600 /etc/netplan/61-zeek-capture.yaml
sudo netplan apply

echo "Zeek capture NIC $IFACE configured (no IP)."
