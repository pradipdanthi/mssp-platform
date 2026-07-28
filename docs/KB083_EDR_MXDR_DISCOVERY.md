# KB-083 — EDR & MXDR discovery (2026-07-28)

## STEP 1 discovery summary

### Backend (FastAPI `/opt/mssp-control/backend-api`)

| Area | Location |
|------|----------|
| Routers wired in `app/main.py` | `admin`, `customer`, `alert_incident_triage`, `soc_sync`, `entitlements`, … |
| Wazuh ingress | `app/api/routes/soc_sync.py` → `POST /integrations/soc/hooks/wazuh/{token}` |
| Shuffle forward | Same file, `_forward_to_shuffle()`; URL from `SHUFFLE_WEBHOOK_URL` / `.secrets/shuffle_webhook_url` |
| Wazuh Manager API | `app/services/wazuh_client.py` (groups, agent lookup) |
| TheHive API | `app/services/thehive_client.py` |
| Alerts / MITRE column | `security_alerts.mitre_mapping`, `raw_event` (ingress often empty today) |
| Incidents | `incidents`, `incident_alerts`, triage in `alert_incident_triage.py` |
| RBAC roles | `platform_admin`, `soc_manager`, `soc_analyst`, `customer_admin`, `customer_viewer` (no `tenant_admin`) |
| Entitlements | `tenant_entitlements` incl. `velociraptor_enabled` |

### Frontend

| Portal | Incident UI |
|--------|-------------|
| Admin | `IncidentDetailPanel.tsx`, `IncidentDrawer.tsx`, `IncidentsPage.tsx` |
| Customer | `IncidentDetailPage.tsx` (read-only today) |

API prefix: browsers call `/api/*` → nginx strips to backend (`frontend-admin/nginx.conf`).

### External VMs (env / secrets, not in Git)

- Wazuh Manager: `WAZUH_API_URL`, `.secrets/wazuh_api_*`
- Shuffle: `.secrets/shuffle_webhook_url`
- TheHive: `.secrets/thehive_password`, `THEHIVE_DEFAULT_ORG`
- Velociraptor: **not deployed** (entitlement flag exists)

### Gaps vs EDR directive

1. No `/v1/edr/*` routes yet.
2. Wazuh instant ingress does not persist `raw_event` / MITRE on `security_alerts`.
3. No active-response or EDR action audit table.
4. Customer incident view has no process tree or response bar.

## Planned files (KB-083 implementation)

**New**

- `postgres/init/014_kb083_edr_actions.sql`
- `backend-api/app/schemas/edr.py`
- `backend-api/app/services/edr_process_tree.py`
- `backend-api/app/services/edr_mitre.py`
- `backend-api/app/services/edr_actions.py`
- `backend-api/app/services/shuffle_edr_client.py`
- `backend-api/app/api/routes/edr.py`
- `scripts/kb083_validate_edr_mxdr.sh`
- `frontend-admin/src/components/edr/*` (shared patterns)
- `frontend-customer/src/components/edr/*`

**Modified**

- `backend-api/app/main.py` — include EDR router
- `backend-api/app/services/wazuh_client.py` — active response helpers
- `backend-api/app/api/routes/soc_sync.py` — persist raw_event + MITRE on ingress
- `backend-api/app/api/routes/customer.py` — EDR-safe incident enrichment
- `frontend-admin/src/components/IncidentDetailPanel.tsx`
- `frontend-customer/src/pages/IncidentDetailPage.tsx`
- `frontend-admin/src/pages/DashboardPage.tsx`, `frontend-customer/src/pages/DashboardPage.tsx`
- `frontend-*/src/api/*.ts`
