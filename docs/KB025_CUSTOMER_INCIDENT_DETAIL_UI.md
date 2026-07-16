# KB-025 — Customer Incident Detail UI

Status: Implemented (pending commit).  
Branch: `kb025-customer-incident-detail-ui`

## Purpose

Let a logged-in customer open one incident from the incidents list and view **read-only, customer-safe detail** for that incident only — including customer-visible timeline events and related customer-visible alerts. No comments, writes, acknowledgements, or admin APIs.

## Endpoint

```http
GET /customer/incidents/{short_code}/{incident_number}
Authorization: Bearer <access_token>
```

Auth / isolation (same as other customer GETs):

1. `get_current_user`
2. Resolve tenant by `short_code` (404 if missing)
3. `require_tenant_match` — customer mismatch → **404** (not 403)
4. Parameterized SQL: `tenant_id` + `incident_number`
5. Missing incident for that tenant → **404**

Uses **`incident_number`** (not internal `incidents.id`) in the URL and frontend route.

## Response shape

```json
{
  "tenant": { "id": "...", "name": "...", "short_code": "DEMO" },
  "incident": {
    "incident_number": "...",
    "title": "...",
    "severity": "...",
    "status": "...",
    "customer_visible_summary": "...",
    "business_impact": "...",
    "customer_action_required": "...",
    "resolution_summary": "...",
    "opened_at": "...",
    "resolved_at": null,
    "closed_at": null
  },
  "timeline": [
    { "event_type": "created", "title": "...", "created_at": "..." }
  ],
  "related_alerts": [
    {
      "alert_id": "...",
      "title": "...",
      "severity": "...",
      "status": "...",
      "source": "...",
      "summary": "...",
      "description": "...",
      "detected_at": "...",
      "hostname": "..."
    }
  ]
}
```

## Safe fields

| Area | Fields / filter |
|---|---|
| Incident | Listed fields above (same safe set as list) |
| Timeline | `event_type`, `title`, `created_at` only where `visibility = 'customer'` |
| Related alerts | Via `incident_alerts` → `security_alerts`; same tenant + `customer_visible = true`; KB-022 field set |

## Hidden / forbidden fields

- `internal_notes`, `assigned_to_user_id`, `primary_alert_id`, internal incident UUID as `id`
- Timeline: `details`, `created_by_user_id`, `visibility = 'internal'` rows
- **Comments (`incident_comments`) — omitted entirely in KB-025** (schema has a visibility flag; deferred)
- Alert: `raw_event`, IPs, `external_alert_id`, technical AI, MITRE, FP score, secrets
- API keys, token/password hashes, stack traces, admin notes

## Tenant isolation

DEMO customer may not load DEMO2’s incident (404), whether via DEMO2 `short_code` or a foreign `incident_number` under DEMO.

## Frontend behavior

- `getCustomerIncidentDetail(shortCode, incidentNumber)` → `/api/customer/incidents/{shortCode}/{incidentNumber}`
- Route: `/incidents/:incidentNumber` (`IncidentDetailPage.tsx`)
- Incidents list links number + title to the detail page
- Loading / error / not_found / forbidden states; read-only tables
- No `/admin` under `frontend-customer/src`

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb025_validate_customer_incident_detail_ui.sh
./scripts/kb025_validate_customer_incident_detail_ui.sh
```

Or: `CUSTOMER_VIEWER_PASSWORD='...' ./scripts/kb025_validate_customer_incident_detail_ui.sh`

The script creates temporary DEMO/DEMO2 incidents, customer+internal timeline rows, and visible+hidden related alerts; proves filtering; then **cleans up all fixtures**.

Expected final line:

```text
KB-025 CUSTOMER INCIDENT DETAIL UI VALIDATION PASSED
```

## Manual browser checklist

1. Open `http://localhost:3001`, sign in as `customer.viewer@demo.local`.
2. Open **Incidents**, click an incident number or title.
3. Confirm detail shows summary/impact/timeline/related alerts (or empty sections).
4. Network: only `/api/customer/incidents/...` — never `/admin/*`.
5. No internal notes, timeline details, or hidden alerts appear.

## Deferred

- Customer-visible comments / reply submission
- Incident acknowledgement
- Status / assignment changes from customer portal
- Admin incident workflow UI
- PDF / export
- Richer timeline (`details` even for customer-visible rows)
- Showing `incident_comments` (schema supports `visibility`; omitted in KB-025 by design)
