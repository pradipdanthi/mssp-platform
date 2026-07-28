#!/usr/bin/env bash
# KB-047: Run on Proxmox host (labhyp) as root.
# Adds a second capture vNIC on VM 106 for Zeek and mirrors VM 105 traffic to it.
set -euo pipefail

VMID=106
SRC_TAP="tap105i0"
DST_SURICATA_TAP="tap106i1"
DST_ZEEK_TAP="tap106i2"
BR_CAPTURE="vmbr-capture"

usage() {
  echo "Usage: $0 {add-nic|mirror-enable|mirror-disable|status}"
}

add_nic() {
  if qm config "$VMID" | grep -q '^net2:'; then
    echo "net2 already present on VM $VMID"
    qm config "$VMID" | grep '^net2:'
    return 0
  fi
  qm set "$VMID" -net2 "virtio,bridge=${BR_CAPTURE},firewall=0"
  echo "Added net2 on ${BR_CAPTURE}. Hot-plug or reboot VM 106, then run guest netplan script."
}

mirror_enable() {
  # Existing Suricata mirror (KB-043) should remain; add Zeek destination.
  if ! ip link show "$SRC_TAP" &>/dev/null; then
    echo "Missing $SRC_TAP — is VM 105 running?"
    exit 1
  fi
  if ! ip link show "$DST_ZEEK_TAP" &>/dev/null; then
    echo "Missing $DST_ZEEK_TAP — add net2 and start/reboot VM 106 first."
    exit 1
  fi
  if ! tc qdisc show dev "$SRC_TAP" | grep -q clsact; then
    tc qdisc add dev "$SRC_TAP" clsact
  fi
  # Mirror to Zeek tap (priority 20; Suricata mirror typically priority 10).
  if ! tc filter show dev "$SRC_TAP" ingress | grep -q "$DST_ZEEK_TAP"; then
    tc filter add dev "$SRC_TAP" ingress protocol all prio 20 \
      mirror to "$DST_ZEEK_TAP"
  fi
  echo "Zeek mirror enabled: $SRC_TAP -> $DST_ZEEK_TAP"
}

mirror_disable() {
  if ip link show "$SRC_TAP" &>/dev/null; then
    tc filter del dev "$SRC_TAP" ingress prio 20 2>/dev/null || true
  fi
  echo "Zeek mirror rule removed (prio 20 on $SRC_TAP)."
}

status() {
  echo "=== VM $VMID NICs ==="
  qm config "$VMID" | grep -E '^net[0-9]:' || true
  echo "=== tc on $SRC_TAP ==="
  tc filter show dev "$SRC_TAP" ingress 2>/dev/null || echo "(no ingress filters)"
  ip -br link show "$DST_SURICATA_TAP" "$DST_ZEEK_TAP" 2>/dev/null || true
}

case "${1:-}" in
  add-nic) add_nic ;;
  mirror-enable) mirror_enable ;;
  mirror-disable) mirror_disable ;;
  status) status ;;
  *) usage; exit 1 ;;
esac
