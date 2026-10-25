# Operator summary — Kevantic Quote & Billing (overnight build)

## What you have (v1.1)

Standalone **enterprise quote-to-cash** for NikTiar: dashboard, CPQ quotes, Tally-style GST invoices, payments, aging, company/bank settings. Own Compose — **does not** touch Admin `:3000` / Customer `:3001`.

| Item | Value |
|---|---|
| UI + API | `http://192.168.0.201:8090/` |
| Health | `http://127.0.0.1:8090/health` |
| Postgres | `127.0.0.1:5433` (loopback only) |
| Containers | `kevantic-billing-app`, `kevantic-billing-db` |
| Login | `data/OPERATOR_CREDS.txt` |

## Features

- **Dashboard** — open quotes, AR, MTD invoiced/collected, GST break-up, aging bars, overdue + expiring quotes  
- **Parties** — GSTIN, Indian state codes, export flag, payment terms  
- **Catalog** — edit list prices / active flags in UI  
- **Quotes** — opportunity, owner, line + doc discount, approval when discount ≥ threshold, duplicate, send/accept/decline, PDF, terms  
- **Invoices** — tax invoice + proforma, credit note, void, record payment (UTR/UPI/cheque), balance due, PDF with bank details  
- **Company settings** — GSTIN, bank/IFSC/UPI, default terms, LUT, validity days  

## How to quote

1. Sign in → **Company settings** (GSTIN + bank) once  
2. **Parties** → customer  
3. **New quote** → SKUs + term → Create  
4. Approve if prompted → Tax invoice / Proforma → Record payment  

## Move to another cloud VM

```bash
cd /opt/mssp-control/kevantic-billing
docker compose up -d --build   # after copying folder + volume / dump
```
