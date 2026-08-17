# Playwright E2E — Admin + Customer portals

Targets the **live nginx builds** on VM 100:

- Admin: `http://192.168.0.201:3000` (override with `E2E_ADMIN_URL`)
- Customer: `http://192.168.0.201:3001` (override with `E2E_CUSTOMER_URL`)

Credentials come from `/opt/mssp-control/.secrets/validation.env` (never commit).

## Setup (once)

```bash
cd /opt/mssp-control/e2e
npm install
npx playwright install chromium
```

## Run

```bash
cd /opt/mssp-control/e2e
# All tests (live + mocked)
npm test

# Live stack only
npm run test:live

# Deterministic mock-data chart tests only
npm run test:mocked
```

## What is covered

| Suite | Checks |
|-------|--------|
| `admin-dashboard.spec.ts` | Login, KPI shell, timeline / donut / heatmap widgets, 24h↔7d filter, Customer scope |
| `admin-dashboard.mocked.spec.ts` | Same widgets with mocked API payloads |
| `admin-filters.spec.ts` | Incidents severity filter + Alerts search URL |
| `customer-dashboard.spec.ts` | Login, chart widgets, Alerts filters |
| `customer-dashboard.mocked.spec.ts` | Mocked customer KPIs + charts |

After UI `data-testid` changes, rebuild portals:

```bash
cd /opt/mssp-control
./scripts/production_deploy_control_plane.sh
```

## Host without Node

VM 100 may not have Node installed. Prefer:

```bash
cd /opt/mssp-control
./scripts/run_e2e_playwright.sh
# or only mocked:
./scripts/run_e2e_playwright.sh --grep @mocked
```
