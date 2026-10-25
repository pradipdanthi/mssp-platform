# Kevantic Quote & Billing (standalone)

**Status:** Enterprise quote-to-cash appliance for the NikTiar portfolio  
**Runtime:** Own Docker Compose · UI+API `http://HOST:8090` · Postgres `127.0.0.1:5433`  
**Isolation:** Does **not** modify `mssp-control` compose, Admin `:3000`, or Customer `:3001`.

## Research summary (why this shape)

| Reference | What we took |
|---|---|
| Modern CPQ (ISG / Subskribe patterns) | Guided configure → price → quote; catalog-driven lines; discount + approval hooks; quote → billing handoff without re-typing |
| SaaS invoice-to-cash (India) | GSTIN, place of supply, CGST/SGST vs IGST, export zero-rate flag, TDS note, credit notes (not silent invoice edits) |
| Tally (billing / GST) | Party ledger, voucher-style invoice numbers, tax breakup on every line & total, printable tax invoice, credit note |
| Product portfolio | Silver / Gold / Platinum subscription SKUs + NikTiar SecureEdge Shared/Dedicated + Edge Node appliance |

## Quote-to-cash flow

1. **Party** — legal name, billing address, GSTIN, place-of-supply state, currency, payment terms  
2. **Quote** — pick catalog SKUs (tiers, SecureEdge, appliances), qty, term months, discount %  
3. **Tax engine** — domestic intra-state CGST+SGST, inter-state IGST, export zero-rated (LUT flag)  
4. **Accept quote** → mint **Invoice** (Tally-like voucher number `KEV/INV/YYYY/####`)  
5. **Credit note** for corrections (never rewrite posted invoices)  
6. **PDF** + JSON export for accountant / future Tally sync  

## Portability

- Entire stack lives under `kevantic-billing/` with its own `docker-compose.yml`.  
- Move to another cloud VM: copy folder + volume, set env, `docker compose up -d`.  
- Optional later: sync tenants from control-plane API (read-only) — not required for v1.

## Security

- Basic auth for UI/API (`BILLING_ADMIN_USER` / `BILLING_ADMIN_PASSWORD`).  
- Bind Postgres to loopback only.  
- No shared secrets with `mssp-control` `.env`.
