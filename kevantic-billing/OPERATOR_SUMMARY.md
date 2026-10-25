# Operator summary — Kevantic Quote & Billing (overnight build)

## What you have

A **standalone** enterprise quoting + GST invoicing tool for the NikTiar portfolio, running on this server **without touching** Admin (`:3000`), Customer (`:3001`), or `mssp-control` Compose.

| Item | Value |
|---|---|
| UI + API | `http://<server-ip>:8090/` |
| Health | `http://127.0.0.1:8090/health` |
| Postgres | `127.0.0.1:5433` (loopback only) |
| Containers | `kevantic-billing-app`, `kevantic-billing-db` |
| Login | See `data/OPERATOR_CREDS.txt` (chmod 600, not in git) |

## How to quote a customer

1. Open `:8090` → sign in  
2. **Parties** → add legal name, state/code, GSTIN  
3. **New Quote** → pick SKUs (Silver/Gold/Platinum, SecureEdge, appliances) + term months  
4. Tax auto-picks **IGST** (inter-state) or **CGST+SGST** (same state as company)  
5. **Create invoice** from the quote → PDF → Mark paid / Credit note  

## Proven overnight smoke

- Quote `KEV/QT/2026/0001` → Invoice `KEV/INV/2026/0001` (IGST, sample Acme Karnataka)  
- PDFs generated; mark-paid works  
- Admin/Customer portals still HTTP 200; mssp `/health` ok  

## Move to another cloud VM later

```bash
cd /opt/mssp-control/kevantic-billing
docker compose down
# copy folder + docker volume kevantic-billing_billing_pgdata (or pg_dump)
docker compose up -d --build
```

## Next (when you wake)

1. Put real company GSTIN / address in `.env` and recreate app container  
2. Adjust list prices if commercial rates differ  
3. Say **commit** if you want this folder in git (`.env` / `data/` stay ignored)  
4. Optional later: read-only sync of tenants from control-plane API  
