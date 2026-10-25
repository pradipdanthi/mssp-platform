# Kevantic Quote & Billing

Standalone **enterprise quoting (CPQ) + Tally-style GST invoicing** for the NikTiar product portfolio.

- **Does not** modify `mssp-control` Docker Compose, Admin portal `:3000`, or Customer portal `:3001`.
- Own containers: `kevantic-billing-app` (`:8090`) and `kevantic-billing-db` (`127.0.0.1:5433`).
- Portable: copy this folder + volume to another cloud VM and `docker compose up -d`.

## Design references

See [`docs/DESIGN.md`](docs/DESIGN.md) — CPQ configure-price-quote, India GST (CGST/SGST/IGST), Tally-like voucher numbers, credit notes.

## Quick start

```bash
cd /opt/mssp-control/kevantic-billing
cp .env.example .env
# edit .env — set strong BILLING_ADMIN_PASSWORD and POSTGRES_PASSWORD
docker compose up -d --build
curl -fsS http://127.0.0.1:8090/health
```

Open `http://<host>:8090/` and sign in with `BILLING_ADMIN_USER` / `BILLING_ADMIN_PASSWORD`.

## Catalog (seeded)

| SKU | Product |
|---|---|
| NKT-SILVER-EP | NikTiar Silver (per endpoint / month) |
| NKT-GOLD-EP | NikTiar Gold |
| NKT-PLATINUM-EP | NikTiar Platinum |
| NKT-SE-SHARED-HOST | SecureEdge Shared (per hostname / month) |
| NKT-SE-DEDICATED | SecureEdge Dedicated |
| NKT-EDGE-NODE | Edge Node appliance (one-time) |
| NKT-ONBOARD-PKG | Onboarding package |
| NKT-RETAINER-STD | SOC advisory retainer |

List prices are commercial defaults — edit via `PATCH /api/catalog/{id}`.

## API (Basic auth)

- `GET /health` — public
- `GET /api/me` · `/api/catalog` · `/api/parties` · `/api/quotes` · `/api/invoices`
- `POST /api/quotes` → `POST /api/invoices/from-quote/{id}` → PDF / mark-paid / credit-note

## Move to another cloud host

1. `docker compose down` (optional)  
2. Copy `kevantic-billing/` and the named volume `kevantic-billing_billing_pgdata` (or `pg_dump`)  
3. Set `.env` on the new host  
4. `docker compose up -d --build`
