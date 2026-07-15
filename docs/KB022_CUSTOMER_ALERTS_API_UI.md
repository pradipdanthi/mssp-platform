# KB-022 — Customer Alerts API and Customer Alerts Page

Status: Implemented (pending commit).  
Branch: `kb022-customer-alerts-api-ui`

## Purpose

Give each customer a read-only Alerts page in the customer portal (port 3001) that loads **only that tenant’s customer-visible alerts** from the own API. The customer UI never calls admin/SOC alert endpoints.

## Endpoint

```http
GET /customer/alerts/{short_code}
Authorization: Bearer <access_token>
```

Auth and tenant rules match dashboard/incidents (KB-011):

1. Caller must be authenticated (`get_current_user`).
2. Tenant is resolved by `short_code` (404 if missing).
3. `require_tenant_match` — customer roles may only access their own tenant; mismatch returns **404** (not 403).
4. SQL is parameterized and always filters `tenant_id = <resolved tenant>`.

### `customer_visible = true` rule

Only rows with `security_alerts.customer_visible = true` are returned. Internal SOC triage alerts stay hidden from the customer portal. The list may be empty even when the SOC has other alerts for that tenant — that is correct.

Ordered by `event_time DESC NULLS LAST`, then `created_at DESC`, limited to 100 rows.

### Response shape

```json
{
  "tenant": { "id": "...", "name": "...", "short_code": "DEMO" },
  "alerts": [
    {
      "alert_id": "<uuid>",
      "title": "...",
      "severity": "low|medium|high|critical",
      "status": "...",
      "source": "<source_tool>",
      "summary": "<ai_plain_summary or null>",
      "description": "<alert_description or null>",
      "detected_at": "<event_time or null>",
      "hostname": "<destination_host or null>"
    }
  ]
}
```

### Safe fields returned

| API field | Database source |
|---|---|
| `alert_id` | `id` |
| `title` | `alert_title` |
| `severity` | `severity` |
| `status` | `status` |
| `source` | `source_tool` |
| `summary` | `ai_plain_summary` |
| `description` | `alert_description` |
| `detected_at` | `event_time` |
| `hostname` | `destination_host` |

### Hidden fields (not selected / not returned)

- `raw_event`
- `external_alert_id`
- `source_ip`, `destination_ip`, `source_user`
- `ai_technical_summary`, `ai_likely_attack_type`, `ai_business_impact`, `ai_recommended_action`
- `ai_false_positive_score`
- `mitre_mapping`
- Appliance/asset UUIDs, secrets, token hashes, API keys, stack traces, admin notes

## Frontend behavior

- File: `frontend-customer/src/api/customer.ts` — `getCustomerAlerts(shortCode)` calls `/api/customer/alerts/{shortCode}` only (Vite proxies `/api` → backend).
- File: `frontend-customer/src/pages/AlertsPage.tsx` — loading / error / empty / read-only table.
- No `/admin` paths under `frontend-customer/src`.
- Read-only: no alert create, acknowledge, close, or edit.

## Files touched

| Path | Change |
|---|---|
| `backend-api/app/api/routes/customer.py` | Added `GET /alerts/{short_code}` |
| `frontend-customer/src/api/customer.ts` | Types + `getCustomerAlerts` |
| `frontend-customer/src/pages/AlertsPage.tsx` | Real alerts UI |
| `scripts/kb022_validate_customer_alerts_api_ui.sh` | Validation gate |
| `docs/KB022_CUSTOMER_ALERTS_API_UI.md` | This document |

Not modified: `.env`, `postgres/init/`, `docker-compose.yml`, `frontend-admin/`, database rows.

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb022_validate_customer_alerts_api_ui.sh
./scripts/kb022_validate_customer_alerts_api_ui.sh
```

Expected final line:

```text
KB-022 CUSTOMER ALERTS API UI VALIDATION PASSED
```

The script prompts interactively for the `customer.viewer@demo.local` password (never stored in the repo), or accepts `CUSTOMER_VIEWER_PASSWORD` from the environment for non-interactive runs. It rebuilds `backend-api` so the new route is loaded (backend image is not volume-mounted).

## Manual browser checklist

1. Open `http://localhost:3001` and sign in as `customer.viewer@demo.local`.
2. Open **Alerts** — loading then a table or an empty-state message (empty is OK if no `customer_visible` rows).
3. Browser DevTools Network: only `/api/auth/*` and `/api/customer/*` — never `/admin/*`.
4. Confirm the UI shows only safe columns (title, severity, status, source, summary, hostname, detected) — no raw JSON blobs.
5. Sign out; confirm unauthenticated access to alerts data is blocked.

## Deferred

- Marking demo alerts `customer_visible = true` (no DB updates in KB-022)
- Customer alert acknowledge / close / comment
- Pagination beyond `LIMIT 100`
- Alert detail drawer
- Admin UI changes for toggling `customer_visible`
- Demo data wipe/rebuild
- Production nginx / HTTPS
