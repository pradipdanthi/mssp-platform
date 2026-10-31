# MSSP execution ledger (persistent)

Started: 2026-10-30T21:00Z · Baseline git `a2453bf` · Branch `kb112-sovereign-edge`  
**Release baseline (preserve):** `a3df314` (docs follow-up `7973f34`) on `kb112-sovereign-edge`  
Latest deployed backend image: `sha256:ebee1adbdc3beb715f9423b30f8132efeaf1a6a41ee2786b6a5e52d9686ae2c6` (2026-10-31T06:35:17Z)  
EDR remediate ZIP sha256: `f9cf3eae0d67db6301cbcc5eb9c987003b185a19fbb3ecb6e410ff19ba9ffcb6`  
Golden snapshot: `kb-edr-key-202610311152` (VM 199) · image-release `git_commit=a2453bf`  
Golden clone inspect: VM **219** `mssp-golden-clone-accept` (**stopped**, no live enroll)

Evidence classes: **code** · **deployed-runtime** · **simulated** · **real-source**

States: `NOT STARTED` | `IN PROGRESS` | `IMPLEMENTED` | `DEPLOYED` | `VERIFIED` | `FAILED` | `BLOCKED` | `N/A`

## Safe rollback (a3df314+)

**Do not** restore `mssp-callback.key.bak.pre-edr-canary` or any SOC-sync-length callback key onto managers/endpoints.

| Layer | Procedure |
|---|---|
| App image | Tag/redeploy `mssp-control-backend-api:pre-tia-tls-workers-20261030T200932Z` (`sha256:ef21b00aa8d3…`) **only with current** `/run/secrets/edr_callback_api_key`, Wazuh CA, and `WAZUH_API_VERIFY_TLS=true`. Isolated compat (2026-10-31): health ok; dedicated EDR key → auth OK / unknown exec 404; SOC-sync header → **401**. |
| Migration 125 | **Keep** on DB if present (`file`/`telegram` notification types). Old image ignores unused types. Restore DB from 2026-10-30 backup **lacks** 125 — do not expect file-channel inserts there without applying `postgres/init/125_*.sql`. |
| EDR callbacks | If dedicated key unavailable: **leave actions unauthorized** (fail closed). Republish dedicated key via `scripts/publish_edr_ar_fleet.sh` — never re-alias SOC sync. |
| Ingress | Never restore leaked/retired token into hook URLs or `.secrets/wazuh_ingress_token`. Rotate forward only. |
| Wazuh conf | Prefer current conf; gated bak `ossec.conf.bak.gate1-*` / `gate2-ingress-*` only if needed **without** putting retired ingress token back. |
| Golden | Clone/enroll only after regenerating `machine-id` and Wazuh `client.keys`; image does **not** embed `mssp-callback.key` (keys from manager shared groups after enroll). |

## Requirements — Gate 1 security

| ID | Requirement | Status | Evidence class | Evidence / next check |
|---|---|---|---|---|
| E1 | Production env effects | VERIFIED | deployed-runtime | `/health` `environment=production`; TLS validate-on-start fail-closed |
| E2 | Wazuh TLS verify | VERIFIED | deployed-runtime | `WAZUH_API_VERIFY_TLS=true` + CA pin; API auth OK |
| E3 | Dedicated EDR callback key | VERIFIED | real-source + deployed | Fleet central 8/8 + appliance 2/2; sync/invalid 401; canary verified; ZIP hash above |
| E3b | Cross-tenant/agent callback bind | VERIFIED | deployed-runtime | Prior canary wrong-agent 404; unknown exec 404 with valid key; sync cannot authorize |
| E4 | Sample/ITDR seed fail-closed | VERIFIED | code + runtime | `_allow_lab_sample_seed` false under production |
| E5 | Agent HTTPS / CA | VERIFIED | deployed-runtime | `SOC_AGENT_REQUIRE_TLS=true`; agent `https://192.168.0.228:8443` health ok (restarted this session) |
| E15 | Inference sandbox / tool rights | VERIFIED | deployed-runtime | SOC agent uvicorn TLS, user `secadmin`; Ollama disabled on agent; prompt-injection typed canary refused secrets/remediation |
| E16 | Ingress token hygiene | VERIFIED | deployed-runtime | See token table below |
| E18 | Portal/RBAC + tenant isolation | VERIFIED | deployed-runtime | kb011 PASS; customer wrong-tenant **404**; restore drill same |
| E19 | Indexer :9200 | N/A | deployed-runtime | Remains closed (`ConnectionRefused`); analyst path = Wazuh UI/API `:443`/`:55000` |

## Requirements — Gate 2 collection / incidents

| ID | Requirement | Status | Evidence class | Evidence |
|---|---|---|---|---|
| E6a | Linux source→incident lifecycle | VERIFIED | real-source | agent 001 → appliance → `c76efe84…` / `INC-BETAWINCORP-J3FW-APP-0001` closed |
| E6b | Suricata network path | VERIFIED | real-source | Alert ingest **and** lifecycle: `4987505d…` → `INC-BETAWINCORP-J3FW-TH-0001` assign/comment/**closed** (2026-10-31) |
| E6c | Windows collection→routing | VERIFIED | real-source (authorized channel) | Agent **006** `WIN-BL72S84GDTF` Active, group `tenant_ALPHAWINCORP_6VS2`; live archive rule 92032 elevated to L10 for CP threshold → alert `22da2daa…` → `INC-ALPHAWINCORP-6VS2-TH-0005` closed. SSH not used / not required. |
| E6c-ssh | Windows SSH access | BLOCKED | — | `192.168.0.214` SSH denied — **not** acceptance criteria |
| E6d | Zeek processing | PARTIAL | real-source | Zeek container processing `conn`/`dns`/`notice`; Wazuh rules **110101** fire from `notice.log` (20 hits in sample). **No** `security_alerts` Zeek rows in CP (health notices below incident ingress usefulness / not mapped as SOC queue items). |
| E6e | Human analyst path w/o TIA | VERIFIED | deployed-runtime | Admin assign/comment/close on Suricata + Windows incidents |
| E17 | Appliance ingress | VERIFIED | deployed-runtime | `custom-mssp-ingress` present on `.226` (aborted shell still completed insert) |

## Requirements — Gate 3 escalation / recovery

| ID | Requirement | Status | Evidence class | Evidence |
|---|---|---|---|---|
| E7 | Notification pipeline (local) | VERIFIED | deployed-runtime | file sent; webhook failed@4; WhatsApp queued missing creds; ack=harness |
| E7b | Real WhatsApp/human ack | BLOCKED | — | Missing provider token/phone + authorized recipient |
| E8a | Isolated DB restore | VERIFIED | deployed-runtime | Backup `2026-10-30_143106Z` → 3 tenants / 524 alerts / 313 incidents; live untouched |
| E8b | App recovery on restored DB | VERIFIED | deployed-runtime | Isolated API `:18000` + dedicated Redis; auth admin/customer/viewer; tenant 404; incidents/reports readable; notifier/workers off; **DB restore time ~1–6s** (prior) vs **app recovery login/workflows ~0.4s** after API up |
| E20 | Durable jobs / worker recovery | VERIFIED | deployed-runtime | `/health` `tia_workers: 3` self-heal; stability 45.3s / 88 read-only turns / `jobs_delta=0` / errs=0 |
| E21 | Bounded stability | VERIFIED | deployed-runtime | Above — **not** a 24/7 proof |

## Requirements — Gate 4 ops

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| E9 | Ownership age visibility | VERIFIED | `ownership_state` / `age_hours` on triage lists |
| E10 | Ops scope draft | IMPLEMENTED | `docs/MSSP_OPS_SCOPE_DRAFT.md` |
| E22 | Offboarding drill | N/A (parked) | Not in this acceptance window; no designated disposable lab user exercised now |

## Requirements — Gate 5 TIA

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| E12 | Typed greetings/engines/customers | VERIFIED | Prior + re-verified intents; `jobs_delta=0` |
| E12b | Injection / malicious instructions | VERIFIED | Typed canary → unrecognised / no secret echo / no remediation |
| E12c | Voice utterance/owner lifecycle (automated) | VERIFIED (unit/fixture) | `tiaVoiceOwner` / utterance tests + greeting pytest; physical mic **BLOCKED** separately |
| E13 | Autonomous closure | BLOCKED | Policy `tia-closure-1` |
| E14 | Physical microphone | BLOCKED | Operator |

## Adapter acceptance rows

| Adapter | Supported function (actual) | Status | Evidence |
|---|---|---|---|
| Wazuh | Detect/ingest via API TLS + instant ingress; agent inventory | VERIFIED | Engine health auth/api ok; Linux/Windows/Suricata paths |
| Appliance ingress | Edge manager → CP hook | VERIFIED | Linux E6a depends on `.226` ingress |
| Suricata | NDR eve → Wazuh → CP alerts/incidents | VERIFIED | E6b full lifecycle |
| Zeek | Network logs + notice→Wazuh rules | PARTIAL | Manager processing yes; CP SOC rows no |
| TheHive | Alternate case UI/API (MSSP incidents remain SoR) | VERIFIED (API health) | Engine health auth ok — **not** SoR for acceptance notes |
| Shuffle | Webhook forward from ingress | PARTIAL | `forwarded_to_shuffle:true` on Windows ingest; workflow content not re-proven |
| MISP | TI bridge health | PARTIAL | Bridge healthy; customer TI product completeness N/A |
| Velociraptor | DFIR bridge health | PARTIAL | Bridge healthy; hunt-per-tenant not sampled |
| Greenbone/Nuclei/Vuls | Vuln stack on VM 109 | PARTIAL | Reachable; no new bounded scan this window |
| SOC agent | Cursor inference over TLS | VERIFIED | Health + ExecStart TLS; not required for human MSSP path |

## Ingress token evidence (reconcile 200 vs 422)

| When (approx IST) | Purpose | Result | Stored result |
|---|---|---|---|
| 2026-10-31 ~11:57 | Token path check acceptance | **200** ingest | alert `6be38e28…` |
| 2026-10-31 ~12:00 | Probe / rotate follow-ups | mixed | alert `46f68e43…` retired title |
| 2026-10-31 ~12:40 | Auth probe unbound agent JSON | **422** tenant unresolved = **token accepted** | no alert row (expected) |
| 2026-10-31 12:45 | Windows 92205 (noise-suppressed) | **200** | `82434ed2…` status `false_positive` (no incident — known noise) |
| 2026-10-31 12:50 | Windows 92032 acceptance | **200** | `22da2daa…` + `INC-ALPHAWINCORP-6VS2-TH-0005` |
| Retired full-backup token | Negative auth | **404** | — |
| Garbage token | Negative auth | **404** | — |

## Golden clone results

| Check | Result |
|---|---|
| Full clone VM 219 | Created from 199; **stopped** after inspect (no duplicate live identity) |
| SMBIOS | Clone `e2cf43c8-…` ≠ gold `af934305-…` |
| `machine-id` | Still identical to gold until first-boot regenerate — **must regenerate before enroll** |
| `client.keys` | Empty (0 bytes) — good |
| `mssp-callback.key` in image | **Absent** (by design; empty hash) — keys from manager shared after enroll |
| CP secrets on image | Absent |
| image-release | `git_commit=a2453bf`, edr_ar `1.1.0` |
| Rebake for `a3df314` | **Not required** for live fleet (managers already have dedicated key); optional to refresh image-release label only |

## Journal (continuation)

- 2026-10-31 PM: Safe rollback rewritten; restore→app recovery on `:18000`; Windows 006→ALPHA incident; Suricata lifecycle closed; Zeek manager processing evidenced; golden clone offline inspect; stability 88 turns; injection canary; adapter matrix; token 200/422 reconciled.
