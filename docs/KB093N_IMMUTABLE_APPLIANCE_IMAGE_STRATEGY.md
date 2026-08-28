# KB-093N — Immutable NikTiar Appliance Image Strategy

Status: **Active architecture decision (2026-08-06)**  
Replaces: Subiquity live-ISO remaster (`iso/build_install_iso.sh`) as the **primary** customer ship path.  
Brand: **NikTiar** · Base: **Ubuntu 24.04 LTS** (not rebranded) · Control plane: VM 100 · Appliance Mgmt: **VM 114** · **Image factory: VM 113** (never VM 100 / never VM 114)

---

## 1. Decision

We are **stopping investment** in the mutating “install Ubuntu → firstboot Ansible mutates root” ISO.

We are switching to an **image-based, tamper-resistant appliance**:

| Pillar | Target |
|--------|--------|
| Boot | Unified Kernel Image (UKI) + Secure Boot (NikTiar keys / MOK where needed) |
| Root | **dm-verity** integrity-protected, effectively read-only |
| Secrets / state | Encrypted writable volumes (LUKS2; TPM2/Clevis when hardware allows) |
| Hardening | CIS-aligned + AppArmor enforce + nftables locked + strict sysctl (sealed post-factory) |
| Engines | Baked idle into the golden image (packages and/or rootless Podman); reconcile by license |
| Updates | **A/B dual root** atomic OTA with automatic rollback |
| Trust | Hardware fingerprint now; **remote TPM attestation** to Appliance Mgmt later |

Old `NikTiar-Appliance-Install-v*.iso` remaster artifacts are **retired** (deleted from ship channel). Keep reusable content: `cli/`, `channel/`, `licensing/`, `engines/`, offline package fetch, nftables/AppArmor sources — consumed by the **new** image build, not by Subiquity firstboot.

---

## 2. Why (development-stage reset)

The remaster path blocked true immutability: firstboot **writes** the rootfs (apt, engines, harden). That conflicts with dm-verity and A/B. We still have room to change strategy; rebuilding now is cheaper than shipping the old model to customers.

---

## 3. Toolchain (locked)

| Layer | Choice | Role |
|-------|--------|------|
| Image build | **mkosi** (systemd) | Produce golden root + ESP/UKI candidates from declarative config |
| Partitioning | **systemd-repart** | Disk layout: ESP + A + B + encrypted data |
| Boot | **ukify** / systemd-stub | UKI: kernel + initrd + cmdline + optional PCR sigs |
| Secure Boot | **sbctl** (lab) → OEM/MOK runbook (field) | Sign UKI; enroll NikTiar DB keys |
| Verity | **systemd-veritysetup** / mkosi verity | Merkle-backed root |
| Encryption | **cryptsetup LUKS2** + **Clevis/TPM2** (SKU-dependent) | `/var` (logs, lake, secrets) |
| OTA | **RAUC** (preferred) or systemd-sysupdate | Slot A/B switch + rollback |
| Config overlays | Thin Ansible/scripts on **writable** `/var` / `/etc` overlay only | No apt on sealed root |
| Channel / license | Existing `channeld` + license enforcer | Unchanged product semantics |

**Not primary:** Cubic, live-build remaster, Subiquity autoinstall for customer media.

---

## 4. Disk layout (target)

```text
┌──────── ESP (FAT) ────────┐  UKI A / UKI B (Secure Boot)
├──────── Root slot A ──────┤  dm-verity protected (active or inactive)
├──────── Root slot B ──────┤  dm-verity protected (inactive or active)
├──────── Data (LUKS2) ─────┤  /var/lib/niktiar, logs, lake, secrets
└──────── (optional swap) ──┘
```

Factory / first power-on: repart grows data partition; generates machine identity; **does not** apt-install the world.

---

## 5. Build & ship artifacts

| Artifact | Consumer |
|----------|----------|
| `NikTiar-Appliance-Immutable-vX.Y.raw` / `.qcow2` | Lab / cloud / imaging |
| `NikTiar-Appliance-Immutable-vX.Y.raucb` (or sysupdate bundle) | Field OTA |
| Optional hybrid **installer USB** that only **dd/reparts** the golden image | Bare metal (not Subiquity) |

Version string continues from `niktiar-appliance/VERSION`.

---

## 6. Phased delivery (no waiting on “perfect”)

### Phase N0 — Scaffold (this KB) ✅ in progress
- Repo layout `niktiar-appliance/mkosi/`
- Deprecate remaster scripts
- Delete retired `dist-install` ship ISOs from `.cache`
- **Dedicated factory VM 113** (`niktiar-appliance-build`, `192.168.0.223`) for all mkosi builds — **not** VM 100, **not** VM 114

### Phase N1 — Golden image boots in lab (first working rebuild)
- On **VM 113**: mkosi builds Ubuntu 24.04 root with NikTiar user, nftables bootstrap, CLI + channel stubs
- Engines: stage from existing `iso/offline-packages` **into the image at build time** (idle units)
- Output: qcow2 bootable on Proxmox **without** Subiquity
- Validator: `scripts/kb093n_validate_immutable_image_scaffold.sh`

### Phase N2 — Verity + writable data
- dm-verity root; `/var` on separate partition
- Factory firstboot = identity + register only (no apt)

### Phase N3 — UKI + Secure Boot lab
- ukify; sbctl keys in `.tools/sbkeys/` (never commit private keys)
- Proxmox/OVMF enroll for lab

### Phase N4 — LUKS2 + TPM2 Clevis (SKU matrix)
- Required on physical SKU; optional/emulated on lab VM

### Phase N5 — RAUC A/B + channel OTA
- Signed bundles; rollback on failed boot

### Phase N6 — Remote attestation
- Quote → Appliance Mgmt (VM 114); policy gate on heartbeat

Track 5 field cutover **pauses** until **N1** lab boot works; then resume register against VM 114 on the new image.

---

## 7. What we keep from the old tree

| Keep | Use in new world |
|------|------------------|
| `cli/junexis-cli` | Baked into image |
| `channel/`, `ota/` | Baked; OTA upgraded to RAUC later |
| `licensing/` | Same JWS model |
| `engines/`, offline package fetch | **Build-time** install into golden root |
| `hardening/nftables`, `hardening/apparmor`, CIS sysctl lists | Applied at **image build**, not mutating firstboot |
| Appliance Mgmt VM 114 + register API | Unchanged |

| Retire | Replacement |
|--------|-------------|
| `iso/build_install_iso.sh` remaster as ship path | `mkosi/build.sh` |
| `iso/firstboot/junexis-firstboot.sh` full Ansible mutate | Factory agent (identity/register only) |
| `.cache/dist-install/NikTiar-Appliance-Install-*.iso` | Immutable raw/qcow2 + later installer USB |

---

## 8. Security posture vs Gemini checklist

| Checklist item | Phase |
|----------------|-------|
| Custom UEFI / MOK / UKI | N3 |
| TPM measured boot / PCR-bound LUKS | N4 (physical SKU) |
| dm-verity RO root | N2 |
| Overlay/tmpfs + encrypted data | N2–N4 |
| CIS/OpenSCAP full suite | Not required; keep explicit harden set + exceptions |
| Password SSH off / console lock | After register + `network lock` (N1+) |
| Rootless engines | Incremental; start with idle debs in image, migrate hot path to Podman where justified |
| A/B OTA | N5 |
| Remote attestation | N6 |

---

## 9. Operator commands (N1+)

```bash
cd /opt/mssp-control
./scripts/kb093n_validate_immutable_image_scaffold.sh
./niktiar-appliance/mkosi/build.sh
# → niktiar-appliance/.cache/mkosi/NikTiar-Appliance-Immutable-*.qcow2
```

Proxmox: import qcow2 as VM disk; boot; login `junexis`; run Admin **Copy register command** to VM 114.

---

## 10. Validation

```bash
./scripts/kb093n_validate_immutable_image_scaffold.sh
```

Later phases add Secure Boot, verity, RAUC validators.

---

## 12. Dedicated factory VM (do not use VM 100 or VM 114)

| VMID | Name | IP | Role |
|------|------|-----|------|
| **113** | `niktiar-appliance-build` | `192.168.0.223` | **mkosi / UKI / image factory only** |
| **114** | `niktiar-appliance-mgmt` | `192.168.0.224` | Register / heartbeat / channel gateway (keep) |
| 100 | `mssp-control` | `192.168.0.201` | Admin/Customer portals + Postgres (keep) |

Recreate factory: `./niktiar-appliance/scripts/b2_proxmox_create_build_vm.sh`

## 13. Idle engines on a tamper-proof image (compatibility)

**Yes — baking all catalogue engines into the golden image in idle/stopped state is compatible with the immutable strategy**, and is the intended MSSP SKU model (one image, entitle later).

| Concern | Reality |
|---------|---------|
| Conflicts with dm-verity / UKI? | **No**, if engines are installed **at image build time** and left **disabled**. Root stays sealed; no firstboot `apt`. |
| Conflicts with A/B OTA? | **No** — engine version bumps ship as a **new signed image/bundle**, not live apt on the box. |
| Disk size | Golden image grows (multi‑GB). Plan ~32–64+ GiB root slots. |
| RAM at idle | Stopped units ≈ little RAM. Must ensure **no timers/sockets auto-start** until license. |
| Attack surface | Binaries exist on disk even idle — mitigate with AppArmor, no listeners, locked nftables, license gate before enable. |
| `modules_disabled=1` later | Apply only after sealed factory; engines that need kernel modules must be accounted for before sealing. |
| Rootless Podman later | Optional migration; idle `.deb` services are fine for N1–N5. |

**Rule:** idle = installed + **masked/disabled** + reconciler enables only entitled services. Never “half-running.”
