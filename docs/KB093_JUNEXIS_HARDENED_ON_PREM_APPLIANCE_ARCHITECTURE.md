# KB-093 — Junexis Hardened On-Prem Appliance Architecture

Status: **Architecture / design** (scaffold under `junexis-appliance/`).  
Module type: Documentation + repository layout — **no control-plane runtime changes** in this KB.  
Brand: **Junexis** (platform, CLI, licensing, cloud SOC). Base OS remains **Ubuntu Server LTS** (not rebranded).

Related: KB-016 (register/heartbeat), KB-036 (on-prem metadata sync), KB-037 (appliance registry), KB-058 (Compose template), KB-073 (deployment modes), KB-076 (service upgrade requests / entitlements direction).

---

## 1. Purpose

Define the architecture for the **Junexis Hardened On-Prem Appliance**: a turnkey, aggressively minimized Ubuntu Server image that:

1. Collects and processes customer telemetry **locally**
2. Retains sensitive log payloads on-prem per customer preference
3. Forwards **only structured metadata and critical high-fidelity alerts** to Junexis Cloud SOC
4. Uses **one ISO** for physical or virtual deploy (on-prem or cloud-endpoint contracts)
5. Allows a **one-time bootstrap Internet** window for critical OS/engine patches, then **locks** to LAN + SOC channel only
6. Never hosts **TheHive** or other on-prem ticketing — casework stays centralized in Cloud SOC
7. Supports **dynamic licensing** of ten modular services and staged Wazuh Agent updates

This KB is the design contract for ISO builds, the outbound control channel, OTA/WPK staging, and `junexis-cli`.

---

## 2. Product boundaries

| Layer | Owns |
|-------|------|
| Junexis Admin / Customer portals (VM 100 control plane) | Human UX, entitlements commerce, activation tokens, **centralized casework / ticketing UI** |
| Junexis Cloud SOC (`soc.junexis.com`) | Central triage, **TheHive / case platform**, mTLS CA, signed license issuance, OTA repository |
| **This appliance** | Local sensors, parsers, staging, Wazuh Manager (customer-site), channel agent, wipe |
| Customer endpoints | **Only** native `wazuh-agent` — no second Junexis endpoint agent |

Deployment modes that use this appliance (KB-073): `on_prem_appliance`, `cloud_appliance`, `hybrid`.

### 2.1 Explicitly NOT on the appliance

| Component | Why excluded |
|-----------|----------------|
| **TheHive** (or any on-prem ticketing/case UI) | Casework is **centralized** in Junexis Cloud SOC only |
| Shuffle / SOAR console | Orchestration UI and playbook hosting stay in cloud; appliance may run **signed local remediation jobs** only |
| Admin / Customer portals | Cloud / control plane only |
| Second endpoint agent | Endpoints use `wazuh-agent` only |

`svc-02` on the appliance is an **IR execution worker** (run signed containment/remediation jobs locally). It is **not** a local TheHive, not a ticket inbox, and not a case dashboard.

### 2.2 One ISO, all contract paths

A **single** artifact — `Junexis-Appliance-vX.Y.iso` — covers every appliance contract:

| Customer choice | How the same ISO is used |
|-----------------|--------------------------|
| On-prem endpoints + appliance | Deploy ISO on customer LAN (physical or VM); agents register to local Manager |
| Cloud endpoints (AWS / Azure / GCP) + appliance (`cloud_appliance`) | Same ISO as VM (customer or Junexis-managed VPC) or physical edge; agents point at appliance reachability path |
| Hybrid | Same ISO; entitlements and network placement differ, image does not |

There is **no** separate “cloud ISO” vs “on-prem ISO.” Placement and KB-073 deployment mode are configuration/token metadata, not different media.

### 2.3 Two field deployment methods (same ISO)

| Method | Where first install happens | Typical flow |
|--------|----------------------------|--------------|
| **A — Physical / factory pre-stage** | Junexis office builds or images the box **before** shipping to customer | Engineer runs install + **first-time bootstrap updates** on Junexis network → ship → at customer site: LAN + SOC channel (bootstrap already done unless re-run is required) |
| **B — Customer virtual infrastructure** | Customer has ESXi / Proxmox / Hyper-V / KVM capacity | Engineer deploys **same ISO** as a VM on-site → runs **first-time bootstrap updates** with temporary internet → then locks network |

Both methods must complete the same bootstrap → lock sequence before production handoff (§3.1, §4.5).

---

## 3. High-level architecture

```text
┌──────────────── Customer / edge site (or VPC) ─────────────────┐
│  Endpoints (on-prem and/or cloud): wazuh-agent only            │
│       │ alerts to local Manager (LAN / private path)           │
│       ▼                                                        │
│  ┌──────── Junexis Appliance (ONE ISO → bare metal OR VM) ───┐ │
│  │  NO TheHive / NO case UI                                  │ │
│  │  svc-01 Log/Event   svc-06 NDR …  + ir-worker (jobs only) │ │
│  │  Local Wazuh Manager + Fluent Bit + OTA/WPK cache         │ │
│  │  junexis-channeld  +  junexis-cli  +  license enforcer     │ │
│  │  Network: BOOTSTRAP (temp internet) → LOCKED (SOC-only)   │ │
│  └───────────────────────────┬───────────────────────────────┘ │
└──────────────────────────────┼─────────────────────────────────┘
                               │ AFTER LOCK: SOC channel only
                               │ (metadata + critical alerts)
                               ▼
                    ┌── Junexis Cloud SOC ──┐
                    │  soc.junexis.com:443  │
                    │  TheHive / ticketing  │
                    │  PKI / licensing/OTA  │
                    └──────────────────────┘
```

**Inbound from Internet:** never required for day-to-day ops. LAN listeners (Wazuh agent, syslog, SPAN) stay on **customer/private networks only**.

### 3.1 Network lifecycle: bootstrap then lock

The appliance has **two** network postures. Engineers must finish posture **BOOTSTRAP** successfully, then switch to **LOCKED** before leaving the site (or before shipping a pre-staged physical unit into production).

| Posture | When | Allowed traffic |
|---------|------|-----------------|
| **BOOTSTRAP** | First install / first critical patch cycle (office or customer site) | Temporary **outbound Internet** for: Ubuntu LTS **critical security** updates; Junexis-approved **backend engine** critical updates (Wazuh Manager, Suricata/Zeek packages or images, Fluent Bit, container runtime, etc.); DNS/NTP as needed; registration to SOC |
| **LOCKED** (steady state) | After bootstrap reports success and `junexis-cli network lock` (or equivalent) | **No general Internet** inbound or outbound. Allowed: (1) **internal/private** receive of endpoint (and permitted collector) alerts on LAN/VPC; (2) **outbound secure channel** to Junexis MSSP SOC for metadata + selected critical high-fidelity alerts (+ control/OTA over that same channel). Everything else denied |

**After lock, further OS/engine patches** do **not** use open Internet `apt` by default — they arrive as **signed OTA** over the SOC channel (or a controlled break-glass re-open of BOOTSTRAP with dual confirmation + audit).

CLI markers (see CLI spec): `junexis-cli bootstrap update` → `junexis-cli network lock` → `status` shows `network_mode: locked`.

---

## 4. Communication: outbound mTLS reverse channel

### 4.1 Goals

- Persistent, authenticated control + data plane without inbound NAT/firewall holes
- Hardware-bound client identity
- Signed control messages (feature enable, OTA, remediation jobs)
- Compatible evolution from today’s KB-016 API-key heartbeat

### 4.2 Protocol phasing

| Phase | Transport | Auth | Notes |
|-------|-----------|------|-------|
| **A — Bridge (now → first ISO)** | HTTPS to control plane | Activation token → durable API key (`X-Appliance-ID` / `X-Appliance-API-Key`) | Reuses KB-016 `POST /appliance/register` + `POST /appliance/heartbeat` |
| **B — Channel v1 (target)** | `wss://soc.junexis.com/appliance/v1/channel` | Mutual TLS client cert + appliance UUID | Bidirectional frames; heartbeat becomes channel ping + status publish |
| **C — Channel v2 (optional)** | NATS leafnode over mTLS to same :443 (or dedicated host) | Same client cert | Higher fan-in; same message schemas |

Phase A remains supported as **fallback** if WebSocket is blocked (rare); prefer B.

### 4.3 Certificate lifecycle

1. Field engineer burns ISO, runs `junexis-cli setup --token …`
2. Appliance computes **hardware fingerprint** (TPM EK public hash preferred; else product UUID + disk + NIC MACs, hashed with HMAC device salt)
3. Registration request includes fingerprint + token (Phase A) or CSR (Phase B)
4. Junexis CA issues **client certificate** bound to appliance UUID + fingerprint claims (SAN/URI)
5. Private key stored in TPM (preferred) or file under `/var/lib/junexis/secrets/` (0600, AppArmor confined)
6. Renewal: channel command `cert.renew` before `notAfter`; revoke on offboard

### 4.4 Frame model (channel v1)

All frames are JSON (or protobuf later) with envelope:

| Field | Meaning |
|-------|---------|
| `v` | Protocol version (`1`) |
| `type` | `heartbeat` \| `status` \| `alert.meta` \| `control` \| `ack` \| `ota.offer` \| `license.push` \| `job` |
| `id` | UUID for ack correlation |
| `ts` | RFC3339 UTC |
| `tenant_id` | Bound server-side; appliance must not spoof other tenants |
| `payload` | Type-specific object |
| `sig` | Optional detached signature for `control` / `license` / `ota` (Ed25519) |

**Control payload examples:** `service.enable`, `service.disable`, `ota.stage`, `wpk.stage`, `agent.reconfigure`, `remediate.run`, `offboard`.

**Data payload rules (customer safety):**

- Allowed: normalized alert summary, severity, rule id, asset hostname (if policy allows), incident reference, health metrics, entitlement state
- Forbidden on wire to cloud: raw log bodies, PCAP, credentials, unrestricted IP dumps unless a future explicit policy flag per tenant (default off)

Schemas live in `junexis-appliance/channel/schemas/`.

### 4.5 Firewall posture on appliance

nftables (see `hardening/nftables/`) switches with **network mode**:

**BOOTSTRAP (temporary — first-time critical updates only)**

- **INPUT:** default drop; established/related; optional SSH from **mgmt LAN** only (engineer)
- **OUTPUT:** allow DNS, NTP, HTTPS to Ubuntu security mirrors / Junexis-approved package & image endpoints / `soc.junexis.com`; optional customer HTTP(S) proxy
- Purpose: install Ubuntu critical security patches + backend engine critical patches **once**, then leave this mode

**LOCKED (production steady state — mandatory before handoff)**

- **INPUT:** default drop; established/related; **customer/private LAN (or VPC) only** for Wazuh agent / syslog / collectors / SPAN as configured — **no Internet-facing listeners**
- **OUTPUT:** **deny general Internet**; allow **only** the Junexis SOC secure channel (`soc.junexis.com:443` mTLS / WSS) for metadata, selected critical alerts, heartbeat/control/OTA; DNS/NTP only if required to reach that channel (prefer pinning / local chrony already synced)
- No cloud-initiated inbound TCP into the customer perimeter
- Re-opening BOOTSTRAP requires `junexis-cli network unlock --yes` (audited break-glass), never silent

State file: `/var/lib/junexis/network_mode` ∈ `bootstrap` \| `locked`.

---

## 5. Onboarding & offboarding

### 5.1 Onboarding (single ISO, either deployment method)

1. Contract signed with appliance option (`on_prem_appliance`, `cloud_appliance`, or `hybrid` per KB-073) — Admin issues activation token
2. Engineer uses **the same** `Junexis-Appliance-vX.Y.iso`:
   - **Method A:** image physical hardware at Junexis office, **or**
   - **Method B:** create VM on customer hypervisor / cloud VPC from the same ISO
3. Autoinstall + first boot → `junexis-cli setup` (token, name, network)
4. **`junexis-cli bootstrap update`** — temporary Internet: Ubuntu critical security + approved backend engine critical updates; verify success
5. **`junexis-cli network lock`** — steady-state: LAN/VPC agents in; SOC channel out only
6. Channel up → core `svc-01` (+ entitled modules); Admin sees appliance online
7. Hand off only when `status` shows `network_mode: locked` and bootstrap last-run `success`

Pre-staged physical units may complete steps 4–5 at the Junexis office so customer-site work is mainly LAN integration + SOC channel verify. If the unit sat long enough that new critical patches shipped, engineer re-runs bootstrap **before** lock (or unlock → update → lock).

### 5.2 Offboarding & cryptographic decommission

Triggered from Admin portal **or** `junexis-cli offboard` / `wipe`:

1. Control plane revokes client cert at Junexis CA; marks appliance `retired` (KB-016 heartbeat already returns 403 for retired)
2. Appliance stops services; deletes key material; shreds secret volumes
3. Purges `/var/lib/junexis` data pools and local logs per retention policy
4. Optional console lock; machine requires re-image to return to service

---

## 6. Dynamic licensing & feature enablement

### 6.1 Model

Services **01–10** are modular (systemd units and/or rootless containers).  
Subscription changes in Junexis Portal → signed **entitlement payload** → appliance.

**Online path:**

1. Portal/billing updates tenant entitlements
2. Cloud signs payload; pushes `license.push` on channel
3. `license_enforcer` verifies signature + binding + expiry
4. `service_manager` pulls images/modules over mTLS if needed and starts units
5. If endpoint modules needed, stage `agent.conf` / WPK via local Wazuh Manager

**Offline path:**

```bash
junexis-cli enable-service --key <SIGNED_BLOB>
```

Same verifier; no channel required.

### 6.2 Enforcer responsibilities (script/daemon)

Implemented as `junexis-license-enforcer` (Ansible role `license_enforcer`):

- Maintain trust store of Junexis verify keys
- Atomic write of `entitlements.json`
- Reconcile desired vs running services every N seconds and on signal
- Refuse to start non-entitled modules
- Emit auditd-friendly logs (no secrets)

### 6.3 Mapping to control-plane entitlements

Align service IDs with commercial catalog / KB-071–076 entitlement concepts. Customer upgrade requests (KB-076) remain a **portal workflow**; fulfillment ends in a signed entitlement to this appliance.

---

## 7. Local update staging (OTA) & Wazuh WPK

### 7.1 Appliance OTA (post-lock path)

After **LOCKED** mode, updates prefer the SOC channel — not open Internet mirrors:

```text
Cloud OTA repo (signed manifests)
    --channel--> appliance ota_staging
    --> verify signature + hash
    --> stage under /var/lib/junexis/ota/
    --> apply in maintenance window (no silent reboot of collectors)
    --> report result on channel
```

Manifest fields: version, component list, sha256, signature, min/max from-version, disruptiveness flag.

**First-time** critical OS/engine patching is **BOOTSTRAP** (§3.1), not OTA. OTA covers ongoing life after lock.

### 7.2 Endpoint agent updates (WPK)

When customer chose on-prem appliance path:

1. Appliance pulls verified Wazuh Agent WPK from Junexis cloud repo over channel/mTLS
2. Stages under `/var/lib/junexis/wpk/`
3. Local Wazuh Manager `agent_upgrade` deploys to endpoints
4. Enabling agent-dependent services (automation AR, SCA, FIM, syscollector flags) pushes **config** via shared `agent.conf` groups — **not** a second agent binary

### 7.3 Upstream tracking

CI watches Ubuntu LTS security + Wazuh releases → rebuild minimal image → integration tests → promote OTA + regenerate ISO (see §10).

---

## 8. Endpoint vs appliance capabilities

| Capability | Where it runs | Endpoint agent impact |
|------------|---------------|------------------------|
| Log & Event Monitoring | Appliance Manager + collectors | Agent ships events to **local** Manager |
| IR **ticketing / TheHive / case UI** | **Cloud SOC only — never on appliance** | — |
| IR local remediation | Appliance `ir-worker` only | Optional Active Response when job requires |
| Automation / containment | Appliance orchestrates | Wazuh **Active Response** via existing agent |
| VMaaS | Appliance scanner + inventory | `syscollector` module flags |
| CaaS | Appliance SCA aggregator | SCA module |
| NDR | Appliance only (SPAN/TAP) | None |
| Threat intel cache | Appliance | None (enrich before forward) |
| Forensics / deception | Appliance listener; cases in **cloud** | FIM / SCA / custom rules via agent.conf |
| EASM internal probes | Appliance on request | None |
| ITDR | Appliance connectors (AD/LDAP/API) | None |

**Hard rules:** only one endpoint agent — **`wazuh-agent`**. **No TheHive** (or other case/ticketing stack) on the appliance.

---

## 9. Ten-service local component map

| ID | Service | Local components (appliance) |
|----|---------|------------------------------|
| svc-01 | Log & Event Monitoring (Core) | Wazuh Manager, Fluent Bit, syslog/webhook collectors; metadata forwarder |
| svc-02 | Incident Response (local worker only) | `ir-worker` — executes signed remediation jobs from cloud; **no TheHive, no case UI, no ticket store** |
| svc-03 | Security Automation & Containment | Orchestration worker → Active Response / firewall API hooks |
| svc-04 | Vulnerability Management (VMaaS) | Agentless scanner engine (align Nuclei/Vuls pattern; not on control plane) + syscollector aggregate |
| svc-05 | Continuous Compliance (CaaS) | SCA result parser / benchmark evaluator |
| svc-06 | NDR | Suricata + Zeek (Junexis-wrapped), SPAN/TAP capture |
| svc-07 | Threat Intelligence | Local IOC cache (MISP-lite or redis/sqlite feed store) |
| svc-08 | Endpoint Forensics & Deception | Artifact collection listener; FIM/deception rule packs to agents |
| svc-09 | EASM | On-demand internal perimeter probe runner |
| svc-10 | Cloud & Identity (ITDR) | AD/LDAP collectors + cloud IdP API connectors |

Module definitions: `junexis-appliance/services/NN-*/`.

---

## 10. ISO / OS minimization & hardening pipeline

### 10.1 Build chain

1. **Packer** builders (QEMU for CI; Proxmox/ESXi/Hyper-V as needed) consume Ubuntu Server LTS ISO  
2. **Subiquity autoinstall** (`packer/http/user-data`) — minimal target, LUKS FDE, Secure Boot-capable layout  
3. **Ansible `minimize`** — purge snapd, cloud-init (post-install), multipath, bluetooth, wireless extras, cups, modemmanager, update-notifier, unused Python, legacy net services  
4. **Mask** systemd units not required for Junexis runtime or OS stability  
5. **Retain:** kernel, systemd, netplan/networkd, container runtime, OpenSSL, auditd, needed NIC drivers  
6. **harden_cis** — CIS Level 2 Server with documented exceptions register  
7. **nftables + AppArmor + auditd**  
8. Install `junexis-cli`, `junexis-channeld`, core svc-01  
9. Shrink → produce `Junexis-Appliance-vX.Y.iso`

### 10.2 Patching

| Phase | Mechanism |
|-------|-----------|
| **First-time (BOOTSTRAP)** | Temporary Internet: Ubuntu critical security + approved backend engine critical packages/images; then **network lock** |
| **Ongoing (LOCKED)** | Signed OTA over SOC channel; no auto-reboot of collector-critical services; reboot via maintenance window or CLI |
| **Break-glass** | Audited `network unlock` → limited bootstrap update → `network lock` again |

ISO build still ships a reasonably current baseline so bootstrap time/volume stays small — but engineers **must** always run bootstrap once per deployment path before production lock.

---

## 11. Repository layout

Canonical tree: `/opt/mssp-control/junexis-appliance/` — see `junexis-appliance/docs/REPO_LAYOUT.md`.

CLI contract: `junexis-appliance/docs/JUNEXIS_CLI_SPEC.md`.

KB-058 `templates/on-prem-appliance/` remains the interim Admin-downloadable Compose stub until ISO GA.

---

## 12. Control-plane integration & production topology

### 12.1 Near-term (lab / current path)

Appliance registration/heartbeat may temporarily use APIs on **VM 100 `mssp-control`** (KB-016). Admin Appliances UI stays on the control plane for tenant UX.

### 12.2 Production target (mandatory split)

**Appliance Management must move off the `mssp-control` server onto a dedicated Appliance Management plane** before/at production scale. Do not permanently couple channel gateway, appliance CA, OTA/WPK repository, or high-volume appliance ingress to the control-plane host.

| Plane | Host role (production) | Responsibilities |
|-------|------------------------|------------------|
| **MSSP Control Plane** | `mssp-control` (VM 100 today) | Admin/Customer portals, PostgreSQL system of record, RBAC, entitlements UX, normalized records, case UX pointers |
| **Appliance Management Plane** | **VM 114** `junexis-appliance-mgmt` (`192.168.0.224`) — live; see `docs/KB093L_APPLIANCE_MANAGEMENT_PLANE_VM114.md` | `soc.junexis.com` edge for appliances: mTLS channel gateway, appliance CA issue/revoke, OTA + WPK repo, registration/bootstrap update allow-lists, appliance health fan-in |
| **Cloud SOC engines** | Existing/shared SOC VMs | TheHive (ticketing), Wazuh cloud path, etc. — not on the customer appliance |

Control plane talks to Appliance Management over **internal** admin APIs (service auth), not by co-locating those daemons on VM 100 forever.

Follow-on implementation KBs (after approval):

| Work | Intent | Lives on (production) |
|------|--------|------------------------|
| Channel gateway | Terminate `wss://…/appliance/v1/channel` | Appliance Management plane |
| Junexis CA service | Issue/revoke appliance client certs | Appliance Management plane |
| Entitlement signer / push | Portal → signed `license.push` | Sign on control plane or HSM; **deliver** via Appliance Mgmt channel |
| OTA / WPK repository | Signed manifests + blobs | Appliance Management plane |
| Admin UI (appliance list/health) | Operator UX | Control plane (calls Appliance Mgmt APIs) |
| KB-016 bridge (interim) | HTTPS register/heartbeat | May start on control plane; **migrate** to Appliance Mgmt |

Until the split lands, lab appliances can still use KB-016 on VM 100 — with an explicit migration debt tracked here.

---

## 13. Security requirements (non-negotiable)

- No secrets in Git; placeholder keys only under `licensing/keys/`
- Tenant isolation enforced server-side on all channel frames
- Customer portal never receives raw logs/PCAP/credentials (KB-036 safety)
- **No TheHive / ticketing stack on the appliance** — cases stay in Junexis Cloud SOC
- **One ISO** for physical and virtual, on-prem and cloud-endpoint appliance contracts
- Default-deny inbound on appliance Internet face; after lock, **no general Internet egress** except SOC secure channel
- Cryptographic wipe on decommission
- Fail-closed entitlements and fail-closed tenant mapping (existing control-plane rule)
- Production handoff requires `network_mode: locked` after successful bootstrap

---

## 14. What KB-093 changes

### Changes

- `junexis-appliance/` — build repo scaffold + docs
- `docs/KB093_JUNEXIS_HARDENED_ON_PREM_APPLIANCE_ARCHITECTURE.md` — this file
- `scripts/kb093_validate_junexis_appliance_architecture.sh`
- `docs/AI_PROMPT_LEDGER.md` (ledger row)

### Must not change (this KB)

- `backend-api/`, `frontend-*`, `postgres/init/`, `docker-compose.yml`, `.env`
- Live engine VMs / installs

---

## 15. Validation

```bash
cd /opt/mssp-control
chmod +x scripts/kb093_validate_junexis_appliance_architecture.sh
./scripts/kb093_validate_junexis_appliance_architecture.sh
```

Expected final line:

```text
KB-093 JUNEXIS HARDENED ON-PREM APPLIANCE ARCHITECTURE VALIDATION PASSED
```

---

## 16. Build phases (approved to start)

| Phase | Scope | Status |
|-------|--------|--------|
| **B0** | Docs + scaffold + bootstrap/lock design + production split note | Done (KB-093) |
| **B1** | `junexis-cli` stub + network mode state + nftables profiles + Ansible `minimize` | Done |
| **B2** | Packer/Subiquity + Docker/KVM builder + disposable qcow2 smoke (`b2-smoke.yml`) | Validate gate done; **nested Packer on VM 100 retired as default** |
| **B2F / 093F** | **Proxmox build VM 113** factory (create → Ansible provision → export qcow2/raw/ISO) | **Active default** — `docs/KB093F_PROXMOX_APPLIANCE_BUILD_VM.md` |
| **B2E / 093E** | DuckDB/Parquet data lake, anonymizing telemetry router, retrospective hunter | **Done** — `scripts/kb093e_validate_appliance_engine.sh` |
| **B3** | Channeld stub + mock Appliance Mgmt gateway (separate process; not permanent on VM 100) | Later |
| **B4** | Production Appliance Management server cutover plan | Before GA |

Do **not** implement permanent channel/CA/OTA hosting on `mssp-control` — design for the separate Appliance Management plane from B3 onward.
