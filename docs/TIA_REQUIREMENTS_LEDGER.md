# TIA requirements and evidence ledger

Policy: reconcile claims against live code and runtime. Statuses: `not started` · `implementing` · `verified` · `failed` · `blocked`.

Distinguish **implemented** (code present), **deployed** (running on :3443), and **behaviorally verified** (observed against UI/API).

Last updated: 2026-10-30T20:12Z (workers+TLS follow-up after `2058d77`).

## Deployed baseline (observed)

| Item | Value |
|---|---|
| Git | `2058d77` + pending commit for workers/TLS/fixture |
| SOC UI | https://192.168.0.201:3443 |
| Backend health | `tia_workers: 3` (self-heal on `/health`) |
| Admin :3000 / Customer :3001 | unchanged (targeted backend/soc only) |
| SOC agent | **HTTPS** `https://192.168.0.228:8443/health` → 200, Cursor available; CA pinned via `SOC_AGENT_CA_BUNDLE` |
| Rollback | `pre-tia-tls-workers-20261030T200932Z`, `pre-tia-brief-20261030T195652Z` |

## Requirement ledger

| ID | Requirement | Status | Location | Acceptance | Evidence |
|---|---|---|---|---|---|
| R1 | Shared typed/spoken conversation path | verified | `tia_conversation` / converse | Same intents typed+spoken | Live A–E API |
| R2 | Assessment ≠ job | verified | `tia_intents` + `_assess_case` | No job on “what happened” | Live A1 |
| R3 | Recommendation ≠ execution | verified | `recommend_next` | No job on “investigate next” | Live B |
| R4 | Explicit investigate → durable job | verified | `tia_jobs` | Job id | `b8917890…` succeeded |
| R5 | Status ≠ new job | verified | STATUS family | Status only | Live E |
| R6 | Wazoo variants | verified | `engines_in_text` | wazuh+shuffle | Live D1 |
| R7 | Engine processing layers | verified | `tia_engine_health` + MISP/Velo probes | Layers + freshness | Live ingest + probes |
| R8 | Occurrence merge / SLA | verified | `124_*`, merge | first_seen immutable | prior |
| R9 | Skip VD inventory | verified | `soc_sync` | no 23505 flood | prior |
| R10 | Utterance settle | verified (unit+fixture host) | `tiaUtterance`/`tiaEars` | lead-in holds | unit PASS; fixture allowed on `.201` with `?voice=fixture` (not physical mic) |
| R11 | Voice owner lifecycle | verified (code+deploy) | `tiaVoiceOwner`+ChatPanel | tab claim/release | deployed; physical cross-tab still operator |
| R12 | Dashboard open ack | verified | ui-ack | loaded_alert_id | Live ack |
| R13 | Ticket notes | verified | `ensure_incident_for_alert` | timeline note | `INC-TIA-ACCEPT-001` |
| R14 | Closure policy | verified (code) / activation **blocked** | `tia-closure-1` | no confidence-only close | needs reviewed FP labels |
| R15 | On-call WhatsApp delivery | **blocked** | `tia_schema` faults | delivered page | Missing: `SOC_ONCALL_WHATSAPP`, WhatsApp token/phone id, receipts, escalation target; 1 page waiting |
| R16 | TLS to SOC agent | **verified** | agent unit + `SOC_AGENT_URL=https://…` + CA pin | encrypted health | Live CA-verified health from backend; `SOC_AGENT_REQUIRE_TLS=true` |
| R17 | Dead letter | verified | `tia_jobs` | dead=0 | live |
| R18 | Physical mic F–H | **blocked** | operator | headset on :3443 | no physical access |
| R19 | Case 487ea4c4 | **blocked** | — | inspect | wiped |
| R20 | Continuous new-alert workers | **verified** | `tia_jobs` + `/health` self-heal | workers alive; no historical sweep | `/health` → `tia_workers: 3`; startup warning logs; `TIA_SWEEP_MISSING` off |

## Still blocked (exact operator inputs)

1. **R15** set in `.env` (never commit): `SOC_ONCALL_WHATSAPP`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, optional `WHATSAPP_APP_SECRET` / verify token, `SOC_ONCALL_ESCALATION_WHATSAPP`, enable `SOC_NOTIFIER_ENABLED=true`.
2. **R18** physical mic on https://192.168.0.201:3443 (optional fixture rehearsal: `?voice=fixture` — not a physical pass).
3. **R14** independently reviewed FP/malicious labels before enabling playbook auto-closure.
4. **R19** not recoverable.

## Rollback

```bash
docker tag mssp-control-backend-api:pre-tia-tls-workers-20261030T200932Z mssp-control-backend-api:latest
docker tag mssp-control-frontend-soc:pre-tia-tls-workers-20261030T200932Z mssp-control-frontend-soc:latest
docker compose up -d --no-deps --force-recreate backend-api frontend-soc
# Agent TLS unit backup on .228: /etc/systemd/system/mssp-soc-agent.service.bak.pre-tls
```
