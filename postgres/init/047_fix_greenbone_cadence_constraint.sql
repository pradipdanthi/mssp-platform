-- Phase 4: Allow Platinum-tier daily Greenbone cadence in tenant_entitlements.

ALTER TABLE tenant_entitlements
    DROP CONSTRAINT IF EXISTS tenant_entitlements_greenbone_cadence_check;

ALTER TABLE tenant_entitlements
    ADD CONSTRAINT tenant_entitlements_greenbone_cadence_check
    CHECK (greenbone_cadence IN ('weekly', 'monthly', 'daily', 'off'));

-- Align demo Platinum tenant with PLATINUM_ENTITLEMENTS bundle.
UPDATE tenant_entitlements te
SET greenbone_cadence = 'daily',
    updated_at = now()
FROM tenants t
WHERE te.tenant_id = t.id
  AND upper(t.short_code) = 'ALPHAWINCORP-6VS2'
  AND t.subscription_tier = 'PLATINUM';
