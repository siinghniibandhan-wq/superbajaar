-- Apply explicitly to the existing production database before enabling account APIs.
-- This migration creates only new user-management tables and does not modify catalogue data.
CREATE TABLE IF NOT EXISTS app_users (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'customer'
        CHECK (role IN ('super_admin', 'admin', 'staff', 'customer')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'disabled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_login TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS app_users_email_lower_unique ON app_users (lower(email));
CREATE INDEX IF NOT EXISTS app_users_role_status_idx ON app_users (role, status);
CREATE TABLE IF NOT EXISTS user_audit_log (
    id BIGSERIAL PRIMARY KEY,
    actor_user_id BIGINT REFERENCES app_users(id) ON DELETE SET NULL,
    target_user_id BIGINT REFERENCES app_users(id) ON DELETE SET NULL,
    action TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS user_audit_log_created_idx ON user_audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS user_audit_log_target_idx ON user_audit_log (target_user_id, created_at DESC);
