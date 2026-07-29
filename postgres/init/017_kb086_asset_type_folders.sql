-- KB-086: Expand protected_assets.asset_type for network gear folders (additive).

ALTER TABLE protected_assets
  DROP CONSTRAINT IF EXISTS protected_assets_asset_type_check;

ALTER TABLE protected_assets
  ADD CONSTRAINT protected_assets_asset_type_check
  CHECK (asset_type IN (
    'server',
    'workstation',
    'firewall',
    'switch',
    'load_balancer',
    'network_device',
    'application',
    'database',
    'other'
  ));
