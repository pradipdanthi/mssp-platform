# KB-028 — Customer Dashboard v2 / Portal Polish

Status: Implemented (pending commit).  
Branch: `kb028-customer-dashboard-v2`

## Purpose

Make the customer portal dashboard stronger and more useful by composing already-validated, tenant-scoped customer APIs into a single read-only overview — with KPI cards, recent lists, and links into existing detail/list pages. No backend changes. No write actions.

## Frontend-only decision

KB-028 does **not** add or change backend routes, schema, compose, or `.env`.  
The legacy `GET /customer/dashboard/{short_code}` endpoint remains available for compatibility but is **not** used by Dashboard v2 (it lacks `recommendation_id` for detail links and can expose `metrics` on nested reports).

## APIs used

Client helper `getCustomerDashboardV2(shortCode)` runs `Promise.all` on:

| Helper | Endpoint |
|---|---|
| `getCustomerIncidents` | `GET /customer/incidents/{short_code}` |
| `getCustomerAlerts` | `GET /customer/alerts/{short_code}` |
| `getCustomerRecommendations` | `GET /customer/recommendations/{short_code}` |
| `getCustomerAssets` | `GET /customer/assets/{short_code}` |
| `getCustomerReports` | `GET /customer/reports/{short_code}` |

All-or-nothing load via `useCustomerQuery`: any 401/403/404/error fails the whole dashboard. Empty arrays render polished empty states.

## Dashboard sections

1. Welcome / tenant summary (`user.full_name`, `tenant.name`, `tenant.short_code`)
2. KPI cards
3. Recent incidents (max 5) → `/incidents/:incidentNumber`
4. Recent recommendations (max 5) → `/recommendations/:recommendationId`
5. Recent alerts (max 5) → list page `/alerts` only (no alert detail)
6. Latest report card → `/reports`
7. Appliance health snippet + asset counts → `/assets`

## KPI definitions

| KPI | Definition |
|---|---|
| Open incidents | `status` in `open`, `in_progress`, `waiting_customer` |
| High/critical alerts | `severity` in `high`, `critical` |
| Open recommendations | `status` in `open`, `in_progress` |
| Assets monitored | `assets.length` |
| Appliances online / other | `status === "online"` vs everything else |
| Latest report | first item from reports API (already newest-first), or “None” |

## Safe fields by section

| Section | Fields |
|---|---|
| Welcome | tenant name/short_code; optional user full_name |
| Incidents | incident_number, title, severity, status, customer_visible_summary, opened_at |
| Recommendations | recommendation_id (link only), title, priority, status, due_at |
| Alerts | title, severity, status, source, summary, description, detected_at |
| Reports | title, report_month, status, summary, published_at |
| Appliances | appliance_name, site_name, status, health_status, last_seen_at + counts |

## Hidden / forbidden fields

`/admin/*`; `metrics` JSON; raw JSON/details; related_alert_id / related_incident_id; internal/admin notes; IPs; secrets/hashes/tokens/passwords; stack traces; write actions; new dependencies.

## Tenant isolation

All composed APIs enforce `require_tenant_match` server-side. DEMO customer receives **404** for DEMO2 short_code on each underlying endpoint. Frontend only uses `tenant_short_code` from the authenticated session.

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb028_validate_customer_dashboard_v2.sh
./scripts/kb028_validate_customer_dashboard_v2.sh
```

Or: `CUSTOMER_VIEWER_PASSWORD='...' ./scripts/kb028_validate_customer_dashboard_v2.sh`

Expected final line: `KB-028 CUSTOMER DASHBOARD V2 VALIDATION PASSED`

## Manual browser checklist

1. Open `http://localhost:3001`, sign in as `customer.viewer@demo.local`.
2. Open **Dashboard** — welcome, KPIs, and sections render (or empty states).
3. Click an incident / recommendation link — detail pages open.
4. Alerts “View all” goes to `/alerts` (no per-alert detail).
5. Network tab: only `/api/customer/*` and `/api/auth/*` — never `/admin/*`.

## Deferred

- Charts / trend analytics
- Write actions (ack, comments, status changes)
- Alert detail page
- SLA widgets
- Notifications inbox
- Admin-configurable dashboard widgets
