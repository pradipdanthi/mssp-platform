# KB-035 — Customer Appliance Detail UI

Status: Validated (pending tag).  
Branch: `kb035-customer-appliance-detail-ui`

## Purpose

Let a logged-in customer open one appliance from the Assets list and view **read-only, customer-safe posture detail**, including linked protected assets. No create/edit/rotate workflow. No admin APIs. No IP or credential exposure.

## Tables used

Primary: `appliances` and latest row from `appliance_heartbeats` (same safe posture fields as KB-023 list).

Linked: `protected_assets` filtered by `appliance_id` for a customer-safe sub-list (hostname links to existing asset detail).

## Endpoints

### List (updated)

`GET /customer/assets/{short_code}` — appliances array now includes **`appliance_id`** so the Assets page can link to detail.

### Detail (new)

```http
GET /customer/appliances/{short_code}/{appliance_id}
Authorization: Bearer <access_token>
```

Auth: `get_current_user` → resolve tenant by `short_code` → `require_tenant_match` (404 on mismatch) → parameterized:

```sql
WHERE a.tenant_id = %s AND a.id = %s
```

Missing row or wrong tenant → **404** (not 403).

## Response shape

```json
{
  "tenant": { "id": "...", "name": "...", "short_code": "DEMO" },
  "appliance": {
    "appliance_id": "<uuid>",
    "appliance_name": "...",
    "site_name": "...",
    "status": "online",
    "last_seen_at": "...",
    "health_status": "healthy",
    "cpu_percent": 12.5,
    "memory_percent": 40.0,
    "disk_percent": 55.0,
    "agent_version": "...",
    "config_version": "...",
    "update_status": "current",
    "latest_heartbeat_at": "...",
    "protected_assets_count": 1,
    "protected_assets": [
      {
        "asset_id": "<uuid>",
        "hostname": "...",
        "asset_type": "server",
        "criticality": "high",
        "status": "active",
        "last_seen_at": "..."
      }
    ]
  }
}
```

## Safe fields

**Appliance:** `appliance_id`, `appliance_name`, `site_name`, `status`, `last_seen_at`, heartbeat health %, `agent_version`, `config_version`, `update_status`, `latest_heartbeat_at`, `protected_assets_count`, linked `protected_assets` (safe asset list fields only).

## Hidden / forbidden fields

IPs (`local_ip`, `last_source_ip`, heartbeat `source_ip`), `appliance_uuid`, `health_snapshot`, heartbeat/asset `details` JSON, API keys/hints/hashes, activation tokens, `tenant_id` on appliance object, `git_commit`, admin notes, stack traces, backend internals.

## Tenant isolation

DEMO customer cannot load DEMO2 appliance detail (404). Guessed/nonexistent UUIDs return 404.

## Frontend behavior

- `getCustomerApplianceDetail(shortCode, applianceId)` → `/api/customer/appliances/{shortCode}/{applianceId}`
- Route `/appliances/:applianceId` (`ApplianceDetailPage.tsx`)
- Assets page: appliance **name** links to detail; protected-asset hostname links unchanged
- Loading / error / not_found / forbidden; read-only detail + linked assets table; Back to assets
- No `/admin` under `frontend-customer/src`

## Validation command

```bash
cd /opt/mssp-control
chmod +x scripts/kb035_validate_customer_appliance_detail_ui.sh
./scripts/kb035_validate_customer_appliance_detail_ui.sh
```

The script prompts for the `customer.viewer@demo.local` password. It creates temporary DEMO/DEMO2 appliances and protected assets, proves filtering and response shape, then cleans up.

Expected final line: `KB-035 CUSTOMER APPLIANCE DETAIL UI VALIDATION PASSED`

## Manual browser checklist

1. Open `http://localhost:3001`, sign in as `customer.viewer@demo.local`.
2. Open **Assets**, click an appliance name.
3. Confirm detail shows posture fields and linked protected assets; **Back to assets** works.
4. Click a linked asset hostname and confirm asset detail loads.
5. Network: only `/api/customer/appliances/...` and `/api/customer/assets/...` — never `/admin/*`.

## Deferred

- Heartbeat history charts
- Alerts/incidents per appliance
- Customer edit of appliance metadata
- Credential or activation-token visibility
- Dashboard appliance links
