-- KB-111 Phase 3: TOTP MFA columns on platform_users.

BEGIN;

ALTER TABLE platform_users
    ADD COLUMN IF NOT EXISTS mfa_secret TEXT,
    ADD COLUMN IF NOT EXISTS is_mfa_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS mfa_updated_at TIMESTAMPTZ;

COMMENT ON COLUMN platform_users.mfa_secret IS
    'Base32 TOTP shared secret; present after setup, enabled after verify.';
COMMENT ON COLUMN platform_users.is_mfa_enabled IS
    'When true, login requires a second-factor TOTP code after password.';
COMMENT ON COLUMN platform_users.mfa_updated_at IS
    'Last time MFA secret or enabled flag was changed.';

COMMIT;
