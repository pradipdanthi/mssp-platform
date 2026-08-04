# Junexis Hardened On-Prem Appliance — Build Repository

**Brand:** Junexis (MSSP platform, cloud SOC, licensing, `junexis-cli`)  
**Base OS:** Ubuntu Server LTS (not rebranded)  
**Customer media:** bootable **install ISO** `Junexis-Appliance-Install-vX.Y.iso` (bare metal / hypervisor / cloud VM)  
**Control plane home:** `/opt/mssp-control` (KB-016 registration/heartbeat; KB-093G licensing)

This tree is the **appliance software lifecycle** repo: install-ISO remaster, OS minimization, hardening, modular 10-service packaging (idle until Junexis license), outbound channel agent, OTA staging, and local CLI.

### Build the install ISO (customer media)

```bash
cd /opt/mssp-control
./junexis-appliance/scripts/b2_fetch_ubuntu_iso.sh   # once
./junexis-appliance/iso/build_install_iso.sh
# → junexis-appliance/.cache/dist-install/Junexis-Appliance-Install-v*.iso
./scripts/kb093g_validate_appliance_install_iso.sh
```

Plan: `/opt/mssp-control/docs/KB093G_APPLIANCE_ISO_ENTITLEMENT_PLAN.md`  
Default install user `junexis` / password `ChangeMeNow!` — rotate after setup.

## What this is

- Hardened local **collector / parser / sensor** at the customer site (or customer/Junexis VPC)
- **One ISO** for physical hardware and virtual appliances; on-prem or cloud-endpoint contracts
- Keeps sensitive log payloads on-prem per customer preference
- Sends **structured metadata + high-fidelity critical alerts** only to Junexis Cloud SOC
- **Bootstrap then lock:** temporary Internet for first critical OS/engine patches; then LAN + SOC channel only
- **No TheHive / ticketing** on the box — cases stay in Cloud SOC

## Edge engine (KB-093E)

Local DuckDB/Parquet lake, anonymizing telemetry, retrospective hunt:

- Code: `junexis-appliance/appliance/`
- Doc: `/opt/mssp-control/docs/KB093E_APPLIANCE_ENGINE_DATALAKE_TELEMETRY_HUNT.md`
- Validate: `./scripts/kb093e_validate_appliance_engine.sh`

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
| `cli/junexis-cli/` | Local management wrapper (spec → implementation) |
| `docs/` | Appliance-local design notes (canonical KB is under control-plane `docs/`) |
| `tests/` + `ci/` | Build, integration, security regression |

## Canonical design docs (control plane)

| Doc | Topic |
|-----|--------|
| `/opt/mssp-control/docs/KB093_JUNEXIS_HARDENED_ON_PREM_APPLIANCE_ARCHITECTURE.md` | Architecture (channel, OTA, licensing, 10 services) |
| `/opt/mssp-control/junexis-appliance/docs/JUNEXIS_CLI_SPEC.md` | `junexis-cli` specification |
| `/opt/mssp-control/junexis-appliance/docs/REPO_LAYOUT.md` | Folder hierarchy detail |

## Build phases (high level)

1. **Packer + autoinstall** — Ubuntu Server LTS minimal target + LUKS/Secure Boot hooks  
2. **Ansible minimize** — purge snapd/cloud-init/bluetooth/cups/etc.; mask unused units  
3. **Ansible harden** — CIS L2, nftables default-deny inbound, AppArmor, auditd  
4. **Runtime** — container engine + `junexis-channeld` + `junexis-cli` + core service 01  
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
