#!/usr/bin/env bash
# kevantic-firstboot-identity — one-shot clone/factory identity reset.
#
# Runs when /etc/kevantic/GOLDEN_TEMPLATE exists (left on golden images / clones).
# Before Wazuh manager/agent enrolls:
#   * regenerate /etc/machine-id (unique host identity)
#   * clear Wazuh client.keys so the node cannot reuse a prior agent identity
#   * never plant mssp-callback.key (callback secret comes from manager shared groups)
#   * rewrite netplan from live NIC MAC + Proxmox cloud-init IP; netplan generate
#     (no netplan apply — this unit runs before systemd-networkd exists)
# Subsequent boots: marker removed → this unit is a no-op (ConditionPathExists).
set -euo pipefail

MARKER=/etc/kevantic/GOLDEN_TEMPLATE
DONE=/var/lib/kevantic/identity-initialized
LOG=/var/log/kevantic/firstboot-identity.log
NETPLAN_OUT=/etc/netplan/50-kevantic-firstboot.yaml
CI_ENV=/run/kevantic-firstboot-ci.env
mkdir -p /var/lib/kevantic /var/log/kevantic /etc/kevantic /run

exec >>"$LOG" 2>&1
echo "=== kevantic-firstboot-identity $(date -Is) ==="

if [[ ! -e "$MARKER" ]]; then
  echo "no GOLDEN_TEMPLATE marker; nothing to do"
  exit 0
fi

OLD_ID="$(tr -d '[:space:]' </etc/machine-id 2>/dev/null || true)"
echo "old_machine_id=${OLD_ID:-empty}"

rm -f /etc/machine-id /var/lib/dbus/machine-id
systemd-machine-id-setup
NEW_ID="$(tr -d '[:space:]' </etc/machine-id)"
echo "new_machine_id=${NEW_ID}"

if [[ -n "$OLD_ID" && "$OLD_ID" == "$NEW_ID" ]]; then
  # Golden bake host: SMBIOS UUID yields the same id. Keep GOLDEN_TEMPLATE for clones.
  echo "machine-id unchanged (template/golden host); leaving GOLDEN_TEMPLATE in place"
  exit 0
fi

if [[ -d /var/ossec/etc ]]; then
  : >/var/ossec/etc/client.keys
  chown root:wazuh /var/ossec/etc/client.keys 2>/dev/null || chown root:root /var/ossec/etc/client.keys
  chmod 640 /var/ossec/etc/client.keys
  find /var/ossec/etc/shared -name 'mssp-callback.key' -type f -delete 2>/dev/null || true
  echo "wazuh client.keys cleared; shared mssp-callback.key removed if present"
fi

LIVE_MAC=""
for nic_addr in /sys/class/net/*/address; do
  nic="$(basename "$(dirname "$nic_addr")")"
  case "$nic" in lo|docker*|veth*|br*|virbr*) continue ;; esac
  LIVE_MAC="$(tr '[:upper:]' '[:lower:]' <"$nic_addr" | tr -d '[:space:]')"
  [[ -n "$LIVE_MAC" ]] && break
done
echo "live_mac=${LIVE_MAC:-empty}"

CIDATA_MNT=/run/kevantic-cidata
mkdir -p "$CIDATA_MNT"
CIDATA_MOUNTED=0
for cand in /dev/disk/by-label/cidata /dev/disk/by-label/CIDATA /dev/sr0 /dev/sr1; do
  [[ -e "$cand" ]] || continue
  if mount -o ro "$cand" "$CIDATA_MNT" 2>/dev/null; then
    CIDATA_MOUNTED=1
    echo "cidata_mounted=$cand"
    break
  fi
done

rm -f "$CI_ENV"
CIDATA_MNT="$CIDATA_MNT" python3 - <<'PY'
import os, re
mnt = os.environ["CIDATA_MNT"]
addr = prefix = gw = dns = ""
text = ""
for name in ("network-config", "network-config.yaml", "network.yaml"):
    path = os.path.join(mnt, name)
    if os.path.isfile(path):
        text = open(path, encoding="utf-8", errors="replace").read()
        print(f"cidata_network_file={name}")
        break
if not text:
    print("cidata_network_file=missing")
    open("/run/kevantic-firstboot-ci.env", "w").write("")
    raise SystemExit(0)
m = re.search(r"address:\s*['\"]?([0-9.]+)(?:/([0-9]+))?['\"]?", text)
if m:
    addr, prefix = m.group(1), (m.group(2) or "")
m = re.search(r"addresses:\s*\n\s*-\s*['\"]?([0-9.]+)(?:/([0-9]+))?['\"]?", text)
if m and not addr:
    addr, prefix = m.group(1), (m.group(2) or prefix)
m = re.search(r"netmask:\s*['\"]?([0-9.]+)['\"]?", text)
if m and not prefix:
    prefix = str(sum(bin(int(o)).count("1") for o in m.group(1).split(".")))
m = re.search(r"gateway:\s*['\"]?([0-9.]+)['\"]?", text)
if m:
    gw = m.group(1)
m = re.search(r"via:\s*['\"]?([0-9.]+)['\"]?", text)
if m and not gw:
    gw = m.group(1)
m = re.search(r"nameservers:\s*(?:\n\s*addresses:\s*)?(?:\n\s*-\s*)?['\"]?(\d+\.\d+\.\d+\.\d+)", text)
if m:
    dns = m.group(1)
if not dns:
    dns = "192.168.0.1"
if not prefix:
    prefix = "24"
with open("/run/kevantic-firstboot-ci.env", "w", encoding="utf-8") as fh:
    fh.write(f"CI_ADDR={addr}\nCI_PREFIX={prefix}\nCI_GW={gw}\nCI_DNS={dns}\n")
print(f"parsed addr={addr}/{prefix} gw={gw} dns={dns}")
PY

# shellcheck disable=SC1090
source "$CI_ENV" 2>/dev/null || true
echo "ci_addr=${CI_ADDR:-} ci_prefix=${CI_PREFIX:-} ci_gw=${CI_GW:-} ci_dns=${CI_DNS:-}"

if [[ -z "${LIVE_MAC:-}" || -z "${CI_ADDR:-}" || -z "${CI_GW:-}" ]]; then
  echo "ERROR: cannot build clone netplan (need live MAC + cloud-init address/gateway)" >&2
  [[ "$CIDATA_MOUNTED" == 1 ]] && umount "$CIDATA_MNT" 2>/dev/null || true
  exit 1
fi

mkdir -p /etc/netplan /etc/cloud/cloud.cfg.d
rm -f /etc/netplan/50-cloud-init.yaml /etc/netplan/50-cloud-init.yml
printf 'network: {config: disabled}\n' >/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
cat >"$NETPLAN_OUT" <<EOF
# Written by kevantic-firstboot-identity — clone MAC + Proxmox cloud-init IP.
network:
  version: 2
  ethernets:
    eth0:
      match:
        macaddress: "${LIVE_MAC}"
      set-name: "eth0"
      addresses:
      - "${CI_ADDR}/${CI_PREFIX:-24}"
      nameservers:
        addresses:
        - "${CI_DNS:-192.168.0.1}"
      routes:
      - to: default
        via: "${CI_GW}"
EOF
chmod 600 "$NETPLAN_OUT"
echo "netplan_written file=$NETPLAN_OUT addr=${CI_ADDR}/${CI_PREFIX:-24} mac=$LIVE_MAC gw=$CI_GW"
# generate only — networkd is not up yet (Before=systemd-networkd)
netplan generate
echo "netplan_generate=ok"

[[ "$CIDATA_MOUNTED" == 1 ]] && umount "$CIDATA_MNT" 2>/dev/null || true

rm -f "$MARKER"
date -Is >"$DONE"
echo "identity initialized; GOLDEN_TEMPLATE removed"
echo "=== done $(date -Is) ==="
