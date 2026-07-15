# KB-023 — Customer Assets API and Assets Page

Status: Implemented (pending commit).  
Branch: `kb023-customer-assets-api-ui`

## Purpose

Give each customer a dedicated, read-only **Assets** page (port 3001) that loads **appliance posture** and **protected assets** for their own tenant from a tenant-scoped customer API. The customer UI never calls admin appliance/asset endpoints and never shows credentials or raw internals.

## Endpoint

```http
GET /customer/assets/{short_code}
Authorization: Bearer <access_token>
```

Auth and tenant rules match dashboard/incidents/alerts (KB-011):

1. Caller must be authenticated (`get_current_user`).
2. Tenant is resolved by `short_code` (404 if missing).
3. `require_tenant_match` — customer roles may only access their own tenant; mismatch returns **404** (not 403).
4. Both SQL queries filter by `tenant_id` with parameterized binds.

### Response shape

```json
{
  "tenant": { "id": "...", "name": "...", "short_code": "DEMO" },
  "appliances": [
    {
      "appliance_name": "...",
      "site_name": "...",
      "status": "online",
      "last_seen_at": "...",
      "health_status": "healthy",
      "cpu_percent": 12.5,
      "memory_percent": 40.0,
      "disk_percent": 55.0,
      "agent_version": "..."
    }
  ],
  "assets": [
    {
      "asset_id": "<uuid>",
      "hostname": "...",
      "asset_type": "server",
      "criticality": "high",
      "status": "active",
      "os_name": "...",
      "owner": "...",
      "last_seen_at": "...",
      "appliance_name": "...",
      "site_name": "..."
    }
  ]
}
```

Arrays may be empty. Appliances and assets are each limited to 200 rows.

### Safe fields returned

**Appliances:** name, site, status, last_seen_at, latest heartbeat health %, agent_version.

**Assets:** asset_id, hostname, asset_type, criticality, status, os_name, owner, last_seen_at, linked appliance_name/site_name.

### Hidden fields

- Appliance API keys, `appliance_api_key_hash`, `appliance_api_key_hint`, key created/last-used timestamps
- Activation tokens / token hashes / token hints
- `health_snapshot` and heartbeat/asset `details` JSONB
- `source_ip`, `local_ip`, `last_source_ip`, asset `ip_address`
- Password hashes, admin notes, raw logs

## Tenant isolation

Customer DEMO accounts cannot load `/customer/assets/DEMO2` (404). SOC/platform roles retain cross-tenant support read access via the same `require_tenant_match` exemption used elsewhere.

## Frontend behavior

- `frontend-customer/src/api/customer.ts` — `getCustomerAssets(shortCode)` calls `/api/customer/assets/{shortCode}` only.
- `frontend-customer/src/pages/AssetsPage.tsx` — no longer uses the dashboard endpoint; shows loading/error/empty states and two read-only tables (appliances + protected assets).
- No `/admin` paths under `frontend-customer/src`.

## Files touched

| Path | Change |
|---|---|
| `backend-api/app/api/routes/customer.py` | Added `GET /assets/{short_code}` |
| `frontend-customer/src/api/customer.ts` | Types + `getCustomerAssets` |
| `frontend-customer/src/pages/AssetsPage.tsx` | Real assets UI |
| `scripts/kb023_validate_customer_assets_api_ui.sh` | Validation gate |
| `docs/KB023_CUSTOMER_ASSETS_API_UI.md` | This document |

Not modified: `.env`, `postgres/init/`, `docker-compose.yml`, `frontend-admin/`, database rows.

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb023_validate_customer_assets_api_ui.sh
./scripts/kb023_validate_customer_assets_api_ui.sh
```

Or non-interactive:

```bash
CUSTOMER_VIEWER_PASSWORD='...' ./scripts/kb023_validate_customer_assets_api_ui.sh
```

Expected final line:

```text
KB-023 CUSTOMER ASSETS API UI VALIDATION PASSED
```

## Manual browser checklist

1. Open `http://localhost:3001` and sign in as `customer.viewer@demo.local`.
2. Open **Assets** — Network shows `/api/customer/assets/...` (not dashboard, not `/admin/*`).
3. Confirm appliance table and/or protected-assets table (or empty states).
4. Confirm no credential, IP, or raw JSON fields appear.
5. Sign out; unauthenticated access is blocked.

## Deferred

- Customer create/edit/retire of assets or appliances
- Showing asset or appliance IP addresses
- Heartbeat history / detail drawers
- Activation tokens or credential visibility for customers
- Pagination beyond `LIMIT 200`
- Demo seed / DB cleanup
- Admin protected-assets management UI
