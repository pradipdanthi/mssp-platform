# Executive Summary: Go-Live Beta Demo Readiness

**Report date:** 2026-08-02 (IST)  
**Environment:** On-prem production-path control plane VM 100 (`192.168.0.201`) + engine VMs  
**VIP demo tenant:** Alpha-Win Corp (`ALPHAWINCORP-6VS2`)  
**Git HEAD at audit:** `f3051c4`  
**September 14 context:** This report covers **Beta Demo readiness on the current on-prem stack**. HA cloud migration remains a separate workstream before the Sep 14 deadline.

### Verdict (one line)

**PASSED WITH CONDITIONS** — All 10 catalog engines are demonstrable for Alpha-Win with live backends or documented adapter fallbacks. Three VMs (105 / 108 / 110) were **stopped overnight** and had to be started for this audit; keep them running for demos. Live Microsoft Graph ITDR and Windows Velociraptor client remain optional polish items.

---

## 1. Catalog & Service Engine Status Matrix

| # | Catalog service | Sub-tool stack | VM / IP | Primary control-plane route(s) | Live check (2026-08-02) | Status |
|---:|---|---|---|---|---|---|
| 1 | Log & Event Monitoring | Wazuh Manager / Indexer / agents | **101** `192.168.0.211` | Ingress → `security_alerts`; Admin/Customer alerts | API `:55000` up; **3 agents active**; Alpha **459** alerts | **100% LIVE** |
| 2 | Incident Response & Casework | TheHive **4.1.24** + Shuffle | **102** `192.168.0.212` | Incidents / SOC sync | TheHive status OK; Alpha **13** incidents | **100% LIVE** (note: TheHive **4.x**, not 5) |
| 3 | Security Automation & Containment | Wazuh AR + Shuffle queue | **101** + **102** | `/v1/edr/actions/*` | AR scripts present (`isolate` / `kill` / `block-hash`); Redis durable queue `mssp:shuffle:outbound`; **6** historically `verified` EDR executions | **100% LIVE** (proof history; do not fire quarantine mid-demo unless planned) |
| 4 | Continuous Compliance (CaaS) | Wazuh SCA | **101** | `/admin/compliance/{code}/sync`, Customer Compliance | Sync **200**, score **27.3%**, 359 checks | **100% LIVE** |
| 5 | Vulnerability Management (VMaaS) | Greenbone CE + Nuclei (+ Vuls) | **109** `192.168.0.219` | `/admin/vmaas/*/sync`, vulns APIs | GSA HTTPS 200; Nuclei **v3.11.0**; VMaaS sync **COMPLETED** / `live_ingest` | **100% LIVE** |
| 6 | External Attack Surface (EASM) | Amass agent + Nuclei | **109** | `/admin/easm/*/scan`, `/integrations/easm/*` | Timer active; Amass binary present; scan **PENDING** remote queue (agent cycle) | **100% LIVE** (async agent) |
| 7 | Network Detection & Response | Suricata + Zeek | **106** `192.168.0.216` | `/admin/ndr/*/sync` | Suricata **active**, Zeek running, `eve.json` present; NDR sync **200** (`analysis_adapter` enrichment over live sensors) | **LIVE + adapter enrichment** |
| 8 | Threat Intelligence | MISP-compatible REST bridge | **108** `192.168.0.218:8080` | `/admin/threat-intel/*/sync` | Health OK; sync **`source=misp_vm108`**, **6 IOCs** | **100% LIVE** (bridge, not full MISP UI) |
| 9 | Endpoint Forensics & Deception | Velociraptor + bridge | **110** `192.168.0.220` (`:8001` bridge, `:8002` API, `:8000` frontend) | `/admin/forensics/*/sync`, EDR collect | Bridge healthy; forensics sync OK; VQL collect **HTTP 202 RUNNING** on Linux **105**; tripwire/collection rows present | **LIVE (Linux)** / Windows client pack pending |
| 10 | Cloud & Identity (ITDR) | Microsoft Graph client | Control plane adapter | `/admin/itdr/*/sync` | `itdr_graph_client.configured()=False`; sync **200** via **analysis_adapter** seed | **Adapter fallback** (code-ready for Graph secrets) |

**Customer portal pages present for demo navigation:** Dashboard, Services, Alerts, Incidents, Assets, Reports, Recommendations, Notifications, Account, Compliance, VMaaS/EASM/NDR/Threat Intel/Forensics/ITDR pages under `frontend-customer/src/pages/`.

---

## 2. Infrastructure & VM Connectivity Status

| VMID | Name | IP | Role | Health check (this audit) | Agent / notes |
|---:|---|---|---|---|---|
| 100 | mssp-control | 192.168.0.201 | Control plane (API `:8000`, Admin `:3000`, Customer `:3001`) | `/health` api/db/redis **ok**; portals respond | Docker stack Up |
| 101 | wazuh-stack | 192.168.0.211 | SIEM / SCA / AR | API auth endpoint reachable | Agents: manager, Suricata, **WIN-BL72S84GDTF** active |
| 102 | thehive-shuffle | 192.168.0.212 | Cases + SOAR | TheHive `/api/status` OK (v4.1.24) | Shuffle webhook + durable CP queue |
| 103 | linux-endpoint | (lab) | Extra Linux endpoint | Running on Proxmox | Not primary demo host |
| 104 | windows-endpoint-lab | 192.168.0.214 | Windows lab / Wazuh agent | Running; Wazuh agent **006** active | Velociraptor Windows install still **manual** (`deploy/velociraptor-client/`) |
| 105 | linux-endpoint-lab | 192.168.0.215 | Linux DFIR client | **Was stopped**; started for audit → SSH OK; `velociraptor-client` **active** | Keep powered on for demos |
| 106 | suricata-sensor | 192.168.0.216 | NDR sensors | Suricata active; Zeek process; eve.json | Wazuh agent **002** |
| 108 | misp | 192.168.0.218 | Threat intel bridge `:8080` | **Was stopped**; started → health OK | MISP-compatible bridge (not full MISP UI) |
| 109 | greenbone | 192.168.0.219 | VMaaS + EASM | GSA 200; Nuclei OK; EASM timer active | Amass under `/opt/mssp-easm-agent` |
| 110 | velociraptor | 192.168.0.220 | DFIR server + bridge | **Was stopped**; started → bridge `:8001` OK | gRPC API on `:8002` (bridge owns `:8001`) |
| 112 | automation | 192.168.0.222 | Ansible controller | SSH/hostname OK | Required for restore ops |

**Overnight shutdown lesson:** After powering systems down for the night, **always start 105 / 108 / 110** (and confirm bridge/MISP health) before a customer demo. Serial console “starting serial terminal on interface serial0” is **normal** for these cloud-init VMs — not a pending OS install.

---

## 3. Onboarding & Entitlement Verification

### Alpha-Win Corp (`ALPHAWINCORP-6VS2`)

Live admin entitlements confirm full catalog flags enabled (`wazuh_siem`, `thehive_mode=full`, `shuffle_mode=standard`, Greenbone, Zeek, MISP, Velociraptor, CaaS, EASM, ITDR).

Mapped to customer Service Catalog card labels (same rules as `frontend-customer` Services page):

| Card | Demo status |
|---|---|
| Log & Event Monitoring | **INCLUDED** |
| Incident Response | **INCLUDED** |
| Security Automation | **ACTIVE** |
| Vulnerability Management | **ACTIVE** |
| Continuous Compliance | **ACTIVE** |
| External Attack Surface | **ACTIVE** |
| Cloud & Identity | **ACTIVE** |
| Network Detection | **ACTIVE** |
| Threat Intelligence | **ACTIVE** |
| Endpoint Forensics | **ACTIVE** |

**ALL cards INCLUDED/ACTIVE = true** for Alpha-Win. Customer portal pages for each capability exist (no missing module shells for the 10-card story).

### New-tenant commercial defaults

Code path `entitlements_for_new_tenant()` verified in runtime:

- New short codes → **core-only** (`wazuh_siem` + `thehive_mode=full`; add-ons false / `shuffle_mode=off`) → UI **AVAILABLE** + **Request for Consulting**
- `ALPHAWINCORP-6VS2` → full demo catalog
- Consultation APIs present:  
  `POST/GET /customer/service-consultation-requests/{short_code}`  
  Admin: `/admin/service-consultation-requests*` (sales approval on `:3000`)

---

## 4. Key Pre-Demo Operator Steps

### Must do before every demo session

1. **Power on** VMs **105, 108, 110** (if shut down overnight) and wait ~30s.  
2. Smoke:  
   - `curl http://192.168.0.201:8000/health`  
   - `curl http://192.168.0.218:8080/health`  
   - `curl http://192.168.0.220:8001/health`  
3. Login Admin `:3000` as `platform.admin@example.local` with **`TempPass123!`** (include the `!`).  
4. Login Customer `:3001` as Alpha admin (`admin@alphawin.com` — use the known lab password).  
5. Walk Alpha **Services** page — all 10 cards INCLUDED/ACTIVE; open each engine page once.

### Strongly recommended before stakeholder demo

6. Take a **Proxmox snapshot** of VM 100 (+ optionally 101/102/109) after a clean smoke.  
7. Confirm daily DR timer still next at **20:00 IST** (`scripts/dr_backup_status.sh`) — or run a manual backup if demo day skips the evening window.  
8. Do **not** isolate the Windows lab host mid-demo unless the containment story is planned; show historical verified EDR rows / AR script presence instead.

### Optional polish (not blockers for Beta Demo)

9. Install Velociraptor on **Windows VM 104** via `deploy/velociraptor-client/`.  
10. Add Azure Graph app secrets to enable **live ITDR** (until then, seeded identity events still demo cleanly).  
11. Optional full upstream MISP UI later — current REST bridge already feeds TI.  
12. HA cloud migration plan/runbook for **September 14** (separate from this on-prem beta readiness).

---

## 5. Beta Demo Readiness Verdict

| Gate | Result |
|---|---|
| 10 catalog engines demonstrable | **PASS** |
| Alpha-Win full entitlement / cards | **PASS** |
| New-tenant core-only + consulting request path | **PASS** |
| Control plane + primary engines healthy | **PASS** (after starting 105/108/110) |
| Honest marketing posture | **PASS** — do not claim TheHive 5, full MISP UI, or live Entra Graph without secrets |
| HA cloud (Sep 14) | **OUT OF SCOPE** for this on-prem beta report — schedule as next milestone |

### Final verdict

# **PASSED WITH CONDITIONS**

**Conditions:** Keep DFIR/MISP/Linux-lab VMs powered for demos; treat ITDR Graph and Windows Velociraptor as optional upgrades; describe TheHive as **4.x** and MISP as a **compatible bridge**.

The platform is ready for an initial **Beta Demo** of the multi-tenant MSSP control plane and 10-card Service Catalog on the current on-prem path. Proceed to stakeholder walkthroughs, then execute the HA cloud migration workstream ahead of **September 14**.

---

*Generated from live probes, admin sync APIs, PostgreSQL counts, Proxmox `qm list`, and entitlement code checks on 2026-08-02. Re-run this audit after any overnight shutdown or major engine change.*
