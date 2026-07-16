# KB-031 — Customer Report Detail UI

Status: Implemented (pending commit).  
Branch: `kb031-customer-report-detail-ui`

## Purpose

Let a logged-in customer open one **published or archived** monthly report from the Reports list or Dashboard latest-report card and view **read-only, customer-safe detail**. No PDF/download. No raw metrics JSON. No draft access. No acknowledgement or comments.

## Table used

`monthly_reports` in `postgres/init/001_mssp_core_schema.sql` — same table as KB-024 list. Detail uses `id` as `report_id` (no friendly report number in schema).

## Endpoint

```http
GET /customer/reports/{short_code}/{report_id}
Authorization: Bearer <access_token>
```

Auth: `get_current_user` → resolve tenant by `short_code` → `require_tenant_match` (404 on mismatch) → parameterized:

```sql
WHERE tenant_id = %s
  AND id = %s
  AND status IN ('published', 'archived')
```

## Status visibility rule

Only `published` and `archived` rows are returned. A `draft` report returns **404** even if its UUID is guessed. Missing or wrong-tenant reports also return **404** (not 403).

## Response shape

```json
{
  "tenant": { "id": "...", "name": "...", "short_code": "DEMO" },
  "report": {
    "report_id": "<uuid>",
    "report_month": "2026-06-01",
    "status": "published",
    "title": "Monthly Security Report — Jun 2026",
    "summary": "...",
    "created_at": "...",
    "published_at": "..."
  }
}
```

Title is derived the same way as the KB-024 list:

```sql
('Monthly Security Report — ' || to_char(report_month, 'Mon YYYY')) AS title
```

`executive_summary` is returned as `summary`.

## Safe fields

`report_id`, `report_month`, `status`, `title`, `summary`, `created_at`, `published_at`.

`report_id` is the customer-facing detail identifier and is allowed.

## Hidden / forbidden fields

`tenant_id`, `metrics`, `report_file_path`, `raw_json`, `raw_event`, `details`, `internal_notes`, `admin_notes`, generation internals, `api_key`, `token`, `token_hash`, `password`, `password_hash`, `stack_trace`, `updated_at`, backend internals.

## Tenant isolation

DEMO customer cannot load DEMO2 report detail (404). Drafts and nonexistent UUIDs return 404.

## Frontend behavior

- `getCustomerReportDetail(shortCode, reportId)` → `/api/customer/reports/{shortCode}/{reportId}`
- Route `/reports/:reportId` (`ReportDetailPage.tsx`)
- Reports page: title links to detail
- Dashboard: latest-report title and primary CTA link to detail; “View all” remains `/reports`
- Loading / error / not_found / forbidden; read-only detail table; Back to reports
- No PDF download, no metrics charts, no `/admin` under `frontend-customer/src`
- `Layout.tsx` unchanged

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb031_validate_customer_report_detail_ui.sh
./scripts/kb031_validate_customer_report_detail_ui.sh
```

Or: `CUSTOMER_VIEWER_PASSWORD='...' ./scripts/kb031_validate_customer_report_detail_ui.sh`

Creates temporary DEMO published/draft + DEMO2 published fixtures, proves filtering and response shape, then cleans up.

Expected final line: `KB-031 CUSTOMER REPORT DETAIL UI VALIDATION PASSED`

## Manual browser checklist

1. Open `http://localhost:3001`, sign in as `customer.viewer@demo.local`.
2. Open **Reports**, click a title — confirm read-only detail and **Back to reports**.
3. Open **Dashboard**, click latest report title or **Open report** — confirm detail opens.
4. Network: only `/api/customer/reports/...` — never `/admin/*`. No download button.

## Deferred

- PDF/file download
- Safe metrics projection/charts
- Customer report acknowledgement
- Customer comments
- Report sharing/export
- Admin report publishing UI changes
