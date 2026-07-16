# KB-029 — Customer Alert Detail UI

Status: Implemented (pending commit).  
Branch: `kb029-customer-alert-detail-ui`

## Purpose

Let a logged-in customer open one alert from the Alerts list or Dashboard v2 and view **read-only, customer-safe detail** for that alert only. No acknowledge/close workflow. No related incident drill-down. No admin APIs.

## Table used

`security_alerts` in `postgres/init/001_mssp_core_schema.sql` — same table as KB-022 list. Detail uses `id` as `alert_id` (no friendly alert number in schema).

## Endpoint

```http
GET /customer/alerts/{short_code}/{alert_id}
Authorization: Bearer <access_token>
```

Auth: `get_current_user` → resolve tenant by `short_code` → `require_tenant_match` (404 on mismatch) → parameterized:

```sql
WHERE tenant_id = %s AND id = %s AND customer_visible = true
```

Missing row, wrong tenant, or `customer_visible = false` → **404** (not 403).

## Response shape

```json
{
  "tenant": { "id": "...", "name": "...", "short_code": "DEMO" },
  "alert": {
    "alert_id": "<uuid>",
    "title": "...",
    "severity": "high",
    "status": "new",
    "source": "...",
    "summary": "...",
    "description": "...",
    "detected_at": "...",
    "hostname": "..."
  }
}
```

## Safe fields

`alert_id`, `title`, `severity`, `status`, `source`, `summary`, `description`, `detected_at`, `hostname`.

Column mapping:

| Response field | Database column |
|---|---|
| `alert_id` | `id::text` |
| `title` | `alert_title` |
| `severity` | `severity` |
| `status` | `status` |
| `source` | `source_tool` |
| `summary` | `ai_plain_summary` |
| `description` | `alert_description` |
| `detected_at` | `event_time` |
| `hostname` | `destination_host` |

Note: a status **value** such as `"false_positive"` is valid under the safe `status` field. Validation forbids a JSON **key** named `false_positive`, not that string value.

## Hidden / forbidden fields

`tenant_id`, `appliance_id`, `asset_id`, `protected_asset_id`, `external_alert_id`, `raw_event`, `ai_technical_summary`, `ai_likely_attack_type`, `ai_business_impact`, `ai_recommended_action`, `ai_false_positive_score`, `mitre_mapping`, `customer_visible`, IPs (`source_ip`, `destination_ip`, `local_ip`, `ip_address`), `source_user`, internal/admin notes, `details`, `raw_json`, user IDs, secrets/hashes/tokens/passwords, stack traces, backend internals.

No `incident_alerts` join — incident IDs and related incident summaries are not exposed.

## Tenant isolation

DEMO customer cannot load DEMO2 alert detail (404). Hidden alerts return 404 even if the UUID is guessed.

## Frontend behavior

- `getCustomerAlertDetail(shortCode, alertId)` → `/api/customer/alerts/{shortCode}/{alertId}`
- Route `/alerts/:alertId` (`AlertDetailPage.tsx`)
- Alerts list and Dashboard recent alerts link title → detail; back link to `/alerts`
- Loading / error / not_found / forbidden; read-only detail table
- No `/admin` under `frontend-customer/src`
- `Layout.tsx` unchanged

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb029_validate_customer_alert_detail_ui.sh
./scripts/kb029_validate_customer_alert_detail_ui.sh
```

Or: `CUSTOMER_VIEWER_PASSWORD='...' ./scripts/kb029_validate_customer_alert_detail_ui.sh`

Creates temporary DEMO visible/hidden + DEMO2 alert fixtures in `security_alerts`, proves filtering and response shape, then cleans up.

Expected final line: `KB-029 CUSTOMER ALERT DETAIL UI VALIDATION PASSED`

## Manual browser checklist

1. Open `http://localhost:3001`, sign in as `customer.viewer@demo.local`.
2. Open **Alerts** or **Dashboard**, click an alert title.
3. Confirm detail page shows severity, status, summary, description, hostname, detected time; **Back to alerts** works.
4. Network tab: only `/api/customer/alerts/...` — never `/admin/*`.

## Deferred

- Alert acknowledge/close workflow
- Customer comments on alerts
- Related incident drill-down
- Alert timeline
- Richer evidence view
- Admin alert publishing controls
