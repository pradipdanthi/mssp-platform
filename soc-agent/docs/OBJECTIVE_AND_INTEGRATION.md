# SOC Agent — objective vs Gemini prompt vs our MSSP

## Your real objective

Reduce **human SOC effort**. The agent should behave like a certified Tier-1/Tier-2 analyst: enrich, reason, verdict, recommend — **not** rebuild Admin portals, Wazuh, TheHive, or billing.

## What the Gemini prompt asks

| Ask | Meaning |
|---|---|
| $0 LLM | Use Cursor subscription CLI and/or free OpenRouter models — no new paid API |
| Isolated VM | Separate from control plane (we already have **VM 117**) |
| Do **not** touch production code/schemas | No edits to `backend-api`, Postgres, Admin/Customer portals |
| Webhook + OSINT + LLM triage + audit log | Analyst pipeline on the agent host |

## How our MSSP already works (do not duplicate UI)

- Engines → adapters → Postgres → Admin/Customer APIs  
- **Tier-1 AI triage already lives in control plane** (`ai_tier1_triage.py` → Ollama on VM **115**)  
- Cases/SOAR: TheHive/Shuffle on VM 102  

So this agent must be a **sidecar analyst**, not a second product UI.

## Integration posture (tight, without schema changes)

**Inbound (engines → agent)**  
Normalized alert JSON POSTed to the agent webhook (Shuffle/Wazuh custom integration / future control-plane forwarder). Same shape as MSSP alert fields where possible.

**Outbound (agent → MSSP)** — *next approved step* (still no schema change if we reuse existing APIs):  
POST triage notes into existing incident/recommendation endpoints with a service JWT — **not implemented until you approve** (Gemini forbids touching production in this pass).

**This pass:** upgrade agent intelligence (LLM + OSINT + audit) on VM 117 only; publish a stable webhook contract Admin/Shuffle can call later.

## Drivers ($0 extra — Cursor subscription)

1. **Cursor CLI** (`agent` / `cursor-agent`) on VM 117 — **only** LLM for SOC agent  
2. Requires `CURSOR_API_KEY` in `/opt/soc-agent/.env`  
3. **Lab Ollama (VM 115) is NOT used here** — it stays for control-plane Tier-1 only (slow / already wired)  

Without `CURSOR_API_KEY`, ingest returns HTTP 503 until you paste the key and restart the service.
