# KB-066 — Admin Ops Catalog (Recommendations / Reports / Assets / Audit)

Status: **Implemented & validated** (2026-07-25)  
Module: Admin dashboard completeness after KB-065 onboarding UI.

## What was missing

After customer onboarding (KB-065), Admin still lacked day-to-day MSSP ops screens that `AGENTS.md` §1.1 expects:

1. Create/edit recommendations + customer visibility  
2. Monthly report draft/publish  
3. Protected assets inventory  
4. Audit log visibility  

## What shipped

### Backend

| Method | Path | Roles |
|---|---|---|
| GET | `/admin/recommendations/{id}` | admin/SOC read |
| POST | `/admin/recommendations` | platform_admin, soc_manager |
| PATCH | `/admin/recommendations/{id}` | platform_admin, soc_manager |
| GET/POST/PATCH | `/admin/reports`, `/admin/reports/{id}` | read all SOC; write admin+manager |
| GET/POST/PATCH | `/admin/assets`, `/admin/assets/{id}` | same |
| GET | `/admin/audit-logs` | admin/SOC read |

No schema migration. Uses existing tables. Report responses omit `metrics` / `report_file_path`. Asset responses omit raw `details` JSONB.

### Frontend (`http://192.168.0.201:3000/`)

New/updated nav: **Assets**, **Reports**, **Audit**  
Enhanced: **Recommendations** (Add / Edit + visibility)

Write buttons require **platform_admin** or **soc_manager** (same as triage).  
`soc_manager` can create recommendations/reports/assets; only **platform_admin** creates customers/users (KB-065).

## Validation

```bash
cd /opt/mssp-control
./scripts/kb066_validate_admin_ops_catalog_ui.sh
```

Expected: `KB-066 ADMIN OPS CATALOG UI VALIDATION PASSED`

## Intentionally still out of scope

- Notification **send** worker / WhatsApp delivery UI  
- AI auto-summary workers  
- Hard-delete of tenants/users/assets  
- Full appliance detail page polish  
- Audit log write instrumentation for every admin action (viewer reads existing `audit_logs` rows)

## Browser check

1. Login as `platform.admin@example.local` or `soc.manager@example.local`  
2. Hard refresh Admin UI  
3. Open Recommendations → Add Recommendation  
4. Open Reports / Assets / Audit in the left nav  
