# KB-030 — Customer Protected Asset Detail UI

Status: Implemented (pending commit).  
Branch: `kb030-customer-asset-detail-ui`

## Purpose

Let a logged-in customer open one protected asset from the Assets list and view **read-only, customer-safe detail** for that asset only. No create/edit/retire workflow. No appliance detail page. No admin APIs. No IP or credential exposure.

## Table used

Primary: `protected_assets` in `postgres/init/001_mssp_core_schema.sql` — same table as KB-023 list. Detail uses `id` as `asset_id` (no friendly asset number in schema).

Optional safe join: `appliances` for `appliance_name` and `site_name` only (LEFT JOIN). Does not expose `appliance_id`, appliance UUIDs, IPs, credentials, `health_snapshot`, or heartbeat details.

## Endpoint

```http
GET /customer/assets/{short_code}/{asset_id}
Authorization: Bearer <access_token>
```

Auth: `get_current_user` → resolve tenant by `short_code` → `require_tenant_match` (404 on mismatch) → parameterized:

```sql
WHERE pa.tenant_id = %s AND pa.id = %s
```

There is **no** `customer_visible` column on `protected_assets`. Missing row or wrong tenant → **404** (not 403).

## Response shape

```json
{
  "tenant": { "id": "...", "name": "...", "short_code": "DEMO" },
  "asset": {
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
}
```

## Safe fields

`asset_id`, `hostname`, `asset_type`, `criticality`, `status`, `os_name`, `owner`, `last_seen_at`, `appliance_name`, `site_name`.

`asset_id` is the customer-facing detail identifier and is allowed.

## Hidden / forbidden fields

`tenant_id`, `appliance_id`, `protected_asset_id`, `ip_address`, `source_ip`, `local_ip`, `last_source_ip`, `details`, `raw_json`, `raw_event`, `health_snapshot`, `appliance_uuid`, `appliance_api_key_hash`, `appliance_api_key_hint`, activation-token fields, `api_key`, `token`, `token_hash`, `password`, `password_hash`, `internal_notes`, `admin_notes`, `stack_trace`, `created_at`, `updated_at`, backend internals.

## Tenant isolation

DEMO customer cannot load DEMO2 asset detail (404). Guessed/nonexistent UUIDs return 404.

## Frontend behavior

- `getCustomerAssetDetail(shortCode, assetId)` → `/api/customer/assets/{shortCode}/{assetId}`
- Route `/assets/:assetId` (`AssetDetailPage.tsx`)
- Assets page: protected-asset **hostname** links to detail; **appliance rows stay plain text**
- Loading / error / not_found / forbidden; read-only detail table; Back to assets
- No `/admin` under `frontend-customer/src`
- `DashboardPage.tsx` and `Layout.tsx` unchanged

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb030_validate_customer_asset_detail_ui.sh
./scripts/kb030_validate_customer_asset_detail_ui.sh
```

Or: `CUSTOMER_VIEWER_PASSWORD='...' ./scripts/kb030_validate_customer_asset_detail_ui.sh`

Creates temporary DEMO/DEMO2 protected assets (and linked appliances for name/site proof), proves filtering and response shape, then cleans up.

Expected final line: `KB-030 CUSTOMER ASSET DETAIL UI VALIDATION PASSED`

## Manual browser checklist

1. Open `http://localhost:3001`, sign in as `customer.viewer@demo.local`.
2. Open **Assets**, click a protected-asset hostname.
3. Confirm detail shows type, criticality, status, OS, owner, appliance name, site, last seen; **Back to assets** works.
4. Confirm appliance table names are **not** clickable detail links.
5. Network: only `/api/customer/assets/...` — never `/admin/*`.

## Deferred

- Appliance detail page
- Customer asset create/edit/retire workflow
- Asset comments
- Vulnerability/evidence view
- Alert history per asset
- Asset IP visibility policy
- Admin asset publishing controls
