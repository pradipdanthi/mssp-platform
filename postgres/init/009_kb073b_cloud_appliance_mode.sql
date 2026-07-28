-- KB-073b: Split cloud modes — with vs without onsite appliance.
-- Keeps existing `cloud` (= without appliance). Adds `cloud_appliance`.

ALTER TABLE tenants DROP CONSTRAINT IF EXISTS tenants_deployment_mode_check;

ALTER TABLE tenants
    ADD CONSTRAINT tenants_deployment_mode_check
    CHECK (deployment_mode IN (
        'cloud',
        'cloud_appliance',
        'on_prem_direct',
        'on_prem_appliance',
        'hybrid'
    ));
