-- Customer authentication and referral foundations.
-- Idempotent: creates only new customer/referral objects; preserves existing schema files and data.
CREATE TABLE IF NOT EXISTS customer_accounts (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    phone TEXT,
    password_hash TEXT NOT NULL,
    referral_code TEXT NOT NULL UNIQUE,
    referred_by_customer_id BIGINT REFERENCES customer_accounts(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (length(trim(email)) > 3),
    CHECK (length(trim(full_name)) > 0),
    CHECK (length(trim(referral_code)) >= 6),
    CHECK (referred_by_customer_id IS NULL OR referred_by_customer_id <> id)
);
CREATE INDEX IF NOT EXISTS customer_accounts_referrer_idx
    ON customer_accounts (referred_by_customer_id, created_at DESC);

CREATE TABLE IF NOT EXISTS customer_sessions (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customer_accounts(id) ON DELETE CASCADE,
    token_id TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS customer_sessions_customer_active_idx
    ON customer_sessions (customer_id, expires_at DESC) WHERE revoked_at IS NULL;

-- Referral tracking is separate from reward issuance. Rewards remain disabled until
-- the business confirms beneficiary, amount and trigger (registration vs delivered order).
CREATE TABLE IF NOT EXISTS customer_referrals (
    id BIGSERIAL PRIMARY KEY,
    referrer_customer_id BIGINT NOT NULL REFERENCES customer_accounts(id),
    referred_customer_id BIGINT NOT NULL UNIQUE REFERENCES customer_accounts(id),
    referral_code TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'tracked'
        CHECK (status IN ('tracked', 'eligible', 'rewarded', 'rejected')),
    reward_coins INTEGER NOT NULL DEFAULT 0 CHECK (reward_coins >= 0),
    reward_trigger TEXT
        CHECK (reward_trigger IS NULL OR reward_trigger IN ('registration', 'first_order_delivered')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (referrer_customer_id <> referred_customer_id)
);
CREATE INDEX IF NOT EXISTS customer_referrals_referrer_idx
    ON customer_referrals (referrer_customer_id, created_at DESC);

-- Keep the existing loyalty card keyed to the same normalized customer email.
-- Card creation is handled by the customer registration endpoint.
