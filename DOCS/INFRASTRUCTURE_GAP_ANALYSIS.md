# MSSP Infrastructure Gap & VM Deployment Audit

**Status:** Living audit + remediation log  
**Created:** 2026-08-01 · **Remediation applied:** 2026-08-01 (VM 110 + VM 109 EASM)

**Sources of truth inspected:** live code under `backend-api/`, `ansible/inventory/hosts.yml`, `DOCS/MSSP_IP_PROXMOX_INVENTORY.md`, `DOCS/SERVICE_ENGINE_DEVELOPMENT_ROADMAP.md`, KB-036 / KB-054 / KB-078 / KB-079 / KB-083 / KB-091  
**Rule:** Git tags, validation scripts, and inspected source beat stale prose in older KBs.

---

## 0. Remediation update (2026-08-01)

| Item | Result |
|---|---|
| **VM 110 Velociraptor** | **LIVE** — Proxmox VM created (`192.168.0.220`); Velociraptor + HTTP bridge on `:8001`; control plane `velociraptor_client.py` smoke-tested (`collect_artifacts` → job RUNNING) |
| **VM 109 Amass EASM** | **LIVE** — `/opt/mssp-easm-agent` + timer; APIs `/integrations/easm/scan-plan` + `/sync`; Amass v4.2.0 installed |
| **Shuffle durability** | **LIVE** — Redis-backed `shuffle_retry_queue` (replaces fire-and-forget for Wazuh ingress + EDR webhooks) |
| **Kill-process honesty** | **Improved** — dispatch stays `executing` until endpoint `applied` callback; Linux AR script posts callback |
| **Still open** | VM 108 MISP; ITDR live IdP connectors; Velociraptor **endpoint client enrollment**; real canary sensors; block-hash enforcement |

---

## 1. Executive summary

The control plane on **VM 100** (`192.168.0.201`) already presents a full **10-card Service Catalog**. Behind those cards, maturity is uneven:

| Maturity | Meaning |
|---|---|
| **Live engine + adapter** | Real tool on an external VM; control plane normalizes into PostgreSQL |
| **Live adapter / lightweight probe** | Real work runs from VM 100 (or pulls live Wazuh/Suricata data) without a dedicated heavy engine VM |
| **Analysis adapter (seeded fallback)** | Dashboard prefers live DB rows; if empty, seeds deterministic sample data so cards are never blank |
| **Planning only** | Inventory placeholder / KB plan — VM or tool not deployed |

**Largest remaining infrastructure gaps:**

1. **VM 108 (MISP)** — not created; Threat Intelligence still uses curated reputation + alert IOC extraction.  
2. **ITDR** — no live Microsoft Graph / Entra / AWS IAM connector yet (seeded identity events).  
3. **Velociraptor clients** — server LIVE; Windows/Linux agents not yet enrolled for deep host collections.  
4. **Real deception sensors** — tripwires may still seed when no live canary feed exists.  
5. **Block-hash enforcement** — still honesty-limited (text denylist, not WDAC/AppLocker).

**Already production-path engines:** Wazuh (101), TheHive+Shuffle (102), Suricata+Zeek (106), Greenbone CE + Nuclei + Vuls + **Amass EASM** (109), **Velociraptor** (110), Ansible controller (112).

---

## 2. Current state vs ideal state (10 catalog services)

| # | Catalog service | `service_key` | Current backend location | Ideal backend | Gap severity |
|---|---|---|---|---|---|
| 1 | Log & Event Monitoring | `log_event_monitoring` | **External VM 101** — Wazuh webhook → `POST /integrations/soc/hooks/wazuh/{token}` → `security_alerts` | Same | **Low** (ops hardening: TLS verify, durable Shuffle forward) |
| 2 | Incident Response & Casework | `incident_response` | **External VM 102** — TheHive + Shuffle; SOC sync / case adapters → `incidents` | Same | **Low** |
| 3 | Security Automation & Containment | `security_automation` | **VM 100 adapter + VM 101 AR** — `wazuh_client.run_active_response` + scripts under `deploy/wazuh-active-response/`; Shuffle webhook on VM 102 for EDR workflows | Same + stronger proof on kill/block-hash | **Medium** (honesty gaps KB-091) |
| 4 | Vulnerability Management (VMaaS) | `vulnerability_management` | **External VM 109** — Nuclei/Vuls agent pulls scan-plan / pushes sync; Greenbone CE also feeds `vulnerabilities`. Control plane: `vmaas_service` + `vuln_sync` | Same (Greenbone Enterprise optional later — KB-077) | **Low** (seeded samples only when no live findings) |
| 5 | Continuous Compliance (CaaS) | `continuous_compliance` | **VM 100 adapter → VM 101** — live Wazuh SCA API (`sca_compliance_service` / `wazuh_client`) | Same | **Low** |
| 6 | Network Detection & Response (NDR) | `network_detection_response` | **External VM 106** Suricata (+ Zeek co-located) → alerts into control plane; `ndr_service` imports matching alerts, else **seeds samples** | Same + real flow counters (not fabricated sensor metrics) | **Medium** |
| 7 | Threat Intelligence | `threat_intelligence` | **VM 100 analysis adapter** — extract IOCs from alerts + hardcoded `_REPUTATION_DB`; **no MISP client** | **VM 108 MISP** (+ optional OTX/AbuseIPDB) via adapter | **High** |
| 8 | Endpoint Forensics & Deception | `endpoint_forensics_deception` | **External VM 110** Velociraptor bridge `:8001` + EDR artifacts; deception tripwires may still seed | Same + enrolled clients + real canaries | **Low–Medium** (server live; clients pending) |
| 9 | External Attack Surface (EASM) | `external_attack_surface` | **External VM 109** Amass/Nuclei agent via `/integrations/easm/*` (remote default) | Same | **Low** |
| 10 | Cloud & Identity Protection (ITDR) | `cloud_identity_protection` | **VM 100 analysis adapter** — `itdr_service.py` registers domain + **seeds** identity events (no Graph/Entra API) | Live IdP connectors (Entra/M365/AWS IAM) via adapter | **High** |

### Legend (backend class)

- **Native on VM 100:** FastAPI service that *executes* discovery/analysis on the control plane itself.  
- **Connected external VM:** Tool process lives on 101/102/106/109/…; control plane is adapter-only.  
- **Analysis adapter:** Prefer real DB/engine rows; otherwise deterministic seed so UI demos cleanly.

---

## 3. Audit checkpoint detail

### 3.1 VM 110 — Velociraptor Forensic Server

**Code paths inspected (actual filenames):**

| Expected name in task | Actual path in repo |
|---|---|
| `forensics_deception_service.py` | `backend-api/app/services/endpoint_forensics_service.py` |
| `forensics_deception.py` | `backend-api/app/api/routes/endpoint_forensics.py` |
| Related live EDR forensics | `edr_actions.py`, `edr_forensics_storage.py`, `shuffle_edr_client.py`, routes in `edr.py` |

**Finding:** Remote triage does **not** call a live Velociraptor API.

- Phase 7 sync seeds tripwires / deception events / collection metadata (templates + tenant hash).  
- Optional bridge imports real rows from `edr_forensic_artifacts` (Wazuh AR + signed upload path).  
- `VELOCIRAPTOR_SERVER_URL` is only passed through in Shuffle EDR webhook payloads (`shuffle_edr_client.velociraptor_server_url()`). **Nothing HTTP-calls that URL.**  
- No `velociraptor_client.py`, no Ansible role `velociraptor/`, no API token env vars beyond the unused URL passthrough.  
- Inventory placeholder: `ansible/inventory/hosts.yml` → `192.168.0.220`, VMID **110**.  
- Plan doc: `docs/KB054_VELOCIRAPTOR_DFIR_DEPLOYMENT_PLAN.md` (planning only). Evidence workflow: `docs/KB055_DFIR_EVIDENCE_SAFETY_CASE_WORKFLOW.md`.

**Requirements to deploy and pair VM 110 (outline):**

1. **Create Proxmox VM 110** — hostname `velociraptor`, static IP `192.168.0.220` (per inventory / KB-054). Size for DFIR (CPU/RAM/disk per KB-054 implementation KB — not installed by this audit).  
2. **Named implementation KB** (do not install until approved) — Ansible role mirroring `greenbone`/`wazuh_stack` pattern: preflight → install server → validate.  
3. **Secrets (files / vault — never commit):** server admin password, client enroll config, TLS/gRPC material; control-plane `VELOCIRAPTOR_SERVER_URL` + API credential files.  
4. **Control-plane wiring:** add `velociraptor_client.py`; change `COLLECT_FORENSICS` in `edr_actions.py` to start VQL collections; map results → `edr_forensic_artifacts` / forensics collections with **customer-safe** metadata only.  
5. **Endpoint clients:** enroll Windows lab (VM 104) and future Linux lab; tag with tenant metadata.  
6. **TheHive linkage:** case attachment metadata per KB-055 (SOC-only; never raw evidence to `:3001`).  
7. **Deception sensors:** separate named KB for real canaries — until then, keep seeded tripwires clearly as analysis-adapter data.

---

### 3.2 VM 109 — Vulnerability & EASM discovery (Greenbone / Nuclei / Vuls)

**VMaaS (`vmaas_service.py`) — connected to VM 109**

| Path | How it works |
|---|---|
| Nuclei + Vuls | Agent on **109** (`/opt/mssp-vuln-free`) polls `GET /integrations/vuln/scan-plan`, scans, `POST /integrations/vuln/sync` with `VULN_SYNC_API_KEY` |
| Greenbone CE | Co-located on 109; GMP / Task-Done webhook → same `vulnerabilities` table (KB-068–070) |
| Control plane | `run_tenant_vmaas_sync` imports live findings; **seeds sample CVEs only if empty** |
| Ansible | `ansible/roles/vuln_free_stack/`, `ansible/roles/greenbone/` — **hard-gated to vm_id 109** |

**EASM (`easm_service.py`) — not actually using Amass on 109**

| Claim in docstring | Reality in code |
|---|---|
| “Heavy scanners (Amass / Nuclei) remain on VM 109” | **No Amass client, no `AMASS_*` env, no SSH to 109 for EASM** |
| Phase 2 MVP | Stdlib DNS + fixed subdomain list + port/TLS/HTTP probes **from VM 100** |

**Missing / needed for deeper VM 109 EASM (if approved):**

- Amass (or equivalent) + Nuclei templates on 109  
- Agent or API that posts discoveries into control-plane EASM tables (same pattern as vuln sync)  
- Shared auth key (prefer per-engine key files under `.secrets/`, not Git)  
- Explicit decision: keep lightweight probes on 100 as permanent MVP **or** move all outbound discovery off the control plane (aligns with “no scanners on VM 100”)

**Greenbone / Nuclei config note:** Tool credentials live **on VM 109 host files**, not in FastAPI env. Control plane only needs sync/webhook keys (`VULN_SYNC_API_KEY`, Greenbone ingress tokens as already used by KB-070).

---

### 3.3 Wazuh / Sysmon / Active Response

| Concern | Status |
|---|---|
| Alert stream into control plane | **Live** — Wazuh Manager webhook → instant ingress; fail-closed tenant via agent group binding |
| Sysmon | Windows agent telemetry path (lab VM 104); not a separate VM — depends on agent config / rules on 101 |
| Isolate host | **Live** — Linux `mssp-isolate-host` + Windows `netsh` AR; callback proof for isolate/unisolate |
| Kill process | **Wired** via Wazuh AR scripts; **weaker proof** than isolate (KB-091) |
| Block hash | **Honesty gap** — appends denylist file; **not** WDAC/AppLocker/ASR enforcement |
| Shuffle notify | EDR actions also POST to Shuffle webhook (fail-safe) |

**Gaps to close (not new VMs):** durable queue instead of `threading.Thread` for Shuffle forward; per-execution callback tokens; optional `WAZUH_API_VERIFY_TLS=true`; real block-hash enforcement if product claims require it.

---

### 3.4 SOAR & workflow automation (Shuffle / n8n)

| Item | Finding |
|---|---|
| External SOAR | **Shuffle on VM 102** (`192.168.0.212`) with TheHive — **live** |
| Standalone VM 103 | **Deferred** — inventory placeholder only |
| n8n | **Not used** in this repo |
| Control-plane workers | FastAPI handles sync HTTP; Redis is primarily health/cache — **not** the SOAR engine. Separate AI/notification workers are unrelated to Shuffle playbooks |
| Automation path | Wazuh alert → (optional) Shuffle → TheHive ticket; EDR actions → Shuffle webhook + Wazuh AR |

**Gap:** treat Shuffle as source of truth for multi-step playbooks, but make outbound webhook delivery **durable** (retry / dead-letter) and tighten callback auth.

---

## 4. Pending VM deployment list

Ordered by impact on closing “adapter → live engine” gaps for the catalog:

| Priority | VMID | Hostname / IP | Tool | Why needed | Status today |
|---|---:|---|---|---|---|
| **P0** | **110** | `velociraptor` / `192.168.0.220` | Velociraptor | Replace seeded DFIR/deception with real collections; pair `COLLECT_FORENSICS` | **Not created** |
| **P1** | **108** | `misp` / `192.168.0.218` | MISP | Live threat intel feeds / sharing for Card 7 | **Not created** |
| **P2** | **109** (enhance) | `greenbone` / `192.168.0.219` | Amass (+ Nuclei EASM templates) | Move deep EASM off VM 100; match docstring | **VM exists**; Amass/EASM agent **missing** |
| **P3** | **105** | Linux lab / `192.168.0.215` | Wazuh agent (+ optional AR) | Re-enroll Linux endpoint lab (removed 2026-07-29) | **Removed** — reinstall when needed |
| **P4** | **111** | `monitoring` / `192.168.0.221` | Prometheus/Grafana | Platform health (not a catalog card) | **Not created** |
| — | 103 | Shuffle standalone | — | Not required (Shuffle on 102) | Deferred by design |
| — | 107 | Zeek standalone | — | Not required (Zeek on 106) | Deferred by design |
| — | Enterprise Greenbone | optional replace/augment 109 | Paid feed | Only when volume justifies spend (KB-077) | Deferred |

**Already deployed (baseline — do not recreate unless DR):**

| VMID | IP | Role |
|---:|---|---|
| 100 | 192.168.0.201 | Control plane |
| 101 | 192.168.0.211 | Wazuh |
| 102 | 192.168.0.212 | TheHive + Shuffle |
| 104 | 192.168.0.214 | Windows endpoint lab |
| 106 | 192.168.0.216 | Suricata + Zeek |
| 109 | 192.168.0.219 | Greenbone CE + Nuclei + Vuls |
| 112 | 192.168.0.222 | Ansible automation |

---

## 5. Action plan (bridge remaining gaps)

### Phase A — Documentation & honesty (no new VMs)

1. Keep this file as the living gap list; update `DOCS/SERVICE_ENGINE_DEVELOPMENT_ROADMAP.md` “Later” section when a VM goes live.  
2. Treat Alpha-Win full-catalog demos as **analysis-adapter + live engines mixed** — do not market seeded ITDR/TI/Forensics as live IdP/MISP/Velociraptor.  
3. Decide EASM architecture explicitly: **(a)** approve stdlib probes on VM 100 as permanent MVP, or **(b)** require Amass-class discovery on VM 109.

### Phase B — VM 110 Velociraptor (recommended next install)

1. User approves a **named implementation KB** (builds on KB-054/055).  
2. Create VM 110 at `192.168.0.220`.  
3. Ansible role: install + validate Velociraptor server.  
4. Wire `velociraptor_client` + `COLLECT_FORENSICS`; set `VELOCIRAPTOR_SERVER_URL` (+ credential files).  
5. Enroll lab endpoints; SOC-only UI; customer sees status only.  
6. Later: real deception sensors KB.

### Phase C — VM 108 MISP

1. Named KB + create VM at `192.168.0.218`.  
2. MISP install; control-plane `misp_client` replace `_REPUTATION_DB` seeding.  
3. Entitlement `misp_enabled` already exists — flip from analysis adapter to live pull.

### Phase D — Deepen VM 109 for EASM

1. Install Amass (and optional Nuclei EASM templates) under a dedicated path on 109.  
2. Agent pattern like vuln sync: plan → scan → POST findings to control plane.  
3. Reduce or remove outbound scanning from VM 100 once agent is healthy.

### Phase E — ITDR live connectors

1. Named KB for Microsoft Graph / Entra (and later AWS).  
2. Replace `itdr_service` seed path with live event import; keep customer-safe labels.

### Phase F — Containment & SOAR hardening (no new VMs)

1. Close KB-091 items: callback proof for kill/block-hash; per-execution tokens.  
2. Replace Shuffle fire-and-forget threads with Redis/RQ or equivalent durable jobs.  
3. Enable Wazuh API TLS verify when certificates are ready.

### Phase G — Optional ops

1. Reinstall Linux lab VM 105 when needed for E2E.  
2. VM 111 Prometheus/Grafana when platform monitoring becomes priority.

---

## 6. Config / secret checklist (names only — never commit values)

| Integration | Typical env / secret **names** | Where used |
|---|---|---|
| Wazuh | `WAZUH_API_URL`, `WAZUH_API_USER`, `WAZUH_API_PASSWORD(_FILE)`, `WAZUH_INGRESS_TOKEN(_FILE)`, `WAZUH_API_VERIFY_TLS` | Alert ingress, AR, SCA |
| Shuffle | `SHUFFLE_WEBHOOK_URL(_FILE)` | Alert forward, EDR workflows |
| TheHive | `THEHIVE_URL`, `THEHIVE_USER`, `THEHIVE_PASSWORD(_FILE)`, `THEHIVE_DEFAULT_ORG` | Case adapter |
| Vuln sync (109 → 100) | `VULN_SYNC_API_KEY(_FILE)` | Nuclei/Vuls agent |
| EDR callbacks | `EDR_CALLBACK_API_KEY(_FILE)`, `EDR_FORENSICS_*` | AR proof, artifact upload |
| Velociraptor (future) | `VELOCIRAPTOR_SERVER_URL` (+ future API credential files) | Passthrough today; real client later |
| Greenbone (on 109 host) | Host-local admin secret files under `/opt/mssp-greenbone/` | GMP / lab scripts — not in Git |

---

## 7. Related documents

| Doc | Role |
|---|---|
| `DOCS/SERVICE_ENGINE_DEVELOPMENT_ROADMAP.md` | Phase tracker for catalog engines |
| `DOCS/MSSP_IP_PROXMOX_INVENTORY.md` | Live vs planned VM IPs |
| `docs/KB036_MSSP_PLATFORM_ARCHITECTURE_ROADMAP.md` | Full platform roadmap (some VM “Future” rows are stale vs inventory) |
| `docs/KB054_VELOCIRAPTOR_DFIR_DEPLOYMENT_PLAN.md` | VM 110 plan |
| `docs/KB055_DFIR_EVIDENCE_SAFETY_CASE_WORKFLOW.md` | Evidence safety |
| `docs/KB078_NUCLEI_VULS_FREE_STACK.md` / `KB079_*` | VM 109 free vuln stack |
| `docs/KB077_GREENBONE_ENTERPRISE_READINESS_PLAN.md` | Paid Greenbone deferral |
| `docs/KB083_EDR_LIVE_WAZUH_SHUFFLE.md` / `KB091_*` | Containment honesty |

---

## 8. Bottom line

- **Do not install** Velociraptor, MISP, or Amass until you explicitly start the matching KB.  
- **Next infrastructure create** that unlocks the biggest catalog honesty gap: **VM 110 Velociraptor**.  
- **Next deepen on an existing VM:** Amass/EASM agent on **VM 109**, and/or **VM 108 MISP**.  
- Core MDR path (Wazuh → control plane → Shuffle/TheHive → Active Response) is already the production backbone on VMs **100 / 101 / 102 / 106 / 109**.
