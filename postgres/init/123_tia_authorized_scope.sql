-- 123: approved scanner activity may name a destination scope (CIDR and/or hostname).
-- Additive. Existing rows keep NULL scope, which means "any destination" — the previous behaviour.
-- A scan whose destination is outside a named scope is refused; that is not a false positive.

ALTER TABLE tia_authorized_activity
    ADD COLUMN IF NOT EXISTS destination_cidr CIDR,
    ADD COLUMN IF NOT EXISTS destination_host TEXT;

COMMENT ON COLUMN tia_authorized_activity.destination_cidr IS
    'Optional. When set, the alert destination address must fall in this network.';
COMMENT ON COLUMN tia_authorized_activity.destination_host IS
    'Optional. When set, the alert destination host must match this name (case-insensitive).';

INSERT INTO tia_schema_version (component, version) VALUES ('tia_authorized_scope', 123)
ON CONFLICT (component) DO UPDATE SET version = GREATEST(tia_schema_version.version, EXCLUDED.version);
