# KB-093F — Junexis Appliance build on Proxmox (replaces nested Packer default)

Status: Active build path  
Date: 2026-08-04  
Audience: Operator building `Junexis-Appliance-vX.Y` field artifacts

## Why this path

Nested Packer/QEMU **inside VM 100** fought for RAM with the MSSP stack and made Subiquity failures hard to see.  
**Default build host is now a disposable Proxmox VM** on `Labhyp` (`192.168.0.191`). Nested Packer remains optional/legacy only.

## Build VM (lab)

| Item | Value |
|------|--------|
| Proxmox host | `labhyp` / `192.168.0.191` (SSH: `~/.ssh/config` Host `proxmox`) |
| VMID | **113** |
| Name | `junexis-appliance-build` |
| IP | **192.168.0.223/24** (gateway `192.168.0.1`) |
| Specs | 2 vCPU, **6 GiB RAM**, 40 GiB disk (`local-zfs`), bridge `vmbr0` |
| Base | Ubuntu 24.04 cloud image already on Proxmox (`ubuntu-24.04-server-cloudimg-amd64.img`) |
| User | `junexis` + build SSH key `junexis-appliance/.tools/build-ssh/junexis_packer` |
| Lifetime | Disposable — destroy after exporting artifacts (or snapshot before export) |

**Lab status (2026-08-05):** VM **113 was destroyed** to free Proxmox RAM/disk after install ISO artifacts were already on VM 100 (`.cache/dist*`). Recreate anytime with `junexis-appliance/scripts/b2_proxmox_create_build_vm.sh` before the next image build. Permanent Appliance Management is **VM 114** (`docs/KB093L_APPLIANCE_MANAGEMENT_PLANE_VM114.md`), not this factory.

This VM is **not** a permanent SOC engine VM. Do not put TheHive or production customer data on it.

## Build topology

| Role | Where |
|------|--------|
| Factory disk / install target | Proxmox **VM 113** `junexis-appliance-build` (`192.168.0.223`) |
| Ansible controller | **VM 112** `automation` (`192.168.0.222`) — runs `b2-smoke.yml` |
| Stack playbooks (Wazuh, etc.) | Same VM 112 tree: `/home/secadmin/mssp-automation/ansible` — refresh with `./scripts/sync_ansible_controller.sh` |
| Orchestration scripts + artifact pull | **VM 100** `mssp-control` (does **not** run nested Packer) |
| Proxmox API/SSH for create/export | `labhyp` (`192.168.0.191`) |

## Operator steps (from VM 100)

```bash
cd /opt/mssp-control

# 1) Create + start build VM on Proxmox (idempotent if 113 already exists)
./junexis-appliance/scripts/b2_proxmox_create_build_vm.sh

# 2) Sync roles to VM 112 and provision the build VM (Ansible on 112)
./junexis-appliance/scripts/b2_proxmox_provision.sh

# 3) Export qcow2/raw/delivery ISO under junexis-appliance/.cache/dist/
./junexis-appliance/scripts/b2_proxmox_export_artifacts.sh
```

Expected success markers:

- Create: `B2_PROXMOX_BUILD_VM_READY`
- Provision: `B2_PROXMOX_PROVISION_OK`
- Export: artifacts `Junexis-Appliance-v*.{qcow2,raw,iso}` + `SHA256SUMS`

## What stays on VM 100

- Source: `junexis-appliance/` (Ansible, CLI, engine, autoinstall reference `packer/http/`)
- Cached Ubuntu **input** ISO (optional; Proxmox already has a copy)
- Build SSH key under `.tools/build-ssh/`
- Published artifacts under `.cache/dist/` after export

## What was retired as default

- `./junexis-appliance/scripts/b2_packer_build.sh` — nested QEMU inside VM 100 (legacy; do not use unless explicitly requested)
- Docker image `junexis-appliance-b2-builder:local` — cleared with ISO-build residuals

## Cleanup (ISO-build residuals only)

Safe to remove anytime:

- `junexis-appliance/.cache/output/`
- `junexis-appliance/.cache/logs/`
- `junexis-appliance/.cache/dist/` (after you copied artifacts elsewhere)
- Docker image `junexis-appliance-b2-builder:local`

Keep:

- `junexis-appliance/` source tree
- `.cache/ubuntu-*.iso` + `SHA256SUMS` (optional)
- `.tools/build-ssh/`

## Relation to field ISO design

KB-093 still defines **one field image** (physical + virtual).  
This Proxmox VM is the **factory** that builds that image; customers never see VM 113.
