# KB-093G — Bootable install ISO, core entitlements, and licensing (planning)

Status: Planning agreement + **P1 build started** (2026-08-04)  
Audience: Product / operator  
Supersedes delivery misunderstanding of “qcow2 delivery ISO” for customer media.  
Related: KB-093, KB-076, SERVICE_MATRIX.md  

**P1 deliverables in tree:** `junexis-appliance/iso/build_install_iso.sh`, idle roles (`license_enforcer`, `service_manager`, `wazuh_local` + Fluent Bit), Admin mint `POST /admin/tenants/{id}/appliance-licenses`, `junexis-cli license apply|show`, validator `scripts/kb093g_validate_appliance_install_iso.sh`.

---

## 1. Decisions locked in this discussion

| Topic | Decision |
|-------|----------|
| Customer media | **One bootable/installable ISO** (bare metal, hypervisor VM, cloud VM) — not a pre-baked qcow2 as the field deliverable |
| TheHive / Shuffle on ISO | **No** — central ticketing + SOAR stay in Junexis Cloud SOC / Admin |
| Engines on ISO | **Every appliance-installable catalogue service** is **bundled on the ISO, fully installed/configurable, idle** until a Junexis-issued license enables it. No “ship later / download later” for those engines. |
| Offline package pool | `junexis-appliance/iso/offline-packages/` — fetch with `scripts/b2_fetch_offline_packages.sh` (wazuh-manager, fluent-bit, suricata + deps); `build_install_iso.sh` embeds them so firstboot installs without Internet |
| Core always included (after contract) | **Log & Event Monitoring** + **Ticketing (central)** — with or without appliance |
| Contract gate | Core (and any other service) only after **minimum 1-year contract** signed |
| License keys | **Only** Junexis MSSP control plane can generate license keys, bound to **that customer/tenant identity** (and appliance fingerprint when appliance SKU) |
| Appliance Wazuh Manager | **Always-on for appliance SKU** once core contract active (local agents need a Manager) |
| Fluent Bit | **Included on appliance ISO** (appliance-side collector next to Manager — never as an endpoint agent) |
| Same commercial model | With-appliance and without-appliance use the **same entitlement / portal story** |
| Hardening | Minimized Ubuntu + CIS-style harden + Junexis-only remote mgmt + tamper resistance |
| ISO currency | Rebuild/promote patched ISOs for **new** deployments; in-field updates via channel/OTA after lock |
| Single media | Same ISO for physical / on-prem VM / cloud VM |

---

## 2. Commercial model (with vs without appliance)

```
Sign ≥1 year contract
    → Core entitled: Log & Event Monitoring + Ticketing
    → Optional upsells: NDR, VMaaS, Automation, … (svc-03…10)

Without appliance:
    Core LEM → cloud/shared Wazuh path (existing)
    Ticketing → central TheHive + portals (existing)

With appliance:
    Core LEM → local Wazuh Manager (on appliance) + agents on site
    Ticketing → still central TheHive + portals (alerts sync via channel)
    Upsells → start idle local engines on appliance + show on Customer dashboard
```

**“Enabled by default”** means: included in the **minimum core SKU** of the signed contract — not free / not pre-contract.

---

## 3. What goes on the install ISO (bundled, idle)

### 3.1 Always present after install (small core runtime)

- Hardened minimal Ubuntu Server LTS  
- `junexis-cli`, channel agent, license enforcer, service manager  
- Bootstrap → locked network profiles  
- Tamper / integrity baseline (see §8)

### 3.2 Core commercial (start when 1-year core contract active)

| Capability | Where it runs |
|------------|----------------|
| Log & Event Monitoring | **Local Wazuh Manager** + collectors on appliance; **wazuh-agent only** on endpoints |
| Ticketing / cases | **Cloud SOC TheHive + Admin/Customer portals** — never on ISO |

### 3.3 All appliance-installable catalogue engines (on ISO, idle)

**Correction:** Not “some engines later.” If a catalogue service is defined as installable on the appliance, its software **must already be on the installed system**, configured enough to start, and **stopped/disabled** until a Junexis license key enables it.

| ID | Catalogue service | On appliance ISO (idle until license) |
|----|-------------------|----------------------------------------|
| svc-01 | Log & Event Monitoring | Local Wazuh Manager + collectors (core when licensed) |
| svc-02 | Incident Response (local execution) | `ir-worker` only — **not** TheHive |
| svc-03 | Security Automation | Local containment / AR worker — **not** Shuffle |
| svc-04 | Vulnerability Management | Scanner engines (Nuclei/Vuls-class) |
| svc-05 | Continuous Compliance | SCA aggregator |
| svc-06 | NDR | Suricata (+ Zeek when in catalogue build) |
| svc-07 | Threat Intelligence | Local IOC cache |
| svc-08 | Endpoint Forensics & Deception | Collection listener + rule packs |
| svc-09 | EASM | Internal probe runner |
| svc-10 | ITDR | IdP/AD connectors |

**Catalogue services that are NOT installable on the appliance** (by design — still sold, fulfilled centrally):

| Catalogue capability | Where it runs |
|----------------------|---------------|
| **Ticketing / cases** | Central TheHive + Admin/Customer portals |
| **SOAR playbook UI (Shuffle)** | Cloud SOC only (default SKU) |

So: your assumption “all services in the catalogue are installable on the appliance” is **almost** right — all **detection/scan/local-execution** services are. **Ticketing** (and default SOAR UI) stay central on purpose.

---

## 4. Fluent Bit — role (locked in)

**Endpoint rule (hard):** only **`wazuh-agent`** on endpoints. Never Fluent Bit on endpoints.

**On the appliance (bundled, idle until LEM/core license):** Fluent Bit sits beside local Wazuh Manager for agentless / syslog / CEF-style feeds into Manager or the SOC channel. It is **not** a second endpoint agent.

| Need | Tool |
|------|------|
| Endpoint logs/FIM/SCA/AR | `wazuh-agent` → local Manager |
| Agentless / device syslog pipes | **Fluent Bit on appliance** → Manager / channel |

---

## 5. svc-02 — IR (local only): what it is and value

**Not** a local ticketing system.

| | Cloud (always) | Appliance svc-02 |
|--|----------------|------------------|
| Tickets / cases / TheHive | Yes | No |
| Analyst UI | Admin portal | No |
| Value | Case workflow | **Execute** signed containment jobs **on the customer LAN** when cloud SOC decides |

Examples of local value:

- Quarantine host via local Wazuh Active Response when the box cannot wait for a human on-site  
- Apply a local firewall/nftables block that cloud cannot push into the customer LAN directly  
- Collect a forensic bundle from an endpoint **through** the local Manager and stage it for channel upload  

Flow: SOC opens/updates case in **central** TheHive → signed job → appliance `ir-worker` runs → result reported on channel → case updated in cloud.

---

## 6. svc-03 — Security Automation vs Shuffle (SOAR)

### 6.1 Difference

| | Shuffle (cloud SOAR) | Appliance svc-03 |
|--|----------------------|------------------|
| What it is | Playbook UI, integrations, human/automation workflows | Small **local action worker** |
| Where | Junexis Cloud SOC | Customer appliance |
| On ISO? | **No** | Yes, idle until entitled |
| Customer sees | Outcomes via portals / cases | Capability “Security Automation” when entitled |

**svc-03** = “run approved local actions” (AR scripts, network device API hooks, isolate VLAN via local controller) under entitlement + signed policy.  
**Shuffle** = where rich multi-step playbooks and many SaaS integrations live for the **MSSP SOC**.

### 6.2 Will customers reject “SOAR in cloud”?

Often they ask; the answer depends on **what data leaves**:

| Leaves site (typical, minimize) | Stays on site |
|----------------------------------|---------------|
| Alert summaries, case metadata, job requests/results, entitlement state | Full raw logs, PCAP, bulk telemetry (policy-controlled) |

If cloud Shuffle only receives **already-normalized case/alert metadata** (same class of data as central ticketing), most customers accept it — same as accepting central TheHive.

If a customer requires **zero** orchestration dependency on cloud:

- Default ISO still has **no Shuffle**  
- Offer a **special SKU** later (local SOAR) — not the default product  
- Document data-flow in the contract (DPA / processing schedule)

**Recommendation:** keep default = cloud SOAR for MSSP + local svc-03 for LAN actions; special SKU only if procurement forces it.

---

## 7. Entitlement / licensing — strong mechanism (target design)

### 7.1 Principles

- Portal/billing is system of record (same for appliance and non-appliance)  
- **Only the Junexis MSSP control plane** can generate license keys (Admin role / internal API — never customer self-mint)  
- Keys are bound to **that customer/tenant identity** (+ appliance id/fingerprint for appliance SKU)  
- Appliance **never** trusts an unsigned “enable” flag alone  
- Binding: tenant + appliance fingerprint + expiry + service set  
- Online and offline fulfillment  

### 7.2 Artifact: signed entitlement token (JWS)

Issued by Junexis license CA (Ed25519 or ECDSA P-256):

```json
{
  "iss": "junexis-license",
  "sub": "<tenant_id>",
  "aid": "<appliance_id>",
  "fp": "<hardware/cloud instance fingerprint>",
  "svc": ["svc-01", "svc-03"],
  "core": true,
  "nbf": "...",
  "exp": "...",
  "jti": "<unique license id>",
  "contract": "<contract_id>",
  "min_term_years": 1
}
```

Signed → compact JWS. Appliance verifies with embedded Junexis public keys (rotatable via channel).

### 7.3 Delivery paths

1. **Online:** Admin entitles → control plane signs → `license.push` on channel → appliance stores `/var/lib/junexis/entitlements.json` → `service_manager` reconciles units  
2. **Offline / on-site:** Admin exports license file → engineer `junexis-cli license apply --file …`  
3. **Heartbeat:** appliance reports `enabled_services[]` + health → Admin/Customer dashboards  

### 7.4 Anti-abuse

- Fingerprint mismatch → refuse  
- Expiry / contract end → stop non-grace modules; core grace policy product-defined  
- Replay: `jti` denylist / monotonic `iat`  
- Clock skew limits; optional channel nonce  
- Audit log of every apply/enable/disable  

### 7.5 Non-appliance parity

Same entitlement records in PostgreSQL; fulfillment target is `cloud_engines` vs `appliance_id`. Customer dashboard capability labels stay identical (KB customer-safe labels).

---

## 8. Hardening + “locked network” + tamper posture

### 8.1 Minimized + hardened OS

- Purge unused packages/snaps; CIS-aligned baselines  
- ssh restricted; Junexis mgmt only via `junexis-cli` + outbound channel  
- Secure Boot–capable layout where hardware allows  
- Measured config: hashes of critical unit files / entitlement file  

### 8.2 Locked network (post-bootstrap)

| Mode | Meaning |
|------|---------|
| **BOOTSTRAP** | Temporary outbound Internet for critical OS/engine patches + first registration |
| **LOCKED** | Day-to-day: **no general Internet**. Allowed: customer LAN (agents/syslog/SPAN as configured) + **outbound-only** SOC channel (DNS/NTP as policy). No inbound from Internet |

“Locked” = production posture after first-time updates — not “no network.”

### 8.3 Tamper resistance (goals)

- Read-only root or A/B root where feasible; secrets on encrypted volume  
- Refuse unsigned entitlement / OTA  
- Offboard wipe for keys + entitlements  
- Detect unexpected unit enable outside reconciler  

### 8.4 Keeping the ISO fresh (new deployments)

| Path | Use |
|------|-----|
| **Rebuild ISO** in CI when Ubuntu security + engine versions update → promote `Junexis-Appliance-vX.Y.iso` | New customer installs |
| **In-field OTA** over channel after LOCKED | Already-deployed appliances |

Old ISOs are retired from the “ship new customers” channel; version + changelog published internally.

---

## 9. Build phases (revised after your answers)

| Phase | Scope |
|-------|--------|
| **P1** | True **bootable install ISO** + hardened minimal Ubuntu + core runtime + **all engines packaged idle** + local Wazuh Manager + channel/license stubs |
| **P2** | Strong entitlement wiring (sign, push, apply, heartbeat service list, Admin/Customer visibility) + 1-year contract gate |
| **P3** | Production reconcile of each idle engine; locked network soak; OTA/ISO rebuild pipeline |
| **P4** | Optional special SKU research (local SOAR) only if customers demand |

Factory qcow2 path remains optional CI smoke — **not** customer media.

---

## 10. Open items (small)

1. Core grace period after contract expiry (how many days before Manager stops).  
2. Exact engine versions pinned per ISO tag.  
3. Fluent Bit: **mandatory on appliance ISO** (idle until LEM/core license) — locked 2026-08-04.  

---

## 11. One-line product summary

**One hardened install ISO → all engines present but idle → 1-year contract unlocks core LEM (local Manager) + central ticketing → upsells start local modules → same dashboards as non-appliance; TheHive/Shuffle stay in cloud; endpoints run only wazuh-agent.**
