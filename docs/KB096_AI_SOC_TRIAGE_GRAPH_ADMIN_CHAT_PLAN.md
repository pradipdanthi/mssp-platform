# KB-096 — AI SOC Triage Assist + Live Entra Graph + Admin AI Chat

**Status:** PLAN + Phase 1 scaffolding (feature-flagged)  
**Date:** 2026-08-12  
**Rule:** Do not break today’s working MDR path. Ship dark behind flags. Human SOC always finalizes.

---

## 1. Goals (what you asked for)

| # | Goal | Outcome |
|---|------|---------|
| 1 | AI SOC Agent: enrich + correlate + risk score end-to-end | Draft assist for analysts — **Human SOC finalizes** (edit, approve visibility, contain) |
| 2 | Live Entra / M365 Graph | Real identity events in ITDR (replace sample adapter when Graph creds exist) |
| 3 | Admin AI chat window | SOC analyst asks questions about tenants/alerts/incidents/IOCs in Admin portal |

---

## 2. Critical design rule — AI vs Threat Intelligence

**Threat Intelligence (catalog card #7) stays the system of record for IOCs/feeds.**

| Layer | Owner | Job |
|-------|--------|-----|
| **Threat Intel service** | MISP bridge / STIX / TAXII / alert IOC extract | Collect, store, match indicators |
| **AI SOC Triage Assist** | Ollama (local LLM) | **Consume** TI + alert context → explain correlation + draft risk narrative for humans |

AI **complements** TI — it does **not** replace the Threat Intel service or invent a second IOC database.

```
Detection → Control plane alert
              │
              ├─► Threat Intel sync/match (structured IOCs)     ← keep as-is
              │
              └─► AI Triage Assist (reads TI + related alerts)
                        │
                        ├─ enrich notes (which IOCs matched / why it matters)
                        ├─ correlate notes (related open cases / same host/user)
                        └─ risk score draft (0–100 + rationale)
                        │
                        ▼
                  Human SOC reviews → edits → customer_visible / contain
```

**Never auto-set:** `customer_visible`, isolate/kill, close incident, send customer notification.

---

## 3. Safe delivery phases

### Phase 0 — Guardrails (always on)
- Feature flags default **OFF** in Compose if unset  
- New DB columns only (additive migration)  
- No change to ingest latency (async Redis queues)  
- Validator scripts before enabling in lab  
- Deploy: backend + both frontends when UI changes  

### Phase 1 — AI SOC Triage Assist (enrich / correlate / risk) ← **START HERE**
**Behind:** `AI_SOC_TRIAGE_ENABLED=false` by default  

Deliverables:
- Migration `034_ai_soc_triage_assist.sql` — new alert columns  
- Service `ai_soc_triage.py` — gather TI IOCs + related alerts + call Ollama  
- Chain after existing KB-092 explain worker (or shared queue step)  
- Admin Alert detail shows **AI triage draft** (score + notes) for SOC to accept/edit  
- Validator `kb096_validate_ai_soc_triage_assist.sh`  

**Human finalize UX:**
- Analyst sees draft risk score + correlation notes  
- Can overwrite text / ignore score  
- Still manually sets customer visibility and containment  

### Phase 2 — Live Entra / M365 Graph
**Blocked on:** Azure app registration secrets (you must create)  

Code already exists: `itdr_graph_client.py` + `itdr_service.py` (Graph first, sample fallback).

Operator steps:
1. Azure AD app (client credentials)  
2. Application permissions: `AuditLog.Read.All`, `Directory.Read.All` (+ admin consent)  
3. Put `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET` in `.env` (never commit)  
4. Recreate `backend-api`  
5. Admin sync ITDR for Alpha → confirm `source=graph` not `analysis_adapter`  

Code hardening (safe, optional while waiting for secrets):
- Token cache  
- Time-window filter / pagination on sign-ins  

### Phase 3 — Admin AI Chat
**Behind:** `AI_CHAT_ENABLED=false` by default  

Deliverables:
- `POST /admin/ai/chat` (SOC roles only)  
- Tools: tenant-scoped read of alerts/incidents/IOCs/recommendations (reuse existing services — no raw SQL)  
- Page `:3000/ai-assistant` + nav entry  
- Same Ollama endpoint (or separate `AI_CHAT_*` if load isolation needed)  
- Redact secrets in prompts; never return `.env` / hashes / keys  

### Phase 4 — Demo / enable in lab
1. Enable `AI_SOC_TRIAGE_ENABLED=true` on VM 100 with Ollama up  
2. Fire controlled high alert → verify draft fields  
3. Enable Graph when secrets ready  
4. Enable chat for SOC users only  

---

## 4. What we will NOT break

- Existing KB-092 explain worker (plain summary fields)  
- Threat Intel sync / MISP / STIX paths  
- Alert ingest / incident auto-open  
- Customer visibility fail-closed  
- ITDR sample fallback until Graph configured  

---

## 5. Env flags (new)

| Variable | Default | Meaning |
|----------|---------|---------|
| `AI_SOC_TRIAGE_ENABLED` | `false` | Enrich/correlate/risk draft worker |
| `AI_CHAT_ENABLED` | `false` | Admin chat API + UI |
| (existing) `AI_ALERT_ENABLED` | lab `true` | Explain worker (KB-092) |
| `AZURE_TENANT_ID` / `CLIENT_ID` / `CLIENT_SECRET` | empty | Live Graph |

---

## 6. Success criteria

| Goal | Pass signal |
|------|-------------|
| AI triage | High alert gets `ai_risk_score` + correlation notes; SOC can edit; customer_visible still false until human |
| TI complementarity | IOC matches still come from TI tables; AI cites them in notes |
| Graph | ITDR sync shows live Graph events when secrets set |
| Chat | Analyst question returns grounded answers from control-plane data; no cross-tenant leak for customer roles (admin SOC may be cross-tenant by design) |

---

## 7. Rollback

- Set flags to `false` → recreate backend (and frontends if UI)  
- Columns may remain (harmless)  
- Remove Azure secrets → ITDR returns to adapter samples  

---

## 8. Implementation status (2026-08-12)

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1 AI SOC triage | **ON in lab** | Migration 034 applied; drafts on Admin alert detail; human Accept/Reject; containment suggestion never auto-executed |
| Phase 2 Live Graph | **Hardened + waiting** | Token cache in `itdr_graph_client.py`; needs Azure app secrets in `.env` |
| Phase 3 Admin chat | **Enabling** | `/ai-assistant` + `POST /admin/ai/chat`; set `AI_CHAT_ENABLED=true` after tag |

Validator: `./scripts/kb096_validate_ai_soc_triage_assist.sh`

To enable in lab (after PASS):
1. Set `AI_SOC_TRIAGE_ENABLED=true` in `.env` (Ollama already used by KB-092)
2. Recreate `backend-api` only
3. Fire a high alert → confirm draft fields on Admin alert detail
4. Later: `AI_CHAT_ENABLED=true` + recreate backend + admin frontend already has UI

---

*Ship dark. Human SOC always finalizes.*
