# TIA requirements and evidence ledger

Policy: reconcile claims against live code and runtime. Statuses: `not started` · `implementing` · `verified` · `failed` · `blocked`.

Distinguish **implemented** (code present), **deployed** (running on :3443), and **behaviorally verified** (observed against UI/API).

Last updated: 2026-10-30T19:58Z (brief phases 1–4 + live A–E API).

## Deployed baseline (observed)

| Item | Value |
|---|---|
| Git working tree | uncommitted TIA brief changes on `kb112-sovereign-edge` (prior baseline `806dc97`) |
| SOC UI | https://192.168.0.201:3443 — image `sha256:a17ee6a9…` started 2026-10-30T19:57:09Z |
| Backend | `mssp-backend-api` image `sha256:e1ac4454…` same start |
| Admin :3000 / Customer :3001 | **unchanged** container IDs from 11:47Z (targeted recreate only) |
| SOC agent | `http://192.168.0.228:8443/health` → 200, Cursor available, Ollama disabled |
| Seed alert | `803ebcc6-0ffe-4d3f-8960-4a92a4950717` (BETAWINCORP-J3FW, synthetic acceptance) |
| Acceptance job | `b8917890-09e8-4a9d-882d-843d1dd40c11` (operator, was `running` at last check) |
| Rollback tags | `pre-tia-brief-20261030T195652Z` (+ prior `pre-occ-merge-20261030T192612Z`) |

## Requirement ledger

| ID | Requirement | Status | Location | Acceptance | Evidence |
|---|---|---|---|---|---|
| R1 | Shared typed/spoken conversation path | verified (API) | `tia_conversation.py`, `/admin/soc-console/converse` | Same intents for typed and spoken | Live converse A–E; spoken path still uses converse after ASR |
| R2 | Assessment ≠ investigation job | verified | `tia_intents` + `_assess_case` | “What happened here?” / criticality without new job | Live A1/A2; jobs unchanged through B |
| R3 | Recommendation ≠ execution | verified | `recommend_next` before `_RE_INVESTIGATE` | “What should we investigate next?” advice only | Live B: intent=`recommendation`, job count unchanged |
| R4 | Explicit investigate creates durable job | verified | `start_investigation` / `tia_jobs` | Job id returned | Live C: job `b8917890…` |
| R5 | Status does not launch another job | verified | STATUS family | Status query only | Live E: `investigation_status`, job already from C |
| R6 | Product-name variants (Wazoo) | verified | `tia_intents.engines_in_text` | Resolves to wazuh+shuffle | Live D1 sections `## shuffle` + `## wazuh` |
| R7 | Engine processing ≠ open port | verified | `tia_engine_health`, `ingest_status`, MISP/Velo probes | Layers + telemetry freshness | Live D1 spoken: reachability ok, Wazuh ingest degraded; MISP/Velo bridge probes deployed |
| R8 | Occurrence merge + SLA clock | verified | `124_…`, `soc_alert_merge.py` | Merge keeps first_seen | Prior deploy; unchanged |
| R9 | Skip vulnerability-detector inventory | verified | `soc_sync` | No SOC rows for 23505 | Prior deploy |
| R10 | Voice settle / incomplete utterance | verified (unit) | `tiaUtterance.ts`, `tiaEars.ts` | Lead-in + pause holds | Unit: “Can you check” incomplete; hold ×2; **physical mic blocked (R18)** |
| R11 | One voice owner / mic lifecycle | verified (code+deploy) | `tiaVoiceOwner.ts` + `ChatPanel` | Second tab stops first; pagehide releases | Deployed SOC UI; **cross-tab physical not run this session** |
| R12 | Dashboard open ack | verified | converse + ui-ack | Confirm only after loaded_alert_id | Live open+ack verified=true for seed alert |
| R13 | Ticket notes on MSSP incident timeline | verified | `tia_ticket_note.ensure_incident_for_alert` → timeline | Note on incident; TheHive not claimed | Job `b8917890…` / attempt `e5107633…` note on `INC-TIA-ACCEPT-001` (verified). Missing-incident path now opens `INC-TIA-…` instead of permanent skip. TheHive not claimed. |
| R14 | Closure policy tia-closure-1 | verified (code) | `tia_closure_policy.py` | No confidence-only auto-close | Shadow; activation blocked pending reviewed labels |
| R15 | On-call / WhatsApp page delivery | blocked | readiness faults | Delivered page | WhatsApp/on-call unset |
| R16 | TLS to SOC agent | blocked | `SOC_AGENT_URL` http://…:8443 | Verified TLS | Agent serves HTTP only |
| R17 | Dead-letter backlog | verified (ops) | `tia_jobs` | dead=0 | Live count dead=0 |
| R18 | Physical mic acceptance | blocked | operator on :3443 | Real headset scenarios F–H | No physical access this session |
| R19 | Case 487ea4c4 outcome | blocked | — | Inspect without replacing | Cleared with alert wipe; not in DB |
| R20 | Continuous new-alert processing | verified (partial) | `tia_jobs` worker | Bounded new-alert; no historical sweep | Job from C entered `running`; `TIA_SWEEP_MISSING` not enabled |

## Observed failure reconciliation

| Observation | Confirmed cause | Action / result |
|---|---|---|
| “What do you think happened here?” weak | Assessment not early-wired | Live A1 → `assessment` + evidence/criticality |
| “Is this actually critical?” | Criticality tool path | Live A2 → `criticality` (read-only; no job) |
| “Wazoo and Shuffle processing” | Alias + multi-ingest | Live D1 both engines |
| “What should we investigate next?” creates job | `_RE_INVESTIGATE` before recommendation | Live B no job; unit + live |
| Mid-sentence pause submits partial | Short settle + single incomplete hold | Incomplete patterns + 2 holds; unit verified; physical pending |
| Speech after browser close | Other tab / missing release | `claimVoiceOwner` + pagehide/beforeunload; physical pending |
| Case 487ea4c4 | Gone after wipe | Remains blocked |

## Change / release manifest (this deploy)

| Change | Files | Deploy |
|---|---|---|
| Intent families + Wazoo aliases | `tia_intents.py`, `tia_conversation.py`, tests | backend-api recreated |
| MISP + Velociraptor health probes | `tia_engine_health.py` + tests | backend-api |
| Utterance hold + voice owner | `tiaUtterance.ts`, `tiaEars.ts`, `tiaVoiceOwner.ts`, `ChatPanel.tsx` | frontend-soc recreated |
| Ledger + verifier assertions | `docs/TIA_REQUIREMENTS_LEDGER.md`, `verify_platform_state.py` | docs/scripts only |

**Rollback:** `docker tag mssp-control-backend-api:pre-tia-brief-20261030T195652Z mssp-control-backend-api:latest` (same for `frontend-soc`), then `docker compose up -d --no-deps --force-recreate backend-api frontend-soc`. Do not recreate admin/customer unless intentionally rolling those images.

## Live acceptance (API, not physical mic)

| Scenario | Result | IDs |
|---|---|---|
| A assessment / criticality / unknowns | PASS intents assessment / criticality / known_unknowns | alert `803ebcc6…` |
| B recommend next | PASS no job | jobs 0→0 through B |
| C investigate | PASS job queued then running | job `b8917890…` |
| D Wazoo+Shuffle + component + back | PASS ingest + component + return_case | — |
| E status | PASS investigation_status | same job |
| F–H voice physical | BLOCKED | operator on :3443 |
| I isolation / denied | prior unit suite + customer 401/403 paths | local tests OK |
| J worker interrupt | prior local crash-recovery suite | not re-injected in prod |
| K closure labels | blocked activation | shadow policy |

## Latency sample (server telemetry, last 60m window)

| Path | n | p50_ms | p95_ms |
|---|---|---|---|
| action (tool turns) | 2 | 26.7 | 29.1 |
| navigation | 16 | 15.8 | 77.3 |
| model | 10 | 17071 | 18119 |
| status | 1 | 18.9 | 18.9 |

EOS→first-audio and physical barge-in timings: **not measured** (R18).

## External dependencies (exact)

1. Operator physical mic session on https://192.168.0.201:3443 for R18 / scenarios F–H.
2. WhatsApp / on-call recipient for R15.
3. TLS cert + HTTPS listener for agent :8443 for R16.
4. Independently reviewed FP labels before enabling auto-closure (R14).
5. Case `487ea4c4…` not recoverable (R19).
