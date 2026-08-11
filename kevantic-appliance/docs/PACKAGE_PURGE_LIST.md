# Package purge / retain list (Ubuntu Server LTS)

Status: Design baseline for Ansible role `minimize`. Exact package names validated per Ubuntu LTS point release in CI.

## Purge / remove (aggressive)

| Area | Examples (illustrative) |
|------|-------------------------|
| Snap | `snapd`, snap-seeded apps |
| Cloud | `cloud-init` (after first boot complete), `cloud-guest-utils` if unused |
| Printing | `cups*`, `cups-browsed` |
| Modem / WWAN | `modemmanager`, `ppp` (unless SKU needs) |
| Bluetooth / wireless extras | `bluez*`, unused firmware packs (keep NIC firmware required for server NICs) |
| Multipath | `multipath-tools` (unless SAN SKU) |
| Desktop / notifier | `update-notifier*`, popularity-contest |
| Legacy net | `ifupdown` when netplan/networkd is sole stack |
| Docs / extras | `*-doc` packages not required for runtime |
| Unneeded Python stacks | Remove only packages not required by Kevantic runtime or Wazuh |

## Mask systemd units (examples)

`bluetooth.service`, `cups.service`, `ModemManager.service`, `snapd.service`, `cloud-init*` (post-install), `multipathd.service` — final list maintained in `ansible/roles/minimize/defaults/main.yml`.

## Retain (required)

| Area | Components |
|------|------------|
| Kernel + modules | LTS kernel, hardware NIC drivers in use |
| Init | `systemd` |
| Network | `netplan.io`, `systemd-networkd` or NetworkManager **only if** required by SKU (prefer networkd) |
| Crypto | OpenSSL, `cryptsetup` (LUKS) |
| Audit | `auditd` |
| Container | Podman (preferred) or Docker engine — pick one per SKU |
| Kevantic | `kevantic-cli`, `kevantic-channeld`, service units |
| Security agents local | Wazuh Manager packages for appliance SKU |
| Time / certs | `chrony` or `systemd-timesyncd`, CA certificates |

## Policy

Every purge entry must have a CI test proving the appliance still boots, gets DHCP/static, runs channeld, and registers. If a purge breaks a required dependency, move it to the **exceptions register** under `hardening/cis/`.
