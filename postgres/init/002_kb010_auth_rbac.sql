-- KB-010: Authentication + Role-Based Access Control (schema additions)
--
-- IMPORTANT: PostgreSQL only runs files in postgres/init/ automatically the
-- first time it initializes a brand-new, empty data volume. It will NOT
-- automatically apply to the existing mssp-postgres database, because that
-- database already has data in it. This file exists so any FUTURE fresh
-- install gets these changes automatically. For the already-running
-- environment, apply the same change using scripts/kb010_create_auth_rbac.sh
-- instead, which runs the equivalent statements directly against the live
-- database.
--
-- Changes:
--   1. Adds platform_users.password_hash (nullable) to support secure,
--      bcrypt-based password login. Nullable so it never breaks existing
--      rows - a NULL password_hash simply means that account cannot log in
--      with a password yet.
--   2. Renames the top platform-admin role value from 'super_admin' to
--      'platform_admin' in the role CHECK constraint, and updates any
--      existing rows that still use the old value.
--
-- This script is idempotent and safe to run more than once.

ALTER TABLE platform_users ADD COLUMN IF NOT EXISTS password_hash TEXT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'platform_users_role_check'
    ) THEN
        ALTER TABLE platform_users DROP CONSTRAINT platform_users_role_check;
    END IF;
END $$;

UPDATE platform_users SET role = 'platform_admin' WHERE role = 'super_admin';

ALTER TABLE platform_users
    ADD CONSTRAINT platform_users_role_check
    CHECK (role IN ('platform_admin', 'soc_manager', 'soc_analyst', 'customer_admin', 'customer_viewer'));
