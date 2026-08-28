-- Admin-only CUSTOM tier — à-la-carte capability bundle (not a public SKU).

DO $$
BEGIN
    ALTER TYPE subscription_tier ADD VALUE 'CUSTOM';
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

COMMENT ON COLUMN tenants.subscription_tier IS
    'Commercial tier: SILVER / GOLD / PLATINUM (standard SKUs) or CUSTOM (admin-only bespoke bundle).';
