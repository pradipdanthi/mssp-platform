# KB-092 — AI Alert Analysis Worker (Planning)

**Status:** PLAN ONLY — awaiting user approval before implementation  
**Date:** 2026-08-04  
**Brand context:** Supports Junexis “AI-ready” marketing with honest, live plain-English summaries  
**Legal entity:** Cicilia Consultancy  

---

## 1. Why this exists

The control plane already has:

- DB columns on `security_alerts` for AI-named fields
- Customer/admin APIs that expose plain-English summary, business impact, recommended action, likely attack type
- **KB-091** rule-based synthesis (templates) when those fields are empty

What is **missing**: a real LLM worker that rewrites alert noise into high-quality customer language.

Without this worker, website claims must stay at **“AI-ready”**. With MVP live, we can honestly say **“AI-assisted plain-English alerts”** (still not “AI stops every breach”).

---

## 2. Current state (source of truth)

| Piece | State |
|---|---|
| Schema (`ai_plain_summary`, `ai_business_impact`, `ai_recommended_action`, `ai_likely_attack_type`, `ai_technical_summary`, `ai_false_positive_score`) | Present since core schema |
| Customer API remap (`summary`, `business_impact`, …) | Live |
| KB-091 `soc_alert_synthesis.py` | Live template fallback |
| LLM worker / OpenAI / Anthropic / Ollama in production path | **Not present** |
| Celery / RQ | Not used |
| Redis | Live (`mssp-redis`) |
| Existing background pattern | `shuffle_retry_queue.py` daemon thread inside API |
| Paused-work rule | Listed AI workers as optional until requested — **this KB is that request** |

**Weakest customer field today:** `ai_plain_summary` often stays generic (“SOC is reviewing: …”) unless an analyst edits it.

---

## 3. Goal (MVP)

Build an **AI alert analysis worker** that:

1. Picks up new/updated high-priority alerts from a Redis queue  
2. Calls a configured LLM provider (cloud or local OpenAI-compatible endpoint)  
3. Writes **only empty** customer-safe fields (never overwrites SOC edits)  
4. Leaves KB-091 templates as the floor when AI is off or fails  
5. Never auto-publishes to customers (`customer_visible` stays SOC-controlled)

---

## 4. Non-goals (MVP)

- Claiming fully autonomous “AI-native breach prevention” like Falcon Charlotte  
- Auto-setting `customer_visible = true` from model output  
- Filling `ai_false_positive_score` (Phase 2)  
- Replacing TheHive / Shuffle / containment logic  
- Training a custom model  
- Notification WhatsApp worker (still separate paused item)

---

## 5. Architecture (fits this repo)

Reuse the **Shuffle retry queue** pattern — no Celery, no new broker.

```
Alert ingest / SOC sync / EDR enrich
        │
        ▼
  RPUSH mssp:ai:alert_analysis  { alert_id, tenant_id }
        │
        ▼
  Worker (daemon thread in backend-api for MVP)
        │
        ├─ LOAD alert WHERE id AND tenant_id
        ├─ REDACT secrets / minimize raw_event for prompt
        ├─ CALL provider (if AI_ALERT_ENABLED=true)
        └─ UPDATE COALESCE empty columns only
              ai_plain_summary
              ai_business_impact      (optional if still template-empty)
              ai_recommended_action
              ai_likely_attack_type
```

**Precedence (highest wins):**  
SOC/admin PATCH → AI worker fill → KB-091 synthesis → generic sync stub  

**Phase 2 (optional):** separate Compose service `ai-alert-worker` same image, different command — isolates LLM latency from API.

---

## 6. Provider & config (no secrets in git)

Feature flag **off by default**.

Proposed env names (values only in `.env` / Hostinger secrets — never committed):

| Variable | Purpose |
|---|---|
| `AI_ALERT_ENABLED` | `true` / `false` (default false) |
| `AI_ALERT_PROVIDER` | `openai_compatible` |
| `AI_ALERT_BASE_URL` | API base (OpenAI, Azure, Groq, local Ollama, etc.) |
| `AI_ALERT_API_KEY` | Secret |
| `AI_ALERT_MODEL` | Model id |
| `AI_ALERT_QUEUE_KEY` | Default `mssp:ai:alert_analysis` |
| `AI_ALERT_MIN_SEVERITY` | Default `high` (MVP cost control) |
| `AI_ALERT_TIMEOUT_SECONDS` | Default `30` |

Compose: add env passthrough to `backend-api` **only with explicit approval** (protected file).

---

## 7. Security & tenant rules

- Queue payload = `{alert_id, tenant_id}` only; always reload from DB  
- Updates: `WHERE id = %s AND tenant_id = %s`  
- Prompt redaction: strip passwords, tokens, appliance keys; truncate raw JSON  
- Never put other tenants’ data in a prompt  
- Never expose `ai_technical_summary` or model chain-of-thought to `/customer`  
- Fail closed: on LLM error, keep synthesis / existing text; log server-side  
- Do not invent engine brand names in customer-facing AI text (use capability labels)

---

## 8. Implementation phases

### Phase A — MVP (this KB after approval)

1. `ai_alert_queue.py` — enqueue / BLPOP / retry (clone shuffle pattern)  
2. `ai_alert_analysis.py` — prompt builder, provider client, COALESCE persist  
3. Hook enqueue from alert create/enrich paths (Wazuh/SOC/EDR) for severity ≥ threshold  
4. Start worker from `main.py` when `AI_ALERT_ENABLED=true`  
5. Docs + `scripts/kb092_validate_ai_alert_analysis_worker.sh`  
6. Admin UI microcopy: “AI-assisted” vs “rule-driven” when field source differs (optional small note)

### Phase B — Hardening

- Dedicated Compose worker service  
- Metrics: success/fail/cost counters  
- Backfill job for recent empty summaries  
- Optional human-approve-before-visible workflow  

### Phase C — Marketing unlock

- Junexis website: upgrade “AI-ready” → “AI-assisted plain-English alerts” **only after** live demo proof on a tenant  
- Demo script: ingest alert → worker fills summary → customer portal shows it  

---

## 9. Files (expected)

| Action | Path |
|---|---|
| Create | `backend-api/app/services/ai_alert_queue.py` |
| Create | `backend-api/app/services/ai_alert_analysis.py` |
| Create | `docs/KB092_AI_ALERT_ANALYSIS_WORKER.md` (this plan → completion notes) |
| Create | `scripts/kb092_validate_ai_alert_analysis_worker.sh` |
| Edit | `backend-api/app/main.py` (start worker if flagged) |
| Edit | ingest/enrich services (enqueue) |
| Edit | `backend-api/requirements.txt` only if needed (prefer stdlib `urllib` or existing `httpx`) |
| Edit | `docker-compose.yml` **only if approved** (env passthrough) |
| Do not touch | `postgres/init/` (columns exist), customer API response shape |

---

## 10. Validation (must PASS before commit)

1. Flag **off** → no outbound LLM; KB-091 still works  
2. Flag **on** + mock provider → empty `ai_plain_summary` gets filled; non-empty SOC text untouched  
3. Wrong-tenant update impossible  
4. Customer API still omits forbidden fields; remapped keys present  
5. Script: `./scripts/kb092_validate_ai_alert_analysis_worker.sh` → PASS  

---

## 11. Effort & dependencies

| Item | Estimate |
|---|---|
| Phase A code + validator | ~1 focused build session |
| User must provide | LLM endpoint + API key in `.env` (you paste; agent never prints secrets) |
| Compose change | Requires your explicit OK |
| Cost control | MVP defaults to high/critical only |

---

## 12. Approval checklist (reply with choices)

Please confirm:

1. **Approve Phase A MVP?** Yes / No  
2. **Provider preference?** OpenAI / Groq / Azure / Local Ollama / Other OpenAI-compatible  
3. **Allow `docker-compose.yml` env passthrough?** Yes / No (if No: document manual env inject only)  
4. **Enqueue severity?** `high+critical` (recommended) / `all severities`  
5. **Website copy:** keep “AI-ready” until MVP proven, then upgrade — OK?

---

**Stop here.** No runtime implementation until you approve the checklist above.
