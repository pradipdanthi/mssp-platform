#!/bin/bash
# kevantic-firstboot-netconfig — interactive first-boot network wizard (console).
# Pink/magenta background, white text via newt/whiptail.
# Runs once until /var/lib/kevantic/firstboot-network.done exists.
#
# Security posture (appliance bootstrap):
# - Requires an already-authenticated interactive login (kevantic/packer).
# - Intended for Proxmox/physical console when the box has no usable IP yet.
# - Configures IP/hostname only — never activation tokens, API keys, or licenses.
# - Completes once; does not reappear on later logins unless the marker is removed.
set -euo pipefail

MARKER=/var/lib/kevantic/firstboot-network.done
NETPLAN_FILE=/etc/netplan/50-kevantic-static.yaml
TITLE="Kevantic Appliance — First Boot Network"

export NEWT_COLORS='
root=white,magenta
border=white,magenta
window=white,magenta
shadow=black,black
title=brightwhite,magenta
button=magenta,white
actbutton=brightwhite,magenta
compactbutton=white,magenta
checkbox=white,magenta
actcheckbox=magenta,white
entry=brightwhite,magenta
listbox=white,magenta
actlistbox=brightwhite,magenta
sellistbox=brightwhite,magenta
actsellistbox=brightwhite,magenta
textbox=white,magenta
acttextbox=brightwhite,magenta
helpline=white,magenta
roottext=white,magenta
emptyscale=,magenta
disabledentry=gray,magenta
label=white,magenta
'

die() { echo "ERROR: $*" >&2; exit 1; }

need_root() {
  if [[ "$(id -u)" -ne 0 ]]; then
    exec sudo -n "$0" "$@"
  fi
}

detect_iface() {
  local ifc
  ifc="$(ip -o link show | awk -F': ' '$2!="lo" && $2 !~ /@/ {print $2; exit}')"
  [[ -n "$ifc" ]] || ifc="ens18"
  printf '%s' "$ifc"
}

current_ipv4() {
  ip -4 -br addr show "$1" 2>/dev/null | awk '{print $3}' | head -1 | cut -d/ -f1 || true
}

validate_ipv4() {
  local ip="$1"
  [[ "$ip" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || return 1
  local o IFS=.
  read -r a b c d <<<"$ip"
  for o in "$a" "$b" "$c" "$d"; do
    [[ "$o" -ge 0 && "$o" -le 255 ]] || return 1
  done
  return 0
}

write_netplan() {
  local ifc="$1" addr="$2" prefix="$3" gw="$4" dns="$5"
  cat >"$NETPLAN_FILE" <<EOF
# Written by kevantic-firstboot-netconfig — do not rely on Proxmox cloud-init for LAN IP.
network:
  version: 2
  ethernets:
    ${ifc}:
      addresses:
        - "${addr}/${prefix}"
      nameservers:
        addresses:
          - "${dns}"
      routes:
        - to: default
          via: "${gw}"
EOF
  chmod 600 "$NETPLAN_FILE"
  # Avoid fights with leftover cloud-init netplan
  rm -f /etc/netplan/50-cloud-init.yaml
  mkdir -p /etc/cloud/cloud.cfg.d
  printf 'network: {config: disabled}\n' >/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
  netplan generate
  netplan apply
}

set_hostname_safe() {
  local hn="$1"
  [[ "$hn" =~ ^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$ ]] || die "invalid hostname"
  hostnamectl set-hostname "$hn"
  if grep -qE '^10\.0\.0\.|127\.0\.1\.1' /etc/hosts 2>/dev/null; then
    sed -i "s/^127\\.0\\.1\\.1.*/127.0.1.1\t${hn}/" /etc/hosts || true
  else
    grep -q "$hn" /etc/hosts || echo "127.0.1.1	${hn}" >>/etc/hosts
  fi
}

show_status() {
  local ifc="$1"
  local msg
  msg="$(ip -br link; echo; ip -4 -br a; echo; echo "Hostname: $(hostname)"; echo "Marker: $([[ -f $MARKER ]] && echo done || echo pending)")"
  whiptail --title "$TITLE" --msgbox "$msg" 20 70 || true
}

configure_flow() {
  local ifc="$1"
  local addr prefix gw dns hn

  addr="$(whiptail --title "$TITLE" --inputbox "IPv4 address for ${ifc}" 10 60 "192.168.0.226" 3>&1 1>&2 2>&3)" || return 1
  validate_ipv4 "$addr" || { whiptail --title "$TITLE" --msgbox "Invalid IPv4: $addr" 8 50; return 1; }

  prefix="$(whiptail --title "$TITLE" --inputbox "Prefix length (CIDR, e.g. 24)" 10 60 "24" 3>&1 1>&2 2>&3)" || return 1
  [[ "$prefix" =~ ^[0-9]+$ && "$prefix" -ge 1 && "$prefix" -le 32 ]] || {
    whiptail --title "$TITLE" --msgbox "Invalid prefix: $prefix" 8 50
    return 1
  }

  gw="$(whiptail --title "$TITLE" --inputbox "Default gateway" 10 60 "192.168.0.1" 3>&1 1>&2 2>&3)" || return 1
  validate_ipv4 "$gw" || { whiptail --title "$TITLE" --msgbox "Invalid gateway: $gw" 8 50; return 1; }

  dns="$(whiptail --title "$TITLE" --inputbox "DNS server" 10 60 "192.168.0.1" 3>&1 1>&2 2>&3)" || return 1
  validate_ipv4 "$dns" || { whiptail --title "$TITLE" --msgbox "Invalid DNS: $dns" 8 50; return 1; }

  hn="$(whiptail --title "$TITLE" --inputbox "Hostname" 10 60 "kevantic-appliance-lab-01" 3>&1 1>&2 2>&3)" || return 1

  if ! whiptail --title "$TITLE" --yesno \
    "Apply this configuration?\n\nInterface: ${ifc}\nAddress:   ${addr}/${prefix}\nGateway:   ${gw}\nDNS:       ${dns}\nHostname:  ${hn}\n\nCloud-init network will be disabled so Proxmox ipconfig cannot override this." \
    18 70; then
    return 1
  fi

  set_hostname_safe "$hn"
  write_netplan "$ifc" "$addr" "$prefix" "$gw" "$dns"
  mkdir -p "$(dirname "$MARKER")"
  date -Is >"$MARKER"
  chmod 644 "$MARKER"

  whiptail --title "$TITLE" --msgbox \
    "Network applied.\n\nIP: ${addr}/${prefix}\nHostname: ${hn}\n\nYou can now SSH from the control plane:\n  ssh kevantic@${addr}\n\nThis wizard will not run again." \
    16 70 || true
}

main_menu() {
  local ifc cur
  ifc="$(detect_iface)"
  cur="$(current_ipv4 "$ifc")"
  [[ -n "$cur" ]] || cur="(none)"

  while true; do
    if [[ -f "$MARKER" ]]; then
      whiptail --title "$TITLE" --msgbox "First-boot network already completed.\n\nRemove $MARKER to run again." 10 60 || true
      return 0
    fi

    choice="$(whiptail --title "$TITLE" --menu \
      "Welcome. Set LAN IP before registering this appliance.\n\nNIC: ${ifc}\nCurrent IPv4: ${cur}" \
      18 70 5 \
      "1" "Configure static IP / hostname" \
      "2" "Show current network status" \
      "3" "Skip for now (not recommended)" \
      "4" "Exit to shell" \
      3>&1 1>&2 2>&3)" || return 0

    case "$choice" in
      1) configure_flow "$ifc" && return 0 ;;
      2) show_status "$ifc" ;;
      3)
        whiptail --title "$TITLE" --msgbox "Skipped. Wizard will appear again on next login until configured." 9 60 || true
        return 0
        ;;
      4) return 0 ;;
    esac
  done
}

need_root "$@"
# Only interactive terminals
[[ -t 0 && -t 1 ]] || exit 0
command -v whiptail >/dev/null 2>&1 || die "whiptail is required"
main_menu
