# Kevantic Hardened On-Prem Appliance — Build Repository

**Brand:** Kevantic (MSSP platform, cloud SOC, licensing, `kevantic-cli`)  
**Base OS:** Ubuntu Server LTS (not rebranded)  
**Customer media (active):** **immutable disk image** via **mkosi** (KB-093N) — UKI / dm-verity / A/B roadmap  
**Retired:** Subiquity remaster install ISO (`iso/build_install_iso.sh`) — do not ship  
**Control plane home:** `/opt/mssp-control` (KB-016 registration/heartbeat; Appliance Mgmt VM 114)

### Build the immutable appliance image (primary)

```bash
cd /opt/mssp-control
# optional: refresh offline engine .debs used at *image build* time
./kevantic-appliance/scripts/b2_fetch_offline_packages.sh
sudo apt-get install -y mkosi systemd-container uidmap qemu-utils   # once
./scripts/kb093n_validate_immutable_image_scaffold.sh
./kevantic-appliance/mkosi/build.sh
# → kevantic-appliance/.cache/mkosi/Kevantic-Appliance-Immutable-v*.qcow2
```

Strategy: `/opt/mssp-control/docs/KB093N_IMMUTABLE_APPLIANCE_IMAGE_STRATEGY.md`  
Default user `kevantic` / password `ChangeMeNow!` — rotate after register.

## What this is

- Hardened local **collector / parser / sensor** at the customer site (or customer/Kevantic VPC)
- **One ISO** for physical hardware and virtual appliances; on-prem or cloud-endpoint contracts
- Keeps sensitive log payloads on-prem per customer preference
- Sends **structured metadata + high-fidelity critical alerts** only to Kevantic Cloud SOC
- **Critical-alert forwarder (KB-093P):** tails local Manager `alerts.json`, forwards level ≥ 10 only
- **Bootstrap then lock:** temporary Internet for first critical OS/engine patches; then LAN + SOC channel only
- **No TheHive / ticketing** on the box — cases stay in Cloud SOC

## Edge engine (KB-093E)

Local DuckDB/Parquet lake, anonymizing telemetry, retrospective hunt:

- Code: `kevantic-appliance/appliance/`
- Doc: `/opt/mssp-control/docs/KB093E_APPLIANCE_ENGINE_DATALAKE_TELEMETRY_HUNT.md`
- Validate: `./scripts/kb093e_validate_appliance_engine.sh`

## Critical-alert forward (KB-093P)

Local Manager → anonymize → `POST /api/v1/telemetry/ingest`:

- Doc: `/opt/mssp-control/docs/KB093P_APPLIANCE_CRITICAL_ALERT_FORWARD.md`
- Install on a live box: `sudo ./kevantic-appliance/scripts/install_critical_alert_forwarder.sh`
- Validate: `./scripts/kb093p_validate_appliance_critical_alert_forward.sh`

## What this is not

- Not a second customer-facing product UI (portals stay on the control plane)
- Not a rebranded Linux distro
- Not a second endpoint agent (endpoints use **Wazuh Agent only**)
- Not an on-prem TheHive / case-management appliance
- Not permanently open to the public Internet after first-time bootstrap

## Quick map

| Path | Purpose |
|------|---------|
| `iso/` | **Bootable install ISO** remaster (autoinstall + firstboot + payload) |
| `packer/` | Legacy/CI nested Packer path (not customer media) |
| `ansible/` | Debloat, CIS L2 hardening, runtime, idle engines, license enforcer |
| `hardening/` | CIS baselines, AppArmor, nftables, auditd assets |
| `services/01–10/` | Modular microservice definitions (systemd/quadlet) |
| `channel/` | Outbound mTLS WebSocket/NATS protocol schemas |
| `licensing/` | Signed activation / entitlement payload formats |
| `ota/` | Local update + WPK staging manifests |
| `cli/kevantic-cli/` | Local management wrapper (spec → implementation) |
| `docs/` | Appliance-local design notes (canonical KB is under control-plane `docs/`) |
| `tests/` + `ci/` | Build, integration, security regression |

## Canonical design docs (control plane)

| Doc | Topic |
|-----|--------|
| `/opt/mssp-control/docs/KB093_KEVANTIC_HARDENED_ON_PREM_APPLIANCE_ARCHITECTURE.md` | Architecture (channel, OTA, licensing, 10 services) |
| `/opt/mssp-control/kevantic-appliance/docs/KEVANTIC_CLI_SPEC.md` | `kevantic-cli` specification |
| `/opt/mssp-control/kevantic-appliance/docs/REPO_LAYOUT.md` | Folder hierarchy detail |

## Build phases (high level)

1. **Packer + autoinstall** — Ubuntu Server LTS minimal target + LUKS/Secure Boot hooks  
2. **Ansible minimize** — purge snapd/cloud-init/bluetooth/cups/etc.; mask unused units  
3. **Ansible harden** — CIS L2, nftables default-deny inbound, AppArmor, auditd  
4. **Runtime** — container engine + `kevantic-channeld` + `kevantic-cli` + core service 01  
5. **CI** — ephemeral VM boot of ISO → register → heartbeat → entitlement enable → offboard wipe dry-run  
6. **Promote** — signed OTA packages + regenerate official ISO

## Safety rules

- Never commit activation tokens, API keys, client certs, or CA private keys
- Never put secrets under `licensing/keys/` in Git (placeholders only)
- Customer-safe sync only — no raw logs/PCAP/credentials to cloud or customer portal
- Do not open inbound listener ports for cloud control; cloud talks down the outbound channel

## Related control-plane KBs

- KB-016 — `POST /appliance/register`, `POST /appliance/heartbeat`
- KB-058 — on-prem template download (Compose placeholder)
- KB-073 — tenant deployment modes including `on_prem_appliance` / `hybrid`
- KB-036 — platform roadmap (on-prem metadata sync model)
