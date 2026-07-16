# KB-056 — Admin/SOC Triage Dashboard Enhancements

Status: Implemented; static/build validation passed, live API validation pending backend redeploy.  
Module type: Backend API and Admin/SOC frontend.

## Purpose

Turn the existing read-only alerts and incidents lists into practical SOC triage views. Analysts can inspect internal alert/case data, open detail pages, maintain incident assignment and customer-safe summaries, and add case comments without exposing these internal endpoints to customer users.

## Approved scope

### Backend

- New `GET /admin/alerts/{alert_id}` internal alert detail.
- New `PATCH /admin/alerts/{alert_id}` for `status` and `customer_visible`.
- New `GET /admin/incidents/{incident_id}` detail with internal timeline and comments.
- New `PATCH /admin/incidents/{incident_id}` for `status`, `assigned_to_user_id`, and `customer_visible_summary`.
- New `POST /admin/incidents/{incident_id}/comments`.
- Optional `status`, `severity`, and `tenant_id` filters on the existing alert and incident list endpoints.
- Request validation models in `backend-api/app/schemas/triage.py`.

Alert updates are restricted to `platform_admin` and `soc_manager`, as required. Incident updates and comments use the existing Admin/SOC role boundary (`platform_admin`, `soc_manager`, `soc_analyst`). Assignment accepts only active Admin/SOC users.

### Admin frontend

- Alert and incident list entries link to detail pages.
- `/alerts/:alertId` displays internal alert evidence and provides status/customer-visibility triage controls.
- `/incidents/:incidentId` displays internal case detail, timeline, and comments, with status, assignee, customer-summary, and comment forms.
- Alert controls are read-only for `soc_analyst`, matching backend RBAC.

## Security boundaries

- Every endpoint requires a valid Admin/SOC JWT.
- Customer roles cannot access `/admin` endpoints.
- All SQL values are parameterized. The small dynamic query fragments contain only server-defined column names and predicates.
- Customer portal code is unchanged and continues to call no `/admin` APIs.
- Internal alert data, raw events, internal notes, and internal comments are shown only in the Admin/SOC portal.
- No credentials, token hashes, password hashes, or appliance API keys are selected or returned.

## Data model

No schema change is needed. KB-056 uses the existing:

- `security_alerts`
- `incidents`
- `incident_timeline`
- `incident_comments`
- `platform_users`
- `tenants`, `appliances`, and `protected_assets`

## Files

- `backend-api/app/api/routes/alert_incident_triage.py`
- `backend-api/app/schemas/triage.py`
- `backend-api/app/api/routes/admin.py`
- `backend-api/app/main.py`
- `frontend-admin/src/api/admin.ts`
- `frontend-admin/src/App.tsx`
- `frontend-admin/src/pages/AlertsPage.tsx`
- `frontend-admin/src/pages/IncidentsPage.tsx`
- `frontend-admin/src/pages/AlertDetailPage.tsx`
- `frontend-admin/src/pages/IncidentDetailPage.tsx`
- `scripts/kb056_validate_admin_soc_triage_dashboard_enhancements.sh`
- `docs/KB056_ADMIN_SOC_TRIAGE_DASHBOARD_ENHANCEMENTS.md`
- `docs/AI_PROMPT_LEDGER.md`

## Validation

Run:

```bash
cd /opt/mssp-control
chmod +x scripts/kb056_validate_admin_soc_triage_dashboard_enhancements.sh
./scripts/kb056_validate_admin_soc_triage_dashboard_enhancements.sh
```

Set `PLATFORM_ADMIN_PASSWORD` for a non-interactive run, or enter the platform administrator password when prompted. The validator checks source wiring, Python and TypeScript builds, Docker Compose service state, API health, login/RBAC, list filters, alert triage, incident triage, timeline/comments detail, and fixture cleanup.

Expected final line:

```text
KB-056 ADMIN/SOC TRIAGE DASHBOARD ENHANCEMENTS VALIDATION PASSED
```
