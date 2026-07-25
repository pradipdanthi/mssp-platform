# KB-067 — Enterprise Monthly Report (On-screen + PDF + Excel)

Status: **Implemented** (2026-07-25)  
Module type: Control-plane feature (Admin + Customer)

## Purpose

Make the monthly report a real MSSP deliverable:

- **On-screen** enterprise sections in Admin preview and Customer portal  
- **PDF download**  
- **Excel (.xlsx) download**  
- Auto-calculated metrics from live platform data, frozen into `monthly_reports.metrics`  
- SOC-authored narrative (summary, highlights, trends, next-month focus, leadership asks)

## What the report contains

| Section | Source |
|---|---|
| Cover (customer, SLA, criticality, period) | `tenants` + report row |
| Executive summary | SOC (`executive_summary`) |
| Posture (appliances/assets counts) | `appliances`, `protected_assets` |
| Detection volume by severity/status | `security_alerts` in month |
| Incident outcomes + notable safe summaries | `incidents` (notable only when `customer_visible_summary` set) |
| Recommendations / action items | `customer_recommendations` where `customer_visible=true` |
| Notification activity counts | `notification_events` (no recipient PII) |
| Narrative / leadership asks | SOC fields in snapshot.narrative |
| Deferred MTTD/MTTR/SLA timers note | Static until timers exist |

Customer never receives: IPs, raw alerts, raw metrics dump, `report_file_path`, internal notes.

## APIs

Admin:

- `POST /admin/reports/{id}/refresh-metrics`
- `GET /admin/reports/{id}/download.pdf`
- `GET /admin/reports/{id}/download.xlsx`
- Detail includes projected `sections`

Customer (published/archived only):

- Detail includes `sections`
- `GET /customer/reports/{short_code}/{report_id}/download.pdf`
- `GET /customer/reports/{short_code}/{report_id}/download.xlsx`

## Validation

```bash
cd /opt/mssp-control
./scripts/kb067_validate_enterprise_monthly_report_export.sh
```

Expected: `KB-067 ENTERPRISE MONTHLY REPORT EXPORT VALIDATION PASSED`

## How to use (lab)

1. Login Admin as `platform_admin` or `soc_manager`  
2. **Reports → Add Report** (pick customer + month + summary)  
3. **Open** → **Refresh metrics** → edit narrative → set **published** → Save  
4. **Download PDF / Excel** from Admin  
5. Customer portal → **Reports** → open report → **Download PDF / Excel**
