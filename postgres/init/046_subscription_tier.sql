-- KB-111 Phase 7: Subscription tier enum, tenant column, and entitlement sync.

DO $$
BEGIN
    CREATE TYPE subscription_tier AS ENUM ('SILVER', 'GOLD', 'PLATINUM');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS subscription_tier subscription_tier NOT NULL DEFAULT 'SILVER';

CREATE INDEX IF NOT EXISTS idx_tenants_subscription_tier
    ON tenants (subscription_tier);

COMMENT ON COLUMN tenants.subscription_tier IS
    'Commercial tier: SILVER (ITDR), GOLD (+MDR/EDR/EASM/VMaaS), PLATINUM (+NDR/DFIR/hunts/OLAP).';

-- All tenants (including demo QA) start at SILVER; upgrade via admin tier rollout.
