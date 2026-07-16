# KB-026 — Customer Recommendations API and UI

Status: Implemented (pending commit).  
Branch: `kb026-customer-recommendations-api-ui`

## Purpose

Give each customer a dedicated, read-only **Recommendations** page that lists **customer-visible** SOC recommendations for their own tenant (including historical completed/dismissed items). No accept/dismiss/complete workflow in this KB. No admin APIs.

## Table used

`customer_recommendations` in `postgres/init/001_mssp_core_schema.sql`:

| Column | Customer use |
|---|---|
| `id` | Returned as `recommendation_id` |
| `title`, `description` | Returned |
| `priority`, `category`, `status` | Returned (all statuses) |
| `due_at`, `completed_at`, `created_at`, `updated_at` | Returned |
| `customer_visible` | Filter only (`= true`); not returned |
| `tenant_id`, `related_alert_id`, `related_incident_id` | **Hidden** |

## Endpoint

```http
GET /customer/recommendations/{short_code}
Authorization: Bearer <access_token>
```

Auth: `get_current_user` → resolve tenant by `short_code` → `require_tenant_match` (404 on mismatch) → parameterized `WHERE tenant_id = %s AND customer_visible = true`, ordered by priority then `created_at DESC`, `LIMIT 100`.

## Response shape

```json
{
  "tenant": { "id": "...", "name": "...", "short_code": "DEMO" },
  "recommendations": [
    {
      "recommendation_id": "<uuid>",
      "title": "...",
      "description": "...",
      "priority": "high",
      "category": "general",
      "status": "open",
      "due_at": "...",
      "completed_at": null,
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

## Safe fields

`recommendation_id`, `title`, `description`, `priority`, `category`, `status`, `due_at`, `completed_at`, `created_at`, `updated_at`.

## Hidden / forbidden fields

`tenant_id`, `related_alert_id`, `related_incident_id`, internal notes, raw JSON/details, IPs, assignment/creator user IDs, API keys, tokens/hashes, passwords, stack traces, admin notes, invented columns (`business_impact`, `recommended_action`).

## Tenant isolation

DEMO customer cannot call `/customer/recommendations/DEMO2` (404). Hidden (`customer_visible = false`) DEMO rows are never returned.

## Frontend behavior

- `getCustomerRecommendations(shortCode)` → `/api/customer/recommendations/{shortCode}`
- Route `/recommendations` + nav item in `Layout.tsx`
- Loading / error / empty / read-only table
- No `/admin` under `frontend-customer/src`
- Dashboard behavior unchanged (still shows a recommendation snippet from the dashboard API)

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb026_validate_customer_recommendations_api_ui.sh
./scripts/kb026_validate_customer_recommendations_api_ui.sh
```

Or: `CUSTOMER_VIEWER_PASSWORD='...' ./scripts/kb026_validate_customer_recommendations_api_ui.sh`

Creates temporary DEMO visible/hidden and DEMO2 visible fixtures, proves filtering, then cleans up.

Expected final line: `KB-026 CUSTOMER RECOMMENDATIONS API UI VALIDATION PASSED`

## Manual browser checklist

1. Open `http://localhost:3001`, sign in as `customer.viewer@demo.local`.
2. Open **Recommendations** in the nav.
3. Network shows `/api/customer/recommendations/...` only — never `/admin/*`.
4. Confirm table or empty state; no related alert/incident IDs or secrets.

## Deferred

- Accept / dismiss / complete workflow from the customer portal
- Related alert / incident drill-down
- Customer comments
- SLA / due-date workflow automation
- Admin recommendation management UI
- Notification workflow
- Pagination beyond `LIMIT 100`
