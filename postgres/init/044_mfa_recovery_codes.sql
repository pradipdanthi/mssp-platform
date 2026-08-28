-- KB-111: MFA recovery codes + mandatory tenant MFA policy.

BEGIN;

ALTER TABLE platform_users
    ADD COLUMN IF NOT EXISTS mfa_recovery_codes JSONB;

COMMENT ON COLUMN platform_users.mfa_recovery_codes IS
    'Hashed single-use emergency backup codes: [{hash, used_at}, ...].';

ALTER TABLE tenants
    ADD COLUMN IF NOT EXISTS enforce_mfa BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN tenants.enforce_mfa IS
    'When true, customer portal users must enroll MFA before accessing the tenant.';

COMMIT;
