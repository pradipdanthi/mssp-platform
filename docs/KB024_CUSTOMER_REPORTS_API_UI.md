# KB-024 — Customer Reports API and Reports Page

Status: Implemented (pending commit).  
Branch: `kb024-customer-reports-api-ui`

## Purpose

Give each customer a dedicated, read-only **Reports** page that loads **published/archived monthly security reports** for their own tenant. Replaces the dashboard-backed reports list. No admin API calls; no raw metrics JSON or file paths.

## Table used

`monthly_reports` in `postgres/init/001_mssp_core_schema.sql`:

| Column | Customer use |
|---|---|
| `id` | Returned as `report_id` |
| `report_month` | Returned as `report_month` |
| `status` | Returned; only `published` / `archived` rows |
| `executive_summary` | Returned as `summary` |
| `created_at` / `published_at` | Returned |
| *(no title column)* | `title` derived: `Monthly Security Report — Mon YYYY` |
| `metrics` (JSONB) | **Hidden** |
| `report_file_path` | **Hidden** |
| `draft` status rows | **Hidden** from customer portal |

## Endpoint

```http
GET /customer/reports/{short_code}
Authorization: Bearer <access_token>
```

Auth: `get_current_user` → resolve tenant by `short_code` → `require_tenant_match` (404 on mismatch) → parameterized `WHERE tenant_id = %s`, `ORDER BY report_month DESC`, `LIMIT 100`.

### Response shape

```json
{
  "tenant": { "id": "...", "name": "...", "short_code": "DEMO" },
  "reports": [
    {
      "report_id": "<uuid>",
      "report_month": "2026-06-01",
      "status": "published",
      "title": "Monthly Security Report — Jun 2026",
      "summary": "...",
      "created_at": "...",
      "published_at": "..."
    }
  ]
}
```

### Safe fields

`report_id`, `report_month`, `status`, `title` (derived), `summary`, `created_at`, `published_at`.

### Hidden fields

`metrics`, `report_file_path`, drafts, secrets, token/API key/password hashes, raw JSON, internal/admin notes, stack traces, generation internals.

## Tenant isolation

Customer DEMO cannot call `/customer/reports/DEMO2` (404). SQL always filters by resolved `tenant_id`.

## Frontend behavior

- `getCustomerReports(shortCode)` → `/api/customer/reports/{shortCode}` only.
- `ReportsPage.tsx` no longer uses the dashboard endpoint.
- Loading / error / empty / read-only table.
- No `/admin` under `frontend-customer/src`.

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb024_validate_customer_reports_api_ui.sh
./scripts/kb024_validate_customer_reports_api_ui.sh
```

Expected final line: `KB-024 CUSTOMER REPORTS API UI VALIDATION PASSED`

## Manual browser checklist

1. Open `http://localhost:3001`, sign in as `customer.viewer@demo.local`.
2. Open **Reports** — Network shows `/api/customer/reports/...` only.
3. Confirm table or empty state (empty is OK if only drafts exist).
4. No metrics blobs, file paths, or credentials in the UI.

## Deferred

- PDF / file download of `report_file_path`
- Customer-visible metrics charts (would need a safe metrics projection)
- Draft visibility for customers
- Report acknowledge / comment
- Pagination beyond `LIMIT 100`
- Admin report publishing UI changes
- Demo seed / DB cleanup
