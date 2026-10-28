-- Super Bajaar loyalty programme and partner enquiries.
-- Idempotent: safe to apply more than once; does not modify existing tables.
CREATE TABLE IF NOT EXISTS loyalty_rules (
    id BIGSERIAL PRIMARY KEY,
    scope_type TEXT NOT NULL CHECK (scope_type IN ('default', 'category', 'product')),
    scope_id BIGINT,
    coins_per_100 NUMERIC(10, 4) NOT NULL DEFAULT 1 CHECK (coins_per_100 >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT loyalty_rules_scope_id_check CHECK (
        (scope_type = 'default' AND scope_id IS NULL) OR
        (scope_type IN ('category', 'product') AND scope_id IS NOT NULL AND scope_id > 0)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS loyalty_rules_scope_unique
    ON loyalty_rules (scope_type, COALESCE(scope_id, 0));
INSERT INTO loyalty_rules (scope_type, scope_id, coins_per_100, is_active)
VALUES ('default', NULL, 1, TRUE)
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS loyalty_accounts (
    id BIGSERIAL PRIMARY KEY,
    customer_email TEXT NOT NULL UNIQUE,
    card_number TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS loyalty_transactions (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL REFERENCES loyalty_accounts(id),
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('earn', 'redeem', 'expire', 'adjustment')),
    coins INTEGER NOT NULL CHECK (coins > 0),
    order_reference TEXT,
    description TEXT,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    idempotency_key TEXT UNIQUE,
    CHECK (
      (transaction_type = 'earn' AND expires_at IS NOT NULL) OR
      (transaction_type <> 'earn' AND expires_at IS NULL)
    )
);
CREATE INDEX IF NOT EXISTS loyalty_transactions_account_created
    ON loyalty_transactions (account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS loyalty_transactions_expiry
    ON loyalty_transactions (account_id, expires_at) WHERE transaction_type = 'earn';

CREATE TABLE IF NOT EXISTS loyalty_redemption_allocations (
    id BIGSERIAL PRIMARY KEY,
    redemption_transaction_id BIGINT NOT NULL REFERENCES loyalty_transactions(id),
    earned_transaction_id BIGINT NOT NULL REFERENCES loyalty_transactions(id),
    coins INTEGER NOT NULL CHECK (coins > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (redemption_transaction_id, earned_transaction_id)
);

CREATE TABLE IF NOT EXISTS partner_enquiries (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    business_name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    partnership_type TEXT NOT NULL CHECK (partnership_type IN ('Seller', 'Brand', 'Supplier', 'Delivery / logistics', 'Other')),
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'reviewing', 'contacted', 'accepted', 'declined', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS partner_enquiries_status_created
    ON partner_enquiries (status, created_at DESC);
