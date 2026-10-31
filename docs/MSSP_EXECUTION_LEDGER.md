# MSSP execution ledger (persistent)

Started: 2026-10-30T21:00Z · Baseline git `a2453bf` · Branch `kb112-sovereign-edge`  
**Release baseline (preserve):** `a3df314` (docs follow-up `7973f34` / `0248cd7`) on `kb112-sovereign-edge`  
Latest deployed backend image: `sha256:ebee1adbdc3beb715f9423b30f8132efeaf1a6a41ee2786b6a5e52d9686ae2c6` (2026-10-31T06:35:17Z)  
EDR remediate ZIP sha256: `f9cf3eae0d67db6301cbcc5eb9c987003b185a19fbb3ecb6e410ff19ba9ffcb6`  
Golden snapshot: `kb-edr-key-202610311152` (VM 199) · image-release `git_commit=a2453bf`  
Golden acceptance clone: VM **219** `mssp-golden-clone-accept` (**stopped**)

Evidence classes: **code** · **deployed-runtime** · **simulated** · **real-source**

States: `NOT STARTED` | `IN PROGRESS` | `IMPLEMENTED` | `DEPLOYED` | `VERIFIED` | `FAILED` | `BLOCKED` | `DEFERRED` | `N/A`

## Safe rollback (a3df314+)

**Do not** restore `mssp-callback.key.bak.pre-edr-canary` or any SOC-sync-length callback key onto managers/endpoints.

| Layer | Procedure |
|---|---|
| App image | Tag/redeploy `mssp-control-backend-api:pre-tia-tls-workers-20261030T200932Z` (`sha256:ef21b00aa8d3…`) **only with current** `/run/secrets/edr_callback_api_key`, Wazuh CA, and `WAZUH_API_VERIFY_TLS=true`. Isolated compat (2026-10-31): health ok; dedicated EDR key → auth OK / unknown exec 404; SOC-sync header → **401**. |
| Migration 125 | **Keep** on DB if present (`file`/`telegram` notification types). Old image ignores unused types. Restore DB from 2026-10-30 backup **lacks** 125 — do not expect file-channel inserts there without applying `postgres/init/125_*.sql`. |
| EDR callbacks | If dedicated key unavailable: **leave actions unauthorized** (fail closed). Republish dedicated key via `scripts/publish_edr_ar_fleet.sh` — never re-alias SOC sync. |
| Ingress | Never restore leaked/retired token into hook URLs or `.secrets/wazuh_ingress_token`. Rotate forward only. |
| Wazuh conf | Prefer current conf; gated bak `ossec.conf.bak.gate1-*` / `gate2-ingress-*` only if needed **without** putting retired ingress token back. |
| Golden | Clone/enroll only after regenerating `machine-id` and Wazuh `client.keys`; image does **not** embed `mssp-callback.key` (keys from manager shared groups after enroll). Next intentional bake installs `kevantic-firstboot-identity` + `GOLDEN_TEMPLATE`. |

## Requirements — Gate 1 security

| ID | Requirement | Status | Evidence class | Evidence / next check |
|---|---|---|---|---|
| E1 | Production env effects | VERIFIED | deployed-runtime | `/health` `environment=production`; TLS validate-on-start fail-closed |
| E2 | Wazuh TLS verify | VERIFIED | deployed-runtime | `WAZUH_API_VERIFY_TLS=true` + CA pin; API auth OK |
| E3 | Dedicated EDR callback key | VERIFIED | real-source + deployed | Fleet central 8/8 + appliance 2/2; sync/invalid 401; canary verified; ZIP hash above |
| E3b | Cross-tenant/agent callback bind | VERIFIED | deployed-runtime | Prior canary wrong-agent 404; unknown exec 404 with valid key; sync cannot authorize |
| E4 | Sample/ITDR seed fail-closed | VERIFIED | code + runtime | `_allow_lab_sample_seed` false under production |
| E5 | Agent HTTPS / CA | VERIFIED | deployed-runtime | `SOC_AGENT_REQUIRE_TLS=true`; agent `https://192.168.0.228:8443` health ok |
| E15 | Inference sandbox / tool rights | VERIFIED | code + deployed-runtime | **Boundaries (not model refusal):** `cli_exec` sandbox suite **18 OK** (empty workspace/home, env allow-list, no unsandboxed mode, credential not on argv, oversized prompt refuse, socket not world-accessible); dossier `redacted` withholds raw events/names/addresses; research `no_grant` refuses + records; SOC agent process `secadmin` + TLS ExecStart; Ollama disabled on agent. TLS config tracked under E5 — separate from tool isolation. |
| E16 | Ingress token hygiene | VERIFIED | deployed-runtime | See token table below |
| E18 | Portal/RBAC + tenant isolation | VERIFIED | deployed-runtime | kb011 PASS; customer wrong-tenant **404**; restore drill same |
| E19 | Indexer :9200 | N/A | deployed-runtime | Remains closed (`ConnectionRefused`); analyst path = Wazuh UI/API `:443`/`:55000` |

## Requirements — Gate 2 collection / incidents

| ID | Requirement | Status | Evidence class | Evidence |
|---|---|---|---|---|
| E6a | Linux source→incident lifecycle | VERIFIED | real-source | agent 001 → appliance → `c76efe84…` / `INC-BETAWINCORP-J3FW-APP-0001` closed |
| E6b | Suricata network path | VERIFIED | real-source | Alert ingest **and** lifecycle: `4987505d…` → `INC-BETAWINCORP-J3FW-TH-0001` assign/comment/**closed** (2026-10-31) |
| E6c | Windows collection→routing | VERIFIED | real-source (authorized channel) | Agent **006** `WIN-BL72S84GDTF` Active, group `tenant_ALPHAWINCORP_6VS2`. Acceptance used **transport-only** JSON from live archive with `rule.level=10` + acceptance groups — **no** Wazuh manager/local_rules change. Alert `22da2daa…` → `INC-ALPHAWINCORP-6VS2-TH-0005` closed. SSH not used / not required. |
| E6c-ssh | Windows SSH access | BLOCKED | — | `192.168.0.214` SSH denied — **not** acceptance criteria |
| E6c-cfg | Windows 92032 / 92205 config honesty | VERIFIED | real-source + code | **92032 L10:** temporary acceptance elevation **only in the POSTed ingress sample** (archive replay). Not production rule tuning; not left on the manager. **92205 / PSScriptPolicyTest:** `is_known_noise_file_drop` matches path substring `__PSScriptPolicyTest_` (any rule id). Effect: `create_incident=False` → alert stored as `false_positive` (`82434ed2…`); **does not** close an existing incident; suppresses auto-incident only. Focused matrix 2026-10-31: noise path True; 92032 cmd / `payload.exe` False. |
| E6d | Zeek processing | PARTIAL | real-source | Zeek container processing `conn`/`dns`/`notice`; Wazuh rules **110101** fire from `notice.log`. **No** `security_alerts` Zeek rows in CP (health notices below incident ingress usefulness / not mapped as SOC queue items). |
| E6e | Human analyst path w/o TIA | VERIFIED | deployed-runtime | Admin assign/comment/close on Suricata + Windows incidents |
| E17 | Appliance ingress | VERIFIED | deployed-runtime | `custom-mssp-ingress` present on `.226` |

## Requirements — Gate 3 escalation / recovery

| ID | Requirement | Status | Evidence class | Evidence |
|---|---|---|---|---|
| E7 | Notification pipeline (local) | VERIFIED | deployed-runtime | file sent; webhook failed@4; WhatsApp queued missing creds; ack=harness |
| E7b | Real WhatsApp/human ack | BLOCKED | — | Missing provider token/phone + authorized recipient |
| E8a | Isolated DB restore | VERIFIED | deployed-runtime | Backup `2026-10-30_143106Z` → 3 tenants / 524 alerts / 313 incidents; live untouched |
| E8b | App recovery on restored DB | VERIFIED | deployed-runtime | Isolated API `:18000` + dedicated Redis; auth admin/customer/viewer; tenant 404; incidents/reports readable; notifier/workers off; **DB restore time ~1–6s** (prior) vs **app recovery login/workflows ~0.4s** after API up |
| E20 | Durable jobs / worker recovery | VERIFIED | code (isolated) + deployed-runtime | **Keep** read-only stability as its own result: 45.3s / 88 turns / `jobs_delta=0` / errs=0 / `tia_workers: 3`. **Active job recovery (this pass):** isolated Docker PG+Redis + current backend image — `CrashRecoveryTests` (mid-analysis reclaim; lost-lease cannot complete/fail new owner — job `9c124449-8e44-4347-8047-d885702444d8`; graceful shutdown returns work without spending attempt) + `TicketNoteTests` lease expiry no duplicate note — job `e4cdfab5-259e-4494-b528-093e1c38fa3a`. Transitions: running→lease expire→`recover_expired`→reclaim/idempotent ignore. Shared live worker fleet **not** interrupted. Log: `/tmp/e20_job_recovery.log` (OK, Ran 4). |
| E21 | Bounded stability | VERIFIED | deployed-runtime | Above 45.3s proof — **not** a 24/7 proof |

## Requirements — Gate 4 ops

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| E9 | Ownership age visibility | VERIFIED | `ownership_state` / `age_hours` on triage lists |
| E10 | Ops scope draft | IMPLEMENTED | `docs/MSSP_OPS_SCOPE_DRAFT.md` |
| E22 | Offboarding / revocation | VERIFIED | Disposable lab user `525a3080-7ce1-4493-a83e-5b213a229bd1` (`e22.dispose.a3eaea43@lab.local`, `customer_viewer`, ALPHA): login/me **200** while active → PATCH `inactive` → login/me/dashboard **403**; owner `platform.admin` me **200**; other-tenant customer login **200**. JWT checked via `status≠active` on each protected request (not N/A). User left **inactive**. |

## Requirements — Gate 5 TIA

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| E12 | Typed greetings/engines/customers | VERIFIED | Prior + re-verified intents; `jobs_delta=0` |
| E12b | Injection / malicious instructions | VERIFIED | **Routing vs sandbox split:** prior typed canary classified `other` / converse `unrecognised` (command routing — never reached investigation/model tool path). Investigation-path boundaries separately: redacted dossier + research no-grant (E15). Dummy secrets not echoed. |
| E12c | Voice utterance/owner lifecycle (automated) | VERIFIED (unit/fixture) | `tiaVoiceOwner` / utterance tests + greeting pytest; physical mic **BLOCKED** separately |
| E13 | Autonomous closure | BLOCKED | Policy `tia-closure-1` |
| E14 | Physical microphone | BLOCKED | Operator |

## Golden first-boot identity

| Check | Status | Evidence |
|---|---|---|
| Mechanism in repo | IMPLEMENTED | `kevantic-appliance/scripts/kevantic-firstboot-identity.sh` + `systemd/kevantic-firstboot-identity.service`; bake installs unit + touches `GOLDEN_TEMPLATE` |
| Unique identity before enroll | VERIFIED | Clone 219 offline: old `af934305…` → new `e2cf43c886364afabbc4bbbba5f02475` (≠ gold); `GOLDEN_TEMPLATE` removed; `identity-initialized` written |
| Fresh Wazuh keys | VERIFIED | `CLIENT_KEYS_BYTES=0`; shared `mssp-callback.key` absent (`NO_CALLBACK_FILES`) — reuses prior SMBIOS/key-file inspect |
| Subsequent boot preserves identity | VERIFIED | Re-run with marker gone: `IDENTITY_PRESERVED=yes` (`e2cf43c8…` unchanged) |
| Live enroll → intended tenant group | DEFERRED | Clone had no usable network this pass; left **stopped** to avoid dual live managers. Prerequisites for enroll proven; live enroll waits next intentional clone boot + register |
| Golden VM 199 image has unit yet | DEFERRED | Gold disk still lacks script (`gold199_no_firstboot_script`); ships on **next intentional bake** — no rebake solely for git label / no fleet republish this pass |
| Clone final state | — | VM **219 stopped**; machine-id unique; keys empty; no callback secret |

## Adapter acceptance rows

| Adapter | Supported function (actual) | Status | Evidence |
|---|---|---|---|
| Wazuh | Detect/ingest via API TLS + instant ingress; agent inventory | VERIFIED | Engine health auth/api ok; Linux/Windows/Suricata paths |
| Appliance ingress | Edge manager → CP hook | VERIFIED | Linux E6a depends on `.226` ingress |
| Suricata | NDR eve → Wazuh → CP alerts/incidents | VERIFIED | E6b full lifecycle |
| Zeek | Network logs + notice→Wazuh rules | PARTIAL | Manager processing yes; CP SOC rows no (health notices ≠ incidents) |
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

## Bounded completion pass (2026-10-31 ~13:15 IST)

| Item | How satisfied | Defect repaired? |
|---|---|---|
| E20 active job recovery | **Executed** isolated CrashRecovery + TicketNote tests (existing health/45.3s kept separate) | No product defect — evidence gap closed |
| E15 / E12b | **Existing** cli_exec + agent TLS; **executed** dossier/research units + live classify=`other` (routing honesty) | No OS/tool defect found; over-claim of canary corrected in ledger |
| Golden first-boot | **Implemented** identity unit + bake wiring; **executed** offline proof on clone 219 | Missing init mechanism → added; live enroll + gold 199 bake **DEFERRED** |
| E22 offboarding | **Executed** disposable user drill on live CP | No defect — JWT+status revocation works |
| Windows 92032/92205 | **Existing** lifecycle + noise code; **executed** noise matrix; clarified transport-only L10 | No unintended global rule to remove |
| Deploy | Skipped — no control-plane code/config change this pass | — |

**Not claimed complete:** real paging, staffing, physical mic, autonomous-closure activation. Adapter depth (Zeek CP rows, hunts, enrichment, deeper vuln scans) remains in adapter backlog above.

## Journal (continuation)

- 2026-10-31 PM: Safe rollback rewritten; restore→app recovery on `:18000`; Windows 006→ALPHA incident; Suricata lifecycle closed; Zeek manager processing evidenced; golden clone offline inspect; stability 88 turns; injection canary; adapter matrix; token 200/422 reconciled.
- 2026-10-31 ~13:15 IST: Bounded gap pass — E20 lease recovery jobs `9c124449…` / `e4cdfab5…`; E15/E12b boundary honesty; firstboot identity on 219; E22 disposable revoke; Windows config clarification; ledger updated. No fleet republish / no full retest / no backup rebuild.
