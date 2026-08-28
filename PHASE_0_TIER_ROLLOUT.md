# Phase 0 — Tier-only commercial model (NikTiar)

**Status:** P0 + P1 implemented; uniformity router (U2) + CUSTOM tier + downgrade path (2026-08-28).

## Uniformity

One tier model for cloud SOC and NikTiar Edge. See **`PLATFORM_SERVICE_UNIFORMITY.md`**.  
Tier rollout calls `fulfill_tier_change()` — upgrades use `fulfill_tier_capabilities()`; downgrades use `fulfill_tier_downgrade()`.

## Phase 0 scope

### P0 — Tier rollout becomes end-to-end

1. **`POST /admin/tenants/tier-rollout`** after `sync_entitlements_for_tier()`:
   - **All tenants:** deployment-aware cloud adapter sync via `capability_fulfillment_service` (skips duplicate cloud engine sync when appliance owns the workload locally).
   - **Appliance tenants** (`on_prem_appliance`, `cloud_appliance`, `hybrid`): signed license from entitlement flags → `apply_entitlements` on every online appliance.
2. **Downgrade path:** `fulfill_tier_downgrade()` — revoked module schedulers stopped, asset coverage cleared, reduced appliance license pushed.

### P1 — Retire per-module rollout as primary ops

3. Admin Service Catalog: reference/pricing + **Provision tier upgrade** / **Provision custom tier** full pages (`/services/tier-rollout`, `/services/custom-tier`).
4. Customer portal: tier upgrade requests only (`tier_gold`, `tier_platinum`).
5. `POST /admin/service-catalog/{key}/rollout` — **break-glass / MSSP exception only** (labeled in OpenAPI + API response `break_glass: true`).

### P2 — Asset coverage default

6. Tier entitlement = **all active protected assets** (empty `tenant_asset_service_coverage` = all — VMAAS already supports this).

## Deployment matrix

| Mode | Tier rollout must |
|------|-------------------|
| `cloud` / `on_prem_direct` | Postgres entitlements + API gates + cloud engine syncs |
| `on_prem_appliance` / `cloud_appliance` / `hybrid` | Same entitlements + portal gates + local engines via license JWS (`svc-*` derived from flags) + cloud-only TheHive/Shuffle |

## References

- `PRODUCT_TIER_SOURCE_OF_TRUTH.md`
- `capability_fulfillment_service.py`
- `subscription_tier_service.py`
- `appliance_entitlement_sync.py`
- `TierRolloutPage.tsx`, `CustomTierProvisionPage.tsx`
