-- KB-073: Tenant deployment mode + cloud provider (customer onboarding).
-- Additive only. Existing tenants default to cloud.

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS deployment_mode TEXT NOT NULL DEFAULT 'cloud';

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS cloud_provider TEXT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tenants_deployment_mode_check'
    ) THEN
        ALTER TABLE tenants
            ADD CONSTRAINT tenants_deployment_mode_check
            CHECK (deployment_mode IN (
                'cloud',
                'on_prem_direct',
                'on_prem_appliance',
                'hybrid'
            ));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'tenants_cloud_provider_check'
    ) THEN
        ALTER TABLE tenants
            ADD CONSTRAINT tenants_cloud_provider_check
            CHECK (
                cloud_provider IS NULL
                OR cloud_provider IN ('aws', 'azure', 'gcp', 'other')
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_tenants_deployment_mode
    ON tenants (deployment_mode);
