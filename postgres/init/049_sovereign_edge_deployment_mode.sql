-- KB-112: NikTiar Sovereign Edge — air-gapped on-prem full-stack deployment mode.
-- Same subscription tiers; local fulfillment only; offline license delivery.

ALTER TABLE tenants DROP CONSTRAINT IF EXISTS tenants_deployment_mode_check;

ALTER TABLE tenants
    ADD CONSTRAINT tenants_deployment_mode_check
    CHECK (deployment_mode IN (
        'cloud',
        'cloud_appliance',
        'on_prem_direct',
        'on_prem_appliance',
        'hybrid',
        'sovereign_edge'
    ));
