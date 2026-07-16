# KB-027 — Customer Recommendation Detail UI

Status: Implemented (pending commit).  
Branch: `kb027-customer-recommendation-detail-ui`

## Purpose

Let a logged-in customer open one recommendation from the Recommendations list and view **read-only, customer-safe detail** for that item only. No accept/dismiss/complete workflow. No related alert/incident drill-down. No admin APIs.

## Table used

`customer_recommendations` in `postgres/init/001_mssp_core_schema.sql` — same table as KB-026 list. Detail uses `id` as `recommendation_id` (no friendly number in schema).

## Endpoint

```http
GET /customer/recommendations/{short_code}/{recommendation_id}
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
  "recommendation": {
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
}
```

## Safe fields

`recommendation_id`, `title`, `description`, `priority`, `category`, `status`, `due_at`, `completed_at`, `created_at`, `updated_at`.

## Hidden / forbidden fields

`tenant_id`, `related_alert_id`, `related_incident_id`, `customer_visible`, internal/admin notes, raw JSON/details, IPs, user IDs, secrets/hashes/tokens/passwords, stack traces, invented columns.

## Tenant isolation

DEMO customer cannot load DEMO2 recommendation detail (404). Hidden recommendations return 404 even if the UUID is guessed.

## Frontend behavior

- `getCustomerRecommendationDetail(shortCode, recommendationId)` → `/api/customer/recommendations/{shortCode}/{recommendationId}`
- Route `/recommendations/:recommendationId` (`RecommendationDetailPage.tsx`)
- List page links title → detail; back link to `/recommendations`
- Loading / error / not_found / forbidden; read-only detail table
- No `/admin` under `frontend-customer/src`
- `Layout.tsx` unchanged (nav still `/recommendations`)

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb027_validate_customer_recommendation_detail_ui.sh
./scripts/kb027_validate_customer_recommendation_detail_ui.sh
```

Or: `CUSTOMER_VIEWER_PASSWORD='...' ./scripts/kb027_validate_customer_recommendation_detail_ui.sh`

Creates temporary DEMO visible/hidden + DEMO2 fixtures, proves filtering, then cleans up.

Expected final line: `KB-027 CUSTOMER RECOMMENDATION DETAIL UI VALIDATION PASSED`

## Manual browser checklist

1. Open `http://localhost:3001`, sign in as `customer.viewer@demo.local`.
2. Open **Recommendations**, click a title.
3. Confirm detail page shows full description and metadata; **Back to recommendations** works.
4. Network: only `/api/customer/recommendations/...` — never `/admin/*`.

## Deferred

- Accept / dismiss / complete workflow
- Related alert / incident drill-down
- Customer comments
- SLA workflow
- Admin recommendation management UI
- Notification workflow
