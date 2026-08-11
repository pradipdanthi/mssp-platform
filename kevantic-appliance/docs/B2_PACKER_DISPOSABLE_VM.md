# B2 — Packer disposable VM pipeline

Status: Build phase B2 (KB-093).  
Goal: one reproducible path from Ubuntu 24.04 live-server ISO → qcow2 appliance image with minimize + `kevantic-cli`, **without** installing TheHive, and **without** hosting Appliance Management permanently on `mssp-control`.

## Why Docker builder?

This control-plane host has Docker + `/dev/kvm` but no host `qemu`/`packer`/`ansible` packages and no passwordless sudo. B2 therefore builds a **self-contained builder image** (`ci/Dockerfile.b2-builder`) and runs Packer inside it.

Long-term, move image builds and Appliance Management off VM 100 (KB-093 §12).

## Commands

```bash
cd /opt/mssp-control

# 1) Structural + Packer validate + Ansible syntax (default B2 gate)
./scripts/kb093c_validate_kevantic_appliance_b2.sh

# 2) Download Ubuntu ISO (~3GB) into kevantic-appliance/.cache/
./kevantic-appliance/scripts/b2_fetch_ubuntu_iso.sh

# 3) Full disposable QEMU build (20–60+ minutes, needs RAM/KVM)
KEVANTIC_B2_FULL=1 ./scripts/kb093c_validate_kevantic_appliance_b2.sh
# or:
./kevantic-appliance/scripts/b2_packer_build.sh
```

Artifacts land in `kevantic-appliance/.cache/output/`.

## What the guest gets (b2-smoke.yml)

1. Ansible `minimize` (purge snapd/cloud-init/cups/…; refuses hostname `mssp-control`)
2. `firewall_nftables` in **bootstrap** mode (temporary Internet for first patches)
3. `kevantic_runtime` (`kevantic-cli`, state dirs)
4. Assert **no TheHive** package

## Build-only credentials

Autoinstall user `kevantic` uses password `KevanticBuildOnlyChangeMe` (**build/lab only**). Field handoff must rotate or replace with SSH keys / `kevantic-cli setup`.

## Deploy methods (same image)

| Method | Use of B2 artifact |
|--------|--------------------|
| A — Physical / factory | Flash/convert qcow2→disk or burn later ISO post-processor; bootstrap+lock at Kevantic office |
| B — Customer VM | Import qcow2 into ESXi/Proxmox/Hyper-V; bootstrap+lock on site |

ISO post-processor (`Kevantic-Appliance-vX.Y.iso`) is the next packaging step after qcow2 smoke is green.

## Memory note

VM 100 has limited RAM with the Compose stack running. Full Packer builds use ~1.5–2 GB guest memory. Prefer running full builds on a dedicated build host when available.
