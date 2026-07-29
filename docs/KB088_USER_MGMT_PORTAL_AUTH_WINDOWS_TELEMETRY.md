# KB-088 — Deploy snapshot: user management, portal auth, SPA routes, Windows telemetry

Status: Implemented on control plane (VM 100).  
Date: 2026-07-29  
Purpose: Capture work required to **redeploy** this stack without losing recent operational fixes.

## 1. Scope in this snapshot

| Area | What shipped |
|------|----------------|
| **Delegated user management** | Customer admin + MSSP governance APIs (`/v1/customer/users`, `/v1/admin/customers/{id}/users`); Admin tenant Users panel; Customer **User Management** UI; soft-delete; audit actions; `scripts/validate_user_management.py` auto-cleans test tenants |
| **Portal-scoped login** | `POST /auth/login` accepts `portal=admin\|customer`; Admin (:3000) staff-only; Customer (:3001) customer roles only; frontends send portal + hard-block wrong roles |
| **SPA `/assets` hard refresh** | Vite `assetsDir: "bundled"`; nginx `try_files $uri /index.html` (both portals) — fixes clash with React route `/assets` |
| **Windows endpoint telemetry** | `scripts/bootstrap_windows_telemetry.ps1` + Sysmon baseline; Windows agent ZIP embeds telemetry; installer runs Sysmon + 4688/cmdline + `ossec.conf` localfiles |
| **Related prior uncommitted stack** | Agent packages, EDR sweeper/cloud-readiness pieces, audit enrichment migrations, purge helpers, AR Windows scripts — included so a fresh clone can rebuild |

## 2. Redeploy checklist (new infra)

1. Clone this repo; copy `.env` from a secure store (**never** commit `.env` / `.secrets/`).
2. Apply postgres init / migrations under `postgres/init/` (including `016`–`020` if not already applied).
3. `docker compose up -d --build` on the control-plane host.
4. Provision tenants / engine bindings; download **fresh** per-tenant agent packages (do not reuse old ZIPs).
5. **Windows endpoints:** run telemetry bootstrap (or new Windows package) before expecting process-tree alerts.
6. Validate:
   - `./scripts/kb088_validate_user_management.sh`
   - `./scripts/kb088_validate_windows_telemetry_onboarding.sh`
   - `python3 scripts/validate_user_management.py`
   - Portal login: customer user must **fail** on `:3000` with portal=admin

## 3. Operational standards (do not regress)

- **Collect ≠ alert:** Sysmon enables filtered process telemetry; Wazuh rules + SOC visibility decide alerts/customer view.
- **Agent package = tenant-specific:** Folder/script embeds Wazuh group; never reuse Melvik/old customer packages on a new tenant.
- **Hard delete users:** Prefer `inactive`/`locked` (audit trail).
- **URLs:** Admin `http://<host>:3000`, Customer `http://<host>:3001` (not port 80).

## 4. Key paths

| Path | Role |
|------|------|
| `scripts/bootstrap_windows_telemetry.ps1` | Existing Windows host telemetry fix |
| `scripts/sysmon-windows-baseline.xml` | Filtered Sysmon config |
| `backend-api/app/services/agent_package_builder.py` | Per-tenant agent ZIP (Windows includes telemetry) |
| `backend-api/app/api/routes/delegated_user_management_v1.py` | V1 user APIs |
| `backend-api/app/api/routes/auth.py` | Portal login enforcement |
| `frontend-*/vite.config.ts` + `nginx.conf` | SPA routing /assets fix |
| `scripts/validate_user_management.py` | E2E user-mgmt + cleanup |

## 5. Validation notes

- User management E2E script: PASS (with auto tenant cleanup).
- Windows telemetry packaging: `kb088_validate_windows_telemetry_onboarding.sh` PASS (9 checks).
- Live Windows Sysmon install is **operator-run** on the endpoint (elevated PowerShell); not executed from this doc.
