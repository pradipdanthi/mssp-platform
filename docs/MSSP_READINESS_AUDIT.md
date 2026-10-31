# MSSP readiness audit (evidence-based)

**Audit type:** Read-only inspection — no rebuilds, deploys, migrations, credential rotation, investigation triggers, queue replays, notification sends, ticket closures, or response actions.

**Observation window:** 2026-10-30T20:27Z–20:40Z (UTC)  
**Stable checkpoint:** git `a2453bf` on branch `kb112-sovereign-edge` (working tree clean at audit start)  
**Inspector host:** VM 100 `mssp-control` (`192.168.0.201`)  
**Master verifier (code pack):** `PASSED 246 / FAILED 0 / CLOUD-READY YES` (code/portability assertions — not a live customer-service proof)

**Related prior artifacts:** `docs/TIA_REQUIREMENTS_LEDGER.md`, `docs/PENDING_BEFORE_PRODUCTION.md`, `docs/audit/END-TO-END-PLATFORM-GAP-ANALYSIS.md`, `CONTEXT.md`

---

## 1. Plain-English executive assessment

You have built a real **multi-tenant MSSP control plane** with Admin, Customer, and SOC portals; Dockerized API/DB/Redis; Wazuh + TheHive/Shuffle + Suricata/Zeek + MISP + vuln scanners + Velociraptor + appliance edge; EDR containment plumbing; encrypted DR backups to local + Google Drive; and an optional AI assistant (TIA) backed by a Cursor SOC agent over **verified HTTPS**.

**What works today as a human-operated service foundation:** staff can sign into Admin (`:3000`), see tenants/assets/alerts/incidents (when data exists), manage customers, and use engine adapters. Customer portal (`:3001`) is a separate branded surface with tenant isolation rules in code and tests. Ingest/adapters and durable investigation jobs exist. One online appliance and a small asset set are present.

**What prevents calling this a complete sellable 24/7 MDR today:**

1. **Operational empty board** — at audit time the database held **1 open alert** and **1 open incident** (synthetic TIA acceptance seed). There is no usable sample of closed production cases, multi-customer live queues, or overdue human ownership. That is a **missing verification / data-state** finding, not proof that detections cannot work.
2. **Customer paging is not deliverable** — WhatsApp/on-call recipient and provider credentials are unset; TIA notification rows sit `required` with `no_recipients_configured` / `escalation_target_not_configured`.
3. **Business packaging unknowns** — staffed hours, primary/backup on-call people, contractual SLAs, customer-approved containment authority, and unit economics were **not discoverable from code**.
4. **Production hardening gaps still open** — `APP_ENV=development`; Wazuh API TLS verify is `false` inside the API container; indexer port 9200 refused from control plane (may be intentional binding); prior gap analyses list ITDR sample-seed and shared callback-key concerns not re-proved fixed in this pass.
5. **Backup success ≠ restore proven** — last DR run **succeeded** (local + `gdrive:MSSP/MSSP_Backups/…`); this audit found **no dated restore-test PASS evidence**.

**TIA is optional assist, not the spine of the MSSP.** Human Admin workflows and `soc_sync` → Postgres incidents do not require voice or the LLM. When `SOC_AGENT_ENABLED` / deep-triage flags are on, **automated deep investigation** does call the agent; that path is additive assist/automation, not the only way to record an alert or open an incident.

**Smallest defensible launch:** a **limited, human-supervised paid pilot** for 1–2 friendly customers, business-hours coverage, written scope, manual escalation (phone/email until WhatsApp works), containment only with authenticated Admin approval — **if** you accept the P0 gaps below and validate live detection→ticket on their traffic before promising outcomes.

---

## 2. Architecture and dependency map

### 2.1 Observation checkpoint

| Layer | Observed |
|---|---|
| Git | `a2453bf` `kb112-sovereign-edge` |
| API health | `api/database/redis=ok`, `tia_workers=3` |
| Portals | Admin `:3000` 200, Customer `:3001` 200, SOC `:3443` 200 |
| Agent | `https://192.168.0.228:8443/health` → ok, Cursor available, version `2.1.0`; transport `encrypted=true`, CA pinned, `SOC_AGENT_REQUIRE_TLS=true` |
| Compose | `mssp-backend-api`, `frontend-admin`, `frontend-customer`, `frontend-soc`, `postgres:16`, `redis:7` — all Up |
| DR | Timer active; last success 2026-10-30; next 20:00 local; STATE IDLE |

### 2.2 Proxmox inventory (host `192.168.0.191`, `qm list`)

| VMID | Name | Status | Role (from inventory/docs) |
|---|---|---|---|
| 100 | mssp-control | running | Control plane (API/UI/DB/Redis) |
| 101 | wazuh-stack | running | SIEM / agents / rules |
| 102 | thehive-shuffle | running | TheHive + Shuffle (co-located) |
| 103 | yt-ai-media | stopped | Out of MSSP scope |
| 104 | windows-endpoint-lab | running | Windows agent lab |
| 105 | linux-endpoint-lab | running | Linux agent lab (docs also note prior decommission history — VM present running now) |
| 106 | suricata-sensor | running | Suricata + Zeek (co-located) |
| 108 | misp | running | Threat intel |
| 109 | greenbone | running | Greenbone CE + Nuclei/Vuls free stack |
| 110 | velociraptor | running | DFIR |
| 112 | automation | running | Ansible controller |
| 114 | junexis-appliance-mgmt | running | Appliance management edge |
| 115 | mssp-ai | running | Ollama/tier-1 AI host (per roadmap) |
| 116 | niktiar-secure-edge | running | Secure Edge |
| 117 | mssp-soc-agent | running | TIA/Cursor SOC agent |
| 120 | helper-dmz-gateway | running | DMZ helper |
| 199 | mssp-appliance-golden-build | stopped | Golden appliance image |
| 210 | junexis-appliance-lab-01 | running | Customer-style appliance lab |

**Dependency rule observed:** Customer/agent → Wazuh (101) / appliance (210→114/100) → control plane DB → Admin/Customer UIs; Shuffle/TheHive (102) for SOAR/cases; SOC agent (117) for optional deep LLM triage; scanners (109); MISP (108); Velociraptor (110).

### 2.3 Component register (summary)

| Component | Location | Purpose | Installed | Configured | Reachable | Auth/ready | Performing function | Notes |
|---|---|---|---|---|---|---|---|---|
| Control API | 100 `:8000` | System of record | Y | Y | Y | Y | Y | Health ok; `APP_ENV=development` |
| Admin UI | 100 `:3000` | Staff SOC/ops | Y | Y | Y | — | Y (homepage 200) | Login not re-probed (rate-limit safety) |
| Customer UI | 100 `:3001` | Tenant portal | Y | Y | Y | — | Y (homepage 200) | |
| SOC UI | 100 `:3443` | TIA console | Y | Y | Y | — | Y (homepage 200) | Voice physical unproven |
| Postgres/Redis | 100 compose | Data/queue | Y | Y | Y | Y | Y | |
| Wazuh API | 101 `:55000` | Detection engine | Y | secrets present | TCP ok | credentials on disk | **Partial** | Live alert volume at audit = 1 row; indexer `:9200` refused from CP |
| TheHive | 102 `:9000` | Alternate case UI | Y | password file | HTTP status 200 | status JSON ok | **Unknown as SoR** | Product SoR is MSSP incidents; TheHive sync not verified this audit |
| Shuffle | 102 `:3001` | SOAR webhooks | Y | webhook secret file | health JSON ok | webhook-only auth model | **Partial** | Health says workflows can run; no live case chain sampled |
| Suricata/Zeek | 106 | NDR | Y | documented | SSH TCP ok | — | **Insufficient live alerts** | Prior docs claim ingest proof; DB empty of suricata/zeek rows now |
| MISP | 108 | TI | Y | API key | health ok | configured | Bridge healthy | Not same as customer TI product completeness |
| Greenbone/Nuclei/Vuls | 109 | Vuln | Y | keys present | SSH TCP | — | Not re-scanned this audit | |
| Velociraptor | 110 | DFIR | Y | bridge key | bridge health ok | configured | Bridge healthy | Hunt success per tenant not sampled |
| Appliance mgmt | 114 `:8000` | Edge channel | Y | — | TCP ok | — | Appliance online=1 | |
| SOC agent | 117 `:8443` | Cursor LLM | Y | TLS+CA | HTTPS health ok | Cursor available | Ready for calls | Optional path |
| DR backup | 100→Drive | Continuity | Y | timer | last success | — | Backup Y / **restore UNKNOWN** | |

---

## 3. Capability matrix

Legend: **PASS** / **PARTIAL** / **FAIL** / **UNKNOWN** / **N/A** — with evidence at observation time; inspected build `a2453bf` unless noted.

| Capability | State | Evidence | Gaps / type |
|---|---|---|---|
| Customer onboarding (tenants/users/entitlements) | PARTIAL | Code+KB-075; 3 tenants, 7 active users in DB | Commercial onboarding runbook/staffing UNKNOWN (missing process) |
| Offboarding / access revocation | PARTIAL | User status model + audit logs (207 in 7d) | End-to-end offboarding drill not evidenced (missing verification) |
| Asset inventory | PARTIAL | 4 protected_assets; 1 online appliance | Fleet coverage thin (data-state / missing verification) |
| Agent deployment (Wazuh/Windows/Linux/appliance) | PARTIAL | Lab endpoints VMs 104/105 running; golden 199; packages in repo | Production customer enroll volume not evidenced |
| Endpoint / server monitoring | PARTIAL | Wazuh stack reachable; mid-layer/EDR docs+tags exist | Almost no current alert corpus (data-state) |
| Network monitoring (Suricata/Zeek) | PARTIAL | VM 106 up; prior re-prove in PENDING doc | No current NDR rows in `security_alerts` |
| Identity / email / cloud monitoring | PARTIAL/UNKNOWN | ITDR code exists; Graph live test deferred (PENDING) | Prior audit: sample seed risk if Graph empty (confirmed defect risk in older analysis — not re-exercised) |
| Log collection / search / retention | PARTIAL | Wazuh/OpenSearch expected on 101; CP indexer port closed | Retention SLAs / search UX for analysts not measured here |
| Detection / correlation / noise control | PARTIAL | Rules/merge/VD-skip in code (`806dc97` lineage) | Effectiveness needs live multi-day corpus (missing verification) |
| Analyst investigation (human) | PARTIAL | Admin APIs/UI; incident+timeline model | Only 1 open unassigned incident; no closed-case sample |
| Ticket SoR | PASS (MSSP) | `incidents` + `incident_timeline`; TIA note on `INC-TIA-ACCEPT-001` | TheHive update **not** claimed/verified (N/A as SoR) |
| Escalation / customer notification | FAIL (delivery) | `tia_notifications` state=`required`; blocked_reason recipient/escalation; WhatsApp env EMPTY | Missing configuration |
| Response approvals / host isolate | PARTIAL | KB-104 isolate path documented; approval-gated in TIA policy | Live isolate proof not re-run this audit (missing verification) |
| Automated response | PARTIAL | EDR AR / Shuffle hooks in product | Depends on approvals + live agents |
| Vulnerability / patch services | PARTIAL | VM 109 stack; adapters | Patch **deployment** not evidenced (visibility ≠ management) |
| Customer reports | PARTIAL | Customer report APIs/UI through KB-031+ | Fresh published reports not sampled |
| RBAC / portal separation | PARTIAL→PASS code | Portal login roles; kb011 script present; tenant tests exist | Live login matrix not re-run (avoid rate-limit); code+tests strong |
| Tenant isolation (server) | PARTIAL | RLS tests `test_db_rls.py`; converse cross-tenant tests | Production penetration-style proof not in this audit |
| Audit trails | PARTIAL | `audit_logs` activity last 7d | Completeness vs all privileged actions UNKNOWN |
| TIA conversation assist | PARTIAL | Ledger R1–R13 verified API; R18 physical blocked | Voice not launch-blocking for human MSSP |
| TIA/LLM deep investigation | PARTIAL | Job succeeded earlier; workers=3; agent TLS ok | Optional; depends on Cursor subscription/runtime |
| Backups | PARTIAL | Last backup success; Drive path recorded | Restore test UNKNOWN (missing verification) |
| Self-monitoring of MSSP | PARTIAL | Health, TIA readiness faults, engine health module | Silent collection failure detection not fully proven with empty board |

---

## 4. Representative end-to-end case traces

**Sample limitation (critical):** At audit time `security_alerts` total = **1**, `incidents` total = **1**, closed incidents = **0**. Historical multi-customer production traces were **not available** in DB (likely cleared earlier). The following is the only complete recent chain present.

### Trace A — Synthetic acceptance case (available)

| Stage | Evidence |
|---|---|
| Source | Synthetic seed title “TIA acceptance: suspicious PowerShell…”; `source_tool=wazuh`; tenant `BETAWINCORP-J3FW`; alert `803ebcc6-…`; created `2026-10-30T19:45:23Z` |
| Collection/detection | Record present in CP DB; **not** proven from live endpoint telemetry in this audit |
| Triage | Status still `new`; severity `critical` (label, not independently validated threat) |
| Ticket | `INC-TIA-ACCEPT-001` opened `20:00:08Z`; **unassigned** |
| Investigation | TIA job `b8917890-…` (prior session) **succeeded**; timeline “TIA investigation note” at `20:00:14Z`; disposition was model `inconclusive` / suspicious (ledger) |
| Escalation/page | **Not delivered** — platform paging blocked (no recipients) |
| Response | **None** observed; no containment execution in timeline |
| Disposition/customer report | Incident still `open`; no closed/resolved row; no customer notification events in 30d |

**Missing transitions:** human assignment, customer notify, closure with rationale, TheHive case id sync.

### Trace B — Closed case

**INSUFFICIENT EVIDENCE** — zero closed/resolved incidents in DB at audit time.

### Trace C — Unresolved/overdue human ownership

Only open incident is unassigned since open; with a one-item board this is weak evidence of backlog process failure, but it **does** show ownership is not automatic.

### Collection freshness signals

| Signal | Value |
|---|---|
| Open alerts | 1 |
| Dead TIA jobs | 0 |
| Notification events 30d | 0 |
| TIA pages waiting | 2 (`required`) |
| Appliance online | 1 |
| Wazuh indexer from CP | connection refused `:9200` |

---

## 5. Separate readiness verdicts

### A. Demonstrations and customer discovery — **READY WITH EXPLICIT LIMITS**

Can show Admin/Customer/SOC portals, architecture story, appliance/golden narrative, engine VMs up, AI assist demo.  
**Limits:** Do not imply live multi-tenant alert flood or 24/7 paging. Board is nearly empty.  
**Blockers:** None for a scripted demo.  
**Evidence to improve:** Seed or wait for real multi-source alerts; record a demo script with honest labels.

### B. Limited human-supervised paid pilot — **READY WITH EXPLICIT LIMITS**

**Offerable if:** written scope + hours; named human owners; phone/email escalation (WhatsApp not ready); containment only via Admin approval; customer accepts `APP_ENV`/TLS hardening plan; live detection proven on their agents before go-live week.  
**Blockers for “set and forget” pilot:** paging delivery FAIL; restore unproven; empty historical case proof.  
**Must not use “pilot” to skip:** tenant isolation expectations, approval for disruptive actions, clear who owns incidents.

### C. Recurring production service (defined scope & hours) — **NOT READY**

Needs: stable live detection corpus, assigned on-call roster with **delivered** pages, restore-tested backups, production env flags (`APP_ENV=production`, Wazuh TLS verify), documented hours/SLAs, at least one closed-case quality sample set.  
**Confirmed blockers:** notification config; business hours/SLA docs unknown; restore UNKNOWN; production TLS verify off.

### D. Full 24/7 monitoring + investigation + escalation — **NOT READY**

No evidence of staffed 24/7 roster, backup on-call, or measured response clocks. Automated collection ≠ 24/7 human investigation.

### E. Optional TIA assistance and autonomous actions — **READY WITH EXPLICIT LIMITS** (assist) / **NOT READY** (autonomous closure/response)

- **Assist:** Conversation tools + durable investigate jobs + HTTPS agent — usable for analysts; voice physical incomplete.  
- **Autonomous closure:** policy shadow/`tia-closure-1`; activation blocked without reviewed labels.  
- **Disruptive response by voice:** correctly refused; Admin approval required.  
**Essential backend dependency on LLM?** **No** for ingest→DB→human Admin ticket path. **Yes (optional)** for deep automated investigation when agent/deep-triage flags enabled.

---

## 6. What you can truthfully sell today — and what you cannot

### Can substantiate (with limits)

- Multi-tenant MSSP **control plane** (Admin + Customer portals) on your infrastructure.
- Integration adapters for Wazuh, TheHive/Shuffle, NDR sensor VM, MISP/Velo bridges, vuln free stack, appliances.
- Human-led monitoring/triage **during staffed hours you actually cover** (hours themselves still a business input).
- Optional AI-assisted investigation notes into **MSSP incidents** (not proven TheHive write-back).
- Encrypted scheduled backups to local + Google Drive (**backup succeeded**; restore not proven).

### Cannot yet substantiate

- “24/7 managed detection and response with guaranteed paging.”
- “We always investigate and close every critical within X minutes” (no SLA measurement evidence).
- “Fully autonomous AI SOC.”
- “TheHive is kept in sync as the ticket of record.”
- “Backups are restore-tested / DR proven.”
- “WhatsApp/on-call escalation works.”
- Broad claims of continuous live detection across many customers (board empty).
- Certifications, legal compliance posture, or profitability (not in repo).

---

## 7. Prioritized enhancements

### P0 — before applicable launch (pilot or production)

| # | Gap type | Observed gap | Customer impact | Correction | Dependencies | Effort (rough) | Acceptance evidence |
|---|---|---|---|---|---|---|---|
| P0-1 | Missing configuration | WhatsApp/on-call unset; pages `required` | Criticals may never wake a human | Configure recipient + provider; enable notifier; prove delivery+ack | Meta business account; phone numbers | S–M | Delivered page with provider id; ack path tested |
| P0-2 | Missing verification | Near-empty alert/incident corpus | Cannot prove E2E service | Controlled live detection from lab agents → CP ticket **without** claiming historical wipe recovery | Lab endpoints 104/105/210 | S | ≥N alerts across ≥2 sources with timestamps |
| P0-3 | Missing verification | No restore-test evidence | Data-loss risk | Scheduled restore drill to isolated target | Backup passphrase; downtime window | M | Dated RESTORE_PASS artifact |
| P0-4 | Missing configuration / defect risk | `APP_ENV=development`; `WAZUH_API_VERIFY_TLS=false` | Weaker production posture | Move to production env + verified TLS for Wazuh API | Valid CA/trust | S | Container env shows production + verify true; health green |
| P0-5 | Missing operational process | No documented staffed hours / named on-call | Unclear responsibility | One-page ops roster + escalation tree | People | S | Signed roster; test escalate |

### P1 — reliability / delivery / capacity

| # | Gap | Impact | Correction | Effort |
|---|---|---|---|---|
| P1-1 | TheHive sync unverified | Dual-ticket confusion | Decide SoR (recommend MSSP incidents); if TheHive needed, verify write + id map | M |
| P1-2 | Indexer not reachable from CP `:9200` | Search/ops friction | Document intended access path or open controlled route | S–M |
| P1-3 | Revisit ITDR sample-seed & shared EDR callback key (prior audit) | Integrity / spoof risk | Confirm fixes or remediate | M |
| P1-4 | Assignment/ownership SLAs | Unowned criticals | Queue rules + dashboards for unassigned age | M |
| P1-5 | Capacity/storage growth | Silent disk full | Monitor backup+DB growth; alerts on CP | S |

### P2 — efficiency / experience

| # | Gap | Correction |
|---|---|---|
| P2-1 | Customer reporting cadence | Automate monthly publish checklist |
| P2-2 | Noise/tuning playbooks | Document merge/VD-skip operational use |
| P2-3 | Cloud cutover pack | Keep `verify_platform_state --release` green; inventory production.yml when ready |

### Optional TIA improvements (do not block human MSSP)

| # | Gap | Correction |
|---|---|---|
| TIA-1 | Physical mic acceptance (R18) | Operator headset tests on `:3443` |
| TIA-2 | Closure activation (R14) | Reviewed FP/malicious label set |
| TIA-3 | Voice UX polish | Already partially shipped; continue from ledger |
| TIA-4 | Autonomous actions | Keep approval-gated; no confidence-only close |

**Prefer improving existing components** (notifier config, env hardening, restore drill, live detection proof) over new product platforms.

---

## 8. Business information not discoverable from the platform

1. Actual staffed hours and who is primary/backup on-call today.  
2. Customer contracts, MSA/DPA terms, and promised SLAs.  
3. Customer-approved containment/remediation authority matrix.  
4. Fully loaded monthly cost (people, power, licenses, Cursor, Drive, bandwidth).  
5. Target price / margin / how many paid customers are intended for year one.  
6. Certifications (ISO, SOC2, etc.) status.  
7. Whether a formal restore test was ever completed (no PASS artifact found).  
8. Legal entity commitments for “production” vs lab naming (code still `APP_ENV=development`).

---

## Security & continuity snapshot (audit §5)

| Theme | Finding | Class |
|---|---|---|
| Tenant isolation | Strong code/tests; not re-penetrated live | Missing verification (live) |
| Secrets | `.secrets/` files present; not echoed | Config review PASS-ish |
| Agent transport | HTTPS + pinned CA + require TLS | Confirmed fixed vs earlier HTTP concern |
| Paging | Undeliverable | Confirmed missing configuration |
| Dead letters | `tia_jobs` dead=0 | OK at observation |
| Stale sources | Empty board / thin telemetry | Missing verification / data-state |
| Engine integrations | Reachable; function partially proven | Partial |
| Ticket sync TheHive | Not verified | Missing verification |
| Backups | Success recorded | Restore missing verification |
| SPOF | Single Proxmox cluster / single CP VM | Architecture risk (known) |
| LLM data egress | Agent on `.228` with Cursor — customer evidence may leave host when deep investigate runs | Process/policy UNKNOWN |

---

## Human path without TIA / LLM (dependency analysis)

| Workflow | Requires TIA voice? | Requires LLM/agent? | Evidence |
|---|---|---|---|
| Alert land in Postgres via soc_sync / ingest | No | No | `soc_sync_service` incident create path |
| Analyst views/triages in Admin UI | No | No | Admin frontend + APIs |
| Incident notes by human | No | No | `incident_timeline` model |
| Customer portal view | No | No | Customer APIs; no `/admin` |
| Host isolate | No | No | Approval-gated Admin/EDR path (TIA refuses disruptive voice) |
| Deep automated investigation note | No voice | **Yes if flags on** | `ai_deep_triage` / `soc_agent_client` |
| Conversational SOC assist | Yes for voice UX | Often for open questions | SOC `:3443` |

**Conclusion:** Essential human MSSP operation does **not** depend on TIA voice. Optional automation quality depends on agent/LLM when those flags are enabled.

---

## Final statement

**Smallest defensible service:** human-supervised, limited-scope, business-hours MSSP pilot on this control plane — with honest limits, manual escalation until WhatsApp works, and live detection proof before charging for outcomes.

**What blocks the next level (recurring / 24/7):** delivered on-call paging, restore-tested DR, production hardening flags, evidenced multi-case operations, and documented staffed coverage.

**Three most valuable next actions**

1. Configure and **prove** on-call page delivery (P0-1).  
2. Run a **restore drill** and file a dated PASS (P0-3).  
3. Generate a **live detection→MSSP incident** sample from lab endpoints and assign a human owner (P0-2 + ownership).

---

*End of audit. No production mutations were performed to obtain this report.*
